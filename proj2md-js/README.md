# proj2md

[![npm version](https://img.shields.io/npm/v/proj2md)](https://www.npmjs.com/package/proj2md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

**把整个项目合并成一份 Markdown，直接投喂给网页端 AI** —— Node.js 版，`npx` / `npm i -g` 即用，**零必需依赖，不需要 Python**。

> Bundle a whole project into a single Markdown document for web-based AI tools (ChatGPT / Claude / Gemini / Grok / DeepSeek / GLM / Kimi …).
> Pure Node.js — run it with `npx`, no Python required.

输出结构：元信息 → 给 AI 的阅读说明 → 我的需求（可选）→ 目录结构 → 文件索引（含起始行号）→ 源代码正文（带语法高亮围栏）→ 附录（被跳过的文件 / 被忽略的隐藏目录）。

```text
project_bundle.md
├─ # 项目代码合集：my-project
├─ ## 📖 给 AI 的阅读说明
├─ ## 🗂 目录结构
├─ ## 📑 文件索引        (路径 / 语言 / 行数 / 起始行，可点击跳转)
├─ ## 📄 源代码正文      (### 1. src/main.py + 围栏代码块)
└─ --- *END · …*
```

---

## 🚀 快速开始

```bash
# 免安装，直接运行：拼接当前目录 -> project_bundle.md
npx proj2md

# 指定项目目录与输出文件
npx proj2md ./my-project -o bundle.md

# 只拼接 js / ts / md，并给正文加行号（方便 AI 精确引用）
npx proj2md --only-ext js ts md --line-numbers

# 附带你的需求，并复制到剪贴板
npx proj2md --prompt "帮我找出潜在 bug" --clip
```

全局安装后直接使用 `proj2md` 命令：

```bash
npm install --global proj2md
proj2md --help
```

要求 **Node.js >= 14**。

## 📖 常用示例

```bash
proj2md --ext proto graphql           # 在默认扩展名范围上追加
proj2md --exclude-dir tests docs      # 额外排除目录
proj2md --include-pattern "src/*"     # 强制包含（优先级最高，可穿透一切忽略规则）
proj2md --include-hidden              # 不忽略 . 开头的文件夹
proj2md --include-pattern ".github/*" # 只捞回某个隐藏目录
proj2md --max-file-lines 300          # 单文件超过 300 行则截断
proj2md --max-total-kb 200            # 总体积预算 200KB
proj2md --split-tokens 60000          # 体积过大时自动切成多个分卷
proj2md --lang en                     # 界面切英文（auto / zh / en）
proj2md --dry-run                     # 只预览，不写文件
proj2md --init-config                 # 生成 proj2md.json 配置模板
```

## ⚙️ 主要参数

| 参数 | 说明 |
| --- | --- |
| `[root]` | 项目根目录（默认当前目录） |
| `-o, --output <file>` | 输出文件（默认 `project_bundle.md`） |
| `--ext <e...>` / `--only-ext <e...>` | 追加扩展名 / 只用这些扩展名 |
| `--any-text` | 包含所有非二进制文本文件（忽略扩展名白名单） |
| `--include-hidden` | 不忽略以 `.` 开头的文件夹 |
| `--exclude-dir` / `--exclude-file` / `--exclude-pattern` | 追加排除的目录名 / 文件名 / 通配符 |
| `--include-pattern <p...>` | 强制包含的通配符（最高优先级） |
| `--line-numbers` | 正文每行加行号，AI 引用更精准 |
| `--max-file-lines N` | 单文件最多保留 N 行，超出截断（0=不限） |
| `--max-file-kb KB` | 超过此大小的文件跳过（默认 512） |
| `--max-total-kb KB` | 合集总预算，超出后停止追加 |
| `--split-tokens N` | 按 token 预估切成多个 `.md` 分卷 |
| `--prompt "..."` / `--prompt-file FILE` | 附带需求，置于合集最前 |
| `--clip` | 生成后复制到系统剪贴板 |
| `--stdout` | 输出到标准输出而不写文件 |
| `--dry-run` | 只预览将拼接的文件与统计 |
| `--config PATH` / `--no-config` / `--init-config` | 指定 / 忽略 / 生成配置文件 |
| `--lang {auto,zh,en}` | 界面语言（默认 `auto`，跟随系统） |
| `--quiet` | 静默模式，只输出结果路径 |
| `-h, --help` / `--version` | 帮助 / 版本号 |

忽略规则按顺序生效：**隐藏目录（默认开）→ 目录黑名单 → 文件黑名单 → 通配符黑名单 → 扩展名白名单**，
其中 `--include-pattern` 优先级最高，可穿透以上所有规则。通配符遵循 `fnmatch` 语义，`*` 可跨目录层级，大小写不敏感。

## 🪟 配置文件 `proj2md.json`

放在项目根目录即自动加载，**命令行参数优先级高于配置文件**；键名与 Python 版完全互通：

```json
{
  "language": "auto",
  "output": "project_bundle.md",
  "exts": [],
  "any_text": false,
  "exclude_hidden": true,
  "exclude_dirs": [],
  "exclude_files": [],
  "exclude_patterns": [],
  "include_patterns": [],
  "line_numbers": false,
  "max_file_lines": 0,
  "max_file_kb": 512,
  "max_total_kb": 0,
  "split_tokens": 0,
  "show_tree": true,
  "show_index": true,
  "ai_header": true,
  "smart_order": true,
  "clip": false
}
```

`proj2md --init-config` 一键生成模板。

## 🔧 细节

- **编码识别**：`utf-8-sig → utf-8 → gbk → big5 → latin-1`，自动识别，无需手动指定；GBK/Big5 依赖可选依赖 [`iconv-lite`](https://www.npmjs.com/package/iconv-lite)（缺失时自动降级为 latin-1，其余功能不受影响）。
- **智能排序**：`README` / 项目清单（`package.json`、`pyproject.toml`、`requirements.txt`…）/ 入口文件（`main`、`app`、`index`…）优先，其余按路径排序。
- **剪贴板**：Windows 用 PowerShell / `clip`，macOS 用 `pbcopy`，Linux 用 `wl-copy` / `xclip` / `xsel`，全部走系统原生命令，无需第三方依赖。
- **输出**：与 Python 版 `proj2md.py` 结构完全一致，可无缝互换。

## 🧪 开发与发布

```bash
npm test                              # 冒烟测试（临时目录里跑一遍完整流程）
npm start -- --help                   # 等价于 node bin/proj2md.js --help
npm publish --dry-run                 # 检查将被打包的文件
npm publish                           # 发布到 npm（账号开启 2FA 时会提示输入 OTP）
```

发布后任何人即可直接运行：

```bash
npx proj2md --help
npx proj2md ./my-project --prompt "帮我审查代码" --clip
```

## 📄 License

MIT © 苍天在上晚自习

---

## English (short)

`npx proj2md` merges an entire project into one Markdown file, ready to paste into a web-based AI.

- No required dependencies, no Python, Node.js >= 14.
- Bilingual UI (`--lang auto|zh|en`), config file `proj2md.json`, ignore rules, smart ordering, split volumes, clipboard support — all included.
- Encoding chain `utf-8-sig → utf-8 → gbk → big5 → latin-1` (GBK/Big5 via the optional `iconv-lite` dependency; everything else still works without it).

```bash
npx proj2md ./my-project -o bundle.md
npx proj2md --only-ext js ts md --line-numbers --clip
npx proj2md --prompt "review my code" --split-tokens 60000
npx proj2md --dry-run
```

Full documentation (Chinese/English) lives in the repository:
<https://github.com/Avlorayne/proj2md>