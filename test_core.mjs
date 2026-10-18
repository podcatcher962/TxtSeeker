// TxtSeeker 核心逻辑自测：直接从交付的 HTML 中提取 /*__CORE__*/ 段执行，测的就是上线代码
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "TxtSeeker.html"), "utf8");
const m = html.match(/\/\*__CORE__\*\/([\s\S]*?)\/\*__END_CORE__\*\//);
if (!m) { console.error("未找到 CORE 代码段"); process.exit(1); }

const C = new Function(`${m[1]}; return {decodeBuffer, parseKeywords, lineMatches, searchText, hitSpans, humanSize, esc, detectEncoding, buildRegex, toGlobal, nameMatches, TXT_EXTS, TEXT_EXTS, MAX_LINE_CHARS, I18N, LANG, t};`)();

let pass = 0, fail = 0;
function eq(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log(`${ok ? "✅" : "❌"} ${name}: ${JSON.stringify(got)}${ok ? "" : "  期望 " + JSON.stringify(want)}`);
  ok ? pass++ : fail++;
}

// ---- T1 UTF-8 单关键词 + 命中行数
{
  const text = "第一行没有关键词\n今天天气不错\n无关\n明天天气怎么样？\n";
  const r = C.searchText(text, "天气", "AND", false);
  eq("T1 UTF-8 单关键词命中数", r.hits, 2);
  eq("T1 预览首行", r.previews[0], { lineno: 2, line: "今天天气不错" });
}

// ---- T2 GBK buffer 回退解码（字节由 Python 生成：你好天气\n世界和平\n）
{
  const bytes = Buffer.from([
    0xC4,0xE3, 0xBA,0xC3, 0xCC,0xEC, 0xC6,0xF8, 0x0A,
    0xCA,0xC0, 0xBD,0xE7, 0xBA,0xCD, 0xC6,0xBD, 0x0A,
  ]);
  const text = C.decodeBuffer(bytes);
  eq("T2 GBK 回退解码", text, "你好天气\n世界和平\n");
  const r = C.searchText(text, "世界和平", "AND", false);
  eq("T2 GBK 命中", r.hits, 1);
}

// ---- T3 AND（两词分布在不同行：应 0；同一行：应 1）
{
  const text = "世界呼吁和平\n今天天气好\n";
  eq("T3a AND 分散在不同行", C.searchText(text, "天气 世界", "AND", false).hits, 0);
  const text2 = "世界与天气\n天气\n";
  eq("T3b AND 同一行", C.searchText(text2, "天气 世界", "AND", false).hits, 1);
}

// ---- T4 OR
{
  const text = "今天天气晴\n世界需要和平\n无关内容\n";
  const r = C.searchText(text, "天气 和平", "OR", false);
  eq("T4 OR", r.hits, 2);
}

// ---- T5 引号短语
{
  const text = "他说：世界和平来之不易\n世界的和平\n";
  eq("T5a 不带引号(两词AND)", C.searchText(text, "世界 和平", "AND", false).hits, 2);
  eq("T5b 带引号短语", C.searchText(text, '"世界和平" 和平', "AND", false).hits, 1);
  eq("T5c parseKeywords", C.parseKeywords('你好 "世界和平" 结束'), ["你好", "世界和平", "结束"]);
  eq("T5d parseKeywords 空", C.parseKeywords("   "), []);
}

// ---- T6 区分大小写（按行计数：3 行各含一次）
{
  const text = "Hello\nhello\nHELLO\n";
  eq("T6a 不区分", C.searchText(text, "hello", "AND", false).hits, 3);
  eq("T6b 区分", C.searchText(text, "hello", "AND", true).hits, 1);
}

// ---- T7 空文本 / 无关键词
{
  eq("T7a 空文本", C.searchText("", "abc", "AND", false).hits, 0);
  eq("T7b 空关键词", C.searchText("abc", "", "AND", false).hits, 0);
  eq("T7c 无换行结尾", C.searchText("abc天气", "天气", "AND", false).hits, 1);
}

// ---- T8 高亮区间
{
  const spans = C.hitSpans("aa天气bb天气cc", ["天气"]);
  eq("T8 高亮区间", spans, [[2, 4], [6, 8]]);
  eq("T8b 重叠合并", C.hitSpans("abcabc", ["abc", "bca"]), [[0, 6]]);
  eq("T8c 无命中", C.hitSpans("xyz", ["abc"]), []);
}

// ---- T9 预览截断
{
  const long = "天气".repeat(200);
  const r = C.searchText(long + "\n第二行", "天气", "AND", false);
  eq("T9 预览截断长度", r.previews[0].line.length, C.MAX_LINE_CHARS + 2); // +" …"
}

// ---- T10 humanSize / esc
{
  eq("T10a", C.humanSize(512), "512B");
  eq("T10b", C.humanSize(2048), "2.0KB");
  eq("T10c", C.humanSize(5 * 1024 * 1024), "5.0MB");
  eq("T10d esc", C.esc('<a href="x">&\''), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
}

// ---- T11 CRLF / 行号
{
  const text = "a\r\n天气x\r\nb";
  const r = C.searchText(text, "天气", "AND", false);
  eq("T11 CRLF 命中行号", r.previews[0].lineno, 2);
}

// ---- T12 detectEncoding（v1.2 编码列）
{
  eq("T12a UTF-8 识别", C.detectEncoding(Buffer.from("你好天气", "utf8")), "UTF-8");
  eq("T12b GBK 识别", C.detectEncoding(Buffer.from([0xC4,0xE3, 0xBA,0xC3])), "GBK");
  eq("T12c 空文件", C.detectEncoding(Buffer.alloc(0)), "UTF-8");
}

// ---- T13 buildRegex / toGlobal（v1.2 正则模式）
{
  const re = C.buildRegex("第\\d+章", false);
  eq("T13a 编译成功", re instanceof RegExp, true);
  eq("T13b 大小写不敏感带 i", re.flags.includes("i"), true);
  eq("T13c 区分大小写无 i", C.buildRegex("abc", true).flags.includes("i"), false);
  eq("T13d 非法正则返回 null", C.buildRegex("[unclosed", false), null);
  eq("T13e 空模式返回 null", C.buildRegex("", false), null);
  const g = C.toGlobal(re);
  eq("T13f toGlobal 带 g", g.flags.includes("g"), true);
}

// ---- T14 searchText 正则模式（v1.2）
{
  const re = C.buildRegex("第\\d+章", false);
  const text = "第12章 序\n正文第 345 章开始\n无关\n这是第678章的内容\n";
  const r = C.searchText(text, "第\\d+章", "regex", false, re);
  eq("T14a 正则命中行数", r.hits, 2);
  eq("T14b 正则预览行号", r.previews.map(p => p.lineno), [1, 4]);
  eq("T14c 正则无匹配", C.searchText("abc", "\\d+", "regex", false, C.buildRegex("\\d+", false)).hits, 0);
  eq("T14d 正则未编译(传 null) 不崩", C.searchText("abc", "x", "regex", false, null).hits, 0);
  eq("T14e 正则大小写", C.searchText("ABC\nabc", "abc", "regex", true, C.buildRegex("abc", true)).hits, 1);
  eq("T14f 正则 lastIndex 状态不残留", (() => {
    const re2 = C.buildRegex("天气", false);
    C.searchText("天气\n天气", "天气", "regex", false, re2);
    return C.searchText("天气", "天气", "regex", false, re2).hits;
  })(), 1);
}

// ---- T15 hitSpans 正则高亮（v1.2）
{
  const re = C.buildRegex("\\d+", false);
  eq("T15a 正则区间", C.hitSpans("第12章共345字", null, re), [[1, 3], [5, 8]]);
  eq("T15b 空匹配不死循环", C.hitSpans("abc", null, C.buildRegex("a*", false)).length > 0, true);
  eq("T15c 关键词路径不受影响", C.hitSpans("aa天气bb", ["天气"]), [[2, 4]]);
}

// ---- T16 nameMatches 文件名匹配（v1.2）
{
  eq("T16a 文件名 AND", C.nameMatches("novel/斗破苍穹.txt", "斗破 苍穹", "AND", false), 1);
  eq("T16b 文件名 AND 缺词", C.nameMatches("novel/斗破.txt", "斗破 苍穹", "AND", false), 0);
  eq("T16c 文件名 OR", C.nameMatches("a/b.txt", "xyz b", "OR", false), 1);
  eq("T16d 文件名大小写", C.nameMatches("a/B.TXT", "b.txt", "AND", true), 0);
  eq("T16e 文件名大小写不敏感", C.nameMatches("a/B.TXT", "b.txt", "AND", false), 1);
  eq("T16f 文件名正则", C.nameMatches("vol/第12章.txt", "第\\d+章", "regex", false, C.buildRegex("第\\d+章", false)), 1);
  eq("T16g 文件名多次匹配计数", C.nameMatches("test_test_test.txt", "test", "OR", false), 3);
}

// ---- T17 旧签名兼容（不传 regex 第五参，行为不变）
{
  eq("T17a 旧四参调用", C.searchText("天气\n无关", "天气", "AND", false).hits, 1);
  eq("T17b 旧 hitSpans 两参（相邻区间合并语义不变）", C.hitSpans("天气天气", ["天气"]), [[0, 4]]);
}

// ---- T18 双语字典：zh/en 键集合必须完全一致（v1.3 i18n）
{
  const zh = Object.keys(C.I18N.zh).sort();
  const en = Object.keys(C.I18N.en).sort();
  eq("T18a 键数量一致", en.length, zh.length);
  eq("T18b 键集合一致（无漏翻）", en, zh);
  eq("T18c 字典非空", zh.length > 100, true);
}

// ---- T19 页面静态文案键无漏翻（v1.3 i18n）
{
  const used = new Set();
  for (const mm of html.matchAll(/data-i18n(?:-html|-ph|-title)?="([^"]+)"/g)) {
    used.add(mm[1]);
  }
  const missing = [...used].filter(k => !(k in C.I18N.zh) || !(k in C.I18N.en));
  eq("T19a data-i18n 键全部有双语翻译", missing, []);
  eq("T19b data-i18n 键数量合理", used.size > 40, true);
  // 动态拼接的键（t("scope."+v) / t("help."+i) / t("dir.root") 等）
  const dyn = ["scope.content", "scope.name", "scope.both",
               "help.1", "help.5", "help.9", "help.10", "dir.root", "dir.picked",
               "dt.ready", "ex.none", "st.loaded", "langseg.tip",
               "sv.browserNoFile", "sv.browserSaving", "sv.browserProgress",
               "sv.browserDone", "of.browserNoFile", "of.browserOpened"];
  const dynMissing = dyn.filter(k => !(k in C.I18N.zh) || !(k in C.I18N.en));
  eq("T19c 动态拼接键双语齐全", dynMissing, []);
}

// ---- T20 t() 取值与回退（v1.3 i18n）
{
  C.LANG.cur = "zh";
  eq("T20a 中文取值", C.t("menu.file"), "文件");
  eq("T20b 占位符替换", C.t("st.loaded", {n: 3}), "已加载 3 个文本文件，输入关键词开始搜索");
  eq("T20c 未知键回退键名", C.t("no.such.key"), "no.such.key");
  C.LANG.cur = "en";
  eq("T20d 英文取值", C.t("menu.file"), "File");
  eq("T20e 英文占位符替换", C.t("st.loaded", {n: 3}), "Loaded 3 text files — enter keywords to start searching");
  eq("T20f 英文下动态键", C.t("scope.both"), "Content + Name");
  C.LANG.cur = "zh";   // 还原，避免影响后续
}

// ---- T21 英文文案不为空且与中文不同（防复制粘贴漏改）
{
  const same = Object.keys(C.I18N.zh).filter(k => C.I18N.zh[k] === C.I18N.en[k]);
  // about.copy（署名）/ about.title（版本号）/ ex.fileH（Markdown 标题格式）/
  // langseg.tip（提示条本身双语）有意相同，其余必须不同
  const unexpected = same.filter(k => !["about.copy", "about.title", "ex.fileH",
                                        "langseg.tip"].includes(k));
  eq("T21 中英文案仅有署名/版本号相同", unexpected, []);
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败`);
process.exit(fail ? 1 : 0);
