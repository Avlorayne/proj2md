'use strict';
const D = require('./defaults.js');
const { t } = require('./i18n.js');
const CJK_RE = /[\u3000-\u9fff\uff00-\uffef]/g;
const _ASCII_MAP = {
  '═': '=', '─': '-', '├': '|', '└': '`', '│': '|', '▶': '>',
  '✔': '[OK]', '⚠': '[!]', '❌': '[X]', '★': '*', '…': '...', '·': '-',
  '（': '(', '）': ')', '「': '"', '」': '"',
};
function asciiFallback(s) {
  return s.replace(/[═─├└│▶✔⚠❌★…·（）「」]/g, (ch) => _ASCII_MAP[ch] || ch);
}
/** 安全打印：设置 PROJ2MD_ASCII=1 可强制降级为 ASCII（老终端兜底）。 */
function cprint(...args) {
  let s = args.map(String).join(' ');
  if (process.env.PROJ2MD_ASCII) s = asciiFallback(s);
  console.log(s);
}
function expandUser(p) {
  const s = String(p);
  if (s === '~') return require('os').homedir();
  if (s.startsWith('~/') || s.startsWith('~\\')) return require('path').join(require('os').homedir(), s.slice(2));
  return s;
}
function normalizeExt(e) { return String(e).trim().toLowerCase().replace(/^\.+/, ''); }
function fmtSize(n) {
  n = Number(n);
  const units = ['B', 'KB', 'MB', 'GB'];
  for (const u of units) {
    if (n < 1024 || u === 'GB') return (u === 'B' ? n.toFixed(0) : n.toFixed(1)) + ' ' + u;
    n /= 1024;
  }
}
function fmtInt(n) { return Number(n).toLocaleString('en-US'); }
/** 按 Unicode 码点计数，与 Python 的 len(str) 对齐（emoji 等增补平面字符按 1 计）。 */
function cpLen(s) {
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const hi = s.charCodeAt(i);
    if (hi >= 0xd800 && hi <= 0xdbff && i + 1 < s.length) {
      const lo = s.charCodeAt(i + 1);
      if (lo >= 0xdc00 && lo <= 0xdfff) i++;
    }
    n++;
  }
  return n;
}
/** 粗略估算 token：中文按 ~1.1 token/字，其他按 ~3.8 字符/token。 */
function estimateTokens(text) {
  const m = text.match(CJK_RE);
  const cjk = m ? m.length : 0;
  return Math.trunc(cjk * 1.1 + (cpLen(text) - cjk) / 3.8);
}
function tokenHint(tok) {
  if (tok < 30_000) return t('hint_moderate');
  if (tok < 100_000) return t('hint_long');
  if (tok < 200_000) return t('hint_very_long');
  return t('hint_too_long');
}
// ── 路径名小工具（输入为任意分隔符的路径字符串）──
function baseNameOf(p) {
  const s = String(p).replace(/[\\/]+$/, '');
  const i = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'));
  return i < 0 ? s : s.slice(i + 1);
}
function extOf(name) {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
}
function stemOf(name) {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(0, dot) : name;
}
function langOf(rel) {
  const nameL = baseNameOf(rel).toLowerCase();
  if (Object.prototype.hasOwnProperty.call(D.LANGUAGE_BY_NAME, nameL)) return D.LANGUAGE_BY_NAME[nameL];
  const ext = extOf(nameL);
  if (D.LANGUAGE_BY_EXT[ext]) return D.LANGUAGE_BY_EXT[ext];
  return ext ? ext.toUpperCase() : 'Text';
}
// ── Markdown 辅助 ──
function fenceFor(content) {
  let longest = 0, m;
  const re = /`+/g;
  while ((m = re.exec(content))) longest = Math.max(longest, m[0].length);
  return '`'.repeat(Math.max(3, longest + 1));
}
function fenceLangOf(rel) {
  const nameL = baseNameOf(rel).toLowerCase();
  if (Object.prototype.hasOwnProperty.call(D.FENCE_LANG_BY_NAME, nameL)) return D.FENCE_LANG_BY_NAME[nameL];
  const ext = extOf(nameL);
  return D.FENCE_LANG_BY_EXT[ext] !== undefined ? D.FENCE_LANG_BY_EXT[ext] : ext;
}
/** GitHub 风格标题锚点（保留中文/字母/数字/连字符，\w 的 Unicode 等价）。 */
function mdSlug(text) {
  return text.trim().toLowerCase()
    .replace(/[^\p{L}\p{N}_\- ]/gu, '')
    .replace(/ /g, '-');
}
function mdCodeSpan(s) { return s.includes('`') ? s : '`' + s + '`'; }
function mdTableCell(s) {
  if (s.includes('`')) return s.replace(/\|/g, '\\|').replace(/\[/g, '\\[').replace(/\]/g, '\\]');
  return '`' + s.replace(/\|/g, '\\|') + '`';
}
// ── fnmatch（Python 语义：* 可跨目录层级，大小写不敏感）──
const _reCache = new Map();
function _compileFnmatch(pat) {
  let out = '';
  for (let i = 0; i < pat.length; i++) {
    const c = pat[i];
    if (c === '*') out += '[\\s\\S]*';
    else if (c === '?') out += '[\\s\\S]';
    else if (c === '[') {
      let j = i + 1, neg = false;
      if (pat[j] === '!') { neg = true; j++; }
      if (pat[j] === ']') j++;
      let k = j;
      while (k < pat.length && pat[k] !== ']') k++;
      if (k >= pat.length) { out += '\\['; continue; }
      out += '[' + (neg ? '^' : '') + pat.slice(j, k).replace(/([\\\]])/g, '\\$1') + ']';
      i = k;
    } else {
      out += c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
  }
  return new RegExp('^' + out + '$');
}
function fnmatch(name, pat) {
  let re = _reCache.get(pat);
  if (!re) { re = _compileFnmatch(pat); _reCache.set(pat, re); }
  return re.test(name);
}
module.exports = {
  cprint, expandUser, normalizeExt, fmtSize, fmtInt, cpLen, estimateTokens, tokenHint,
  baseNameOf, extOf, stemOf, langOf,
  fenceFor, fenceLangOf, mdSlug, mdCodeSpan, mdTableCell, fnmatch,
};

