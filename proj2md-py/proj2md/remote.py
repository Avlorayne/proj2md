"""proj2md 远程仓库快照（不 clone）：GitHub 归档 API / git archive --remote。"""
from __future__ import annotations
import io
import os
import re
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ★ 修复（P2）：远程归档整体读入内存，这里给一个宽松上限，
#   防止误配到超大仓库时把内存吃满。
_MAX_ARCHIVE_BYTES = 1 << 30  # 1 GiB
def _read_limited(resp, limit: int = _MAX_ARCHIVE_BYTES) -> bytes:
    """分块读取响应体，超过 limit 抛 RuntimeError（无 Content-Length 时也可用）。"""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = resp.read(1 << 20)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise RuntimeError(f"remote archive exceeds the {limit} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)

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
    # 显式拒绝以 / 或 \ 开头的绝对路径条目：拆分时空段会被丢掉，
    # "/etc/x" 将被相对化为 "etc/x"，从而绕过下面的 is_absolute() 检查。
    if name.startswith("/") or name.startswith("\\"):
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
                payload = _read_limited(response)  # ★ 限量读取
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
