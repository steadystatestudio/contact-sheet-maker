# Desktop appearance

All interface text uses one selected UI family and size, including dialogs, Help, menus, tooltips and status. Headings use weight. Exported photo, caption and document typography stays controlled by the task; window decorations belong to the desktop.

Open **Settings** to choose System, Light or Dark, use the system font or a custom family and 6–72 point size, and choose a system or custom accent. **Refresh system settings** checks the desktop again while preserving saved overrides. **Reset appearance to System** stages only appearance changes; Save applies them and Cancel discards them. Theme changes preserve the selected font. Existing layout and processing preferences remain separate.

On Linux, font, size, light/dark preference and accent resolve independently. Explicit app choices take priority, followed by an explicitly selected qt6ct configuration, supported desktop preferences, captured Qt values and readable fallbacks. The bundled portal reader supplies supported color preferences. KDE configuration and an isolated native GTK 3 helper supply other available desktop values, including GTK's X11 settings integration. Basic matching requires neither system Python nor PyGObject. Missing integrations, invalid settings and a failed or timed-out helper leave the app usable.

Qt retains display scaling. Desktop font normalization uses the provider's actual size, DPI and scale instead of applying one X11 multiplier. Desktop environments and installed theme integrations differ, so a fallback is not proof of system matching. Use Refresh after changing GTK preferences; some platform integrations require restarting the app. Windows retains native font and personalization integration and supported notifications.

Primary actions, enabled choice controls, selections and progress use the resolved accent with readable text and visible focus; ordinary secondary actions stay neutral. The app records bounded, per-property source and fallback information locally in its application-data folder. Diagnostics exclude document names, user names and home paths, and nothing is uploaded automatically.

Main windows reserve a useful workspace and measure complete toolbar/action rows at the selected font. Controls stay on one row when the monitor fits them. Ordinary settings/color forms fit their contents; scrolling is used when a small work area cannot contain them. Content previews and long file lists remain scrollable normally.
