# -*- coding: utf-8 -*-
"""TxtSeeker「浏览…」真机探针：验证原生文件夹对话框确实会弹出。

背景：2026-10-18 兰兰反馈 exe 里点「浏览…」没反应。根因是 app.py 的
pick_folder() 用了 pywebview 5.x 时代 API（webview.FOLDER 常量 + gui 级
create_file_dialog），6.x 已移除/签名不符，异常被吞 → 静默无反应。
本脚本不起窗口人工点击：后台线程调 Api.pick_folder()，另一线程轮询
「新增的 #32770 对话框窗口」，出现即 PostMessage WM_CLOSE 取消。

判定：
  dialog_seen == True  → 对话框真的弹了（修复有效）
  picked 为 None       → 取消后干净返回（无异常、无卡死）
用法: python _pick_probe.py
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as shell  # noqa: E402

WATCHDOG = 40
result = {"picked": "unset", "dialog_seen": False, "err": None, "t_pop": None}


def dialog_hwnds():
    """当前所有顶层 #32770（对话框类）可见窗口 HWND 集合。"""
    found = set()
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def _cb(hwnd, _):
        cls = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "#32770" and ctypes.windll.user32.IsWindowVisible(hwnd):
            found.add(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found


def main():
    import webview
    api = shell.Api()

    def bg_pick():
        time.sleep(2.0)  # 等 webview 窗口就绪
        try:
            result["picked"] = api.pick_folder()  # None = 用户取消，属预期
        except Exception as e:  # noqa: BLE001
            result["err"] = repr(e)
        finally:
            try:
                webview.windows[0].destroy()
            except Exception:  # noqa: BLE001
                os._exit(0)

    def closer():
        before = dialog_hwnds()
        t0 = time.time()
        while time.time() - t0 < 12:
            time.sleep(0.15)
            new = dialog_hwnds() - before
            if new:
                result["dialog_seen"] = True
                result["t_pop"] = round(time.time() - t0, 2)
                hwnd = sorted(new)[0]
                # WM_CLOSE=0x0010 取消对话框（低于 WM_USER，不受 UIPI 拦截）
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
                return
        os._exit(3)  # 12 秒没弹出 → 判失败，强退

    def watchdog():
        time.sleep(WATCHDOG)
        print("WATCHDOG: 超时强退")
        os._exit(4)

    threading.Thread(target=watchdog, daemon=True).start()
    webview.create_window("pick probe", "about:blank",
                          width=320, height=200)
    threading.Thread(target=bg_pick, daemon=True).start()
    threading.Thread(target=closer, daemon=True).start()
    webview.start()

    print("dialog_seen:", result["dialog_seen"],
          "| t_pop:", result["t_pop"],
          "| picked:", repr(result["picked"]),
          "| err:", result["err"])
    ok = result["dialog_seen"] and result["err"] is None
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
