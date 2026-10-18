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

/* ---------- 执行页面脚本 ---------- */
const C = new Function(core + `
  return { I18N, LANG, t, results, files, isDesktop,
           browserSave, openSelFile, saveSelected, saveAll, _doSave,
           applyLang, setLang };`)();

/* ---------- 断言工具 ---------- */
let pass = 0, fail = 0;
function ok(name, cond, extra){
  if(cond){ pass++; console.log("✅ " + name); }
  else { fail++; console.log("❌ " + name + (extra ? "  → " + extra : "")); }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const $ = id => elements.get(id);
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

  console.log(`\n结果: ${pass} 通过, ${fail} 失败`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error("💥", e); process.exit(1); });
