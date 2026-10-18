/* v1.3.1 在线版（纯浏览器）链路无头 DOM mock 验证
 * 从交付物 TxtSeeker.html 提取整段 <script>，mock 浏览器全局对象后执行，
 * 驱动 browserSave / openSelFile / saveSelected / saveAll 真实函数。
 * 运行：node _browser_test.mjs
 */
import fs from "node:fs";

const html = fs.readFileSync("TxtSeeker.html", "utf8");
const core = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
if(!core) { console.error("未找到 <script> 块"); process.exit(1); }

/* ---------- 浏览器全局 mock ---------- */
const elements = new Map();
function mkEl(id){
  const cls = {
    _s: new Set(),
    add(...c){ c.forEach(x => cls._s.add(x)); },
    remove(...c){ c.forEach(x => cls._s.delete(x)); },
    toggle(c, f){ const on = f === undefined ? !cls._s.has(c) : !!f;
                 on ? cls._s.add(c) : cls._s.delete(c); return on; },
    contains(c){ return cls._s.has(c); }
  };
  return {
    id, innerHTML: "", textContent: "", value: "", checked: false,
    disabled: false, href: "", download: "", dataset: {}, scrollTop: 0,
    style: new Proxy({}, {get: () => "", set: () => true}),
    classList: cls, children: [], listeners: {},
    addEventListener(t, fn){ (this.listeners[t] ||= []).push(fn); },
    appendChild(c){ this.children.push(c); return c; },
    remove(){}, click(){ this._clicked = (this._clicked || 0) + 1; },
    focus(){ this._focused = true; }, blur(){ this._focused = false; },
    scrollIntoView(){}, closest(){ return null; },
    querySelector(){ return mkEl("q-" + Math.random().toString(36).slice(2, 7)); },
    querySelectorAll(){ return []; }, setAttribute(){}
  };
}
global.__created = [];
global.document = {
  getElementById(id){ if(!elements.has(id)) elements.set(id, mkEl(id));
                      return elements.get(id); },
  querySelectorAll(){ return []; },
  createElement(tag){ const el = mkEl("dyn-" + tag); global.__created.push(el);
                      return el; },
  createDocumentFragment(){ return mkEl("frag"); },
  addEventListener(){}, title: "",
  documentElement: mkEl("html"),
  body: mkEl("body")
};
const store = {};
global.localStorage = {
  getItem: k => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; }
};
Object.defineProperty(globalThis, "navigator",
  { value: { language: "zh-CN" }, configurable: true });
global.__opened = [];
global.window = { open: url => { global.__opened.push(url); return { focus(){} }; } };
global.__urls = [];
URL.createObjectURL = f => { global.__urls.push(f); return "blob:mock/" + global.__urls.length; };
URL.revokeObjectURL = () => {};
global.__alerts = [];
global.alert = m => { global.__alerts.push(m); };
global.performance = { now: () => Date.now() };

/* v1.4：主题 / 方案面板需要的浏览器 API */
global.__sysLight = false;                 // 可切换的"系统深浅色"
global.matchMedia = q => ({
  get matches(){ return /prefers-color-scheme:\s*light/.test(q) ? global.__sysLight : false; },
  addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){}
});
global.window.matchMedia = global.matchMedia;
global.__promptQueue = [];
global.__promptSeen = [];
global.prompt = (msg, def) => {
  global.__promptSeen.push({msg, def});
  return global.__promptQueue.length ? global.__promptQueue.shift() : null;
};
global.__confirmQueue = [];
global.confirm = msg => {
  global.__confirmSeen = (global.__confirmSeen || []).concat([msg]);
  return global.__confirmQueue.length ? !!global.__confirmQueue.shift() : true;
};
global.__docCreated = [];

/* ---------- 执行页面脚本 ---------- */
const C = new Function(core + `
  return { I18N, LANG, t, results, files, isDesktop,
           browserSave, openSelFile, saveSelected, saveAll, _doSave,
           applyLang, setLang,
           PREF, applyTheme, setTheme, sysLight,
           pushHistory, renderHistory, applyHistory, clearHistory,
           saveScheme, applyScheme, openPicker, closePicker, exportCSV,
           kvGet, kvSet, loadPrefs,
           getHist: () => histList, getSchemes: () => schemes };`)();

/* ---------- 断言工具 ---------- */
let pass = 0, fail = 0;
function ok(name, cond, extra){
  if(cond){ pass++; console.log("✅ " + name); }
  else { fail++; console.log("❌ " + name + (extra ? "  → " + extra : "")); }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const $ = id => document.getElementById(id);
// saveSelected/saveAll 内部对 _doSave 是 fire-and-forget（按钮处理器无需 await），
// 测试侧轮询等待浏览器保存流程走完（以最终 alert 为完成信号）
async function waitSaved(timeout = 8000){
  const t0 = Date.now();
  while(Date.now() - t0 < timeout){
    if(global.__alerts.some(a => /已保存|Saved/.test(a))) return true;
    await sleep(50);
  }
  return false;
}

const row = (relPath, extra) => Object.assign({
  relPath, dir: relPath.split("/").slice(0, -1).join("/"),
  size: 1024, mtime: Date.now(), hits: 1, previews: [], enc: "UTF-8"
}, extra);

(async () => {
  await sleep(300);   // 让顶层 initLang/applyLang/detectDesktop 跑完

  /* ---- B1 浏览器态识别 ---- */
  ok("B1 纯浏览器态 isDesktop()=false", C.isDesktop() === false);

  /* ---- B2 中英文案 ---- */
  ok("B2a zh browserSaving", C.t("sv.browserSaving", {n: 2}) ===
     "正在逐份保存 2 个文件（浏览器下载）…", C.t("sv.browserSaving", {n: 2}));
  ok("B2b en browserSaving", C.I18N.en["sv.browserSaving"] ===
     "Saving {n} file(s) one by one (browser downloads)…");

  /* ---- B3 browserSave：saveSelected 全链路 ---- */
  C.results.length = 0;
  C.results.push(
    row(" novels/武侠/天龙八部.txt", { file: {name: "f1"}, checked: true }),
    row("logs/run.log",             { file: {name: "f2"}, checked: true }),
    row("desk/无file.txt", { absPath: "D:/x/无file.txt", checked: true })
  );
  global.__urls.length = 0; global.__alerts.length = 0; global.__created.length = 0;
  C.saveSelected();
  ok("B3a 等待浏览器保存流程完成", await waitSaved());
  const anchors = global.__created.filter(e => e.download);
  ok("B3b 过滤后只保存有 file 的 2 份", global.__urls.length === 2,
     "urls=" + global.__urls.length);
  ok("B3c 逐份创建 objectURL", global.__urls.every(f => f && f.name));
  ok("B3d 下载锚点均被 click", anchors.length === 2 &&
     anchors.every(a => a._clicked === 1), "anchors=" + anchors.length);
  ok("B3e 下载文件名正确", anchors.map(a => a.download).join("|") ===
     "天龙八部.txt|run.log", anchors.map(a => a.download).join("|"));
  ok("B3f 完成提示（中文）", global.__alerts.some(a =>
     a.includes("已保存 2 个文件")), JSON.stringify(global.__alerts));
  ok("B3g 状态栏进度", $("stLeft").innerHTML.includes("已保存 2 个文件"),
     $("stLeft").innerHTML);

  /* ---- B4 browserSave：saveAll 入口同样分流 ---- */
  global.__urls.length = 0; global.__alerts.length = 0; global.__created.length = 0;
  C.saveAll();
  ok("B4 saveAll 也走浏览器下载（3 行中 2 个有 file）",
     (await waitSaved()) && global.__urls.length === 2,
     "urls=" + global.__urls.length);

  /* ---- B5 openSelFile 浏览器分支：有 file → 新标签打开 ---- */
  global.__opened.length = 0; global.__alerts.length = 0;
  await C.openSelFile();  ok("B5a window.open 被调用", global.__opened.length === 1,
     "opened=" + global.__opened.length);
  ok("B5b 打开的是 blob URL", /^blob:mock\//.test(global.__opened[0] || ""),
     global.__opened[0]);
  ok("B5c 状态栏提示已打开", $("stLeft").innerHTML.includes("已在新标签页打开"),
     $("stLeft").innerHTML);

  /* ---- B6 openSelFile 浏览器分支：无 file → 明确提示 ---- */
  C.results.length = 0;
  C.results.push(row("desk/仅路径.txt",
    { absPath: "D:/x/仅路径.txt", checked: true }));
  global.__opened.length = 0; global.__alerts.length = 0;
  await C.openSelFile();
  ok("B6a 无 file 时不乱开标签", global.__opened.length === 0);
  ok("B6b 给出在线版限制提示", global.__alerts.some(a =>
     a.includes("只能打开")), JSON.stringify(global.__alerts));

  /* ---- B7 英文态下 browserSave ---- */
  C.setLang("en");
  await sleep(50);
  C.results.length = 0;
  C.results.push(row("a/英文.txt", { file: {name: "f3"}, checked: true }));
  global.__alerts.length = 0; global.__urls.length = 0; global.__created.length = 0;
  C.saveSelected();
  ok("B7a 英文完成提示", (await waitSaved()) && global.__alerts.some(a =>
     a.includes("Saved 1 file(s)")), JSON.stringify(global.__alerts));

  /* ---- B8 滑块回归（v1.3.1 标题栏） ---- */
  C.setLang("zh");
  await sleep(50);
  ok("B8a 中文态滑块回位", $("langSeg").classList.contains("en") === false
     && $("segZh").classList.contains("on") === true);
  C.setLang("en");
  await sleep(50);
  ok("B8b 英文态滑块滑动", $("langSeg").classList.contains("en") === true
     && $("segEn").classList.contains("on") === true);
  C.setLang("zh");
  await sleep(50);

  /* ================================================================
     v1.4 新功能
     ================================================================ */

  /* ---- B9 外观主题 ---- */
  global.__sysLight = false;
  C.applyTheme("light");
  ok("B9a 浅色主题写入 data-theme",
     document.documentElement.dataset.theme === "light",
     document.documentElement.dataset.theme);
  C.applyTheme("dark");
  ok("B9b 深色主题写入 data-theme",
     document.documentElement.dataset.theme === "dark");
  C.applyTheme("auto");
  ok("B9c auto + 系统深色 → dark",
     document.documentElement.dataset.theme === "dark");
  global.__sysLight = true;
  C.applyTheme("auto");
  ok("B9d auto + 系统浅色 → light",
     document.documentElement.dataset.theme === "light");
  ok("B9e sysLight() 跟随系统", C.sysLight() === true);
  global.__sysLight = false;
  C.setTheme("light");
  ok("B9f setTheme 落盘 localStorage",
     store["txtseeker.theme"] === "light", store["txtseeker.theme"]);

  /* ---- B10 搜索历史 ---- */
  store["txtseeker.history"] = "";
  $("kw").value = "服务器 日志";
  $("mode").value = "AND";
  $("scope").value = "content";
  $("extSel").value = "txt";
  C.pushHistory();
  ok("B10a 搜索后记入历史",
     C.getHist().length === 1 && C.getHist()[0].kw === "服务器 日志",
     JSON.stringify(C.getHist()));
  ok("B10b 历史落盘 localStorage",
     JSON.parse(store["txtseeker.history"]).length === 1);
  C.pushHistory();
  ok("B10c 相同搜索不重复记录", C.getHist().length === 1,
     "len=" + C.getHist().length);
  $("kw").value = "正则测试"; $("mode").value = "regex";
  C.pushHistory();
  ok("B10d 不同模式单独记录",
     C.getHist().length === 2 && C.getHist()[0].kw === "正则测试");
  for(let i = 0; i < 12; i++){
    $("kw").value = "kw" + i; $("mode").value = "AND";
    C.pushHistory();
  }
  ok("B10e 历史上限 10 条", C.getHist().length === 10, "len=" + C.getHist().length);
  ok("B10f 新记录排最前", C.getHist()[0].kw === "kw11", C.getHist()[0].kw);
  $("kw").value = ""; $("mode").value = "";
  C.applyHistory(0);
  ok("B10g 点击历史回填关键词", $("kw").value === "kw11");
  ok("B10h 回填同时恢复模式", $("mode").value === "AND");
  C.clearHistory();
  ok("B10i 清空历史", C.getHist().length === 0 &&
     store["txtseeker.history"] === "[]");

  /* ---- B11 检索方案 ---- */
  $("kw").value = "第\\d+章"; $("mode").value = "regex";
  $("scope").value = "both"; $("extSel").value = "text";
  $("caseS").checked = true; $("subdir").checked = false;
  global.__promptQueue.push("  章节目录  ");
  C.saveScheme();
  ok("B11a 保存方案（命名去空格）",
     C.getSchemes().length === 1 && C.getSchemes()[0].name === "章节目录",
     JSON.stringify(C.getSchemes()));
  ok("B11b 方案含全部条件", (() => {
     const s = C.getSchemes()[0];
     return s.kw === "第\\d+章" && s.mode === "regex" && s.scope === "both"
         && s.ext === "text" && s.cs === true && s.sub === false;
  })());
  ok("B11c 方案落盘 localStorage",
     JSON.parse(store["txtseeker.schemes"]).length === 1);
  global.__promptQueue.push("章节目录");
  $("kw").value = "第二版";
  C.saveScheme();
  ok("B11d 同名方案覆盖不重复",
     C.getSchemes().length === 1 && C.getSchemes()[0].kw === "第二版",
     JSON.stringify(C.getSchemes()));
  $("kw").value = ""; global.__alerts.length = 0;
  C.saveScheme();
  ok("B11e 空关键词拒绝保存",
     global.__alerts.some(a => a.includes("无法保存")) && C.getSchemes().length === 1,
     JSON.stringify(global.__alerts));
  $("kw").value = ""; $("mode").value = ""; $("scope").value = "";
  $("extSel").value = ""; $("caseS").checked = false;
  C.applyScheme(0);
  ok("B11f 套用方案回填全部条件",
     $("kw").value === "第二版" && $("mode").value === "regex"
     && $("scope").value === "both" && $("extSel").value === "text"
     && $("caseS").checked === true);
  C.openPicker("标题", [{label: "A", meta: "m1"}], () => {}, () => {});
  ok("B11g 方案面板可打开", $("picker").classList.contains("show") === true);
  C.closePicker();
  ok("B11h 方案面板可关闭", $("picker").classList.contains("show") === false);

  /* ---- B12 导出 CSV ---- */
  C.results.length = 0;
  C.results.push(row("novels/武侠/天龙八部.txt",
    { absPath: "D:/书/天龙八部.txt", hits: 12, enc: "GBK", size: 2048,
      mtime: Date.UTC(2026, 9, 18, 4, 30, 0), checked: true }));
  C.results.push(row('logs/a,b"c.txt',
    { hits: 3, enc: "UTF-8", size: 99,
      mtime: Date.UTC(2026, 9, 18, 5, 0, 0), nameOnly: true }));
  global.__urls.length = 0; global.__alerts.length = 0; global.__created.length = 0;
  C.exportCSV();
  ok("B12a CSV 生成一次 Blob", global.__urls.length === 1);
  const blob = global.__urls[0];
  // Blob.text() 会按规范吞掉 BOM，所以 BOM 必须查原始字节
  const rawBytes = blob ? new Uint8Array(await blob.arrayBuffer()) : new Uint8Array();
  ok("B12b CSV 带 UTF-8 BOM",
     rawBytes[0] === 0xEF && rawBytes[1] === 0xBB && rawBytes[2] === 0xBF,
     Array.from(rawBytes.slice(0, 3)).join(","));
  const csvText = new TextDecoder("utf-8").decode(rawBytes);
  const csvLines = csvText.split("\r\n");
  ok("B12c 表头 8 列", csvLines[0].split(",").length === 8, csvLines[0]);
  ok("B12d 中文表头正确", csvLines[0].startsWith("文件名,相对路径,所在目录"), csvLines[0]);
  ok("B12e 数据行含文件名与命中数",
     csvLines[1].includes("天龙八部.txt") && csvLines[1].includes(",12,"), csvLines[1]);
  ok("B12f 类型列区分命中行/文件名",
     csvLines[1].includes("命中行") && csvLines[2].includes("文件名"),
     csvLines[1] + " || " + csvLines[2]);
  ok("B12g 逗号与引号被转义", csvLines[2].includes('"logs/a,b""c.txt"'), csvLines[2]);
  const csvAnchor = global.__created.filter(e => e.download)[0] || {};
  ok("B12h 下载文件名带日期",
     /^TxtSeeker结果_\d{4}-\d{2}-\d{2}\.csv$/.test(csvAnchor.download || ""),
     csvAnchor.download);
  ok("B12i 状态栏提示导出完成",
     $("stLeft").innerHTML.includes("已导出 CSV"), $("stLeft").innerHTML);

  /* ---- B13 偏好读回（模拟重启后恢复） ---- */
  store["txtseeker.theme"] = "light";
  store["txtseeker.history"] = JSON.stringify([{kw: "读回测试", mode: "OR", scope: "name"}]);
  store["txtseeker.schemes"] = JSON.stringify([{name: "读回方案", kw: "abc", mode: "AND", scope: "content"}]);
  C.PREF.theme = "auto";
  await C.loadPrefs();
  ok("B13a loadPrefs 恢复主题",
     C.PREF.theme === "light" && document.documentElement.dataset.theme === "light",
     C.PREF.theme + "/" + document.documentElement.dataset.theme);
  ok("B13b loadPrefs 恢复历史",
     C.getHist().length === 1 && C.getHist()[0].kw === "读回测试");
  ok("B13c loadPrefs 恢复方案",
     C.getSchemes().length === 1 && C.getSchemes()[0].name === "读回方案");

  console.log(`\n结果: ${pass} 通过, ${fail} 失败`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error("💥", e); process.exit(1); });
