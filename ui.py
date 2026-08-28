"""全息悬浮 UI：全屏透明无边框置顶窗口 + 科技感文字特效。

- 鼠标穿透（WS_EX_TRANSPARENT）：完全不干扰其他操作
- Ctrl+Alt+Q 全局退出（托盘右键退出仍可用）
- 事件协议与旧版一致，JS 侧每 100ms 轮询：
  {"type":"state","state":"idle|listening|thinking|speaking"}
  {"type":"level","v":0.0~1.0}
  {"type":"message","role":"user|assistant","text":"..."}   # 完整消息（用户输入/最终回复）
  {"type":"chunk","role":"assistant","text":"..."}          # 流式增量（打字机逐块上屏）
  {"type":"quit"}
"""
import ctypes
import os
import pathlib
import queue
import threading

import webview

import config


class UiBridge:
    """线程安全的事件队列，JS 通过 window.pywebview.api.get_events() 轮询。"""

    def __init__(self):
        self._events = queue.Queue()

    def push(self, event: dict) -> None:
        self._events.put(event)

    def get_events(self):
        out = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                return out


def _screen_size():
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


# ---- 鼠标穿透：给本进程所有窗口（含 WebView2 子窗口）设置穿透样式 ----
# 顶层窗口：穿透 + 分层透明 + 不抢焦点 + 不进 Alt+Tab
# 子窗口（WebView2 渲染层）：穿透 + 不抢焦点（子窗口会拦截点击，必须一并处理）
_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_LAYERED = 0x00080000
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080
_TOP_MASK = _WS_EX_TRANSPARENT | _WS_EX_LAYERED | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW
_CHILD_MASK = _WS_EX_TRANSPARENT | _WS_EX_NOACTIVATE

_user32 = ctypes.windll.user32
_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
_user32.EnumWindows.argtypes = [_WNDENUMPROC, ctypes.c_void_p]
_user32.EnumChildWindows.argtypes = [ctypes.c_void_p, _WNDENUMPROC]   # (父窗口, 回调)，无 lParam
_user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
_user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_uint32
_user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32]
# SetWindowLongW 改样式后必须 SetWindowPos(SWP_FRAMECHANGED) 才会真正生效
_user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_uint32]
# 颜色键透明：纯黑像素 → 全透明（页面背景为纯黑，青色内容不受影响）。
# WebView2 窗口化模式不支持逐像素 alpha，这是唯一可靠的"看到桌面"方案。
_user32.SetLayeredWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                               ctypes.c_uint8, ctypes.c_uint32]
_user32.SetLayeredWindowAttributes.restype = ctypes.c_bool

# 窗口过程子类化：WM_NCHITTEST 一律返回 HTTRANSPARENT（鼠标消息穿透）
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_void_p, ctypes.c_uint,
                              ctypes.c_uint64, ctypes.c_longlong)
_user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
_user32.SetWindowLongPtrW.restype = ctypes.c_longlong
_user32.CallWindowProcW.argtypes = [ctypes.c_longlong, ctypes.c_void_p, ctypes.c_uint,
                                    ctypes.c_uint64, ctypes.c_longlong]
_user32.CallWindowProcW.restype = ctypes.c_longlong

_orig_procs: dict = {}   # hwnd -> 原窗口过程地址


def _wnd_proc(hwnd, msg, wparam, lparam):
    if msg == 0x0084:      # WM_NCHITTEST
        return -1          # HTTRANSPARENT：点击穿透到下层窗口
    orig = _orig_procs.get(hwnd)
    if orig is None:
        return 0
    return _user32.CallWindowProcW(orig, hwnd, msg, wparam, lparam)


_HOOKED_PROC = _WNDPROC(_wnd_proc)   # 模块级引用，防止被 GC


def _hook_hit_test(hwnd) -> bool:
    """子类化窗口过程，强制所有鼠标命中测试穿透。"""
    if hwnd in _orig_procs:
        return True
    GWLP_WNDPROC = -4
    orig = _user32.SetWindowLongPtrW(
        hwnd, GWLP_WNDPROC,
        ctypes.cast(_HOOKED_PROC, ctypes.c_void_p).value,
    )
    if not orig:
        return False
    _orig_procs[hwnd] = orig
    return True


def _refresh_window(hwnd) -> None:
    """样式变更后刷新窗口（SWP_FRAMECHANGED），否则 WS_EX_LAYERED 等不生效。"""
    _user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                         0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0010)
    # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE


def _apply_color_key(hwnd) -> bool:
    """纯黑像素变透明（LWA_COLORKEY=1）。返回是否设置成功。"""
    return bool(_user32.SetLayeredWindowAttributes(hwnd, 0x000000, 0, 0x1))

_proc_pid = 0
_tops: list[int] = []
_children: list[int] = []
_sub_list: list[int] = []

# ---- 隐藏/显示（最小化）----
_user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
_ui_hidden = False


def is_ui_hidden() -> bool:
    return _ui_hidden


def toggle_ui_hidden() -> bool:
    """隐藏/显示全息界面：顶层窗 SW_HIDE/SW_SHOW，子窗口随父窗一起隐去。

    隐藏后语音循环照常监听唤醒词；喊「贾维斯」会自动恢复界面。
    """
    global _ui_hidden
    _ui_hidden = not _ui_hidden
    cmd = 0 if _ui_hidden else 5   # SW_HIDE=0 / SW_SHOW=5
    tops, _ = _collect_windows()
    for h in tops:
        _user32.ShowWindow(h, cmd)
    print(f"[UI] 界面已{'隐藏' if _ui_hidden else '显示'}")
    return _ui_hidden


_user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                 ctypes.c_uint64, ctypes.c_longlong]


def close_ui() -> None:
    """原生关闭 UI 窗口（发 WM_CLOSE）。

    不能依赖 JS 的 window.close()：WebView2 会按 Chromium 安全策略
    拦截脚本关窗，导致退出流程卡死、进程不结束。
    托盘/热键/语音退出统一走这里。
    """
    tops, _ = _collect_windows()
    for h in tops:
        _user32.PostMessageW(h, 0x0010, 0, 0)   # WM_CLOSE


def _child_cb(hwnd, _):
    _sub_list.append(hwnd)
    return True


def _top_cb(hwnd, _):
    p = ctypes.c_uint32(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    if p.value == _proc_pid:
        _tops.append(hwnd)
    return True


# 回调必须保存在模块级，防止被垃圾回收
_CHILD_PROC = _WNDENUMPROC(_child_cb)
_TOP_PROC = _WNDENUMPROC(_top_cb)


def _collect_windows() -> tuple[list, list]:
    """枚举本进程顶层窗口 + 全部子孙窗口。

    WebView2 的渲染子窗口（Chrome_WidgetWin_*）属于 msedgewebview2.exe
    进程，但它们挂在我们的窗口下、是真正拦截点击的元凶——所以子孙树
    要按窗口关系递归收集，不能按进程过滤。
    """
    global _proc_pid, _tops, _children, _sub_list
    _proc_pid = os.getpid()
    _tops, _children = [], []
    _user32.EnumWindows(_TOP_PROC, None)
    queue = list(_tops)
    seen = set(_tops)
    while queue:
        parent = queue.pop()
        _sub_list = []
        _user32.EnumChildWindows(parent, _CHILD_PROC)
        for h in _sub_list:
            if h not in seen:
                seen.add(h)
                _children.append(h)
                queue.append(h)   # 孙窗口继续下钻
    return _tops, _children


def _apply_mask(hwnd, mask) -> bool:
    ex = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    if (ex & mask) != mask:
        _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex | mask)
        _refresh_window(hwnd)   # 关键：不改这一下，样式写了也不生效
    return (_user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & mask) == mask


def _poll_click_through():
    """常驻轮询：持续给所有窗口重设穿透样式 + 子类化命中测试。

    WebView2 可能重建子窗口，因此每 1.5 秒全量重扫一遍。
    """
    import time
    done = False
    while True:
        try:
            tops, children = _collect_windows()
            if tops:
                ok = (all(_apply_mask(h, _TOP_MASK) for h in tops)
                      and all(_apply_mask(h, _CHILD_MASK) for h in children)
                      and all(_hook_hit_test(h) for h in tops + children)
                      and all(_apply_color_key(h) for h in tops))
                if ok and not done:
                    done = True
                    print(f"[UI] 穿透+颜色键透明已启用（顶层 {len(tops)} 个 / 子窗口 {len(children)} 个）")
        except Exception as e:
            print(f"[UI] 穿透设置异常（{e}），1.5 秒后重试")
        time.sleep(1.5)


def run_ui(bridge: UiBridge, stop_event) -> None:
    """主线程运行全屏全息窗，阻塞直到窗口关闭。"""
    html = pathlib.Path(config.BASE_DIR, "ui", "face.html").read_text(encoding="utf-8")
    w, h = _screen_size()
    print(f"[UI] 全息全屏窗启动（{w}x{h}，鼠标穿透，Ctrl+Alt+Q 退出）")
    window = webview.create_window(
        f"{config.WAKE_WORD} · 语音助手",
        html=html,
        width=w,
        height=h,
        x=0,
        y=0,
        frameless=True,
        transparent=True,
        on_top=True,
        easy_drag=False,      # 鼠标已穿透，不需要拖拽
        js_api=bridge,
    )
    window.events.closed += lambda: stop_event.set()   # 用户关窗 → 退出程序
    threading.Thread(target=_poll_click_through, daemon=True).start()
    webview.start()
