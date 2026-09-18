#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""proj2md 最小回归测试（标准库 unittest，无第三方依赖）。

运行：cd proj2md-py && python -m unittest discover tests
覆盖远程仓库解析 / 安全解包 / 版本号一致性，以及不需要联网的命令行分支。
"""
from __future__ import annotations
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import proj2md  # noqa: E402  （需先补 sys.path）
from proj2md.discover import discover  # noqa: E402
from proj2md.remote import _safe_archive_path, extract_tar, github_repo  # noqa: E402
from proj2md.restore import safe_rel  # noqa: E402
from proj2md.util import estimate_tokens  # noqa: E402

JS_PKG = ROOT.parent / "proj2md-js" / "package.json"


def _cli_env() -> dict:
    return {**os.environ, "PYTHONPATH": str(ROOT)}


def run_cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "proj2md", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=_cli_env())


class TestGithubRepo(unittest.TestCase):
    """--repo 的 GitHub URL 解析。"""

    def test_https_forms(self):
        want = ("Avlorayne", "proj2md")
        for url in (
            "https://github.com/Avlorayne/proj2md",
            "https://github.com/Avlorayne/proj2md/",
            "https://github.com/Avlorayne/proj2md.git",
            "https://github.com/Avlorayne/proj2md.git/",
            "https://www.github.com/Avlorayne/proj2md",
            "https://github.com/Avlorayne/proj2md?tab=readme",
            "https://github.com/Avlorayne/proj2md#top",
        ):
            with self.subTest(url=url):
                self.assertEqual(github_repo(url), want)

    def test_ssh_forms(self):
        want = ("Avlorayne", "proj2md")
        for url in ("git@github.com:Avlorayne/proj2md.git", "ssh://git@github.com/Avlorayne/proj2md"):
            with self.subTest(url=url):
                self.assertEqual(github_repo(url), want)

    def test_non_github_is_none(self):
        # 非 GitHub 走 git archive 回退分支，因此必须返回 None 而不是猜一个 owner/repo
        for url in ("https://gitlab.com/owner/repo",
                    "https://gitee.com/owner/repo.git",
                    "https://github.com/owner",
                    "octocat/Hello-World"):
            with self.subTest(url=url):
                self.assertIsNone(github_repo(url))


class TestExtractTar(unittest.TestCase):
    """归档解包：剥离顶层目录，并拒绝写到目标目录之外。"""

    @staticmethod
    def make_tar(members) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            for name, body in members:
                data = body.encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def test_strips_common_top_level_dir(self):
        payload = self.make_tar([("repo-main/src/main.py", "print(1)\n"),
                                 ("repo-main/README.md", "# hi\n")])
        with tempfile.TemporaryDirectory() as tmp:
            out = extract_tar(payload, Path(tmp))
            self.assertTrue((out / "src" / "main.py").is_file())
            self.assertTrue((out / "README.md").is_file())
            self.assertFalse((out / "repo-main").exists())

    def test_keeps_files_when_no_common_root(self):
        payload = self.make_tar([("a.txt", "a\n"), ("b/c.txt", "c\n")])
        with tempfile.TemporaryDirectory() as tmp:
            out = extract_tar(payload, Path(tmp))
            self.assertTrue((out / "a.txt").is_file())
            self.assertTrue((out / "b" / "c.txt").is_file())

    def test_rejects_path_traversal(self):
        payload = self.make_tar([("ok.txt", "ok\n"), ("../escape.txt", "nope\n")])
        with tempfile.TemporaryDirectory() as tmp:
            out = extract_tar(payload, Path(tmp))
            self.assertTrue((out / "ok.txt").is_file())
            self.assertFalse((Path(tmp).parent / "escape.txt").exists())

    def test_safe_archive_path(self):
        self.assertIsNone(_safe_archive_path("../x"))
        self.assertIsNone(_safe_archive_path("a/../../x"))
        self.assertIsNone(_safe_archive_path(""))
        self.assertIsNone(_safe_archive_path("C:/x"))   # 绝对路径
        self.assertIsNotNone(_safe_archive_path("a/b.txt"))

    def test_safe_archive_path_rejects_absolute(self):
        # 拆分时空段会被丢掉，"/etc/x" 会被相对化成 "etc/x"，必须显式拒绝
        for name in ("/etc/x", "//server/share/x", "\\windows\\x", "/x"):
            with self.subTest(name=name):
                self.assertIsNone(_safe_archive_path(name))

    def test_absolute_entry_not_extracted(self):
        payload = self.make_tar([("ok.txt", "ok\n"), ("/etc/cron.d/evil", "nope\n")])
        with tempfile.TemporaryDirectory() as tmp:
            out = extract_tar(payload, Path(tmp))
            self.assertTrue((out / "ok.txt").is_file())
            self.assertFalse((Path(tmp) / "etc").exists())


class TestCliGuards(unittest.TestCase):
    """不需要联网的参数校验分支。"""

    def test_repo_with_root_exits_2(self):
        r = run_cli("--repo", "https://github.com/o/r", ".")
        self.assertEqual(r.returncode, 2)

    def test_repo_with_init_config_exits_2(self):
        # 远程模式下配置模板会写进随后被删除的临时快照目录，必须在下载前拦下
        r = run_cli("--repo", "https://github.com/o/r", "--init-config")
        self.assertEqual(r.returncode, 2)

    def test_version_flag(self):
        r = run_cli("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn(f"v{proj2md.VERSION}", r.stdout)

    def test_help_lists_repo_options(self):
        for lang in ("zh", "en"):
            with self.subTest(lang=lang):
                self.assertIn("--repo", run_cli("--help", "--lang", lang).stdout)


class TestTokenEstimate(unittest.TestCase):
    """token 估算同时影响显示与 --split-tokens 分卷，口径需与 Node 版一致。"""

    def test_cjk_weighted_higher(self):
        self.assertGreater(estimate_tokens("中文" * 100), estimate_tokens("a" * 100))

    def test_astral_char_counts_as_one(self):
        # JS 侧按码点计数（cpLen），emoji 不能按 2 个 UTF-16 单元算，否则两端分卷结果会不同
        self.assertEqual(estimate_tokens("😀" * 38), 10)


class TestRestore(unittest.TestCase):
    """--restore 反向还原：round-trip / 安全护栏 / 各开关。"""

    @staticmethod
    def _make_project(root: Path):
        (root / "src").mkdir(parents=True)
        (root / "src" / "main.py").write_text("def main():\n    print('hi')\n", encoding="utf-8")
        (root / "README.md").write_text("# sample\n", encoding="utf-8")
        (root / "empty.txt").write_text("", encoding="utf-8")

    def _bundle(self, root: Path) -> str:
        r = run_cli(str(root), "--stdout", "--no-ai-header", "--lang", "en")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def _restore(self, md: str, target: Path, *extra, stdin=False, stdin_env=None):
        if stdin:
            env = _cli_env()
            if stdin_env:
                env.update(stdin_env)
            # text=True + encoding="utf-8"：父进程把 md 以 UTF-8 字节写进子进程 stdin，
            # 正是管道场景（子进程可能按 GBK 解码，见 test_stdin_restore_utf8_not_mojibake）。
            return subprocess.run(
                [sys.executable, "-m", "proj2md", "--restore", "-", str(target),
                 "--lang", "en", *extra],
                input=md, capture_output=True, text=True,
                encoding="utf-8", errors="replace", env=env)
        bundle = target.parent / "bundle.md"
        bundle.write_text(md, encoding="utf-8")
        return run_cli("--restore", str(bundle), str(target), "--lang", "en", *extra)

    def test_roundtrip_and_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj, out = tmp / "proj", tmp / "out"
            self._make_project(proj)
            md = self._bundle(proj)
            r = self._restore(md, out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((out / "src" / "main.py").read_text(encoding="utf-8"),
                             (proj / "src" / "main.py").read_text(encoding="utf-8"))
            self.assertTrue((out / "README.md").is_file())
            self.assertEqual((out / "empty.txt").read_text(encoding="utf-8"), "")
            r2 = self._restore(md, out)
            self.assertIn("unchanged", r2.stdout)

    def test_stdin_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj, out = tmp / "proj", tmp / "out"
            self._make_project(proj)
            r = self._restore(self._bundle(proj), out, stdin=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((out / "src" / "main.py").read_text(encoding="utf-8"),
                             (proj / "src" / "main.py").read_text(encoding="utf-8"))

    def test_stdin_restore_utf8_not_mojibake(self):
        """管道里的 UTF-8 字节必须按 UTF-8 解码。
        Windows 控制台 stdin 默认 GBK，用 sys.stdin.read() 会把中文读成乱码
        （且文件路径也会跟着错），因此改为读 buffer 再解码。"""
        md = "### 1. 中文目录/说明.md\n\n```\n中文内容 €\n```\n"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            r = self._restore(md, out)                     # 先确认基线（文件入口）
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            # 强制 stdin 按 GBK 解码：复现 Windows 控制台的默认行为。
            # 修复前 sys.stdin.read() 会把 UTF-8 管道读成乱码，路径与正文全错。
            r2 = self._restore(md, Path(tmp) / "out2", stdin=True,
                               stdin_env={"PYTHONIOENCODING": "gbk"})
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            want = "中文内容 €\n"
            self.assertEqual(
                (Path(tmp) / "out" / "中文目录" / "说明.md").read_text(encoding="utf-8"), want)
            self.assertEqual(
                (Path(tmp) / "out2" / "中文目录" / "说明.md").read_text(encoding="utf-8"), want)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            md = "### 1. ../evil.txt\n\n```\nevil\n```\n\n### 2. ok.txt\n\n```\nfine\n```\n"
            out = tmp / "out"
            r = self._restore(md, out)
            self.assertEqual(r.returncode, 1)
            self.assertFalse((tmp / "evil.txt").exists())
            self.assertEqual((out / "ok.txt").read_text(encoding="utf-8"), "fine\n")

    def test_safe_rel_rejects_absolute(self):
        for name in ("/etc/cron.d/evil", "//server/share/x", r"\windows\system32\x"):
            with self.subTest(name=name):
                self.assertIsNone(safe_rel(name))
        self.assertEqual(safe_rel("src/main.py"), Path("src/main.py"))

    def test_rejects_absolute_path_entry(self):
        # 合集里写绝对路径时必须报「路径不安全」，且不能写到目标目录之外
        md = "### 1. /etc/cron.d/evil\n\n```\nevil\n```\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = tmp / "out"
            r = self._restore(md, out)
            self.assertEqual(r.returncode, 1)
            self.assertIn("unsafe", r.stdout)
            self.assertFalse((out / "etc").exists())

    def test_truncated_skipped_unless_forced(self):
        md = ("### 1. t/a.txt\n\n```\nline1\n"
              "...(the file has 10 lines in total, beyond the --max-file-lines=1 limit; "
              "only the first 1 lines are kept)\n```\n")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            r = self._restore(md, tmp / "out1")
            self.assertEqual(r.returncode, 0)
            self.assertFalse((tmp / "out1" / "t" / "a.txt").exists())
            self.assertIn("skipped", r.stdout)
            r2 = self._restore(md, tmp / "out2", "--allow-truncated")
            self.assertEqual(r2.returncode, 0)
            self.assertEqual((tmp / "out2" / "t" / "a.txt").read_text(encoding="utf-8"),
                             "line1\n")

    def test_list_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj = tmp / "proj"
            self._make_project(proj)
            md = self._bundle(proj)
            bundle = tmp / "bundle.md"
            bundle.write_text(md, encoding="utf-8")
            rl = run_cli("--restore", str(bundle), "--list", "--lang", "en")
            self.assertEqual(rl.returncode, 0)
            self.assertIn("files parsed", rl.stdout)
            self.assertIn("src/main.py", rl.stdout)
            rj = run_cli("--restore", str(bundle), "--json")
            self.assertEqual(rj.returncode, 0)
            data = json.loads(rj.stdout)
            paths = {e["path"] for e in data}
            self.assertIn("src/main.py", paths)
            self.assertTrue(all(e["safe"] for e in data))

    def test_diff_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj, out = tmp / "proj", tmp / "out"
            self._make_project(proj)
            md = self._bundle(proj)
            self._restore(md, out)
            (out / "src" / "main.py").write_text("changed\n", encoding="utf-8")
            rd = self._restore(md, out, "--diff")
            self.assertIn("--- a/src/main.py", rd.stdout)
            self.assertIn("+++ b/src/main.py", rd.stdout)
            self.assertIn("@@", rd.stdout)
            # --diff 那次已把文件更新为新内容，先再次改旧内容才有得备份
            (out / "src" / "main.py").write_text("changed2\n", encoding="utf-8")
            rb = self._restore(md, out, "--backup")
            self.assertEqual(rb.returncode, 0)
            baks = list((out / "src").glob("main.py.bak-*"))
            self.assertEqual(len(baks), 1)
            self.assertEqual(baks[0].read_text(encoding="utf-8"), "changed2\n")
            self.assertEqual((out / "src" / "main.py").read_text(encoding="utf-8"),
                             (proj / "src" / "main.py").read_text(encoding="utf-8"))

    def test_include_pattern_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj = tmp / "proj"
            self._make_project(proj)
            md = self._bundle(proj)
            out = tmp / "out"
            r = self._restore(md, out, "--include-pattern", "src/*")
            self.assertEqual(r.returncode, 0)
            self.assertTrue((out / "src" / "main.py").is_file())
            self.assertFalse((out / "README.md").exists())
            self.assertIn("not in --include-pattern scope", r.stdout)

    def test_cli_guards(self):
        # 第二个位置参数只在 --restore 模式下有效
        self.assertEqual(run_cli("somewhere", "elsewhere").returncode, 2)
        self.assertEqual(
            run_cli("--restore", "--repo", "https://github.com/o/r").returncode, 2)
        # 目标目录为 '-'：需要合集能正常解析才会走到写盘前的目标校验
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "tiny.md"
            bundle.write_text("### 1. a.txt\n\n```\nx\n```\n", encoding="utf-8")
            self.assertEqual(run_cli("--restore", str(bundle), "-").returncode, 2)


class TestDiscover(unittest.TestCase):
    """文件发现：目录黑名单（含通配）、自排除、目录链接不递归。"""

    @staticmethod
    def _cfg(root: Path, **over):
        cfg = SimpleNamespace(
            root=root, output=Path("project_bundle.md"),
            config_path=None, exclude_dirs={"node_modules"},
            exclude_files=set(), exclude_patterns=[], include_patterns=[],
            exclude_hidden=True, any_text=False, exts={"txt", "py"},
        )
        for k, v in over.items():
            setattr(cfg, k, v)
        return cfg

    def test_wildcard_dir_blacklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pkg.egg-info").mkdir()
            (root / "pkg.egg-info" / "PKG-INFO").write_text("x\n", encoding="utf-8")
            (root / "d.dist-info").mkdir()
            (root / "d.dist-info" / "METADATA").write_text("x\n", encoding="utf-8")
            (root / ".eggs").mkdir()
            (root / ".eggs" / "a.txt").write_text("x\n", encoding="utf-8")
            (root / "keep.txt").write_text("k\n", encoding="utf-8")
            cfg = self._cfg(root, exclude_dirs={"*.egg-info", "*.dist-info", ".eggs"})
            found, _ = discover(cfg)
            rels = sorted(r.as_posix() for _, r in found)
            self.assertEqual(rels, ["keep.txt"])
            r2 = list(root.rglob("*.egg-info"))
            self.assertTrue(r2)

    def test_excludes_own_entry_files(self):
        # 把包目录当项目跑时，discover / cli / __main__ 三份驱动源文件应被排除
        pkg = Path(proj2md.__file__).resolve().parent
        found, _ = discover(self._cfg(pkg, exclude_dirs=set()))
        rels = {r.as_posix() for _, r in found}
        for own in ("discover.py", "cli.py", "__main__.py"):
            with self.subTest(own=own):
                self.assertNotIn(own, rels)
        # 同目录下的其它模块仍应正常收录（自排除范围不能过大）
        self.assertIn("restore.py", rels)

    @staticmethod
    def _make_dir_link(root: Path):
        """在 root 下建一个指向 src/ 的目录链接；无法创建时返回 None。
        优先符号链接（Unix / 开启开发者模式的 Windows），退回 junction（mklink /J）。"""
        link = root / "linked-src"
        target = root / "src"
        try:
            link.symlink_to(target, target_is_directory=True)
            return link
        except (OSError, NotImplementedError):
            pass
        try:
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                               capture_output=True)
            if r.returncode == 0:
                return link
        except Exception:
            pass
        return None

    def test_dir_link_not_recursed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "a.txt").write_text("a\n", encoding="utf-8")
            link = self._make_dir_link(root)
            if link is None:
                self.skipTest("无法创建目录链接（需权限）")
            found, _ = discover(self._cfg(root))
            rels = {r.as_posix() for _, r in found}
            self.assertIn("src/a.txt", rels)
            self.assertNotIn("linked-src/a.txt", rels)


class TestClipOnly(unittest.TestCase):
    """--clip 未指定输出文件：输出文件不存在则不落盘，已存在则更新。"""

    def _run(self, cwd: Path, *args):
        return subprocess.run(
            [sys.executable, "-m", "proj2md", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(cwd), env=_cli_env())

    def test_clip_no_output_file_not_created_then_updated(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj = tmp / "proj"
            TestRestore._make_project(proj)
            out = tmp / "project_bundle.md"
            r = self._run(tmp, str(proj), "--clip", "--no-config", "--lang", "en")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(out.exists())
            self.assertIn("was not created", r.stdout)
            out.write_text("stale\n", encoding="utf-8")
            r2 = self._run(tmp, str(proj), "--clip", "--no-config", "--lang", "en")
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            self.assertNotIn("was not created", r2.stdout)
            self.assertIn("def main", out.read_text(encoding="utf-8"))

    def test_clip_with_explicit_output_always_creates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proj = tmp / "proj"
            TestRestore._make_project(proj)
            r = self._run(tmp, str(proj), "--clip", "--no-config", "-o", "custom.md")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((tmp / "custom.md").is_file())


class TestVersionSync(unittest.TestCase):
    """两套实现各自发布，版本号必须同步递增。"""

    def test_manifests_match_module(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        npm_version = json.loads(JS_PKG.read_text(encoding="utf-8"))["version"]
        self.assertIn(f'version = "{proj2md.VERSION}"', pyproject)
        self.assertEqual(npm_version, proj2md.VERSION)

    def test_js_defaults_match(self):
        defaults = (ROOT.parent / "proj2md-js" / "lib" / "defaults.js").read_text(encoding="utf-8")
        self.assertIn(f"VERSION = '{proj2md.VERSION}'", defaults)


if __name__ == "__main__":
    unittest.main(verbosity=2)
