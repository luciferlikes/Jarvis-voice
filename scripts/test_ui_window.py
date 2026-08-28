"""UI 渲染诊断：开一个纯品红色测试窗，配合截屏判断页面是否渲染。

用法：.venv/Scripts/python scripts/test_ui_window.py [transparent|opaque]
"""
import sys

import webview

transparent = sys.argv[1] != "opaque" if len(sys.argv) > 1 else True
window = webview.create_window(
    "UI TEST",
    html='<html><body style="margin:0;background:#ff00ff">'
         '<h1 style="color:#00ff00;font-size:40px">TEST PAGE</h1></body></html>',
    width=400,
    height=300,
    x=1000,
    y=200,
    frameless=True,
    transparent=transparent,
    on_top=True,
)
webview.start()
