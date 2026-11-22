#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Cache Mozilla candidates using native curl, checking signed APT metadata.

Run on the Linux build host, after apt-get update in ROOT has authenticated the
Mozilla index. This never imports packages from an untrusted mirror or relaxes
TLS verification. Partial downloads stay in the build root for diagnosis.
"""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


def metadata(root, package):
    policy = subprocess.check_output(
        ['chroot', str(root), 'apt-cache', 'policy', package], text=True,
        env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    match = re.search(r'^\s*Candidate:\s*(\S+)', policy, re.M)
    if not match or match[1] == '(none)':
        raise ValueError(f'no candidate for {package}')
    version = match[1]
    text = subprocess.check_output(
        ['chroot', str(root), 'apt-cache', 'show', f'{package}={version}'], text=True)
    for paragraph in text.split('\n\n'):
        fields = dict(line.split(': ', 1) for line in paragraph.splitlines()
                      if ': ' in line and not line.startswith(' '))
        if (fields.get('Package') == package and fields.get('Version') == version
                and fields.get('Filename', '').startswith('pool/mozilla/')
                and re.fullmatch(r'[0-9a-f]{64}', fields.get('SHA256', ''))):
            return fields
    raise ValueError(f'candidate {package} is not a Mozilla indexed package')


def verify(path, fields):
    if not path.is_file() or path.stat().st_size != int(fields['Size']):
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == fields['SHA256']


def cache(root):
    root = Path(root).resolve(strict=True)
    if root == Path('/') or not (root / 'etc/apt/sources.list.d/mozilla.sources').is_file():
        raise ValueError('expected a dedicated build root with configured Mozilla source')
    archives = root / 'var/cache/apt/archives'
    archives.mkdir(parents=True, exist_ok=True)
    for package in ('firefox', 'firefox-l10n-zh-cn'):
        fields = metadata(root, package)
        # APT's cache convention percent-encodes an epoch colon but not a tilde.
        version = fields['Version'].replace(':', '%3a')
        dest = archives / f'{package}_{version}_{fields["Architecture"]}.deb'
        if not verify(dest, fields):
            partial = dest.with_suffix('.deb.partial')
            url = 'https://packages.mozilla.org/apt/' + quote(fields['Filename'], safe='/')
            print(f'Download {package} {fields["Version"]} ({fields["Size"]} bytes)', flush=True)
            subprocess.run(['curl', '--http1.1', '--fail', '--location', '--continue-at', '-',
                            '--connect-timeout', '20', '--max-time', '900',
                            '--retry', '2', '--retry-all-errors', '--retry-delay', '3',
                            '--output', str(partial), url], check=True)
            if not verify(partial, fields):
                raise ValueError(f'size or SHA256 mismatch for {partial}; retained for inspection')
            partial.replace(dest)
        print(f'VERIFIED {fields["SHA256"]} {dest.name}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    cache(args.root)
