# TxtSeeker — TXT 全文搜索定位工具

> 在堆积如山的 TXT 文件里，一眼找到含有那段文字的文件。
> **纯本地运行，零上传，零依赖联网。**
>
> © 永远的兰兰 / Lanlan Eternal · v1.4.0

---

## 三种用法（同一颗心脏）

| 用法 | 文件 | 适合场景 |
| --- | --- | --- |
| 🖥️ **桌面版** | `TxtSeeker.exe`（Windows 单文件，约 17MB） | 日常主力：整目录递归搜索、批量另存、定位文件夹 |
| 📄 **本地 HTML 版** | `TxtSeeker.html`（单文件，双击即用） | 不想装 exe / 非 Windows 系统（Linux、Android、iOS 均可） |
| 🌐 **在线版** | <https://podcatcher962.github.io/TxtSeeker/> | 随手用：浏览器打开，把文件拖进去就能搜 |

三种形态共用同一套界面与逻辑；桌面版额外提供「整目录加载 / 批量另存到指定目录 / 打开所在文件夹」等本地能力。

---

## 功能特性

**搜索**
- 🔍 全文内容搜索，支持 **内容 / 文件名 / 两者** 三种范围
- 🔗 关键词 **AND / OR / 正则表达式**
- 🔠 大小写敏感开关
- 📁 递归子目录；可限定目录层级
- 🧬 编码自动识别（UTF-8 / GBK 等），中文 TXT 无乱码

**结果**
- 📊 结果表：文件名、命中数、编码、大小、修改时间、所在目录，七列可点击排序
- 👁️ 预览面板：命中行高亮 + 行号，一眼看到上下文
- ☑️ 行勾选 / 全选，配合「另存」批量导出命中文件
- 💾 **另存选中文件 / 另存全部命中**（桌面版整批复制；在线版逐份下载）
- 📄 打开选中文件（默认程序）/ 定位所在文件夹
- 🧾 导出结果清单（.txt）/ 导出命中内容摘录（.md）
- 📊 **导出结果表格（.csv）**：文件名、路径、命中数、编码、大小、修改时间，Excel / WPS 双击即开（UTF-8 BOM，中文不乱码）
- 🕘 最近目录记忆（桌面版）

**效率（v1.4 新增）**
- ⏱️ **搜索历史**：关键词框右侧 🕘 记住最近 10 次搜索，点击即回填并重搜（相同搜索自动去重）
- 💼 **检索方案**：把「关键词 + 模式 + 范围 + 扩展名 + 大小写 + 子目录」整套存成命名方案，下次一键套用；最多 20 套
- 🎨 **深浅主题**：深色 / 浅色 / 跟随系统，浅色是灰底不刺眼（不是刺眼纯白），选择自动记忆

**体验**
- 🌗 中英双语：标题栏「中 / EN」滑块一键切换，选择自动记忆（英语用户无需先认出"语言"二字）
- 🖱️ 支持拖放：把文件或文件夹拖进窗口即可加载
- 🧭 单文件、免安装、无注册表、无后台驻留

**隐私与安全**
- 桌面版通过 `127.0.0.1` 本机回环与内置页面通信，**没有任何数据离开你的电脑**（打开页面时浏览器不会提示"上传至此站点"——那只是本地回环地址）
- 不收集任何信息、无遥测、无账号
- 在线版同样只在浏览器本地内存中处理你拖入的文件

---

## 快速上手

### 桌面版（exe）
1. 双击 `TxtSeeker.exe`（Windows 10/11，无需安装 Python）
2. 「打开目录…」选择 TXT 所在文件夹，或直接把文件/文件夹拖进窗口
3. 输入关键词 → 「开始搜索」
4. 勾选命中行 → 「另存选中文件…」选目标目录即可整批导出

### 本地 HTML 版
直接双击 `TxtSeeker.html`，用任意现代浏览器打开即可。

### 在线版
打开 <https://podcatcher962.github.io/TxtSeeker/> →「进入应用」→ 把 TXT 文件拖进虚线框 → 输入关键词搜索 → 「文件 → 另存选中文件…」逐份下载。
> 浏览器安全模型限制：在线版只能处理「拖入或选择的文件」，无法像桌面版那样扫描整个磁盘目录。

---

## 从源码构建（开发者）

```bash
# 依赖：Python 3.13+、pywebview、PyInstaller
pip install pywebview pyinstaller

# 打包桌面版（spec 内为绝对路径，按本机实际路径调整）
python -m PyInstaller --clean --noconfirm TxtSeeker.spec

# 跑测试（Node 22+）
node test_core.mjs        # 65 项：搜索内核 / 双语字典 / i18n 链路
node _browser_test.mjs    # 19 项：在线版（纯浏览器）保存/打开链路
```

仓库文件说明：

| 文件 | 作用 |
| --- | --- |
| `app.py` | pywebview 桌面壳：loopback HTTP + `/api/*` 本地接口、双语壳文案、语言持久化 |
| `TxtSeeker.html` | 全部界面与逻辑（单文件，桌面版与在线版共用） |
| `index.html` | 在线版落地页（GitHub Pages 入口） |
| `test_core.mjs` | Node 测试：搜索内核、双语一致性、i18n 无漏翻 |
| `_browser_test.mjs` | Node 无头 DOM mock：在线版保存/打开链路 |
| `_exe_test.py` | 真机验收脚本（对话框枚举、语言探针等 23 项） |
| `_exe_unpack.py` | 解包 exe 校验内嵌 HTML 与源码一致 |
| `_pick_probe.py` | 文件夹对话框行为探针 |
| `gen_icon.py` / `TxtSeeker.ico` | 图标生成脚本与成品 |
| `TxtSeeker.spec` | PyInstaller 打包配置 |

---

## 免责声明

本工具仅在本地检索你授权目录内的文本文件，不绕过任何技术保护措施，不抓取网络内容。
请勿用于检索/传播受版权保护或法律法规禁止的内容，由此产生的后果由使用者自行承担。

---

# English

## TxtSeeker — Full-Text Search & Locator for TXT Files

> Find every TXT file containing that phrase — across thousands of files, in seconds.
> **100% local. Nothing ever leaves your machine.**
>
> © 永远的兰兰 / Lanlan Eternal · v1.4.0

### Three ways to run

| Flavor | File | Best for |
| --- | --- | --- |
| 🖥️ **Desktop app** | `TxtSeeker.exe` (Windows, single file, ~17MB) | Daily driver: whole-folder recursive scan, batch export, reveal in Explorer |
| 📄 **Local HTML** | `TxtSeeker.html` (single file) | No exe wanted / Linux, Android, iOS |
| 🌐 **Online** | <https://podcatcher962.github.io/TxtSeeker/> | Quick use: drop files into the browser |

All three share the same UI and engine; the desktop build adds whole-folder loading, batch copy to a destination folder, and "open containing folder".

### Features
- Full-text search with **Content / Filename / Both** scopes
- **AND / OR / RegEx** keyword modes, case-sensitivity toggle
- Recursive subdirectories, depth limit
- Automatic encoding detection (UTF-8 / GBK, …) — no mojibake for Chinese TXT
- Sortable result table (name, hits, encoding, size, mtime, directory)
- Preview pane with highlighted hit lines + line numbers
- Row checkboxes / select-all → **Save Selected / Save All Hits**
- Open file with default app / reveal in folder
- Export result list (.txt) / hit excerpts (.md)
- **Export results table (.csv)** — name, path, hits, encoding, size, mtime; opens straight in Excel / WPS (UTF-8 BOM, Chinese-safe)
- Recent-folders memory (desktop)

### New in v1.4
- **Search history** — the 🕘 button next to the keyword box keeps your last 10 searches; one click refills and re-searches (identical searches are de-duplicated)
- **Search schemes** — store keywords + mode + scope + extension + case + subfolder as a named scheme, then apply it in one click (up to 20)
- **Dark / Light / Follow-system theme** — the light theme is a soft grey (not glaring white), and your choice is remembered

### Basics
- **Bilingual UI (中 / EN)** — one-click toggle in the title bar, choice remembered
- Drag & drop files or folders
- Single file, portable, no installer, no background service

### Privacy
The desktop app talks to its embedded page over `127.0.0.1` loopback only — **no data ever leaves your computer**. The browser build processes dropped files in local memory only. No telemetry, no accounts, no network calls.

### Quick start
1. **Desktop**: run `TxtSeeker.exe` → "Open Folder…" (or drag & drop) → type keywords → Search → check rows → "Save Selected Files…"
2. **Local HTML**: double-click `TxtSeeker.html`
3. **Online**: open <https://podcatcher962.github.io/TxtSeeker/> → "Enter App" → drop TXT files in → search → File → "Save Selected Files…" to download one by one
   *(Browsers can't scan disk folders — the online build only sees files you drop or pick.)*

### Build from source
```bash
pip install pywebview pyinstaller
python -m PyInstaller --clean --noconfirm TxtSeeker.spec   # adjust absolute paths in spec
node test_core.mjs        # 65 checks: search core + bilingual consistency
node _browser_test.mjs    # 19 checks: browser-only save/open flows
```

### Disclaimer
This tool only searches text files in folders you explicitly choose, locally. It bypasses no protection measures and fetches nothing from the network. Do not use it to locate or distribute copyrighted or unlawful content; users bear all responsibility for their usage.
