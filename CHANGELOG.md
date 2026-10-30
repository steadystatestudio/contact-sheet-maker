# Changes

## 1.0.0 candidate

- Honor valid embedded ICC profiles in JPEG/PNG inputs, including CMYK and wide-gamut RGB. Convert colors to sRGB before blending transparency onto white. Report invalid or incompatible profiles with a concrete recovery step.
- Keep the import, Help, Donate and Settings toolbar visible while scrolling a short workspace.
- Improve selected-row, progress and pressed-control text contrast in both appearances while retaining the existing primary-action and focus colors.
- Exercise color-profile conversion in the actual packaged executable smoke test.
- Isolate the Windows packager's DLL search path from unrelated native tools, preventing incompatible ICU/UCRT libraries from entering the download.
- Allow stable and beta release tags to be staged as exact-commit drafts; automatic publication remains disabled. The existing user-observation gate is tracked separately from automated checks.

See `docs/RELEASE-CANDIDATE.md` for verification evidence and unresolved release gates.
