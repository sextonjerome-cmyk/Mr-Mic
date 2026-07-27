# UI theme rules

- Mr. Mic looks like CobbAttack (`../CobbAttack/ui.py`). Palette lives in
  `theme.py` and is the single source of truth:
  BG `#14181d`, PANEL `#1c2229`, FIELD `#242c35`, TEXT `#d7dde3`, DIM `#7a8794`,
  GREEN `#5dd08c`, AMBER `#e8b33e`, RED `#e06c5b`, BLUE `#5aa7e0`, BORDER `#34455a`.
  Never inline hex colors elsewhere — import from `theme.py`.
- Color meanings: GREEN = headset/good, BLUE = laptop/speakers, AMBER = warning
  (low battery, missing device), RED = error, DIM = inactive/unknown.
- Tray icons are drawn with PIL in `tray.py` (headset glyph = GREEN, speaker = BLUE,
  unknown device = DIM). Keep glyphs chunky — they render at 16 px.
- The future flyout/settings windows: tkinter (stdlib, no extra installs), borderless
  panel style, reuse CobbAttack's RoundButton/panel-canvas patterns
  (the `RoundButton` and `RoundBox` classes in `../CobbAttack/ui.py`) — copy the
  pattern into this repo, don't import across projects.
- Any HTML manual/cheatsheet gets the same dark theme and labeled, organized layout
  as CobbAttack's `Install-Instruction.html` / `commands-cheatsheet.html`.
