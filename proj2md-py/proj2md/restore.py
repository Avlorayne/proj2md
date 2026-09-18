"""proj2md 反向还原（--restore）：Markdown 合集 → 真实文件。"""
from __future__ import annotations
import difflib
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .discover import read_text  # ★ 修复（P2）：编码探测读取（utf-8-sig→utf-8→gbk→big5→latin-1）
from .i18n import t
from .util import cprint

# ═══════════════════════ 反向还原（--restore）═══════════════════════
# 解析约定与 render() 的输出一一对应，同时容忍 AI 回复的松散写法：
#   ### 序号. 相对路径            → 文件路径（序号可省略）
#   围栏代码块（长度自适应）      → 文件内容（代码内含 ``` 也能正确解析）
#   **i/n** · `语言` · N 行 · 编码 `gbk` → 元信息（--keep-encoding 按原编码写回）
HEAD_RE = re.compile(r"^(#{2,4})\s+(?:(\d{1,4})\s*[.、)]\s*)?(.+?)\s*$")
FENCE_OPEN_RE = re.compile(r"^(`{3,})(\S*)")
FENCE_CLOSE_RE = re.compile(r"^(`{3,})\s*$")
ENC_RE = re.compile(r"(?:编码|encoding)\s*`([^`]+)`", re.IGNORECASE)
TITLE_PREFIX_RE = re.compile(r"^(?:file|filename|filepath|path|文件|文件名|路径)\s*[:：]\s*", re.IGNORECASE)
LN_STRICT_RE = re.compile(r"^ {0,5}\d{1,6} \|\s?")          # 与 f"{k:>5} | " 一致
LN_NUM_RE = re.compile(r"^ {0,5}(\d{1,6}) \|")
LN_LOOSE_RE = re.compile(r"^\s*\d{1,6}\s*\|\s?")
TRUNC_ZH_RE = re.compile(r"^……（该文件共\s*\d+\s*行.*）\s*$")
TRUNC_EN_RE = re.compile(r"^\.{2,3}\(the file has\s*\d+\s*lines.*kept\)\s*$", re.IGNORECASE)
APPENDIX_RE = re.compile(r"附录：未包含的文件|Appendix:\s*Files Not Included", re.IGNORECASE)
SKIP_ITEM_RE = re.compile(r"^\s*[-*]\s+`?([^`（(]+)")
BAD_HEAD_RE = re.compile(
    r"目录结构|文件索引|源代码正文|给 ?AI|我的需求|附录[：:]"
    r"|directory tree|file index|source code|reading notes|my request|appendix",
    re.IGNORECASE)
NONPATH_RE = re.compile(r"^[*_>#\-|\[(`【（]")
# 无扩展名但可作为路径的文件名 / Windows 保留设备名
KNOWN_NAMES = {
    "makefile", "dockerfile", "rakefile", "gemfile", "procfile", "brewfile",
    "justfile", "vagrantfile", "license", "licence", "notice",
    ".gitignore", ".gitattributes", ".dockerignore", ".editorconfig",
    ".npmrc", ".nvmrc", ".python-version", ".env.example", ".env.sample",
}
_WIN_RESERVED = {"con", "prn", "aux", "nul",
                 *(f"com{i}" for i in range(1, 10)),
                 *(f"lpt{i}" for i in range(1, 10))}
@dataclass
class Entry:
    path_text: str            # 标题里写的原始路径
    rel: Path | None          # 清洗后的安全相对路径；None = 已拒绝
    content: str
    lang: str = ""
    encoding: str | None = None
    truncated: bool = False
def safe_rel(path_text: str) -> Path | None:
    """拒绝绝对路径 / 盘符 / .. / Windows 保留名；返回清洗后的相对路径。"""
    name = path_text.replace("\\", "/").strip()
    # 显式拒绝 Unix 绝对路径：先 strip("/") 再 split 会把 "/etc/x" 相对化为 "etc/x"，
    # 使 is_absolute() 判断失效、护栏静默放行（与「路径不安全」的帮助文案矛盾）。
    if name.startswith("/"):
        return None
    segs = [s for s in name.split("/") if s not in ("", ".")]
    if not segs:
        return None
    pure = Path(*segs)
    if pure.is_absolute() or pure.drive or ".." in pure.parts:
        return None
    for seg in pure.parts:
        if len(seg) > 255:
            return None
        if seg.split(".")[0].strip().lower() in _WIN_RESERVED:
            return None
    return pure
def clean_title(raw: str) -> str:
    """清洗标题：去掉 '文件：' 前缀、包裹反引号、尾部的 ':42' 行引用。"""
    s = raw.strip()
    s = TITLE_PREFIX_RE.sub("", s, count=1).strip()
    s = re.sub(r"[:：]\d{1,6}$", "", s).strip()
    return s.strip("`").strip()
def looks_like_path(title: str) -> bool:
    """判断标题是否像文件路径（过滤章节标题、元信息等干扰项）。"""
    s = title.strip()
    if not s or len(s) > 200 or s.endswith("/"):
        return False
    if BAD_HEAD_RE.search(s) or NONPATH_RE.match(s):
        return False
    last = s.rsplit("/", 1)[-1]
    if "." in last or last.lower() in KNOWN_NAMES:
        return True
    return "/" in s and " " not in s
def strip_line_numbers(content: str, mode: str):
    """剥离 --line-numbers 生成的前缀（如 '   12 | '）。
    auto: 所有非空行都带严格前缀且行号连续 1..n 才剥离（几乎零误伤）；
    on:   逐行宽松剥离；
    off:  原样返回。返回 (content, stripped)。"""
    if mode == "off" or not content.strip():
        return content, False
    lines = content.split("\n")
    body = [l for l in lines if l.strip()]
    if not body:
        return content, False
    if mode == "auto":
        if not all(LN_STRICT_RE.match(l) for l in body):
            return content, False
        nums = [int(LN_NUM_RE.match(l).group(1)) for l in body]
        if nums != list(range(1, len(nums) + 1)):
            return content, False
        return "\n".join(LN_STRICT_RE.sub("", l, count=1) for l in lines), True
    out = [LN_LOOSE_RE.sub("", l, count=1) if LN_LOOSE_RE.match(l) else l for l in lines]
    return "\n".join(out), True
def is_trunc_note(line: str) -> bool:
    """识别 proj2md 的截断提示行（严格 + 宽松两种）。"""
    if TRUNC_ZH_RE.match(line) or TRUNC_EN_RE.match(line):
        return True
    if "该文件共" in line and ("保留前" in line or "超过" in line):
        return True
    low = line.lower()
    if "lines in total" in low and ("kept" in low or "beyond" in low or "first" in low):
        return True
    return False
def parse_bundle(text: str, strip_mode: str):
    """把 Markdown 合集解析为条目列表。返回。
    解析以标题为驱动：只有「路径样标题 + 紧随的围栏代码块」才会成为条目，
    目录树 / 索引表 / 附录说明等其余内容自动忽略。"""
    lines = text.split("\n")
    # 容错：脱掉 AI 常见的最外层 ```markdown 包装围栏（只处理带 markdown/md 标识的）
    idx = [k for k, l in enumerate(lines) if l.strip()]
    if idx:
        fm = FENCE_OPEN_RE.match(lines[idx[0]].strip())
        cm = FENCE_CLOSE_RE.match(lines[idx[-1]].strip())
        if (fm and cm and len(cm.group(1)) >= len(fm.group(1))
                and (fm.group(2) or "").lower() in ("markdown", "md")):
            lines = lines[idx[0] + 1: idx[-1]]
    entries, missing, warns = [], [], []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        hm = HEAD_RE.match(line)
        title = clean_title(hm.group(3)) if hm else ""
        if hm and looks_like_path(title):
            # 标题之后允许夹空白 / **元信息** 行，寻找围栏开始
            meta, j, opened = "", i + 1, None
            while j < n and j - i <= 8:
                st = lines[j].strip()
                if not st:
                    j += 1
                    continue
                if st.startswith("**"):
                    meta = st
                    j += 1
                    continue
                fm = FENCE_OPEN_RE.match(st)
                if fm:
                    opened = (j, len(fm.group(1)), (fm.group(2) or "").strip())
                break
            if opened:
                j, ticks, lang = opened
                # 收集正文：关栏条件 = 反引号数 >= 开栏（兼容 render 的变长围栏）
                body, k, closed = [], j + 1, False
                while k < n:
                    cm = FENCE_CLOSE_RE.match(lines[k].strip())
                    if cm and len(cm.group(1)) >= ticks:
                        closed = True
                        break
                    body.append(lines[k])
                    k += 1
                if closed:
                    content, _ = strip_line_numbers("\n".join(body), strip_mode)
                    # 识别并剥离截断提示行（可能仍带行号前缀）
                    ls = content.split("\n")
                    while ls and not ls[-1].strip():
                        ls.pop()
                    truncated = False
                    if ls:
                        last = ls[-1]
                        if LN_LOOSE_RE.match(last):
                            last = LN_LOOSE_RE.sub("", last, count=1)
                        if is_trunc_note(last):
                            ls.pop()
                            truncated = True
                    content = "\n".join(ls)
                    if content and not content.endswith("\n"):
                        content += "\n"
                    if content.strip() in ("（空文件）", "(empty file)"):
                        content = ""                     # 还原为空文件
                    em = ENC_RE.search(meta)
                    rel = safe_rel(title)
                    if rel is None:
                        warns.append(t("warn_unsafe_path", path=title))
                    entries.append(Entry(title, rel, content, lang,
                                         em.group(1) if em else None, truncated))
                    i = k + 1
                    continue
                else:
                    warns.append(t("warn_unclosed", path=title))
                    i = k
                    continue
        # 附录「未包含的文件」：收集清单，仅作提示（本就不在合集里，无法还原）
        if APPENDIX_RE.search(line):
            j = i + 1
            while j < n and not lines[j].lstrip().startswith("#"):
                sm = SKIP_ITEM_RE.match(lines[j])
                if sm:
                    path_txt = sm.group(1).strip()
                    if not path_txt.startswith(("…", "...")):
                        missing.append(path_txt)
                j += 1
            i = j
            continue
        i += 1
    # 同路径去重：后出现的通常是更新版本；若旧的未截断而新的被截断则保留旧的
    seen, final = {}, []
    for e in entries:
        if e.rel is None:
            final.append(e)
            continue
        key = e.rel.as_posix().lower()
        if key in seen:
            idx2 = seen[key]
            old = final[idx2]
            warns.append(t("warn_dup_path", path=e.rel.as_posix()))
            if old.truncated and not e.truncated:
                final[idx2] = e
        else:
            seen[key] = len(final)
            final.append(e)
    return final, missing, warns
def print_diff(rel: str, old: str, new: str, limit: int):
    dl = list(difflib.unified_diff(old.split("\n"), new.split("\n"),
                                   fromfile="a/" + rel, tofile="b/" + rel, lineterm=""))
    if len(dl) > limit:
        dl = dl[:limit] + [t("more_items", n=len(dl) - limit).strip()]
    print("\n".join(dl))
def read_clipboard() -> str | None:
    """读取系统剪贴板文本；优先 pyperclip，再按平台回退。"""
    try:
        import pyperclip  # type: ignore
        text = pyperclip.paste()
        if text:
            return text
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            ps = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
                  "Get-Clipboard -Raw")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, timeout=30)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", errors="replace")
        elif sys.platform == "darwin":
            r = subprocess.run(["pbpaste"], capture_output=True, timeout=30)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", errors="replace")
        else:
            for cmd in (["wl-paste"], ["xclip", "-selection", "clipboard", "-o"],
                        ["xsel", "--clipboard", "--output"]):
                if shutil.which(cmd[0]):
                    r = subprocess.run(cmd, capture_output=True, timeout=30)
                    if r.returncode == 0:
                        return r.stdout.decode("utf-8", errors="replace")
    except Exception:
        pass
    return None
def apply_entries(entries, root: Path, args, bundle_path):
    """把条目写回磁盘。返回。"""
    created, updated, unchanged, skipped, failed = [], [], [], [], []
    root_res = root.resolve()
    include = [p.lower() for p in (args.include_pattern or [])]
    exclude = [p.lower() for p in (args.exclude_pattern or [])]
    for e in entries:
        rel_posix = e.rel.as_posix() if e.rel else e.path_text
        if e.rel is None:
            failed.append((rel_posix, t("reason_unsafe")))
            continue
        if include and not any(fnmatch.fnmatch(rel_posix.lower(), p) for p in include):
            skipped.append((rel_posix, t("reason_only")))
            continue
        if exclude and any(fnmatch.fnmatch(rel_posix.lower(), p) for p in exclude):
            skipped.append((rel_posix, t("reason_excluded")))
            continue
        if e.truncated and not args.allow_truncated:
            skipped.append((rel_posix, t("reason_truncated")))
            continue
        target = root / e.rel
        try:                                   # 双保险：解析后必须仍在 root 内
            target_res = target.resolve()
            target_res.relative_to(root_res)
        except (OSError, ValueError):
            failed.append((rel_posix, t("reason_escape")))
            continue
        if bundle_path and target_res == bundle_path:
            skipped.append((rel_posix, t("reason_self")))
            continue
        if target_res.is_dir():
            failed.append((rel_posix, t("reason_isdir")))
            continue
        text = e.content
        if text and not text.endswith("\n"):
            text += "\n"
        exists = target.exists()
        if exists:
            try:
                old = target.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
            except OSError as err:
                failed.append((rel_posix, t("reason_read_old", err=err)))
                continue
            if old == text:
                unchanged.append(rel_posix)
                continue
            if args.skip_existing:
                skipped.append((rel_posix, t("reason_skip_existing")))
                continue
            if args.diff:
                print_diff(rel_posix, old, text, args.max_diff)
        if args.dry_run:
            (created if not exists else updated).append(rel_posix)
            continue
        if exists and args.backup:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            bak = target.with_name(target.name + ".bak-" + stamp)
            k = 1
            while bak.exists():
                bak = target.with_name(f"{target.name}.bak-{stamp}-{k}")
                k += 1
            try:
                target.rename(bak)
            except OSError as err:
                failed.append((rel_posix, t("reason_backup", err=err)))
                continue
        enc = e.encoding if (args.keep_encoding and e.encoding) else "utf-8"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding=enc, newline="\n") as fh:
                fh.write(text)
        except (UnicodeEncodeError, LookupError):
            cprint(t("warn_enc_fallback", path=rel_posix, enc=enc))
            try:
                with open(target, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            except OSError as err:
                failed.append((rel_posix, t("reason_write", err=err)))
                continue
        except OSError as err:
            failed.append((rel_posix, t("reason_write", err=err)))
            continue
        (created if not exists else updated).append(rel_posix)
    return created, updated, unchanged, skipped, failed
def run_restore(args) -> int:
    """--restore 反向模式：读入 Markdown（文件 / stdin / 剪贴板）→ 解析 → 写盘。"""
    # ── 1. 读入 Markdown 文本 ──
    bundle_path = None
    if args.clip:
        text = read_clipboard()
        if text is None:
            cprint(t("err_restore_clip"))
            return 1
    elif args.root in ("-", None):
        if args.root is None:
            cprint(t("err_restore_need_bundle"))
            return 2
        # Windows 控制台 stdin 默认按 GBK 解码，直接 read() 会把 UTF-8 管道读成乱码。
        # 合集本身就是 UTF-8 写出的，这里读原始字节再按 UTF-8 解码。
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    else:
        bp = Path(args.root).expanduser()
        if not bp.is_file():
            cprint(t("err_restore_bundle", path=bp))
            return 1
        bundle_path = bp.resolve()
        # ★ 修复（P2）：按编码链读取合集。此前固定按 utf-8 读，Windows PowerShell 5.1
        #   「Out-File」类工具写出的 UTF-16 文件会整篇乱码、解析出 0 条目；
        #   改用与打包端一致的编码探测（utf-8-sig→utf-8→gbk→big5→latin-1）。
        raw_text, _enc, err = read_text(bp)
        if raw_text is None:
            # read_text 的二进制嗅探（\x00 检查）会把 UTF-16 误判为二进制；
            # 带 BOM 的 UTF-16 正是 Out-File 的默认格式，此处按 BOM 再试一次。
            try:
                raw_text = bp.read_bytes().decode("utf-16")  # utf-16 编解码自动识别并剥离 BOM
            except (UnicodeDecodeError, UnicodeError):
                raw_text = None
            if raw_text is None:
                cprint(t("err_restore_read", err=err))  # 文案键 err_restore_read 已加入 i18n
                return 1
        text = raw_text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # ── 2. 解析 ──
    entries, missing, warns = parse_bundle(text, args.strip_linenum)
    real = [e for e in entries if e.rel is not None]
    # 先报警告再判断「无可用条目」：合集里全是非法路径时，
    # 用户需要看到「路径不安全」的原因，而不是笼统的「未解析到条目」。
    for w in warns:
        (print(w, file=sys.stderr) if args.json else cprint(w))
    if not real:
        cprint(t("err_restore_no_entries"))
        return 1
    # ── 3. JSON / 清单模式 ──
    if args.json:
        payload = [{
            "path": e.rel.as_posix() if e.rel else e.path_text,
            "safe": e.rel is not None,
            "language": e.lang,
            "encoding": e.encoding,
            "truncated": e.truncated,
            "lines": len(e.content.splitlines()),
            "content": e.content,
        } for e in entries]
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.list:
        cprint(t("list_title", n=len(real)))
        for idx, e in enumerate(real, 1):
            flag = t("flag_trunc") if e.truncated else ""
            cprint(t("list_item", i=f"{idx:>4}", path=e.rel.as_posix(),
                     lang=e.lang or "-", n=len(e.content.splitlines()), flag=flag))
        if missing:
            cprint()
            cprint(t("info_missing_files", n=len(missing)))
            for m in missing[:20]:
                cprint(t("info_missing_item", path=m))
        return 0
    # ── 4. 写盘 ──
    if args.target == "-":
        cprint(t("err_restore_bad_target"))
        return 2
    root = Path(args.target or ".").expanduser().resolve()
    if not root.exists():
        if args.dry_run:
            cprint(t("info_dry_root", root=root))
        else:
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                cprint(t("err_restore_mkdir", err=err))
                return 1
    created, updated, unchanged, skipped, failed = apply_entries(
        entries, root, args, bundle_path)
    # ── 5. 报告 ──
    cprint()
    head = t("sum_restore", c=len(created), u=len(updated), s=len(unchanged),
             k=len(skipped), f=len(failed))
    if args.dry_run:
        head += t("sum_restore_dry")
    cprint(head)
    if not args.quiet:
        for p in created[:50]:
            cprint(t("item_created", path=p))
        if len(created) > 50:
            cprint(t("more_items", n=len(created) - 50))
        for p in updated[:50]:
            cprint(t("item_updated", path=p))
        if len(updated) > 50:
            cprint(t("more_items", n=len(updated) - 50))
        for p, why in skipped[:30]:
            cprint(t("item_skipped", path=p, reason=why))
        if len(skipped) > 30:
            cprint(t("more_items", n=len(skipped) - 30))
        for p, why in failed[:30]:
            cprint(t("item_failed", path=p, reason=why))
        if len(failed) > 30:
            cprint(t("more_items", n=len(failed) - 30))
    if missing:
        cprint()
        cprint(t("info_missing_files", n=len(missing)))
        for m in missing[:20]:
            cprint(t("info_missing_item", path=m))
    return 1 if failed else 0
