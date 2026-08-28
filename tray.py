"""系统托盘：托盘图标 + 暂停/退出菜单，让程序常驻后台。

有 UI 时用 run_tray_detached（主线程留给 webview 悬浮窗）；
无 UI 时用 run_tray（阻塞主线程）。
"""
import pystray
from PIL import Image

import config
from ui import toggle_ui_hidden, close_ui


def _build_icon(stop_event, pause_event, bridge=None):
    def on_toggle_pause(_icon, _item):
        if pause_event.is_set():
            pause_event.clear()
            print("[托盘] 继续")
        else:
            pause_event.set()
            print("[托盘] 暂停")

    def on_toggle_hide(_icon, _item):
        toggle_ui_hidden()

    def on_exit(icon, _item):
        print("[托盘] 退出")
        stop_event.set()
        if bridge is not None:
            bridge.push({"type": "quit"})   # 通知 UI 收尾
        close_ui()                          # 原生关窗（JS window.close 被 WebView2 拦截）
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            "暂停",
            on_toggle_pause,
            checked=lambda _item: pause_event.is_set(),
            default=True,   # 双击托盘图标 = 暂停/继续
        ),
        pystray.MenuItem("隐藏界面", on_toggle_hide),
        pystray.MenuItem("退出", on_exit),
    )
    return pystray.Icon(
        "jarvis",
        Image.open(config.ICON_PATH),
        f"{config.WAKE_WORD}语音助手",
        menu,
    )


def run_tray(stop_event, pause_event, bridge=None) -> None:
    """阻塞运行（无 UI 模式）。"""
    _build_icon(stop_event, pause_event, bridge).run()


def run_tray_detached(stop_event, pause_event, bridge=None):
    """独立线程运行（有 UI 模式）。返回 Icon 句柄——退出流程必须调用
    icon.stop()，否则托盘线程会拖住进程变成僵尸。"""
    icon = _build_icon(stop_event, pause_event, bridge)
    icon.run_detached()
    return icon
