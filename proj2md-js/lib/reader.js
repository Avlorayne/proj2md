'use strict';
const fs = require('fs');
const { t } = require('./i18n.js');
// 可选依赖：提供 GBK/Big5 解码；未安装时自动降级为 latin-1
let iconv = null;
try { iconv = require('iconv-lite'); } catch (e) { /* optional */ }
/**
 * 自动识别编码读取文本文件。
 * 返回 { text, enc, err }；二进制/读取失败时 text 为 null。
 * 编码链与 Python 版一致：utf-8-sig → utf-8 → gbk → big5 → latin-1。
 */
function readText(absPath) {
  let raw;
  try { raw = fs.readFileSync(absPath); }
  catch (e) { return { text: null, enc: null, err: t('read_fail', { cls: e.code || (e && e.constructor.name) || 'Error' }) }; }
  if (raw.includes(0)) return { text: null, enc: null, err: t('looks_binary') };
  // utf-8 / utf-8-sig（TextDecoder 默认吞掉 BOM；fatal:true 保证严格校验）
  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
    const hadBom = raw[0] === 0xef && raw[1] === 0xbb && raw[2] === 0xbf;
    return { text, enc: hadBom ? 'utf-8-sig' : 'utf-8', err: null };
  } catch (e) { /* fall through */ }
  // gbk / big5（需要 iconv-lite；round-trip 校验避免误判）
  for (const enc of ['gbk', 'big5']) {
    if (iconv && iconv.encodingExists(enc)) {
      const text = iconv.decode(raw, enc);
      if (iconv.encode(text, enc).equals(raw)) return { text, enc, err: null };
    }
  }
  // latin-1 永不失败（与 Python 行为一致）
  return { text: raw.toString('latin1'), enc: 'latin-1', err: null };
}
module.exports = { readText };

