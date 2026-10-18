// TxtSeeker v1.4 真实浏览器冒烟（Edge headless + CDP，file:// 打开单文件 HTML）
// 验证：主题切换 / 搜索历史下拉 / 检索方案面板 / CSV 菜单项 / 零 console error
import { spawn } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const APP = 'file:///E:/workbuddy/2026-10-18-08-03-52/TxtSeeker/TxtSeeker.html';
const PORT = 9333;
const PROFILE = path.join(os.tmpdir(), 'txtseeker_v14_smoke');

// file:// 下探测 /api/info 必然触发 CORS 报错（预期行为，在线版/桌面版都不会有）
const NOISE = /favicon|ERR_FILE|ERR_PROXY|net::|Failed to load resource|CORS policy|\/api\/info/i;
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail !== undefined ? '  [' + detail + ']' : ''));
}

async function main() {
  const edge = spawn(EDGE, [
    '--headless=new', '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + PROFILE, '--no-first-run', '--no-default-browser-check',
    '--window-size=1200,860', APP,
  ], { stdio: 'ignore' });

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let wsUrl = null;
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find(t => t.type === 'page' && t.url.includes('TxtSeeker.html'));
      if (page) { wsUrl = page.webSocketDebuggerUrl; break; }
    } catch (e) { /* 还没起来 */ }
  }
  if (!wsUrl) { console.log('FAIL CDP 目标未出现'); edge.kill(); process.exit(1); }

  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

  let mid = 0;
  const pending = new Map();
  const errors = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    else if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') {
      const t = m.params.entry.text || '';
      const u = m.params.entry.url || '';
      if (!NOISE.test(t) && !NOISE.test(u) && !/\/api\/info/.test(u)) {
        errors.push('LOG: ' + t.slice(0, 120));
      }
    } else if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params.exceptionDetails;
      errors.push('EXC: ' + String(d.exception?.description || d.text).slice(0, 120));
    }
  };
  const call = (method, params) => new Promise(res => {
    const id = ++mid;
    pending.set(id, m => res(m.result));
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  });
  const evaluate = async expr => {
    const r = await call('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r && r.exceptionDetails) return { __err: String(r.exceptionDetails.text) };
    return r ? r.result.value : undefined;
  };

  await call('Runtime.enable');
  await call('Log.enable');
  await call('Page.enable');
  await sleep(7000);   // 等 detectDesktop 20 次探测跑完（file:// 下 5s）

  const title = await evaluate('document.title');
  check('页面标题正确', /TxtSeeker/.test(title || ''), title);
  const isDesk = await evaluate('typeof isDesktop === \'function\' ? isDesktop() : \'nofunc\'');
  check('浏览器态 isDesktop()=false', isDesk === false, String(isDesk));
  const seg = await evaluate('!!document.getElementById(\'langSeg\')');
  check('标题栏语言滑块在', seg === true);

  /* ---------- 主题 ---------- */
  const opts = await evaluate('document.querySelectorAll("[data-theme-opt]").length');
  check('视图菜单有三个主题选项', opts === 3, opts);
  const lightBg = await evaluate(`(() => {
    setTheme('light');
    const bg = getComputedStyle(document.body).backgroundColor;
    const m = bg.match(/\\d+/g).map(Number);
    return { theme: document.documentElement.dataset.theme, bg,
             lum: Math.round((m[0]*299 + m[1]*587 + m[2]*114) / 1000) };
  })()`);
  check('浅色主题生效（灰底不刺眼，亮度 180~245）',
        lightBg.theme === 'light' && lightBg.lum >= 180 && lightBg.lum <= 245, JSON.stringify(lightBg));
  const lightFg = await evaluate(`(() => {
    const c = getComputedStyle(document.body).color.match(/\\d+/g).map(Number);
    return Math.round((c[0]*299 + c[1]*587 + c[2]*114) / 1000);
  })()`);
  check('浅色主题文字足够深（对比度可读）', lightFg < 90, lightFg);
  const darkBg = await evaluate(`(() => {
    setTheme('dark');
    const bg = getComputedStyle(document.body).backgroundColor;
    const m = bg.match(/\\d+/g).map(Number);
    return { theme: document.documentElement.dataset.theme,
             lum: Math.round((m[0]*299 + m[1]*587 + m[2]*114) / 1000) };
  })()`);
  check('深色主题生效（亮度 < 80）', darkBg.theme === 'dark' && darkBg.lum < 80, JSON.stringify(darkBg));
  const stored = await evaluate(`localStorage.getItem('txtseeker.theme')`);
  check('主题选择写入 localStorage', stored === 'dark', stored);
  const toggleOn = await evaluate(`(() => {
    setTheme('light');
    return document.querySelector('[data-theme-opt="light"]').classList.contains('on');
  })()`);
  check('主题菜单高亮当前项', toggleOn === true);

  /* ---------- 搜索历史 ---------- */
  const histSetup = await evaluate(`(() => {
    const kw = document.getElementById('kw');
    kw.value = '服务器 日志';
    document.getElementById('mode').value = 'AND';
    document.getElementById('scope').value = 'content';
    pushHistory();
    kw.value = '第\\\\d+章';
    document.getElementById('mode').value = 'regex';
    pushHistory();
    document.getElementById('btnHist').click();
    const pop = document.getElementById('histPop');
    const items = pop.querySelectorAll('#histList .item');
    return { show: pop.classList.contains('show'), n: items.length,
             last: items.length ? items[0].querySelector('.k').textContent : '',
             ls: JSON.parse(localStorage.getItem('txtseeker.history') || '[]').length };
  })()`);
  check('点 🕘 打开历史下拉', histSetup.show === true);
  check('历史记录最近两条（新的在前）',
        histSetup.n === 2 && histSetup.last === '第\\d+章', JSON.stringify(histSetup));
  check('历史落盘 localStorage', histSetup.ls === 2, histSetup.ls);
  const histClick = await evaluate(`(() => {
    const items = document.querySelectorAll('#histList .item');
    items[1].click();      // 第二条 = 「服务器 日志」
    return { kw: document.getElementById('kw').value,
             mode: document.getElementById('mode').value,
             show: document.getElementById('histPop').classList.contains('show') };
  })()`);
  check('点历史项回填关键词', histClick.kw === '服务器 日志', histClick.kw);
  check('点历史项恢复匹配模式', histClick.mode === 'AND', histClick.mode);
  check('回填后自动收起下拉', histClick.show === false);
  const histClear = await evaluate(`(() => {
    document.getElementById('btnHist').click();
    clearHistory({ stopPropagation() {} });
    return { ls: localStorage.getItem('txtseeker.history'),
             txt: document.querySelector('#histList .none')?.textContent || '' };
  })()`);
  check('清空历史后显示空态', histClear.ls === '[]' && histClear.txt.includes('还没有'), JSON.stringify(histClear));

  /* ---------- 检索方案面板 ---------- */
  const picker = await evaluate(`(() => {
    openPicker('检索方案（点击套用）',
      [{ label: '章节目录', meta: '第\\\\d+章 · regex' }],
      () => {}, () => {});
    const m = document.getElementById('picker');
    const r = { show: m.classList.contains('show'),
                rows: m.querySelectorAll('.item').length,
                title: m.querySelector('h4')?.textContent || '',
                del: m.querySelectorAll('.item .del').length,
                close: m.querySelector('.foot .btn')?.textContent || '' };
    closePicker();
    r.closed = !m.classList.contains('show');
    return r;
  })()`);
  check('方案面板可打开', picker.show === true);
  check('方案面板渲染条目', picker.rows === 1 && picker.title.includes('检索方案'), JSON.stringify(picker));
  check('方案条目带删除按钮', picker.del === 1);
  check('方案面板有关闭按钮', picker.close === '关闭', picker.close);
  check('方案面板可关闭', picker.closed === true);

  /* ---------- 菜单项 ---------- */
  const menu = await evaluate(`(() => {
    const txt = document.getElementById('menuFile').textContent;
    const act = document.getElementById('menuAct').textContent;
    const view = document.getElementById('menuView').textContent;
    return { csv: txt.includes('.csv'), scheme: act.includes('检索方案'),
             dark: view.includes('深色') && view.includes('浅色') && view.includes('跟随系统') };
  })()`);
  check('文件菜单含「导出结果表格(.csv)」', menu.csv === true);
  check('操作菜单含「检索方案」', menu.scheme === true);
  check('视图菜单含三种主题', menu.dark === true);

  /* ---------- 英文态 ---------- */
  const en = await evaluate(`(() => {
    setLang('en');
    const txt = document.getElementById('menuView').textContent;
    const kw = document.getElementById('histPop').textContent;
    return { view: txt, hist: kw,
             theme: document.querySelector('[data-theme-opt="light"]').textContent };
  })()`);
  check('英文态主题菜单已翻译',
        en.view.includes('Dark') && en.view.includes('Light') && en.view.includes('Follow system'),
        en.view);
  check('英文态历史面板已翻译', en.hist.includes('Recent searches'), en.hist.slice(0, 40));
  await evaluate(`setLang('zh')`);
  await sleep(300);

  await sleep(600);
  check('零 console error / exception',
        errors.length === 0, errors.slice(0, 3).join(' | '));

  const fails = results.filter(r => !r.ok);
  console.log(`\n冒烟结果: ${results.length - fails.length}/${results.length} 通过`);
  ws.close();
  edge.kill();
  try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) { /* ignore */ }
  process.exit(fails.length ? 1 : 0);
}

main().catch(e => { console.error('💥', e); process.exit(1); });
