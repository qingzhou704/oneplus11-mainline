#!/usr/bin/env python3
"""Read-only, host-side checks for an unpacked desktop rootfs.

No target code is executed. dpkg transaction state is checked here; the builder
must additionally run dpkg --audit and apt-get check inside its controlled chroot
for dependency validation. This is not a proof of first-boot hardware operation.
"""
from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path
import re
import sys

PACKAGES_FILE = Path(__file__).resolve().parents[1] / "rootfs/desktop/packages.txt"
EXTRA_PACKAGES = {"firefox", "firefox-l10n-zh-cn", "salami-device", "rmtfs"}
DESKTOP_ENTRIES = {
    "Firefox": ("firefox", "org.mozilla.firefox"),
    "file manager": ("org.gnome.Nautilus",),
    "terminal": ("org.gnome.Console", "org.gnome.Ptyxis", "org.gnome.Terminal", "gnome-terminal"),
    "settings": ("gnome-control-center", "org.gnome.Settings"),
    "text editor": ("org.gnome.TextEditor", "org.gnome.gedit"),
    "PDF reader": ("org.gnome.Papers", "org.gnome.Evince", "evince"),
    "image viewer": ("org.gnome.Loupe", "org.gnome.eog", "eog"),
    "media player": ("org.gnome.Showtime", "org.gnome.Totem", "totem"),
}


class Root:
    """Resolve Linux absolute symlinks against the image, never the host root."""

    def __init__(self, path: Path):
        self.path = path

    def get(self, name: str) -> Path:
        parts = name.split("/")
        resolved: list[str] = []
        links = 0
        while parts:
            part = parts.pop(0)
            if part in ("", "."):
                continue
            if part == "..":
                if resolved:
                    resolved.pop()
                continue
            candidate = self.path.joinpath(*resolved, part)
            if candidate.is_symlink():
                links += 1
                if links > 40:
                    raise OSError(f"symlink loop: {name}")
                target = os.readlink(candidate)
                if target.startswith("/"):
                    resolved = []
                parts = target.split("/") + parts
            else:
                resolved.append(part)
        return self.path.joinpath(*resolved)

    def text(self, name: str) -> str:
        return self.get(name).read_text(encoding="utf-8")


def _records(text: str) -> list[dict[str, str]]:
    records = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        record: dict[str, str] = {}
        for line in paragraph.splitlines():
            if line[:1].isspace():
                continue
            key, separator, value = line.partition(":")
            if not separator or key in record:
                raise ValueError("malformed or duplicate dpkg field")
            record[key] = value.strip()
        if record:
            records.append(record)
    return records


def verify(root: Path) -> list[str]:
    """Return policy errors, including unreadable or malformed filesystem errors."""
    try:
        return _verify(root)
    except (OSError, UnicodeError, ValueError) as exc:
        return [f"cannot inspect rootfs: {exc}"]


def _verify(root: Path) -> list[str]:
    errors: list[str] = []
    root = Path(root).absolute()
    if not root.is_dir():
        return [f"root is not a directory: {root}"]
    fs = Root(root)

    def read(name: str, required: bool = True) -> str:
        try:
            return fs.text(name)
        except (OSError, UnicodeError) as exc:
            if required or not isinstance(exc, FileNotFoundError):
                errors.append(f"cannot read {name}: {exc}")
            return ""

    try:
        required = {line.split("#", 1)[0].strip() for line in PACKAGES_FILE.read_text(encoding="utf-8").splitlines()}
        required.discard("")
        if not required or any(not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?", p) for p in required):
            raise ValueError("empty or malformed package list")
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"cannot read package manifest: {exc}")
        required = set()
    required |= EXTRA_PACKAGES
    installed: dict[str, dict[str, str]] = {}
    try:
        for record in _records(read("var/lib/dpkg/status")):
            package = record.get("Package", "")
            status = record.get("Status", "").split()
            if not package or len(status) != 3:
                errors.append(f"malformed dpkg status record: {package or '<unnamed>'}")
                continue
            if status[1:] == ["ok", "installed"]:
                if not record.get("Version"):
                    errors.append(f"dpkg package has no version: {package}")
                installed[package] = record
            elif status[1:] not in (["ok", "config-files"], ["ok", "not-installed"]):
                errors.append(f"dpkg incomplete state: {package}: {' '.join(status)}")
    except ValueError as exc:
        errors.append(f"invalid dpkg status: {exc}")
    for package in sorted(required):
        if package.split(":", 1)[0] not in installed:
            errors.append(f"required package not installed: {package}")
    if not any(p.startswith("linux-image-") for p in installed):
        errors.append("missing installed linux-image package")
    if "snapd" in installed:
        errors.append("forbidden installed package: snapd")
    if "snap" in installed.get("firefox", {}).get("Version", "").lower():
        errors.append("Firefox is an Ubuntu snap transitional package")

    updates = fs.get("var/lib/dpkg/updates")
    if updates.is_dir() and any(p.name.isdigit() for p in updates.iterdir()):
        errors.append("dpkg has pending updates/transactions")
    if read("var/lib/dpkg/triggers/Unincorp", required=False).strip():
        errors.append("dpkg has unincorporated triggers")

    passwd = read("etc/passwd")
    if not passwd.strip():
        errors.append("etc/passwd has no accounts")
    for line in passwd.splitlines():
        fields = line.split(":")
        if len(fields) != 7 or not fields[2].isdigit():
            errors.append("malformed etc/passwd entry")
            continue
        name, password = fields[:2]
        if 1000 <= int(fields[2]) <= 59999:
            errors.append(f"ordinary user present: {name} (UID {fields[2]})")
        if password not in ("x", "!", "*", "!!"):
            errors.append(f"usable password in passwd: {name}")
    shadow = read("etc/shadow")
    if not shadow.strip():
        errors.append("etc/shadow has no locked accounts")
    for line in shadow.splitlines():
        fields = line.split(":")
        if len(fields) != 9:
            errors.append("malformed etc/shadow entry")
        elif not fields[1].startswith(("!", "*")):
            errors.append(f"usable password in shadow: {fields[0]}")

    sudo = [fs.get("etc/sudoers")]
    sudo_dir = fs.get("etc/sudoers.d")
    if sudo_dir.is_dir():
        sudo.extend(sudo_dir.iterdir())
    for path in sudo:
        if path.is_file() or path.is_symlink():
            text = read(str(path.relative_to(root)))
            # A leading #UID is a sudoers user specification, not a comment.
            active = "\n".join(line for line in text.splitlines()
                               if not re.match(r"\s*#(?![0-9])", line))
            if re.search(r"\bNOPASSWD\s*:", active):
                allowed = (path.relative_to(root).as_posix() == "etc/sudoers.d/50-salami-passwordless"
                           and active.strip() == "%salami-passwordless ALL=(ALL:ALL) NOPASSWD: ALL"
                           and "salami-desktop-passwordless" in installed)
                if allowed:
                    groups = [line.split(":") for line in read("etc/group").splitlines()]
                    selected = [g for g in groups if g[0] == "salami-passwordless"]
                    allowed = (len(selected) == 1 and len(selected[0]) == 4
                               and selected[0][2].isdigit() and selected[0][3] == "")
                    if allowed:
                        gid = selected[0][2]
                        allowed = not any(len(f := line.split(":")) == 7 and f[3] == gid
                                          for line in passwd.splitlines())
                if not allowed:
                    errors.append(f"NOPASSWD sudo policy: {path.relative_to(root)}")

    # Walk without following directory symlinks; read file links through Root.
    # Searching all names also catches keys stashed outside conventional homes.
    def walk_error(exc: OSError) -> None:
        errors.append(f"cannot inspect rootfs: {exc}")

    remote = re.compile(r"^(?:ssh(?:d)?(?:@.*)?|xrdp(?:-sesman)?|gnome-remote-desktop(?:-headless)?|salami-debug-shell)(?:\.(?:service|socket))$")
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if name in ("authorized_keys", "authorized_keys2") or (name.startswith("ssh_host_") and name.endswith("_key")):
                errors.append(f"private SSH material: {relative}")
            if path.is_symlink() and any(p.endswith((".wants", ".requires", ".upholds")) for p in path.parts):
                target_name = Path(os.readlink(path)).name
                if remote.match(name) or remote.match(target_name):
                    if os.readlink(path) != "/dev/null":
                        errors.append(f"remote/debug unit enabled: {relative}")

    for directory in ("home", "etc/NetworkManager/system-connections", "run/NetworkManager/system-connections", "var/lib/NetworkManager/system-connections", "var/lib/iwd"):
        path = fs.get(directory)
        if path.is_dir() and any(path.iterdir()):
            errors.append(f"private home or Wi-Fi data present: {directory}")
    wpa_dir = fs.get("etc/wpa_supplicant")
    if wpa_dir.is_dir():
        for path in wpa_dir.glob("*.conf"):
            if read(path.relative_to(root).as_posix()).strip():
                errors.append(f"private Wi-Fi configuration: {path.relative_to(root)}")

    if read("etc/machine-id"):
        errors.append("etc/machine-id must be empty")
    if read("var/lib/dbus/machine-id", required=False):
        errors.append("var/lib/dbus/machine-id must be absent or empty")
    try:
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(read("etc/gdm3/custom.conf"))
        if not config.getboolean("daemon", "InitialSetupEnable", fallback=False):
            errors.append("GDM InitialSetupEnable=true is required in [daemon]")
        for key in ("AutomaticLoginEnable", "TimedLoginEnable"):
            if config.getboolean("daemon", key, fallback=False):
                errors.append(f"GDM {key} must not be enabled")
    except (configparser.Error, ValueError) as exc:
        errors.append(f"invalid GDM configuration: {exc}")
    default = root / "etc/systemd/system/default.target"
    if not default.is_symlink() or fs.get("etc/systemd/system/default.target").name != "graphical.target" or not fs.get("etc/systemd/system/default.target").is_file():
        errors.append("default.target must link to an existing graphical.target")

    images = sorted(fs.get("boot").glob("boot.img-*"))
    modules = fs.get("usr/lib/modules")
    if not modules.is_dir():
        modules = fs.get("lib/modules")
    releases = sorted(p.name for p in modules.iterdir() if p.is_dir()) if modules.is_dir() else []
    if len(images) != 1 or not images[0].is_file():
        errors.append("exactly one boot/boot.img-* is required")
    elif releases != [images[0].name.removeprefix("boot.img-")]:
        errors.append(f"modules release {releases} does not match {images[0].name}")
    if not releases:
        errors.append("missing kernel modules release directory")

    for name in ("ucm.conf", "lib/card-init.conf", "lib/ctl-remap.conf"):
        if not fs.get(f"usr/share/alsa/ucm2/{name}").is_file():
            errors.append(f"missing board UCM dependency: {name}")

    for label, names in DESKTOP_ENTRIES.items():
        if not any(fs.get(f"usr/share/applications/{name}.desktop").is_file() for name in names):
            errors.append(f"missing desktop entry: {label}")
    for label, paths in {
        "Firefox binary": ("usr/bin/firefox", "usr/lib/firefox/firefox"),
        "GNOME Initial Setup binary": ("usr/libexec/gnome-initial-setup", "usr/lib/gnome-initial-setup/gnome-initial-setup"),
    }.items():
        if not any(fs.get(path).is_file() for path in paths):
            errors.append(f"missing {label}")
    if fs.get("usr/sbin/policy-rc.d").exists():
        errors.append("build-only usr/sbin/policy-rc.d remains")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="unpacked rootfs directory")
    args = parser.parse_args()
    try:
        errors = verify(args.root)
    except (OSError, UnicodeError, ValueError) as exc:
        errors = [f"cannot inspect rootfs: {exc}"]
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("Desktop rootfs offline checks passed (hardware first boot not verified).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
