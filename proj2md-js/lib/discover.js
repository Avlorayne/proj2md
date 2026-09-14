'use strict';
const fs = require('fs');
const path = require('path');
const D = require('./defaults.js');
const { fnmatch } = require('./util.js');
function _matchAny(relPosix, nameLower, patterns) {
  for (const pat of patterns) {
    const patL = String(pat).toLowerCase();
    if (fnmatch(nameLower, patL) || fnmatch(relPosix, patL)) return true;
  }
  return false;
}
/** 判断某目录是否可能被 --include-pattern 覆盖（让强制包含穿透「隐藏目录忽略」）。 */
function _dirMayBeIncluded(dirRel, patterns) {
  for (const pat of patterns) {
    const prefix = String(pat).toLowerCase().split('*')[0];
    if (!prefix) return true;
    if (dirRel.toLowerCase().startsWith(prefix)) return true;
    if (prefix.startsWith(dirRel.toLowerCase() + '/')) return true;
  }
  return false;
}
function _realish(p) { try { return fs.realpathSync(p); } catch (e) { return p; } }
/**
 * 遍历项目收集候选文件，返回 { found: [{p, rel}], prunedHidden: [relDir] }。
 * 目录剪枝顺序：include-pattern 覆盖 > 隐藏目录忽略 > 目录黑名单。
 * rel 统一为 posix 风格（"/"分隔），与输出格式一致。
 */
function discover(cfg) {
  const root = cfg.root;
  const outAbs = _realish(path.resolve(cfg.output));
  const cfgAbs = cfg.configPath ? _realish(path.resolve(cfg.configPath)) : null;
  const selfAbs = new Set([_realish(__filename)]);
  if (process.argv[1]) selfAbs.add(_realish(path.resolve(process.argv[1])));
  const found = [];
  const prunedHidden = [];
  const walk = (dir, relBase) => {
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
    catch (e) { return; }
    const dirs = [], files = [];
    for (const e of entries) {
      if (e.isDirectory()) dirs.push(e.name);        // 符号链接目录不跟随（同 os.walk 默认）
      else if (e.isFile()) files.push(e.name);
    }
    dirs.sort(); files.sort();
    // ── 目录剪枝 ──
    const kept = [];
    for (const d of dirs) {
      const relDir = relBase ? relBase + '/' + d : d;
      if (_dirMayBeIncluded(relDir, cfg.includePatterns)) { kept.push(d); continue; }
      if (cfg.excludeHidden && d.startsWith('.')) { prunedHidden.push(relDir); continue; }
      if (cfg.excludeDirs.has(d.toLowerCase())) continue;
      kept.push(d);
    }
    // ── 当前目录文件（与 os.walk 顺序一致：先本层文件，再递归子目录）──
    for (const fn of files) {
      const p = path.join(dir, fn);
      const rel = relBase ? relBase + '/' + fn : fn;
      const nameL = fn.toLowerCase();
      const pa = _realish(p);
      if (pa === outAbs || (cfgAbs && pa === cfgAbs) || selfAbs.has(pa)) continue;
      const includedOverride = _matchAny(rel, nameL, cfg.includePatterns);
      if (cfg.excludeFiles.has(nameL) && !includedOverride) continue;
      if (_matchAny(rel, nameL, cfg.excludePatterns) && !includedOverride) continue;
      const dot = fn.lastIndexOf('.');
      const ext = dot > 0 ? fn.slice(dot + 1).toLowerCase() : '';
      if (!(cfg.anyText || cfg.exts.has(ext) || D.DEFAULT_FILENAMES.has(nameL))) {
        if (!includedOverride) continue;
      }
      found.push({ p, rel });
    }
    for (const d of kept) walk(path.join(dir, d), relBase ? relBase + '/' + d : d);
  };
  walk(root, '');
  return { found, prunedHidden };
}
module.exports = { discover };

