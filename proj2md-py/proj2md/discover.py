"""proj2md 文件发现、编码识别读取与记录构建。"""
from __future__ import annotations
import fnmatch
import os
from pathlib import Path

from .config import Config, FileRec
from .defaults import CONFIG_MANIFESTS, DEFAULT_FILENAMES, ENTRY_EXTS, ENTRY_STEMS
from .i18n import t
from .util import fmt_size, lang_of

# ─────────────────────────── 文件发现与读取 ───────────────────────────
def _match_any(rel_posix: str, name_l: str, patterns) -> bool:
    for pat in patterns:
        pat_l = str(pat).lower()
        if fnmatch.fnmatch(name_l, pat_l) or fnmatch.fnmatch(rel_posix, pat_l):
            return True
    return False
def _dir_may_be_included(dir_rel: str, patterns) -> bool:
    """判断某个目录是否可能被 --include-pattern 覆盖（用于让强制包含
    穿透「隐藏目录忽略」）。取每个 pattern 第一个 * 之前的字面前缀：
      - 前缀为空（如 "*"、"*.md"）→ 可能覆盖一切目录 → True
      - 目录路径以前缀开头（如 ".github" vs ".github/*"）→ True
      - 前缀以「目录/」开头（目录是 pattern 覆盖范围的祖先）→ True
    宁可放宽（多遍历再逐文件判断），不可误剪。"""
    for pat in patterns:
        prefix = str(pat).lower().split("*")[0]
        if not prefix:
            return True
        if dir_rel.lower().startswith(prefix):
            return True
        if prefix.startswith(dir_rel.lower() + "/"):
            return True
    return False
_JUNCTION_TAG = 0xA0000003   # IO_REPARSE_TAG_MOUNT_POINT（Windows 目录 junction）
def _is_dir_link(path: Path) -> bool:
    """目录形式的链接：Unix/Windows 符号链接，以及 Windows junction。

    Node 侧 fs.Dirent.isSymbolicLink() 对 junction 同样返回 true，这里保持一致。
    跟随这类目录会让同一棵子树被收录两遍（junction 还能指回祖先目录，
    使遍历无限递归），所以两端都直接跳过、不递归。"""
    try:
        if os.path.islink(path):
            return True
        return getattr(os.lstat(path), "st_reparse_tag", 0) == _JUNCTION_TAG
    except OSError:
        return False
def _dir_excluded(name_l: str, patterns) -> bool:
    """目录黑名单匹配：大小写不敏感，支持 * / ? 通配（如 *.egg-info）。"""
    for pat in patterns:
        pat_l = str(pat).lower()
        if name_l == pat_l or fnmatch.fnmatchcase(name_l, pat_l):
            return True
    return False
def discover(cfg: Config):
    """遍历项目收集候选文件。返回。
    目录剪枝顺序：include-pattern 覆盖 > 隐藏目录忽略 > 目录黑名单。"""
    root = cfg.root
    out_abs = cfg.output.expanduser().resolve()
    cfg_abs = cfg.config_path.resolve() if cfg.config_path else None
    # 与 Node 版对齐：排除 discover / cli / __main__ 三份自身驱动源文件，
    # 否则把包目录当项目跑（回归验证的常见做法）时会把自己的源码拼进合集。
    # 用包目录下的固定文件名而非 sys.modules：结果确定，且绝不会误伤用户自己的模块。
    pkg_dir = Path(__file__).resolve().parent
    self_abs = {
        Path(__file__).resolve(),
        pkg_dir / "cli.py",
        pkg_dir / "__main__.py",
    }
    found, pruned_hidden = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        kept = []
        for d in sorted(dirnames):
            rel_dir = (Path(dirpath) / d).relative_to(root).as_posix()
            # 目录链接（符号链接 / junction）一律不递归，且不受 include-pattern 影响：
            # 对应 Node 侧在 readdir 阶段就把它排除出 dirs，两端行为需一致。
            if _is_dir_link(Path(dirpath) / d):
                continue
            # 强制包含规则优先：可能被 include-pattern 覆盖的目录一律不剪
            if _dir_may_be_included(rel_dir, cfg.include_patterns):
                kept.append(d)
                continue
            # 隐藏目录：以 . 开头且开启忽略 → 整目录剪掉
            if cfg.exclude_hidden and d.startswith("."):
                pruned_hidden.append(rel_dir)
                continue
            # 目录黑名单（支持 *.egg-info 这类通配目录名）
            if _dir_excluded(d.lower(), cfg.exclude_dirs):
                continue
            kept.append(d)
        dirnames[:] = kept
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = p.relative_to(root)
            rel_posix = rel.as_posix()
            name_l = fn.lower()
            try:
                pa = p.resolve()
            except OSError:
                pa = p
            if pa in self_abs or pa == out_abs or (cfg_abs and pa == cfg_abs):
                continue
            included_override = _match_any(rel_posix, name_l, cfg.include_patterns)
            if name_l in cfg.exclude_files and not included_override:
                continue
            if _match_any(rel_posix, name_l, cfg.exclude_patterns) and not included_override:
                continue
            ext = p.suffix.lower().lstrip(".")
            if not (cfg.any_text or ext in cfg.exts or name_l in DEFAULT_FILENAMES):
                if not included_override:
                    continue
            found.append((p, rel))
    return found, pruned_hidden
def read_text(p: Path):
    """自动识别编码读取文本；返回。二进制返回。"""
    try:
        raw = p.read_bytes()
    except OSError as e:
        return None, None, t("read_fail", cls=e.__class__.__name__)
    if b"\x00" in raw:
        return None, None, t("looks_binary")
    for enc in ("utf-8-sig", "utf-8", "gbk", "big5", "latin-1"):
        try:
            return raw.decode(enc), enc, None
        except (UnicodeDecodeError, LookupError):
            continue
    return None, None, t("undecodable")
def file_priority(p: Path) -> int:
    name_l = p.name.lower()
    if name_l.startswith("readme"):
        return 0
    if name_l in CONFIG_MANIFESTS or name_l in (".gitignore", ".dockerignore", ".editorconfig"):
        return 1
    if p.stem.lower() in ENTRY_STEMS and p.suffix.lower() in ENTRY_EXTS:
        return 2
    if p.stem.lower() in ("config", "settings"):
        return 2
    return 3
def order_key(item):
    p, rel = item
    return (file_priority(p), rel.as_posix().lower())
def build_records(cfg: Config, candidates):
    records, skipped = [], []
    total = 0  # ★ 修复（P0-1）：预算按 UTF-8 字节计，与 --max-file-kb 的字节口径一致
               #   （原按字符数计，中文项目实际产物体积可达预算的 ~3 倍）
    budget = int(cfg.max_total_kb * 1024) if cfg.max_total_kb else 0
    for p, rel in candidates:
        try:
            size = p.stat().st_size
        except OSError as e:
            skipped.append((rel.as_posix(), t("skip_unreadable", cls=e.__class__.__name__)))
            continue
        if cfg.max_file_kb and size > cfg.max_file_kb * 1024:
            skipped.append((rel.as_posix(),
                            t("skip_too_large", kb=cfg.max_file_kb, size=fmt_size(size))))
            continue
        text, enc, err = read_text(p)
        if text is None:
            skipped.append((rel.as_posix(), t("skip_read_err", err=err)))
            continue
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.endswith("\n"):
            text += "\n"
        orig_lines = len(text.splitlines())
        truncated = False
        if cfg.max_file_lines and orig_lines > cfg.max_file_lines:
            keep = cfg.max_file_lines
            text = "\n".join(text.split("\n")[:keep])
            if not text.endswith("\n"):
                text += "\n"
            text += t("truncated_note", orig=orig_lines, keep=keep)
            truncated = True
        if not text.strip():
            text = t("empty_file")
        nb = len(text.encode("utf-8"))  # ★ 按最终写入正文的字节数计（截断/换行归一之后）
        if budget and records and total + nb > budget:
            skipped.append((rel.as_posix(), t("skip_over_budget")))
            continue
        records.append(FileRec(
            rel=rel, abspath=p, language=lang_of(p), encoding=enc,
            content=text, lines=len(text.splitlines()), chars=len(text),
            nbytes=size, truncated=truncated, orig_lines=orig_lines,
        ))
        total += nb
    return records, skipped
