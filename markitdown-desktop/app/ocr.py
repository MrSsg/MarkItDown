# SPDX-License-Identifier: MIT
"""Optional local OCR component management and JSONL engine protocol."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import InvalidVersion, Version


COMPONENT_NAME = "ocr-engine"
DEFAULT_MANIFEST_URL = (
    "https://github.com/MrSsg/MarkItDown/releases/download/ocr-engine-v1/"
    "ocr-engine-manifest.json"
)


def _load_public_keys() -> dict[str, str]:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    try:
        data = json.loads(
            (root / "app" / "ocr_public_keys.json").read_text(encoding="utf-8")
        )
        return {str(key): str(value) for key, value in data.items() if value}
    except (OSError, ValueError, TypeError):
        return {}


# Production builds replace this bundled file with a release-owned public key.
OCR_COMPONENT_PUBLIC_KEYS = _load_public_keys()


class OcrComponentError(RuntimeError):
    def __init__(self, message: str, code: str = "OCR_COMPONENT_ERROR") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OcrComponentInfo:
    installed: bool
    version: str | None = None
    path: Path | None = None
    message: str = ""


def default_component_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "MarkItDownDesk" / "ocr-components"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_visible_characters(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def parse_jsonl_event(line: str) -> dict:
    try:
        event = json.loads(line)
    except json.JSONDecodeError as exc:
        raise OcrComponentError(
            f"OCR 引擎返回了无效 JSON: {line[:160]}", "PROTOCOL_INVALID"
        ) from exc
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise OcrComponentError("OCR 引擎事件缺少 type 字段", "PROTOCOL_INVALID")
    if event["type"] in {"progress", "result", "error"} and not isinstance(
        event.get("request_id"), str
    ):
        raise OcrComponentError("OCR 引擎事件缺少 request_id 字段", "PROTOCOL_INVALID")
    return event


def canonical_manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    payload = {key: value for key, value in manifest.items() if key != "signature"}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def verify_manifest_signature(
    manifest: Mapping[str, object], public_keys: Mapping[str, str]
) -> None:
    required = (
        "version",
        "url",
        "sha256",
        "size_bytes",
        "min_app_version",
        "key_id",
        "signature",
    )
    if not all(
        isinstance(manifest.get(key), str) and manifest[key]
        for key in required
        if key != "size_bytes"
    ):
        raise OcrComponentError("OCR 组件清单不完整", "MANIFEST_INVALID")
    if not isinstance(manifest.get("size_bytes"), int) or manifest["size_bytes"] <= 0:
        raise OcrComponentError("OCR 组件清单缺少文件大小", "MANIFEST_INVALID")
    key_id = str(manifest["key_id"])
    public_key = public_keys.get(key_id)
    if not public_key:
        raise OcrComponentError("OCR 组件签名密钥不受信任", "SIGNING_KEY_UNKNOWN")
    try:
        public_bytes = base64.b64decode(public_key, validate=True)
        signature_bytes = base64.b64decode(str(manifest["signature"]), validate=True)
        if len(public_bytes) != 32 or len(signature_bytes) != 64:
            raise ValueError("Ed25519 密钥或签名长度错误")
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(
            signature_bytes, canonical_manifest_bytes(manifest)
        )
    except (TypeError, ValueError, InvalidSignature) as exc:
        raise OcrComponentError("OCR 组件签名校验失败", "SIGNATURE_INVALID") from exc


class OcrComponentManager:
    """Installs a versioned OCR engine without changing the main app folder."""

    def __init__(
        self,
        root: str | Path | None = None,
        public_keys: Mapping[str, str] | None = None,
        health_check: Callable[[Path], None] | None = None,
    ) -> None:
        self.root = Path(root) if root else default_component_root()
        self.current_file = self.root / "current.json"
        self.previous_file = self.root / "previous.json"
        self.public_keys = dict(
            public_keys if public_keys is not None else OCR_COMPONENT_PUBLIC_KEYS
        )
        self._health_check = health_check or self._default_health_check

    def status(self) -> OcrComponentInfo:
        try:
            data = json.loads(self.current_file.read_text(encoding="utf-8"))
            version = str(data["version"])
            install_dir = self.root / version
            engine = install_dir / "ocr-engine.exe"
            if engine.is_file():
                return OcrComponentInfo(True, version, engine)
            return OcrComponentInfo(False, message="OCR 组件文件不完整")
        except (OSError, ValueError, KeyError, TypeError):
            return OcrComponentInfo(False, message="OCR 组件未安装")

    def install_from_manifest_url(
        self,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        progress: Callable[[float], None] | None = None,
    ) -> OcrComponentInfo:
        try:
            with urllib.request.urlopen(manifest_url, timeout=20) as response:
                manifest = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise OcrComponentError(
                "无法获取 OCR 组件清单", "MANIFEST_DOWNLOAD_FAILED"
            ) from exc
        verify_manifest_signature(manifest, self.public_keys)
        self._verify_minimum_app_version(str(manifest["min_app_version"]))

        with tempfile.TemporaryDirectory(prefix="markitdown-ocr-") as temp_dir:
            archive = Path(temp_dir) / "ocr-engine.zip"
            self._download(
                manifest["url"], archive, progress, int(manifest["size_bytes"])
            )
            return self.install_archive(
                archive, manifest["version"], manifest["sha256"]
            )

    def install_archive(
        self,
        archive_path: str | Path,
        version: str,
        expected_sha256: str,
    ) -> OcrComponentInfo:
        archive = Path(archive_path)
        if not archive.is_file():
            raise OcrComponentError("未找到 OCR 组件压缩包", "ARCHIVE_MISSING")
        if sha256_file(archive).lower() != expected_sha256.lower():
            raise OcrComponentError("OCR 组件校验失败，文件可能损坏", "ARCHIVE_HASH_INVALID")
        try:
            Version(version)
        except InvalidVersion as exc:
            raise OcrComponentError("OCR 组件版本号无效", "VERSION_INVALID") from exc
        if (
            not version
            or version in {".", ".."}
            or Path(version).name != version
            or any(char in version for char in "\\/:")
        ):
            raise OcrComponentError("OCR 组件版本号无效", "VERSION_INVALID")

        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="ocr-install-", dir=self.root))
        moved_previous = False
        try:
            with zipfile.ZipFile(archive) as package:
                self._extract_safely(package, staging)
            component_dir = self._normalise_component_root(staging)
            engine = component_dir / "ocr-engine.exe"
            if not engine.is_file():
                raise OcrComponentError("OCR 组件中缺少 ocr-engine.exe")

            target = self.root / version
            replacement = self.root / f".{version}.new"
            previous = self.root / f".{version}.previous"
            if replacement.exists():
                shutil.rmtree(replacement)
            shutil.move(str(component_dir), replacement)
            self._health_check(replacement / "ocr-engine.exe")
            if target.exists():
                if previous.exists():
                    shutil.rmtree(previous)
                target.replace(previous)
                moved_previous = True
            replacement.replace(target)
            current_temp = self.root / ".current.new"
            current_temp.write_text(
                json.dumps(
                    {"version": version, "sha256": expected_sha256}, ensure_ascii=False
                ),
                encoding="utf-8",
            )
            current_temp.replace(self.current_file)
            if previous.exists():
                self.previous_file.write_text(
                    json.dumps(
                        {"version": previous.name.lstrip(".").removesuffix(".previous")}
                    ),
                    encoding="utf-8",
                )
            return OcrComponentInfo(True, version, target / "ocr-engine.exe")
        except Exception:
            if moved_previous and previous.exists():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                previous.replace(target)
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def install_offline_archive(
        self, archive_path: str | Path, manifest_path: str | Path
    ) -> OcrComponentInfo:
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            verify_manifest_signature(manifest, self.public_keys)
            self._verify_minimum_app_version(str(manifest["min_app_version"]))
            return self.install_archive(
                archive_path, manifest["version"], manifest["sha256"]
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise OcrComponentError("离线组件清单无效", "MANIFEST_INVALID") from exc

    @staticmethod
    def _verify_minimum_app_version(minimum: str) -> None:
        try:
            from app.__about__ import __version__

            if Version(__version__) < Version(minimum):
                raise OcrComponentError("桌面程序版本过低，无法安装该 OCR 组件", "APP_VERSION_TOO_OLD")
        except InvalidVersion as exc:
            raise OcrComponentError("OCR 组件最低版本字段无效", "MANIFEST_INVALID") from exc

    def _download(
        self,
        url: str,
        target: Path,
        progress: Callable[[float], None] | None,
        expected_size: int,
    ) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "MarkItDownDesk"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response, open(
                target, "wb"
            ) as stream:
                total = int(response.headers.get("Content-Length", "0") or 0)
                done = 0
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done / max(total or expected_size, 1))
                if done != expected_size:
                    raise OcrComponentError("OCR 组件下载大小不匹配", "ARCHIVE_SIZE_INVALID")
        except OSError as exc:
            raise OcrComponentError("OCR 组件下载失败", "ARCHIVE_DOWNLOAD_FAILED") from exc

    @staticmethod
    def _default_health_check(engine: Path) -> None:
        if not engine.is_file():
            raise OcrComponentError("OCR 组件中缺少 ocr-engine.exe", "ENGINE_MISSING")
        try:
            completed = subprocess.run(
                [str(engine), "--health"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                cwd=str(engine.parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            event = parse_jsonl_event(completed.stdout.strip().splitlines()[-1])
            if (
                completed.returncode != 0
                or event.get("type") != "health"
                or event.get("status") != "ok"
            ):
                raise OcrComponentError("OCR 组件健康检查失败", "ENGINE_HEALTH_FAILED")
        except (
            OSError,
            subprocess.TimeoutExpired,
            IndexError,
            OcrComponentError,
        ) as exc:
            if isinstance(exc, OcrComponentError):
                raise
            raise OcrComponentError("OCR 组件健康检查失败", "ENGINE_HEALTH_FAILED") from exc

    @staticmethod
    def _extract_safely(package: zipfile.ZipFile, target: Path) -> None:
        target_root = target.resolve()
        for member in package.infolist():
            destination = (target / member.filename).resolve()
            if not destination.is_relative_to(target_root):
                raise OcrComponentError("OCR 压缩包包含非法路径")
        package.extractall(target)

    @staticmethod
    def _normalise_component_root(staging: Path) -> Path:
        if (staging / "ocr-engine.exe").is_file():
            return staging
        children = [path for path in staging.iterdir() if path.is_dir()]
        if len(children) == 1 and (children[0] / "ocr-engine.exe").is_file():
            return children[0]
        raise OcrComponentError("OCR 压缩包目录结构无效")


class OcrEngineClient:
    """Runs one reusable JSONL engine for the lifetime of a conversion job."""

    def __init__(
        self,
        engine_path: str | Path,
        timeout_seconds: int = 300,
        request_id: str | None = None,
        progress_callback: Callable[[dict], None] | None = None,
        launcher: list[str] | None = None,
    ) -> None:
        self.engine_path = Path(engine_path)
        self.timeout_seconds = timeout_seconds
        self.request_id = request_id
        self.progress_callback = progress_callback
        self._launcher = list(launcher) if launcher else None
        self._active_process: subprocess.Popen | None = None
        self._process: subprocess.Popen | None = None
        self._stdout_queue: queue.Queue[str | None] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr = None
        self._run_lock = threading.Lock()
        self._stop_code: str | None = None

    def _command(self) -> list[str]:
        return list(self._launcher or [str(self.engine_path)]) + ["--jsonl"]

    @staticmethod
    def _read_stdout(stream, target: queue.Queue[str | None]) -> None:
        try:
            for line in stream:
                target.put(line)
        finally:
            target.put(None)

    def _ensure_process(self) -> subprocess.Popen:
        if self._process and self._process.poll() is None:
            return self._process
        if self._process:
            self._dispose_process()
        if self._launcher is None and not self.engine_path.is_file():
            raise OcrComponentError("OCR 组件未安装或已损坏", "ENGINE_MISSING")
        try:
            self._stderr = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
            process = subprocess.Popen(
                self._command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(self.engine_path.parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            if self._stderr:
                self._stderr.close()
                self._stderr = None
            raise OcrComponentError("无法启动 OCR 引擎", "ENGINE_START_FAILED") from exc
        assert process.stdout is not None
        self._process = process
        self._active_process = process
        self._stdout_queue = queue.Queue()
        self._reader_thread = threading.Thread(
            target=self._read_stdout,
            args=(process.stdout, self._stdout_queue),
            name="markitdown-ocr-reader",
            daemon=True,
        )
        self._reader_thread.start()
        return process

    def _stderr_text(self) -> str:
        if not self._stderr:
            return ""
        try:
            self._stderr.seek(0)
            return self._stderr.read()[:1000]
        except (OSError, ValueError):
            return ""

    def _dispose_process(self) -> None:
        process = self._process
        reader = self._reader_thread
        stderr = self._stderr
        self._process = None
        self._active_process = None
        self._stdout_queue = None
        self._reader_thread = None
        self._stderr = None
        if process:
            for stream in (process.stdin, process.stdout):
                if stream:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
        if reader and reader is not threading.current_thread():
            reader.join(timeout=1)
        if stderr:
            try:
                stderr.close()
            except OSError:
                pass

    def _terminate_process(self, code: str | None, wait: bool = True) -> None:
        process = self._process
        if not process:
            return
        if code:
            self._stop_code = code
        if process.poll() is None:
            process.terminate()
            if wait:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    def stop(self) -> None:
        """Stop only the owned OCR child, normally after its timeout."""
        self._terminate_process("OCR_TIMEOUT", wait=False)

    def close(self) -> None:
        """Release the reusable OCR child at the end of a conversion job."""
        self._terminate_process(None)
        self._dispose_process()

    def run(self, request: dict) -> Iterator[dict]:
        request_id = str(request.get("request_id", ""))
        with self._run_lock:
            process = self._ensure_process()
            output_queue = self._stdout_queue
            assert process.stdin is not None and output_queue is not None
            self._stop_code = None
            try:
                process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                diagnostic = self._stderr_text()
                self._dispose_process()
                raise OcrComponentError(
                    f"OCR 引擎写入失败: {diagnostic[:300]}", "ENGINE_RUNTIME_ERROR"
                ) from exc

            deadline = time.monotonic() + self.timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._terminate_process("OCR_TIMEOUT")
                    self._dispose_process()
                    raise OcrComponentError("OCR 识别超时", "OCR_TIMEOUT")
                try:
                    line = output_queue.get(timeout=remaining)
                except queue.Empty as exc:
                    self._terminate_process("OCR_TIMEOUT")
                    self._dispose_process()
                    raise OcrComponentError("OCR 识别超时", "OCR_TIMEOUT") from exc
                if line is None:
                    diagnostic = self._stderr_text()
                    code = self._stop_code or "ENGINE_RUNTIME_ERROR"
                    self._dispose_process()
                    if code == "OCR_TIMEOUT":
                        raise OcrComponentError("OCR 识别超时", code)
                    raise OcrComponentError(f"OCR 引擎异常退出: {diagnostic[:300]}", code)
                if not line.strip():
                    continue
                try:
                    event = parse_jsonl_event(line)
                except OcrComponentError:
                    self._terminate_process(None)
                    self._dispose_process()
                    raise
                if event.get("request_id") != request_id:
                    self._terminate_process(None)
                    self._dispose_process()
                    raise OcrComponentError(
                        "OCR 引擎返回了不匹配的 request_id", "REQUEST_ID_MISMATCH"
                    )
                if self.progress_callback and event.get("type") == "progress":
                    self.progress_callback(event)
                yield event
                if event.get("type") in {"result", "error"}:
                    return

    def recognise(
        self,
        file_path: str,
        file_type: str,
        pages: list[int] | None = None,
        request_id: str | None = None,
    ) -> dict:
        self.request_id = request_id or self.request_id or uuid.uuid4().hex
        result: dict | None = None
        for event in self.run(
            {
                "version": 1,
                "input_path": file_path,
                "file_type": file_type,
                "pages": pages or [],
                "language": "chinese_english",
                "request_id": self.request_id,
            }
        ):
            if event["type"] == "error":
                raise OcrComponentError(
                    str(event.get("message", "OCR 识别失败")),
                    str(event.get("code", "ENGINE_RUNTIME_ERROR")),
                )
            if event["type"] == "result":
                result = event
        if result is None:
            raise OcrComponentError("OCR 引擎未返回识别结果", "RESULT_MISSING")
        return result
