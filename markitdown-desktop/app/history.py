# SPDX-License-Identifier: MIT

import json
import time
import os
from dataclasses import dataclass, asdict, is_dataclass
from typing import List

from PySide6.QtCore import QStandardPaths


@dataclass
class HistoryEntry:
    file_path: str
    file_name: str
    file_size: int
    file_type: str
    timestamp: float
    output_preview: str = ""  # retained only for backwards-compatible reads
    export_path: str = ""
    exported_at: float | None = None
    pinned_path: str = ""


class HistoryManager:
    """历史记录管理，JSON 文件持久化。"""

    def __init__(self, max_entries: int = 50, path: str | os.PathLike[str] | None = None) -> None:
        self._max = max_entries
        data_dir = (
            os.path.dirname(os.path.abspath(os.fspath(path)))
            if path is not None
            else QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        )
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.abspath(os.fspath(path)) if path is not None else os.path.join(data_dir, "history.json")
        self._entries: List[HistoryEntry] = []
        self._load()

    @property
    def entries(self) -> List[HistoryEntry]:
        return list(self._entries)

    def add(self, entry: HistoryEntry) -> None:
        # deduplicate by file_path
        self._entries = [e for e in self._entries if e.file_path != entry.file_path]
        self._entries.insert(0, entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[: self._max]
        self._save()

    def remove(self, file_path: str) -> None:
        self._entries = [e for e in self._entries if e.file_path != file_path]
        self._save()

    def clear(self) -> None:
        self._entries.clear()
        self._save()

    def mark_export(self, file_path: str, export_path: str) -> None:
        for entry in self._entries:
            if entry.file_path == file_path:
                entry.export_path = export_path
                entry.exported_at = time.time()
                break
        self._save()

    def mark_pinned(self, file_path: str, pinned_path: str) -> None:
        for entry in self._entries:
            if entry.file_path == file_path:
                entry.pinned_path = pinned_path
                break
        self._save()

    @property
    def pinned_entries(self) -> List[HistoryEntry]:
        return [entry for entry in self._entries if entry.pinned_path]

    def unpin(self, file_path: str) -> str:
        """Detach and remove the managed pinned result for one source file."""
        pinned_path = ""
        for entry in self._entries:
            if entry.file_path == file_path:
                pinned_path = entry.pinned_path
                entry.pinned_path = ""
                break
        if pinned_path:
            self._delete_managed_pinned(pinned_path)
        self._save()
        return pinned_path

    def clear_pins(self) -> List[str]:
        """Detach and remove every managed pinned result."""
        paths = [entry.pinned_path for entry in self._entries if entry.pinned_path]
        for entry in self._entries:
            entry.pinned_path = ""
        for path in paths:
            self._delete_managed_pinned(path)
        self._save()
        return paths

    def _delete_managed_pinned(self, pinned_path: str) -> None:
        target = os.path.abspath(pinned_path)
        root = os.path.abspath(os.path.join(os.path.dirname(self._path), "pinned"))
        try:
            if os.path.commonpath([target, root]) != root:
                return
            if os.path.isfile(target):
                os.remove(target)
        except (OSError, ValueError):
            pass

    def _load(self) -> None:
        if not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            migrated = False
            self._entries = []
            for item in data[: self._max]:
                if not isinstance(item, dict):
                    continue
                if item.get("output_preview"):
                    migrated = True
                item = dict(item)
                item["output_preview"] = ""
                self._entries.append(HistoryEntry(**item))
            if migrated:
                self._save()
        except (json.JSONDecodeError, TypeError, KeyError):
            self._entries = []

    def _save(self) -> None:
        data = [asdict(e) for e in self._entries]
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def make_entry(
        file_path: str, output_text: str = "", preview_len: int = 200
    ) -> HistoryEntry:
        name = os.path.basename(file_path)
        _, ext = os.path.splitext(name)
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = 0
        return HistoryEntry(
            file_path=file_path,
            file_name=name,
            file_size=size,
            file_type=ext.lower(),
            timestamp=time.time(),
            output_preview="",
        )
