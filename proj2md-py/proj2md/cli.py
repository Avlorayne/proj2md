"""proj2md 命令行入口与主流程。"""
from __future__ import annotations
import argparse
import json
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

from .clipboard import copy_clipboard
from .config import build_config
from .defaults import CONFIG_FILENAME, CONFIG_TEMPLATE, DEFAULT_OUTPUT, TOOL, VERSION
from .discover import build_records, discover, order_key
from .i18n import SUPPORTED_LANGS, set_lang, t
from .remote import fetch_remote_repo
from .render import build_tree, render
from .restore import run_restore
from .util import cprint, estimate_tokens, fmt_size, token_hint

# ─────────────────────────── 报告输出 ───────────────────────────
def print_summary(out_path: Path, records, skipped, text: str, pruned_hidden=None):
    tot_lines = sum(r.lines for r in records)
    tot_tokens = sum(estimate_tokens(r.content) for r in records)
    size = len(text.encode("utf-8"))
    pruned_hidden = pruned_hidden or []
    cprint()
    cprint(t("sum_generated", path=out_path))
    if skipped:
        cprint(t("sum_files_skipped", n=len(records), skipped=len(skipped)))
    else:
        cprint(t("sum_files", n=len(records)))
    if pruned_hidden:
        cprint(t("sum_hidden", n=len(pruned_hidden)))
    cprint(t("sum_lines", lines=f"{tot_lines:,}"))
    cprint(t("sum_size", size=fmt_size(size)))
    cprint(t("sum_tokens", tokens=f"{tot_tokens:,}", hint=token_hint(tot_tokens)))
    cprint()
    cprint(t("sum_tip1"))
    cprint(t("sum_tip2"))
def dry_run_report(cfg: Config, records, skipped, pruned_hidden=None, root_name=None):
    tot = sum(estimate_tokens(r.content) for r in records)
    pruned_hidden = pruned_hidden or []
    cprint(t("dry_preview", n=len(records),
             lines=f"{sum(r.lines for r in records):,}", tokens=f"{tot:,}"))
    if cfg.show_tree:
        cprint()
        cprint(build_tree(records, root_name or cfg.root.name).rstrip("\n"))
        cprint()
    for i, r in enumerate(records, 1):
        flag = t("dry_truncated_flag") if r.truncated else ""
        cprint(t("dry_file_item", i=f"{i:>3}", path=r.rel.as_posix(),
                 lang=r.language, lines=r.lines, size=fmt_size(r.nbytes), flag=flag))
    if skipped:
        cprint(t("dry_skipped_head", n=len(skipped)))
        for rel, reason in skipped[:20]:
            cprint(t("dry_skip_item", rel=rel, reason=reason))
        if len(skipped) > 20:
            cprint(t("dry_more", n=len(skipped) - 20))
    if pruned_hidden:
        cprint(t("dry_hidden_head", n=len(pruned_hidden)))
        for d in pruned_hidden[:20]:
            cprint(f" - {d}/")
        if len(pruned_hidden) > 20:
            cprint(t("dry_more", n=len(pruned_hidden) - 20))
    cprint(t("dry_tokens", tokens=f"{tot:,}", hint=token_hint(tot)))
    cprint(t("dry_dryrun"))

# ─────────────────────────── CLI ───────────────────────────
def _nonneg_int(s: str) -> int:
    """★ argparse type：非负整数。修复（P0-3）：此前 --max-file-lines -5 会被
    静默接受，导致「从末尾截断」并生成「仅保留前 -5 行」的荒谬提示。"""
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: '{s}'")
    if v < 0:
        raise argparse.ArgumentTypeError(f"value must be >= 0: '{s}'")
    return v
def _nonneg_float(s: str) -> float:
    """★ argparse type：非负浮点数（--max-file-kb / --max-total-kb）。"""
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid float value: '{s}'")
    if v < 0:
        raise argparse.ArgumentTypeError(f"value must be >= 0: '{s}'")
    return v
def parse_args(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # 预扫描 --lang/--language：让 --help 也按所选语言渲染
    pre = None
    for i, a in enumerate(argv):
        if a in ("--lang", "--language") and i + 1 < len(argv):
            pre = argv[i + 1]
        elif a.startswith("--lang=") or a.startswith("--language="):
            pre = a.split("=", 1)[1]
    set_lang(pre)   # None → 按系统探测
    p = argparse.ArgumentParser(
        description=t("cli_desc"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=t("cli_epilog"),
        add_help=False)   # 关闭 argparse 自动注册的 -h/--help，改为下方显式声明
    p.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS,
                   help=t("arg_help"))
    p.add_argument("root", nargs="?", default=None, help=t("arg_root"))
    p.add_argument("--repo", default=None, metavar="URL", help=t("arg_repo"))
    p.add_argument("--ref", default=None, metavar="REF", help=t("arg_ref"))
    p.add_argument("-o", "--output", default=None, help=t("arg_output", out=DEFAULT_OUTPUT))
    p.add_argument("--ext", nargs="+", metavar="EXT", help=t("arg_ext"))
    p.add_argument("--only-ext", nargs="+", metavar="EXT", help=t("arg_only_ext"))
    p.add_argument("--any-text", action="store_true", help=t("arg_any_text"))
    p.add_argument("--include-hidden", action="store_true", help=t("arg_include_hidden"))
    p.add_argument("--exclude-dir", nargs="+", metavar="DIR", help=t("arg_exclude_dir"))
    p.add_argument("--exclude-file", nargs="+", metavar="NAME", help=t("arg_exclude_file"))
    p.add_argument("--exclude-pattern", nargs="+", metavar="PAT", help=t("arg_exclude_pattern"))
    p.add_argument("--include-pattern", nargs="+", metavar="PAT", help=t("arg_include_pattern"))
    p.add_argument("--lang", "--language", dest="lang",
                   choices=("auto",) + SUPPORTED_LANGS, default=None, help=t("arg_lang"))
    p.add_argument("--line-numbers", action="store_true", help=t("arg_line_numbers"))
    p.add_argument("--max-file-lines", type=_nonneg_int, default=None, metavar="N",
                   help=t("arg_max_file_lines"))      # ★
    p.add_argument("--max-file-kb", type=_nonneg_float, default=None, metavar="KB",
                   help=t("arg_max_file_kb"))         # ★
    p.add_argument("--max-total-kb", type=_nonneg_float, default=None, metavar="KB",
                   help=t("arg_max_total_kb"))        # ★
    p.add_argument("--split-tokens", type=_nonneg_int, default=None, metavar="N",
                   help=t("arg_split_tokens"))        # ★
    p.add_argument("--no-tree", action="store_true", help=t("arg_no_tree"))
    p.add_argument("--no-index", action="store_true", help=t("arg_no_index"))
    p.add_argument("--no-ai-header", action="store_true", help=t("arg_no_ai_header"))
    p.add_argument("--no-smart-order", action="store_true", help=t("arg_no_smart_order"))
    p.add_argument("--prompt", default=None, help=t("arg_prompt"))
    p.add_argument("--prompt-file", default=None, help=t("arg_prompt_file"))
    p.add_argument("--clip", action="store_true", help=t("arg_clip"))
    p.add_argument("--stdout", action="store_true", help=t("arg_stdout"))
    p.add_argument("--dry-run", action="store_true", help=t("arg_dry_run"))
    p.add_argument("--config", default=None, help=t("arg_config", cfg=CONFIG_FILENAME))
    p.add_argument("--no-config", action="store_true", help=t("arg_no_config"))
    p.add_argument("--init-config", action="store_true",
                   help=t("arg_init_config", cfg=CONFIG_FILENAME))
    p.add_argument("--restore", action="store_true", help=t("arg_restore"))
    p.add_argument("target", nargs="?", default=None, help=t("arg_target"))
    p.add_argument("--list", action="store_true", help=t("arg_list"))
    p.add_argument("--json", action="store_true", help=t("arg_json"))
    p.add_argument("--diff", action="store_true", help=t("arg_diff"))
    p.add_argument("--max-diff", type=_nonneg_int, default=120, metavar="N",
                   help=t("arg_max_diff"))            # ★
    p.add_argument("--backup", action="store_true", help=t("arg_backup"))
    p.add_argument("--skip-existing", action="store_true", help=t("arg_skip_existing"))
    p.add_argument("--allow-truncated", action="store_true", help=t("arg_allow_truncated"))
    p.add_argument("--strip-linenum", choices=("auto", "on", "off"), default="auto",
                   help=t("arg_strip_linenum"))
    p.add_argument("--keep-encoding", action="store_true", help=t("arg_keep_encoding"))
    p.add_argument("--quiet", action="store_true", help=t("arg_quiet"))
    p.add_argument("--version", action="store_true", help=t("arg_version"))
    return p.parse_args(argv)

def load_prompt(args) -> str:
    if args.prompt:
        return args.prompt.strip()
    if args.prompt_file:
        try:
            return Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except Exception as e:
            cprint(t("warn_prompt_file", err=e))
    return ""

# ─────────────────────────── 主流程 ───────────────────────────
def main(argv=None):
    args = parse_args(argv)
    if args.version:
        cprint(f"{TOOL} v{VERSION}")
        return 0
    # ── 反向还原模式：第一个位置参数是合集文件，第二个是还原目标目录 ──
    if args.restore:
        if args.repo:
            cprint(t("err_restore_repo"))
            return 2
        if args.init_config:
            cprint(t("err_restore_initcfg"))
            return 2
        return run_restore(args)
    if args.target:
        cprint(t("err_target_no_restore"))
        return 2
    # 临时快照目录用 ExitStack 托管：异常 / 任何 return / Ctrl+C 都会走到 __exit__ 清理，
    # 不再依赖 TemporaryDirectory 的 GC 时机。
    with ExitStack() as stack:
        remote_name = None
        root_label = None
        if args.repo:
            if args.root:
                cprint(t("err_repo_and_root"))
                return 2
            if args.init_config:
                cprint(t("err_init_config_repo"))
                return 2
            try:
                remote_name = stack.enter_context(tempfile.TemporaryDirectory(prefix="proj2md-"))
                root, root_label = fetch_remote_repo(args.repo, args.ref, Path(remote_name))
            except RuntimeError as e:
                cprint(t("err_repo_fetch", err=e))
                return 1
        else:
            root = Path(args.root or ".").expanduser().resolve()
            root_label = root.name
        quiet = args.quiet
        cfg_path = (Path(args.config).expanduser().resolve()
                    if args.config else (Path(remote_name) / CONFIG_FILENAME if remote_name else root / CONFIG_FILENAME))
        # ── 1. 先静默读取配置文件（界面语言可能写在里面），暂存加载结果 ──
        data, load_state = {}, None   # None / ("ok",) / ("bad_root",) / ("error", exc)
        if not args.no_config and cfg_path.is_file():
            try:
                loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    load_state = ("bad_root",)
                else:
                    data, load_state = loaded, ("ok",)
            except Exception as e:
                load_state = ("error", e)
        # ── 2. 解析界面语言：--lang 参数 > 配置文件 language 字段 > 系统探测 ──
        set_lang(args.lang or data.get("language") or "auto")
        if not quiet and load_state:
            if load_state[0] == "ok":
                cprint(t("info_config_loaded", path=cfg_path))
            elif load_state[0] == "bad_root":
                cprint(t("warn_config_parse", err=t("err_config_root")))
            else:
                cprint(t("warn_config_parse", err=load_state[1]))
        if not root.is_dir():
            cprint(t("err_root_not_dir", root=root))
            return 1
        if args.init_config:
            if cfg_path.exists():
                cprint(t("err_config_exists", path=cfg_path))
                return 1
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
            cprint(t("ok_config_created", path=cfg_path))
            cprint(t("config_hint"))
            return 0
        cfg = build_config(root, args, data, cfg_path)
        candidates, pruned_hidden = discover(cfg)
        if not candidates:
            cprint(t("err_no_files"))
            return 1
        if cfg.smart_order:
            candidates.sort(key=order_key)
        records, skipped = build_records(cfg, candidates)
        if not records:
            cprint(t("err_all_skipped"))
            return 1
        prompt_text = load_prompt(args)
        if args.dry_run:
            dry_run_report(cfg, records, skipped, pruned_hidden, root_label)
            return 0
        # ── 分卷模式 ──
        if cfg.split_tokens and not args.stdout:
            chunks, cur_chunk, cur_tok = [], [], 0
            for r in records:
                tk = estimate_tokens(r.content)   # 注意：勿命名为 t，避免遮蔽翻译函数
                if cur_chunk and cur_tok + tk > cfg.split_tokens:
                    chunks.append((cur_chunk, cur_tok))
                    cur_chunk, cur_tok = [], 0
                cur_chunk.append(r)
                cur_tok += tk
            if cur_chunk:
                chunks.append((cur_chunk, cur_tok))
            if len(chunks) > 1:
                base = cfg.output.expanduser()
                base.parent.mkdir(parents=True, exist_ok=True)
                stem, suf = base.stem, base.suffix or ".md"
                for i, (chunk, tok) in enumerate(chunks, 1):
                    label = t("part_label", i=i, n=len(chunks))
                    sk = skipped if i == len(chunks) else []
                    ph = pruned_hidden if i == len(chunks) else []
                    txt = render(cfg, chunk, sk, prompt_text, root_label,
                                 part_label=label, pruned_hidden=ph)
                    p = base.with_name(f"{stem}.part{i}{suf}")
                    with open(p, "w", encoding="utf-8", newline="\n") as fh:
                        fh.write(txt)
                    if not quiet:
                        cprint(t("ok_part_generated", name=p.name, files=len(chunk),
                                 tokens=f"{tok:,}",
                                 size=fmt_size(len(txt.encode("utf-8")))))
                if not quiet:
                    cprint(t("split_hint", n=cfg.split_tokens, total=len(chunks)))
                return 0
        text = render(cfg, records, skipped, prompt_text, root_label, pruned_hidden=pruned_hidden)
        if args.stdout:
            sys.stdout.write(text)
            return 0
        out = cfg.output.expanduser()
        # 仅 --clip 且未指定输出文件（-o / 配置）：输出文件不存在时不落盘，已存在才更新
        if cfg.clip and args.output is None and not data.get("output") and not out.exists():
            ok, how = copy_clipboard(text)
            cprint(t("ok_clipboard", how=how) if ok else t("err_clipboard"))
            if not ok:
                # 该分支不落盘，剪贴板失败等于结果全丢；CI / 管道下必须让失败可见
                if not sys.stdout.isatty():
                    print(t("warn_clip_discarded"), file=sys.stderr)
            if not quiet:
                cprint(t("info_clip_no_write", path=out))
            return 0
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        if quiet:
            cprint(str(out))
        else:
            print_summary(out, records, skipped, text, pruned_hidden)
        if cfg.clip:
            ok, how = copy_clipboard(text)
            if ok:
                cprint(t("ok_clipboard", how=how))
            else:
                cprint(t("err_clipboard"))
                # 非交互场景（CI / 管道）静默失败会丢结果，向 stderr 提示
                if not sys.stdout.isatty():
                    print(t("warn_clip_wrote_file"), file=sys.stderr)
        return 0

def cli() -> None:
    """命令行入口：pip/pipx 安装后由 `proj2md` 可执行文件调用。"""
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        cprint(t("cancelled"))
        sys.exit(130)
