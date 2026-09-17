#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""proj2md 最小回归测试（标准库 unittest，无第三方依赖）。

运行：python tests/test_proj2md.py   或   python -m unittest discover tests
覆盖远程仓库解析 / 安全解包 / 版本号一致性，以及不需要联网的命令行分支。
"""
from __future__ import annotations
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import proj2md  # noqa: E402  （需先补 sys.path）

TOOL = ROOT / "proj2md.py"
JS_PKG = ROOT / "proj2md-js" / "package.json"


def run_cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


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
                self.assertEqual(proj2md.github_repo(url), want)

    def test_ssh_forms(self):
        want = ("Avlorayne", "proj2md")
        for url in ("git@github.com:Avlorayne/proj2md.git", "ssh://git@github.com/Avlorayne/proj2md"):
            with self.subTest(url=url):
                self.assertEqual(proj2md.github_repo(url), want)

    def test_non_github_is_none(self):
        # 非 GitHub 走 git archive 回退分支，因此必须返回 None 而不是猜一个 owner/repo
        for url in ("https://gitlab.com/owner/repo",
                    "https://gitee.com/owner/repo.git",
                    "https://github.com/owner",
                    "octocat/Hello-World"):
            with self.subTest(url=url):
                self.assertIsNone(proj2md.github_repo(url))


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
            out = proj2md.extract_tar(payload, Path(tmp))
            self.assertTrue((out / "src" / "main.py").is_file())
            self.assertTrue((out / "README.md").is_file())
            self.assertFalse((out / "repo-main").exists())

    def test_keeps_files_when_no_common_root(self):
        payload = self.make_tar([("a.txt", "a\n"), ("b/c.txt", "c\n")])
        with tempfile.TemporaryDirectory() as tmp:
            out = proj2md.extract_tar(payload, Path(tmp))
            self.assertTrue((out / "a.txt").is_file())
            self.assertTrue((out / "b" / "c.txt").is_file())

    def test_rejects_path_traversal(self):
        payload = self.make_tar([("ok.txt", "ok\n"), ("../escape.txt", "nope\n")])
        with tempfile.TemporaryDirectory() as tmp:
            out = proj2md.extract_tar(payload, Path(tmp))
            self.assertTrue((out / "ok.txt").is_file())
            self.assertFalse((Path(tmp).parent / "escape.txt").exists())

    def test_safe_archive_path(self):
        self.assertIsNone(proj2md._safe_archive_path("../x"))
        self.assertIsNone(proj2md._safe_archive_path("a/../../x"))
        self.assertIsNone(proj2md._safe_archive_path(""))
        self.assertIsNone(proj2md._safe_archive_path("C:/x"))   # 绝对路径
        self.assertIsNotNone(proj2md._safe_archive_path("a/b.txt"))


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
        self.assertGreater(proj2md.estimate_tokens("中文" * 100), proj2md.estimate_tokens("a" * 100))

    def test_astral_char_counts_as_one(self):
        # JS 侧按码点计数（cpLen），emoji 不能按 2 个 UTF-16 单元算，否则两端分卷结果会不同
        self.assertEqual(proj2md.estimate_tokens("😀" * 38), 10)


class TestVersionSync(unittest.TestCase):
    """两套实现各自发布，版本号必须同步递增。"""

    def test_manifests_match_module(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        npm_version = json.loads(JS_PKG.read_text(encoding="utf-8"))["version"]
        self.assertIn(f'version = "{proj2md.VERSION}"', pyproject)
        self.assertEqual(npm_version, proj2md.VERSION)

    def test_js_defaults_match(self):
        defaults = (ROOT / "proj2md-js" / "lib" / "defaults.js").read_text(encoding="utf-8")
        self.assertIn(f"VERSION = '{proj2md.VERSION}'", defaults)


if __name__ == "__main__":
    unittest.main(verbosity=2)
