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
  const env = {
    ...process.env,
    LANG: 'zh_CN.UTF-8',
    LANGUAGE: 'zh_CN.UTF-8',
  };
  let r;
  try {
    r = spawnSync(process.execPath, [BIN].concat(args), { env, stdio: ['ignore', fd, fd] });
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
// 构建产物目录：*.egg-info 等通配黑名单（proj2md 自己的合集就曾收录 egg-info）
write('pkg.egg-info/PKG-INFO', 'Metadata-Version: 2.1\n');
write('pkg.egg-info/SOURCES.txt', 'src/main.py\n');
write('deps.dist-info/METADATA', 'Name: deps\n');
const outEgg = path.join(OUT, 'egg.md');
run([PROJ, '-o', outEgg]);
const mdEgg = read(outEgg);
ok('wildcard dir blacklist skips egg-info', !bundled(mdEgg).some((f) => /egg-info|dist-info/.test(f)),
  bundled(mdEgg).join(','));
// 目录链接不递归（跟随会让子树被收录两遍，成环时还会无限递归）
const linkDir = path.join(PROJ, 'linked-src');
let linkMade = false;
try { fs.symlinkSync(path.join(PROJ, 'src'), linkDir, 'junction'); linkMade = true; } catch (e) { /* 无权限则跳过 */ }
if (linkMade) {
  const outLink = path.join(OUT, 'link.md');
  run([PROJ, '-o', outLink]);
  ok('does not recurse into dir links', !bundled(read(outLink)).includes('linked-src/main.py'));
  fs.rmSync(linkDir, { recursive: true, force: true });
}
// 文件链接照常收录（与 Python os.walk 把 symlink-to-file 归入 filenames 一致）
const linkFile = path.join(PROJ, 'linked-util.js');
let fileLinkMade = false;
try { fs.symlinkSync(path.join(PROJ, 'src', 'util.js'), linkFile, 'file'); fileLinkMade = true; } catch (e) { /* Windows 建文件软链需管理员 */ }
if (fileLinkMade) {
  const outLinkF = path.join(OUT, 'linkf.md');
  run([PROJ, '-o', outLinkF]);
  ok('includes file links', bundled(read(outLinkF)).includes('linked-util.js'));
  fs.rmSync(linkFile, { force: true });
}

// 编码判定：能 decode 就接受，不做 round-trip（GBK 存在多对一区段，
// round-trip 失败会让 Node 降级 latin-1，与 Python 的「编码」字段分叉）。
// iconv-lite 是可选依赖，缺失时跳过。
(function encodingChain() {
  let iconv = null;
  try { iconv = require('iconv-lite'); } catch (e) { iconv = null; }
  if (!iconv) { process.stdout.write('  skip gbk decode (iconv-lite not installed)\n'); return; }
  const { readText } = require(path.join(__dirname, '..', 'lib', 'reader.js'));
  const txt = '中文测试内容\n';
  const p = path.join(TMP, 'gbk.txt');
  fs.writeFileSync(p, iconv.encode(txt, 'gbk'));
  const r = readText(p);
  ok('gbk file decoded as gbk', r.enc === 'gbk' && r.text === txt, 'enc=' + r.enc);
  // a2e3 解码为 "€" 但再编码得到 80（GBK 多对一）：旧 round-trip 判定会判失败并降级
  // latin-1，于是同一份字节 Python 报 gbk、Node 报 latin-1。
  const p2 = path.join(TMP, 'gbk-tricky.txt');
  fs.writeFileSync(p2, Buffer.concat([Buffer.from([0xa2, 0xe3]), Buffer.from('\n', 'utf8')]));
  const r2 = readText(p2);
  ok('gbk multi-to-one bytes still decode as gbk', r2.enc === 'gbk' && r2.text === '€\n',
    'enc=' + r2.enc + ' text=' + JSON.stringify(r2.text));
})();

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
ok('--repo with root -> exit 2', run(['--repo', 'https://github.com/o/r', PROJ]).status === 2);
ok('--repo with --init-config -> exit 2', run(['--repo', 'https://github.com/o/r', '--init-config']).status === 2);

// ── 10. 远程仓库（离线校验，不访问网络） ──
section('10. remote repo helpers');
const remote = require(path.join(__dirname, '..', 'lib', 'remote.js'));
const gh = remote.githubRepo;
ok('parses https URL', JSON.stringify(gh('https://github.com/Avlorayne/proj2md')) === JSON.stringify({ owner: 'Avlorayne', repo: 'proj2md' }));
ok('parses .git / trailing slash / query', JSON.stringify(gh('https://github.com/Avlorayne/proj2md.git/?tab=readme')) === JSON.stringify({ owner: 'Avlorayne', repo: 'proj2md' }));
ok('parses ssh form', JSON.stringify(gh('git@github.com:Avlorayne/proj2md.git')) === JSON.stringify({ owner: 'Avlorayne', repo: 'proj2md' }));
ok('rejects non-GitHub host', gh('https://gitlab.com/owner/repo') === null);
ok('rejects bare shorthand', gh('octocat/Hello-World') === null);

// 造一个带顶层目录的 tar.gz（含 ../ 与盘符穿越条目），验证解包与路径隔离
function tarBlock(name, body) {
  const hdr = Buffer.alloc(512);
  hdr.write(name, 0, 'utf8');
  hdr.write('0000644\0', 100, 'ascii');
  hdr.write('0000000\0', 108, 'ascii');
  hdr.write('0000000\0', 116, 'ascii');
  hdr.write(body.length.toString(8).padStart(11, '0') + '\0', 124, 'ascii');
  hdr.write('00000000000\0', 136, 'ascii');
  hdr.write('00000000000\0', 148, 'ascii');
  hdr[156] = 48; // 普通文件
  hdr.write('ustar\0', 257, 'ascii');
  let sum = 0;
  for (const b of hdr) sum += b;
  hdr.write(sum.toString(8).padStart(6, '0') + '\0 ', 148, 'ascii'); // 校验和字段本身按空格计
  return [hdr, body, Buffer.alloc((512 - (body.length % 512)) % 512)];
}
function makeTarGz(entries) {
  const blocks = [];
  for (const [name, text] of entries) blocks.push(...tarBlock(name, Buffer.from(text)));
  blocks.push(Buffer.alloc(1024)); // 归档结束标记
  return require('zlib').gzipSync(Buffer.concat(blocks));
}
const tar = makeTarGz([
  ['repo-main/src/main.py', 'print(1)\n'],
  ['repo-main/README.md', '# hi\n'],
  ['../escape.txt', 'nope\n'],
]);
const dest = path.join(TMP, 'unpacked');
fs.mkdirSync(dest, { recursive: true });
remote.extractTar(tar, dest);
ok('strips common top-level dir', fs.existsSync(path.join(dest, 'src', 'main.py')) && fs.existsSync(path.join(dest, 'README.md')));
ok('rejects .. path traversal', !fs.existsSync(path.join(TMP, 'escape.txt')) && !fs.existsSync(path.join(dest, '..', 'escape.txt')));
ok('rejects drive-letter entry', remote.tarEntries(makeTarGz([['C:/evil.txt', 'x\n']])).length === 0);
// 绝对路径条目（filter(Boolean) 会把首段空串滤掉，需显式拒绝才能拦住）
ok('rejects absolute-path tar entry', remote.tarEntries(makeTarGz([['/etc/evil.txt', 'x\n']])).length === 0);
ok('empty archive -> throws', (function () {
  try { remote.extractTar(Buffer.alloc(1024), dest); return false; } catch (e) { return /no files/.test(e.message); }
})());

// 代理：Node 的 https 不读系统代理，需要自己探测才能与 Python 版行为一致
const px = remote.parseProxy;
ok('parses host:port', JSON.stringify(px('127.0.0.1:12000')) === JSON.stringify({ host: '127.0.0.1', port: 12000, noProxy: [] }));
ok('parses scheme form', JSON.stringify(px('http://proxy.local:3128')) === JSON.stringify({ host: 'proxy.local', port: 3128, noProxy: [] }));
ok('parses per-scheme form', px('http=10.0.0.1:8080;https=10.0.0.2:8443').host === '10.0.0.2');
ok('ignores malformed value', px('not a url') === null && px('') === null && px(null) === null);
ok('no_proxy suffix match', remote.matchNoProxy('example.com', 'api.example.com') && !remote.matchNoProxy('example.com', 'notexample.com'));
ok('no_proxy wildcard', remote.matchNoProxy('*', 'anything.io'));
ok('envProxy reads HTTPS_PROXY', (function () {
  const p = remote.envProxy({ HTTPS_PROXY: 'http://127.0.0.1:12000' }, 'api.github.com');
  return p && p.port === 12000;
})());
ok('envProxy honours NO_PROXY', remote.envProxy({ HTTPS_PROXY: 'http://127.0.0.1:12000', NO_PROXY: 'github.com' }, 'api.github.com') === null);
ok('envProxy absent -> null', remote.envProxy({}, 'api.github.com') === null);

// 本地假代理：验证 CONNECT 隧道能建立，并对非 200 应答报错
function withFakeProxy(reply, fn) {
  const srv = require('net').createServer((sock) => {
    sock.once('data', (req) => sock.write(reply(req.toString('latin1'))));
  });
  return new Promise((resolve, reject) => {
    srv.listen(0, '127.0.0.1', async () => {
      try { resolve(await fn(srv.address().port)); }
      catch (e) { reject(e); }
      finally { srv.close(); }
    });
  });
}
// 响应头与紧随其后的数据粘在同一个 chunk 时，剩余字节必须回推到隧道 socket。
// 旧实现直接丢弃（或错用累积串偏移做 chunk 切片），真实 TLS 握手会永远等不到 ServerHello。
function withStickyProxy(fn) {
  const rest = 'PAYLOAD-AFTER-HEADERS';
  const srv = require('net').createServer((sock) => {
    sock.once('data', () => sock.write('HTTP/1.1 200 Connection established\r\n\r\n' + rest));
  });
  return new Promise((resolve, reject) => {
    srv.listen(0, '127.0.0.1', async () => {
      try { resolve(await fn(srv.address().port, rest)); }
      catch (e) { reject(e); }
      finally { srv.close(); }
    });
  });
}

// ── 11. 反向还原（--restore） ──
section('11. restore');
const bundleOut = path.join(OUT, 'restore-src.md');
run([PROJ, '-o', bundleOut, '--no-config']);
ok('restore --list', run(['--restore', bundleOut, '--list']).out.includes('src/main.py') && run(['--restore', bundleOut, '--list']).out.includes('共解析到'));
const restored = path.join(OUT, 'restored');
const rRes = run(['--restore', bundleOut, restored]);
ok('restore round-trip', rRes.status === 0
  && read(path.join(restored, 'src', 'main.py')) === read(path.join(PROJ, 'src', 'main.py'))
  && read(path.join(restored, 'api', 'schema.proto')) === read(path.join(PROJ, 'api', 'schema.proto'))
  && fs.existsSync(path.join(restored, '.gitignore')));
ok('second restore all unchanged', run(['--restore', bundleOut, restored]).out.includes('未变更'));
const rstDry = run(['--restore', bundleOut, path.join(OUT, 'never'), '--dry-run']);
ok('restore --dry-run writes nothing', rstDry.status === 0 && rstDry.out.includes('未写盘') && !fs.existsSync(path.join(OUT, 'never')));
const rstJson = run(['--restore', bundleOut, '--json']);
ok('restore --json', rstJson.status === 0 && rstJson.out.trim().startsWith('[') && rstJson.out.includes('"path": "src/main.py"'));
// 截断保护：默认跳过，--allow-truncated 强制写回
const truncMd = path.join(OUT, 'trunc-bundle.md');
fs.writeFileSync(truncMd, '### 1. t/a.txt\n\n```\nline1\n……（该文件共 10 行，超过 --max-file-lines=1 限制，此处仅保留前 1 行）\n```\n');
const rstTr = run(['--restore', truncMd, path.join(OUT, 'r-trunc')]);
ok('truncated skipped by default', rstTr.status === 0 && !fs.existsSync(path.join(OUT, 'r-trunc', 't', 'a.txt')) && rstTr.out.includes('跳过'));
ok('--allow-truncated writes', (function () {
  const p = path.join(OUT, 'r-trunc2', 't', 'a.txt');
  const r = run(['--restore', truncMd, path.join(OUT, 'r-trunc2'), '--allow-truncated']);
  return r.status === 0 && fs.existsSync(p) && fs.readFileSync(p, 'utf8') === 'line1\n';
})());
// 路径逃逸：../ 被拒绝，其余条目正常写回
const badMd = path.join(OUT, 'bad-bundle.md');
fs.writeFileSync(badMd, '### 1. ../escape.txt\n\n```\nevil\n```\n\n### 2. ok.txt\n\n```\nfine\n```\n');
const rstBad = run(['--restore', badMd, path.join(OUT, 'r-bad')]);
ok('unsafe path rejected', rstBad.status === 1 && rstBad.out.includes('路径不安全')
  && !fs.existsSync(path.join(OUT, 'escape.txt'))
  && fs.readFileSync(path.join(OUT, 'r-bad', 'ok.txt'), 'utf8') === 'fine\n');
// 绝对路径：safeRel 曾把 "/etc/x" 相对化成 "etc/x"，护栏形同虚设
const { safeRel } = require(path.join(__dirname, '..', 'lib', 'restore.js'));
ok('safeRel rejects absolute paths',
  ['/etc/cron.d/evil', '//server/share/x', '\\windows\\system32\\x', 'C:\\x'].every((p) => safeRel(p) === null));
ok('safeRel rejects .. and reserved names', ['../x', 'a/../../x', 'CON.txt'].every((p) => safeRel(p) === null));
ok('safeRel keeps normal relative paths', safeRel('src/main.py') === 'src/main.py');
// 合集里写绝对路径时，应报「路径不安全」而不是写到目标目录之外
const absMd = path.join(OUT, 'abs-bundle.md');
fs.writeFileSync(absMd, '### 1. /etc/cron.d/evil\n\n```\nevil\n```\n');
const rstAbsDir = path.join(OUT, 'r-abs');
const rstAbs = run(['--restore', absMd, rstAbsDir]);
ok('absolute bundle path rejected', rstAbs.status === 1 && rstAbs.out.includes('路径不安全')
  && !fs.existsSync(path.join(rstAbsDir, 'etc')));
// stdin（run() 助手固定 ignore stdin，这里单独起子进程喂管道）
(function testStdinRestore() {
  const log = path.join(LOGS, 'stdin-restore.txt');
  const fd = fs.openSync(log, 'w');
  const env = { ...process.env, LANG: 'zh_CN.UTF-8', LANGUAGE: 'zh_CN.UTF-8' };
  let r;
  try {
    r = spawnSync(process.execPath, [BIN, '--restore', '-', path.join(OUT, 'r-stdin')],
      { input: fs.readFileSync(bundleOut), env, stdio: ['pipe', fd, fd] });
  } finally { fs.closeSync(fd); }
  ok('stdin restore', r.status === 0
    && read(path.join(OUT, 'r-stdin', 'src', 'main.py')) === read(path.join(PROJ, 'src', 'main.py')));
})();
// 更新 / diff / backup
const updDir = path.join(OUT, 'r-upd');
run(['--restore', bundleOut, updDir]);
fs.writeFileSync(path.join(updDir, 'src', 'main.py'), 'changed\n', 'utf8');
const rstDiff = run(['--restore', bundleOut, updDir, '--diff']);
ok('restore --diff prints unified diff', rstDiff.status === 0
  && rstDiff.out.includes('--- a/src/main.py') && rstDiff.out.includes('+++ b/src/main.py') && rstDiff.out.includes('@@'));
ok('restore --backup keeps .bak', (function () {
  fs.writeFileSync(path.join(updDir, 'src', 'main.py'), 'changed2\n', 'utf8');
  const r = run(['--restore', bundleOut, updDir, '--backup']);
  const files = fs.readdirSync(path.join(updDir, 'src'));
  return r.status === 0 && files.some((f) => /^main\.py\.bak-\d{8}-\d{6}/.test(f))
    && read(path.join(updDir, 'src', 'main.py')) === read(path.join(PROJ, 'src', 'main.py'));
})());
ok('restore --include-pattern filters', (function () {
  const dir = path.join(OUT, 'r-only');
  const r = run(['--restore', bundleOut, dir, '--include-pattern', 'src/*']);
  return r.status === 0 && fs.existsSync(path.join(dir, 'src', 'main.py'))
    && !fs.existsSync(path.join(dir, 'README.md')) && r.out.includes('不在 --include-pattern 范围');
})());
// --max-diff 0：与 Python 一致，只输出 "and N more"，不打印 diff 主体
ok('--max-diff 0 prints no diff body', (function () {
  const dir = path.join(OUT, 'r-max0');
  run(['--restore', bundleOut, dir]);
  fs.writeFileSync(path.join(dir, 'src', 'main.py'), 'changed\n', 'utf8');
  const r = run(['--restore', bundleOut, dir, '--diff', '--max-diff', '0']);
  return r.status === 0 && !r.out.includes('@@') && !r.out.includes('--- a/')
    && /另外|more/.test(r.out);
})());
ok('--restore with --repo -> exit 2', run(['--restore', '--repo', 'https://github.com/o/r']).status === 2);
ok('second positional without --restore -> exit 2', run([PROJ, 'elsewhere']).status === 2);
ok('restore target "-" -> exit 2', run(['--restore', bundleOut, '-']).status === 2);
// --clip：不指定 -o 且输出文件不存在时不落盘，已存在则更新
function runIn(dir, args) {
  const log = path.join(LOGS, 'cwd' + (++seq) + '.txt');
  const fd = fs.openSync(log, 'w');
  const env = { ...process.env, LANG: 'zh_CN.UTF-8', LANGUAGE: 'zh_CN.UTF-8' };
  let r;
  try { r = spawnSync(process.execPath, [BIN].concat(args), { cwd: dir, env, stdio: ['ignore', fd, fd] }); }
  finally { fs.closeSync(fd); }
  return { status: r.status, out: fs.readFileSync(log, 'utf8') };
}
ok('--clip without existing output creates nothing', (function () {
  const cwd = path.join(OUT, 'clip-cwd');
  fs.mkdirSync(cwd, { recursive: true });
  const r = runIn(cwd, [PROJ, '--clip', '--no-config']);
  return r.status === 0 && r.out.includes('未创建') && !fs.existsSync(path.join(cwd, 'project_bundle.md'));
})());
ok('--clip updates an existing output file', (function () {
  const cwd = path.join(OUT, 'clip-cwd');
  fs.writeFileSync(path.join(cwd, 'project_bundle.md'), 'stale\n');
  const r = runIn(cwd, [PROJ, '--clip', '--no-config']);
  return r.status === 0 && !r.out.includes('未创建')
    && read(path.join(cwd, 'project_bundle.md')).includes('# Sample');
})());
ok('--clip with -o always creates', (function () {
  const cwd = path.join(OUT, 'clip-cwd');
  const r = runIn(cwd, [PROJ, '--clip', '--no-config', '-o', 'custom.md']);
  return r.status === 0 && fs.existsSync(path.join(cwd, 'custom.md'));
})());
// 剪贴板回退：PowerShell 失败必须抛异常，否则 clip 回退分支是死代码
// （修复前 _winClipboard 返回 false，错误地被当成「成功」，回退永不触发）
if (process.platform === 'win32') {
  const cp = require('child_process');
  const origSpawn = cp.spawnSync;
  let clipWorks = true;
  cp.spawnSync = (cmd, a, o) => {
    if (cmd === 'powershell') return { error: new Error('ENOENT'), status: null };
    if (cmd === 'clip') return clipWorks ? { error: null, status: 0 } : { error: new Error('ENOENT'), status: null };
    return origSpawn(cmd, a, o);
  };
  try {
    const clipMod = path.join(__dirname, '..', 'lib', 'clipboard.js');
    delete require.cache[require.resolve(clipMod)];
    const { copyClipboard } = require(clipMod);
    const res = copyClipboard('hello');
    ok('clipboard falls back to clip when PowerShell fails',
      res.ok === true && res.how === 'clip', JSON.stringify(res));
    clipWorks = false;
    const res2 = copyClipboard('hello');
    ok('clipboard reports failure when every backend fails', res2.ok === false, JSON.stringify(res2));
  } finally {
    cp.spawnSync = origSpawn;
  }
}
// ★ 新增：负数参数拒绝（P0-3）与逗号扩展名（P2）
ok('--max-file-lines=-5 rejected', run([PROJ, '--max-file-lines=-5', '-o', path.join(OUT, 'neg1.md')]).status === 2);
ok('--max-file-kb=-3 rejected', run([PROJ, '--max-file-kb=-3', '-o', path.join(OUT, 'neg2.md')]).status === 2);
ok('--split-tokens=-1 rejected', run([PROJ, '--split-tokens=-1', '-o', path.join(OUT, 'neg3.md')]).status === 2);
ok('--only-ext accepts comma form', (function () {
  const o = path.join(OUT, 'csv.md');
  run([PROJ, '-o', o, '--only-ext=py,md']);
  const f = bundled(read(o));
  return f.includes('src/main.py') && !f.includes('src/util.js');
})());

(async function asyncChecks() {
  ok('CONNECT tunnel established', await withFakeProxy(
    (req) => (/^CONNECT api\.github\.com:443 /.test(req) ? 'HTTP/1.1 200 Connection established\r\n\r\n' : 'HTTP/1.1 400 Bad\r\n\r\n'),
    async (port) => {
      const sock = await remote.proxyTunnel({ host: '127.0.0.1', port }, 'api.github.com', 443);
      const shape = sock && typeof sock.destroy === 'function';
      sock.destroy();
      return shape;
    }
  ));
  // 统计口径：emoji 等增补平面字符按 1 个码点计，与 Python len(str) 对齐
ok('cpLen counts code points', require(path.join(__dirname, '..', 'lib', 'util.js')).cpLen('a😀b') === 3);
  ok('CONNECT failure rejects', await withFakeProxy(
    () => 'HTTP/1.1 403 Forbidden\r\n\r\n',
    async (port) => {
      try { await remote.proxyTunnel({ host: '127.0.0.1', port }, 'api.github.com', 443); return false; }
      catch (e) { return /CONNECT failed with HTTP 403/.test(e.message); }
    }
  ));
  // 响应头与后续字节同处一个 chunk：剩余字节必须回推，不能被丢掉
  ok('CONNECT keeps bytes after headers', await withStickyProxy(async (port, want) => {
    const sock = await remote.proxyTunnel({ host: '127.0.0.1', port }, 'api.github.com', 443);
    return await new Promise((resolve) => {
      const timer = setTimeout(() => { sock.destroy(); resolve(false); }, 3000);
      sock.once('data', (buf) => {
        clearTimeout(timer);
        const got = buf.toString('latin1');
        sock.destroy();
        resolve(got === want);
      });
      sock.resume();
    });
  }));

  // ── 收尾 ──
  process.stdout.write('\n' + pass + ' passed, ' + failures.length + ' failed\n');
  if (failures.length) {
    process.stdout.write('failed: ' + failures.join(', ') + '\n');
    process.exitCode = 1;
  } else {
    fs.rmSync(TMP, { recursive: true, force: true });
  }
})();
