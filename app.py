# -*- coding: utf-8 -*-
"""
TxtSeeker 桌面壳
© 永远的兰兰 / Lanlan Eternal

- 内嵌单页面 TxtSeeker.html，经 127.0.0.1 loopback http 提供（安全上下文）
- pywebview + WebView2 窗口，无地址栏
- 单实例：%LOCALAPPDATA%\\TxtSeeker\\app.lock 字节区间锁
- 运行时把实际端口写 %LOCALAPPDATA%\\TxtSeeker\\runtime.json（供真机验收读取）
- --selftest --out=FILE：不开窗自检（资源 / 路由 / 404 / 内容一致性）

用法：
  TxtSeeker.exe                      正常启动
  TxtSeeker.exe --selftest --out=X   自检，报告写 JSON 到 X
"""
import hashlib
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import time
import urllib.parse

APP = "TxtSeeker"
VERSION = "1.3.2"
TITLE = "TxtSeeker — TXT 全文搜索定位"
PAGE_FILE = "TxtSeeker.html"
PORT_START = 38971
PORT_TRIES = 50
MIN_PAGE = 10000
MAX_PAGE = 2 * 1024 * 1024


def appdata_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP)


# ------------------------------------------------------------ 语言（v1.3 双语）
def lang_path():
    return os.path.join(appdata_dir(), "lang.txt")


def load_lang():
    """壳记住的界面语言（zh / en），缺省 zh"""
    try:
        with open(lang_path(), encoding="utf-8-sig") as f:
            v = f.read().strip().lower()
        if v in ("zh", "en"):
            return v
    except OSError:
        pass
    return "zh"


def save_lang(lang):
    if lang not in ("zh", "en"):
        return
    try:
        os.makedirs(appdata_dir(), exist_ok=True)
        with open(lang_path(), "w", encoding="utf-8") as f:
            f.write(lang)
    except OSError:
        pass


SHELL_TEXT = {
    "zh": {
        "already": "TxtSeeker 已在运行中。\n请查看任务栏处的窗口。",
        "title": "TxtSeeker — TXT 全文搜索定位",
        "pick_desc": "选择要搜索的文件夹：单击即选中（包含其下所有子目录），"
                     "点「确定」开始加载",
        "save_name": "TxtSeeker导出.txt",
        "missing_page": "未找到内嵌页面 {page}，请重新安装。",
    },
    "en": {
        "already": "TxtSeeker is already running.\n"
                   "Please check the window in the taskbar.",
        "title": "TxtSeeker — TXT Full-Text Search & Locate",
        "pick_desc": "Pick the folder to search: a single click selects it "
                     "(including all subfolders), then click OK to load.",
        "save_name": "TxtSeeker_export.txt",
        "missing_page": "Embedded page {page} not found. Please reinstall.",
    },
}


def st(lang, key):
    """壳内文案：按语言取，缺语言回退中文"""
    d = SHELL_TEXT.get(lang) or SHELL_TEXT["zh"]
    return d.get(key, SHELL_TEXT["zh"].get(key, ""))


def base_dir():
    """onefile 解包目录优先，否则取本文件所在目录"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def page_path():
    return os.path.join(base_dir(), PAGE_FILE)


def load_page():
    with open(page_path(), "rb") as f:
        return f.read()


def find_port(start=PORT_START, tries=PORT_TRIES):
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("找不到可用端口")


class PageHandler(http.server.SimpleHTTPRequestHandler):
    page = b""
    api = None            # Api 实例（selftest / 运行时注入）

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _text(self, text, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/" + PAGE_FILE):
            body = self.page
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if not self.api:
            self.send_error(404, "Not Found")
            return
        # ---- 本地 API（同源 http，绕开 pywebview JS bridge 的不确定性） ----
        if path == "/api/info":
            self._json({"app": APP, "version": VERSION, "desktop": True})
        elif path == "/api/pick_folder":
            self._json({"path": self.api.pick_folder()})
        elif path == "/api/list_files":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            root = q.get("root", [""])[0]
            exts = [e.strip() for e in q.get("exts", [""])[0].split(",") if e.strip()]
            sub = q.get("sub", ["1"])[0] == "1"
            self._json(self.api.list_files(root, exts, sub))
        elif path == "/api/open_folder":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._json({"ok": bool(self.api.open_folder(q.get("path", [""])[0]))})
        elif path == "/api/open_file":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._json({"ok": bool(self.api.open_file(q.get("path", [""])[0]))})
        elif path == "/api/recent_dirs":
            self._json({"dirs": self.api.recent_dirs()})
        elif path == "/api/lang":
            self._json({"lang": self.api.get_lang()})
        elif path == "/api/reveal":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._json({"ok": bool(self.api.reveal_file(q.get("path", [""])[0]))})
        elif path == "/api/beacon":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._json({"ok": bool(self.api.beacon(q.get("event", [""])[0]))})
        elif path == "/api/_beacons":
            self._json({"beacons": getattr(self.api, "_beacons", [])})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""
        if not self.api:
            self.send_error(404, "Not Found")
            return
        if path == "/api/read_text":
            p = body.decode("utf-8", "replace").strip()
            text = self.api.read_text(p)
            if text is None:
                self._json({"error": "read failed"}, 400)
            else:
                self._text(text)
        elif path == "/api/copy_files":
            try:
                data = json.loads(body.decode("utf-8"))
                self._json(self.api.copy_files(data.get("paths") or [],
                                               data.get("dest")))
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 400)
        elif path == "/api/save_text":
            try:
                data = json.loads(body.decode("utf-8"))
                p = self.api.save_text(data.get("content", ""),
                                       data.get("name") or "")
                self._json({"path": p})
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 400)
        elif path == "/api/set_lang":
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                self._json({"lang": self.api.set_lang(data.get("lang"))})
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 400)
        else:
            self.send_error(404, "Not Found")

    def log_message(self, *args):
        pass


class PageServer(socketserver.TCPServer):
    allow_reuse_address = False


def serve(port, page, api=None):
    PageHandler.page = page
    PageHandler.api = api
    srv = PageServer(("127.0.0.1", port), PageHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ------------------------------------------------------------ 单实例
_lock_file = None


def acquire_single_instance():
    global _lock_file
    os.makedirs(appdata_dir(), exist_ok=True)
    f = open(os.path.join(appdata_dir(), "app.lock"), "a+b")
    try:
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_file = f
        return True
    except (OSError, ImportError):
        f.close()
        return False


def _msg(text, flags, caption=None):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, caption or TITLE, flags)
    except Exception:
        pass


def notify_already_running(lang="zh"):
    _msg(st(lang, "already"), 0x40, st(lang, "title"))


# ------------------------------------------------------------ 运行时信息
def write_runtime(port):
    rt = {
        "app": APP, "version": VERSION, "title": TITLE,
        "pid": os.getpid(), "port": port,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(appdata_dir(), "runtime.json"), "w", encoding="utf-8") as f:
        json.dump(rt, f, ensure_ascii=False, indent=1)
    return rt


def remove_runtime():
    try:
        os.remove(os.path.join(appdata_dir(), "runtime.json"))
    except OSError:
        pass


# ------------------------------------------------------------ 本地 API（桌面版）
MAX_READ_SIZE = 200 * 1024 * 1024


def decode_bytes(raw):
    """UTF-8 优先，失败回退 GB18030（与页面 decodeBuffer 同策略）"""
    try:
        return raw.decode("utf-8-sig")
    except (UnicodeDecodeError, UnicodeError):
        return raw.decode("gb18030", errors="replace")


def _first(res):
    """兼容 pywebview 5.x（返回 tuple）与 6.x（返回 str）"""
    if res is None:
        return None
    if isinstance(res, str):
        return res
    try:
        return res[0] if len(res) else None
    except (TypeError, IndexError):
        return None


def _unique_path(dest, name):
    base, ext = os.path.splitext(name)
    cand = os.path.join(dest, name)
    i = 1
    while os.path.exists(cand):
        cand = os.path.join(dest, f"{base} ({i}){ext}")
        i += 1
    return cand


def sniff_encoding(abs_path):
    """读文件头猜编码（UTF-8 优先，回退 GB18030）——与页面 decodeBuffer 同策略。
    容忍 8KB 边界把多字节字符切断：依次少看 0~3 个尾字节重试。"""
    try:
        with open(abs_path, "rb") as f:
            head = f.read(8192)
    except OSError:
        return ""
    if not head:
        return "UTF-8"
    for trim in range(4):
        try:
            (head[:-trim] if trim else head).decode("utf-8")
            return "UTF-8"
        except UnicodeDecodeError:
            continue
    return "GBK"


def _ui_form():
    """pywebview 的 WinForms 窗口对象（用于 Invoke 回 UI 线程）；取不到返回 None"""
    try:
        import webview
        wins = [w for w in webview.windows if getattr(w, "gui", None) is not None]
        if not wins:
            return None
        from webview.platforms import winforms as _wf
        return _wf.BrowserView.instances.get(wins[0].uid)
    except Exception:  # noqa: BLE001
        return None


def _invoke_ui(fn):
    """把 fn 调度到 pywebview UI 线程执行并取回返回值。

    跨线程直接碰 WinForms 控件会抛 InvalidOperation，故与 pywebview 内部
    （set_title/show/load_url）同款：InvokeRequired 时 Invoke 回去。
    """
    form = _ui_form()
    if form is not None and getattr(form, "InvokeRequired", False):
        try:
            from System import Func, Type
            return form.Invoke(Func[Type](fn))
        except Exception:  # noqa: BLE001 —— pythonnet 委托异常时退回直调
            return fn()
    return fn()


def _pick_folder_dialog(start_dir="", parent=None, lang="zh"):
    """.NET FolderBrowserDialog：单击即选中，双击=选中并返回，不会钻进子目录。
    返回选中路径或 None（取消/异常）。

    为什么不用 pywebview 自带的 IFileDialog+FOS_PICKFOLDERS（v1.1.1 之前用的）：
    那是 VS Code 式交互——双击文件夹会进入该文件夹，想选父目录必须
    单击+点确定。兰兰 2026-10-18 反馈「选择文件夹后还会进入选择子目录，
    不能直接选择带有子目录的文件夹」，FolderBrowserDialog 的心智模型
    更直白：看到哪个文件夹，点它，确定。
    """
    try:
        import System.Windows.Forms as WinForms
        dlg = WinForms.FolderBrowserDialog()
        dlg.Description = st(lang, "pick_desc")
        dlg.ShowNewFolderButton = False
        if start_dir and os.path.isdir(start_dir):
            dlg.SelectedPath = start_dir
        res = dlg.ShowDialog(parent) if parent is not None else dlg.ShowDialog()
        if res == WinForms.DialogResult.OK and dlg.SelectedPath:
            return str(dlg.SelectedPath)
        return None
    except Exception:  # noqa: BLE001 —— pythonnet 异常时退回 pywebview 对话框
        try:
            import webview
            wins = [w for w in webview.windows
                    if getattr(w, "gui", None) is not None]
            if wins:
                r = wins[0].create_file_dialog(webview.FileDialog.FOLDER)
                if r:
                    return str(r[0])
        except Exception:  # noqa: BLE001
            pass
        return None


class Api:
    """暴露给页面的本地能力。全部仅在 127.0.0.1 回环内被页面调用，不联网。"""

    MAX_RECENT = 5

    def __init__(self):
        self._beacons = []   # 页面回敲的信标（真机验收读它）
        self._recent = self._load_recent()
        self.lang = load_lang()   # v1.3：界面语言（页面切换时经 /api/set_lang 同步）

    # ---------------- 语言（v1.3 双语） ----------------
    def get_lang(self):
        return self.lang

    def set_lang(self, lang):
        if lang in ("zh", "en"):
            self.lang = lang
            save_lang(lang)
            self._apply_window_title()
        return self.lang

    def _apply_window_title(self):
        """窗口标题随语言切换（set_title 内部会 Invoke 回 UI 线程，http 线程可调）"""
        try:
            import webview
            wins = [w for w in webview.windows
                    if getattr(w, "gui", None) is not None]
            if wins:
                wins[0].set_title(st(self.lang, "title"))
        except Exception:  # noqa: BLE001
            pass

    # ---------------- 最近目录记忆（最多 5 个，新的在前） ----------------
    @staticmethod
    def _recent_path():
        return os.path.join(appdata_dir(), "last_dirs.json")

    def _load_recent(self):
        p = self._recent_path()
        dirs = []
        try:
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    dirs = json.load(f)
                if not isinstance(dirs, list):
                    dirs = []
        except (OSError, ValueError):
            dirs = []
        if not dirs:
            # 迁移 v1.1.2 的单目录记忆
            try:
                old = os.path.join(appdata_dir(), "last_dir.txt")
                if os.path.isfile(old):
                    with open(old, encoding="utf-8-sig") as f:
                        d = f.read().strip()
                    if d:
                        dirs = [d]
            except OSError:
                pass
        return [d for d in dirs if isinstance(d, str) and os.path.isdir(d)][:self.MAX_RECENT]

    def _remember_dir(self, path):
        if not path or not os.path.isdir(path):
            return
        norm = os.path.normpath(path)
        dirs = [path] + [d for d in self._recent
                         if os.path.normpath(d) != norm and os.path.isdir(d)]
        self._recent = dirs[:self.MAX_RECENT]
        try:
            os.makedirs(appdata_dir(), exist_ok=True)
            with open(self._recent_path(), "w", encoding="utf-8") as f:
                json.dump(self._recent, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def recent_dirs(self):
        return list(self._recent)

    def beacon(self, event):
        """页面状态信标：detectDesktop 成功/失败都会回敲"""
        try:
            self._beacons.append({"event": str(event), "t": time.time()})
        except Exception:  # noqa: BLE001
            pass
        return True

    def get_app_info(self):
        return {"app": APP, "version": VERSION, "desktop": True}

    # ---------------- 目录选择（原生对话框，无 file input、无上传提示）
    def pick_folder(self):
        """http 线程调用：Invoke 回 pywebview 的 UI 线程（STA）弹对话框。

        对话框用 FolderBrowserDialog（单击即选中、不会钻进子目录——
        IFileDialog+FOS_PICKFOLDERS 是 VS Code 式交互，兰兰 2026-10-18
        反馈「不能直接选择带有子目录的文件夹」）。
        pywebview 6.x 另有两个坑（曾导致「浏览」点了没反应）：① 旧常量
        webview.FOLDER 已被移除；② 跨线程碰 WinForms 控件会抛
        InvalidOperation——统一走 _invoke_ui 回 UI 线程。
        """
        def _show():
            start = self._recent[0] if self._recent else ""
            path = _pick_folder_dialog(start, _ui_form(), self.lang)
            if path:
                self._remember_dir(path)
            return path

        return _invoke_ui(_show)

    # ---------------- 文件枚举（返回绝对路径+编码，供打开目录/定位/另存）
    def list_files(self, root, exts, include_subdir=True):
        if not root or not os.path.isdir(root):
            return []
        exts = {e.lower() if e.startswith(".") else "." + e.lower()
                for e in (exts or [])}
        out = []
        if include_subdir:
            for dirpath, _dirs, names in os.walk(root):
                for name in names:
                    if os.path.splitext(name)[1].lower() in exts:
                        p = os.path.join(dirpath, name)
                        try:
                            st = os.stat(p)
                            if 0 < st.st_size <= MAX_READ_SIZE:
                                out.append({
                                    "relPath": os.path.relpath(p, root).replace("\\", "/"),
                                    "absPath": p, "size": st.st_size,
                                    "mtime": int(st.st_mtime * 1000),
                                    "enc": sniff_encoding(p),
                                })
                        except OSError:
                            continue
        else:
            try:
                for name in os.listdir(root):
                    p = os.path.join(root, name)
                    if os.path.isfile(p) and os.path.splitext(name)[1].lower() in exts:
                        try:
                            st = os.stat(p)
                            if 0 < st.st_size <= MAX_READ_SIZE:
                                out.append({"relPath": name, "absPath": p,
                                            "size": st.st_size,
                                            "mtime": int(st.st_mtime * 1000),
                                            "enc": sniff_encoding(p)})
                        except OSError:
                            continue
            except OSError:
                return []
        return out

    # ---------------- 读文件内容（UTF-8/GBK 自动识别）
    def read_text(self, abs_path):
        try:
            if os.path.getsize(abs_path) > MAX_READ_SIZE:
                return None
            with open(abs_path, "rb") as f:
                return decode_bytes(f.read())
        except OSError:
            return None

    # ---------------- 用系统默认程序打开文件
    def open_file(self, abs_path):
        try:
            if not abs_path or not os.path.isfile(abs_path):
                return False
            os.startfile(os.path.normpath(abs_path))  # noqa: S606
            return True
        except OSError:
            return False

    # ---------------- 保存文本（原生保存对话框，UTF-8 落盘）
    def save_text(self, content, default_name=""):
        """弹保存对话框写 UTF-8 文本，返回保存路径或 None（取消/无窗口）。
        默认文件名随界面语言（v1.3）"""
        if content is None:
            return None

        def _show():
            try:
                import webview
                wins = [w for w in webview.windows
                        if getattr(w, "gui", None) is not None]
                if not wins:
                    return None
                res = wins[0].create_file_dialog(
                    webview.FileDialog.SAVE,
                    save_filename=default_name or st(self.lang, "save_name"))
                p = _first(res)
                if not p:
                    return None
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                return p
            except Exception:  # noqa: BLE001
                return None

        return _invoke_ui(_show)

    # ---------------- 资源管理器定位
    def open_folder(self, abs_path):
        """打开文件所在文件夹"""
        try:
            d = os.path.dirname(abs_path)
            os.startfile(d)  # noqa: S606
            return True
        except OSError:
            return False

    def reveal_file(self, abs_path):
        """资源管理器中定位（选中）该文件"""
        try:
            import subprocess
            subprocess.Popen(["explorer", "/select," + os.path.normpath(abs_path)])
            return True
        except Exception:  # noqa: BLE001
            return self.open_folder(abs_path)

    # ---------------- 另存（复制到指定目录，自动处理重名）
    def copy_files(self, abs_paths, dest_dir=None):
        if not abs_paths:
            return {"copied": 0, "failed": [], "dest": None}
        if not dest_dir:
            dest_dir = self.pick_folder()
        if not dest_dir or not os.path.isdir(dest_dir):
            return {"copied": 0, "failed": [{"path": p, "err": "目标目录无效"}
                                            for p in abs_paths],
                    "dest": dest_dir}
        copied, failed = 0, []
        for p in abs_paths:
            try:
                if not os.path.isfile(p):
                    failed.append({"path": p, "err": "文件不存在"})
                    continue
                import shutil
                shutil.copy2(p, _unique_path(dest_dir, os.path.basename(p)))
                copied += 1
            except Exception as e:  # noqa: BLE001
                failed.append({"path": p, "err": str(e)})
        return {"copied": copied, "failed": failed, "dest": dest_dir}


# ------------------------------------------------------------ 自检


def selftest(out_path):
    rep = {"app": APP, "version": VERSION, "checks": [], "ok": True}
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    def chk(name, ok, detail=""):
        rep["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)})
        if not ok:
            rep["ok"] = False

    p = page_path()
    chk("页面文件存在", os.path.isfile(p), p)
    if not os.path.isfile(p):
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        return 1

    page = load_page()
    rep["page_size"] = len(page)
    rep["page_md5"] = hashlib.md5(page).hexdigest()
    chk("页面体积合理", MIN_PAGE < len(page) < MAX_PAGE, f"{len(page)} bytes")
    chk("页面关键标记在",
        b"TxtSeeker" in page and b"__CORE__" in page and b"parseKeywords" in page,
        "")
    chk("页面含双语机制（v1.3）",
        b"I18N" in page and b"data-i18n" in page
        and b"function setLang" in page and b"function applyLang" in page, "")

    import shutil as _sh
    import tempfile
    import urllib.error
    import urllib.parse
    import urllib.request

    # 造测试数据：UTF-8 + GBK + 子目录 + 二进制
    tmp = tempfile.mkdtemp(prefix="TxtSeeker_selftest_")
    dest = None
    try:
        os.makedirs(os.path.join(tmp, "sub"))
        with open(os.path.join(tmp, "a.txt"), "w", encoding="utf-8") as f:
            f.write("你好天气\n无关\n")
        with open(os.path.join(tmp, "sub", "b.txt"), "w", encoding="gbk") as f:
            f.write("世界和平\n")
        with open(os.path.join(tmp, "skip.bin"), "wb") as f:
            f.write(b"\x00\x01\x02")

        port = find_port()
        api = Api()
        srv = serve(port, page, api)
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def get(path):
            try:
                with op.open(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
                    return r.status, r.headers.get("Content-Type", ""), r.read()
            except urllib.error.HTTPError as e:
                return e.code, "", e.read()
            except Exception as e:  # noqa: BLE001
                return -1, "", str(e).encode()

        def jget(p):
            try:
                with op.open(f"http://127.0.0.1:{port}{p}", timeout=10) as r:
                    return r.status, json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                try:
                    return e.code, json.loads(e.read().decode("utf-8"))
                except Exception:  # noqa: BLE001
                    return e.code, None
            except (urllib.error.URLError, OSError) as e:
                return -1, {"error": repr(e)}

        def jpost(p, payload=None, raw=None):
            if raw is not None:
                data = raw
            elif payload is not None:
                data = json.dumps(payload).encode("utf-8")
            else:
                data = b""
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{p}", data=data, method="POST",
                headers={"Content-Type": "application/json"})
            try:
                with op.open(req, timeout=10) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
            except (urllib.error.URLError, OSError) as e:
                return -1, repr(e).encode()

        # ---- 页面路由 ----
        st, ct, body = get("/")
        chk("GET / 返回 200", st == 200, f"status={st}")
        chk("/ 内容类型 text/html", "text/html" in ct, ct)
        chk("/ 内容长度与源一致", len(body) == len(page),
            f"{len(body)} vs {len(page)}")
        chk("/ 内容与源逐字节一致", body == page,
            "md5 " + hashlib.md5(body).hexdigest())

        st2, _, body2 = get("/" + PAGE_FILE)
        chk("GET /" + PAGE_FILE + " 返回 200", st2 == 200, f"status={st2}")
        chk("该路由内容一致", body2 == page, "")

        st3, _, _ = get("/no-such-file.txt")
        chk("陌生路径返回 404", st3 == 404, f"status={st3}")

        # ---- 本地 API 路由（页面真实调用路径）----
        st, info = jget("/api/info")
        chk("API /api/info 桌面标记", st == 200 and info.get("desktop") is True,
            f"status={st}")

        st, fl = jget("/api/list_files?root=" +
                      urllib.parse.quote(tmp) + "&exts=.txt&sub=1")
        ok_list = st == 200 and isinstance(fl, list) and len(fl) == 2
        chk("API /api/list_files 递归找全", ok_list,
            f"status={st}, {len(fl) if isinstance(fl, list) else fl} 个")
        chk("API /api/list_files 给绝对路径",
            ok_list and all(os.path.isabs(f["absPath"]) for f in fl), "")
        chk("API /api/list_files 带编码列",
            ok_list and all(f.get("enc") in ("UTF-8", "GBK") for f in fl),
            str([f.get("enc") for f in fl]) if ok_list else "-")
        if ok_list:
            encs = {f["absPath"][-5:]: f.get("enc") for f in fl}
            chk("API /api/list_files 编码判断正确",
                encs.get("a.txt") == "UTF-8" and encs.get("b.txt") == "GBK",
                str(encs))

        st, fl2 = jget("/api/list_files?root=" +
                       urllib.parse.quote(tmp) + "&exts=.txt&sub=0")
        chk("API /api/list_files 不含子目录",
            st == 200 and isinstance(fl2, list) and len(fl2) == 1,
            f"{len(fl2) if isinstance(fl2, list) else fl2} 个")

        if ok_list:
            a = next(f for f in fl if f["absPath"].endswith("a.txt"))
            b = next(f for f in fl if f["absPath"].endswith("b.txt"))

            st, body = jpost("/api/read_text", raw=a["absPath"].encode("utf-8"))
            chk("API /api/read_text UTF-8",
                st == 200 and "你好天气" in body.decode("utf-8"), f"status={st}")
            st, body = jpost("/api/read_text", raw=b["absPath"].encode("utf-8"))
            chk("API /api/read_text GBK",
                st == 200 and "世界和平" in body.decode("utf-8"), f"status={st}")
            st, _ = jpost("/api/read_text",
                          raw=os.path.join(tmp, "nope.txt").encode("utf-8"))
            chk("API /api/read_text 坏文件返回 400", st == 400, f"status={st}")

            dest = tempfile.mkdtemp(prefix="TxtSeeker_dest_")
            st, body = jpost("/api/copy_files",
                             {"paths": [a["absPath"], b["absPath"]], "dest": dest})
            try:
                r = json.loads(body.decode("utf-8"))
            except Exception:  # noqa: BLE001
                r = {}
            chk("API /api/copy_files 复制 2 个",
                st == 200 and r.get("copied") == 2 and not r.get("failed"),
                f"status={st}, copied={r.get('copied')}")
            st, body = jpost("/api/copy_files",
                             {"paths": [a["absPath"], a["absPath"]], "dest": dest})
            try:
                r2 = json.loads(body.decode("utf-8"))
            except Exception:  # noqa: BLE001
                r2 = {}
            chk("API /api/copy_files 重名自动改名",
                st == 200 and r2.get("copied") == 2, f"copied={r2.get('copied')}")
            chk("API /api/copy_files 目标目录共 4 个文件",
                len(os.listdir(dest)) == 4, str(sorted(os.listdir(dest))))
            st, body = jpost("/api/copy_files",
                             {"paths": [a["absPath"]], "dest": "Z:\\不存在的目录"})
            try:
                r3 = json.loads(body.decode("utf-8"))
            except Exception:  # noqa: BLE001
                r3 = {}
            chk("API /api/copy_files 坏目标不崩",
                st == 200 and r3.get("copied") == 0 and len(r3.get("failed", [])) == 1,
                f"status={st}")

            st, _ = jget("/api/beacon?event=selftest_ping")
            chk("API /api/beacon 收信标", st == 200, f"status={st}")
            st, bl = jget("/api/_beacons")
            chk("API /api/_beacons 读得回",
                st == 200 and any(b.get("event") == "selftest_ping"
                                  for b in (bl or {}).get("beacons", [])),
                f"status={st}")

            # ---- v1.2 新接口 ----
            st, rd = jget("/api/recent_dirs")
            chk("API /api/recent_dirs 返回目录列表",
                st == 200 and isinstance((rd or {}).get("dirs"), list),
                f"status={st}, dirs={rd}")
            st, of = jget("/api/open_file?path=" +
                          urllib.parse.quote(os.path.join(tmp, "nope.txt")))
            chk("API /api/open_file 坏路径返回 ok=false",
                st == 200 and of.get("ok") is False, f"status={st}, {of}")
            st, sv = jpost("/api/save_text",
                           {"content": "自检内容", "name": "selftest.txt"})
            try:
                svj = json.loads(sv.decode("utf-8")) if isinstance(sv, bytes) else {}
            except Exception:  # noqa: BLE001
                svj = {}
            chk("API /api/save_text 无窗口时返回 path=null（不弹框）",
                st == 200 and svj.get("path") is None,
                f"status={st}, {svj}")

            # ---- v1.3 语言 round-trip（快照 lang.txt，用完还原，不污染用户设置） ----
            lang_file = lang_path()
            lang_orig_bytes = None
            try:
                if os.path.isfile(lang_file):
                    with open(lang_file, "rb") as f:
                        lang_orig_bytes = f.read()
            except OSError:
                lang_orig_bytes = None
            orig_lang = (lang_orig_bytes or b"").decode("utf-8", "replace").strip().lower()
            if orig_lang not in ("zh", "en"):
                orig_lang = "zh"
            try:
                stl, lg = jget("/api/lang")
                chk("API /api/lang 返回语言",
                    stl == 200 and (lg or {}).get("lang") in ("zh", "en"),
                    f"status={stl}, {lg}")
                stl, raw2 = jpost("/api/set_lang", {"lang": "en"})
                try:
                    lg2 = json.loads(raw2.decode("utf-8")) if isinstance(raw2, bytes) else {}
                except Exception:  # noqa: BLE001
                    lg2 = {}
                chk("API /api/set_lang 切换为 en",
                    stl == 200 and lg2.get("lang") == "en",
                    f"status={stl}, {lg2}")
                stl, lg3 = jget("/api/lang")
                chk("API /api/lang 读得回 en",
                    stl == 200 and (lg3 or {}).get("lang") == "en",
                    f"status={stl}, {lg3}")
                try:
                    with open(lang_file, encoding="utf-8-sig") as f:
                        disk_lang = f.read().strip()
                except OSError:
                    disk_lang = ""
                chk("API /api/set_lang 已落盘 lang.txt", disk_lang == "en", disk_lang)
                stl, raw4 = jpost("/api/set_lang", {"lang": "xx"})
                try:
                    lg4 = json.loads(raw4.decode("utf-8")) if isinstance(raw4, bytes) else {}
                except Exception:  # noqa: BLE001
                    lg4 = {}
                chk("API /api/set_lang 非法值被拒（保持 en）",
                    stl == 200 and lg4.get("lang") == "en",
                    f"status={stl}, {lg4}")
            finally:
                # 还原 lang.txt 与内存态
                try:
                    if lang_orig_bytes is None:
                        if os.path.isfile(lang_file):
                            os.remove(lang_file)
                    else:
                        with open(lang_file, "wb") as f:
                            f.write(lang_orig_bytes)
                except OSError:
                    pass
                api.lang = orig_lang
    finally:
        _sh.rmtree(tmp, ignore_errors=True)
        if dest:
            _sh.rmtree(dest, ignore_errors=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    return 0 if rep["ok"] else 1


# ------------------------------------------------------------ 主入口
def _get_out(argv):
    """支持 --out=FILE 与 --out FILE 两种写法"""
    for a in argv:
        if a.startswith("--out="):
            return a.split("=", 1)[1]
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        out = _get_out(argv)
        if not out:
            print("用法: --selftest --out=FILE")
            return 2
        return selftest(os.path.abspath(out))

    if not os.path.isfile(page_path()):
        _msg(st(load_lang(), "missing_page").format(page=PAGE_FILE), 0x10,
             st(load_lang(), "title"))
        return 2

    if not acquire_single_instance():
        notify_already_running(load_lang())
        return 0

    page = load_page()
    port = find_port()
    # 本地 API 直接挂 http 服务（/api/*），页面同源 fetch 调用，
    # 不依赖 pywebview 的 JS bridge（6.x 注入不可靠，实测页面探测不到）
    api = Api()
    serve(port, page, api)
    write_runtime(port)

    import webview

    storage = os.path.join(appdata_dir(), "webview")
    for key, val in (("ALLOW_DOWNLOADS", True),
                     ("PRIVATE_MODE", False),
                     ("STORAGE_PATH", storage)):
        try:
            webview.settings[key] = val
        except Exception:  # noqa: BLE001 —— 不同 pywebview 版本键位略有差异
            pass

    try:
        webview.create_window(
            st(api.lang, "title"),     # v1.3：窗口标题随记忆的语言
            f"http://127.0.0.1:{port}/",
            width=1100, height=760, min_size=(860, 560),
            resizable=True,
        )
        webview.start()
    finally:
        remove_runtime()
    return 0


if __name__ == "__main__":
    sys.exit(main())
