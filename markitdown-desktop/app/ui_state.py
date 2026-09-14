# SPDX-License-Identifier: MIT
"""Shared UI state types for the desktop workspace."""

from __future__ import annotations

from enum import Enum


class WorkspaceMode(str, Enum):
    WIDE = "Wide"
    COMPACT = "Compact"
    STACKED = "Stacked"
