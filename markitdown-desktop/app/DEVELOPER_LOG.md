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

## v0.10.6 — DragBubble Restore + Queue Fixes (2026-07-16)

**Bubble:** Restored standalone DragBubble widget with show/hide-only logic
(created once in `__init__`, never `deleteLater`).
Debounce timer (200ms) prevents rapid toggle flicker.

**Queue fix:** `_process_next_in_queue` now skips files already in
`_conversion_results` (no re-conversion).
**Preview fix:** `_on_file_selected` sets `_file_manually_selected` flag;
`_on_convert_finished` only auto-switches preview when flag is False.
`_start_convert` clears the flag so first run auto-switches normally.

## v0.10.7 — Clean Batch Conversion Rewrite (2026-07-16)

Restored main_window.py from v0.8.0 backup, applied minimal batch logic:

- Added `_conversion_results = {}` dict in __init__
- Added `_process_next_in_queue()`: skips converted, marks status, converts next
- Added `_on_file_selected()`: click queue item to preview its result
- Updated `_start_convert()`: starts queue processing instead of single file
- Updated `_on_convert_finished()`: stores result, advances queue
- Updated `_on_convert_error()`: skips(error does not block queue)
No ghost indentation, no duplicate methods, no file corruption.

## v0.11.0 -- Full UI Refactor (2026-07-18)

**Spec-driven redesign based on UI Development Spec.**

**New layout:** Sidebar(240px) + TopBar(56px) + Stacked Content Pages
**New components:** Sidebar navigation, stacked page system
**Design tokens applied:** #F7F8FC bg, #FFFFFF cards, 8px radius, #407BFF primary
**Cleanup:** Removed old icon assets no longer in use.
**Pages (in progress):** Batch Convert, History Log, Settings

## v0.11.0 phase 1 -- Sidebar + Page Framework (2026-07-18)

**New:** Sidebar (240px) with 3 nav items (batch convert, history, settings)
**New:** QStackedWidget with 3 pages for page-based navigation
**New:** Page switching via sidebar clicks
**New:** History page with full history list (synced with bottom panel)
**Cleanup:** Removed old unused icon assets
**Next:** Settings page implementation, history page filters, design tokens

## v0.11.0 phase 2 -- Settings + History Pages (2026-07-18)

**Settings page:** Save path, theme mode, history max entries, save button.
Three helper methods: _browse_save_path, _load_settings_values, _save_settings_values.
**History page:** Full history list synced with bottom panel.
**Cleanup:** Removed old SettingsDialog references where superseded by in-page version.

## v0.11.1 — HTML Reference Redesign (2026-07-18)

**Complete layout restructured to match HTML reference.**

**Old:** Sidebar(240px) + TopBar(tool buttons) + Content
**New:** TopNavBar(nav + actions) + Content (grid: 280/1fr/380)

**TopNavBar:** Logo "M" + gradient, nav items (文件/历史/设置),
action buttons (导入/批量导入/清空/复制MD/导出), theme toggle
**Brand color:** #6366F1 (indigo) with gradient to #8B5CF6
**Card radius:** 12px, **Button radius:** 6-8px
**Colors:** success #10B981, error #EF4444, warning #F59E0B
**Removed:** Inline TopBar, Sidebar widget from main_window.py

## v0.11.2 — Batch Conversion Fix + Checkbox Indicator (2026-07-18)

**Batch conversion (bug fix):**
- _start_convert was still the old single-file version (c.replace failed due to CRLF vs LF)
- Replaced _start_convert with queue-processing version (_process_next_in_queue)
- Added _convert_btn.clicked → _start_convert (was lost during _connect_signals rewrite)
- Added _upload_panel.file_selected → _on_file_selected (queue item click → preview)

**Checkbox indicator:**
- check.png was deleted during asset cleanup; recreated as 18x18 white checkmark
- light.qss and dark.qss: added image: url(assets/check.png) to QCheckBox::indicator:checked
- theme.py URL resolution (url(assets/…) → absolute path) already in place

**UploadPanel cleanup:**
- Removed \"一键转换\" and \"新建转换\" buttons (user request)
- Drop zone is now clickable (mouseReleaseEvent → QFileDialog → add_file)

**Root cause debugged:** CRLF line endings (\r\n) in .py files caused all c.replace() with
\n to silently fail. Fixed by normalizing to LF before replacements.


## v0.11.5 — Dark Theme Fix + Settings Theme Options (2026-07-18)

**Core bug fixed:** `_on_settings_theme_toggled` method was missing from `main_window.py`.
Theme radio buttons in settings page connected to it on init but the method was never defined,
causing AttributeError on app startup.

**Fix:**
- Added `_on_settings_theme_toggled` to MainWindow class — immediately applies theme when
  any radio button is clicked, syncs settings to disk
- Added `_on_theme_toggled` to SettingsDialog — same immediate-apply behavior when user
  clicks theme radio buttons in the dialog (was previously only applied on OK press)
- Fixed indentation issues in main_window.py (3-space vs 4-space methods)

**QSS overhaul:**
- Completely rewrote `dark.qss` with comprehensive selectors for all current UI widgets:
  TopNavBar buttons, CardWidget, HistoryPanel, UploadDropZone, SettingsDialog, etc.
- Updated `light.qss` to match, adding missing selectors for CardWidget, HistoryPanel,
  nav buttons, tool buttons, icon buttons
- Both themes now properly style QComboBox, QSpinBox, QGroupBox, QRadioButton, QCheckBox
- Consistent color palette: #303643 borders for dark, #E5E6EB for light
- Checkbox and radio button indicators have hover state styling


## v0.11.6 — Icon Files Restoration (2026-07-18)

**Warning:** `QSystemTrayIcon::setVisible: No Icon set` — system tray had no icon.

**Root cause:** During UI refactors in v0.11.0, the icon_*.png files were never copied
from user's source directory (`markconvert_icon/` and `markconvert_float_icon/`) to the
`assets/` folder. The code at `main.py:33-35` looked for them but they didn't exist.

**Fix:** Copied all 6 icon files to `assets/`:
- icon_16/32/128.png — app/tray window icon
- markconvert_float_16/32/128.png — float window custom-drawn icon


## v0.11.8 — Float Window Icon Background Fix (2026-07-18)

**Bug:** Collapsed float window showed a dark gray rounded rectangle with border
behind the icon PNG, making the icon look like it had a black frame with sharp corners.

**Root cause:** `paintEvent` unconditionally filled the entire window with 
`#2d2d2d` and drew a 1px border, even in COLLAPSED state. The icon PNG
already contains its own blue-purple gradient background.

**Fix:** Modified `paintEvent` to skip the background fill and border drawing
when `self._state == State.COLLAPSED`. Only the icon PNG is drawn directly
on the transparent window (WA_TranslucentBackground handles the rest).


## v0.11.9 — Remove Heading Level + Fix Label Backgrounds (2026-07-18)

**1. Removed "标题层级" dropdown:**
- This UI control was never wired up to the conversion pipeline
- Deleted heading_cb QComboBox + "标题层级:" label + associated QHBoxLayout from options card

**2. Removed label background bleed:**
- Generic QSS rule `QMainWindow, QWidget { background-color: ... }` applied the page
  background color to ALL QWidget instances, including QLabels inside cards/panels
- This created a visible color mismatch (label bg ≠ parent card bg)
- **Fix:** Changed `QMainWindow, QWidget` to just `QMainWindow` so child widgets
  don't inherit the page background; added explicit `QLabel { background: transparent; }`
- Also replaced `color: palette(mid)` with explicit `#86909C` to avoid palette resolution issues


## v0.11.10 — Pre-warm Kernel Version Cache + Silence ffmpeg Warning (2026-07-18)

**Problem:** Every fresh app start → first time opening settings → `get_local_kernel_version()`
imported markitdown (cache miss) → pydub loaded → ffmpeg check → terminal warning + UI lag.

**Fix 1 — Pre-warm cache:** Added `get_local_kernel_version()` call in `main.py` right after
core module initialization. Import happens during app startup (user already waits for this),
kernel version is cached before user can click settings.

**Fix 2 — Silence ffmpeg warning:** Added `warnings.filterwarnings("ignore", ...)` in `main.py`
for `RuntimeWarning` from `pydub.utils` module. Warning was harmless but visually noisy.


## v0.11.11 — Nav Buttons: "文件" Opens File, "历史" Toggles History Size (2026-07-18)

**Problem:** TopNavBar "文件" and "历史" buttons had no functionality — only highlighted.

**Changes to `_on_nav_changed`:**
- "文件" → calls `_open_file()` (opens multi-format file dialog)
- "历史" → calls `_toggle_history_size()`

**New method `_toggle_history_size`:**
- First click: outer splitter → 50/50 (history panel expands to ~50% height)
- Second click: restores default 60/40 ratio
- Uses ratio detection (45%-55% window) to determine toggle direction
- Status bar updates: "历史面板已展开" / "已收起历史面板"


## v0.11.12 — History Panel: Default Height 22% + List Expands With Panel (2026-07-18)

**Default height too tall:** Splitter ratio was 600:400 (40% for history). Changed
to [780, 220] — history panel now occupies ~22% of window.

**List didn't grow with panel:** HistoryPanel's QListWidget had `setMaximumHeight(160)`.
When expanding the panel, only the empty padding below the list grew — actual file
list was capped at 160px.

**Fix:** Removed `setMaximumHeight(160)`, changed `layout.addWidget(self._list)` to
`layout.addWidget(self._list, 1)` (stretch factor). List now fills all available
space and expands/contracts with the splitter.


## v1.0.0 — 正式版 (2026-07-18)

**Float window icon aliasing fix:**
- Added `SmoothPixmapTransform` render hint to float window paintEvent.
  Previously only `Antialiasing` was enabled (smooths vector lines), but
  pixmap scaling needs `SmoothPixmapTransform` for proper downscale quality.
- Expanded source image loader to support 256px and 512px in addition to
  16/32/128. If a higher-res PNG is placed in assets/, it will be used
  as the preferred source for scaling down to the display size (~28px).

**Inner splitter ratio:** Changed from 1:1:1 (333, 333, 334) to 2:1:4
(286, 143, 571) — upload/options/preview. Preview now gets ~57% of space.


## v1.0.1 — Settings: Float Window Toggle + Close Behavior (2026-07-18)

**Two new settings options:**

**1. 悬浮窗开关 (Toggle Float Window)**
- Checkbox in SettingsDialog: "开启悬浮窗"
- Immediate effect: uncheck hides the float window, check shows it
- Persisted via `settings.show_float_window` (QSettings, default True)
- On startup, float_win.show() is gated behind this setting
- Passed to SettingsDialog via `float_win` parameter for direct show/hide

**2. 关闭主窗口时 (Close Behavior)**
- Two radio buttons: "最小化到系统托盘" / "完全退出应用"
- Default: minimize to tray (preserves existing behavior)
- Persisted via `settings.close_to_tray` (QSettings, default True)
- closeEvent checks the setting: hide() or QApplication.quit()

**File changes:**
- settings.py: added show_float_window + close_to_tray properties
- dialogs.py: added float_win param, float window groupbox, close behavior groupbox
- main_window.py: added _float_win attr + set_float_window(), updated closeEvent
- main.py: wired float_win to main_window, gated float_win.show()


## v1.0.2 — Theme Button + OCR Integration Prep (2026-07-18)

**1. TopNavBar theme button now functional:**
- Changed button from dead symbol to working theme toggle
- Size: 28x28 → 38x38, uses QSS iconBtn styling (18px font, proper hover)
- Icons: ☀ (light theme) / ☾ (dark theme), updates automatically on theme change
- Connected to ThemeManager.toggle() via _theme_btn.clicked signal
- Icon updates in _on_theme_changed (covers all paths: button click, settings, tray menu)

**2. OCR checkox wired to conversion pipeline:**
- worker.py: start_convert() accepts enable_ocr param, passed to MarkItDown(enable_plugins=...)
- main_window.py: _convert_file() reads _ocr_cb state and passes to worker
- Status bar shows "(OCR已开启)" when enabled

**3. Azure Document Intelligence tutorial:**
- Created docs/azure-ocr-setup.md with step-by-step setup guide
- Covers: resource creation, key acquisition, dependency installation, environment config


## v1.1.0 — Code Optimization & Cleanup (2026-07-18)

**Removed dead code (~250 lines total):**
- widgets.py: Removed TopBar, DropArea, Sidebar classes (all replaced by newer 
  equivalents — TopNavBar, UploadPanel, and in-page navigation)
- float_window.py: Removed _draw_hover_text() and _draw_active() methods 
  (defined but never called since the hover/active states rely on other 
  drawing paths)

**Deduplicated signal connections:**
- _connect_signals had 5 file_selected and 2 convert_btn.clicked connections 
  pointing to the same handler — reduced to 2 total. Prevents redundant 
  event processing.

**Removed dead methods:**
- convert_file() in main_window.py (public wrapper for _convert_file, never 
  called from outside the class)

**Cleaned up unused imports:**
- history.py: removed is_dataclass
- updater.py: removed unused field
- dialogs.py: removed unused AppSettings, ThemeManager imports

**Other:**
- Removed __pycache__ (172KB of stale bytecode)
- widgets.py reduced from 563 to 366 lines (-35%%)


## v1.1.1 — Startup Speed Optimization (2026-07-18)

**Problem:** Markitdown pre-warming (importing markitdown + pydub) was done
synchronously during startup, blocking the UI from appearing for ~1.1s.

**Before:** Total startup = 152ms (other) + 1117ms (markitdown) = 1270ms.

**Fix:** Moved `get_local_kernel_version()` from synchronous startup to
`QTimer.singleShot(0, ...)` after window show. UI now appears in ~500ms,
markitdown loads in the background.

**After:** UI ready in ~505ms. Deferred markitdown import (~1s) runs
asynchronously — cache is populated before user can open settings.
