'use strict';
const D = require('./defaults.js');
const { t } = require('./i18n.js');
const {
  estimateTokens, fmtSize, fmtInt,
  fenceFor, fenceLangOf, mdSlug, mdCodeSpan, mdTableCell,
} = require('./util.js');
const MARK = D.MARK;
const MARK_SEARCH_RE = /\x00(\d+)\x00/;
const MARK_STRIP_RE = /\x00\d+\x00/g;
function localNow() {
  const d = new Date();
  const p = (x) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function replaceOnce(hay, needle, replFn) {
  const idx = hay.indexOf(needle);
  if (idx < 0) return hay;
  return hay.slice(0, idx) + replFn() + hay.slice(idx + needle.length);
}
function buildTree(records, rootLabel) {
  const tree = {};
  for (const r of records) {
    let node = tree;
    const parts = r.rel.split('/');
    for (let i = 0; i < parts.length - 1; i++) {
      if (!node[parts[i]] || typeof node[parts[i]] !== 'object') node[parts[i]] = {};
      node = node[parts[i]];
    }
    node[parts[parts.length - 1]] = null;
  }
  const lines = [rootLabel + '/'];
  const walk = (node, prefix) => {
    const items = Object.entries(node).sort((a, b) => {
      const fa = a[1] === null ? 1 : 0, fb = b[1] === null ? 1 : 0; // 目录在前，文件在后
      if (fa !== fb) return fa - fb;
      const la = a[0].toLowerCase(), lb = b[0].toLowerCase();
      return la < lb ? -1 : la > lb ? 1 : 0;
    });
    items.forEach(([name, child], i) => {
      const last = i === items.length - 1;
      lines.push(prefix + (last ? '└── ' : '├── ') + name + (child ? '/' : ''));
      if (child) walk(child, prefix + (last ? '    ' : '│   '));
    });
  };
  walk(tree, '');
  return lines.join('\n') + '\n';
}
function render(cfg, records, skipped, promptText, rootName, partLabel = '', prunedHidden = null) {
  const n = records.length;
  const totLines = records.reduce((s, r) => s + r.lines, 0);
  const totSize = records.reduce((s, r) => s + Buffer.byteLength(r.content, 'utf8'), 0); // ★ 修复（P0-1）：字节口径（原为字符数，与控制台报告不一致）
  const totTokens = records.reduce((s, r) => s + estimateTokens(r.content), 0);
  const now = localNow();
  prunedHidden = prunedHidden || [];
  // ── 头部各节：标题/说明/需求/目录树 ──
  const head = [];
  const meta = [
    '- ' + t('doc_meta_time', { now }),
    '- ' + t('doc_meta_project', { root: rootName }),
    '- ' + (skipped.length
      ? t('doc_meta_files_skipped', { n, skipped: skipped.length })
      : t('doc_meta_files', { n })),
    '- ' + t('doc_meta_lines', { lines: fmtInt(totLines) }),
    '- ' + t('doc_meta_size', { size: fmtSize(totSize) }), // ★
    '- ' + t('doc_meta_tokens', { tokens: fmtInt(totTokens) }),
  ];
  head.push(t('doc_title', { root: rootName, label: partLabel }) + '\n\n' + meta.join('\n'));
  if (cfg.aiHeader) head.push(t('doc_ai_header') + t('ai_notes', { root: rootName }));
  if (promptText) head.push(t('doc_prompt') + promptText);
  if (cfg.showTree) {
    const tree = buildTree(records, rootName).replace(/\n$/, '');
    const tf = fenceFor(tree);
    head.push(t('doc_tree') + tf + '\n' + tree + '\n' + tf);
  }
  // ── 文件正文节 ──
  const fileSecs = [];
  records.forEach((r, idx) => {
    const i = idx + 1;
    let content = r.content;
    if (cfg.lineNumbers) {
      const ls = content.split('\n');
      if (ls.length && ls[ls.length - 1] === '') ls.pop();
      content = ls.map((ln, k) => String(k + 1).padStart(5) + ' | ' + ln).join('\n') + '\n';
    }
    const f = fenceFor(content);
    const info = ['`' + r.language + '`', t('doc_lines_unit', { n: r.lines })];
    if (r.encoding && !r.encoding.startsWith('utf')) info.push(t('doc_encoding', { enc: r.encoding }));
    if (r.truncated) info.push(t('doc_truncated'));
    // 围栏行末尾加内部标记，稍后用于回填索引中的起始行号
    const fenceLine = f + fenceLangOf(r.rel) + MARK + i + MARK;
    fileSecs.push(
      '### ' + i + '. ' + r.rel + '\n\n' +
      '**' + i + '/' + n + '** · ' + info.join(' · ') + '\n\n' +
      fenceLine + '\n' + content + f
    );
  });
  // ── 索引表（起始行先占位，组装后按标记回填真实行号）──
  const makeIndex = (starts) => {
    const rows = [t('doc_index_cols'), '|---:|:---|:---|---:|---:|'];
    records.forEach((r, idx) => {
      const i = idx + 1;
      const cell = mdTableCell(r.rel);
      const anchor = mdSlug(i + '. ' + r.rel);
      rows.push('| ' + i + ' | [' + cell + '](#' + anchor + ') | ' + r.language + ' | ' + r.lines + ' | ' + starts[idx] + ' |');
    });
    return t('doc_index') + rows.join('\n');
  };
  // ── 尾部各节 ──
  const tail = [];
  if (fileSecs.length) tail.push(t('doc_source') + fileSecs.join('\n\n'));
  if (skipped.length) {
    const items = skipped.slice(0, 50).map(([rel, reason]) => t('doc_skip_item', { path: mdCodeSpan(rel), reason }));
    if (skipped.length > 50) items.push(t('doc_more_skipped', { n: skipped.length - 50 }));
    tail.push(t('doc_appendix_skipped') + items.join('\n'));
  }
  if (prunedHidden.length) {
    const items = prunedHidden.slice(0, 30).map((d) => t('doc_hidden_item', { path: mdCodeSpan(d) }));
    if (prunedHidden.length > 30) items.push(t('doc_more_hidden', { n: prunedHidden.length - 30 }));
    tail.push(t('doc_appendix_hidden') + items.join('\n'));
  }
  tail.push(t('doc_end', {
    n, lines: fmtInt(totLines), tokens: fmtInt(totTokens),
    tool: D.TOOL, ver: D.VERSION, now,
  }));
  const dummyIndex = (cfg.showIndex && n) ? makeIndex(records.map(() => 0)) : null;
  const secs = head.concat(dummyIndex ? [dummyIndex] : [], tail);
  let doc = secs.join('\n\n') + '\n';
  // ── 回填真实起始行号，并整体移除内部标记 ──
  if (dummyIndex) {
    const starts = new Array(n).fill(0);
    const lines = doc.split('\n');
    for (let li = 0; li < lines.length; li++) {
      const m = MARK_SEARCH_RE.exec(lines[li]);
      if (m) starts[Number(m[1]) - 1] = li + 2; // 围栏行的下一行即正文首行
    }
    doc = doc.replace(MARK_STRIP_RE, '');
    if (starts.every((s) => s > 0)) {
      doc = replaceOnce(doc, dummyIndex, () => makeIndex(starts));
    }
  }
  return doc;
}
module.exports = { buildTree, render };

