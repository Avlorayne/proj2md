"""
proj2md —— 项目源码一键拼接工具（输出 Markdown，专为投喂网页端 AI 设计）
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
反向还原（v2.4.0 新增）：
  --restore 把 proj2md 生成的 Markdown 合集（或 AI 遵循「### 序号. 相对路径 +
  围栏代码块」约定的回复）反向写回真实文件：
    文件不存在          → 新建（自动创建父目录）
    文件已存在且相同    → 跳过（未变更）
    文件已存在且不同    → 覆盖更新（--backup 备份 / --diff 打印差异）
  - 拒绝绝对路径 / 盘符 / ..（防路径逃逸，写盘前二次校验）
  - 生成时被截断的文件默认跳过（--allow-truncated 强制写入）
  - --dry-run 预览 / --list 清单 / --json 输出 / --clip 从剪贴板读取
快速上手
  python -m proj2md                          # 拼接当前目录 -> project_bundle.md
  python -m proj2md /path/to/project         # 拼接指定项目
  python -m proj2md --repo https://github.com/owner/repo --ref main
  python -m proj2md --clip                   # 生成并复制到剪贴板
  python -m proj2md --prompt "帮我找出潜在 bug"
  python -m proj2md --dry-run                # 只预览，不写文件
  python -m proj2md --init-config            # 生成配置文件模板
  python -m proj2md --restore bundle.md      # 反向还原到当前目录
"""

from .cli import cli, main
from .defaults import CONFIG_FILENAME, DEFAULT_OUTPUT, TOOL, VERSION

__all__ = ["VERSION", "TOOL", "CONFIG_FILENAME", "DEFAULT_OUTPUT", "cli", "main"]
__version__ = VERSION
