<div align="center">

# proj2md.py
**简体中文** | [English](./README_EN.md)  
  
🗂 **项目源码一键拼接工具** —— 把整个项目合并成一份 Markdown，直接投喂给网页端 AI  
`(ChatGPT / Claude / Gemini / Grok / DeepSeek / GLM / Kimi …) ` 

[![PyPI](https://img.shields.io/pypi/v/proj2md-py)](https://pypi.org/project/proj2md-py/)
[![Python](https://img.shields.io/pypi/pyversions/proj2md-py)](https://pypi.org/project/proj2md-py/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)  
[![npm](https://img.shields.io/npm/v/proj2md)](https://www.npmjs.com/package/proj2md)  
`Python 3.8+` · 零第三方依赖 · 单文件脚本 [proj2md](./proj2md.py) · v2.3.0  

</div>

---

## 目录

- [✨ 功能特性](#-功能特性)
- [🚀 快速开始](#-快速开始)
- [📖 常用示例](#-常用示例)
- [⚙️ 命令行参数](#-命令行参数)
- [🙈 忽略规则](#-忽略规则)
- [🧠 智能排序](#-智能排序)
- [📄 生成文档结构](#-生成文档结构)
- [🌐 多语言界面](#-多语言界面)
- [🪟 配置文件](#-配置文件)
- [📏 体积与 Token 预算](#-体积与-token-预算)
- [💡 使用技巧与 FAQ](#-使用技巧与-faq)
- [🧱 项目结构](#-项目结构)
- [📜 许可证](#-许可证)

## ✨ 功能特性

- 🗂 **一键拼接**：遍历整个项目，把代码 / 配置 / 文档合并为单个 `.md` 文件
- 📑 **结构化输出**：元信息 + 目录树 + 文件索引表 + 语法高亮代码块 + 附录
- 🔗 **文件索引**：每个文件带锚点链接和「起始行号」，AI 与人都能快速定位
- 🧠 **智能排序**：README、配置清单、入口文件优先，AI 先读到最关键的内容
- 🔢 **精确引用**：`--line-numbers` 为正文加行号，AI 可用 `路径:行号` 引用代码
- 📏 **体积可控**：单文件行数 / 单文件大小 / 总预算 / 按 Token 自动分卷
- 🙈 **五层忽略规则**：隐藏目录 → 目录黑名单 → 文件黑名单 → 通配符 → 扩展名白名单，且 `--include-pattern` 可强制穿透
- 🌐 **多语言界面**：自动跟随系统语言，支持 `--lang zh / en` 手动切换（帮助、报告、生成的文档说明全部跟随）
- 🎯 **需求直达**：`--prompt` 把你的任务放在合集最前面，AI 第一眼看到
- 📋 **剪贴板**：`--clip` 跨平台复制（pyperclip / PowerShell / pbcopy / wl-copy / xclip / xsel）
- 🈶 **编码友好**：自动识别 UTF-8 / GBK / Big5 / Latin-1；终端不支持中文时自动降级 ASCII
- 🪟 **配置文件**：`proj2md.json` 持久化所有参数，`--init-config` 一键生成模板
- 👀 **dry-run 预览**：先看会拼接哪些文件，再决定是否生成
- 🌐 **远程仓库直出**：传入 GitHub 仓库链接即可下载指定版本的源码归档并生成合集，无需 `git clone`

## 🚀 快速开始

### 方式一：uv 安装（推荐）

已发布到 PyPI（包名 `proj2md-py`，终端命令为 `proj2md`）：

```bash
# 免安装，临时运行（uv 0.3+ 自带 uvx）
uvx proj2md-py --prompt "帮我找出潜在 bug 并给出修复建议"
# 或全局安装，之后直接使用 proj2md 命令
uv tool install proj2md-py

# 拼接当前目录 -> project_bundle.md
proj2md
# 拼接指定项目，并复制到剪贴板
proj2md /path/to/project --clip
# 附带你的需求一起投喂
proj2md --prompt "帮我找出潜在 bug 并给出修复建议"
```

> `pip` 用户：`pip install proj2md-py`，或 `pip install "proj2md-py[clip]"` 一并装上剪贴板支持。

### 方式二：直接运行脚本

无需安装，克隆仓库后直接运行（唯一可选依赖 `pyperclip`，仅 `--clip` 需要）：

```bash
python proj2md.py
python proj2md.py /path/to/project --clip
```

### 方式三：npx / npm（Node.js 版，无需 Python）

已发布到 npm（包名同为 `proj2md`，命令用法完全一致），只要 Node.js ≥ 14，零必需依赖：

```bash
# 免安装直接运行
npx proj2md
npx proj2md /path/to/project -o bundle.md
npx proj2md --only-ext js ts md --line-numbers --clip

# 或全局安装后直接使用 proj2md 命令
npm install -g proj2md
```

> `iconv-lite` 是可选依赖（仅用于 GBK / Big5 编码识别），缺失时自动降级，其余功能不受影响；生成的 Markdown 与 Python 版结构完全一致，可无缝互换。
> Node 版源码见 [`proj2md-js/`](./proj2md-js)，使用说明见 [proj2md-js/README.md](./proj2md-js/README.md)。

生成后，把 `project_bundle.md` 的内容整个粘贴给网页端 AI 即可 —— Markdown 代码块会自动语法高亮。

## 📖 常用示例

> 以下示例使用安装后的 `proj2md` 命令；用源码运行的话，把 `proj2md` 换成 `python proj2md.py` 即可。

```bash
proj2md --only-ext py md            # 只拼接 Python 与 Markdown
proj2md --ext proto graphql         # 在默认范围上追加扩展名
proj2md --exclude-dir tests docs    # 额外排除目录
proj2md --include-pattern "src/*"   # 强制包含（优先级最高）
proj2md --include-hidden            # 不忽略 . 开头的文件夹
proj2md --include-pattern ".github/*"  # 只捞回某个隐藏目录
proj2md --line-numbers              # 正文带行号，AI 引用更精准
proj2md --max-file-lines 300        # 单文件超过 300 行则截断
proj2md --max-total-kb 200          # 总体积预算 200KB
proj2md --split-tokens 60000        # 过大时切成多个分卷
proj2md --lang en                   # 界面切英文
proj2md --dry-run                   # 只预览，不写文件
proj2md --init-config               # 生成配置模板
proj2md --repo https://github.com/owner/repo --ref main -o bundle.md  # 不 clone，直接打包远程仓库
```

> `--repo` 对 GitHub 使用源码归档接口；私有仓库可设置 `GITHUB_TOKEN` 或 `GH_TOKEN`。其他 Git 服务会尝试 `git archive --remote`，需服务端支持 `git-upload-archive`。远程快照只包含指定版本的已提交文件；不会包含本地未提交改动、提交历史、子模块内容或 LFS 大文件实体。
>
> 走代理时两端都会自动识别：Python 版沿用标准库的系统代理；Node 版读取 `HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY`（大小写均可），在 Windows 上还会读取「Internet 选项」中的系统代理配置。

## ⚙️ 命令行参数

**输入与输出**

| 参数 | 说明 |
|---|---|
| `root`（位置参数） | 项目根目录，默认当前目录 |
| `--repo <url>` | 远程 Git 仓库 URL；下载快照后打包，不执行 clone（不可与 `root` 同用） |
| `--ref <ref>` | `--repo` 使用的分支、标签或提交引用（默认 `HEAD`） |
| `-o, --output <file>` | 输出文件路径（默认 `project_bundle.md`） |
| `--stdout` | 输出到标准输出，不写文件 |
| `--clip` | 生成后复制到系统剪贴板 |

**文件范围**

| 参数 | 说明 |
|---|---|
| `--ext <ext...>` | 在默认扩展名白名单上**追加** |
| `--only-ext <ext...>` | 只包含指定扩展名（**替换**默认范围） |
| `--any-text` | 包含所有非二进制文本文件 |
| `--include-hidden` | 不忽略 `.` 开头的文件夹 |
| `--exclude-dir <dir...>` | 追加排除的目录 |
| `--exclude-file <name...>` | 追加排除的文件名 |
| `--exclude-pattern <pat...>` | 追加排除的通配符，如 `*.min.js tests/*` |
| `--include-pattern <pat...>` | 强制包含（最高优先级，可穿透一切忽略规则） |

**体积控制**

| 参数 | 说明 |
|---|---|
| `--max-file-lines <n>` | 单文件最多保留 n 行，超出截断（0 = 不限） |
| `--max-file-kb <kb>` | 超过此大小的文件直接跳过（默认 512） |
| `--max-total-kb <kb>` | 合集总大小预算（KB） |
| `--split-tokens <n>` | 按 Token 预估切成多个 `.partN.md` 分卷 |

**输出内容**

| 参数 | 说明 |
|---|---|
| `--line-numbers` | 正文每行前加行号 |
| `--prompt <text>` | 在合集最前附上你的需求 |
| `--prompt-file <file>` | 从文件读取需求（UTF-8） |
| `--no-tree` / `--no-index` | 不输出目录结构 / 文件索引 |
| `--no-ai-header` | 不输出「给 AI 的阅读说明」 |
| `--no-smart-order` | 禁用智能排序 |

**其他**

| 参数 | 说明 |
|---|---|
| `--lang <auto\|zh\|en>` | 界面语言（默认 auto 跟随系统） |
| `--config <file>` / `--no-config` | 指定 / 忽略配置文件 |
| `--init-config` | 生成 `proj2md.json` 模板后退出 |
| `--dry-run` | 只预览将拼接的文件与统计 |
| `--quiet` | 静默模式，只输出结果路径 |
| `--version` / `-h, --help` | 版本号 / 帮助 |

## 🙈 忽略规则

按顺序生效，任一命中即跳过：
1. **隐藏目录**（默认开）：`.` 开头的文件夹整目录忽略 → `--include-hidden` 关闭
2. **目录黑名单**：内置 `node_modules`、`__pycache__`、`venv`、`dist`、`build` 等 + `--exclude-dir`
3. **文件黑名单**：锁文件 `package-lock.json`、`poetry.lock` 等 + `--exclude-file`
4. **通配符黑名单**：`*.min.js`、`*.png`、`*.zip`、`*.log` 等 + `--exclude-pattern`
5. **扩展名白名单**：仅收录白名单内扩展名 → `--ext` / `--only-ext` / `--any-text` 调整
> ⭐ `--include-pattern` 优先级最高：即使命中上述任何规则也强制包含，且能穿透隐藏目录忽略。

另外：
- 输出文件、配置文件、脚本自身会被自动排除，不会拼进结果；
- 疑似二进制 / 无法解码 / 超限的文件不会丢失，统一记录在文末附录；
- 点开头的**文件**（如 `.gitignore`）不受隐藏目录规则影响，正常收录。

## 🧠 智能排序

合集内的文件按以下优先级排列，让 AI 优先读到最关键的内容：

| 优先级 | 文件类型 |
|:---:|---|
| 0 | `README*` |
| 1 | 项目清单与配置：`package.json`、`pyproject.toml`、`requirements.txt`、`Dockerfile`、`.gitignore` 等 |
| 2 | 入口文件（`main` / `app` / `index` / `server` / `cli`…）及 `config` / `settings` |
| 3 | 其余文件（按路径排序） |

## 📄 生成文档结构

```
# 项目代码合集：<项目名>
├─ 元信息（生成时间 / 文件数 / 行数 / Token 预估）
├─ 📖 给 AI 的阅读说明（约定引用格式等）
├─ 🎯 我的需求（--prompt，若有）
├─ 🗂 目录结构（树状图）
├─ 📑 文件索引（锚点链接 + 起始行号）
├─ 📄 源代码正文（### 序号. 相对路径 + 语法高亮代码块）
├─ 📎 附录：未包含的文件
├─ 📎 附录：已忽略的隐藏目录
└─ END 统计页脚
```

即使源码里含有 ` ``` ` 代码块也不会破坏结构 —— 围栏长度会自适应加长。

## 🌐 多语言界面

语言解析优先级：**`--lang` 参数 > 配置文件 `language` 字段 > 系统自动探测 > 英文兜底**。

```bash
proj2md --lang en      # 本次运行全英文（含 --help 与报告）
proj2md --lang zh      # 强制中文
proj2md --lang auto    # 跟随系统（覆盖配置文件设置）

```
- `auto`（默认）：依次探测环境变量（`LC_ALL` / `LANG`…）→ `locale` 模块 → Windows API，凡 `zh` 开头即中文，否则英文；
- 也可以在 `proj2md.json` 中写 `"language": "zh"` 持久化；
- 切换的不只是控制台输出 —— 生成的 `.md` 文档内的标题、AI 阅读说明、索引表头、附录等也会跟随语言。
## 🪟 配置文件
```bash
proj2md --init-config   # 生成 proj2md.json 模板
```
按需修改后再次运行即自动读取（无需额外参数）：
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
优先级：**命令行参数 > 配置文件 > 内置默认** ；不需要的键可直接删除。
## 📏 体积与 Token 预算

Token 为粗略估算（中文 ≈ 1.1 token/字，其他 ≈ 3.8 字符/token），生成后会给出提示：

| 预估 Token | 建议 |
|---|---|
| < 30k | ✅ 体量适中，直接投喂 |
| 30k – 100k | ⚠️ 部分 AI 输入框有长度限制，建议裁剪 |
| 100k – 200k | ⚠️ 需长上下文模型，或用 `--split-tokens` 分卷 |
| > 200k | ❌ 建议裁剪（`--exclude-dir` / `--max-file-lines` / `--only-ext`）或分卷 |

## 💡 使用技巧与 FAQ

- **让 AI 精确引用代码**：投喂时在 `--prompt` 里要求它用 `相对路径:行号` 格式引用；配合 `--line-numbers` 效果最佳。
- **分卷投喂顺序**：`--split-tokens` 生成 `xxx.part1.md`、`xxx.part2.md`…，请按顺序投喂，最后一卷才附带附录。
- **AI 忘了项目结构？** 把文档中的「目录结构 / 文件索引」两节再粘贴一次即可，无需重发全部代码。
- **Windows 终端中文乱码？** 脚本会自动把中文符号降级为 ASCII；也可以先执行 `chcp 65001` 切到 UTF-8。
- **`--clip` 失败？** `pip install pyperclip`，或直接打开输出文件手动复制。
- **想彻底自定义收录范围？** `--any-text` 收录所有文本文件，配合 `--include-hidden` 就是"全量模式"。

## 🧱 项目结构

同一套功能有两种实现，命令行参数、`proj2md.json` 配置格式、生成的 Markdown 结构完全一致，按手头的运行时任选其一即可。

```
proj2md/
├── proj2md.py           # Python 版：单文件脚本，仅标准库（Python 3.8+）
├── pyproject.toml       #   └─ 打包为 PyPI 包 proj2md-py，uv / pip 安装
├── tests/               #   └─ 回归测试：python tests/test_proj2md.py
├── README.md / README_EN.md
└── proj2md-js/          # Node 版：纯 Node.js，零必需依赖（Node.js ≥ 14）
    ├── bin/proj2md.js   #   └─ 发布为 npm 包 proj2md，npx / npm 安装
    ├── lib/             #      discover / reader / render / i18n / remote …
    ├── test/smoke.js    #      冒烟测试：npm test
    └── package.json
```

| | Python 版 | Node 版 |
|---|---|---|
| 包名 | `proj2md-py`（PyPI） | `proj2md`（npm） |
| 安装 | `uvx proj2md-py` / `uv tool install proj2md-py` / `pip install proj2md-py` | `npx proj2md` / `npm i -g proj2md` |
| 运行时 | Python 3.8+，零第三方依赖 | Node.js ≥ 14，可选 `iconv-lite` |
| 版本号位置 | [pyproject.toml](./pyproject.toml) | [proj2md-js/package.json](./proj2md-js/package.json) |

两端输出逐字节一致（同一份项目 + 同一组参数），`tests/test_proj2md.py` 会校验版本号同步。

```bash
python tests/test_proj2md.py    # Python 版回归测试
cd proj2md-js && npm test       # Node 版冒烟测试
```

> 发布新版本时两处版本号需同步递增：npm 由 GitHub Release 触发 [npm-publish.yml](./.github/workflows/npm-publish.yml) 自动发布（Trusted Publishing，无需 token）；PyPI 在本地执行 `uv build && uv publish`。

## 📜 许可证
[MIT](./LICENSE) © 2025
