# Audio + hardware rules

## Bluetooth
- Disconnecting one paired device beats turning the radio off — the radio takes every
  other paired thing with it (Jerome has four serial-over-Bluetooth COM ports).
  `BluetoothSetServiceState` on the A2DP Audio Sink GUID
  (`0000110B-0000-1000-8000-00805F9B34FB`) does it, **and needs no admin rights**.
- **It disconnects only. It cannot connect an idle device.** Enabling the service on a
  device that is not currently linked returns 87 (ERROR_INVALID_PARAMETER) with a NULL
  radio handle *and* with a real one, and nothing connects — watched 75 s with no
  competing phone (2026-08-02). Connecting must go through Windows
  (`os.startfile("ms-settings:bluetooth")`).
  The trap that hid this: disable-then-enable within a few seconds *does* return
  ERROR_SUCCESS both ways, because the link has not torn down yet. That is not proof
  connect works — test it cold, from genuinely disconnected.
- The hands-free GUID (`...111E...`) also returns 87; don't assume it works.
- **Declare `argtypes`/`restype` on every `bthprops.cpl` call.** `BluetoothFindFirstDevice`
  returns a 64-bit HANDLE; without a declared restype ctypes truncates it to 32 bits and
  the next call is an access violation.
- Bluetooth headphones expose two output endpoints: `Headphones (…)` is A2DP stereo,
  `Headset (…)` is hands-free — mic works, audio turns to mush. Default a device's output
  at the A2DP one. Leaving `input_match` empty means "don't touch the mic", which is the
  right default; Jerome opted into the Hesh mic on 2026-08-01 and found it acceptable.
- "Connected" in Windows is not the same as "audio actually flows". A stale Bluetooth link
  leaves the endpoint Active and default while streams silently render elsewhere (seen
  2026-08-01). To prove where audio really goes, enumerate `IAudioSessionManager2` sessions
  per endpoint and filter to your own PID — the default endpoint reported by Windows lies.

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
- **"No battery reading" has two causes and users need them separated.** A dongle
  that isn't in a USB port and a dongle whose headset is off both return None.
  `battery.status()` returns `(plugged_in, level)` so the tray can say "dongle
  unplugged" instead of "headset off?" — the wrong message cost Jerome an evening on
  2026-07-30, hunting through the app for a bug that was an empty USB port.
