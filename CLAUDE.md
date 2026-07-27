# Mr. Mic — one-key audio switcher for the HyperX headset

A small Python tray app for Jerome's gaming laptop. One hotkey (or the headset's own
power button, auto-detected) switches the Windows default output AND input between the
HyperX Cloud II Core Wireless (USB dongle) and the laptop speakers + mic — including the
Communications defaults, so Discord follows. Also reads headset battery straight from the
dongle. Built because flipping devices by hand in Volume Mixer before every DCS/Discord
session was misery.

Binding rules live in `.claude/rules/` and load automatically:
`audio-api.md` (CoreAudio/IPolicyConfig + battery HID protocol), `ui-theme.md`
(CobbAttack palette, look-and-feel), `quality.md` (testing gates, budgets).

## Talking to me

**Explain things simply, in a few words.** Short plain-English answers, not walls of
detail. Skip the jargon unless I ask. Detail on request, or when the decision is mine
(money, deleting things, hard-to-undo). Don't soften real problems to keep it brief.

## Architecture (one breath)

Hotkey (`keyboard`) or headset-power poll → `set_profile()` → IPolicyConfig
`SetDefaultEndpoint` for render + capture, all three roles → tray icon/tooltip updates
(`pystray` + PIL). Battery: vendor HID request to the dongle every 60 s (`hidapi`).
Devices are matched by saved endpoint ID first, name substring as fallback.

## File map

- `main.py` — wiring: MrMic class, tray menu, headset-watch thread, dark-menu opt-in
- `audio.py` — enumerate endpoints, get/set Windows defaults (IPolicyConfig)
- `battery.py` — HyperX dongle battery over HID (doubles as on/off signal)
- `mixer.py` — middle-click flyout: per-device master + per-app volume sliders
- `chime.py` — generated switch sounds (rising = headset, falling = laptop)
- `hotkeys.py` — global hotkey binding; `config.py` — defaults over `settings.json`
- `tray.py` — PIL icons (green headset / amber speaker); `theme.py` — palette
- `tools/probe_devices.py` — list endpoints / `--watch` for state changes
- `run-mrmic.bat` — hidden launcher (pythonw)

## Sibling project

CobbAttack (`../Viacom project/`) is the styling and conventions reference — same theme
constants, settings.json pattern, PyInstaller packaging. Copy patterns, not dependencies.

## Packaging

Ships as one-file `MrMic.exe` (PyInstaller, `mrmic.ico`); rebuild with
`python -m PyInstaller --noconfirm --onefile --windowed --icon mrmic.ico --name MrMic main.py`
then copy `dist/MrMic.exe` to the project root (settings/chimes/guide live next to the
exe — `config.APP_DIR` handles frozen vs dev). Autostart shortcut targets the exe.
User guide: `mrmic-guide.html` (linked from the tray menu).

## Planned (not built yet)

- **Quest 3 battery** (next session): show headset battery for Jerome's Meta Quest 3 in
  the tray menu (when Quest/Virtual Desktop output is selected) and in the mixer header,
  like the HyperX one. No dongle to query — likely path is ADB (`adb shell dumpsys
  battery` over Wi-Fi/USB, needs developer mode enabled on the Quest) or whatever
  Virtual Desktop exposes; investigate both. He uses Virtual Desktop, not Link.
- **Proper installer** (Jerome asked 2026-07-27): ship a real Windows installer instead
  of handing someone a zip. Should put Mr. Mic somewhere sane (not OneDrive), create the
  Start Menu + autostart shortcuts, bundle `mrmic.ico` and `mrmic-guide.html`, and
  uninstall cleanly while leaving `settings.json` alone. Inno Setup is the likely tool
  (free, single .iss script, plays well with a PyInstaller onefile exe).
- Voice control via the Whisper stack ("Mr. Mic, headset!").
