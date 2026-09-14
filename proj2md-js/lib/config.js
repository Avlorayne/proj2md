'use strict';
const D = require('./defaults.js');
const { normalizeExt, expandUser } = require('./util.js');
class Config {
  constructor(fields) { Object.assign(this, fields); }
}
/** 合并优先级：命令行参数 > 配置文件 > 内置默认（与 Python 版一致）。 */
function buildConfig(root, args, data, cfgPath) {
  data = data || {};
  const v = (key, cli, dflt) =>
    (cli !== undefined && cli !== null) ? cli
      : (data[key] !== undefined && data[key] !== null) ? data[key] : dflt;
  const flag = (key, noCli, dflt) => noCli ? false : Boolean(data[key] !== undefined ? data[key] : dflt);
  const posFlag = (key, cli) => Boolean(cli) || Boolean(data[key] || false);
  let exts = new Set(D.DEFAULT_EXTS);
  const cfgExts = data.exts;
  if (Array.isArray(cfgExts) && cfgExts.length) exts = new Set(cfgExts.map(normalizeExt));
  if (args.only_ext && args.only_ext.length) {
    exts = new Set(args.only_ext.map(normalizeExt));
  } else if (args.ext && args.ext.length) {
    for (const e of args.ext) exts.add(normalizeExt(e));
  }
  const mergeSet = (defaults, key, cliVal) => {
    const s = new Set(defaults);
    const cv = data[key];
    if (Array.isArray(cv)) cv.forEach((x) => s.add(String(x).toLowerCase()));
    if (cliVal) cliVal.forEach((x) => s.add(String(x).toLowerCase()));
    return s;
  };
  const mergeList = (defaults, key, cliVal) => {
    const out = defaults.slice();
    const cv = data[key];
    if (Array.isArray(cv)) out.push(...cv.map(String));
    if (cliVal) out.push(...cliVal.map(String));
    return out;
  };
  // 隐藏目录忽略：默认 true；--include-hidden 或配置 exclude_hidden=false 可关闭
  let excludeHidden = true;
  if (args.include_hidden) excludeHidden = false;
  else if (data.exclude_hidden !== undefined && data.exclude_hidden !== null) excludeHidden = Boolean(data.exclude_hidden);
  return new Config({
    root,
    output: expandUser(String(v('output', args.output, D.DEFAULT_OUTPUT))),
    exts,
    anyText: posFlag('any_text', args.any_text),
    excludeHidden,
    excludeDirs: mergeSet(D.DEFAULT_EXCLUDE_DIRS, 'exclude_dirs', args.exclude_dir),
    excludeFiles: mergeSet(D.DEFAULT_EXCLUDE_FILES, 'exclude_files', args.exclude_file),
    excludePatterns: mergeList(D.DEFAULT_EXCLUDE_PATTERNS, 'exclude_patterns', args.exclude_pattern),
    includePatterns: mergeList([], 'include_patterns', args.include_pattern),
    lineNumbers: posFlag('line_numbers', args.line_numbers),
    maxFileLines: parseInt(v('max_file_lines', args.max_file_lines, 0), 10) || 0,
    maxFileKb: parseFloat(v('max_file_kb', args.max_file_kb, 512)) || 0,
    maxTotalKb: parseFloat(v('max_total_kb', args.max_total_kb, 0)) || 0,
    splitTokens: parseInt(v('split_tokens', args.split_tokens, 0), 10) || 0,
    showTree: flag('show_tree', args.no_tree, true),
    showIndex: flag('show_index', args.no_index, true),
    aiHeader: flag('ai_header', args.no_ai_header, true),
    smartOrder: flag('smart_order', args.no_smart_order, true),
    clip: posFlag('clip', args.clip),
    configPath: cfgPath,
  });
}
module.exports = { Config, buildConfig };

