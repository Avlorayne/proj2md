"""proj2md 剪贴板写入（复制生成结果）。"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import tempfile

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
