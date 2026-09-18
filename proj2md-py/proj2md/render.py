"""proj2md Markdown 渲染：目录树 / 索引表 / 文件正文 / 附录。"""
from __future__ import annotations
from datetime import datetime

from .defaults import MARK, MARK_RE, TOOL, VERSION
from .i18n import t
from .util import estimate_tokens, fence_for, fence_lang_of, fmt_size, md_code_span, md_slug, md_table_cell

# ─────────────────────────── 渲染（Markdown） ───────────────────────────
def build_tree(records, root_label: str) -> str:
    tree = {}
    for r in records:
        node = tree
        parts = list(r.rel.parts)
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None
    lines = [root_label + "/"]
    def walk(node, prefix):
        items = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0].lower()))
        for i, (name, child) in enumerate(items):
            last = (i == len(items) - 1)
            lines.append(prefix + ("└── " if last else "├── ") + name + ("/" if child else ""))
            if child:
                walk(child, prefix + ("    " if last else "│   "))
    walk(tree, "")
    return "\n".join(lines) + "\n"
def render(cfg: Config, records, skipped, prompt_text: str, root_name: str,
           part_label: str = "", pruned_hidden=None) -> str:
    n = len(records)
    tot_lines = sum(r.lines for r in records)
    tot_size = sum(len(r.content.encode("utf-8")) for r in records)  # ★ 修复（P0-1）：字节口径
               # （原按字符数计，与控制台报告 len(text.encode("utf-8")) 口径不一致）
    tot_tokens = sum(estimate_tokens(r.content) for r in records)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    pruned_hidden = pruned_hidden or []
    # ── 头部各节：标题/说明/需求/目录树 ──
    head = []
    meta = [
        "- " + t("doc_meta_time", now=now),
        "- " + t("doc_meta_project", root=root_name),
        "- " + (t("doc_meta_files_skipped", n=n, skipped=len(skipped)) if skipped
                else t("doc_meta_files", n=n)),
        "- " + t("doc_meta_lines", lines=f"{tot_lines:,}"),
        "- " + t("doc_meta_size", size=fmt_size(tot_size)),  # ★
        "- " + t("doc_meta_tokens", tokens=f"{tot_tokens:,}"),
    ]
    head.append(t("doc_title", root=root_name, label=part_label) + "\n\n" + "\n".join(meta))
    if cfg.ai_header:
        head.append(t("doc_ai_header") + t("ai_notes", root=root_name))
    if prompt_text:
        head.append(t("doc_prompt") + prompt_text)
    if cfg.show_tree:
        tree = build_tree(records, root_name).rstrip("\n")
        tf = fence_for(tree)
        head.append(t("doc_tree") + tf + "\n" + tree + "\n" + tf)
    # ── 文件正文节：### 序号. 路径 + 围栏代码块 ──
    file_secs = []
    for i, r in enumerate(records, 1):
        path = r.rel.as_posix()
        content = r.content
        if cfg.line_numbers:
            ls = content.split("\n")
            if ls and ls[-1] == "":
                ls.pop()
            content = "\n".join(f"{k:>5} | {ln}" for k, ln in enumerate(ls, 1)) + "\n"
        f = fence_for(content)
        info = [f"`{r.language}`", t("doc_lines_unit", n=r.lines)]
        if r.encoding and not r.encoding.startswith("utf"):
            info.append(t("doc_encoding", enc=r.encoding))
        if r.truncated:
            info.append(t("doc_truncated"))
        # 围栏行末尾加内部标记，稍后用于回填索引中的起始行号
        fence_line = f + fence_lang_of(r.rel) + MARK + str(i) + MARK
        file_secs.append(
            f"### {i}. {path}\n\n"
            f"**{i}/{n}** · " + " · ".join(info) + "\n\n" +
            fence_line + "\n" + content + f)
    # ── 索引表（起始行先占位，组装后按标记回填真实行号） ──
    def make_index(starts):
        rows = [t("doc_index_cols"), "|---:|:---|:---|---:|---:|"]
        for i, (r, s) in enumerate(zip(records, starts), 1):
            path = r.rel.as_posix()
            cell = md_table_cell(path)
            anchor = md_slug(f"{i}. {path}")
            rows.append(f"| {i} | [{cell}](#{anchor}) | {r.language} | {r.lines} | {s} |")
        return t("doc_index") + "\n".join(rows)
    # ── 尾部各节：附录 / 结尾 ──
    tail = []
    if file_secs:
        tail.append(t("doc_source") + "\n\n".join(file_secs))
    if skipped:
        items = [t("doc_skip_item", path=md_code_span(rel), reason=reason)
                 for rel, reason in skipped[:50]]
        if len(skipped) > 50:
            items.append(t("doc_more_skipped", n=len(skipped) - 50))
        tail.append(t("doc_appendix_skipped") + "\n".join(items))
    if pruned_hidden:
        shown = pruned_hidden[:30]
        items = [t("doc_hidden_item", path=md_code_span(d)) for d in shown]
        if len(pruned_hidden) > 30:
            items.append(t("doc_more_hidden", n=len(pruned_hidden) - 30))
        tail.append(t("doc_appendix_hidden") + "\n".join(items))
    tail.append(t("doc_end", n=n, lines=f"{tot_lines:,}", tokens=f"{tot_tokens:,}",
                  tool=TOOL, ver=VERSION, now=now))
    dummy_index = make_index([0] * n) if (cfg.show_index and n) else None
    secs = head + ([dummy_index] if dummy_index else []) + tail
    doc = "\n\n".join(secs) + "\n"
    # ── 回填真实起始行号，并整体移除内部标记（标记+序号一起删除） ──
    if dummy_index:
        starts = [0] * n
        for li, ln in enumerate(doc.split("\n"), 1):
            m = MARK_RE.search(ln)
            if m:
                starts[int(m.group(1)) - 1] = li + 1   # 围栏行的下一行即正文首行
        doc = MARK_RE.sub("", doc)
        if all(s > 0 for s in starts):
            doc = doc.replace(dummy_index, make_index(starts), 1)
        else:
            doc = MARK_RE.sub("", doc)
    return doc
