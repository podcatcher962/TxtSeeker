# -*- coding: utf-8 -*-
"""
TxtSeeker.exe 真机验收：
 1) 起 exe，进程不秒退
 2) runtime.json 落盘（端口 / PID / 标题）
 3) 顶层窗口真出现且标题正确、可见
 4) 窗口在时 loopback http 服务真能访问（内容与源一致）
 5) 第二个实例应被单实例锁拦下（窗口数不变、第二进程自行退出）
 6) 语言 API round-trip（/api/lang + /api/set_lang，探针后还原不污染用户设置）
 7) 收尾：taskkill /F /IM TxtSeeker.exe 并轮询确认；僵住时删 app.lock
用法：python _exe_test.py <exe路径> [源html路径]
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

APP = "TxtSeeker"
TITLE_KEY = "TxtSeeker"
EXE = os.path.abspath(sys.argv[1])
SRC_HTML = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else \
    os.path.join(os.path.dirname(EXE), "TxtSeeker.html")
RT = os.path.join(os.environ["LOCALAPPDATA"], APP, "runtime.json")
LOCK = os.path.join(os.environ["LOCALAPPDATA"], APP, "app.lock")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

fails = []


def chk(name, ok, detail=""):
    print(("✅ " if ok else "❌ ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def list_windows():
    res = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _l):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
                cls = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetClassNameW(hwnd, cls, 256)
                if buf.value:
                    res.append((hwnd, buf.value, cls.value))
        return True

    ctypes.windll.user32.EnumWindows(cb, 0)
    return res


def app_windows():
    """应用主窗口（排除对话框 #32770 与资源管理器 CabinetWClass/ExploreWClass：
    用户正开着资源管理器浏览本目录时，其标题会含关键字，污染计数）"""
    return [(h, t) for h, t, c in list_windows()
            if TITLE_KEY in t and c not in ("#32770", "CabinetWClass",
                                            "ExploreWClass")]


def dialog_windows():
    return [(h, t) for h, t, c in list_windows()
            if TITLE_KEY in t and c == "#32770"]


def all_dialog_hwnds():
    """全部顶层 #32770 对话框 HWND（不限标题——文件夹选择器标题不含应用名）"""
    out = set()

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _l):
        cls = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "#32770" and ctypes.windll.user32.IsWindowVisible(hwnd):
            out.add(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(cb, 0)
    return out


def _tasklist_text():
    """tasklist 输出按 Windows ANSI 码页（mbcs）容错解码。
    本机 Python 处于 UTF-8 模式，text=True 会以严格 UTF-8 解码，遇到
    GBK 进程名（如某些中文软件）直接抛 UnicodeDecodeError 且 stdout 变 None
    （2026-10-18 真机验收首跑即栽在这里：脚本没启动 exe 就挂了）。"""
    r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True)
    raw = r.stdout or b""
    try:
        return raw.decode("mbcs", "replace")
    except LookupError:               # 非 Windows 平台没有 mbcs
        return raw.decode("utf-8", "replace")


def kill_all():
    subprocess.run(["taskkill", "/F", "/IM", APP + ".exe"],
                   capture_output=True)
    for _ in range(30):
        if APP + ".exe" not in _tasklist_text():
            return True
        time.sleep(0.3)
    # 僵住：删单实例锁文件
    try:
        os.remove(LOCK)
        print("⚠️ 进程僵住，已删除 app.lock")
    except OSError:
        pass
    return False


# ---------- 准备 ----------
kill_all()
for f in (RT, LOCK):
    try:
        os.remove(f)
    except OSError:
        pass
src_bytes = open(SRC_HTML, "rb").read()
print(f"被测 exe: {EXE}\n源页面: {SRC_HTML} ({len(src_bytes)} bytes)\n")

# ---------- 1) 启动 ----------
t0 = time.time()
p = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
time.sleep(3)
alive = p.poll() is None
chk("进程启动 3 秒后仍存活", alive, f"poll={p.poll()}")

# ---------- 2) runtime.json ----------
rt = None
for _ in range(30):
    if os.path.isfile(RT):
        try:
            rt = json.load(open(RT, encoding="utf-8"))
            break
        except Exception:  # noqa: BLE001
            pass
    time.sleep(1)
chk("runtime.json 落盘", rt is not None,
    f"port={rt.get('port') if rt else '-'}")
if rt:
    chk("runtime 标题正确", TITLE_KEY in rt.get("title", ""), rt.get("title", ""))

# ---------- 3) 窗口 ----------
win = None
for _ in range(30):
    ws = app_windows()
    if ws:
        win = ws[0]
        break
    time.sleep(1)
chk("顶层窗口出现且标题正确", win is not None,
    win[1] if win else "未找到")
chk("窗口可见", bool(win) and
    bool(ctypes.windll.user32.IsWindowVisible(win[0])) if win else False, "")

# ---------- 3b) 桌面 API 链路（页面探测成功后会回敲信标到壳的 http 服务） ----------
desk_ok = False
beacons = []
if rt:
    for _ in range(40):
        try:
            with OP.open(f"http://127.0.0.1:{rt['port']}/api/_beacons",
                         timeout=10) as r:
                beacons = json.loads(r.read().decode("utf-8")).get("beacons", [])
            if any(b.get("event") == "desktop_ok" for b in beacons):
                desk_ok = True
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
chk("页面已探测到桌面 API（定位/另存可用）", desk_ok,
    f"信标: {[b.get('event') for b in beacons]}" if beacons else "未收到信标")

# ---------- 4) http 服务端到端 ----------
if rt:
    try:
        with OP.open(f"http://127.0.0.1:{rt['port']}/", timeout=10) as r:
            body = r.read()
        chk("loopback 服务 200", r.status == 200, f"status={r.status}")
        chk("服务内容与源页面逐字节一致", body == src_bytes,
            f"{len(body)} vs {len(src_bytes)}")
    except Exception as e:  # noqa: BLE001
        chk("loopback 服务可访问", False, repr(e))

# ---------- 4b) 「浏览…」原生文件夹对话框回归探针 ----------
# 2026-10-18 兰兰反馈点「浏览…」没反应：根因是 pick_folder 用了 6.x 已移除的
# webview.FOLDER 常量 + gui 级 create_file_dialog（少传 uid），异常被吞。
# 此处起线程打 /api/pick_folder，同时轮询「新增 #32770 窗口」，出现即 WM_CLOSE
# 取消——全程无人值守，证明按钮链路真的能弹出系统对话框。
pick_resp = {"status": None, "body": None, "err": None}

if rt:
    def _call_pick():
        try:
            with OP.open(f"http://127.0.0.1:{rt['port']}/api/pick_folder",
                         timeout=25) as r:
                pick_resp["status"] = r.status
                pick_resp["body"] = r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            pick_resp["err"] = repr(e)

    before_dlg = all_dialog_hwnds()
    th = threading.Thread(target=_call_pick, daemon=True)
    th.start()
    popped = None
    t0 = time.time()
    while time.time() - t0 < 15:
        new = all_dialog_hwnds() - before_dlg
        if new:
            popped = sorted(new)[0]
            break
        time.sleep(0.15)
    chk("「浏览…」弹出原生文件夹对话框", popped is not None,
        f"hwnd={popped}" if popped else "15 秒内未出现")
    if popped:
        ctypes.windll.user32.PostMessageW(popped, 0x0010, 0, 0)  # WM_CLOSE 取消
    th.join(25)
    chk("取消后 /api/pick_folder 干净返回 200",
        pick_resp["err"] is None and pick_resp["status"] == 200,
        f"status={pick_resp['status']} body={pick_resp['body']} err={pick_resp['err']}")

# ---------- 4c) v1.2 新接口探针 ----------
try:
    with OP.open(f"http://127.0.0.1:{rt['port']}/api/recent_dirs", timeout=10) as r:
        rd = json.loads(r.read().decode("utf-8"))
    chk("API /api/recent_dirs 返回目录列表", isinstance(rd.get("dirs"), list),
        f"{len(rd.get('dirs', []))} 个")
except Exception as e:  # noqa: BLE001
    chk("API /api/recent_dirs 返回目录列表", False, repr(e))

try:
    with OP.open(f"http://127.0.0.1:{rt['port']}/api/open_file?path=" +
                 urllib.parse.quote(os.path.join(tempfile.gettempdir(),
                                                 "txtseeker_nope.txt")),
                 timeout=10) as r:
        of = json.loads(r.read().decode("utf-8"))
    chk("API /api/open_file 坏路径 ok=false", of.get("ok") is False, str(of))
except Exception as e:  # noqa: BLE001
    chk("API /api/open_file 坏路径 ok=false", False, repr(e))

# 「导出摘录」的保存对话框：弹 → WM_CLOSE 取消 → path=null
save_resp = {"body": None, "err": None}

def _call_save():
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{rt['port']}/api/save_text",
            data=json.dumps({"content": "TxtSeeker 验收自检内容\n",
                             "name": "selftest_sel.txt"}).encode("utf-8"),
            method="POST", headers={"Content-Type": "application/json"})
        with OP.open(req, timeout=25) as r:
            save_resp["body"] = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        save_resp["err"] = repr(e)

before_dlg = all_dialog_hwnds()
th = threading.Thread(target=_call_save, daemon=True)
th.start()
popped = None
t0 = time.time()
while time.time() - t0 < 15:
    new = all_dialog_hwnds() - before_dlg
    if new:
        popped = sorted(new)[0]
        break
    time.sleep(0.15)
chk("「导出摘录」弹出保存对话框", popped is not None,
    f"hwnd={popped}" if popped else "15 秒内未出现")
if popped:
    ctypes.windll.user32.PostMessageW(popped, 0x0010, 0, 0)  # WM_CLOSE 取消
th.join(25)
try:
    svj = json.loads(save_resp["body"]) if save_resp["body"] else {}
except Exception:  # noqa: BLE001
    svj = {}
chk("取消后 /api/save_text 返回 path=null",
    save_resp["err"] is None and svj.get("path") is None,
    f"body={save_resp['body']} err={save_resp['err']}")

# 「打开选中文件」：真拉默认程序（记事本），按标题唯一标记精准关闭，不误伤他人
tmpf = os.path.join(tempfile.gettempdir(),
                    f"txtseeker_opentest_{os.getpid()}.txt")
with open(tmpf, "w", encoding="utf-8") as f:
    f.write("TxtSeeker 打开文件验收\n")
marker = os.path.basename(tmpf)
try:
    with OP.open(f"http://127.0.0.1:{rt['port']}/api/open_file?path=" +
                 urllib.parse.quote(tmpf), timeout=10) as r:
        of2 = json.loads(r.read().decode("utf-8"))
    chk("API /api/open_file 真实文件 ok=true", of2.get("ok") is True, str(of2))
    np_hwnd = None
    t0 = time.time()
    while time.time() - t0 < 8:
        for h, t, c in list_windows():
            if marker in t:
                np_hwnd = h
                break
        if np_hwnd:
            break
        time.sleep(0.3)
    chk("默认程序（记事本）被拉起", np_hwnd is not None,
        f"hwnd={np_hwnd}" if np_hwnd else "未见标题含标记的窗口")
    if np_hwnd:
        ctypes.windll.user32.PostMessageW(np_hwnd, 0x0010, 0, 0)
        time.sleep(0.5)
except Exception as e:  # noqa: BLE001
    chk("API /api/open_file 真实文件 ok=true", False, repr(e))
finally:
    try:
        os.remove(tmpf)
    except OSError:
        pass

# ---------- 4d) v1.3 语言 API 探针（round-trip + 还原，不污染用户设置） ----------
LANG_FILE = os.path.join(os.environ["LOCALAPPDATA"], APP, "lang.txt")
lang_orig_bytes = None
try:
    if os.path.isfile(LANG_FILE):
        with open(LANG_FILE, "rb") as f:
            lang_orig_bytes = f.read()
except OSError:
    lang_orig_bytes = None
try:
    with OP.open(f"http://127.0.0.1:{rt['port']}/api/lang", timeout=10) as r:
        lg = json.loads(r.read().decode("utf-8"))
    chk("API /api/lang 返回语言", lg.get("lang") in ("zh", "en"), str(lg))

    def _lang_post(lang):
        req = urllib.request.Request(
            f"http://127.0.0.1:{rt['port']}/api/set_lang",
            data=json.dumps({"lang": lang}).encode("utf-8"),
            method="POST", headers={"Content-Type": "application/json"})
        with OP.open(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    chk("API /api/set_lang 切换 en", _lang_post("en").get("lang") == "en", "")
    with OP.open(f"http://127.0.0.1:{rt['port']}/api/lang", timeout=10) as r:
        chk("API /api/lang 读得回 en",
            json.loads(r.read().decode("utf-8")).get("lang") == "en", "")
    chk("API /api/set_lang 非法值被拒", _lang_post("xx").get("lang") == "en", "")
    # 还原到探针前的语言（内存 + 文件），避免验收改掉用户设置
    _lang_post("zh" if lang_orig_bytes is None
               else lang_orig_bytes.decode("utf-8", "replace").strip())
except Exception as e:  # noqa: BLE001
    chk("API 语言 round-trip", False, repr(e))
finally:
    try:
        if lang_orig_bytes is None:
            if os.path.isfile(LANG_FILE):
                os.remove(LANG_FILE)
        else:
            with open(LANG_FILE, "wb") as f:
                f.write(lang_orig_bytes)
    except OSError:
        pass

# ---------- 4.5) v1.4 偏好存储（/api/store） ----------
STORE_FILE = os.path.join(os.environ["LOCALAPPDATA"], APP, "store", "theme.json")
theme_orig = None
try:
    if os.path.isfile(STORE_FILE):
        with open(STORE_FILE, "rb") as f:
            theme_orig = f.read()
except OSError:
    theme_orig = None
try:
    req = urllib.request.Request(
        f"http://127.0.0.1:{rt['port']}/api/store",
        data=json.dumps({"key": "theme", "value": "exe_probe"}).encode("utf-8"),
        method="POST", headers={"Content-Type": "application/json"})
    with OP.open(req, timeout=10) as r:
        ok_w = json.loads(r.read().decode("utf-8")).get("ok") is True
    with OP.open(f"http://127.0.0.1:{rt['port']}/api/store?key=theme",
                 timeout=10) as r:
        v = json.loads(r.read().decode("utf-8")).get("value")
    chk("API /api/store 写后可读回（v1.4）", ok_w and v == "exe_probe",
        f"write={ok_w}, read={v}")
    with OP.open(f"http://127.0.0.1:{rt['port']}/api/store?key=bad",
                 timeout=10) as r:
        v2 = json.loads(r.read().decode("utf-8")).get("value")
    chk("API /api/store 非法 key 返回 null", v2 is None, str(v2))
except Exception as e:  # noqa: BLE001
    chk("API /api/store round-trip", False, repr(e))
finally:
    try:
        if theme_orig is None:
            if os.path.isfile(STORE_FILE):
                os.remove(STORE_FILE)
        else:
            with open(STORE_FILE, "wb") as f:
                f.write(theme_orig)
    except OSError:
        pass

# ---------- 5) 单实例 ----------
# 轮询而非一次性检查：onefile 冷启动解压有时 >5s，曾偶发误报（2026-10-18 0902 构建）
p2 = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
ws2, dlg = [], []
t0 = time.time()
while time.time() - t0 < 12:
    time.sleep(0.5)
    ws2 = app_windows()
    dlg = dialog_windows()
    if len(ws2) >= 1 and dlg:
        break
chk("第二实例被拦下（应用窗口仍为 1）", len(ws2) == 1, f"窗口数={len(ws2)}")
chk("第二实例弹出「已在运行」提示", len(dlg) >= 1,
    dlg[0][1] if dlg else "12 秒内未见对话框")

# ---------- 6) 收尾 ----------
kill_all()
time.sleep(1)
chk("进程可被清理", not app_windows() and not dialog_windows(), "")

dt = time.time() - t0
print(f"\n耗时 {dt:.1f}s —— {'全部通过 ✅' if not fails else '有失败 ❌: ' + '; '.join(fails)}")
sys.exit(1 if fails else 0)
