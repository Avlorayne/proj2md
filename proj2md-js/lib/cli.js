'use strict';
const fs = require('fs');
const path = require('path');
const D = require('./defaults.js');
const { t, setLang } = require('./i18n.js');
const {
  cprint, expandUser, estimateTokens, cpLen, fmtSize, fmtInt, tokenHint,
  baseNameOf, stemOf, extOf,
} = require('./util.js');
const { discover } = require('./discover.js');
const { readText } = require('./reader.js');
const { buildTree, render } = require('./render.js');
const { copyClipboard } = require('./clipboard.js');
const { buildConfig } = require('./config.js');
const { fetchRemoteRepo, removeTree } = require('./remote.js');
class UsageError extends Error {}
// ─────────────────────────── 参数解析 ───────────────────────────
const BOOL_FLAGS = new Set([
  'any_text', 'include_hidden', 'line_numbers', 'no_tree', 'no_index', 'no_ai_header',
  'no_smart_order', 'clip', 'stdout', 'dry_run', 'no_config', 'init_config', 'quiet', 'version', 'help',
]);
const GREEDY_OPTS = new Set(['ext', 'only_ext', 'exclude_dir', 'exclude_file', 'exclude_pattern', 'include_pattern']);
const VALUE_OPTS = new Set(['output', 'repo', 'ref', 'lang', 'max_file_lines', 'max_file_kb', 'max_total_kb', 'split_tokens', 'prompt', 'prompt_file', 'config']);
const SHORT_MAP = { '-h': 'help', '-o': 'output' };
const USAGE_PARTS = [
  '[-h]', '[--repo URL]', '[--ref REF]', '[-o OUTPUT]', '[--ext EXT [EXT ...]]', '[--only-ext EXT [EXT ...]]',
  '[--any-text]', '[--include-hidden]', '[--exclude-dir DIR [DIR ...]]',
  '[--exclude-file NAME [NAME ...]]', '[--exclude-pattern PAT [PAT ...]]',
  '[--include-pattern PAT [PAT ...]]', '[--lang {auto,zh,en}]', '[--line-numbers]',
  '[--max-file-lines N]', '[--max-file-kb KB]', '[--max-total-kb KB]', '[--split-tokens N]',
  '[--no-tree]', '[--no-index]', '[--no-ai-header]', '[--no-smart-order]',
  '[--prompt PROMPT]', '[--prompt-file FILE]', '[--clip]', '[--stdout]', '[--dry-run]',
  '[--config PATH]', '[--no-config]', '[--init-config]', '[--quiet]', '[--version]', '[root]',
];
function usageLine() {
  const prefix = 'usage: ' + D.TOOL + ' ';
  const indent = ' '.repeat(prefix.length);
  const lines = [];
  let cur = prefix;
  for (const p of USAGE_PARTS) {
    if (cur.length + p.length + 1 > 79 && cur !== prefix) { lines.push(cur.trimEnd()); cur = indent; }
    cur += p + ' ';
  }
  if (cur.trim()) lines.push(cur.trimEnd());
  return lines.join('\n');
}
const OPTIONS = [
  ['-o, --output OUTPUT', 'arg_output', { out: D.DEFAULT_OUTPUT }],
  ['--repo URL', 'arg_repo'],
  ['--ref REF', 'arg_ref'],
  ['--ext EXT [EXT ...]', 'arg_ext'],
  ['--only-ext EXT [EXT ...]', 'arg_only_ext'],
  ['--any-text', 'arg_any_text'],
  ['--include-hidden', 'arg_include_hidden'],
  ['--exclude-dir DIR [DIR ...]', 'arg_exclude_dir'],
  ['--exclude-file NAME [NAME ...]', 'arg_exclude_file'],
  ['--exclude-pattern PAT [PAT ...]', 'arg_exclude_pattern'],
  ['--include-pattern PAT [PAT ...]', 'arg_include_pattern'],
  ['--lang {auto,zh,en}', 'arg_lang'],
  ['--line-numbers', 'arg_line_numbers'],
  ['--max-file-lines N', 'arg_max_file_lines'],
  ['--max-file-kb KB', 'arg_max_file_kb'],
  ['--max-total-kb KB', 'arg_max_total_kb'],
  ['--split-tokens N', 'arg_split_tokens'],
  ['--no-tree', 'arg_no_tree'],
  ['--no-index', 'arg_no_index'],
  ['--no-ai-header', 'arg_no_ai_header'],
  ['--no-smart-order', 'arg_no_smart_order'],
  ['--prompt PROMPT', 'arg_prompt'],
  ['--prompt-file FILE', 'arg_prompt_file'],
  ['--clip', 'arg_clip'],
  ['--stdout', 'arg_stdout'],
  ['--dry-run', 'arg_dry_run'],
  ['--config PATH', 'arg_config', { cfg: D.CONFIG_FILENAME }],
  ['--no-config', 'arg_no_config'],
  ['--init-config', 'arg_init_config', { cfg: D.CONFIG_FILENAME }],
  ['--quiet', 'arg_quiet'],
  ['--version', 'arg_version'],
];
function printHelp() {
  const rows = [['-h, --help', t('arg_help')], ['root', t('arg_root')]];
  for (const [flags, key, fmt] of OPTIONS) rows.push([flags, t(key, fmt)]);
  const width = Math.max(...rows.map((r) => r[0].length));
  const out = [usageLine(), '', t('cli_desc'), '', 'options:'];
  for (const [flags, help] of rows) {
    out.push('  ' + flags + ' '.repeat(width - flags.length + 2) + help);
  }
  out.push('', t('cli_epilog'));
  process.stdout.write(out.join('\n') + '\n');
}
function parseArgs(argv) {
  const src = Array.isArray(argv) ? argv.slice() : process.argv.slice(2);
  // 预扫描 --lang/--language：让 --help 也按所选语言渲染
  for (let k = 0; k < src.length; k++) {
    const a = src[k];
    if (a === '--lang' || a === '--language') {
      if (k + 1 < src.length) { setLang(src[k + 1]); break; }
    } else if (a.startsWith('--lang=') || a.startsWith('--language=')) {
      setLang(a.slice(a.indexOf('=') + 1)); break;
    }
  }
  const args = { _: [] };
  const looksOption = (s) => typeof s === 'string' && s.length > 1 && s.charCodeAt(0) === 45;
  let i = 0;
  while (i < src.length) {
    const a = src[i];
    if (a === '--') { for (i++; i < src.length; i++) args._.push(src[i]); break; }
    if (a === '-' || !looksOption(a)) { args._.push(a); i++; continue; }
    let name = a, inline;
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      if (eq !== -1) { name = a.slice(0, eq); inline = a.slice(eq + 1); }
    }
    const key = SHORT_MAP[a] || name.replace(/^-{1,2}/, '').replace(/-/g, '_');
    if (!BOOL_FLAGS.has(key) && !GREEDY_OPTS.has(key) && !VALUE_OPTS.has(key)) {
      throw new UsageError('unrecognized argument: ' + a);
    }
    if (BOOL_FLAGS.has(key)) { args[key] = true; i++; continue; }
    const flagName = '--' + key.replace(/_/g, '-');
    if (GREEDY_OPTS.has(key)) {
      const vals = [];
      if (inline !== undefined) vals.push(inline);
      else while (i + 1 < src.length && !looksOption(src[i + 1])) vals.push(src[++i]);
      if (!vals.length) throw new UsageError('argument ' + flagName + ': expected at least one argument');
      args[key] = vals; i++; continue;
    }
    if (inline !== undefined) { args[key] = inline; i++; continue; }
    if (i + 1 >= src.length || looksOption(src[i + 1])) {
      throw new UsageError('argument ' + flagName + ': expected one argument');
    }
    args[key] = src[++i]; i++;
  }
  // choices / 类型校验
  if (args.lang !== undefined && !['auto', 'zh', 'en'].includes(args.lang)) {
    throw new UsageError("argument --lang: invalid choice: '" + args.lang + "' (choose from 'auto', 'zh', 'en')");
  }
  for (const k of ['max_file_lines', 'split_tokens']) {
    if (args[k] !== undefined) {
      const n = Number(args[k]);
      if (!Number.isInteger(n)) throw new UsageError('argument --' + k.replace(/_/g, '-') + ": invalid int value: '" + args[k] + "'");
      args[k] = n;
    }
  }
  for (const k of ['max_file_kb', 'max_total_kb']) {
    if (args[k] !== undefined) {
      const n = Number(args[k]);
      if (!Number.isFinite(n)) throw new UsageError('argument --' + k.replace(/_/g, '-') + ": invalid float value: '" + args[k] + "'");
      args[k] = n;
    }
  }
  if (args._.length > 1) throw new UsageError('unrecognized arguments: ' + args._.slice(1).join(' '));
  return args;
}
// ─────────────────────────── 文件处理 ───────────────────────────
function filePriority(p) {
  const nameL = baseNameOf(p).toLowerCase();
  if (nameL.startsWith('readme')) return 0;
  if (D.CONFIG_MANIFESTS.has(nameL) || nameL === '.gitignore' || nameL === '.dockerignore' || nameL === '.editorconfig') return 1;
  const stem = stemOf(nameL), ext = extOf(nameL);
  if (D.ENTRY_STEMS.has(stem) && D.ENTRY_EXTS.has('.' + ext)) return 2;
  if (stem === 'config' || stem === 'settings') return 2;
  return 3;
}
function orderKey(a, b) {
  const pa = filePriority(a.p), pb = filePriority(b.p);
  if (pa !== pb) return pa - pb;
  const la = a.rel.toLowerCase(), lb = b.rel.toLowerCase();
  return la < lb ? -1 : la > lb ? 1 : 0;
}
function buildRecords(cfg, candidates) {
  const records = [], skipped = [];
  let total = 0;
  const budget = cfg.maxTotalKb ? Math.trunc(cfg.maxTotalKb * 1024) : 0;
  for (const { p, rel } of candidates) {
    let size;
    try { size = fs.statSync(p).size; }
    catch (e) {
      skipped.push([rel, t('skip_unreadable', { cls: e.code || (e && e.constructor.name) || 'Error' })]);
      continue;
    }
    if (cfg.maxFileKb && size > cfg.maxFileKb * 1024) {
      skipped.push([rel, t('skip_too_large', { kb: cfg.maxFileKb, size: fmtSize(size) })]);
      continue;
    }
    const { text, enc, err } = readText(p);
    if (text === null) { skipped.push([rel, t('skip_read_err', { err })]); continue; }
    if (budget && records.length && total + cpLen(text) > budget) {
      skipped.push([rel, t('skip_over_budget')]); continue;
    }
    let txt = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    if (!txt.endsWith('\n')) txt += '\n';
    const origLines = txt.split('\n').length - 1;
    let truncated = false;
    if (cfg.maxFileLines && origLines > cfg.maxFileLines) {
      const keep = cfg.maxFileLines;
      txt = txt.split('\n').slice(0, keep).join('\n');
      if (!txt.endsWith('\n')) txt += '\n';
      txt += t('truncated_note', { orig: origLines, keep });
      truncated = true;
    }
    if (!txt.trim()) txt = t('empty_file');
    records.push({
      rel, abspath: p,
      language: require('./util.js').langOf(rel),
      encoding: enc, content: txt,
      lines: txt.split('\n').length - 1,
      chars: cpLen(txt), nbytes: size,
      truncated, origLines,
    });
    total += cpLen(txt);
  }
  return { records, skipped };
}
function loadPrompt(args) {
  if (args.prompt !== undefined) return String(args.prompt).trim();
  if (args.prompt_file !== undefined) {
    try { return fs.readFileSync(expandUser(args.prompt_file), 'utf8').trim(); }
    catch (e) { cprint(t('warn_prompt_file', { err: e.message })); }
  }
  return '';
}
// ─────────────────────────── 报告输出 ───────────────────────────
function printSummary(outPath, records, skipped, text, prunedHidden) {
  const totLines = records.reduce((s, r) => s + r.lines, 0);
  const totTokens = records.reduce((s, r) => s + estimateTokens(r.content), 0);
  const size = Buffer.byteLength(text, 'utf8');
  prunedHidden = prunedHidden || [];
  cprint();
  cprint(t('sum_generated', { path: outPath }));
  if (skipped.length) cprint(t('sum_files_skipped', { n: records.length, skipped: skipped.length }));
  else cprint(t('sum_files', { n: records.length }));
  if (prunedHidden.length) cprint(t('sum_hidden', { n: prunedHidden.length }));
  cprint(t('sum_lines', { lines: fmtInt(totLines) }));
  cprint(t('sum_size', { size: fmtSize(size) }));
  cprint(t('sum_tokens', { tokens: fmtInt(totTokens), hint: tokenHint(totTokens) }));
  cprint();
  cprint(t('sum_tip1'));
  cprint(t('sum_tip2'));
}
function dryRunReport(cfg, records, skipped, prunedHidden, rootName) {
  const tot = records.reduce((s, r) => s + estimateTokens(r.content), 0);
  prunedHidden = prunedHidden || [];
  cprint(t('dry_preview', {
    n: records.length,
    lines: fmtInt(records.reduce((s, r) => s + r.lines, 0)),
    tokens: fmtInt(tot),
  }));
  if (cfg.showTree) {
    cprint();
    cprint(buildTree(records, rootName || path.basename(cfg.root)).replace(/\n$/, ''));
  }
  cprint();
  records.forEach((r, idx) => {
    const flag = r.truncated ? t('dry_truncated_flag') : '';
    cprint(t('dry_file_item', {
      i: String(idx + 1).padStart(3), path: r.rel, lang: r.language,
      lines: r.lines, size: fmtSize(r.nbytes), flag,
    }));
  });
  if (skipped.length) {
    cprint(t('dry_skipped_head', { n: skipped.length }));
    skipped.slice(0, 20).forEach(([rel, reason]) => cprint(t('dry_skip_item', { rel, reason })));
    if (skipped.length > 20) cprint(t('dry_more', { n: skipped.length - 20 }));
  }
  if (prunedHidden.length) {
    cprint(t('dry_hidden_head', { n: prunedHidden.length }));
    prunedHidden.slice(0, 20).forEach((d) => cprint(' - ' + d + '/'));
    if (prunedHidden.length > 20) cprint(t('dry_more', { n: prunedHidden.length - 20 }));
  }
  cprint(t('dry_tokens', { tokens: fmtInt(tot), hint: tokenHint(tot) }));
  cprint(t('dry_dryrun'));
}
// ─────────────────────────── 主流程 ───────────────────────────
function isDir(p) { try { return fs.statSync(p).isDirectory(); } catch (e) { return false; } }
function isFile(p) { try { return fs.statSync(p).isFile(); } catch (e) { return false; } }
async function main(argv) {
  let args;
  try { args = parseArgs(argv); }
  catch (e) {
    if (e instanceof UsageError) {
      process.stderr.write(usageLine() + '\n' + 'error: ' + e.message + '\n');
      return 2;
    }
    throw e;
  }
  if (args.help) { printHelp(); return 0; }
  if (args.version) { cprint(D.TOOL + ' v' + D.VERSION); return 0; }
  if (args.repo && args._[0]) {
    cprint(t('err_repo_and_root'));
    return 2;
  }
  // 远程模式下配置模板会写进随后被删除的临时快照，直接在下载前拦下
  if (args.repo && args.init_config) {
    cprint(t('err_init_config_repo'));
    return 2;
  }
  let remote = null;
  let root, rootName;
  if (args.repo) {
    try {
      remote = await fetchRemoteRepo(args.repo, args.ref);
      root = remote.root;
      rootName = remote.label;
    } catch (e) {
      cprint(t('err_repo_fetch', { err: e.message || String(e) }));
      return 1;
    }
  } else {
    root = path.resolve(expandUser(args._[0] || '.'));
    rootName = path.basename(root);
  }
  const finish = (code) => {
    if (remote) removeTree(remote.tmp);
    return code;
  };
  const quiet = Boolean(args.quiet);
  const cfgPath = args.config !== undefined
    ? path.resolve(expandUser(args.config))
    : remote ? path.join(remote.tmp, D.CONFIG_FILENAME) : path.join(root, D.CONFIG_FILENAME);
  // ── 1. 先静默读取配置文件（界面语言可能写在里面），暂存加载结果 ──
  let data = {}, loadState = null; // null / ['ok'] / ['bad_root'] / ['error', exc]
  if (!args.no_config && isFile(cfgPath)) {
    try {
      const loaded = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
      if (typeof loaded !== 'object' || loaded === null || Array.isArray(loaded)) loadState = ['bad_root'];
      else { data = loaded; loadState = ['ok']; }
    } catch (e) { loadState = ['error', e]; }
  }
  // ── 2. 解析界面语言：--lang 参数 > 配置文件 language 字段 > 系统探测 ──
  setLang(args.lang !== undefined ? args.lang : (data.language !== undefined ? data.language : 'auto'));
  if (!quiet && loadState) {
    if (loadState[0] === 'ok') cprint(t('info_config_loaded', { path: cfgPath }));
    else if (loadState[0] === 'bad_root') cprint(t('warn_config_parse', { err: t('err_config_root') }));
    else cprint(t('warn_config_parse', { err: loadState[1].message }));
  }
  if (!isDir(root)) { cprint(t('err_root_not_dir', { root })); return finish(1); }
  if (args.init_config) {
    if (fs.existsSync(cfgPath)) { cprint(t('err_config_exists', { path: cfgPath })); return finish(1); }
    fs.mkdirSync(path.dirname(cfgPath), { recursive: true });
    fs.writeFileSync(cfgPath, JSON.stringify(D.CONFIG_TEMPLATE, null, 2) + '\n', 'utf8');
    cprint(t('ok_config_created', { path: cfgPath }));
    cprint(t('config_hint'));
    return finish(0);
  }
  const cfg = buildConfig(root, args, data, cfgPath);
  const disc = discover(cfg);
  const candidates = disc.found, prunedHidden = disc.prunedHidden;
  if (!candidates.length) { cprint(t('err_no_files')); return finish(1); }
  if (cfg.smartOrder) candidates.sort(orderKey);
  const built = buildRecords(cfg, candidates);
  const records = built.records, skipped = built.skipped;
  if (!records.length) { cprint(t('err_all_skipped')); return finish(1); }
  const promptText = loadPrompt(args);
  if (args.dry_run) { dryRunReport(cfg, records, skipped, prunedHidden, rootName); return finish(0); }
  // ── 分卷模式 ──
  if (cfg.splitTokens && !args.stdout) {
    const chunks = []; let cur = [], curTok = 0;
    for (const r of records) {
      const tk = estimateTokens(r.content); // 注意：勿命名为 t，避免遮蔽翻译函数
      if (cur.length && curTok + tk > cfg.splitTokens) { chunks.push([cur, curTok]); cur = []; curTok = 0; }
      cur.push(r); curTok += tk;
    }
    if (cur.length) chunks.push([cur, curTok]);
    if (chunks.length > 1) {
      const base = path.resolve(cfg.output);
      fs.mkdirSync(path.dirname(base), { recursive: true });
      const suf = path.extname(base) || '.md';
      const stem = path.basename(base, path.extname(base));
      chunks.forEach(([chunk, tok], idx) => {
        const i = idx + 1;
        const label = t('part_label', { i, n: chunks.length });
        const sk = i === chunks.length ? skipped : [];
        const ph = i === chunks.length ? prunedHidden : [];
        const txt = render(cfg, chunk, sk, promptText, rootName, label, ph);
        const p = path.join(path.dirname(base), stem + '.part' + i + suf);
        fs.writeFileSync(p, txt, 'utf8');
        if (!quiet) {
          cprint(t('ok_part_generated', {
            name: path.basename(p), files: chunk.length,
            tokens: fmtInt(tok), size: fmtSize(Buffer.byteLength(txt, 'utf8')),
          }));
        }
      });
      if (!quiet) cprint(t('split_hint', { n: cfg.splitTokens, total: chunks.length }));
      return finish(0);
    }
  }
  const text = render(cfg, records, skipped, promptText, rootName, '', prunedHidden);
  if (args.stdout) { process.stdout.write(text); return finish(0); }
  const out = path.resolve(cfg.output);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, text, 'utf8');
  if (quiet) cprint(out);
  else printSummary(out, records, skipped, text, prunedHidden);
  if (cfg.clip) {
    const res = copyClipboard(text);
    if (res.ok) cprint(t('ok_clipboard', { how: res.how }));
    else cprint(t('err_clipboard'));
  }
  return finish(0);
}
async function cli() {
  process.on('SIGINT', () => { cprint(t('cancelled')); process.exit(130); });
  try {
    process.exitCode = await main();
  } catch (e) {
    process.stderr.write(String((e && e.stack) || e) + '\n');
    process.exitCode = 1;
  }
}
module.exports = { parseArgs, main, cli };
