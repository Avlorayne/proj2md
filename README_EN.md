<div align="center">

# proj2md.py
[简体中文](./README.md) | **English**  

🗂 **Project source bundler** — merge an entire project into a single Markdown file, ready to paste into web-based AIs  
`(ChatGPT / Claude / Gemini / Grok / DeepSeek / GLM / Kimi …)`    

[![PyPI](https://img.shields.io/pypi/v/proj2md-py)](https://pypi.org/project/proj2md-py/)
[![Python](https://img.shields.io/pypi/pyversions/proj2md-py)](https://pypi.org/project/proj2md-py/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)  
[![npm](https://img.shields.io/npm/v/proj2md)](https://www.npmjs.com/package/proj2md)  
`Python 3.8+` · Zero dependencies · Single-file script [proj2md](./proj2md.py) · v2.3.0

</div>

---

## Table of Contents

- [✨ Features](#-features)
- [🚀 Quick Start](#-quick-start)
- [📖 Common Examples](#-common-examples)
- [⚙️ CLI Options](#-cli-options)
- [🙈 Ignore Rules](#-ignore-rules)
- [🧠 Smart Ordering](#-smart-ordering)
- [📄 Generated Document Layout](#-generated-document-layout)
- [🌐 Multilingual UI](#-multilingual-ui)
- [🪟 Config File](#-config-file)
- [📏 Size & Token Budget](#-size--token-budget)
- [💡 Tips & FAQ](#-tips--faq)
- [🧱 Repository Layout](#-repository-layout)
- [📜 License](#-license)

## ✨ Features
- 🗂 **One-command bundling**: walks the whole project and merges code / config / docs into one `.md` file
- 📑 **Structured output**: metadata + directory tree + file index table + syntax-highlighted code blocks + appendices
- 🔗 **File index**: anchor links and "start line" numbers for every file — quick lookup for both AI and humans
- 🧠 **Smart ordering**: README, manifests and entry files come first, so the AI reads the most important content early
- 🔢 **Precise citation**: `--line-numbers` prefixes body lines so the AI can cite `path:line`
- 📏 **Size control**: per-file line limit / per-file size cap / total budget / automatic token-based splitting
- 🙈 **Five-layer ignore rules**: hidden dirs → dir blacklist → file blacklist → globs → extension whitelist, with `--include-pattern` piercing everything
- 🌐 **Multilingual UI**: follows the system language by default; `--lang zh / en` to switch (help, reports and generated docs all follow)
- 🎯 **Request up front**: `--prompt` puts your task at the very top of the bundle
- 📋 **Clipboard**: cross-platform `--clip` (pyperclip / PowerShell / pbcopy / wl-copy / xclip / xsel)
- 🈶 **Encoding friendly**: auto-detects UTF-8 / GBK / Big5 / Latin-1; falls back to ASCII symbols on limited terminals
- 🪟 **Config file**: persist every option in `proj2md.json`; `--init-config` writes a template
- 👀 **Dry-run preview**: see exactly what would be bundled before writing anything
- 🌐 **Remote repository input**: bundle a GitHub URL at a selected ref without running `git clone`

## 🚀 Quick Start

### Option 1: install with uv (recommended)

Published on PyPI as `proj2md-py` (the terminal command is `proj2md`):

```bash
# Run once without installing (uv ships uvx)
uvx proj2md-py --prompt "Find potential bugs and suggest fixes"
# Or install globally, then just use the proj2md command
uv tool install proj2md-py

# Bundle current directory -> project_bundle.md
proj2md
# Bundle a specific project and copy to clipboard
proj2md /path/to/project --clip
# Attach your request along with the code
proj2md --prompt "Find potential bugs and suggest fixes"
```

> `pip` users: `pip install proj2md-py`, or `pip install "proj2md-py[clip]"` to include clipboard support.

### Option 2: run the script directly

No installation needed (the only optional dependency is `pyperclip`, used by `--clip`):

```bash
python proj2md.py
python proj2md.py /path/to/project --clip
```

### Option 3: npx / npm (Node.js edition, no Python required)

Also published to npm (same package name `proj2md`, same commands). Node.js ≥ 14, zero required dependencies:

```bash
# zero-install
npx proj2md
npx proj2md /path/to/project -o bundle.md
npx proj2md --only-ext js ts md --line-numbers --clip

# or install it globally
npm install -g proj2md
```

> `iconv-lite` is an optional dependency (GBK / Big5 detection only) and degrades gracefully when missing; the rest keeps working. The generated Markdown is identical in structure to the Python edition — the two are drop-in interchangeable.
> Node source lives in [`proj2md-js/`](./proj2md-js); see [proj2md-js/README.md](./proj2md-js/README.md).

Then paste the content of `project_bundle.md` straight into a web AI — code blocks get automatic syntax highlighting.

## 📖 Common Examples

> The examples below use the installed `proj2md` command; when running from source, replace `proj2md` with `python proj2md.py`.

```bash
proj2md --only-ext py md            # bundle only Python and Markdown
proj2md --ext proto graphql         # add extensions on top of defaults
proj2md --exclude-dir tests docs    # exclude extra directories
proj2md --include-pattern "src/*"   # force-include (top priority)
proj2md --include-hidden            # don't ignore dot-prefixed folders
proj2md --include-pattern ".github/*"  # fish back one hidden dir
proj2md --line-numbers              # line-numbered body for precise refs
proj2md --max-file-lines 300        # truncate files beyond 300 lines
proj2md --max-total-kb 200          # 200KB total budget
proj2md --split-tokens 60000        # auto-split into volumes
proj2md --lang zh                   # switch UI to Chinese
proj2md --dry-run                   # preview only
proj2md --init-config               # write config template
proj2md --repo https://github.com/owner/repo --ref main -o bundle.md  # bundle a remote repository without cloning
```

> For `--repo`, GitHub uses its source-archive endpoint; set `GITHUB_TOKEN` or `GH_TOKEN` for a private repository. Other Git hosts are tried with `git archive --remote`, which requires the server to support `git-upload-archive`. A remote snapshot includes only committed files at the selected ref—not uncommitted work, history, populated submodules, or LFS object contents.
>
> Both editions pick up a proxy automatically: the Python edition uses the standard library's system-proxy handling, and the Node edition reads `HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY` (either case) plus, on Windows, the system proxy configured in Internet Options.

## ⚙️ CLI Options

**Input & output**

| Option | Description |
|---|---|
| `root` (positional) | project root directory (default: current directory) |
| `--repo <url>` | remote Git repository URL; download a snapshot and bundle it without cloning (cannot be combined with `root`) |
| `--ref <ref>` | branch, tag, or commit ref used with `--repo` (default `HEAD`) |
| `-o, --output <file>` | output file path (default `project_bundle.md`) |
| `--stdout` | print to stdout instead of writing a file |
| `--clip` | copy the result to the system clipboard |

**File scope**

| Option | Description |
|---|---|
| `--ext <ext...>` | **append** extensions to the default whitelist |
| `--only-ext <ext...>` | only include these extensions (**replaces** defaults) |
| `--any-text` | include every non-binary text file |
| `--include-hidden` | don't ignore dot-prefixed folders |
| `--exclude-dir <dir...>` | extra directories to exclude |
| `--exclude-file <name...>` | extra file names to exclude |
| `--exclude-pattern <pat...>` | extra glob patterns, e.g. `*.min.js tests/*` |
| `--include-pattern <pat...>` | force-include (highest priority, pierces all rules) |

**Size control**

| Option | Description |
|---|---|
| `--max-file-lines <n>` | keep at most n lines per file (0 = unlimited) |
| `--max-file-kb <kb>` | skip files larger than this (default 512) |
| `--max-total-kb <kb>` | total size budget for the bundle (KB) |
| `--split-tokens <n>` | split into multiple `.partN.md` volumes by token estimate |

**Output content**

| Option | Description |
|---|---|
| `--line-numbers` | prefix each body line with its number |
| `--prompt <text>` | attach your request at the top of the bundle |
| `--prompt-file <file>` | read the request from a file (UTF-8) |
| `--no-tree` / `--no-index` | omit directory tree / file index |
| `--no-ai-header` | omit the "Reading Notes for AI" section |
| `--no-smart-order` | disable smart ordering |

**Misc**

| Option | Description |
|---|---|
| `--lang <auto\|zh\|en>` | UI language (default: auto = follow system) |
| `--config <file>` / `--no-config` | specify / ignore the config file |
| `--init-config` | write a `proj2md.json` template, then exit |
| `--dry-run` | preview files and stats without writing |
| `--quiet` | quiet mode; print only the result path |
| `--version` / `-h, --help` | version / help |

## 🙈 Ignore Rules

Applied in order — the first matching rule skips the file:

1. **Hidden dirs** (on by default): dot-prefixed folders are pruned entirely → disable with `--include-hidden`
2. **Dir blacklist**: built-ins (`node_modules`, `__pycache__`, `venv`, `dist`, `build`, …) + `--exclude-dir`
3. **File blacklist**: lock files (`package-lock.json`, `poetry.lock`, …) + `--exclude-file`
4. **Glob blacklist**: `*.min.js`, `*.png`, `*.zip`, `*.log`, … + `--exclude-pattern`
5. **Extension whitelist**: only whitelisted extensions are collected → tune via `--ext` / `--only-ext` / `--any-text`
> ⭐ `--include-pattern` has top priority: matching files are force-included even if they hit any rule above, and the rule can pierce the hidden-dir filter.

Also note:
- The output file, config file and the script itself are always self-excluded;
- Binary-looking / undecodable / oversized files are not silently lost — they are listed in the appendix;
- Dot-prefixed **files** (like `.gitignore`) are not affected by the hidden-dir rule and are collected normally.

## 🧠 Smart Ordering

Files inside the bundle are sorted by priority so the AI reads key content first:

| Priority | File type |
|:---:|---|
| 0 | `README*` |
| 1 | Manifests & config: `package.json`, `pyproject.toml`, `requirements.txt`, `Dockerfile`, `.gitignore`, … |
| 2 | Entry files (`main` / `app` / `index` / `server` / `cli`…) and `config` / `settings` |
| 3 | Everything else (sorted by path) |

## 📄 Generated Document Layout

```
# Project Code Bundle: <name>
├─ Metadata (generated at / file count / lines / token estimate)
├─ 📖 Reading Notes for AI (citation conventions, etc.)
├─ 🎯 My Request (--prompt, if provided)
├─ 🗂 Directory Tree
├─ 📑 File Index (anchor links + start lines)
├─ 📄 Source Code (### No. relative/path + highlighted code blocks)
├─ 📎 Appendix: Files Not Included
├─ 📎 Appendix: Ignored Hidden Directories
└─ END footer with totals
```

Even if the source contains ` ``` ` fences, the structure stays intact — fence length adapts automatically.

## 🌐 Multilingual UI

Resolution order: **`--lang` flag > config file `language` field > system auto-detection > English fallback**.

```bash
proj2md --lang en      # English for this run (help & reports included)
proj2md --lang zh      # force Chinese
proj2md --lang auto    # follow system (overrides config file)
```

- `auto` (default): probes environment variables (`LC_ALL` / `LANG`…) → the `locale` module → the Windows UI-language API; anything starting with `zh` maps to Chinese, otherwise English;
- You can also persist it in `proj2md.json` as `"language": "zh"`;
- Switching affects more than console output — titles, AI reading notes, index headers and appendices inside the generated `.md` follow the language too.

## 🪟 Config File

```bash
proj2md --init-config   # write proj2md.json template
```

Edit as needed; it is picked up automatically on the next run:

```json
{
  "language": "auto",
  "output": "project_bundle.md",
  "exts": [],
  "line_numbers": true,
  "max_file_lines": 400,
  "exclude_dirs": ["docs", "benchmarks"],
  "include_patterns": [],
  "split_tokens": 0,
  "clip": false
}
```

Priority: **CLI arguments > config file > built-in defaults** ; unneeded keys can simply be deleted.

## 📏 Size & Token Budget

Tokens are roughly estimated (CJK ≈ 1.1 tokens/char, others ≈ 3.8 chars/token); a hint is printed after generation:

| Estimated tokens | Advice |
|---|---|
| < 30k | ✅ Moderate — paste directly |
| 30k – 100k | ⚠️ Some input boxes have limits; consider trimming |
| 100k – 200k | ⚠️ Needs a long-context model, or split with `--split-tokens` |
| > 200k | ❌ Trim (`--exclude-dir` / `--max-file-lines` / `--only-ext`) or split |

## 💡 Tips & FAQ

- **Precise citations**: ask the AI (via `--prompt`) to cite code as `relative/path:line`; combine with `--line-numbers` for best results.
- **Split volumes**: `--split-tokens` produces `xxx.part1.md`, `xxx.part2.md`… — feed them in order; appendices only appear in the last part.
- **AI forgot the layout?** Re-paste just the "Directory Tree" and "File Index" sections instead of the whole bundle.
- **Garbled Chinese on Windows?** The script auto-degrades CJK symbols to ASCII; you can also run `chcp 65001` first.
- **`--clip` failing?** `pip install pyperclip`, or copy manually from the output file.
- **Full-control mode**: `--any-text` plus `--include-hidden` collects every text file in the project.

## 🧱 Repository Layout

The same feature set ships as two implementations with identical CLI options, identical `proj2md.json` keys and identical generated Markdown — pick whichever runtime you already have.

```
proj2md/
├── proj2md.py           # Python edition: single-file script, standard library only (Python 3.8+)
├── pyproject.toml       #   └─ packaged as the PyPI project proj2md-py (uv / pip)
├── tests/               #   └─ regression tests: python tests/test_proj2md.py
├── README.md / README_EN.md
└── proj2md-js/          # Node edition: pure Node.js, zero required dependencies (Node.js >= 14)
    ├── bin/proj2md.js   #   └─ published to npm as proj2md (npx / npm)
    ├── lib/             #      discover / reader / render / i18n / remote …
    ├── test/smoke.js    #      smoke test: npm test
    └── package.json
```

| | Python edition | Node edition |
|---|---|---|
| Package name | `proj2md-py` (PyPI) | `proj2md` (npm) |
| Install | `uvx proj2md-py` / `uv tool install proj2md-py` / `pip install proj2md-py` | `npx proj2md` / `npm i -g proj2md` |
| Runtime | Python 3.8+, no third-party deps | Node.js >= 14, optional `iconv-lite` |
| Version lives in | [pyproject.toml](./pyproject.toml) | [proj2md-js/package.json](./proj2md-js/package.json) |

Both editions produce byte-identical output for the same project and options; `tests/test_proj2md.py` asserts the version numbers stay in sync.

```bash
python tests/test_proj2md.py    # Python edition regression tests
cd proj2md-js && npm test       # Node edition smoke tests
```

> Bump both version numbers together when releasing. npm publishes automatically from a GitHub Release via [npm-publish.yml](./.github/workflows/npm-publish.yml) (Trusted Publishing, no token); PyPI is published locally with `uv build && uv publish`.

## 📜 License
[MIT](./LICENSE) © 2025
