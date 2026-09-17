'use strict';

// Download a repository snapshot without creating a Git working copy. GitHub
// provides a reliable tarball endpoint; other servers may support upload-archive.
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');
const https = require('https');
const tls = require('tls');
const { spawnSync } = require('child_process');
const zlib = require('zlib');

function removeTree(p) {
  if (fs.rmSync) fs.rmSync(p, { recursive: true, force: true });
  else fs.rmdirSync(p, { recursive: true }); // Node 14.0 compatibility
}

function githubRepo(value) {
  const clean = String(value).trim().replace(/[?#].*$/, '').replace(/\/$/, '');
  const m = clean.match(/^(?:(?:https?|ssh):\/\/(?:[^@/]+@)?|[^@/:]+@)?(?:www\.)?github\.com[\/:]([^\s/:]+)\/([^\s/]+)$/i);
  if (!m) return null;
  const owner = m[1], repo = m[2].endsWith('.git') ? m[2].slice(0, -4) : m[2];
  return owner && repo ? { owner, repo } : null;
}

// ── 代理 ──
// Node 的 https 不会读取系统代理，而 Python 的 urllib 会。缺少这层支持时，
// 同一台开了代理的机器上 Python 版能下载、Node 版只会超时，两端行为就不一致了。
function matchNoProxy(entry, host) {
  const item = entry.trim().toLowerCase();
  if (!item) return false;
  if (item === '*') return true;
  const bare = item.split(':')[0].replace(/^\./, '');
  return host === bare || host.endsWith('.' + bare);
}
function parseProxy(value, noProxy) {
  if (!value) return null;
  const entries = String(noProxy || '').split(/[,;]/).filter(Boolean);
  // "http=host:port;https=host:port" 形式
  let raw = String(value).trim();
  if (raw.includes('=')) {
    const map = {};
    raw.split(/[;,]/).forEach((part) => {
      const i = part.indexOf('=');
      if (i > 0) map[part.slice(0, i).trim().toLowerCase()] = part.slice(i + 1).trim();
    });
    raw = map.https || map.http || map.socks || '';
  }
  if (!raw) return null;
  let u;
  try { u = new URL(raw.includes('://') ? raw : 'http://' + raw); } catch (e) { return null; }
  if (!u.hostname) return null;
  return { host: u.hostname, port: Number(u.port) || 80, noProxy: entries };
}
function envProxy(env, host) {
  const raw = env.HTTPS_PROXY || env.https_proxy || env.HTTP_PROXY || env.http_proxy ||
    env.ALL_PROXY || env.all_proxy;
  const proxy = parseProxy(raw, env.NO_PROXY || env.no_proxy);
  if (!proxy || proxy.noProxy.some((e) => matchNoProxy(e, host))) return null;
  return proxy;
}
function registryProxy(host) {
  if (process.platform !== 'win32') return null;
  let out;
  try {
    out = spawnSync('reg', ['query',
      'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'],
      { encoding: 'utf8' });
  } catch (e) { return null; }
  if (!out || out.status !== 0 || !out.stdout) return null;
  const val = (name) => {
    const m = out.stdout.match(new RegExp('^\\s*' + name + '\\s+REG_\\w+\\s+(.+)$', 'mi'));
    return m ? m[1].trim() : '';
  };
  if (val('ProxyEnable') !== '0x1') return null;
  const proxy = parseProxy(val('ProxyServer'), val('ProxyOverride'));
  if (!proxy || proxy.noProxy.some((e) => matchNoProxy(e, host))) return null;
  return proxy;
}
function detectProxy(host) {
  return envProxy(process.env, host) || registryProxy(host);
}
/** 通过 HTTP 代理建立到目标主机的 CONNECT 隧道，返回明文 socket。 */
function proxyTunnel(proxy, host, port) {
  return new Promise((resolve, reject) => {
    const socket = net.connect(proxy.port, proxy.host);
    const fail = (err) => { socket.destroy(); reject(err); };
    socket.setTimeout(60000, () => fail(new Error('proxy connect timed out')));
    socket.on('error', fail);
    socket.on('connect', () => {
      socket.write(`CONNECT ${host}:${port} HTTP/1.1\r\nHost: ${host}:${port}\r\n\r\n`);
    });
    let buf = '';
    const onData = (chunk) => {
      buf += chunk.toString('latin1');
      if (!buf.includes('\r\n\r\n')) {
        if (buf.length > 8192) fail(new Error('proxy returned a malformed response'));
        return;
      }
      socket.removeListener('data', onData);
      socket.setTimeout(0);
      const status = Number((buf.match(/^HTTP\/1\.[01] (\d+)/) || [])[1]);
      if (status !== 200) { fail(new Error('proxy CONNECT failed with HTTP ' + (status || '?'))); return; }
      resolve(socket);
    };
    socket.on('data', onData);
  });
}
async function get(url, headers, redirects) {
  redirects = redirects || 0;
  if (redirects > 5) throw new Error('too many HTTP redirects');
  const target = new URL(url);
  const proxy = detectProxy(target.hostname);
  let tunnel = null;
  if (proxy) {
    tunnel = await proxyTunnel(proxy, target.hostname, Number(target.port) || 443);
    tunnel = tls.connect({ socket: tunnel, servername: target.hostname });
    await new Promise((resolve, reject) => {
      tunnel.once('secureConnect', resolve);
      tunnel.once('error', reject);
    });
  }
  return new Promise((resolve, reject) => {
    const opts = { headers, agent: false };
    if (tunnel) opts.createConnection = () => tunnel;
    const req = https.get(url, opts, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        if (tunnel) tunnel.destroy(); // 新主机要重新探测代理并另开隧道
        resolve(get(new URL(res.headers.location, url).toString(), headers, redirects + 1));
        return;
      }
      if (res.statusCode < 200 || res.statusCode >= 300) {
        res.resume(); reject(new Error('HTTP ' + res.statusCode)); return;
      }
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => resolve(Buffer.concat(chunks)));
      res.on('error', reject);
    });
    req.setTimeout(60000, () => req.destroy(new Error('request timed out')));
    req.on('error', reject);
  });
}

function octal(buf) {
  const s = buf.toString('ascii').replace(/\0.*$/, '').trim();
  return s ? parseInt(s, 8) : 0;
}
function safeParts(name) {
  const parts = String(name).replace(/\\/g, '/').split('/').filter(Boolean);
  if (!parts.length || parts.some((p) => p === '.' || p === '..')) return null;
  // 盘符条目（"C:/x"）在 Python 版会逃出临时目录，这里同样拒收，保持两端一致
  if (/^[A-Za-z]:$/.test(parts[0])) return null;
  return parts;
}
function tarEntries(payload) {
  let data = payload;
  if (data[0] === 0x1f && data[1] === 0x8b) data = zlib.gunzipSync(data);
  const out = [];
  for (let off = 0; off + 512 <= data.length;) {
    const hdr = data.subarray(off, off + 512);
    if (hdr.every((b) => b === 0)) break;
    const name = hdr.subarray(0, 100).toString('utf8').replace(/\0.*$/, '');
    const prefix = hdr.subarray(345, 500).toString('utf8').replace(/\0.*$/, '');
    const full = prefix ? prefix + '/' + name : name;
    const size = octal(hdr.subarray(124, 136));
    const type = String.fromCharCode(hdr[156] || 48);
    const body = data.subarray(off + 512, off + 512 + size);
    if (type === '0' || type === '\0' || type === '5') out.push({ parts: safeParts(full), type, body });
    off += 512 + Math.ceil(size / 512) * 512;
  }
  return out.filter((entry) => entry.parts);
}
function extractTar(payload, destination) {
  const entries = tarEntries(payload);
  if (!entries.length) throw new Error('remote archive contains no files');
  const files = entries.filter((e) => e.type !== '5');
  const first = new Set(files.filter((e) => e.parts.length > 1).map((e) => e.parts[0]));
  const stripTop = files.length && first.size === 1 && files.every((e) => e.parts.length > 1) ? [...first][0] : null;
  for (const entry of entries) {
    if (stripTop && entry.parts.length === 1) continue;
    const rel = stripTop ? entry.parts.slice(1) : entry.parts;
    const target = path.join(destination, ...rel);
    if (entry.type === '5') fs.mkdirSync(target, { recursive: true });
    else {
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, entry.body);
    }
  }
  return destination;
}

async function fetchRemoteRepo(url, ref) {
  ref = ref || 'HEAD';
  const parsed = githubRepo(url);
  let payload, label;
  if (parsed) {
    const headers = { 'User-Agent': 'proj2md', Accept: 'application/vnd.github+json' };
    const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
    if (token) headers.Authorization = 'Bearer ' + token;
    const endpoint = 'https://api.github.com/repos/' + encodeURIComponent(parsed.owner) + '/' +
      encodeURIComponent(parsed.repo) + '/tarball/' + encodeURIComponent(ref);
    payload = await get(endpoint, headers);
    label = parsed.owner + '/' + parsed.repo + '@' + ref;
  } else {
    const result = spawnSync('git', ['archive', '--format=tar', '--remote=' + url, ref], { encoding: null });
    if (result.error) throw result.error;
    if (result.status !== 0) throw new Error((result.stderr || Buffer.from('git archive failed')).toString('utf8').trim());
    payload = result.stdout;
    const base = path.basename(String(url).replace(/\/$/, '')).replace(/\.git$/, '');
    label = base + '@' + ref;
  }
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'proj2md-'));
  try { return { root: extractTar(payload, tmp), label, tmp }; }
  catch (e) { removeTree(tmp); throw e; }
}

// 内部函数一并导出，供测试直接做离线校验
module.exports = {
  fetchRemoteRepo, removeTree, githubRepo, tarEntries, extractTar,
  parseProxy, matchNoProxy, envProxy, proxyTunnel, detectProxy,
};
