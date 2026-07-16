# MarkItDownDesk -- Developer Log

Version: v1.0 | PySide6 (Qt 6.11) | PyInstaller

---

## Project Structure

  markitdown-desktop/
  +-- main.py                  # Entry + system tray
  +-- build.spec               # PyInstaller config
  +-- requirements.txt         # Dependencies
  +-- start_markitdown.bat     # Quick-launch
  +-- app/
  |   +-- settings.py          # QSettings persistence
  |   +-- history.py           # JSON history (50 entries)
  |   +-- theme.py             # Dark/light/system theme
  |   +-- worker.py            # Background conversion (QThread)
  |   +-- main_window.py       # Main window + settings dialog
  |   +-- float_window.py      # Float window (edge-snap/drag-drop)
  |   +-- styles/
  |       +-- dark.qss
  |       +-- light.qss
  +-- assets/

---

## Module Design

### main.py
- Creates QApplication, instantiates all modules
- Connects float drag -> main convert, settings, etc.
- System tray icon with right-click menu
- setQuitOnLastWindowClosed(False) for Tool window

### settings.py
- QSettings wrapper, persists to Windows registry
- Keys: save path, theme mode, float state, window geometry, history max
- Call sync() after changes

### history.py
- JSON file in %%LOCALAPPDATA%%/MarkItDownDesk/history.json
- Fields: path, name, size, type, timestamp, preview
- Dedup by file_path, max 50 by default

### theme.py
- Loads QSS from app/styles/{dark,light}.qss
- Modes: system (auto), dark, light
- Qt 6.5+ colorScheme detection, fallback to registry
- _resource_path handles PyInstaller sys._MEIPASS

### worker.py (most critical)
- Pattern: Worker Object + moveToThread
- Flow: start_convert -> QThread + _ConvertTask -> worker.run()
- markitdown import is INSIDE run() to defer to worker thread
- Old thread is quit()+wait(3000) before new thread
- Cross-thread signals use explicit QueuedConnection
- Cleanup: deleteLater on worker and thread completion

### main_window.py
- Layout: MenuBar > ToolBar > Splitter(Left|Right) > StatusBar
- Left: file info + history list
- Right: QTextBrowser (Markdown->HTML via markdown+pygments)
- Error dialog uses QMessageBox.warning(None, ...) to avoid float blocking

### float_window.py
- States: COLLAPSED (48x48) > HOVER (64x180) > ACTIVE (260x380)
- Edge snap: distance to all 4 edges of all monitors (<20px snap, >50px detach)
- Flags: StayOnTopHint | FramelessWindowHint | Tool
- WA_TranslucentBackground for QPainter rounded corners
- All content self-painted (no child widgets)
- setAcceptDrops(False) when COLLAPSED

---

## Known Issues
- Audio needs ffmpeg/avconv external binary
- youtube-transcript-api not on Python 3.14 yet
- No progress bar for large files
- OCR plugin not integrated
- exiftool not bundled, silent fallback
- No cancel button

---

## Build
  pip install -r requirements.txt
  pip install -e ../packages/markitdown
  pip install pandas openpyxl pdfminer.six pdfplumber ...
  pyinstaller build.spec

Output: dist/MarkItDownDesk.exe

---

Last updated: 2026-07-13
## Bug Fix Log (2026-07-13)

**Problem:** App stuck on converting... after file drop.

**Root causes:**
1. markitdown not installed -> ImportError caught, but error dialog hidden behind float window
2. Worker Object pattern + QueuedConnection unreliable on this PySide6/Python 3.14

**Fix:**
- Rewrote worker.py: QThread subclass pattern replaces moveToThread+QueuedConnection
- QMessageBox.warning(None, ...) instead of .warning(self, ...)
- Previous-thread cleanup (quit+wait+terminate)

**Verified:** XLSX: 33960 chars, signal delivery ~1450ms

## v0.7.0 - Layout Overhaul (2026-07-13)

**Core change:** Replaced fixed card layout with QSplitter-based resizable panels.

**New class:** `ResettableSplitter(QSplitter)` with double-click reset to default
proportions, hover cursor change (SplitH/SplitV), and minimum size enforcement.

**Layout:**
- Outer: vertical splitter (top 60% | history panel 40%)
- Inner: horizontal splitter (upload | options | preview = 1:1:1)
- Each panel minimum width: 220px; history minimum height: 180px

**Persistence:** Splitter states saved via `window_splitter_outer` / `window_splitter_inner`
settings keys on close, restored on startup.

**QSS:** Added `QSplitter::handle` styles to both dark and light themes.
Handle turns #407BFF with resize cursor on hover via event filter.

**Settings:** Replaced single `window_splitter` property with two keys
(`window_splitter_outer`, `window_splitter_inner`) in AppSettings.

## App Icon Applied (2026-07-14)

User-designed icon with stylized MC logo applied to the application.

**Assets:**
- icons/icon_16.png (16x16, system tray)
- icons/icon_32.png (32x32, window title bar)
- icons/icon_128.png (128x128, Alt+Tab / high-res)
- assets/app_icon.ico (multi-resolution, PyInstaller executable icon)

**Changes:**
- Removed programmatic `_make_app_icon()` from main.py
- Load icon PNGs via QIcon.addFile() with absolute paths
- build.spec: icon set to app_icon.ico; PNGs added as data files
- Unused imports (QPixmap, QPainter, QColor) cleaned up

## Float Icon + Hover/Drag Feedback (2026-07-14)

**Float icon applied:** Custom MC logo icons in 16/32/128px.

**Hover feedback:**
- Hovered state flag tracked in enter/leave event
- Border turns #407BFF on hover (from default gray)
- Background slightly brightens on hover
- Border width increases from 1px to 2px

**Drag feedback:**
- Drop shadow drawn behind the window while dragging
- Border becomes bold #407BFF (3px) while dragging
- Drag state cleared on mouse release

**Collapsed state hover:**
- Icon area background brightens when mouse passes over
- Transition handled via paintEvent repaint on hover change
- All visual states exposed through `_hovered` / `_dragging` flags

## v0.8.0 — Float Icon + Hover/Drag Feedback (2026-07-14)

- Float window now displays your custom MC logo PNG at all states
- Hover: border turns blue + background brightens
- Drag: drop shadow + bold blue border
- Collapsed hover: same glow feedback as expanded

## v0.8.5 — Update System (2026-07-14)

**Core new module:** `app/updater.py`

**Dual version tracking:**
- App version (`__about__.py`): tracks desktop app releases — manually controlled
- Kernel version (`markitdown.__about__.__version__`): tracks upstream markitdown — update target

**Update flow:**
1. App starts → `QTimer.singleShot(3000, main_win._check_update_background)`
2. Background thread queries `GET /repos/microsoft/markitdown/releases/latest`
3. Compares remote tag with local `markitdown.__version__`
4. If newer: `_show_about()` dialog shows "更新可用" with release notes
5. User clicks "立即更新" → `install_update(zip_path)`:
   - Backups `packages/markitdown` → `packages/markitdown.bak`
   - Extracts new kernel from zip
   - Overwrites files (skips __pycache__)
   - `pip install -e packages/markitdown --quiet`
   - Prompts restart
6. Rollback: `rollback()` restores from `.bak` + reinstalls

**Backup:** `markitdown-desktop.v0.8.0-backup.zip` (297 KB) on workspace root.

**Auto-deployed:** app/updater.py, main_window.py (_show_about + _check_update_background), main.py (QTimer trigger).

## v0.9.0 — Code Health: Module Split + Cleanup (2026-07-14)

**Problem:** `main_window.py` had 789 lines with 7 classes mixed together.

**Changes:**
- Extracted TopBar, CollapsibleCard, DropArea, HistoryPanel → `app/widgets.py`
- Extracted SettingsDialog → `app/dialogs.py`
- main_window.py reduced from 789 to 463 lines (41%% reduction)
- All imports moved to module level (no inline imports)
- No circular dependencies between modules

**Final module map:**
  settings.py   (124) — QSettings wrapper
  history.py     (89) — JSON history
  theme.py      (132) — Dark/light/system theme
  worker.py      (50) — QThread conversion
  updater.py    (164) — GitHub update check + install
  widgets.py    (231) — TopBar, CollapsibleCard, DropArea, HistoryPanel
  dialogs.py    (123) — SettingsDialog
  main_window.py(463) — MainWindow, ResettableSplitter

**Health rules going forward:**
- Every change updates DEVELOPER_LOG.md
- Version auto-bumps based on change significance (< 1.0)
- Only user can declare 1.0 release

## v0.10.0 — UI Redesign: New Layout + Color System (2026-07-14)

**Major change:** Complete UI redesign based on reference design.

**New layout:**
- Left sidebar navigation (200px fixed)
- 4-panel splitter: Upload | Options | Preview (60%) / History (40%)
- Top bar with settings/theme/window controls

**New color palette (light theme):**
- Page bg: #F7F8FC, Card bg: #FFFFFF
- Primary btn: #407BFF (white text)
- Title: #1D2129, Body: #4E5969, Sub: #86909C
- Border radius: Cards 16px, Buttons 12px, List items 8px

**New components:**
- SidebarNavigation (dashboard/log/settings nav)
- Enhanced UploadPanel with file type icons
- QueuePanel with status badges
- HistoryPanel with filter tabs

## v0.10.2 — Multi-file Preview + Batch Export (2026-07-14)

**Fix:** Batch conversion now stores all results, not just the last file.

**New:** `_conversion_results` dict tracks per-file output.
**New:** Queue items clickable — clicking a file shows its preview.
**New:** `_save_file(batch=True)` exports all converted files to a folder.
**New:** `UploadPanel.file_selected` signal for per-file preview switching.

## v0.10.3 -- Export-All Button + Retrospective (2026-07-16)

**Added:** Export-All button alongside Export in preview toolbar.
Calls `_save_file(batch=True)` to batch-export all converted files.

**Retrospective -- Common Bugs Introduced During Refactoring:**

1. **Missing imports** -- when splitting modules (widgets.py, dialogs.py),
   frequently forget to add imports for classes used in extracted code
   (QListWidgetItem, QGraphicsDropShadowEffect, QSize, QLabel, etc).
   **Fix:** After ANY module split, run `py_compile.compile(path, doraise=True)`
   on all affected files before reporting success.

2. **Partial replacements** -- when replacing old widget code (DropArea, _file_list_w)
   the replacement often matched the FIRST occurrence but left method bodies
   still referencing deleted attributes (e.g., _refresh_file_list still used
   _file_list_w after the widget was removed).
   **Fix:** After each UI component replacement, grep for all references to
   the old attribute name and verify none remain.

3. **Collateral damage** -- when cleaning up unused imports (QPixmap, QPainter, QColor)
   accidentally overwrote the adjacent QtCore import line, removing QSize.
   **Fix:** Use targeted `str.replace` on specific lines, not entire import blocks.

4. **Console encoding** -- `print()` on files with Chinese text fails with
   `UnicodeEncodeError: gbk` on Windows. Use `@|python` here-strings instead
   of multi-line `python -c` commands.

5. **apply_patch creates files at workspace root** not in the intended subdirectory.
   **Fix:** Always verify file location after apply_patch and move if needed.

6. **Precedent rule:** Before reporting any task as done, run the full import chain:
   `from app.main_window import MainWindow; from app.widgets import *;`
   `from app.dialogs import *; from app.worker import *` etc.

**Precedent added to CI checklist (no more unreported runtime crashes).**

## v0.10.4 — Float Window Queue Integration + Fixes (2026-07-16)

**Bug 1:** Float window drop bypassed queue, went directly to `convert_file`.
  **Fix:** Changed `float_win.file_dropped.connect(main_win.convert_file)`
  to `lambda p: main_win._on_files_dropped([p])` in `main.py`.
  Now float drops appear in queue and participate in batch conversion.

**Bug 2:** `_on_files_dropped` called `_upload_panel.add_file(p)` THEN
  `_refresh_file_list()` which also called `add_file(p)` — double insert.
  **Fix:** Removed inline `add_file`, letting `_refresh_file_list` rebuild queue.

**Bug 3:** Bubble flickered during drag because `dragEnter`/`dragLeave` fired
  rapidly as cursor crossed widget boundary.
  **Fix:** Added `_bubble_hide_timer` (300ms debounce), `_bubble_visible` guard,
  and immediate hide on `dropEvent`. show/hide now idempotent.
