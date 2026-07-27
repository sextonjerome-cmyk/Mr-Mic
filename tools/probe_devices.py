"""Mr. Mic device probe.

  python tools/probe_devices.py            one-shot list of every endpoint + defaults
  python tools/probe_devices.py --watch 60 poll every second, print state changes
                                           (turn the headset off and on while it runs)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audio


def snapshot():
    return {(d["flow"], d["id"]): d for d in audio.list_devices()}


def print_all():
    out_id, _ = audio.get_default(audio.RENDER)
    in_id, _ = audio.get_default(audio.CAPTURE)
    com_out_id, _ = audio.get_default(audio.RENDER, audio.COMMUNICATIONS)
    com_in_id, _ = audio.get_default(audio.CAPTURE, audio.COMMUNICATIONS)
    for flow in (audio.RENDER, audio.CAPTURE):
        print(f"\n=== {audio.FLOW_NAMES[flow].upper()} ===")
        for d in audio.list_devices(flow):
            marks = ""
            if d["id"] == (out_id if flow == audio.RENDER else in_id):
                marks += " [DEFAULT]"
            if d["id"] == (com_out_id if flow == audio.RENDER else com_in_id):
                marks += " [COMMS]"
            print(f"  {d['state_name']:<10} {d['name']}{marks}")
            print(f"             id={d['id']}")


def watch(seconds):
    print(f"Watching for {seconds}s — turn the headset OFF, wait ~5s, then back ON...")
    prev = snapshot()
    end = time.time() + seconds
    changes = 0
    while time.time() < end:
        time.sleep(1)
        now = snapshot()
        for key, d in now.items():
            old = prev.get(key)
            if old is None:
                print(f"  + APPEARED  [{audio.FLOW_NAMES[d['flow']]}] {d['name']} -> {d['state_name']}")
                changes += 1
            elif old["state"] != d["state"]:
                print(f"  ~ {old['state_name']} -> {d['state_name']:<10} [{audio.FLOW_NAMES[d['flow']]}] {d['name']}")
                changes += 1
        for key, d in prev.items():
            if key not in now:
                print(f"  - VANISHED  [{audio.FLOW_NAMES[d['flow']]}] {d['name']}")
                changes += 1
        prev = now
    print(f"\nDone. {changes} state change(s) seen."
          f" {'Auto-detect is FEASIBLE.' if changes else 'No changes — dongle hides headset power state.'}")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        idx = sys.argv.index("--watch")
        secs = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 60
        watch(secs)
    else:
        print_all()
