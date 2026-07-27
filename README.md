# 🎧 Mr. Mic

**One key — or just the headset power button — switches your Windows audio.**

A tiny Windows system-tray app that switches the default **speaker AND microphone
together** between a wireless gaming headset (HyperX Cloud II Core Wireless) and your
laptop/desktop speakers + mic — including the *communications* device Discord uses,
so people can actually hear you the moment you switch.

Built because flipping both devices by hand in Volume Mixer before every DCS/Discord
session gets old fast.

## Features

- **Auto-detect** — turn the headset on, everything switches to it (~2 s). Turn it off,
  everything goes back to the laptop (~4 s). No clicks. Works by pinging the dongle's
  battery channel, which only answers while the headset is powered — more reliable
  than Windows device states, which many dongles never change.
- **Hotkey toggle** — `Ctrl+Alt+H` by default; fully configurable, including single
  keys (`pause`) and two-key chords (`v+c`).
- **Headset battery** in the tray tooltip and menu, read straight from the USB dongle
  (low-battery warning included). Windows can't do this for 2.4 GHz dongles — the
  protocol comes from [HyperX-Cloud-2-Battery-Monitor](https://github.com/auto94/HyperX-Cloud-2-Battery-Monitor).
- **Mixer flyout** — middle-click the tray icon: every output device with master
  volume + mute, every app with its icon + slider (click the icon to mute the app),
  plus microphone input levels. EarTrumpet-style, pure dark mode.
- **Switch chimes** — rising notes = headset, falling = laptop, so your ears confirm
  the switch. No toast spam.
- **Featherweight** — ~60 MB RAM, ~0.05 % CPU, zero GPU, below-normal process
  priority. Built for "don't you dare touch my VR frame rate".

## Tray cheat sheet

| Input | Action |
|---|---|
| Left-click | Toggle headset ⇄ laptop |
| Middle-click | Open mixer |
| Right-click | Menu: profiles, devices, battery, settings, guide, exit |
| Green headset icon | On the headset |
| Orange speaker icon | On laptop speakers + mic |

Full guide: `mrmic-guide.html` (also in the right-click menu).

## Running it

**From source** (Python 3.11+ on Windows):

```
pip install -r requirements.txt
pythonw main.py
```

**Or build a standalone exe:**

```
pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --icon mrmic.ico --name MrMic main.py
```

Copy `dist/MrMic.exe` next to `settings.json` and run it. The tray menu's
"Start with Windows" toggle handles autostart.

First run: open `settings.json` and adjust the `profiles` name matches for your
devices (`tools/probe_devices.py` lists everything Windows sees, with IDs).

## Adapting to other headsets

Default-device switching works with **any** audio devices — just edit the name
matches in `settings.json`. Battery + auto-detect are HyperX-specific (vendor HID
request `0x66 0x89`, battery in response byte 4, for the Cloud II Core / Cloud III).
Other models need different request bytes — see
[auto94's repo](https://github.com/auto94/HyperX-Cloud-2-Battery-Monitor) or
[HeadsetControl](https://github.com/Sapd/HeadsetControl) for yours.

## How it works

- Default device switching: the undocumented-but-stable `IPolicyConfig` COM interface
  (the same one SoundSwitch uses), set for all three roles so communications apps
  follow. Via [pycaw](https://github.com/AndreMiras/pycaw) + comtypes.
- Battery/auto-detect: vendor HID report to the dongle via
  [hidapi](https://github.com/trezor/cython-hidapi).
- Tray: [pystray](https://github.com/moses-palmer/pystray) + Pillow-drawn icons;
  mixer: tkinter, per-app audio via Core Audio session APIs.
- Global hotkeys: [keyboard](https://github.com/boppreh/keyboard).

## License

MIT. Battery protocol thanks to
[auto94/HyperX-Cloud-2-Battery-Monitor](https://github.com/auto94/HyperX-Cloud-2-Battery-Monitor) (MIT).
