# SPDX-License-Identifier: MIT
"""Update checker and installer for markitdown kernel."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Optional, Tuple, Callable
from urllib import error as urlerror
from urllib import request as urlrequest
from zipfile import ZipFile
from dataclasses import dataclass

KERNEL_REPO = "microsoft/markitdown"
GITHUB_API = "https://api.github.com/repos/microsoft/markitdown/releases/latest"


@dataclass
class ReleaseInfo:
    tag_name: str
    version: str = ""
    body: str = ""
    html_url: str = ""
    published_at: str = ""
    zipball_url: str = ""

    def __post_init__(self):
        if not self.version:
            self.version = self.tag_name.lstrip("v")


_KERNEL_VERSION_CACHE: str = ""

def get_local_kernel_version() -> str:
    global _KERNEL_VERSION_CACHE
    if _KERNEL_VERSION_CACHE:
        return _KERNEL_VERSION_CACHE
    try:
        _KERNEL_VERSION_CACHE = importlib_metadata.version("markitdown")
        return _KERNEL_VERSION_CACHE
    except Exception:
        pass
    try:
        about_spec = importlib_metadata.distribution("markitdown").locate_file("markitdown/__about__.py")
        namespace = {}
        with open(about_spec, "r", encoding="utf-8") as f:
            exec(f.read(), namespace)
        _KERNEL_VERSION_CACHE = str(namespace.get("__version__", "0.0.0"))
        return _KERNEL_VERSION_CACHE
    except Exception:
        return "0.0.0"


def _open_json_url(url: str, timeout: int = 15) -> Optional[dict]:
    req = urlrequest.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MarkItDownDesk",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return json.loads(resp.read().decode(charset))
    except (OSError, ValueError, json.JSONDecodeError, urlerror.URLError):
        return None


def find_repo_root() -> Optional[str]:
    """Find the markitdown repo root by tracing from installed package."""
    try:
        import markitdown
        return str(Path(markitdown.__file__).parents[4])
    except Exception:
        return None


def check_latest_release() -> Optional[ReleaseInfo]:
    """Query GitHub API for the latest release."""
    d = _open_json_url(GITHUB_API, timeout=15)
    if not d:
        return None
    try:
        return ReleaseInfo(
            tag_name=d["tag_name"],
            body=d.get("body", "")[:2000],
            html_url=d["html_url"],
            published_at=d.get("published_at", ""),
            zipball_url=d.get("zipball_url", ""),
        )
    except KeyError:
        return None


def download_zip(url: str, target_path: str, cb: Optional[Callable[[float], None]] = None) -> bool:
    """Download ZIP from URL with optional progress callback (0.0-1.0)."""
    try:
        req = urlrequest.Request(url, headers={"User-Agent": "MarkItDownDesk"})
        with urlrequest.urlopen(req, timeout=30) as resp, open(target_path, "wb") as f:
            total = int(resp.headers.get("Content-Length", "0") or 0)
            done = 0
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if cb and total > 0:
                    cb(done / total)
        return True
    except Exception:
        return False


def install_update(zip_path: str) -> Tuple[bool, str]:
    """Extract ZIP, backup, replace, reinstall."""
    repo_root = find_repo_root()
    if not repo_root:
        return False, "找不到本地 MarkItDown 仓库路径"

    dst_pkg = os.path.join(repo_root, "packages", "markitdown")
    backup_dir = os.path.join(repo_root, "packages", "markitdown.bak")
    if not os.path.isdir(dst_pkg):
        return False, "本地 packages/markitdown 不存在"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            with ZipFile(zip_path, "r") as z:
                z.extractall(tmp)

            entries = [d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
            if not entries:
                return False, "ZIP 格式不对：没有找到顶层目录"

            src_pkg = os.path.join(tmp, entries[0], "packages", "markitdown")
            if not os.path.isdir(src_pkg):
                return False, "ZIP 中未找到 packages/markitdown"

            # Backup
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)
            shutil.copytree(dst_pkg, backup_dir,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

            # Clean dst
            for item in os.listdir(dst_pkg):
                p = os.path.join(dst_pkg, item)
                if item in ("__pycache__",):
                    continue
                (shutil.rmtree if os.path.isdir(p) else os.remove)(p)

            # Copy new
            for item in os.listdir(src_pkg):
                s = os.path.join(src_pkg, item)
                d = os.path.join(dst_pkg, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                else:
                    shutil.copy2(s, d)

            # Reinstall
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install",
                 "-e", "packages/markitdown",
                 "--quiet", "--no-warn-script-location"],
                cwd=repo_root, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return False, f"pip install 失败: {r.stderr[:200]}"

        return True, f"内核更新完成（重启后生效）"

    except Exception as e:
        return False, f"更新失败: {str(e)[:200]}"


def rollback() -> Tuple[bool, str]:
    """Rollback to backed-up version."""
    repo_root = find_repo_root()
    if not repo_root:
        return False, "找不到本地仓库路径"
    backup_dir = os.path.join(repo_root, "packages", "markitdown.bak")
    dst = os.path.join(repo_root, "packages", "markitdown")
    if not os.path.isdir(backup_dir):
        return False, "没有备份可恢复"
    try:
        if os.path.exists(dst):
            shutil.rmtree(dst)
        os.rename(backup_dir, dst)
        subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "-e", "packages/markitdown",
             "--quiet", "--no-warn-script-location"],
            cwd=repo_root, capture_output=True, timeout=120)
        return True, "已回退到备份版本"
    except Exception as e:
        return False, f"回退失败: {str(e)[:200]}"
