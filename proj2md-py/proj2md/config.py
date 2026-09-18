"""proj2md 数据模型与配置合成（CLI 参数 > proj2md.json > 默认值）。"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from .defaults import (
    DEFAULT_EXCLUDE_DIRS, DEFAULT_EXCLUDE_FILES, DEFAULT_EXCLUDE_PATTERNS, DEFAULT_EXTS,
    DEFAULT_OUTPUT,
)
from .util import normalize_ext

# ─────────────────────────── 数据结构 ───────────────────────────
@dataclass
class FileRec:
    rel: Path
    abspath: Path
    language: str = ""
    encoding: str = ""
    content: str = ""
    lines: int = 0
    chars: int = 0
    nbytes: int = 0
    truncated: bool = False
    orig_lines: int = 0
@dataclass
class Config:
    root: Path
    output: Path
    exts: set
    any_text: bool
    exclude_hidden: bool          # 是否忽略以 . 开头的文件夹（默认 True）
    exclude_dirs: set
    exclude_files: set
    exclude_patterns: list
    include_patterns: list
    line_numbers: bool
    max_file_lines: int
    max_file_kb: float
    max_total_kb: float
    split_tokens: int
    show_tree: bool
    show_index: bool
    ai_header: bool
    smart_order: bool
    clip: bool
    config_path: Path

def _expand_csv(vals) -> list[str]:
    """★ 修复（P2）：允许 --ext py,md / --ext=py,md 这类逗号写法（与空格分隔等价）。"""
    out: list[str] = []
    for v in vals or []:
        out += [s for s in str(v).split(",") if s.strip()]
    return out


def build_config(root: Path, args, data: dict, cfg_path) -> Config:
    def v(key, cli, default):
        if cli is not None:
            return cli
        if key in data and data[key] is not None:
            return data[key]
        return default
    def flag(key, no_cli, default):
        if no_cli:
            return False
        return bool(data.get(key, default))
    def pos_flag(key, cli):
        return bool(cli) or bool(data.get(key, False))
    exts = set(DEFAULT_EXTS)
    cfg_exts = data.get("exts")
    if isinstance(cfg_exts, list) and cfg_exts:
        exts = {normalize_ext(e) for e in cfg_exts}
    if args.only_ext:
        exts = {normalize_ext(e) for e in _expand_csv(args.only_ext)}  # ★
    elif args.ext:
        exts |= {normalize_ext(e) for e in _expand_csv(args.ext)}      # ★
    def merge_set(defaults, key, cli_val):
        s = set(defaults)
        cv = data.get(key)
        if isinstance(cv, list):
            s |= {str(x).lower() for x in cv}
        if cli_val:
            s |= {str(x).lower() for x in cli_val}
        return s
    def merge_list(defaults, key, cli_val):
        out = list(defaults)
        cv = data.get(key)
        if isinstance(cv, list):
            out += [str(x) for x in cv]
        if cli_val:
            out += [str(x) for x in cli_val]
        return out
    # 隐藏目录忽略：默认 True；命令行 --include-hidden 或配置 exclude_hidden=false 可关闭
    exclude_hidden = True
    if args.include_hidden:
        exclude_hidden = False
    elif "exclude_hidden" in data and data["exclude_hidden"] is not None:
        exclude_hidden = bool(data["exclude_hidden"])
    return Config(
        root=root,
        output=Path(v("output", args.output, DEFAULT_OUTPUT)),
        exts=exts,
        any_text=pos_flag("any_text", args.any_text),
        exclude_hidden=exclude_hidden,
        exclude_dirs=merge_set(DEFAULT_EXCLUDE_DIRS, "exclude_dirs", args.exclude_dir),
        exclude_files=merge_set(DEFAULT_EXCLUDE_FILES, "exclude_files", args.exclude_file),
        exclude_patterns=merge_list(DEFAULT_EXCLUDE_PATTERNS, "exclude_patterns", args.exclude_pattern),
        include_patterns=merge_list([], "include_patterns", args.include_pattern),
        line_numbers=pos_flag("line_numbers", args.line_numbers),
        max_file_lines=int(v("max_file_lines", args.max_file_lines, 0) or 0),
        max_file_kb=float(v("max_file_kb", args.max_file_kb, 512) or 0),
        max_total_kb=float(v("max_total_kb", args.max_total_kb, 0) or 0),
        split_tokens=int(v("split_tokens", args.split_tokens, 0) or 0),
        show_tree=flag("show_tree", args.no_tree, True),
        show_index=flag("show_index", args.no_index, True),
        ai_header=flag("ai_header", args.no_ai_header, True),
        smart_order=flag("smart_order", args.no_smart_order, True),
        clip=pos_flag("clip", args.clip),
        config_path=cfg_path,
    )
