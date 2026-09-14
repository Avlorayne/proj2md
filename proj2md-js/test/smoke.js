#!/usr/bin/env node
'use strict';
/*
 * proj2md 冒烟测试：在临时目录里搭一个示例项目，跑通主要功能。
 * 运行：npm test   （或 node test/smoke.js）
 *
 * 说明：子进程输出统一重定向到临时文件（而不是管道），
 * 这样在限制管道 stdio 的沙箱环境里也能跑；生成物一律写到项目目录之外，
 * 避免被后续运行再次拼接进来。
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const BIN = path.join(__dirname, '..', 'bin', 'proj2md.js');
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'proj2md-test-'));
const PROJ = path.join(TMP, 'sample');
const OUT = path.join(TMP, 'out');
const LOGS = path.join(TMP, 'logs');
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(LOGS, { recursive: true });

let pass = 0;
let seq = 0;
const failures = [];
function ok(name, cond, extra) {
  if (cond) { pass++; process.stdout.write('  ok   ' + name + '\n'); }
  else { failures.push(name); process.stdout.write('  FAIL ' + name + (extra ? '\n       ' + extra : '') + '\n'); }
}
function run(args) {
  const log = path.join(LOGS, 'out' + (++seq) + '.txt');
  const fd = fs.openSync(log, 'w');
  let r;
  try {
    r = spawnSync(process.execPath, [BIN].concat(args), { stdio: ['ignore', fd, fd] });
  } finally {
    fs.closeSync(fd);
  }
  return { status: r.status, out: fs.readFileSync(log, 'utf8') };
}
function write(rel, text) {
  const p = path.join(PROJ, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text, 'utf8');
  return p;
}
function read(p) { return fs.readFileSync(p, 'utf8'); }
function section(name) { process.stdout.write('\n' + name + '\n'); }
/** 提取正文里被拼接进去的源文件列表（### N. path） */
function bundled(md) { return (md.match(/^### \d+\. .+$/gm) || []).map((l) => l.replace(/^### \d+\. /, '')); }

// ── 示例项目 ──
write('README.md', '# Sample\n\nhello\n');
write('package.json', JSON.stringify({ name: 'sample', version: '1.0.0' }, null, 2) + '\n');
write('.gitignore', 'node_modules/\n');
write('src/main.py', 'def main():\n    print("hi")\n');
write('src/util.js', 'module.exports = 1;\n');
write('api/schema.proto', 'message A { string b = 1; }\n');
write('tests/test_main.py', 'def test_x():\n    assert True\n');
write('.hidden/secret.txt', 'hidden secret\n');
write('node_modules/dep/index.js', 'nope\n');
write('assets/logo.png', Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x00, 0x01, 0x02]));
write('big.txt', Array.from({ length: 40 }, (_, i) => 'line ' + (i + 1)).join('\n') + '\n');

// ── 1. 基本命令 ──
section('1. version / help');
ok('--version', /^proj2md v\d+\.\d+\.\d+/.test(run(['--version']).out.trim()));
ok('--help', run(['--help']).out.includes('usage: proj2md'));
ok('--help --lang en', run(['--help', '--lang', 'en']).out.includes('show this help message'));
ok('bad flag -> exit 2', run(['--nope']).status === 2);

// ── 2. 默认拼接 ──
section('2. default bundle');
const out1 = path.join(OUT, 'out1.md');
const r1 = run([PROJ, '-o', out1]);
ok('exit 0', r1.status === 0, r1.out);
ok('file written', fs.existsSync(out1));
const md1 = fs.existsSync(out1) ? read(out1) : '';
const files1 = bundled(md1);
ok('has title', md1.includes('# 项目代码合集：sample'));
ok('has tree/index/source', ['## 🗂 目录结构', '## 📑 文件索引', '## 📄 源代码正文'].every((s) => md1.includes(s)));
ok('includes src/main.py', files1.includes('src/main.py'));
ok('skips node_modules', !files1.includes('node_modules/dep/index.js'));
ok('skips hidden dir', !files1.includes('.hidden/secret.txt') && md1.includes('附录：已忽略的隐藏目录'));
ok('skips binary png', !files1.includes('assets/logo.png'));
ok('smart order: README first', files1[0] === 'README.md', 'first = ' + files1[0]);
ok('no NUL marks left', !md1.includes('\x00'));
ok('ends with END footer', /\*END · / .test(md1) && /共 \d+ 个文件/.test(md1));

// ── 3. 索引“起始行”回填 ──
section('3. index start lines');
const lines1 = md1.split('\n');
const row = lines1.find((l) => /^\|\s*1\s*\|/.test(l));
const startNo = row ? Number(row.trim().split('|').slice(-2)[0]) : 0;
ok('index start is a number', startNo > 0, 'row=' + row);
ok('index start points at body', lines1[startNo - 1] === '# Sample', 'got ' + JSON.stringify(lines1[startNo - 1]));
const rowSkip = lines1.find((l) => /^\|\s*\d+\s*\|\s*\[`src\/main\.py`\]/.test(l));
ok('index has an entry per file', Boolean(rowSkip), 'no row for src/main.py');
ok('index rows == bundled files', lines1.filter((l) => /^\|\s*\d+\s*\|/.test(l)).length === files1.length);

// ── 4. 扩展名筛选 ──
section('4. extension filters');
const outOnly = path.join(OUT, 'only.md');
run([PROJ, '-o', outOnly, '--only-ext', 'py']);
const filesOnly = bundled(read(outOnly));
ok('--only-ext py keeps py', filesOnly.includes('src/main.py') && filesOnly.includes('tests/test_main.py'));
ok('--only-ext py drops js', !filesOnly.includes('src/util.js'));
const outExt = path.join(OUT, 'ext.md');
run([PROJ, '-o', outExt, '--ext', 'proto']);
const filesExt = bundled(read(outExt));
ok('--ext proto adds proto (default set kept)', filesExt.includes('api/schema.proto') && filesExt.includes('src/main.py'));
const outNoExt = path.join(OUT, 'noext.md');
run([PROJ, '-o', outNoExt, '--only-ext', 'py', '--ext', 'proto']);
const filesNoExt = bundled(read(outNoExt));
ok('--only-ext wins over --ext', filesNoExt.includes('src/main.py') && !filesNoExt.includes('src/util.js'));
const outAny = path.join(OUT, 'any.md');
run([PROJ, '-o', outAny, '--any-text', '--exclude-pattern', '*.png']);
ok('--any-text keeps extensionless text', bundled(read(outAny)).includes('.gitignore'));

// ── 5. 忽略 / 包含规则 ──
section('5. ignore rules');
const outHidden = path.join(OUT, 'hidden.md');
run([PROJ, '-o', outHidden, '--include-hidden']);
ok('--include-hidden includes .hidden', bundled(read(outHidden)).includes('.hidden/secret.txt'));
const outInc = path.join(OUT, 'inc.md');
run([PROJ, '-o', outInc, '--include-pattern', '.hidden/*']);
ok('--include-pattern pierces hidden', bundled(read(outInc)).includes('.hidden/secret.txt'));
const outEx = path.join(OUT, 'ex.md');
run([PROJ, '-o', outEx, '--exclude-dir', 'tests', '--exclude-pattern', '*.js']);
const filesEx = bundled(read(outEx));
ok('--exclude-dir works', !filesEx.includes('tests/test_main.py'));
ok('--exclude-pattern works', !filesEx.includes('src/util.js'));

// ── 6. 行号 / 截断 / 预算 ──
section('6. line numbers / truncate / budget');
const outLn = path.join(OUT, 'ln.md');
run([PROJ, '-o', outLn, '--line-numbers']);
ok('--line-numbers prefixes body', /^ {4}1 \| /m.test(read(outLn)));
const outTr = path.join(OUT, 'tr.md');
run([PROJ, '-o', outTr, '--max-file-lines', '5']);
const mdTr = read(outTr);
ok('--max-file-lines truncates', mdTr.includes('--max-file-lines=5') && mdTr.includes('**已截断**'));
const outKb = path.join(OUT, 'kb.md');
run([PROJ, '-o', outKb, '--max-file-kb', '0.2']);
const mdKb = read(outKb);
ok('--max-file-kb skips big files', !bundled(mdKb).includes('big.txt') && mdKb.includes('超过单文件上限'));
const outBudget = path.join(OUT, 'budget.md');
run([PROJ, '-o', outBudget, '--max-total-kb', '0.2']);
ok('--max-total-kb stops appending', read(outBudget).includes('超出 --max-total-kb 总预算'));

// ── 7. 分卷 / stdout / dry-run ──
section('7. split / stdout / dry-run');
const outSplit = path.join(OUT, 'split.md');
const rSplit = run([PROJ, '-o', outSplit, '--split-tokens', '20']);
const parts = [1, 2].map((i) => path.join(OUT, 'split.part' + i + '.md'));
ok('--split-tokens creates volumes', parts.every((p) => fs.existsSync(p)) && !fs.existsSync(outSplit), rSplit.out);
ok('volumes carry part label', read(parts[0]).includes('第 1/'));
ok('volume files are disjoint', bundled(read(parts[0])).every((f) => !bundled(read(parts[1])).includes(f)));
const rStdout = run([PROJ, '--stdout', '--only-ext', 'py']);
ok('--stdout prints markdown, writes nothing', rStdout.out.includes('## 📄 源代码正文') && !fs.existsSync(path.join(PROJ, 'project_bundle.md')));
const rDry = run([PROJ, '--dry-run']);
ok('--dry-run writes nothing', rDry.status === 0 && !fs.existsSync(path.join(PROJ, 'project_bundle.md')));
ok('--dry-run lists files', rDry.out.includes('将被拼接') && rDry.out.includes('src/main.py'));

// ── 8. 配置文件 / prompt / 语言 ──
section('8. config / prompt / lang');
const rInit = run([PROJ, '--init-config']);
const cfgPath = path.join(PROJ, 'proj2md.json');
ok('--init-config creates template', rInit.status === 0 && fs.existsSync(cfgPath));
ok('--init-config twice errors', run([PROJ, '--init-config']).status === 1);
const cfg = JSON.parse(read(cfgPath));
ok('template has snake_case keys', cfg.output === 'project_bundle.md' && cfg.exclude_hidden === true && cfg.language === 'auto');
cfg.line_numbers = true;
fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2));
const outCfg = path.join(OUT, 'cfg.md');
run([PROJ, '-o', outCfg]);
ok('config file is loaded', /^ {4}1 \| /m.test(read(outCfg)));
run([PROJ, '-o', outCfg, '--no-config']);
ok('--no-config ignores config', !/^ {4}1 \| /m.test(read(outCfg)));
ok('config output key is used', (function () {
  cfg.line_numbers = false;
  cfg.output = path.join(OUT, 'from-config.md').replace(/\\/g, '/');
  fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2));
  run([PROJ]);
  return fs.existsSync(path.join(OUT, 'from-config.md'));
})());
const outPrompt = path.join(OUT, 'prompt.md');
run([PROJ, '-o', outPrompt, '--prompt', '请帮我看看']);
ok('--prompt embedded', read(outPrompt).includes('请帮我看看'));
const promptFile = path.join(OUT, 'req.txt');
fs.writeFileSync(promptFile, '来自文件的需求', 'utf8');
const outPrompt2 = path.join(OUT, 'prompt2.md');
run([PROJ, '-o', outPrompt2, '--prompt-file', promptFile]);
ok('--prompt-file embedded', read(outPrompt2).includes('来自文件的需求'));
const rEn = run([PROJ, '--dry-run', '--lang', 'en']);
ok('--lang en', rEn.out.includes('Preview:') && rEn.out.includes('files will be bundled'));
ok('--lang zh', run([PROJ, '--dry-run', '--lang', 'zh']).out.includes('预览'));
ok('--quiet prints only path', (function () {
  const q = run([PROJ, '--quiet', '-o', path.join(OUT, 'quiet.md')]).out.trim();
  return q === path.join(OUT, 'quiet.md');
})());

// ── 9. 错误分支 ──
section('9. errors');
ok('missing root -> exit 1', run([path.join(TMP, 'nope')]).status === 1);
const empty = path.join(TMP, 'empty');
fs.mkdirSync(empty, { recursive: true });
ok('empty root -> exit 1', run([empty]).status === 1);

// ── 收尾 ──
process.stdout.write('\n' + pass + ' passed, ' + failures.length + ' failed\n');
if (failures.length) {
  process.stdout.write('failed: ' + failures.join(', ') + '\n');
  process.exitCode = 1;
} else {
  fs.rmSync(TMP, { recursive: true, force: true });
}