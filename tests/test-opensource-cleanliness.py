#!/usr/bin/env python3
"""Open-source repository hygiene audit: ensure no keys, credentials, outside links, CRLF, or bytecode."""
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]

GENERIC_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PEM private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("OpenSSH public key", re.compile(r"\bssh-(?:ed25519|rsa|ecdsa)\s+AAAA[0-9A-Za-z+/=]{20,}")),
    ("GitHub personal token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("parent-directory escape link", re.compile(r"\.\./\.\./docs/")),
)
FORBIDDEN_FILENAMES = {"authorized_keys", "authorized_keys2", "id_rsa", "id_ed25519"}
BINARY_SUFFIXES = {".bin", ".deb", ".zst", ".xz", ".gz"}


class OpenSourceCleanlinessTests(unittest.TestCase):
    def test_no_credentials_outside_links_crlf_or_bytecode(self):
        violations: list[str] = []
        for path in sorted(REPO.rglob("*")):
            rel = path.relative_to(REPO).as_posix()
            if rel == ".git" or rel.startswith(".git/"):
                continue
            if path.name == "__pycache__" or path.suffix == ".pyc":
                violations.append(f"bytecode artifact in repo: {rel}")
                continue
            if path.name in FORBIDDEN_FILENAMES or path.suffix == ".nmconnection":
                violations.append(f"credential or connection profile in repo: {rel}")
                continue
            if not path.is_file() or path.suffix in BINARY_SUFFIXES:
                continue
            raw = path.read_bytes()
            if b"\r" in raw:
                violations.append(f"CRLF line ending in: {rel}")
            if path.resolve() == Path(__file__).resolve():
                continue
            text = raw.decode("utf-8", errors="replace")
            for label, pattern in GENERIC_FORBIDDEN_PATTERNS:
                match = pattern.search(text)
                if match:
                    violations.append(f"{label} found in {rel}")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_required_public_docs_and_kernel_sources_present(self):
        for required in (
            "LICENSE",
            "README.md",
            "INSTALL.md",
            "tools/install-clean-system.sh",
            "tools/build-kernel.sh",
            "tools/build-desktop-rootfs.sh",
            "tools/verify-desktop-rootfs.py",
            "kernel/sm8550-oneplus-salami.dts",
            "kernel/sm8550-oneplus-salami-display-iris7.dtsi",
            "kernel/sm8550-oneplus-salami-thermal.dtsi",
            "kernel/sm8550-oneplus-salami-touch.dtsi",
            "kernel/kernel.config",
            "kernel/device",
        ):
            self.assertTrue((REPO / required).is_file(), f"missing public file: {required}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
