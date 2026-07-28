# Audio + hardware rules

## Switching default devices
- Default-device changes go through `IPolicyConfig.SetDefaultEndpoint`
  (CLSID `{870af99c-171d-4f9e-af0d-e63df40c2bc9}`) in `audio.py` — undocumented but
  stable since Win7; same mechanism SoundSwitch uses. Don't swap it for anything else
  without testing all three roles.
- Always set ALL THREE roles (Console 0, Multimedia 1, Communications 2) for both
  render and capture. Discord follows the Communications role — skipping it recreates
  the exact bug this app exists to fix.
- Never hardcode endpoint IDs in code. IDs live in `settings.json`; matching is saved
  ID first, then case-insensitive name substring among ACTIVE devices only (the dongle
  re-enumerates as "2-", "3-"… on new USB ports, leaving NotPresent ghosts).
- Jerome's hardware truths (from probe 2026-07-26): headset is "HyperX (2- HyperX
  Cloud II Core Wireless)"; the real laptop mic is the Intel "Microphone Array",
  NOT Realtek (that one is Unplugged); ButtKicker is render-only, never a default.
- COM must be initialized per thread — call sites run on pystray/keyboard/poll
  threads. `audio._com_init()` handles it; route new COM code through `audio.py`.
- **Never `ctypes.cast()` a COM interface pointer — use `QueryInterface`.** pycaw's own
  README does `cast(dev.Activate(...), POINTER(IAudioEndpointVolume))`, and that is a
  process-killer here: a cast pointer keeps its source alive in a reference *cycle*, so
  it survives until the cyclic GC runs, and the cyclic GC runs on whatever thread happens
  to trip it — releasing an apartment-bound pointer from the wrong thread is an access
  violation that takes the whole app down (seen 2026-07-28, crashed ~10 s after start).
  `audio.activate(device_id, Interface)` does it correctly; go through it.
  To check for a regression: loop the call and count
  `gc.get_objects()` entries that are `comtypes` `_compointer_base` instances — it must
  stay at 0 without calling `gc.collect()`.
- Enumerating endpoints is the expensive call. When testing several devices at once
  (the watch loop does, every couple of seconds), call `audio.list_devices()` once and
  pass the result to `audio.match_device()` — don't call `find_device()` per device.

## Battery over HID
- Windows battery APIs don't work for 2.4 GHz dongles. `battery.py` writes the vendor
  request `[0x66, 0x89]` padded to 52 bytes to the dongle's vendor HID interface
  (VID 0x03F0, PID 0x0995, highest usage-page interface = 0xFF13); battery % is
  response byte 4; values > 100 mean headset off. Protocol from
  auto94/HyperX-Cloud-2-Battery-Monitor (MIT).
- A different HyperX model needs different request bytes — check that repo's
  MainForm.cpp before "fixing" anything.
- Open the HID device per read and close it — NGENUITY and other tools share it.
- The battery reading doubles as the headset ON/OFF signal for auto-detect: this
  dongle never changes its Windows endpoint state on headset power (verified
  2026-07-26, 120 s watch, zero transitions), but it only answers the battery
  request while the headset is on. Two consecutive misses = off (debounce).
