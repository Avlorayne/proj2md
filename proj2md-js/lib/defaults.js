'use strict';
const VERSION = '2.4.1';
const TOOL = 'proj2md';
const CONFIG_FILENAME = 'proj2md.json';
const DEFAULT_OUTPUT = 'project_bundle.md';
// 行号回填内部标记（输出前必定整体移除）
const MARK = '\x00';
const DEFAULT_EXTS = new Set([
  // 编程语言
  'py', 'pyw', 'js', 'mjs', 'cjs', 'ts', 'jsx', 'tsx', 'java', 'c', 'h', 'cpp', 'cc', 'hpp',
  'cs', 'go', 'rs', 'rb', 'php', 'swift', 'kt', 'kts', 'scala', 'dart', 'm', 'mm', 'pl', 'pm',
  'lua', 'r', 'jl', 'hs', 'clj', 'ex', 'exs', 'erl', 'groovy', 'asm', 'zig', 'nim', 'v',
  // Web / 模板
  'html', 'htm', 'css', 'scss', 'sass', 'less', 'styl', 'vue', 'svelte', 'astro',
  'ejs', 'hbs', 'pug', 'jinja', 'j2', 'liquid', 'twig',
  // 数据 / 配置
  'json', 'yml', 'yaml', 'toml', 'ini', 'cfg', 'conf', 'properties', 'xml', 'csv', 'tsv',
  'sql', 'graphql', 'gql', 'proto',
  // 文档 / 脚本
  'md', 'markdown', 'mdx', 'rst', 'txt', 'adoc', 'tex',
  'sh', 'bash', 'zsh', 'fish', 'bat', 'cmd', 'ps1', 'psm1',
]);
// 黑名单目录（隐藏目录另有整体开关）
const DEFAULT_EXCLUDE_DIRS = new Set([
  'node_modules', 'bower_components', 'jspm_packages', '__pycache__',
  '.mypy_cache', '.pytest_cache', '.ruff_cache', '.tox',
  'venv', '.venv', 'env', 'virtualenv',
  'dist', 'build', 'out', 'target', 'obj', 'bin', 'vendor',
  'Pods', 'Carthage', 'coverage', '.nyc_output', '.parcel-cache',
  // 构建产物（支持通配目录名，见 discover）：常被误拼进合集
  '*.egg-info', '*.dist-info', '.eggs',
]);
const DEFAULT_EXCLUDE_FILES = new Set([
  'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock',
  'pipfile.lock', 'composer.lock', 'cargo.lock', 'gemfile.lock',
]);
const DEFAULT_EXCLUDE_PATTERNS = [
  '*.min.js', '*.min.css', '*.map', '*.log', '*.pyc', '*.pyo', '*.class',
  '*.o', '*.so', '*.dll', '*.exe', '*.bin',
  '*.woff', '*.woff2', '*.ttf', '*.eot', '*.otf', '*.ico',
  '*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.svg', '*.webp',
  '*.pdf', '*.zip', '*.tar', '*.gz', '*.rar', '*.7z',
  '*.mp3', '*.mp4', '*.avi', '*.mov', '*.db', '*.sqlite',
];
// 无扩展名但属于文本的文件名（点开头的【文件】不受隐藏目录规则影响）
const DEFAULT_FILENAMES = new Set([
  'dockerfile', 'makefile', 'rakefile', 'gemfile', 'procfile', 'brewfile',
  'justfile', 'vagrantfile', 'license', 'licence', 'notice',
  '.gitignore', '.gitattributes', '.dockerignore', '.editorconfig',
  '.npmrc', '.nvmrc', '.python-version', '.env.example', '.env.sample',
]);
const LANGUAGE_BY_EXT = {
  py: 'Python', pyw: 'Python',
  js: 'JavaScript', mjs: 'JavaScript', cjs: 'JavaScript',
  ts: 'TypeScript', tsx: 'TypeScript React', jsx: 'JavaScript React',
  java: 'Java', c: 'C', h: 'C Header', cpp: 'C++', cc: 'C++', hpp: 'C++ Header',
  cs: 'C#', go: 'Go', rs: 'Rust', rb: 'Ruby', php: 'PHP', swift: 'Swift',
  kt: 'Kotlin', kts: 'Kotlin', scala: 'Scala', dart: 'Dart', lua: 'Lua',
  pl: 'Perl', r: 'R', jl: 'Julia', m: 'MATLAB/ObjC',
  html: 'HTML', htm: 'HTML', css: 'CSS', scss: 'SCSS', sass: 'Sass', less: 'Less',
  vue: 'Vue', svelte: 'Svelte',
  json: 'JSON', yml: 'YAML', yaml: 'YAML', toml: 'TOML', ini: 'INI',
  cfg: 'Config', conf: 'Config', env: 'Env', xml: 'XML', sql: 'SQL',
  graphql: 'GraphQL', proto: 'Protobuf',
  md: 'Markdown', markdown: 'Markdown', mdx: 'MDX', rst: 'reST', txt: 'Text',
  csv: 'CSV', tsv: 'TSV', tex: 'LaTeX',
  sh: 'Shell', bash: 'Shell', zsh: 'Shell', fish: 'Shell',
  bat: 'Batch', cmd: 'Batch', ps1: 'PowerShell', psm1: 'PowerShell',
};
const LANGUAGE_BY_NAME = {
  dockerfile: 'Dockerfile', makefile: 'Makefile', rakefile: 'Ruby Rake',
  gemfile: 'Ruby Gemfile', justfile: 'Justfile',
  license: 'License', licence: 'License',
  '.gitignore': 'Git Ignore', '.dockerignore': 'Docker Ignore',
  '.editorconfig': 'EditorConfig',
};
const FENCE_LANG_BY_EXT = {
  py: 'python', pyw: 'python',
  js: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'tsx', jsx: 'jsx',
  java: 'java', c: 'c', h: 'c', cpp: 'cpp', cc: 'cpp', hpp: 'cpp',
  cs: 'csharp', go: 'go', rs: 'rust', rb: 'ruby', php: 'php',
  swift: 'swift', kt: 'kotlin', kts: 'kotlin', scala: 'scala', dart: 'dart',
  lua: 'lua', pl: 'perl', pm: 'perl', r: 'r', jl: 'julia', hs: 'haskell',
  clj: 'clojure', ex: 'elixir', exs: 'elixir', erl: 'erlang', groovy: 'groovy',
  asm: 'asm', zig: 'zig', nim: 'nim', v: 'v', m: 'objective-c', mm: 'objective-c',
  html: 'html', htm: 'html', css: 'css', scss: 'scss', sass: 'sass', less: 'less',
  styl: 'stylus', vue: 'vue', svelte: 'svelte', astro: 'astro',
  ejs: 'html', hbs: 'handlebars', pug: 'pug', jinja: 'jinja', j2: 'jinja',
  liquid: 'liquid', twig: 'twig',
  json: 'json', yml: 'yaml', yaml: 'yaml', toml: 'toml', ini: 'ini',
  cfg: 'ini', conf: 'conf', properties: 'properties', xml: 'xml',
  sql: 'sql', graphql: 'graphql', gql: 'graphql', proto: 'protobuf',
  md: 'markdown', markdown: 'markdown', mdx: 'markdown', rst: 'rst',
  adoc: 'asciidoc', txt: 'text', csv: 'csv', tsv: 'tsv', tex: 'latex',
  sh: 'bash', bash: 'bash', zsh: 'bash', fish: 'fish',
  bat: 'batch', cmd: 'batch', ps1: 'powershell', psm1: 'powershell',
};
const FENCE_LANG_BY_NAME = {
  dockerfile: 'dockerfile', makefile: 'makefile', rakefile: 'ruby', gemfile: 'ruby',
  justfile: 'makefile', procfile: 'text', brewfile: 'ruby', vagrantfile: 'ruby',
  license: 'text', licence: 'text', notice: 'text',
  '.gitignore': 'gitignore', '.gitattributes': 'gitignore', '.dockerignore': 'gitignore',
  '.editorconfig': 'ini', '.npmrc': 'ini', '.nvmrc': 'text',
  '.python-version': 'text', '.env.example': 'ini', '.env.sample': 'ini',
};
// 智能排序：优先级从高到低
const CONFIG_MANIFESTS = new Set([
  'package.json', 'pyproject.toml', 'setup.py', 'setup.cfg', 'requirements.txt',
  'go.mod', 'go.sum', 'cargo.toml', 'pom.xml', 'build.gradle', 'composer.json',
  'gemfile', 'dockerfile', 'docker-compose.yml', 'docker-compose.yaml',
  'manage.py', '.env.example',
]);
const ENTRY_STEMS = new Set(['main', 'app', 'index', 'server', 'wsgi', 'asgi', '__init__', 'cli', 'run']);
const ENTRY_EXTS = new Set(['.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.rb', '.php', '.java']);
const CONFIG_TEMPLATE = {
  '_说明': [
    'proj2md 配置文件。命令行参数优先级高于本文件；',
    '不需要的键可直接删除（恢复默认）；exts 为空列表 [] 时使用内置默认扩展名。',
    'language：界面语言。auto=跟随系统 / zh=中文 / en=英文。',
  ],
  language: 'auto',
  output: 'project_bundle.md',
  exts: [],
  any_text: false,
  exclude_hidden: true,
  exclude_dirs: [],
  exclude_files: [],
  exclude_patterns: [],
  include_patterns: [],
  line_numbers: false,
  max_file_lines: 0,
  max_file_kb: 512,
  max_total_kb: 0,
  split_tokens: 0,
  show_tree: true,
  show_index: true,
  ai_header: true,
  smart_order: true,
  clip: false,
};
module.exports = {
  VERSION, TOOL, CONFIG_FILENAME, DEFAULT_OUTPUT, MARK,
  DEFAULT_EXTS, DEFAULT_EXCLUDE_DIRS, DEFAULT_EXCLUDE_FILES, DEFAULT_EXCLUDE_PATTERNS,
  DEFAULT_FILENAMES, LANGUAGE_BY_EXT, LANGUAGE_BY_NAME,
  FENCE_LANG_BY_EXT, FENCE_LANG_BY_NAME,
  CONFIG_MANIFESTS, ENTRY_STEMS, ENTRY_EXTS, CONFIG_TEMPLATE,
};
