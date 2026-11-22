#!/usr/bin/env python3
"""Observe ADB/Fastboot enumeration after a RAM probe; never change the device."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--serial', required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--seconds', type=int, default=60)
args = parser.parse_args()
if args.seconds <= 0:
    parser.error('--seconds must be positive')
deadline = time.monotonic() + args.seconds
events = []
previous = None
while time.monotonic() < deadline:
    states = {}
    for tool in ('adb', 'fastboot'):
        text = subprocess.check_output([tool, 'devices'], text=True, timeout=5)
        states[tool + '_present'] = any(
            line.split()[0] == args.serial for line in text.splitlines() if line.strip()
        )
    if states != previous:
        event = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), **states}
        events.append(event)
        args.output.write_text(json.dumps(events, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(event), flush=True)
        previous = states
    if states['adb_present']:
        print('ADB_OBSERVED; target kernel still requires a separate query', flush=True)
        raise SystemExit(0)
    time.sleep(min(2, max(0, deadline - time.monotonic())))
print('TIMEOUT: no ADB return observed', flush=True)
raise SystemExit(2)
