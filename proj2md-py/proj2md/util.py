"""proj2md 通用小工具：安全打印、体积 / Token 估算、语言名与 Markdown 辅助函数。"""
from __future__ import annotations
import re

from .defaults import CJK_RE, FENCE_LANG_BY_EXT, FENCE_LANG_BY_NAME, LANGUAGE_BY_EXT, LANGUAGE_BY_NAME
from .i18n import t

_ASCII_FALLBACK = str.maketrans({
    "═": "=", "─": "-", "├": "|", "└": "`", "│": "|",
    "▶": ">", "✔": "[OK]", "⚠": "[!]", "❌": "[X]", "★": "*",
    "…": "...", "·": "-",
    "✅": "[OK]", "⚠": "[!]", "️": "",
    "（": "(", "）": ")", "「": '"', "」": '"',
})

# ─────────────────────────── 小工具 ───────────────────────────
def cprint(*args, **kw):
    """安全打印：终端编码不支持中文符号时自动降级为 ASCII。"""
    s = " ".join(str(a) for a in args)
    try:
        print(s, **kw)
    except UnicodeEncodeError:
        print(s.translate(_ASCII_FALLBACK), **kw)
def normalize_ext(e: str) -> str:
    return str(e).strip().lower().lstrip(".")
def fmt_size(n) -> str:
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} GB"
def estimate_tokens(text: str) -> int:
    """粗略估算 token：中文按 ~1.1 token/字，其他按 ~3.8 字符/token。"""
    cjk = len(CJK_RE.findall(text))
    return int(cjk * 1.1 + (len(text) - cjk) / 3.8)
def token_hint(tok: int) -> str:
    if tok < 30_000:
        return t("hint_moderate")
    if tok < 100_000:
        return t("hint_long")
    if tok < 200_000:
        return t("hint_very_long")
    return t("hint_too_long")
def lang_of(p: Path) -> str:
    name_l = p.name.lower()
    if name_l in LANGUAGE_BY_NAME:
        return LANGUAGE_BY_NAME[name_l]
    ext = p.suffix.lower().lstrip(".")
    if ext in LANGUAGE_BY_EXT:
        return LANGUAGE_BY_EXT[ext]
    return ext.upper() if ext else "Text"
# ─────────────────────────── Markdown 辅助 ───────────────────────────
def fence_for(content: str) -> str:
    """计算安全的围栏长度：比正文中最长的反引号串多 1 个，
    这样即使源码里含有 ``` 代码块也不会截断外层围栏。"""
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)
def fence_lang_of(p: Path) -> str:
    """返回代码围栏的语言标识（用于语法高亮）。"""
    name_l = p.name.lower()
    if name_l in FENCE_LANG_BY_NAME:
        return FENCE_LANG_BY_NAME[name_l]
    ext = p.suffix.lower().lstrip(".")
    return FENCE_LANG_BY_EXT.get(ext, ext)
def md_slug(text: str) -> str:
    """GitHub 风格标题锚点：小写、去标点、空格转连字符（保留中文/字母/数字/连字符）。"""
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")
def md_code_span(s: str) -> str:
    """生成行内代码；含反引号时退化为纯文本。"""
    return f"`{s}`" if "`" not in s else s
def md_table_cell(s: str) -> str:
    """表格单元格里的行内代码：竖线必须转义（表格内代码span也不例外）。"""
    if "`" in s:
        return s.replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")
    esc = s.replace("|", "\\|")
    return f"`{esc}`"
