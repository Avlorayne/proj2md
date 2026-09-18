"""proj2md 默认常量：扩展名白名单、忽略规则、语言映射、配置模板、内部标记。"""
import re

VERSION = "2.4.1"
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
    # 构建产物（支持通配目录名，见 discover._dir_excluded）：常被误拼进合集
    "*.egg-info", "*.dist-info", ".eggs",
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
