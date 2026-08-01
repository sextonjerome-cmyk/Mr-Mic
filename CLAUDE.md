# Mr. Mic — one-key audio switcher for whatever you're listening on

A small Python tray app for Jerome's gaming laptop. One hotkey — or just turning a device
on / plugging it in — switches the Windows default output AND input to any of an editable
list of devices: the HyperX Cloud II Core Wireless (USB dongle), wired earphones in the
headphone jack, Skullcandy Hesh ANC over Bluetooth, the laptop speakers + mic. It sets the
Communications defaults too, so Discord follows. Also reads headset battery straight from
the dongle, and can mute the speakers or mic outright from the tray. Built because
flipping devices by hand in Volume Mixer before every DCS/Discord session was misery.

Think of it as being in the same family as **EarTrumpet** — a small Windows tray utility
for audio, with the middle-click mixer for per-app volume. Where it goes further is the
automatic switching: turn the headset on, and Windows follows without being asked.

It is a self-contained app. It is **not** related to any other project in this folder,
and in particular has nothing to do with CobbAttack (that one is voice recognition for
DCS — a completely different program that happens to also be written in Python).

Binding rules live in `.claude/rules/` and load automatically:
`audio-api.md` (CoreAudio/IPolicyConfig + battery HID protocol), `ui-theme.md`
(CobbAttack palette, look-and-feel), `quality.md` (testing gates, budgets).

## Talking to me

**Explain things simply, in a few words.** Short plain-English answers, not walls of
detail. Skip the jargon unless I ask. Detail on request, or when the decision is mine
(money, deleting things, hard-to-undo). Don't soften real problems to keep it brief.

## Architecture (one breath)

Hotkey (`keyboard`) or the watch thread → `activate(device)` → IPolicyConfig
`SetDefaultEndpoint` for render + capture, all three roles → tray icon/tooltip updates
(`pystray` + PIL). Battery: vendor HID request to the dongle every poll (`hidapi`).
Endpoints are matched by saved ID first, name substring as fallback.

## The device list (the core idea)

`settings.json` holds an ordered `devices` list, not a fixed headset/laptop pair. Each
entry has a label, an icon kind, output/input match + id, `enabled`, `auto`, and
`detect`. Order is priority.

**Auto-switch rule:** a device that *just became available* wins, whatever its priority —
turning something on is a deliberate act. Priority only decides where to land when the
device in use disappears. `_auto_switch()` in `main.py` is the whole rule; the transition
table is worth re-reading before changing it.

`detect` is `"endpoint"` (is it Active in Windows?) for everything except the HyperX,
which is `"battery"` — that dongle's endpoint stays Active whether the headset is on or
off, so a battery reply is the only on/off signal there is.

Old `settings.json` files with the two-entry `profiles` dict migrate automatically in
`config.load()` and keep their saved endpoint ids.

## Tray clicks

`_hook_clicks()` takes over the tray's Win32 messages: left = switch, double-left = mute
(configurable, `tray_double_click`), middle = mixer, right = the menu. Windows sends a
double click as UP, DBLCLK, UP — so the first click's action fires before anyone knows a
double was coming, and the trailing UP would fire it again. Hence the single click is held
for `GetDoubleClickTime()` and the UP after a DBLCLK is ignored. That delay is the price
of the feature; `tray_double_click: "off"` removes both.

## File map

- `main.py` — wiring: MrMic class, tray menu, device watch thread, dark-menu opt-in
- `audio.py` — enumerate endpoints, get/set Windows defaults (IPolicyConfig), mute
- `battery.py` — HyperX dongle battery over HID (doubles as on/off signal)
- `btaudio.py` — connect/disconnect paired Bluetooth audio devices (no admin needed)
- `ui.py` — the one Tk thread; mixer and settings are Toplevels on it
- `settings_ui.py` — settings window: hotkey capture, add/edit/reorder/disable devices
- `mixer.py` — middle-click flyout: per-device master + per-app volume sliders
- `chime.py` — synthesised switch sounds, six styles (rising = worn, falling = speakers)
- `hotkeys.py` — named global hotkeys; `config.py` — defaults over `settings.json`
- `tray.py` — PIL icons per device kind; `theme.py` — palette
- `tools/probe_devices.py` — list endpoints / `--watch` for state changes
- `run-mrmic.bat` — hidden launcher (pythonw)

## Standalone — where the look came from

**Mr. Mic is its own app and does not relate to any other project here.** It switches
audio devices for a headset. That's the whole job.

One cosmetic thing was borrowed at the start: the hex values in `theme.py` were
hand-copied from CobbAttack (`../CobbAttack/ui.py`), an unrelated DCS voice-recognition
app, along with its `settings.json` layout and PyInstaller packaging approach. That is
history, not a dependency — nothing is imported, nothing needs to stay in sync, and
Mr. Mic's colors can change freely without looking at CobbAttack at all.

## Packaging

Ships as one-file `MrMic.exe` (PyInstaller, `mrmic.ico`); rebuild with
`python -m PyInstaller --noconfirm --onefile --windowed --icon mrmic.ico --name MrMic main.py`
then copy `dist/MrMic.exe` to the project root (settings/chimes/guide live next to the
exe — `config.APP_DIR` handles frozen vs dev). Autostart shortcut targets the exe.
User guide: `mrmic-guide.html` (linked from the tray menu).

## Planned (not built yet)

- **Echo speaker** as a device: Jerome wants to send audio to an Amazon Echo. Nothing to
  build in Mr. Mic *if* the Echo shows up as a Windows output endpoint (Bluetooth pairing
  does this) — then it is just "+ Add device" in Settings. If he means Alexa Cast /
  Wi-Fi streaming, Windows has no endpoint for it and something else is needed.
  Check which one it is before writing code.
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
