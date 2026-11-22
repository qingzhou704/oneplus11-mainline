#!/usr/bin/env python3
"""Read-only HTTP evidence collection for the OnePlus 11 RAM probe."""

import argparse
import time
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import URLError
from urllib.request import (
    HTTPDefaultErrorHandler, HTTPErrorProcessor, HTTPHandler,
    OpenerDirector, ProxyHandler,
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--expected-build", required=True)
parser.add_argument("--seconds", type=int, default=210)
args = parser.parse_args()
if args.seconds <= 0 or not args.expected_build:
    parser.error("--seconds must be positive; --expected-build must not be empty")
args.output.mkdir(parents=True, exist_ok=True)

# Disable environment/Windows proxies and omit redirect handling: local GETs only.
opener = OpenerDirector()
for handler in (ProxyHandler({}), HTTPHandler(),
                HTTPDefaultErrorHandler(), HTTPErrorProcessor()):
    opener.add_handler(handler)
base_url = "http://192.168.77.2:8080/"
names = ("build-id.txt", "uname.txt", "compatible.txt", "dmesg.txt", "init.log")
expected_build = args.expected_build.encode("utf-8")
deadline = time.monotonic() + args.seconds
last_state = None
last_error = "HTTP not yet observed"

while time.monotonic() < deadline:
    # Each attempt must establish all identities afresh; never trust old files.
    evidence = {}
    for name in names:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            with opener.open(base_url + name, timeout=min(1.0, remaining)) as response:
                body = response.read()
        except (URLError, TimeoutError, ConnectionError, IncompleteRead) as exc:
            last_error = f"{name}: {exc}"
            state = f"WAIT_HTTP {last_error}"
            if state != last_state:
                print(state, flush=True)
                last_state = state
            break

        # Keep the original bytes, including failed identity evidence.
        (args.output / name).write_bytes(body)
        evidence[name] = body
        if name == "build-id.txt":
            matches = body.rstrip(b"\r\n") == expected_build
        elif name == "uname.txt":
            matches = b"salami-ramprobe" in body
        elif name == "compatible.txt":
            matches = b"oneplus,salami" in body
        else:
            matches = True
        if not matches:
            print(f"IDENTITY_MISMATCH {name}; evidence={args.output / name}", flush=True)
            raise SystemExit(1)

    if len(evidence) == len(names):
        print(f"LINUX_OBSERVED build={args.expected_build}; evidence={args.output}",
              flush=True)
        raise SystemExit(0)
    remaining = deadline - time.monotonic()
    if remaining > 0:
        time.sleep(min(1.0, remaining))

print(f"TIMEOUT after {args.seconds}s; last_error={last_error}", flush=True)
raise SystemExit(2)
