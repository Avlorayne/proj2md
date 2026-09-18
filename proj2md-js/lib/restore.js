'use strict';
// restore.js —— 反向还原（--restore，对齐 Python 版 v2.4.0）
//
// 把 proj2md 生成的 Markdown 合集（或 AI 遵循「### 序号. 相对路径 + 围栏代码块」
// 约定的回复）反向写回真实文件：
//   文件不存在        → 新建（自动创建父目录）
//   文件已存在且相同  → 跳过（未变更）
//   文件已存在且不同  → 覆盖更新（--backup 备份 / --diff 打印差异）
// 安全：拒绝绝对路径 / 盘符 / ..（写盘前二次校验）；生成时被截断的文件默认跳过。
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { t } = require('./i18n.js');
const { cprint, expandUser, fnmatch } = require('./util.js');
const { readText } = require('./reader.js'); // ★ 修复（P2）：编码探测读取（utf-8-sig→utf-8→gbk→big5→latin-1）
// 可选依赖：提供 GBK/Big5 等编码写回；未安装时非 UTF-8 一律回退 UTF-8
let iconv = null;
try { iconv = require('iconv-lite'); } catch (e) { /* optional */ }
const MAX_CLIP = 1 << 26; // 剪贴板 / 管道读取上限（64MB）
// ─────────────────────────── 解析用正则（与 Python 版一致） ───────────────────────────
const HEAD_RE = /^(#{2,4})\s+(?:(\d{1,4})\s*[.、)]\s*)?(.+?)\s*$/;
const FENCE_OPEN_RE = /^(`{3,})(\S*)/;
const FENCE_CLOSE_RE = /^(`{3,})\s*$/;
const ENC_RE = /(?:编码|encoding)\s*`([^`]+)`/i;
const TITLE_PREFIX_RE = /^(?:file|filename|filepath|path|文件|文件名|路径)\s*[:：]\s*/i;
const LN_STRICT_RE = /^ {0,5}\d{1,6} \|\s?/; // 与 --line-numbers 的前缀一致
const LN_NUM_RE = /^ {0,5}(\d{1,6}) \|/;
const LN_LOOSE_RE = /^\s*\d{1,6}\s*\|\s?/;
const TRUNC_ZH_RE = /^……（该文件共\s*\d+\s*行.*）\s*$/;
const TRUNC_EN_RE = /^\.{2,3}\(the file has\s*\d+\s*lines.*kept\)\s*$/i;
const APPENDIX_RE = /附录：未包含的文件|Appendix:\s*Files Not Included/i;
const SKIP_ITEM_RE = /^\s*[-*]\s+`?([^`（(]+)/;
const BAD_HEAD_RE = /目录结构|文件索引|源代码正文|给 ?AI|我的需求|附录[：:]|directory tree|file index|source code|reading notes|my request|appendix/i;
const NONPATH_RE = /^[*_>#\-|[(`【（]/;
// 无扩展名但可作为路径的文件名 / Windows 保留设备名
const KNOWN_NAMES = new Set([
  'makefile', 'dockerfile', 'rakefile', 'gemfile', 'procfile', 'brewfile',
  'justfile', 'vagrantfile', 'license', 'licence', 'notice',
  '.gitignore', '.gitattributes', '.dockerignore', '.editorconfig',
  '.npmrc', '.nvmrc', '.python-version', '.env.example', '.env.sample',
]);
const WIN_RESERVED = new Set([
  'con', 'prn', 'aux', 'nul',
  'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
  'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
]);
class Entry {
  constructor(pathText, rel, content, lang, encoding, truncated) {
    this.pathText = pathText; // 标题里写的原始路径
    this.rel = rel;           // 清洗后的安全相对路径（posix 风格）；null = 已拒绝
    this.content = content;
    this.lang = lang || '';
    this.encoding = encoding || null;
    this.truncated = truncated;
  }
}
// ─────────────────────────── 小工具 ───────────────────────────
function isFile(p) { try { return fs.statSync(p).isFile(); } catch (e) { return false; } }
function isDir(p) { try { return fs.statSync(p).isDirectory(); } catch (e) { return false; } }
/** 真实路径；目标尚不存在时向上找最深的已存在祖先再拼回尾部（近似 Path.resolve(strict=False)）。 */
function realish(p) {
  const abs = path.resolve(p);
  try {
    return fs.realpathSync(abs);
  } catch (e) {
    const tail = [];
    let cur = abs;
    for (;;) {
      const parent = path.dirname(cur);
      if (parent === cur) return path.join(cur, ...tail.reverse());
      tail.push(path.basename(cur));
      cur = parent;
      try {
        return path.join(fs.realpathSync(cur), ...tail.reverse());
      } catch (e2) { /* 继续向上 */ }
    }
  }
}
/** 解析后的目标是否逃出目标目录（跨盘符 / 上级目录）。rel 为空表示同一路径。 */
function escapesRoot(rootRes, targetRes) {
  const rel = path.relative(rootRes, targetRes);
  if (!rel) return false;
  if (path.isAbsolute(rel)) return true;
  return rel === '..' || rel.startsWith('..' + path.sep);
}
// ─────────────────────────── 标题 / 正文清洗 ───────────────────────────
/** 拒绝绝对路径 / 盘符 / .. / Windows 保留名；返回清洗后的 posix 相对路径或 null。 */
function safeRel(pathText) {
  const name = String(pathText).replace(/\\/g, '/').trim();
  // 显式拒绝 Unix 绝对路径：原先先 strip 首尾 / 再 split，
  // 会把 "/etc/x" 相对化为 "etc/x"，护栏形同虚设（与「路径不安全」文案矛盾）。
  if (name.startsWith('/')) return null;
  const stripped = name.replace(/^\/+|\/+$/g, '');
  const segs = stripped.split('/').filter((s) => s !== '' && s !== '.');
  if (!segs.length) return null;
  if (/^[A-Za-z]:/.test(segs[0])) return null; // 盘符 / 盘符相对路径（C:、C:x）
  if (segs.some((s) => s === '..')) return null;
  for (const seg of segs) {
    if (seg.length > 255) return null;
    if (WIN_RESERVED.has(seg.split('.')[0].trim().toLowerCase())) return null;
  }
  return segs.join('/');
}
/** 清洗标题：去掉 '文件：' 前缀、包裹反引号、尾部的 ':42' 行引用。 */
function cleanTitle(raw) {
  let s = String(raw).trim();
  s = s.replace(TITLE_PREFIX_RE, '').trim();
  s = s.replace(/[:：]\d{1,6}$/, '').trim();
  return s.replace(/^`+/, '').replace(/`+$/, '').trim();
}
/** 判断标题是否像文件路径（过滤章节标题、元信息等干扰项）。 */
function looksLikePath(title) {
  const s = title.trim();
  if (!s || s.length > 200 || s.endsWith('/')) return false;
  if (BAD_HEAD_RE.test(s) || NONPATH_RE.test(s)) return false;
  const last = s.slice(s.lastIndexOf('/') + 1);
  if (last.includes('.') || KNOWN_NAMES.has(last.toLowerCase())) return true;
  return s.includes('/') && !s.includes(' ');
}
/** 剥离 --line-numbers 生成的前缀（如 '   12 | '）。返回 [content, stripped]。
 *  auto: 所有非空行都带严格前缀且行号连续 1..n 才剥离（几乎零误伤）；on: 逐行宽松剥离；off: 原样。 */
function stripLineNumbers(content, mode) {
  if (mode === 'off' || !content.trim()) return [content, false];
  const lines = content.split('\n');
  const body = lines.filter((l) => l.trim());
  if (!body.length) return [content, false];
  if (mode === 'auto') {
    if (!body.every((l) => LN_STRICT_RE.test(l))) return [content, false];
    const nums = body.map((l) => Number(LN_NUM_RE.exec(l)[1]));
    for (let k = 0; k < nums.length; k++) {
      if (nums[k] !== k + 1) return [content, false];
    }
    return [lines.map((l) => l.replace(LN_STRICT_RE, '')).join('\n'), true];
  }
  const out = lines.map((l) => (LN_LOOSE_RE.test(l) ? l.replace(LN_LOOSE_RE, '') : l));
  return [out.join('\n'), true];
}
/** 识别 proj2md 的截断提示行（严格 + 宽松两种）。 */
function isTruncNote(line) {
  if (TRUNC_ZH_RE.test(line) || TRUNC_EN_RE.test(line)) return true;
  if (line.includes('该文件共') && (line.includes('保留前') || line.includes('超过'))) return true;
  const low = line.toLowerCase();
  if (low.includes('lines in total') && (low.includes('kept') || low.includes('beyond') || low.includes('first'))) return true;
  return false;
}
// ─────────────────────────── 解析合集 ───────────────────────────
/** 把 Markdown 合集解析为条目列表。返回 [entries, missing, warns]。
 *  解析以标题为驱动：只有「路径样标题 + 紧随的围栏代码块」才会成为条目，
 *  目录树 / 索引表 / 附录说明等其余内容自动忽略。 */
function parseBundle(text, stripMode) {
  let lines = text.split('\n');
  // 容错：脱掉 AI 常见的最外层 ```markdown 包装围栏（只处理带 markdown/md 标识的）
  const idx = [];
  for (let k = 0; k < lines.length; k++) if (lines[k].trim()) idx.push(k);
  if (idx.length) {
    const fm = FENCE_OPEN_RE.exec(lines[idx[0]].trim());
    const cm = FENCE_CLOSE_RE.exec(lines[idx[idx.length - 1]].trim());
    if (fm && cm && cm[1].length >= fm[1].length && ['markdown', 'md'].includes((fm[2] || '').toLowerCase())) {
      lines = lines.slice(idx[0] + 1, idx[idx.length - 1]);
    }
  }
  const entries = [], missing = [], warns = [];
  const n = lines.length;
  let i = 0;
  while (i < n) {
    const line = lines[i];
    const hm = HEAD_RE.exec(line);
    const title = hm ? cleanTitle(hm[3]) : '';
    let handled = false;
    if (hm && looksLikePath(title)) {
      // 标题之后允许夹空白 / **元信息** 行，寻找围栏开始；
      // 首个其他内容行说明标题后没有紧跟代码块（与 Python 版一致：直接 break）
      let meta = '', j = i + 1, opened = null;
      while (j < n && j - i <= 8) {
        const st = lines[j].trim();
        if (!st) { j++; continue; }
        if (st.startsWith('**')) { meta = st; j++; continue; }
        const fm = FENCE_OPEN_RE.exec(st);
        if (fm) opened = [j, fm[1].length, (fm[2] || '').trim()];
        break;
      }
      if (opened) {
        const ticks = opened[1], lang = opened[2];
        const body = [];
        let k = opened[0] + 1, closed = false;
        while (k < n) {
          const cm = FENCE_CLOSE_RE.exec(lines[k].trim());
          if (cm && cm[1].length >= ticks) { closed = true; break; } // 兼容 render 的变长围栏
          body.push(lines[k]);
          k++;
        }
        if (closed) {
          let content = stripLineNumbers(body.join('\n'), stripMode)[0];
          // 识别并剥离截断提示行（可能仍带行号前缀）
          const ls = content.split('\n');
          while (ls.length && !ls[ls.length - 1].trim()) ls.pop();
          let truncated = false;
          if (ls.length) {
            let last = ls[ls.length - 1];
            if (LN_LOOSE_RE.test(last)) last = last.replace(LN_LOOSE_RE, '');
            if (isTruncNote(last)) { ls.pop(); truncated = true; }
          }
          content = ls.join('\n');
          if (content && !content.endsWith('\n')) content += '\n';
          if (content.trim() === '（空文件）' || content.trim() === '(empty file)') content = '';
          const em = ENC_RE.exec(meta);
          const rel = safeRel(title);
          if (rel === null) warns.push(t('warn_unsafe_path', { path: title }));
          entries.push(new Entry(title, rel, content, lang, em ? em[1] : null, truncated));
          i = k + 1;
          handled = true;
        } else {
          warns.push(t('warn_unclosed', { path: title }));
          i = k; // k === n，外层循环随之结束
          handled = true;
        }
      }
    }
    if (handled) continue;
    // 附录「未包含的文件」：收集清单，仅作提示（本就不在合集里，无法还原）
    if (APPENDIX_RE.test(line)) {
      let j = i + 1;
      while (j < n && !lines[j].trimStart().startsWith('#')) {
        const sm = SKIP_ITEM_RE.exec(lines[j]);
        if (sm) {
          const pathTxt = sm[1].trim();
          if (!pathTxt.startsWith('…') && !pathTxt.startsWith('...')) missing.push(pathTxt);
        }
        j++;
      }
      i = j;
      continue;
    }
    i++;
  }
  // 同路径去重：后出现的通常是更新版本；若旧的未截断而新的被截断则保留旧的
  const seen = new Map();
  const finalEntries = [];
  for (const e of entries) {
    if (e.rel === null) { finalEntries.push(e); continue; }
    const key = e.rel.toLowerCase();
    if (seen.has(key)) {
      const pos = seen.get(key);
      const old = finalEntries[pos];
      warns.push(t('warn_dup_path', { path: e.rel }));
      if (old.truncated && !e.truncated) finalEntries[pos] = e;
    } else {
      seen.set(key, finalEntries.length);
      finalEntries.push(e);
    }
  }
  return [finalEntries, missing, warns];
}
// ─────────────────────────── unified diff（LCS 最小实现） ───────────────────────────
function diffOps(a, b) {
  // 去掉首尾公共行，缩小 DP 规模
  const n0 = a.length, m0 = b.length;
  let pre = 0;
  while (pre < n0 && pre < m0 && a[pre] === b[pre]) pre++;
  let suf = 0;
  while (suf < n0 - pre && suf < m0 - pre && a[n0 - 1 - suf] === b[m0 - 1 - suf]) suf++;
  const ops = [];
  for (let k = 0; k < pre; k++) ops.push({ t: '=', s: a[k], ai: k, bi: k });
  const A = a.slice(pre, n0 - suf), B = b.slice(pre, m0 - suf);
  const n = A.length, m = B.length;
  if (n && m && n * m <= 4_000_000) {
    const dp = new Array(n + 1);
    for (let r = 0; r <= n; r++) dp[r] = new Uint32Array(m + 1);
    for (let r = n - 1; r >= 0; r--) {
      const rn = dp[r + 1], row = dp[r];
      for (let c = m - 1; c >= 0; c--) {
        row[c] = A[r] === B[c] ? rn[c + 1] + 1 : (rn[c] >= row[c + 1] ? rn[c] : row[c + 1]);
      }
    }
    let r = 0, c = 0;
    while (r < n && c < m) {
      if (A[r] === B[c]) { ops.push({ t: '=', s: A[r], ai: pre + r, bi: pre + c }); r++; c++; }
      else if (dp[r + 1][c] >= dp[r][c + 1]) { ops.push({ t: '-', s: A[r], ai: pre + r, bi: pre + c }); r++; }
      else { ops.push({ t: '+', s: B[c], ai: pre + r, bi: pre + c }); c++; }
    }
    while (r < n) { ops.push({ t: '-', s: A[r], ai: pre + r, bi: pre + c }); r++; }
    while (c < m) { ops.push({ t: '+', s: B[c], ai: pre + r, bi: pre + c }); c++; }
  } else if (n || m) {
    // 过大文件兜底：整体视为先删后增（不做逐行对齐）
    for (let r = 0; r < n; r++) ops.push({ t: '-', s: A[r], ai: pre + r, bi: pre });
    for (let c = 0; c < m; c++) ops.push({ t: '+', s: B[c], ai: pre + n, bi: pre + c });
  }
  for (let k = 0; k < suf; k++) {
    const ai = n0 - suf + k, bi = m0 - suf + k;
    ops.push({ t: '=', s: a[ai], ai, bi });
  }
  return ops;
}
function unifiedDiff(oldText, newText, fromFile, toFile) {
  const a = oldText.split('\n');
  const b = newText.split('\n');
  if (a.length && a[a.length - 1] === '') a.pop();
  if (b.length && b[b.length - 1] === '') b.pop();
  const ops = diffOps(a, b);
  const out = ['--- ' + fromFile, '+++ ' + toFile];
  const C = 3;
  const nOps = ops.length;
  let i = 0;
  while (i < nOps) {
    if (ops[i].t === '=') { i++; continue; }
    // 找到与本次变更相连（间隔 ≤ 2C 行公共行）的最后一处变更 → 合并为同一 hunk
    let last = i, j = i;
    while (j < nOps) {
      if (ops[j].t !== '=') { last = j; j++; continue; }
      let k = j;
      while (k < nOps && ops[k].t === '=') k++;
      if (k < nOps && k - j <= 2 * C) { j = k; continue; }
      break;
    }
    // 向两侧扩 C 行上下文
    let start = i, back = 0;
    while (start > 0 && ops[start - 1].t === '=' && back < C) { start--; back++; }
    let end = last, fwd = 0;
    while (end + 1 < nOps && ops[end + 1].t === '=' && fwd < C) { end++; fwd++; }
    let aCount = 0, bCount = 0, aFirst = -1, bFirst = -1;
    for (let k = start; k <= end; k++) {
      if (ops[k].t !== '+') { if (aFirst < 0) aFirst = ops[k].ai; aCount++; }
      if (ops[k].t !== '-') { if (bFirst < 0) bFirst = ops[k].bi; bCount++; }
    }
    // 纯插入/纯删除时按 difflib 惯例输出「前一行号,0」
    const aHead = aCount ? (aFirst + 1) + ',' + aCount : ops[start].ai + ',0';
    const bHead = bCount ? (bFirst + 1) + ',' + bCount : ops[start].bi + ',0';
    out.push('@@ -' + aHead + ' +' + bHead + ' @@');
    for (let k = start; k <= end; k++) out.push((ops[k].t === '=' ? ' ' : ops[k].t) + ops[k].s);
    i = last + 1;
  }
  return out.join('\n');
}
function printDiff(rel, oldText, newText, limit) {
  const lines = unifiedDiff(oldText, newText, 'a/' + rel, 'b/' + rel).split('\n');
  // 不再用 limit > 0 守卫：与 Python 版一致，--max-diff 0 应输出 0 行 diff + "and N more"
  let out = lines;
  if (lines.length > limit) {
    out = lines.slice(0, limit);
    out.push(t('more_items', { n: lines.length - limit }).trim());
  }
  process.stdout.write(out.join('\n') + '\n');
}
// ─────────────────────────── 剪贴板读取 ───────────────────────────
/** 读取系统剪贴板文本；按平台原生命令回退，无需第三方依赖。失败返回 null。 */
function readClipboard() {
  try {
    if (process.platform === 'win32') {
      const ps = '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw';
      const r = spawnSync('powershell', ['-NoProfile', '-Command', ps], { encoding: 'utf8', timeout: 30000, maxBuffer: MAX_CLIP });
      if (!r.error && r.status === 0 && r.stdout) return String(r.stdout).replace(/^\uFEFF/, '');
    } else if (process.platform === 'darwin') {
      const r = spawnSync('pbpaste', { encoding: 'utf8', timeout: 30000, maxBuffer: MAX_CLIP });
      if (!r.error && r.status === 0 && r.stdout) return String(r.stdout).replace(/^\uFEFF/, '');
    } else {
      for (const cmd of [['wl-paste'], ['xclip', '-selection', 'clipboard', '-o'], ['xsel', '--clipboard', '--output']]) {
        try {
          const r = spawnSync(cmd[0], cmd.slice(1), { encoding: 'utf8', timeout: 30000, maxBuffer: MAX_CLIP });
          if (!r.error && r.status === 0 && r.stdout) return String(r.stdout).replace(/^\uFEFF/, '');
        } catch (e) { /* try next */ }
      }
    }
  } catch (e) { /* ignore */ }
  return null;
}
/**
 * 从 stdin 聚合 UTF-8 文本。
 * Windows 上 fs.readFileSync(0) 遇到管道会抛 EAGAIN（Node issue #20167），
 * 因此必须用异步事件聚合；上限与剪贴板一致，防内存放大。
 */
function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    process.stdin.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_CLIP) {
        reject(new Error('stdin exceeds ' + MAX_CLIP + ' bytes'));
        process.stdin.destroy();
        return;
      }
      chunks.push(chunk);
    });
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    process.stdin.on('error', reject);
  });
}
// ─────────────────────────── 写盘 ───────────────────────────
/** 按编码写文件；返回 false 表示需要回退 UTF-8（对应 Python 的 UnicodeEncodeError/LookupError）。 */
function writeWithEncoding(target, text, enc) {
  if (!enc || /^utf-?8$/i.test(enc)) {
    fs.writeFileSync(target, text, 'utf8');
    return true;
  }
  if (/^utf-?8-sig$/i.test(enc)) {
    fs.writeFileSync(target, '\uFEFF' + text, 'utf8');
    return true;
  }
  if (iconv && iconv.encodingExists(enc)) {
    const buf = iconv.encode(text, enc);
    // round-trip 校验：存在无法映射的字符时回退 UTF-8
    if (iconv.decode(buf, enc) === text) {
      fs.writeFileSync(target, buf);
      return true;
    }
  }
  return false;
}
function applyEntries(entries, root, opts, bundlePath) {
  const created = [], updated = [], unchanged = [], skipped = [], failed = [];
  const rootRes = realish(root);
  const include = (opts.includePatterns || []).map((p) => String(p).toLowerCase());
  const exclude = (opts.excludePatterns || []).map((p) => String(p).toLowerCase());
  for (const e of entries) {
    const relPosix = e.rel !== null ? e.rel : e.pathText;
    if (e.rel === null) { failed.push([relPosix, t('reason_unsafe')]); continue; }
    if (include.length && !include.some((p) => fnmatch(relPosix.toLowerCase(), p))) {
      skipped.push([relPosix, t('reason_only')]); continue;
    }
    if (exclude.length && exclude.some((p) => fnmatch(relPosix.toLowerCase(), p))) {
      skipped.push([relPosix, t('reason_excluded')]); continue;
    }
    if (e.truncated && !opts.allowTruncated) {
      skipped.push([relPosix, t('reason_truncated')]); continue;
    }
    const target = path.join(root, e.rel);
    const targetRes = realish(target);
    // 双保险：解析后必须仍在 root 内
    if (escapesRoot(rootRes, targetRes)) { failed.push([relPosix, t('reason_escape')]); continue; }
    if (bundlePath && targetRes === bundlePath) { skipped.push([relPosix, t('reason_self')]); continue; }
    if (isDir(targetRes)) { failed.push([relPosix, t('reason_isdir')]); continue; }
    let text = e.content;
    if (text && !text.endsWith('\n')) text += '\n';
    const exists = fs.existsSync(target);
    if (exists) {
      let old;
      try {
        old = fs.readFileSync(target, 'utf8').replace(/\r\n/g, '\n');
      } catch (err) {
        failed.push([relPosix, t('reason_read_old', { err: err.message })]); continue;
      }
      if (old === text) { unchanged.push(relPosix); continue; }
      if (opts.skipExisting) { skipped.push([relPosix, t('reason_skip_existing')]); continue; }
      if (opts.diff) printDiff(relPosix, old, text, opts.maxDiff);
    }
    if (opts.dryRun) { (exists ? updated : created).push(relPosix); continue; }
    if (exists && opts.backup) {
      const d = new Date();
      const p2 = (x) => String(x).padStart(2, '0');
      const stamp = '' + d.getFullYear() + p2(d.getMonth() + 1) + p2(d.getDate()) + '-' +
        p2(d.getHours()) + p2(d.getMinutes()) + p2(d.getSeconds());
      const dir = path.dirname(target), name = path.basename(target);
      let bak = path.join(dir, name + '.bak-' + stamp);
      let k = 1;
      while (fs.existsSync(bak)) {
        bak = path.join(dir, name + '.bak-' + stamp + '-' + k);
        k++;
      }
      try {
        fs.renameSync(target, bak);
      } catch (err) {
        failed.push([relPosix, t('reason_backup', { err: err.message })]); continue;
      }
    }
    const enc = opts.keepEncoding && e.encoding ? e.encoding : 'utf-8';
    try {
      fs.mkdirSync(path.dirname(target), { recursive: true });
      if (!writeWithEncoding(target, text, enc)) {
        cprint(t('warn_enc_fallback', { path: relPosix, enc }));
        fs.writeFileSync(target, text, 'utf8');
      }
    } catch (err) {
      failed.push([relPosix, t('reason_write', { err: err.message })]); continue;
    }
    (exists ? updated : created).push(relPosix);
  }
  return { created, updated, unchanged, skipped, failed };
}
// ─────────────────────────── 主流程 ───────────────────────────
async function runRestore(args) {
  // ── 1. 读入 Markdown 文本（文件 / stdin / 剪贴板）──
  let bundlePath = null;
  let text;
  const first = args._[0];
  if (args.clip) {
    text = readClipboard();
    if (text === null || text === undefined) { cprint(t('err_restore_clip')); return 1; }
  } else if (first === '-' || first === undefined) {
    if (first === undefined) { cprint(t('err_restore_need_bundle')); return 2; }
    try {
      text = await readStdin(); // 标准输入（异步聚合，见 readStdin 注释）
    } catch (e) {
      cprint(t('err_restore_need_bundle'));
      return 1;
    }
  } else {
    const bp = expandUser(first);
    if (!isFile(bp)) { cprint(t('err_restore_bundle', { path: bp })); return 1; }
    bundlePath = realish(bp);
    // ★ 修复（P2）：按编码链读取合集。此前固定 utf-8，Windows PowerShell 5.1
    //   「Out-File」类工具写出的 UTF-16 文件会整篇乱码、解析出 0 条目。
    const r = readText(bp);
    if (r.text === null) {
      // readText 的二进制嗅探（NUL 检查）会把 UTF-16 误判为二进制；
      // 带 BOM 的 UTF-16 LE 正是 Out-File 的默认格式，此处按 BOM 再试一次。
      let utf16 = null;
      try {
        const raw = fs.readFileSync(bp);
        if (raw[0] === 0xff && raw[1] === 0xfe) {
          utf16 = raw.toString('utf16le').replace(/^\uFEFF/, '');
        }
      } catch (e) { /* 走统一的读取失败报错 */ }
      if (utf16 === null) {
        cprint(t('err_restore_read', { err: r.err || 'unknown' })); // 文案键已在 i18n.js 中加入
        return 1;
      }
      text = utf16;
    } else {
      text = r.text;
    }
  }
  text = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  // ── 2. 解析 ──
  const parsed = parseBundle(text, args.strip_linenum || 'auto');
  const entries = parsed[0], missing = parsed[1], warns = parsed[2];
  const real = entries.filter((e) => e.rel !== null);
  // 先报警告再判断「无可用条目」：合集里全是非法路径时，
  // 用户需要看到「路径不安全」的原因，而不是笼统的「未解析到条目」。
  for (const w of warns) {
    if (args.json) process.stderr.write(w + '\n');
    else cprint(w);
  }
  if (!real.length) { cprint(t('err_restore_no_entries')); return 1; }
  // ── 3. JSON / 清单模式 ──
  if (args.json) {
    const payload = entries.map((e) => ({
      path: e.rel !== null ? e.rel : e.pathText,
      safe: e.rel !== null,
      language: e.lang,
      encoding: e.encoding,
      truncated: e.truncated,
      lines: e.content.split('\n').length - 1,
      content: e.content,
    }));
    process.stdout.write(JSON.stringify(payload, null, 2) + '\n');
    return 0;
  }
  if (args.list) {
    cprint(t('list_title', { n: real.length }));
    real.forEach((e, idx) => {
      const flag = e.truncated ? t('flag_trunc') : '';
      cprint(t('list_item', {
        i: String(idx + 1).padStart(4),
        path: e.rel,
        lang: e.lang || '-',
        n: e.content.split('\n').length - 1,
        flag,
      }));
    });
    if (missing.length) {
      cprint();
      cprint(t('info_missing_files', { n: missing.length }));
      missing.slice(0, 20).forEach((m) => cprint(t('info_missing_item', { path: m })));
    }
    return 0;
  }
  // ── 4. 写盘 ──
  const targetArg = args._[1];
  if (targetArg === '-') { cprint(t('err_restore_bad_target')); return 2; }
  const root = path.resolve(expandUser(targetArg || '.'));
  if (!fs.existsSync(root)) {
    if (args.dry_run) {
      cprint(t('info_dry_root', { root }));
    } else {
      try {
        fs.mkdirSync(root, { recursive: true });
      } catch (err) {
        cprint(t('err_restore_mkdir', { err: err.message }));
        return 1;
      }
    }
  }
  const opts = {
    includePatterns: args.include_pattern || [],
    excludePatterns: args.exclude_pattern || [],
    dryRun: Boolean(args.dry_run),
    diff: Boolean(args.diff),
    maxDiff: args.max_diff !== undefined ? args.max_diff : 120,
    backup: Boolean(args.backup),
    skipExisting: Boolean(args.skip_existing),
    allowTruncated: Boolean(args.allow_truncated),
    keepEncoding: Boolean(args.keep_encoding),
  };
  const res = applyEntries(entries, root, opts, bundlePath);
  // ── 5. 报告 ──
  cprint();
  let head = t('sum_restore', {
    c: res.created.length, u: res.updated.length, s: res.unchanged.length,
    k: res.skipped.length, f: res.failed.length,
  });
  if (args.dry_run) head += t('sum_restore_dry');
  cprint(head);
  if (!args.quiet) {
    const showAll = (arr, fmt) => {
      arr.slice(0, 50).forEach(fmt);
      if (arr.length > 50) cprint(t('more_items', { n: arr.length - 50 }));
    };
    const showSome = (arr, fmt) => {
      arr.slice(0, 30).forEach(fmt);
      if (arr.length > 30) cprint(t('more_items', { n: arr.length - 30 }));
    };
    showAll(res.created, (p) => cprint(t('item_created', { path: p })));
    showAll(res.updated, (p) => cprint(t('item_updated', { path: p })));
    showSome(res.skipped, (it) => cprint(t('item_skipped', { path: it[0], reason: it[1] })));
    showSome(res.failed, (it) => cprint(t('item_failed', { path: it[0], reason: it[1] })));
  }
  if (missing.length) {
    cprint();
    cprint(t('info_missing_files', { n: missing.length }));
    missing.slice(0, 20).forEach((m) => cprint(t('info_missing_item', { path: m })));
  }
  return res.failed.length ? 1 : 0;
}
// 内部函数一并导出，供测试直接做离线校验
module.exports = { runRestore, parseBundle, safeRel, readClipboard, readStdin };
