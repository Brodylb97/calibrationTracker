# Custom Theme System Design

*For Calibration Tracker — PyQt5 desktop application*

---

## 1. Architectural Overview

### Current State (Phase 1 Analysis)

**Theme definitions:** `ui/theme.py` lines 11–87  
- Five built-in themes: Fusion, Taylor's Theme, Tess's Theme, Retina Seering, Vice  
- Each theme is a dict with 11 hex color keys

**Color roles (required keys):**
| Key | Usage |
|-----|-------|
| WINDOW_COLOR | Main window, dialogs, QTabWidget::pane |
| BASE_COLOR | Toolbar, status bar, inputs, table, scrollbars |
| ALT_BASE_COLOR | Hover states, alternate rows |
| TEXT_COLOR | Primary text |
| DISABLED_TEXT | Disabled controls |
| BUTTON_COLOR | Buttons, headers, scroll handles |
| BORDER_COLOR | Borders, dividers |
| ACCENT_ORANGE | Links, focus rings, default button border |
| HIGHLIGHT | Selection, menu hover |
| TOOLTIP_BASE | Tooltip background |
| TOOLTIP_TEXT | Tooltip text |

**Application flow:** `apply_global_style(app, theme_name)` → reads `THEMES[theme_name]` → sets QPalette + builds QSS string → `app.setPalette()` / `app.setStyleSheet()`

**Persistence:** QSettings `CalibrationTracker/CalibrationTracker` — key `"theme"` stores theme *name* only. No theme data persisted.

**Gaps:**
- `set_saved_theme()` rejects names not in `THEMES`; custom themes cannot be saved
- `get_saved_theme()` falls back to DEFAULT_THEME if name missing
- One hard-coded color: `#E67D2A` in `QPushButton:default:hover` (line 250)
- No validation, no editor, no color picker

### Proposed Extension

```
┌─────────────────────────────────────────────────────────────────┐
│  BUILT_IN_THEMES (read-only)     CUSTOM_THEMES (load/save)       │
│  Fusion, Taylor, Tess, ...       from themes.json or QSettings   │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  get_all_themes() → merged {name: colors_dict}                   │
│  get_theme_colors(name) → validated dict or None                 │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  apply_global_style(app, theme_name)  [unchanged signature]      │
│  - Resolves theme from get_all_themes()                          │
│  - Validates before apply                                        │
│  - Falls back to DEFAULT_THEME with user feedback if invalid     │
└─────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  ThemeEditorDialog (new)                                         │
│  - List: built-in (read-only) + custom (editable/deletable)      │
│  - Color rows: label, hex input, picker button                   │
│  - Live preview widget                                           │
│  - Apply (preview) / Save / Revert / Cancel                      │
└─────────────────────────────────────────────────────────────────┘
```

**Principle:** Extend `THEMES` conceptually with custom themes; keep `apply_global_style` as the single entry point. `get_saved_theme` / `set_saved_theme` accept custom names when theme exists in merged registry.

---

## 2. Step-by-Step Implementation Plan

### Step 1: Theme registry and validation (ui/theme.py)
- Define `REQUIRED_THEME_KEYS` constant (tuple of 11 keys)
- Add `validate_theme_colors(colors: dict) -> tuple[bool, str]` — returns (valid, error_message)
- Add `hex_color_regex` or `is_valid_hex(s: str) -> bool` — accepts `#RGB`, `#RRGGBB`
- Add `_load_custom_themes() -> dict[str, dict]` — load from `themes.json` (or QSettings fallback), validate each, return only valid
- Add `get_all_themes() -> dict[str, dict]` — merge `THEMES` + custom, never mutate built-in
- Modify `get_saved_theme()` to resolve from `get_all_themes()` instead of `THEMES`
- Modify `set_saved_theme()` to accept any name in `get_all_themes()`
- Modify `apply_global_style()` to use `get_all_themes()`, validate before apply; on invalid, log + show brief warning, fall back to DEFAULT_THEME
- Parameterize `#E67D2A` (derive from ACCENT_ORANGE with slight lighten, or add ACCENT_ORANGE_HOVER)

### Step 2: Custom theme persistence (ui/theme_storage.py — new)
- `CUSTOM_THEMES_PATH`: `get_base_dir() / "themes.json"` (or under APPDATA)
- `load_custom_themes() -> dict[str, dict]` — read JSON, validate each, skip invalid with log
- `save_custom_themes(themes: dict) -> bool` — write JSON, return success
- `add_custom_theme(name, colors)` / `update_custom_theme` / `delete_custom_theme` — CRUD with validation
- Never write keys that overlap built-in names

### Step 3: Theme data model (domain or ui/theme_models.py)
- `ThemeInfo` dataclass: `name`, `author` (optional), `base_theme` (optional), `colors: dict`
- `theme_from_dict(d: dict) -> ThemeInfo | None` — validate and construct
- `theme_to_dict(t: ThemeInfo) -> dict` — for persistence

### Step 4: Color picker and hex input helper (ui/theme_utils.py)
- `open_color_picker(initial_hex: str, parent) -> str | None` — QColorDialog.getColor, return hex or None
- `validate_hex_input(text: str) -> tuple[bool, str]` — (valid, normalized_hex_or_error)
- Normalize: `#fff` → `#FFFFFF`, `abc` → `#AABBCC`

### Step 5: Theme preview widget (ui/theme_preview.py)
- `ThemePreviewWidget(QWidget)` — small pane showing sample: window, button, input, selected row
- `set_theme_colors(colors: dict)` — update stylesheet of internal widgets
- No external apply; purely visual feedback

### Step 6: Theme Editor dialog (ui/dialogs/theme_editor_dialog.py)
- List on left: built-in (grayed/read-only) + custom (selectable, Delete for custom)
- "Create new from..." — duplicate of selected theme as starting point
- Color rows: QFormLayout or QTableWidget — Label, QLineEdit (hex), QPushButton (picker)
- Connect hex edit `textChanged` → validate, show red border if invalid
- Connect picker → open_color_picker, sync back to hex edit
- Right side: `ThemePreviewWidget` — `set_theme_colors(working_colors)` on any change
- Buttons: Apply (calls `apply_global_style` with working copy, does not save), Save (persist + apply), Revert (restore selected theme), Cancel (restore pre-dialog theme, close)
- On open: snapshot current theme; on Cancel: `apply_global_style(app, snapshot_name)`

### Step 7: Menu integration (ui/main_window.py)
- Add "Customize themes..." to View → Theme submenu (or separate item)
- Opens ThemeEditorDialog
- After dialog Save/Apply: refresh `_theme_action_group` actions to include new custom themes

### Step 8: Focus and UX polish
- Tab order: list → hex fields → picker buttons → preview → Apply / Save / Revert / Cancel
- Invalid hex: red border, tooltip with "Invalid hex color"
- Success: status bar or small inline "Saved" feedback
- Deletion: confirm "Delete theme 'X'? This cannot be undone."

---

## 3. Dialog Wireframe (Textual)

```
┌─ Theme Editor ─────────────────────────────────────────────────────────────┐
│  Themes                    │  Colors                                        │
│  ┌──────────────────────┐  │  ┌─────────────────────────────────────────┐  │
│  │ Fusion            ✓  │  │  │ Window background    [#4F5875] [■]       │  │
│  │ Taylor's Theme       │  │  │ Base color           [#262C3D] [■]       │  │
│  │ Tess's Theme         │  │  │ Alternate base       [#30374A] [■]       │  │
│  │ Retina Seering       │  │  │ Text color           [#F5F5F5] [■]       │  │
│  │ Vice                 │  │  │ Disabled text        [#9299AE] [■]       │  │
│  │ ───────────────────  │  │  │ Button color         [#333A4F] [■]       │  │
│  │ My Custom Theme   ●  │  │  │ Border color         [#1E3E62] [■]       │  │
│  └──────────────────────┘  │  │ Accent orange        [#DC6D18] [■]       │  │
│                            │  │ Highlight            [#DC6D18] [■]       │  │
│  [Create new from...] [Del]│  │ Tooltip base         [#121C2A] [■]       │  │
│                            │  │ Tooltip text         [#F5F5F5] [■]       │  │
│                            │  └─────────────────────────────────────────┘  │
│                            │  ┌─ Live preview ──────────────────────────┐  │
│                            │  │ [Sample window with button, input, row] │  │
│                            │  └─────────────────────────────────────────┘  │
│                            └──────────────────────────────────────────────  │
│  [Apply] [Save] [Revert]                                    [Cancel] [OK]  │
└────────────────────────────────────────────────────────────────────────────┘
```

- **List:** Built-in themes show checkmark if active; custom themes show bullet; selected theme highlighted
- **[■]:** Color picker button; shows current color as background
- **Apply:** Temporarily applies working theme to app; does not save
- **Save:** Persists custom theme (if custom selected/created) and applies
- **Revert:** Resets working copy to last saved/selected theme
- **Cancel:** Restores theme that was active when dialog opened; closes without saving

---

## 4. Key Classes and Functions

| Name | Module | Purpose |
|------|--------|---------|
| `REQUIRED_THEME_KEYS` | theme.py | Tuple of 11 required color keys |
| `validate_theme_colors(colors) -> (bool, str)` | theme.py | Validate dict has all keys, valid hex |
| `get_all_themes() -> dict` | theme.py | Built-in + custom merged |
| `get_theme_colors(name) -> dict \| None` | theme.py | Single theme or None |
| `load_custom_themes() -> dict` | theme_storage.py | Load from themes.json |
| `save_custom_themes(themes) -> bool` | theme_storage.py | Persist custom themes |
| `add_custom_theme(name, colors) -> bool` | theme_storage.py | Add with validation |
| `delete_custom_theme(name) -> bool` | theme_storage.py | Remove custom theme |
| `open_color_picker(hex, parent) -> str \| None` | theme_utils.py | QColorDialog wrapper |
| `normalize_hex(s) -> str \| None` | theme_utils.py | Validate and normalize hex |
| `ThemePreviewWidget` | theme_preview.py | Live preview pane |
| `ThemeEditorDialog` | dialogs/theme_editor_dialog.py | Full editor UI |
| `ThemeInfo` | theme_models.py | Dataclass with name, author?, base?, colors |

---

## 5. One Concrete Code Example

### `validate_theme_colors` and `normalize_hex`

```python
# ui/theme.py (additions)

import re

REQUIRED_THEME_KEYS = (
    "WINDOW_COLOR", "BASE_COLOR", "ALT_BASE_COLOR", "TEXT_COLOR",
    "DISABLED_TEXT", "BUTTON_COLOR", "BORDER_COLOR", "ACCENT_ORANGE",
    "HIGHLIGHT", "TOOLTIP_BASE", "TOOLTIP_TEXT",
)

_HEX_PATTERN = re.compile(r"^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


def normalize_hex(s: str) -> str | None:
    """Validate and normalize hex to #RRGGBB. Returns None if invalid."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    m = _HEX_PATTERN.match(s)
    if not m:
        return None
    raw = m.group(1)
    if len(raw) == 3:
        return f"#{raw[0]*2}{raw[1]*2}{raw[2]*2}".upper()
    return f"#{raw}".upper()


def validate_theme_colors(colors: dict) -> tuple[bool, str]:
    """
    Validate theme dict. Returns (True, "") if valid, else (False, error_message).
    """
    if not isinstance(colors, dict):
        return False, "Theme must be a dict"
    for key in REQUIRED_THEME_KEYS:
        if key not in colors:
            return False, f"Missing required key: {key}"
        val = colors[key]
        if not isinstance(val, str) or not val.strip():
            return False, f"Invalid value for {key}: must be non-empty string"
        if normalize_hex(val) is None:
            return False, f"Invalid hex for {key}: {val!r}"
    return True, ""
```

---

## 6. UX Improvements (Ranked)

| # | Improvement | Impact | Effort | Risk | Justification |
|---|-------------|--------|--------|------|---------------|
| 1 | Invalid hex: red border + tooltip | High | Low | Low | Immediate feedback; prevents silent bad state |
| 2 | Color picker button shows current color as background | High | Low | Low | At-a-glance verification without opening picker |
| 3 | Tab order: list → hex fields → picker → preview → buttons | Medium | Low | Low | Keyboard users can navigate fully |
| 4 | "Create new from..." prefills all colors from selection | Medium | Low | Low | Reduces repetitive entry |
| 5 | Delete confirmation: "Delete theme 'X'? Cannot be undone." | Medium | Low | Low | Prevents accidental loss |
| 6 | Status message on Save: "Theme 'X' saved" | Medium | Low | Low | Clear success feedback |
| 7 | Disabled-state styling on Revert when no changes | Low | Low | Low | Clarifies when Revert has no effect |
| 8 | Contrast warning (optional): if TEXT_COLOR on BASE_COLOR fails WCAG AA, show hint | Medium | Medium | Low | Improves accessibility; non-blocking |
| 9 | Group color rows (e.g. "Backgrounds", "Text", "Accents") | Low | Medium | Low | Clearer structure; nice-to-have |
| 10 | Focus ring on hex field when invalid | Low | Low | Low | Reinforces error state for keyboard users |

---

## 7. Storage Format (themes.json)

```json
{
  "version": 1,
  "themes": {
    "My Custom Theme": {
      "author": "Optional",
      "base_theme": "Fusion",
      "colors": {
        "WINDOW_COLOR": "#4F5875",
        "BASE_COLOR": "#262C3D",
        ...
      }
    }
  }
}
```

- `version`: for future schema evolution
- Built-in names are never written; custom names only
- On load: validate each theme; skip invalid with log; never crash
- On corrupted file: log, return `{}`, allow user to recreate

---

## 8. Safety Rules Summary

- **Never overwrite built-in themes** — custom themes use separate storage; built-in keys never appear in themes.json
- **Validate before apply** — `apply_global_style` checks theme; invalid → fallback + message
- **Validate on load** — corrupted or partial custom themes skipped
- **Cancel restores** — dialog keeps snapshot of theme at open; Cancel reapplies it
- **Preview is non-destructive** — preview pane uses local stylesheet; Apply/Save are explicit user actions
- **No silent fallback** — invalid theme triggers visible feedback (message or inline error)

---

*End of design document.*
