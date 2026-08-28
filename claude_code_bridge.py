"""Claude 常驻会话桥：anthropic SDK 流式对话，跨重启保持上下文。

- 会话历史持久化到 session_history.json，重启后仍记得之前的对话
- 流式增量：on_delta(text) 逐块回调（首块约 3-4 秒到达）
- web_search 工具：需要实时信息时委托 claude -p（CLI 自带 WebSearch，权限已配好）
- interrupt() / stop_check：中断当前生成（空格打断）

环境：自动读取 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_MODEL。
"""
import json
import os
import re
import subprocess
import threading

import anthropic

import config

SYSTEM_PROMPT = (
    "你是贾维斯（JARVIS），钢铁侠的 AI 管家，语气沉稳、专业、带一点英式幽默。"
    "用和用户输入相同的语言回答；口语化、简短，最多三句话。"
    "涉及实时信息（天气、新闻、最新数据等）时，调用 web_search 工具，不要凭记忆回答。"
    "用户要求打开网页、启动应用或打开文件/文件夹时，调用 run_command 工具；"
    "文件路径不清楚时先用 list_dir 查找目录内容，再打开；"
    "用户要求退出、关闭或结束贾维斯程序本身时，调用 exit_self 工具；"
    "用户要求最小化、隐藏或收起界面时，调用 hide_self 工具；"
    "永远不要用文字推辞说做不到——优先尝试调用工具。"
)

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "搜索互联网获取实时信息（天气、新闻、最新数据等）。用户问实时问题时必须调用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，例如：洛杉矶今天天气"},
        },
        "required": ["query"],
    },
}

RUN_COMMAND_TOOL = {
    "name": "run_command",
    "description": (
        "在用户电脑上执行本地操作：打开网页（start https://...）、"
        "打开应用（start notepad/calc/mspaint/snippingtool/taskmgr/control）、"
        "打开文件（start C:\\path\\file.docx，须完整路径，不清楚先用 list_dir）、"
        "打开文件夹（explorer C:\\path 或 explorer）。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "动作命令，例如：start https://www.baidu.com / start notepad / start C:\\docs\\报告.docx / explorer D:\\"},
        },
        "required": ["action"],
    },
}

LIST_DIR_TOOL = {
    "name": "list_dir",
    "description": "列出目录内容，用于查找文件。用户要打开某个文件但路径不清楚时先调用此工具。",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径，例如：D:\\、C:\\Users\\10956\\Desktop、E:\\jarvis-voice"},
        },
        "required": ["path"],
    },
}

EXIT_SELF_TOOL = {
    "name": "exit_self",
    "description": "退出贾维斯程序本身（用户要求退出、关闭、结束程序时说再见时调用）。",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

HIDE_SELF_TOOL = {
    "name": "hide_self",
    "description": "隐藏贾维斯的全息界面（用户说最小化、隐藏界面、收起时调用）。隐藏后用户喊「贾维斯」即可唤醒恢复界面。",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def _strip_blocks(content) -> list:
    """把 SDK 内容块转成纯 dict，并去掉 thinking 块（避免回放兼容性/序列化问题）。"""
    out = []
    for b in content:
        t = getattr(b, "type", None)
        if t in ("thinking", "redacted_thinking") or t is None:
            continue
        out.append(b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else b)
    return out


def _is_empty_content(content) -> bool:
    """判定消息内容是否为空。历史里偶发混入空 content 的毒数据会让 API 400
    （all messages must have non-empty content），加载时必须过滤掉。"""
    if not content:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                if b.get("type") in ("tool_use", "tool_result"):
                    return False
                if str(b.get("text", "") or "").strip():
                    return False
        return True
    return False


def _has_tool_result(msg: dict) -> bool:
    """消息内容里是否含 tool_result 块（无配对 tool_use 时 API 会 400）。"""
    c = msg.get("content")
    return (isinstance(c, list)
            and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c))


def _normalize_token(tok: str) -> str:
    """规范化密钥前缀：Windows 用户环境里存的密钥可能缺 sk- 前缀，
    桌面图标启动（走系统环境）时会被网关拒绝认证 → 每轮"服务暂时不可用"。"""
    tok = (tok or "").strip()
    if tok and not tok.lower().startswith(("sk-", "bearer ")):
        tok = "sk-" + tok
    return tok


class ClaudeSession:
    """线程安全的常驻会话。voice_loop 每轮调用 run()。"""

    def __init__(self):
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        token = _normalize_token(os.environ.get("ANTHROPIC_AUTH_TOKEN", ""))
        self._client = anthropic.Anthropic(base_url=base_url or None,
                                           auth_token=token or None)
        print(f"[Session] 端点 {base_url or '默认'}，密钥 {token[:6] + '...' if token else '缺失'}")
        self._model = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]")
        self._lock = threading.Lock()
        self._messages = self._load_history()
        self._aborted = False
        self.was_aborted = False    # run() 结束后可查询：本轮是否被用户打断
        self._tools_broken = False   # 网关不支持工具时降级为纯对话
        self.exit_requested = False  # 用户要求退出程序：voice_loop 播报完本轮后处理
        self.hide_requested = False  # 用户要求隐藏界面：voice_loop 播报完本轮后处理
        self.on_open_action = None   # 成功打开文件/网页后回调：main.py 注入"界面自动让位"

    # ---- 历史持久化：跨重启保持记忆 ----
    def _load_history(self) -> list:
        try:
            with open(config.SESSION_HISTORY, encoding="utf-8") as f:
                msgs = json.load(f)
            if isinstance(msgs, list):
                msgs = [
                    m for m in msgs
                    if isinstance(m, dict)
                    and m.get("role") in ("user", "assistant")
                    and not _is_empty_content(m.get("content"))
                ]
            if isinstance(msgs, list) and msgs:
                msgs = msgs[-(config.SESSION_MAX_TURNS * 2):]
                # 截断可能从一次工具调用的中间切开：开头的 tool_result 成了
                # 孤儿（对应 tool_use 被截掉），API 会 400 卡死，必须丢弃
                while (msgs and msgs[0].get("role") == "user"
                       and _has_tool_result(msgs[0])):
                    msgs.pop(0)
                return msgs
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save_history(self) -> None:
        try:
            with open(config.SESSION_HISTORY, "w", encoding="utf-8") as f:
                json.dump(self._messages, f, ensure_ascii=False)
        except OSError:
            pass

    def clear_history(self) -> None:
        with self._lock:
            self._messages = []
            self._save_history()

    def interrupt(self) -> None:
        """中断当前生成（跨线程安全，从 TTS 线程调用）。"""
        self._aborted = True

    # ---- 主入口 ----
    def run(self, user_text: str, on_delta, stop_check=None) -> str:
        """流式发送 user_text，逐块回调 on_delta(text)。

        返回完整回复文本；被中断则返回已生成的部分。
        stop_check() 返回 True 时立刻中断（空格打断生成）。
        """
        with self._lock:
            self._aborted = False
            self._messages.append({"role": "user", "content": user_text})
            parts: list[str] = []
            try:
                for _ in range(3):   # 工具循环：提问 → 搜索 → 总结，最多 3 轮
                    if self._aborted:
                        break
                    final = self._stream_once(parts, on_delta, stop_check)
                    if self._aborted or final is None:
                        break
                    if final.stop_reason != "tool_use":
                        stripped = _strip_blocks(final.content)
                        if stripped:   # 只有 thinking 块的回复不写入历史（网关拒绝空 content）
                            self._messages.append({"role": "assistant", "content": stripped})
                        break
                    # 执行工具并回填结果
                    stripped = _strip_blocks(final.content)
                    if stripped:
                        self._messages.append({"role": "assistant", "content": stripped})
                    results = []
                    for block in final.content:
                        if block.type == "tool_use":
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": self._execute_tool(block),
                            })
                    if not results:
                        break
                    self._messages.append({"role": "user", "content": results})
            except anthropic.APIStatusError as e:
                print(f"[Session] API 错误（{e.status_code}）：{str(e)[:200]}")
                # 回滚本轮刚追加的 user 消息：若它是被 API 拒绝的坏消息，
                # 留在历史里会让后续每一轮都 400 卡死
                try:
                    if (self._messages
                            and self._messages[-1].get("role") == "user"
                            and self._messages[-1].get("content") == user_text):
                        self._messages.pop()
                except Exception:
                    pass
                if not parts:
                    for ch in "抱歉，服务暂时不可用，请稍后再试。":
                        parts.append(ch)
                        on_delta(ch)   # 兜底文案也要走 UI 打字机 + 语音播报
            except anthropic.APIConnectionError as e:
                print(f"[Session] 连接错误：{str(e)[:200]}")
                if not parts:
                    for ch in "抱歉，网络连接失败，请检查网络后重试。":
                        parts.append(ch)
                        on_delta(ch)
            text = "".join(parts).strip()
            if self._aborted and text:
                # 被打断的回复也记入历史，保持上下文连贯
                self._messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            self._save_history()
            self.was_aborted = self._aborted
            return text

    def _stream_once(self, parts, on_delta, stop_check):
        """单轮流式请求。返回 final message；中断/降级返回 None。"""
        kwargs = dict(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=self._messages,
        )
        if not self._tools_broken:
            kwargs["tools"] = [WEB_SEARCH_TOOL, RUN_COMMAND_TOOL, LIST_DIR_TOOL,
                               EXIT_SELF_TOOL, HIDE_SELF_TOOL]
        try:
            stream = self._client.messages.stream(**kwargs)
        except anthropic.BadRequestError as e:
            # 网关不支持工具 → 降级为纯对话模式
            print(f"[Session] 工具调用被拒绝（{str(e)[:120]}），降级为纯对话")
            self._tools_broken = True
            kwargs.pop("tools", None)
            stream = self._client.messages.stream(**kwargs)
        with stream as st:
            for event in st:
                if self._aborted or (stop_check and stop_check()):
                    self._aborted = True
                    break
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    parts.append(event.delta.text)
                    on_delta(event.delta.text)
        if self._aborted:
            return None
        return st.get_final_message()

    # ---- 工具分发 ----
    def _execute_tool(self, block) -> str:
        name = getattr(block, "name", "")
        if name == "web_search":
            return self._run_web_search(block)
        if name == "run_command":
            return self._run_command(block)
        if name == "list_dir":
            return self._run_list_dir(block)
        if name == "exit_self":
            return self._run_exit_self(block)
        if name == "hide_self":
            return self._run_hide_self(block)
        return f"（未知工具：{name}）"

    # ---- web_search 工具：委托 claude -p（CLI 自带 WebSearch）----
    def _run_web_search(self, block) -> str:
        query = str((block.input or {}).get("query", ""))[:200]
        print(f"[Tool] web_search: {query}")
        prompt = (f"用 WebSearch 搜索：{query}。"
                  f"用 150 字以内简要总结关键信息，列出关键数据。")
        try:
            r = subprocess.run(
                [config.CLAUDE_BIN, "-p", prompt],
                capture_output=True, text=True, encoding="utf-8",
                timeout=config.TOOL_TIMEOUT,
            )
            out = r.stdout.strip()
            if r.returncode != 0:
                out = (r.stderr or "").strip() or out
            return out[:1500] if out else "（搜索无结果）"
        except subprocess.TimeoutExpired:
            return "（搜索超时）"
        except OSError as e:
            return f"（搜索失败：{e}）"

    # ---- run_command 工具：允许列表校验后执行本地操作 ----
    _URL_CMD = re.compile(r"^start\s+(https?://\S+|www\.\S+)\s*$", re.I)
    _APP_CMD = re.compile(r"^start\s+(notepad|calc|mspaint|snippingtool|taskmgr|control|explorer)\s*$", re.I)
    _EXPLORER_CMD = re.compile(r"^explorer\s*$", re.I)
    _START_PATH_CMD = re.compile(r'^start\s+"?(\S[^"]*)"?\s*$', re.I)
    _EXPLORER_PATH_CMD = re.compile(r'^explorer\s+"?(\S[^"]*)"?\s*$', re.I)
    _BLOCKED_EXT = {".exe", ".bat", ".cmd", ".msi", ".ps1", ".vbs", ".scr", ".com"}

    def _opened(self) -> None:
        """成功打开东西后的回调：main.py 注入"界面自动让位"（隐藏悬浮窗）。"""
        if self.on_open_action is not None:
            try:
                self.on_open_action()
            except Exception:
                pass

    def _run_command(self, block) -> str:
        action = str((block.input or {}).get("action", "")).strip()[:300]
        print(f"[Tool] run_command: {action}")
        if self._URL_CMD.match(action):
            import webbrowser
            try:
                webbrowser.open(action.split(None, 1)[1])
                self._opened()
                return "（已执行）"
            except Exception as e:
                return f"（执行失败：{e}）"
        if self._APP_CMD.match(action):
            args = ["cmd", "/c", "start", "", action.split(None, 1)[1]]
        elif self._EXPLORER_CMD.match(action):
            args = ["cmd", "/c", "explorer"]
        else:
            # 文件/文件夹：os.startfile（ShellExecute）——cmd /c 链路会破坏
            # 中文路径，explorer 找不到就回退打开"文档"，必须绕开
            m = self._START_PATH_CMD.match(action)
            if m:
                p = m.group(1).strip()
                ext = os.path.splitext(p)[1].lower()
                if ext in self._BLOCKED_EXT:
                    return f"（拒绝执行：{ext} 类型文件不能直接启动）"
                if not os.path.exists(p):
                    return f"（找不到文件：{p}）"
            else:
                m = self._EXPLORER_PATH_CMD.match(action)
                if not m:
                    return f"（拒绝执行，不在允许列表：{action[:80]}）"
                p = m.group(1).strip()
                if not os.path.isdir(p):
                    return f"（找不到文件夹：{p}）"
            try:
                os.startfile(p)
                self._opened()
                return "（已执行）"
            except OSError as e:
                return f"（执行失败：{e}）"
        try:
            subprocess.run(args, capture_output=True, text=True,
                           errors="replace", timeout=20)
            self._opened()
            return "（已执行）"
        except subprocess.TimeoutExpired:
            return "（执行超时）"
        except OSError as e:
            return f"（执行失败：{e}）"

    # ---- list_dir 工具：列出目录内容找文件 ----
    def _run_list_dir(self, block) -> str:
        p = str((block.input or {}).get("path", "")).strip()[:300]
        print(f"[Tool] list_dir: {p}")
        if not os.path.isdir(p):
            return f"（不是有效目录：{p}）"
        try:
            names = sorted(os.listdir(p))[:50]
            return ("目录内容：" + " | ".join(names)) if names else "（空目录）"
        except OSError as e:
            return f"（读取失败：{e}）"

    # ---- exit_self 工具：本轮回复播报完后由 voice_loop 优雅退出 ----
    def _run_exit_self(self, block) -> str:
        print("[Tool] exit_self")
        self.exit_requested = True
        return "（已确认：本轮回复播报完成后自动退出）"

    # ---- hide_self 工具：本轮回复播报完后由 voice_loop 隐藏界面 ----
    def _run_hide_self(self, block) -> str:
        print("[Tool] hide_self")
        self.hide_requested = True
        return "（已确认：本轮回复播报完成后隐藏界面，喊「贾维斯」可唤醒）"
