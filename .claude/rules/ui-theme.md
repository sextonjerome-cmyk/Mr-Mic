# UI theme rules

- The palette lives in `theme.py` and is the single source of truth. (The hex values
  were originally hand-copied from the unrelated CobbAttack app — history, not a
  dependency. Change them here whenever you like.)
  BG `#14181d`, PANEL `#1c2229`, FIELD `#242c35`, TEXT `#d7dde3`, DIM `#7a8794`,
  GREEN `#5dd08c`, AMBER `#e8b33e`, RED `#e06c5b`, BLUE `#5aa7e0`, BORDER `#34455a`.
  Never inline hex colors elsewhere — import from `theme.py`.
- Color meanings: GREEN = headset/good, BLUE = laptop/speakers, AMBER = warning
  (low battery, missing device), RED = error, DIM = inactive/unknown.
- Tray icons are drawn with PIL in `tray.py` (headset glyph = GREEN, speaker = BLUE,
  unknown device = DIM). Keep glyphs chunky — they render at 16 px.
- The future flyout/settings windows: tkinter (stdlib, no extra installs), borderless
  rounded-panel style.
- Any HTML manual/cheatsheet gets the same dark theme and a labeled, organized layout,
  matching `mrmic-guide.html`.
- If you ever want a worked example of this rounded-panel look in tkinter, the
  `RoundButton` / `RoundBox` classes in `../CobbAttack/ui.py` are one. That app is
  unrelated to Mr. Mic — treat it as a code sample to copy from, never as a dependency.
