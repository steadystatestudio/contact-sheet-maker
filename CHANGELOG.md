# Changes

## 1.0.1

- Keep PDF image streams readable by strict consumers when compressed page data falls on an ASCII85 line boundary. Preview, JPEG output and source preservation are unchanged.
- Add an internal `--qa-ui FRESH_DIRECTORY` launch option for interactive package checks with isolated INI preferences. It rejects existing folders and link/junction paths, and performs no automatic file operation.
