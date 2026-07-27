# Session log

Running notes on what changed and why. Newest first.

## 2026-07-27 — Renamed the project folder, logged the installer plan

**Renamed `mic switch` → `Mr. Mic`.**

Checked first whether anything depended on the old folder name. Almost nothing did:

- `config.py` derives `APP_DIR` from the exe/script location, so `settings.json`,
  `mrmic.log`, and the chimes follow the folder wherever it goes.
- `run-mrmic.bat` uses `%~dp0` (its own directory), so it needed no change.
- `MrMic.spec` and the git remote (`sextonjerome-cmyk/Mr-Mic`) hold no absolute paths.
- The only real dependency was the **autostart shortcut**
  (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Mr Mic.lnk`), which had the
  old path in its target, working directory, and icon location. All three were updated.

A straight `Rename-Item` failed with "access denied" even after stopping MrMic. The
Windows Restart Manager reported **no file locks**, so it was a directory handle —
most likely VSCode's file watcher or the OneDrive sync engine holding the folder open.
Renaming a scratch folder in the same parent worked fine, which confirmed it was
specific to this directory and not a permissions problem.

Workaround that worked: create `Mr. Mic`, move all 29 entries (including `.git` and
`.claude`) across with `Move-Item`, then delete the empty original. Settings, log
history, and git state all survived. App relaunched clean — hotkey bound, ~55 MB.

Loose end: the leftover `build/` folder still has the old path in its PyInstaller
cache. Harmless, but delete `build/` if a future rebuild misbehaves.

**Added the installer to the Planned list in `CLAUDE.md`** — Jerome wants a real
Windows installer rather than distributing a zip. See that section for the requirements.
