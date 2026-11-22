#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline restoration plan for an existing Ubuntu root. Never installs or downloads.

APT_ROOT supplies already authenticated cached repository indexes. TARGET_ROOT
supplies the actual installed dpkg state. Output records the simulated changes,
with explicit boot-stack hazards for human review before any apply step.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('apt_root', type=Path)
    p.add_argument('target_root', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    apt_root = args.apt_root.resolve(strict=True)
    target = args.target_root.resolve(strict=True)
    if apt_root == Path('/') or target == Path('/'):
        p.error('use isolated Linux filesystem roots, never the host root')
    if args.output.exists():
        p.error('output must be new; existing evidence is preserved')
    args.output.mkdir(parents=True)
    # Use a private status file inside the APT chroot, with a unique name; do not
    # alter either installed dpkg database or configured repository settings.
    import tempfile
    with tempfile.NamedTemporaryFile(dir=apt_root/'tmp', prefix='restore-status-', delete=False) as f:
        status = Path(f.name)
        f.write((target/'var/lib/dpkg/status').read_bytes())
    try:
        here = Path(__file__).resolve().parents[1]
        packages = [line.strip() for line in (here/'rootfs/desktop/original-ubuntu-restore.txt').read_text().splitlines()
                    if line.strip() and not line.startswith('#')]
        cmd = ['chroot', str(apt_root), 'apt-get', '-s', '--no-install-recommends',
               '-o', f'Dir::State::status=/{status.relative_to(apt_root)}', 'install', *packages]
        result = subprocess.run(cmd, capture_output=True, text=True)
        (args.output/'apt-simulation.txt').write_text(result.stdout+result.stderr)
        result.check_returncode()
        added = re.findall(r'^Inst (\S+)', result.stdout, re.M)
        removed = re.findall(r'^Remv (\S+)', result.stdout, re.M)
        hazards = [name for name in added if name.startswith(('linux-image-', 'linux-generic', 'flash-kernel', 'dracut', 'kdump', 'kexec'))]
        report = {'mode':'offline-simulation-only', 'target_status_sha256':hashlib.sha256((target/'var/lib/dpkg/status').read_bytes()).hexdigest(),
                  'requested':packages, 'install':added, 'remove':removed, 'boot_stack_review_required':hazards,
                  'boundary':'Ubuntu session recovery subset, not proof of full historical system equivalence'}
        (args.output/'plan.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        # This exact resolved temporary path was created by this process above.
        status.unlink()

if __name__ == '__main__':
    main()
