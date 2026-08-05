# SPDX-License-Identifier: MIT
"""Single-job scheduling, input guards, and session-backed result storage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QStandardPaths


class JobState(str, Enum):
    IDLE = "Idle"
    RUNNING = "Running"
    CANCELLING = "Cancelling"
    TIMED_OUT_WAITING = "TimedOutWaiting"
    COMPLETED = "Completed"


@dataclass(frozen=True)
class ResourceLimits:
    max_file_bytes: int = 200 * 1024 * 1024
    max_batch_items: int = 100
    max_pdf_pages: int = 500
    max_zip_uncompressed_bytes: int = 1024 * 1024 * 1024
    max_zip_entries: int = 10_000
    max_zip_ratio: int = 100


@dataclass
class JobFailure:
    stage: str
    code: str
    message: str
    detail: str = ""
    retryable: bool = True


@dataclass
class JobItem:
    file_path: str
    state: str = "queued"
    result_path: Path | None = None
    failure: JobFailure | None = None
    request_id: str = ""
    log_path: Path | None = None
    pinned_path: Path | None = None
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def file_name(self) -> str:
        return os.path.basename(self.file_path)


class SessionStore:
    """Keeps only the current session's results on disk, not in process memory."""

    def __init__(self, root: str | Path | None = None) -> None:
        if root is None:
            base = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
            root = Path(base) / "sessions"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_id = uuid.uuid4().hex
        self.path = self.root / self.session_id
        self.path.mkdir()
        self.logs_path = self.path / "logs"
        self.logs_path.mkdir()

    @staticmethod
    def cleanup_stale(root: str | Path | None = None) -> None:
        if root is None:
            base = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
            root = Path(base) / "sessions"
        directory = Path(root)
        if not directory.is_dir():
            return
        for child in directory.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    def write(self, file_path: str, markdown: str) -> Path:
        digest = hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:16]
        target = self.path / f"{digest}.md"
        target.write_text(markdown, encoding="utf-8")
        return target

    def write_log(self, file_path: str, **event: object) -> Path:
        digest = hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:16]
        target = self.logs_path / f"{digest}.jsonl"
        record = {"timestamp": time.time(), "file_path": file_path, **event}
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return target

    @staticmethod
    def read_log(path: Path | None) -> str:
        return path.read_text(encoding="utf-8") if path and path.is_file() else ""

    @staticmethod
    def read(path: Path | None) -> str:
        if not path:
            return ""
        return path.read_text(encoding="utf-8")

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)

    def pin(self, result_path: Path, file_name: str) -> Path:
        if not result_path.is_file():
            raise FileNotFoundError("没有可固定的转换结果")
        directory = self.root.parent / "pinned"
        directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(
            (file_name + str(time.time_ns())).encode("utf-8")
        ).hexdigest()[:12]
        target = directory / f"{digest}-{Path(file_name).stem}.md"
        shutil.copy2(result_path, target)
        return target


class JobController:
    """State-only controller. The UI owns worker creation and signal wiring."""

    def __init__(
        self, limits: ResourceLimits | None = None, store: SessionStore | None = None
    ) -> None:
        self.limits = limits or ResourceLimits()
        self.store = store or SessionStore()
        self.state = JobState.IDLE
        self.items: list[JobItem] = []
        self.index = 0
        self.cancel_requested = False
        self.timed_out_path: str | None = None

    @property
    def current(self) -> JobItem | None:
        if 0 <= self.index < len(self.items):
            return self.items[self.index]
        return None

    @property
    def failures(self) -> list[JobItem]:
        return [item for item in self.items if item.failure]

    @property
    def completed_count(self) -> int:
        return sum(item.state == "success" for item in self.items)

    def enqueue(self, paths: Iterable[str]) -> list[JobItem]:
        if self.state in (
            JobState.RUNNING,
            JobState.CANCELLING,
            JobState.TIMED_OUT_WAITING,
        ):
            return []
        candidates = list(dict.fromkeys(str(Path(path)) for path in paths))
        self.items = []
        for path in candidates[: self.limits.max_batch_items]:
            issue = self.preflight(path)
            item = JobItem(path)
            if issue:
                item.state = "error"
                item.failure = issue
                self._record_failure(item)
            self.items.append(item)
        for path in candidates[self.limits.max_batch_items :]:
            item = JobItem(
                path,
                state="error",
                failure=JobFailure(
                    "preflight",
                    "BATCH_LIMIT",
                    f"批次最多允许 {self.limits.max_batch_items} 个文件",
                    retryable=False,
                ),
            )
            self._record_failure(item)
            self.items.append(item)
        self.index = 0
        self.cancel_requested = False
        self.timed_out_path = None
        self.state = JobState.IDLE
        return self.items

    def start(self) -> JobItem | None:
        if self.state not in (JobState.IDLE, JobState.COMPLETED):
            return None
        self.state = JobState.RUNNING
        return self.next_pending()

    def next_pending(self) -> JobItem | None:
        if self.cancel_requested:
            self.state = JobState.COMPLETED
            return None
        while self.index < len(self.items):
            item = self.items[self.index]
            if item.state == "queued":
                item.state = "running"
                item.started_at = time.monotonic()
                item.request_id = uuid.uuid4().hex
                item.log_path = self.store.write_log(
                    item.file_path,
                    event="started",
                    request_id=item.request_id,
                    stage="conversion",
                )
                return item
            self.index += 1
        self.state = JobState.COMPLETED
        return None

    def request_cancel(self) -> None:
        if self.state in (JobState.RUNNING, JobState.TIMED_OUT_WAITING):
            self.cancel_requested = True
            self.state = JobState.CANCELLING
            for item in self.items[self.index + 1 :]:
                if item.state == "queued":
                    item.state = "cancelled"

    def mark_timeout_waiting(self) -> None:
        current = self.current
        if current and current.state == "running":
            self.state = JobState.TIMED_OUT_WAITING
            self.timed_out_path = current.file_path

    def complete_current(self, markdown: str) -> JobItem | None:
        current = self.current
        if not current:
            return None
        late = self.timed_out_path == current.file_path
        if late:
            current.state = "error"
            current.failure = JobFailure(
                "conversion", "CONVERSION_TIMEOUT", "转换超过 10 分钟", retryable=True
            )
            self._record_failure(current)
        else:
            current.result_path = self.store.write(current.file_path, markdown)
            current.state = "success"
            current.log_path = self.store.write_log(
                current.file_path,
                event="completed",
                request_id=current.request_id,
                stage="conversion",
            )
        current.finished_at = time.monotonic()
        self.index += 1
        self.timed_out_path = None
        if self.cancel_requested:
            self.state = JobState.COMPLETED
            return None
        self.state = JobState.RUNNING
        return self.next_pending()

    def fail_current(self, failure: JobFailure) -> JobItem | None:
        current = self.current
        if not current:
            return None
        if self.timed_out_path == current.file_path:
            failure = JobFailure(
                "conversion",
                "CONVERSION_TIMEOUT",
                "转换超过 10 分钟",
                detail=failure.detail or failure.message,
                retryable=True,
            )
        current.state = "error"
        current.failure = failure
        self._record_failure(current)
        current.finished_at = time.monotonic()
        self.index += 1
        self.timed_out_path = None
        if self.cancel_requested:
            self.state = JobState.COMPLETED
            return None
        self.state = JobState.RUNNING
        return self.next_pending()

    def retry_failures(self) -> list[JobItem]:
        failed = [
            item.file_path
            for item in self.failures
            if item.failure
            and item.failure.retryable
            and os.path.isfile(item.file_path)
        ]
        return self.enqueue(failed)

    def retry_item(self, file_path: str) -> JobItem | None:
        """Reset one retryable failure without discarding other batch results."""
        if self.state in (JobState.RUNNING, JobState.CANCELLING, JobState.TIMED_OUT_WAITING):
            return None
        target_index = next(
            (index for index, item in enumerate(self.items) if item.file_path == file_path),
            None,
        )
        if target_index is None:
            return None
        target = self.items[target_index]
        if not target.failure or not target.failure.retryable or not os.path.isfile(target.file_path):
            return None
        # A single-item retry skips only earlier pending items. Later items stay
        # queued and continue in their original order after the retried item.
        for item in self.items[:target_index]:
            if item.state == "queued":
                item.state = "cancelled"
        target.state = "queued"
        target.failure = None
        target.result_path = None
        target.log_path = None
        target.started_at = None
        target.finished_at = None
        self.index = target_index
        self.cancel_requested = False
        self.timed_out_path = None
        self.state = JobState.IDLE
        return target

    def _record_failure(self, item: JobItem) -> None:
        failure = item.failure
        if failure is None:
            return
        item.log_path = self.store.write_log(
            item.file_path,
            event="failed",
            request_id=item.request_id,
            stage=failure.stage,
            code=failure.code,
            message=failure.message,
            detail=failure.detail,
            retryable=failure.retryable,
        )

    def preflight(self, path: str) -> JobFailure | None:
        target = Path(path)
        if not target.is_file():
            return JobFailure("preflight", "FILE_NOT_FOUND", "文件不存在", retryable=False)
        size = target.stat().st_size
        if size > self.limits.max_file_bytes:
            return JobFailure(
                "preflight",
                "FILE_TOO_LARGE",
                f"文件超过 {self.limits.max_file_bytes // 1024 // 1024} MiB 限制",
                retryable=False,
            )
        suffix = target.suffix.lower()
        if suffix == ".zip":
            return self._inspect_zip(target)
        if suffix == ".pdf":
            return self._inspect_pdf(target)
        return None

    def _inspect_pdf(self, path: Path) -> JobFailure | None:
        try:
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                if len(pdf.pages) > self.limits.max_pdf_pages:
                    return JobFailure(
                        "preflight",
                        "PDF_PAGE_LIMIT",
                        f"PDF 超过 {self.limits.max_pdf_pages} 页限制",
                        retryable=False,
                    )
        except Exception:
            # Conversion itself reports malformed/encrypted PDFs with richer diagnostics.
            return None
        return None

    def _inspect_zip(self, path: Path) -> JobFailure | None:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > self.limits.max_zip_entries:
                    return JobFailure(
                        "preflight",
                        "ZIP_ENTRY_LIMIT",
                        f"ZIP 超过 {self.limits.max_zip_entries} 项限制",
                        retryable=False,
                    )
                if any(
                    Path(entry.filename).suffix.lower() == ".zip"
                    for entry in entries
                    if not entry.is_dir()
                ):
                    return JobFailure(
                        "preflight",
                        "ZIP_NESTED_ARCHIVE",
                        "ZIP 不允许包含嵌套压缩包",
                        retryable=False,
                    )
                uncompressed = sum(entry.file_size for entry in entries)
                compressed = sum(entry.compress_size for entry in entries)
                if uncompressed > self.limits.max_zip_uncompressed_bytes:
                    return JobFailure(
                        "preflight",
                        "ZIP_SIZE_LIMIT",
                        "ZIP 展开后超过 1 GiB 限制",
                        retryable=False,
                    )
                if (
                    uncompressed
                    and uncompressed / max(compressed, 1) > self.limits.max_zip_ratio
                ):
                    return JobFailure(
                        "preflight",
                        "ZIP_RATIO_LIMIT",
                        "ZIP 压缩率异常，可能包含压缩炸弹",
                        retryable=False,
                    )
        except (OSError, zipfile.BadZipFile):
            return JobFailure("preflight", "ZIP_INVALID", "ZIP 文件无效", retryable=False)
        return None
