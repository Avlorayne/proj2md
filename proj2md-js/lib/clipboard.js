'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
/**
 * 用 PowerShell 写剪贴板。
 * spawnSync 的 error / 非零 status 都必须抛出异常，否则外层 catch 永远不会触发，
 * Windows 上的 clip 回退分支就成了死代码（与 Python 版 check=True 的行为对齐）。
 */
function _winClipboard(text) {
  const tmp = path.join(os.tmpdir(), 'proj2md_clip_' + process.pid + '.txt');
  try {
    fs.writeFileSync(tmp, '\ufeff' + text, 'utf8'); // BOM 便于 PowerShell 按 UTF-8 读取
    const ps = "$t = Get-Content -LiteralPath '" + tmp.replace(/'/g, "''") +
      "' -Raw -Encoding UTF8; Set-Clipboard -Value $t";
    const r = spawnSync('powershell', ['-NoProfile', '-Command', ps], { timeout: 60000 });
    if (r.error) throw r.error;
    if (r.status !== 0) throw new Error('powershell exited with code ' + r.status);
    return true;
  } finally {
    try { fs.unlinkSync(tmp); } catch (e) { /* ignore */ }
  }
}
/** 返回 { ok, how }；依次尝试各平台原生命令，无需任何第三方依赖。 */
function copyClipboard(text) {
  try {
    if (process.platform === 'win32') {
      try {
        _winClipboard(text);
        return { ok: true, how: 'PowerShell' };
      } catch (e) {
        // PowerShell 不可用 / 超时 / Set-Clipboard 失败 → 回退 clip
        const r = spawnSync('clip', { input: Buffer.from(text, 'utf16le') });
        if (!r.error && r.status === 0) return { ok: true, how: 'clip' };
      }
    } else if (process.platform === 'darwin') {
      const r = spawnSync('pbcopy', { input: Buffer.from(text, 'utf8') });
      if (!r.error && r.status === 0) return { ok: true, how: 'pbcopy' };
    } else {
      for (const cmd of [['wl-copy'], ['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']]) {
        try {
          const r = spawnSync(cmd[0], cmd.slice(1), { input: Buffer.from(text, 'utf8') });
          if (!r.error && r.status === 0) return { ok: true, how: cmd[0] };
        } catch (e) { /* try next */ }
      }
    }
  } catch (e) { /* ignore */ }
  return { ok: false, how: '' };
}
module.exports = { copyClipboard };
