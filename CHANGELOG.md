# Changes

## 1.0.2

- Use the operating system's interface font and size, including Cinnamon/GNOME text scaling. Reopen the app after changing desktop font settings.
- Keep toolbar actions reachable at larger text sizes by wrapping the acquisition and utility groups. Size table rows and numeric columns to their content.
- Preserve PDF/JPEG layout and caption settings; interface typography does not change exported sheets.

## 1.0.1

- Keep PDF image streams readable by strict consumers when compressed page data falls on an ASCII85 line boundary. Preview, JPEG output and source preservation are unchanged.
- Add an internal `--qa-ui FRESH_DIRECTORY` launch option for interactive package checks with isolated INI preferences. It rejects existing folders and link/junction paths, and performs no automatic file operation.
