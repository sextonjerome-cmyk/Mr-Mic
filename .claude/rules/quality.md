# Quality gates

Before calling a change done:
- Toggle both directions and confirm in Windows (or `tools/probe_devices.py`) that
  default output AND input AND both Communications defaults moved.
- `python battery.py` returns a sane percentage with the headset on, `None` with it off.
- App starts clean: `python main.py`, no traceback, tray icon appears, `mrmic.log`
  shows hotkey bound. Kill stray instances first (they hold `mrmic.log`):
  python processes whose command line matches `main.py`.
- Memory budget: < 80 MB in Task Manager. No busy loops — all polling uses
  `Event.wait(seconds)`, never `time.sleep` in a tight loop.
- pystray menu callbacks must take (icon, item) or no args — a bound extra parameter
  crashes the whole menu at startup (learned the hard way).
- Nothing blocking in menu/hotkey callbacks: battery HID reads and anything > ~100 ms
  belong on the poll threads.
- Settings changes must survive "Reload settings" without an app restart.
- User-facing errors: notify simply ("output not found"), log the detail to
  `mrmic.log` — never crash the tray app.
