# Changes

## 1.2.10 — 2026-11-04

- Follow Linux desktop font, size, light/dark and accent preferences with independent providers and readable fallbacks; appearance detection needs no system Python or PyGObject.
- Add saved app-wide appearance controls, Refresh and appearance-only Reset, with fitted settings dialogs.
- Measure compact window minimums from current controls instead of multiplying a fixed workspace by font size. Preserve useful previews and use scrolling only on constrained screens.
- Style checkbox choices as accent buttons while retaining checkbox state and keyboard behavior. Existing photo processing and output formats are unchanged.


## 1.1.0 — 2026-11-03

All interface text follows the configured desktop UI size, including headings, Help, tables and status. Document pages, exported captions and watermarks retain their own content typography.

Primary actions, enabled toggles, selections and progress use the system accent, with readable contrasting text. Secondary actions stay neutral. Desktop settings helpers use the host library environment, including in portable packages.

Compact controls preserve more vertical working space. File Renamer keeps its rule controls, Rename and Undo together: Rename shifts horizontally when needed, and resizing stops before the row collides. Layouts adapt to enlarged fonts and constrained monitor work areas.

## 1.0.5 — 2026-11-03

- Keep enlarged preview notes below the page preview when a small screen requires scrolling.
- Restore a useful minimum window size so the preview, everyday controls, task actions and status remain visible together.
- Measure the layout at the system font size; adapt the minimum to the current monitor and use scrolling when its work area is genuinely too small.
- Repair undersized restored windows while keeping the system-font improvements.

## 1.0.2

- Use the operating system's interface font and size, including Cinnamon/GNOME text scaling. Reopen the app after changing desktop font settings.
- Keep toolbar actions reachable at larger text sizes by wrapping the acquisition and utility groups. Size table rows and numeric columns to their content.
- Preserve PDF/JPEG layout and caption settings; interface typography does not change exported sheets.

## 1.0.1

- Keep PDF image streams readable by strict consumers when compressed page data falls on an ASCII85 line boundary. Preview, JPEG output and source preservation are unchanged.
- Add an internal `--qa-ui FRESH_DIRECTORY` launch option for interactive package checks with isolated INI preferences. It rejects existing folders and link/junction paths, and performs no automatic file operation.
