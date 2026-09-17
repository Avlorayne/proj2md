#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
proj2md.py —— 项目源码一键拼接工具（输出 Markdown，专为投喂网页端 AI 设计）
把散落在各个子目录里的代码 / 配置 / 文档文件，合并成一份结构清晰的 Markdown 文档：
标题层级 + 目录树 + 文件索引表 + 语法高亮代码块，并附带「给 AI 的阅读说明」，
方便直接粘贴给 ChatGPT / Claude / Gemini / DeepSeek / 通义 / 文心等网页端 AI。
忽略规则（按顺序生效，任一命中即跳过）：
  1. 隐藏目录：所有以 . 开头的文件夹默认整目录忽略（--include-hidden 可关闭）
  2. 目录名单：DEFAULT_EXCLUDE_DIRS 黑名单 + --exclude-dir 追加
  3. 文件名单：DEFAULT_EXCLUDE_FILES（锁文件等） + --exclude-file 追加
  4. 通配符 ：DEFAULT_EXCLUDE_PATTERNS（*.min.js/*.png 等） + --exclude-pattern 追加
  5. 扩展名白名单：不在 DEFAULT_EXTS 中的扩展名跳过（--ext / --only-ext / --any-text 调整）
  ※ --include-pattern 拥有最高优先级：即使命中上述任何忽略规则也会强制包含，
    且能「穿透」隐藏目录忽略（如 --include-pattern ".github/*"）
多语言界面（v2.2.0 新增）：
  语言解析优先级：--lang 参数 > 配置文件 language 字段 > 系统自动探测 > 英文兜底
  - 默认 auto：自动跟随系统语言（中文系统 → 中文输出，其余 → 英文输出）
  - --lang zh / --lang en：临时切换界面语言（含 --help、控制台报告、生成的文档说明）
  - proj2md.json 中 "language": "zh" / "en" / "auto"：持久化设置
远程仓库（v2.3.0 新增）：
  --repo 直接打包远端仓库快照，不执行 git clone：
  - GitHub URL 走源码归档接口，私有仓库可用环境变量 GITHUB_TOKEN / GH_TOKEN
  - 其他 Git 服务尝试 git archive --remote，需服务端开启 git-upload-archive
  - --ref 指定分支 / 标签 / 提交（默认 HEAD）；不能与本地 root 参数同时使用
快速上手
  python proj2md.py                          # 拼接当前目录 -> project_bundle.md
  python proj2md.py /path/to/project         # 拼接指定项目
  python proj2md.py --repo https://github.com/owner/repo --ref main
  python proj2md.py --clip                   # 生成并复制到剪贴板
  python proj2md.py --prompt "帮我找出潜在 bug"
  python proj2md.py --dry-run                # 只预览，不写文件
  python proj2md.py --init-config            # 生成配置文件模板
"""
from __future__ import annotations
import argparse
import fnmatch
import io
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
VERSION = "2.3.2"
TOOL = "proj2md"
CONFIG_FILENAME = "proj2md.json"
DEFAULT_OUTPUT = "project_bundle.md"
MARK = "\x00"                       # 行号回填内部标记（输出前必定整体移除）
MARK_RE = re.compile("\x00(\\d+)\x00")
# ─────────────────────────── 默认规则 ───────────────────────────
DEFAULT_EXTS = {
    # 编程语言
    "py", "pyw", "js", "mjs", "cjs", "ts", "jsx", "tsx",
    "java", "c", "h", "cpp", "cc", "hpp", "cs", "go", "rs", "rb", "php",
    "swift", "kt", "kts", "scala", "dart", "m", "mm", "pl", "pm", "lua",
    "r", "jl", "hs", "clj", "ex", "exs", "erl", "groovy", "asm", "zig", "nim", "v",
    # Web / 模板
    "html", "htm", "css", "scss", "sass", "less", "styl",
    "vue", "svelte", "astro", "ejs", "hbs", "pug", "jinja", "j2", "liquid", "twig",
    # 数据 / 配置
    "json", "yml", "yaml", "toml", "ini", "cfg", "conf", "properties",
    "xml", "csv", "tsv", "sql", "graphql", "gql", "proto",
    # 文档 / 脚本
    "md", "markdown", "mdx", "rst", "txt", "adoc", "tex",
    "sh", "bash", "zsh", "fish", "bat", "cmd", "ps1", "psm1",
}
# 黑名单目录（隐藏目录另有整体开关，此处只列常见的非隐藏垃圾目录；
# 点开头的目录即使不在此列表也会被「隐藏目录规则」忽略）
DEFAULT_EXCLUDE_DIRS = {
    "node_modules", "bower_components", "jspm_packages",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    "venv", ".venv", "env", "virtualenv",
    "dist", "build", "out", "target", "obj", "bin",
    "vendor", "Pods", "Carthage",
    "coverage", ".nyc_output", ".parcel-cache",
}
DEFAULT_EXCLUDE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "pipfile.lock", "composer.lock",
    "cargo.lock", "gemfile.lock",
}
DEFAULT_EXCLUDE_PATTERNS = [
    "*.min.js", "*.min.css", "*.map", "*.log",
    "*.pyc", "*.pyo", "*.class",
    "*.o", "*.so", "*.dll", "*.exe", "*.bin",
    "*.woff", "*.woff2", "*.ttf", "*.eot", "*.otf", "*.ico",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.svg", "*.webp",
    "*.pdf", "*.zip", "*.tar", "*.gz", "*.rar", "*.7z",
    "*.mp3", "*.mp4", "*.avi", "*.mov",
    "*.db", "*.sqlite",
]
# 无扩展名但属于文本的文件名（注意：点开头的【文件】不受隐藏目录规则影响，
# 只有以 . 开头的【文件夹】会被忽略；根目录下的这类文件仍正常收录）
DEFAULT_FILENAMES = {
    "dockerfile", "makefile", "rakefile", "gemfile", "procfile",
    "brewfile", "justfile", "vagrantfile",
    "license", "licence", "notice",
    ".gitignore", ".gitattributes", ".dockerignore", ".editorconfig",
    ".npmrc", ".nvmrc", ".python-version",
    ".env.example", ".env.sample",
}
# 索引表中展示的人类可读语言名
LANGUAGE_BY_EXT = {
    "py": "Python", "pyw": "Python",
    "js": "JavaScript", "mjs": "JavaScript", "cjs": "JavaScript",
    "ts": "TypeScript", "tsx": "TypeScript React", "jsx": "JavaScript React",
    "java": "Java",
    "c": "C", "h": "C Header", "cpp": "C++", "cc": "C++", "hpp": "C++ Header",
    "cs": "C#", "go": "Go", "rs": "Rust", "rb": "Ruby", "php": "PHP",
    "swift": "Swift", "kt": "Kotlin", "kts": "Kotlin", "scala": "Scala",
    "dart": "Dart", "lua": "Lua", "pl": "Perl", "r": "R", "jl": "Julia",
    "m": "MATLAB/ObjC",
    "html": "HTML", "htm": "HTML",
    "css": "CSS", "scss": "SCSS", "sass": "Sass", "less": "Less",
    "vue": "Vue", "svelte": "Svelte",
    "json": "JSON", "yml": "YAML", "yaml": "YAML", "toml": "TOML",
    "ini": "INI", "cfg": "Config", "conf": "Config", "env": "Env",
    "xml": "XML", "sql": "SQL", "graphql": "GraphQL", "proto": "Protobuf",
    "md": "Markdown", "markdown": "Markdown", "mdx": "MDX",
    "rst": "reST", "txt": "Text", "csv": "CSV", "tsv": "TSV", "tex": "LaTeX",
    "sh": "Shell", "bash": "Shell", "zsh": "Shell", "fish": "Shell",
    "bat": "Batch", "cmd": "Batch", "ps1": "PowerShell", "psm1": "PowerShell",
}
LANGUAGE_BY_NAME = {
    "dockerfile": "Dockerfile", "makefile": "Makefile",
    "rakefile": "Ruby Rake", "gemfile": "Ruby Gemfile", "justfile": "Justfile",
    "license": "License", "licence": "License",
    ".gitignore": "Git Ignore", ".dockerignore": "Docker Ignore",
    ".editorconfig": "EditorConfig",
}
# 代码围栏的语言标识（用于 Markdown 语法高亮）
FENCE_LANG_BY_EXT = {
    "py": "python", "pyw": "python",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "ts": "typescript", "tsx": "tsx", "jsx": "jsx",
    "java": "java",
    "c": "c", "h": "c", "cpp": "cpp", "cc": "cpp", "hpp": "cpp",
    "cs": "csharp", "go": "go", "rs": "rust", "rb": "ruby", "php": "php",
    "swift": "swift", "kt": "kotlin", "kts": "kotlin", "scala": "scala",
    "dart": "dart", "lua": "lua", "pl": "perl", "pm": "perl",
    "r": "r", "jl": "julia", "hs": "haskell", "clj": "clojure",
    "ex": "elixir", "exs": "elixir", "erl": "erlang", "groovy": "groovy",
    "asm": "asm", "zig": "zig", "nim": "nim", "v": "v",
    "m": "objective-c", "mm": "objective-c",
    "html": "html", "htm": "html",
    "css": "css", "scss": "scss", "sass": "sass", "less": "less", "styl": "stylus",
    "vue": "vue", "svelte": "svelte", "astro": "astro",
    "ejs": "html", "hbs": "handlebars", "pug": "pug",
    "jinja": "jinja", "j2": "jinja", "liquid": "liquid", "twig": "twig",
    "json": "json", "yml": "yaml", "yaml": "yaml", "toml": "toml",
    "ini": "ini", "cfg": "ini", "conf": "conf", "properties": "properties",
    "xml": "xml", "sql": "sql", "graphql": "graphql", "gql": "graphql",
    "proto": "protobuf",
    "md": "markdown", "markdown": "markdown", "mdx": "markdown",
    "rst": "rst", "adoc": "asciidoc", "txt": "text", "csv": "csv", "tsv": "tsv",
    "tex": "latex",
    "sh": "bash", "bash": "bash", "zsh": "bash", "fish": "fish",
    "bat": "batch", "cmd": "batch", "ps1": "powershell", "psm1": "powershell",
}
FENCE_LANG_BY_NAME = {
    "dockerfile": "dockerfile", "makefile": "makefile",
    "rakefile": "ruby", "gemfile": "ruby", "justfile": "makefile",
    "procfile": "text", "brewfile": "ruby", "vagrantfile": "ruby",
    "license": "text", "licence": "text", "notice": "text",
    ".gitignore": "gitignore", ".gitattributes": "gitignore",
    ".dockerignore": "gitignore", ".editorconfig": "ini",
    ".npmrc": "ini", ".nvmrc": "text", ".python-version": "text",
    ".env.example": "ini", ".env.sample": "ini",
}
# 智能排序：优先级从高到低
CONFIG_MANIFESTS = {
    "package.json", "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "go.mod", "go.sum", "cargo.toml",
    "pom.xml", "build.gradle", "composer.json", "gemfile",
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "manage.py", ".env.example",
}
ENTRY_STEMS = {"main", "app", "index", "server", "wsgi", "asgi", "__init__", "cli", "run"}
ENTRY_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".rb", ".php", ".java"}
CJK_RE = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
CONFIG_TEMPLATE = {
    "_说明": [
        "proj2md 配置文件。命令行参数优先级高于本文件；",
        "不需要的键可直接删除（恢复默认）；exts 为空列表 [] 时使用内置默认扩展名。",
        "language：界面语言。auto=跟随系统 / zh=中文 / en=英文。",
    ],
    "language": "auto",
    "output": "project_bundle.md",
    "exts": [],
    "any_text": False,
    "exclude_hidden": True,
    "exclude_dirs": [],
    "exclude_files": [],
    "exclude_patterns": [],
    "include_patterns": [],
    "line_numbers": False,
    "max_file_lines": 0,
    "max_file_kb": 512,
    "max_total_kb": 0,
    "split_tokens": 0,
    "show_tree": True,
    "show_index": True,
    "ai_header": True,
    "smart_order": True,
    "clip": False,
}
_ASCII_FALLBACK = str.maketrans({
    "═": "=", "─": "-", "├": "|", "└": "`", "│": "|",
    "▶": ">", "✔": "[OK]", "⚠": "[!]", "❌": "[X]", "★": "*",
    "…": "...", "·": "-",
    "✅": "[OK]", "⚠": "[!]", "️": "",
    "（": "(", "）": ")", "「": '"', "」": '"',
})
# ═══════════════════════ 多语言系统（zh / en）═══════════════════════
# 语言解析优先级：--lang 参数 > 配置文件 language 字段 > 系统自动探测 > 英文兜底
SUPPORTED_LANGS = ("zh", "en")
LANG_TEXTS = {
    "zh": {
        # ── 命令行帮助 ──
        "cli_desc": "项目源码一键拼接工具：把整个项目合并成单个 Markdown 文档，方便投喂给网页端 AI。",
        "cli_epilog": """\
忽略规则（按顺序生效）:
  隐藏目录(默认开) → 目录黑名单 → 文件黑名单 → 通配符黑名单 → 扩展名白名单
  ※ --include-pattern 优先级最高，可穿透所有忽略规则（含隐藏目录）
常用示例:
  python proj2md.py                                # 拼接当前目录 -> project_bundle.md
  python proj2md.py myproject -o bundle.md         # 指定项目目录与输出文件
  python proj2md.py --only-ext py md               # 只拼接 Python 与 Markdown 文件
  python proj2md.py --ext proto graphql            # 在默认范围上追加扩展名
  python proj2md.py --exclude-dir tests docs       # 额外排除某些目录
  python proj2md.py --include-pattern "src/*"      # 强制包含匹配的文件（优先级最高）
  python proj2md.py --include-hidden               # 不忽略以 . 开头的文件夹
  python proj2md.py --include-pattern ".github/*"  # 只捞回某个隐藏目录的内容
  python proj2md.py --lang en                      # 界面切英文（auto/zh/en）
  python proj2md.py --line-numbers                 # 正文带行号，AI 引用更精准
  python proj2md.py --max-file-lines 300           # 单文件超过 300 行则截断
  python proj2md.py --max-total-kb 200             # 总体积预算 200KB
  python proj2md.py --split-tokens 60000           # 体积过大时自动切成多个 .md 分卷
  python proj2md.py --prompt "帮我审查代码" --clip # 附带需求并复制到剪贴板
  python proj2md.py --dry-run                      # 预览将拼接哪些文件
  python proj2md.py --init-config                  # 生成 proj2md.json 配置模板
说明:
  通配符规则同 fnmatch，* 可跨目录层级（如 "src/*" 匹配 src 下所有文件）。""",
        "arg_help": "显示本帮助信息并退出",
        "arg_root": "项目根目录（默认当前目录）",
        "arg_repo": "远程 Git 仓库 URL（不 clone；GitHub 下载源码归档，其他服务尝试 git archive）",
        "arg_ref": "远程仓库的分支、标签或提交引用（默认 HEAD）",
        "arg_output": "输出文件路径（默认 {out}）",
        "arg_ext": "在默认范围上追加扩展名，如 --ext py md",
        "arg_only_ext": "只包含指定扩展名（替换默认范围）",
        "arg_any_text": "包含所有非二进制文本文件（忽略扩展名白名单）",
        "arg_include_hidden": "不忽略以 . 开头的文件夹（默认忽略；--include-pattern 仍可单独捞回）",
        "arg_exclude_dir": "额外排除的目录名",
        "arg_exclude_file": "额外排除的文件名",
        "arg_exclude_pattern": "额外排除的通配符，如 *.min.js tests/*",
        "arg_include_pattern": "强制包含的通配符（优先级最高，可穿透一切忽略规则）",
        "arg_lang": "界面语言: auto=跟随系统 / zh=中文 / en=英文（默认 auto）",
        "arg_line_numbers": "正文每行前加行号，便于 AI 精确引用",
        "arg_max_file_lines": "单文件最多保留 N 行，超出截断（0=不限制）",
        "arg_max_file_kb": "超过此大小的文件直接跳过（默认 512）",
        "arg_max_total_kb": "合集总大小预算（KB），超出后停止追加文件",
        "arg_split_tokens": "按 token 预估把合集切成多个 .md 文件（如 --split-tokens 60000）",
        "arg_no_tree": "不输出目录结构",
        "arg_no_index": "不输出文件索引",
        "arg_no_ai_header": "不输出「给 AI 的阅读说明」",
        "arg_no_smart_order": "禁用智能排序（README/配置/入口优先）",
        "arg_prompt": "附带你的需求/问题，将置于合集最前",
        "arg_prompt_file": "从文件读取需求描述（UTF-8）",
        "arg_clip": "生成后复制到系统剪贴板",
        "arg_stdout": "输出到标准输出而不写文件",
        "arg_dry_run": "只预览将拼接的文件与统计，不生成",
        "arg_config": "指定配置文件（默认自动查找 {cfg}）",
        "arg_no_config": "忽略已存在的配置文件",
        "arg_init_config": "生成 {cfg} 模板后退出",
        "arg_quiet": "静默模式，只输出结果路径",
        "arg_version": "显示版本号",
        # ── 主流程消息 ──
        "err_root_not_dir": "错误：项目目录不存在或不是目录: {root}",
        "err_repo_and_root": "错误：--repo 与本地项目目录不能同时指定。",
        "err_repo_fetch": "错误：无法获取远程仓库快照：{err}",
        "err_init_config_repo": "错误：--init-config 不能与 --repo 同用（模板只能生成在本地目录）。",
        "err_config_exists": "错误：配置文件已存在: {path}（如需重新生成请先删除）",
        "ok_config_created": "✔ 已生成配置模板: {path}",
        "config_hint": " 按需修改后再次运行 proj2md 即可自动读取（命令行参数优先级更高）。language 字段可设 auto / zh / en 切换界面语言。",
        "info_config_loaded": "· 已加载配置文件: {path}",
        "warn_config_parse": "警告：配置文件解析失败（{err}），已忽略。",
        "err_config_root": "配置根节点必须是 JSON 对象",
        "err_no_files": "错误：没有找到任何可拼接的文件。可用 --ext / --include-pattern / --any-text / --include-hidden 调整范围。",
        "err_all_skipped": "错误：所有候选文件都被跳过（过大 / 二进制 / 预算不足）。",
        "warn_prompt_file": "警告：读取 --prompt-file 失败（{err}），已忽略。",
        "part_label": " · 第 {i}/{n} 部分",
        "ok_part_generated": "✔ {name} （{files} 个文件 · ~{tokens} tokens · {size}）",
        "split_hint": "\n提示: 已按 --split-tokens={n} 切成 {total} 卷，请按 part1 → part2 顺序投喂。",
        "ok_clipboard": "✔ 已复制到剪贴板（via {how}）",
        "err_clipboard": "⚠ 复制到剪贴板失败：建议 pip install pyperclip，或手动打开输出文件复制。",
        "cancelled": "\n已取消。",
        # ── 汇总报告 ──
        "sum_generated": "✔ 已生成: {path}",
        "sum_files": " ├─ 文件 : {n} 个",
        "sum_files_skipped": " ├─ 文件 : {n} 个（跳过 {skipped} 个）",
        "sum_hidden": " ├─ 隐藏目录 : 已忽略 {n} 个以 . 开头的文件夹（--include-hidden 可包含）",
        "sum_lines": " ├─ 行数 : {lines}",
        "sum_size": " ├─ 大小 : {size}（UTF-8 Markdown）",
        "sum_tokens": " └─ Token预估: ~{tokens} → {hint}",
        "sum_tip1": "提示: 直接把 .md 内容粘贴给网页 AI —— Markdown 代码块会自动语法高亮，AI 定位文件更轻松。",
        "sum_tip2": " 常用组合: --line-numbers 精确引用行号 · --clip 复制到剪贴板 · --prompt \"你的需求\"",
        # ── dry-run 预览 ──
        "dry_preview": "· 预览：以下 {n} 个文件将被拼接（共 {lines} 行，~{tokens} tokens）",
        "dry_file_item": " {i}. {path} ({lang}, {lines} 行, {size}){flag}",
        "dry_truncated_flag": " [截断]",
        "dry_skipped_head": "\n· 另有 {n} 个文件将被跳过:",
        "dry_skip_item": " - {rel}（{reason}）",
        "dry_more": " ……及另外 {n} 个",
        "dry_hidden_head": "\n· 已忽略 {n} 个隐藏目录（以 . 开头，--include-hidden 可包含）:",
        "dry_tokens": "· Token 预估: ~{tokens} → {hint}",
        "dry_dryrun": "· dry-run 模式，未写入任何文件",
        # ── Token 体量提示 ──
        "hint_moderate": "✅ 体量适中，可直接粘贴给绝大多数网页 AI",
        "hint_long": "⚠️ 较长，部分 AI 输入框有长度限制，建议裁剪或分卷",
        "hint_very_long": "⚠️ 很长，仅长上下文模型（Claude/Gemini 等）能完整读取，建议 --split-tokens 分卷",
        "hint_too_long": "❌ 过长，强烈建议 --exclude-dir / --max-file-lines / --only-ext / --split-tokens 裁剪",
        # ── 跳过原因 / 读取错误 ──
        "skip_unreadable": "无法读取（{cls}）",
        "skip_too_large": "超过单文件上限 {kb:g} KB（实际 {size}），可用 --max-file-kb 调整",
        "skip_read_err": "{err}，未纳入",
        "skip_over_budget": "超出 --max-total-kb 总预算，未纳入",
        "read_fail": "读取失败 {cls}",
        "looks_binary": "疑似二进制",
        "undecodable": "无法解码",
        "truncated_note": "……（该文件共 {orig} 行，超过 --max-file-lines={keep} 限制，此处仅保留前 {keep} 行）\n",
        "empty_file": "（空文件）\n",
        # ── 生成的 Markdown 文档 ──
        "doc_title": "# 项目代码合集：{root}{label}",
        "doc_meta_time": "**生成时间**：{now}",
        "doc_meta_project": "**项目名称**：{root}",
        "doc_meta_files": "**文件数量**：{n} 个",
        "doc_meta_files_skipped": "**文件数量**：{n} 个（另有 {skipped} 个被跳过，见文末附录）",
        "doc_meta_lines": "**代码行数**：{lines} 行",
        "doc_meta_size": "**代码体积**：{size}",
        "doc_meta_tokens": "**Token 预估**：约 {tokens}（粗略估算，实际以平台为准）",
        "doc_ai_header": "## 📖 给 AI 的阅读说明\n\n",
        "ai_notes": """\
本文件是「{root}」项目的源码拼接合集（Markdown 格式），由 proj2md 工具生成。请按以下约定阅读：
1. **目录结构**＝项目整体布局；**文件索引**＝各文件的路径 / 语言 / 行数，其中「起始行」为该文件正文在本文件中的行号，可用于快速定位。
2. 每个源文件对应「源代码正文」中的一个三级标题（`### 序号. 相对路径`），其正文位于紧随其后的围栏代码块中，围栏开头标注了语言标识。所有路径均相对项目根目录。
3. 个别文件若被截断，其代码块末尾会有一行「……该文件共 N 行……」的提示。
4. 引用代码时请使用「相对路径:行号」格式（例如 `src/main.py:42`）；若正文行首带有「 行号 | 」前缀，请以该前缀中的数字为文件内行号。
5. 若「我的需求」中没有给出具体任务，请先简要总结项目结构与所用技术栈，再等待我的进一步指示。""",
        "doc_prompt": "## 🎯 我的需求（请优先阅读）\n\n",
        "doc_tree": "## 🗂 目录结构\n\n",
        "doc_index": "## 📑 文件索引\n\n",
        "doc_index_cols": "| # | 文件路径 | 语言 | 行数 | 起始行 |",
        "doc_source": "## 📄 源代码正文\n\n",
        "doc_lines_unit": "{n} 行",
        "doc_encoding": "编码 `{enc}`",
        "doc_truncated": "**已截断**",
        "doc_appendix_skipped": "## 📎 附录：未包含的文件\n\n",
        "doc_skip_item": "- {path}（{reason}）",
        "doc_more_skipped": "- ……另有 {n} 个文件未列出",
        "doc_appendix_hidden": "## 📎 附录：已忽略的隐藏目录（以 . 开头）\n\n"
                               "如需包含这些目录，请加 `--include-hidden`，或用 "
                               "`--include-pattern \"<目录名>/*\"` 捞回特定目录：\n\n",
        "doc_hidden_item": "- {path}/（隐藏目录，默认忽略）",
        "doc_more_hidden": "- ……另有 {n} 个隐藏目录未列出",
        "doc_end": "---\n\n*END · 共 {n} 个文件 · {lines} 行 · 约 {tokens} tokens · 由 {tool} v{ver} 生成于 {now}*",
    },
    "en": {
        # ── CLI help ──
        "cli_desc": "Project source bundler: merges a whole project into a single Markdown document, ready to paste into web-based AIs.",
        "cli_epilog": """\
Ignore rules (applied in order):
  hidden dirs (on by default) → dir blacklist → file blacklist → glob blacklist → extension whitelist
  ※ --include-pattern has top priority and pierces all ignore rules (incl. hidden dirs)
Common examples:
  python proj2md.py                                # bundle current dir -> project_bundle.md
  python proj2md.py myproject -o bundle.md         # specify project dir and output file
  python proj2md.py --only-ext py md               # bundle only Python and Markdown files
  python proj2md.py --ext proto graphql            # add extensions on top of defaults
  python proj2md.py --exclude-dir tests docs       # exclude extra directories
  python proj2md.py --include-pattern "src/*"      # force-include matching files (top priority)
  python proj2md.py --include-hidden               # don't ignore dot-prefixed folders
  python proj2md.py --include-pattern ".github/*"  # fish back one hidden dir's contents
  python proj2md.py --lang zh                      # switch UI to Chinese (auto/zh/en)
  python proj2md.py --line-numbers                 # line-numbered body for precise AI references
  python proj2md.py --max-file-lines 300           # truncate files beyond 300 lines
  python proj2md.py --max-total-kb 200             # 200KB total budget
  python proj2md.py --split-tokens 60000           # auto-split into several .md volumes
  python proj2md.py --prompt "review my code" --clip  # attach request and copy to clipboard
  python proj2md.py --dry-run                      # preview only, no file written
  python proj2md.py --init-config                  # generate proj2md.json template
Notes:
  Glob rules follow fnmatch; * spans directory levels (e.g. "src/*" matches everything under src).""",
        "arg_help": "show this help message and exit",
        "arg_root": "project root directory (default: current directory)",
        "arg_repo": "remote Git repository URL (no clone; GitHub downloads an archive, others try git archive)",
        "arg_ref": "remote branch, tag, or commit ref (default: HEAD)",
        "arg_output": "output file path (default: {out})",
        "arg_ext": "add extensions on top of the default set, e.g. --ext py md",
        "arg_only_ext": "include only these extensions (replaces the default set)",
        "arg_any_text": "include every non-binary text file (ignores the extension whitelist)",
        "arg_include_hidden": "do not ignore dot-prefixed folders (ignored by default; --include-pattern can still fish one back)",
        "arg_exclude_dir": "extra directory names to exclude",
        "arg_exclude_file": "extra file names to exclude",
        "arg_exclude_pattern": "extra glob patterns to exclude, e.g. *.min.js tests/*",
        "arg_include_pattern": "glob patterns to force-include (highest priority; pierces all ignore rules)",
        "arg_lang": "UI language: auto = follow system / zh = Chinese / en = English (default: auto)",
        "arg_line_numbers": "prefix each body line with its number so the AI can cite precisely",
        "arg_max_file_lines": "keep at most N lines per file, truncate the rest (0 = unlimited)",
        "arg_max_file_kb": "skip files larger than this many KB (default 512)",
        "arg_max_total_kb": "total size budget for the bundle (KB); stop adding files once exceeded",
        "arg_split_tokens": "split the bundle into several .md files by estimated tokens (e.g. --split-tokens 60000)",
        "arg_no_tree": "omit the directory tree section",
        "arg_no_index": "omit the file index section",
        "arg_no_ai_header": "omit the 'Reading Notes for AI' header",
        "arg_no_smart_order": "disable smart ordering (README / config / entry files first)",
        "arg_prompt": "attach your request/question at the very top of the bundle",
        "arg_prompt_file": "read the request description from a file (UTF-8)",
        "arg_clip": "copy the result to the system clipboard after generating",
        "arg_stdout": "print to stdout instead of writing a file",
        "arg_dry_run": "preview the files and stats without writing anything",
        "arg_config": "config file to use (default: auto-look-up {cfg})",
        "arg_no_config": "ignore any existing config file",
        "arg_init_config": "write a {cfg} template, then exit",
        "arg_quiet": "quiet mode; print only the result path",
        "arg_version": "show version and exit",
        # ── main-flow messages ──
        "err_root_not_dir": "Error: project directory does not exist or is not a directory: {root}",
        "err_repo_and_root": "Error: --repo and a local project directory cannot be used together.",
        "err_repo_fetch": "Error: could not fetch remote repository snapshot: {err}",
        "err_init_config_repo": "Error: --init-config cannot be combined with --repo (a template can only be written to a local directory).",
        "err_config_exists": "Error: config file already exists: {path} (delete it first if you want to regenerate)",
        "ok_config_created": "✔ Config template created: {path}",
        "config_hint": " Edit it as needed, then run proj2md again — it is loaded automatically (CLI arguments take priority). Set \"language\" to auto / zh / en to switch the UI language.",
        "info_config_loaded": "· Config file loaded: {path}",
        "warn_config_parse": "Warning: failed to parse config file ({err}); ignored.",
        "err_config_root": "config root must be a JSON object",
        "err_no_files": "Error: no files found to bundle. Adjust the scope with --ext / --include-pattern / --any-text / --include-hidden.",
        "err_all_skipped": "Error: every candidate file was skipped (too large / binary / over budget).",
        "warn_prompt_file": "Warning: failed to read --prompt-file ({err}); ignored.",
        "part_label": " · Part {i}/{n}",
        "ok_part_generated": "✔ {name} ({files} files · ~{tokens} tokens · {size})",
        "split_hint": "\nTip: split into {total} parts by --split-tokens={n}; feed them to the AI in order (part1 → part2 …).",
        "ok_clipboard": "✔ Copied to clipboard (via {how})",
        "err_clipboard": "⚠ Failed to copy to clipboard: try pip install pyperclip, or copy from the output file manually.",
        "cancelled": "\nCancelled.",
        # ── summary report ──
        "sum_generated": "✔ Generated: {path}",
        "sum_files": " ├─ Files : {n}",
        "sum_files_skipped": " ├─ Files : {n} ({skipped} skipped)",
        "sum_hidden": " ├─ Hidden dirs : {n} dot-prefixed folders ignored (--include-hidden to include)",
        "sum_lines": " ├─ Lines : {lines}",
        "sum_size": " ├─ Size : {size} (UTF-8 Markdown)",
        "sum_tokens": " └─ Token est.: ~{tokens} → {hint}",
        "sum_tip1": "Tip: paste the .md straight into a web AI — code blocks get automatic syntax highlighting, which makes file references easier for the AI.",
        "sum_tip2": " Common flags: --line-numbers for precise line refs · --clip to copy · --prompt \"your task\"",
        # ── dry-run preview ──
        "dry_preview": "· Preview: {n} files will be bundled ({lines} lines, ~{tokens} tokens)",
        "dry_file_item": " {i}. {path} ({lang}, {lines} lines, {size}){flag}",
        "dry_truncated_flag": " [truncated]",
        "dry_skipped_head": "\n· {n} more files will be skipped:",
        "dry_skip_item": " - {rel} ({reason})",
        "dry_more": " ...and {n} more",
        "dry_hidden_head": "\n· {n} hidden directories ignored (dot-prefixed; --include-hidden to include):",
        "dry_tokens": "· Token estimate: ~{tokens} → {hint}",
        "dry_dryrun": "· dry-run mode: nothing was written",
        # ── token size hints ──
        "hint_moderate": "✅ Moderate size — can be pasted directly into most web AIs",
        "hint_long": "⚠️ Long — some AI input boxes have length limits; consider trimming or splitting",
        "hint_very_long": "⚠️ Very long — only long-context models (Claude/Gemini etc.) can read it fully; consider --split-tokens",
        "hint_too_long": "❌ Too long — strongly consider trimming with --exclude-dir / --max-file-lines / --only-ext / --split-tokens",
        # ── skip reasons / read errors ──
        "skip_unreadable": "unreadable ({cls})",
        "skip_too_large": "exceeds per-file limit {kb:g} KB (actual {size}); adjust via --max-file-kb",
        "skip_read_err": "{err}; excluded",
        "skip_over_budget": "exceeds --max-total-kb total budget; excluded",
        "read_fail": "read failed: {cls}",
        "looks_binary": "looks binary",
        "undecodable": "undecodable",
        "truncated_note": "...(the file has {orig} lines in total, beyond the --max-file-lines={keep} limit; only the first {keep} lines are kept)\n",
        "empty_file": "(empty file)\n",
        # ── generated Markdown document ──
        "doc_title": "# Project Code Bundle: {root}{label}",
        "doc_meta_time": "**Generated at**: {now}",
        "doc_meta_project": "**Project**: {root}",
        "doc_meta_files": "**Files**: {n}",
        "doc_meta_files_skipped": "**Files**: {n} ({skipped} more skipped — see the appendix at the end)",
        "doc_meta_lines": "**Lines of code**: {lines}",
        "doc_meta_size": "**Code size**: {size}",
        "doc_meta_tokens": "**Token estimate**: ~{tokens} (rough; varies by platform)",
        "doc_ai_header": "## 📖 Reading Notes for AI\n\n",
        "ai_notes": """\
This file is a Markdown bundle of the source code of the "{root}" project, generated by the proj2md tool. Please read it with these conventions:
1. **Directory Tree** = overall layout; **File Index** = each file's path / language / line count, where "Start" is the line number where that file's body begins in this document — handy for quick lookup.
2. Each source file corresponds to one third-level heading under "Source Code" (`### No. relative/path`); its body sits in the fenced code block right below the heading, with a language tag at the opening fence. All paths are relative to the project root.
3. If a file was truncated, the last line of its code block will say "... the file has N lines in total ...".
4. When citing code, use the "relative/path:line" format (e.g. `src/main.py:42`); if body lines carry a " line | " prefix, use the number in that prefix as the in-file line number.
5. If "My Request" contains no specific task, first summarize the project structure and tech stack, then wait for further instructions.""",
        "doc_prompt": "## 🎯 My Request (please read first)\n\n",
        "doc_tree": "## 🗂 Directory Tree\n\n",
        "doc_index": "## 📑 File Index\n\n",
        "doc_index_cols": "| # | File Path | Language | Lines | Start |",
        "doc_source": "## 📄 Source Code\n\n",
        "doc_lines_unit": "{n} lines",
        "doc_encoding": "encoding `{enc}`",
        "doc_truncated": "**truncated**",
        "doc_appendix_skipped": "## 📎 Appendix: Files Not Included\n\n",
        "doc_skip_item": "- {path} ({reason})",
        "doc_more_skipped": "- ...and {n} more files not listed",
        "doc_appendix_hidden": "## 📎 Appendix: Ignored Hidden Directories (dot-prefixed)\n\n"
                               "To include them, pass `--include-hidden`, or fish one back with "
                               "`--include-pattern \"<dir>/*\"`:\n\n",
        "doc_hidden_item": "- {path}/ (hidden dir, ignored by default)",
        "doc_more_hidden": "- ...and {n} more hidden dirs not listed",
        "doc_end": "---\n\n*END · {n} files · {lines} lines · ~{tokens} tokens · generated by {tool} v{ver} at {now}*",
    },
}
_CURRENT_LANG = "zh"   # 当前界面语言，由 set_lang() 写入
def detect_system_lang() -> str:
    """探测操作系统默认语言：任一来源的 locale 以 zh 开头 → 'zh'，否则 'en'。
    依次尝试：环境变量 → locale 模块（抑制弃用警告）→ Windows 用户 UI 语言 API。"""
    codes = []
    for var in ("LC_ALL", "LC_MESSAGES", "LC_CTYPE", "LANG", "LANGUAGE"):
        v = os.environ.get(var)
        if v:
            codes.append(v)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loc = locale.getdefaultlocale()
        if loc and loc[0]:
            codes.append(loc[0])
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            name = locale.windows_locale.get(lid, "")
            if name:
                codes.append(name)
        except Exception:
            pass
    for c in codes:
        if c and str(c).lower().startswith("zh"):
            return "zh"
    return "en"
def set_lang(lang) -> str:
    """解析并设置界面语言。'auto'/None/空 → 探测系统；'zh-CN'/'en_US.UTF-8'
    之类自动取主语言码；未支持的语言回退英文。返回最终生效语言。"""
    global _CURRENT_LANG
    s = str(lang if lang is not None else "auto").strip().lower()
    if s in ("", "auto", "system", "default"):
        _CURRENT_LANG = detect_system_lang()
    else:
        s = s.replace("-", "_").split("_")[0].split(".")[0]
        _CURRENT_LANG = s if s in LANG_TEXTS else "en"
    return _CURRENT_LANG
def t(key: str, **kw) -> str:
    """取当前语言的文案；缺 key 时回退英文，再缺则返回 key 本身。
    无 kw 时不做 format（避免文案中的花括号引发异常）。"""
    text = LANG_TEXTS.get(_CURRENT_LANG, {}).get(key)
    if text is None:
        text = LANG_TEXTS["en"].get(key, key)
    return text.format(**kw) if kw else text
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
def discover(cfg: Config):
    """遍历项目收集候选文件。返回。
    目录剪枝顺序：include-pattern 覆盖 > 隐藏目录忽略 > 目录黑名单。"""
    root = cfg.root
    out_abs = cfg.output.expanduser().resolve()
    cfg_abs = cfg.config_path.resolve() if cfg.config_path else None
    self_abs = Path(__file__).resolve() if "__file__" in globals() else None
    found, pruned_hidden = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        kept = []
        for d in sorted(dirnames):
            rel_dir = (Path(dirpath) / d).relative_to(root).as_posix()
            # 强制包含规则优先：可能被 include-pattern 覆盖的目录一律不剪
            if _dir_may_be_included(rel_dir, cfg.include_patterns):
                kept.append(d)
                continue
            # 隐藏目录：以 . 开头且开启忽略 → 整目录剪掉
            if cfg.exclude_hidden and d.startswith("."):
                pruned_hidden.append(rel_dir)
                continue
            # 目录黑名单
            if d.lower() in cfg.exclude_dirs:
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
            if pa == out_abs or (cfg_abs and pa == cfg_abs) or (self_abs and pa == self_abs):
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
    total = 0
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
        if budget and records and total + len(text) > budget:
            skipped.append((rel.as_posix(), t("skip_over_budget")))
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
        records.append(FileRec(
            rel=rel, abspath=p, language=lang_of(p), encoding=enc,
            content=text, lines=len(text.splitlines()), chars=len(text),
            nbytes=size, truncated=truncated, orig_lines=orig_lines,
        ))
        total += len(text)
    return records, skipped
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
    tot_chars = sum(r.chars for r in records)
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
        "- " + t("doc_meta_size", size=fmt_size(tot_chars)),
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
# ─────────────────────────── 剪贴板 ───────────────────────────
def _win_clipboard(text: str) -> bool:
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
            f.write(text)
        ps = ("$t = Get-Content -LiteralPath '%s' -Raw -Encoding UTF8; "
              "Set-Clipboard -Value $t" % path.replace("'", "''"))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       check=True, timeout=60, capture_output=True)
        return True
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
def copy_clipboard(text: str):
    try:
        import pyperclip  # type: ignore
        pyperclip.copy(text)
        return True, "pyperclip"
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            try:
                if _win_clipboard(text):
                    return True, "PowerShell"
            except Exception:
                subprocess.run(["clip"], input=text.encode("utf-16-le"),
                               check=True, capture_output=True)
                return True, "clip"
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"),
                           check=True, capture_output=True)
            return True, "pbcopy"
        else:
            for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"],
                        ["xsel", "--clipboard", "--input"]):
                if shutil.which(cmd[0]):
                    subprocess.run(cmd, input=text.encode("utf-8"),
                                   check=True, capture_output=True)
                    return True, cmd[0]
    except Exception:
        pass
    return False, ""
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
    p.add_argument("--max-file-lines", type=int, default=None, metavar="N",
                   help=t("arg_max_file_lines"))
    p.add_argument("--max-file-kb", type=float, default=None, metavar="KB",
                   help=t("arg_max_file_kb"))
    p.add_argument("--max-total-kb", type=float, default=None, metavar="KB",
                   help=t("arg_max_total_kb"))
    p.add_argument("--split-tokens", type=int, default=None, metavar="N",
                   help=t("arg_split_tokens"))
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
    p.add_argument("--quiet", action="store_true", help=t("arg_quiet"))
    p.add_argument("--version", action="store_true", help=t("arg_version"))
    return p.parse_args(argv)
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
        exts = {normalize_ext(e) for e in args.only_ext}
    elif args.ext:
        exts |= {normalize_ext(e) for e in args.ext}
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
def load_prompt(args) -> str:
    if args.prompt:
        return args.prompt.strip()
    if args.prompt_file:
        try:
            return Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except Exception as e:
            cprint(t("warn_prompt_file", err=e))
    return ""

# ─────────────────────────── 远程仓库（不 clone） ───────────────────────────
def github_repo(url: str):
    """将常见的 GitHub HTTPS/SSH URL 解析为 (owner, repo)，否则返回 None。"""
    clean = url.strip().split("?", 1)[0].split("#", 1)[0].rstrip("/")
    m = re.match(r"^(?:(?:https?|ssh)://(?:[^@/]+@)?|[^@/:]+@)?(?:www\.)?github\.com[/:]([^/\s:]+)/([^/\s]+)$", clean,
                 re.IGNORECASE)
    if not m:
        return None
    owner, repo = m.groups()
    if repo.endswith(".git"):
        repo = repo[:-4]
    return (owner, repo) if owner and repo else None

def _safe_archive_path(name: str) -> Path | None:
    """拒绝绝对路径 / 盘符路径 / ..，避免不可信归档写出临时目录。

    盘符路径（如 "C:x"）在 Windows 上 is_absolute() 为 False，但用它做 / 运算
    会得到 "C:x" —— 相对当前盘工作目录，从而逃出目标目录，故一并拒绝。
    """
    if not name:
        return None
    pure = Path(*name.replace("\\", "/").split("/"))
    if pure.is_absolute() or pure.drive or ".." in pure.parts:
        return None
    return pure

def extract_tar(data: bytes, destination: Path) -> Path:
    """安全展开 tar/tar.gz，并去掉归档共有的顶层目录（若存在）。"""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        members = [m for m in archive.getmembers() if m.isfile() or m.isdir()]
        paths = [(m, _safe_archive_path(m.name)) for m in members]
        paths = [(m, p) for m, p in paths if p]
        file_paths = [p for member, p in paths if member.isfile()]
        first = {p.parts[0] for p in file_paths if len(p.parts) > 1}
        strip_top = (next(iter(first)) if len(first) == 1
                     and file_paths and all(len(p.parts) > 1 for p in file_paths) else None)
        for member, rel in paths:
            if strip_top:
                if len(rel.parts) == 1:  # 归档的顶层目录本身
                    continue
                rel = Path(*rel.parts[1:])
            target = destination / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is not None:
                with source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
    return destination

def fetch_remote_repo(url: str, ref: str | None, destination: Path) -> tuple[Path, str]:
    """下载一个远程仓库快照；GitHub 走归档 API，其他服务器走 git archive。"""
    ref = ref or "HEAD"
    parsed = github_repo(url)
    try:
        if parsed:
            owner, repo = parsed
            endpoint = "https://api.github.com/repos/{}/{}/tarball/{}".format(
                urllib.parse.quote(owner, safe=""), urllib.parse.quote(repo, safe=""),
                urllib.parse.quote(ref, safe=""))
            headers = {"User-Agent": "proj2md", "Accept": "application/vnd.github+json"}
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            with urllib.request.urlopen(urllib.request.Request(endpoint, headers=headers), timeout=60) as response:
                payload = response.read()
            label = f"{owner}/{repo}@{ref}"
        else:
            cmd = ["git", "archive", "--format=tar", f"--remote={url}", ref]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if result.returncode:
                detail = result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(detail or "git archive failed")
            payload = result.stdout
            name = Path(url.rstrip("/")).stem
            if name.endswith(".git"):
                name = name[:-4]
            label = f"{name}@{ref}"
        if not payload:
            raise RuntimeError("remote archive is empty")
        return extract_tar(payload, destination), label
    except (OSError, urllib.error.URLError, tarfile.TarError, RuntimeError) as e:
        raise RuntimeError(str(e)) from e
# ─────────────────────────── 主流程 ───────────────────────────
def main(argv=None):
    args = parse_args(argv)
    if args.version:
        cprint(f"{TOOL} v{VERSION}")
        return 0
    remote_tmp = None
    root_label = None
    if args.repo:
        if args.root:
            cprint(t("err_repo_and_root"))
            return 2
        if args.init_config:
            cprint(t("err_init_config_repo"))
            return 2
        try:
            remote_tmp = tempfile.TemporaryDirectory(prefix="proj2md-")
            root, root_label = fetch_remote_repo(args.repo, args.ref, Path(remote_tmp.name))
        except RuntimeError as e:
            if remote_tmp:
                remote_tmp.cleanup()
            cprint(t("err_repo_fetch", err=e))
            return 1
    else:
        root = Path(args.root or ".").expanduser().resolve()
        root_label = root.name
    quiet = args.quiet
    cfg_path = (Path(args.config).expanduser().resolve()
                if args.config else (Path(remote_tmp.name) / CONFIG_FILENAME if remote_tmp else root / CONFIG_FILENAME))
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
    return 0

def cli() -> None:
    """命令行入口：pip/pipx 安装后由 `proj2md` 可执行文件调用。"""
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        cprint(t("cancelled"))
        sys.exit(130)


if __name__ == "__main__":   # 保留：直接 python proj2md.py 依然可用
    cli()
