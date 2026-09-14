'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
function _winClipboard(text) {
  const tmp = path.join(os.tmpdir(), 'proj2md_clip_' + process.pid + '.txt');
  try {
    fs.writeFileSync(tmp, '\ufeff' + text, 'utf8'); // BOM 便于 PowerShell 按 UTF-8 读取
    const ps = "$t = Get-Content -LiteralPath '" + tmp.replace(/'/g, "''") +
      "' -Raw -Encoding UTF8; Set-Clipboard -Value $t";
    const r = spawnSync('powershell', ['-NoProfile', '-Command', ps], { timeout: 60000 });
    return r.status === 0;
  } finally {
    try { fs.unlinkSync(tmp); } catch (e) { /* ignore */ }
  }
}
/** 返回 { ok, how }；依次尝试各平台原生命令，无需任何第三方依赖。 */
function copyClipboard(text) {
  try {
    if (process.platform === 'win32') {
      try { if (_winClipboard(text)) return { ok: true, how: 'PowerShell' }; }
      catch (e) {
        const r = spawnSync('clip', { input: Buffer.from(text, 'utf16le') });
        if (!r.error && r.status === 0) return { ok: true, how: 'clip' };
      }
    } else if (process.platform === 'darwin') {
      const r = spawnSync('pbcopy', { input: Buffer.from(text, 'utf8') });
      if (!r.error && r.status === 0) return { ok: true, how: 'pbcopy' };
    } else {
      for (const cmd of [['wl-copy'], ['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']]) {
        try {
          const r = spawnSync(cmd[0], { input: Buffer.from(text, 'utf8') });
          if (!r.error && r.status === 0) return { ok: true, how: cmd[0] };
        } catch (e) { /* try next */ }
      }
    }
  } catch (e) { /* ignore */ }
  return { ok: false, how: '' };
}
module.exports = { copyClipboard };

