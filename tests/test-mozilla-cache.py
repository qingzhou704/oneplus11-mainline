#!/usr/bin/env python3
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('cache', Path(__file__).resolve().parents[1] / 'tools/cache-mozilla-debs.py')
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


class CacheTests(unittest.TestCase):
    def test_hash_and_size(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'test.deb'
            path.write_bytes(b'good')
            fields = {'Size': '4', 'SHA256': hashlib.sha256(b'good').hexdigest()}
            self.assertTrue(cache.verify(path, fields))
            path.write_bytes(b'evil')
            self.assertFalse(cache.verify(path, fields))
            path.write_bytes(b'go')
            self.assertFalse(cache.verify(path, fields))

    def test_reject_non_mozilla_candidate(self):
        outputs = ['Candidate: 1snap\n', 'Package: firefox\nVersion: 1snap\nFilename: pool/main/f/firefox.deb\n']
        with patch.object(cache.subprocess, 'check_output', side_effect=outputs):
            with self.assertRaises(ValueError):
                cache.metadata(Path('/build'), 'firefox')

    def test_existing_verified_archive_avoids_network(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            conf = root / 'etc/apt/sources.list.d/mozilla.sources'
            conf.parent.mkdir(parents=True)
            conf.touch()
            archive = root / 'var/cache/apt/archives'
            archive.mkdir(parents=True)
            fields = {'Version': '1.0', 'Architecture': 'arm64', 'Size': '4',
                      'SHA256': hashlib.sha256(b'good').hexdigest()}
            for p in ('firefox', 'firefox-l10n-zh-cn'):
                (archive / f'{p}_1.0_arm64.deb').write_bytes(b'good')
            with patch.object(cache, 'metadata', return_value=fields), patch.object(cache.subprocess, 'run') as run:
                cache.cache(root)
                run.assert_not_called()

    def test_bad_download_not_promoted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            conf = root / 'etc/apt/sources.list.d/mozilla.sources'
            conf.parent.mkdir(parents=True)
            conf.touch()
            fields = {'Version': '1.0', 'Architecture': 'arm64', 'Size': '4',
                      'Filename': 'pool/mozilla/firefox.deb', 'SHA256': hashlib.sha256(b'good').hexdigest()}
            def download(args, **kwargs):
                Path(args[args.index('--output') + 1]).write_bytes(b'evil')
            with patch.object(cache, 'metadata', return_value=fields), patch.object(cache.subprocess, 'run', side_effect=download):
                with self.assertRaises(ValueError):
                    cache.cache(root)
            self.assertFalse((root / 'var/cache/apt/archives/firefox_1.0_arm64.deb').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
