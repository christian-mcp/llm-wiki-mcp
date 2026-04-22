"""Desktop and sharing helpers for local wiki workflows."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass
class LaunchResult:
    launched: bool
    method: str
    detail: str = ""


def obsidian_uri_for_path(path: Path) -> str:
    """Build an Obsidian URI that opens the note containing this path."""
    return f"obsidian://open?path={quote(str(path.resolve()))}"


def open_external_url(url: str) -> LaunchResult:
    """Ask the OS to open a URL or custom URI in the default handler."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return LaunchResult(True, "open")

        if sys.platform.startswith("win"):
            subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return LaunchResult(True, "start")

        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen(
                [opener, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return LaunchResult(True, "xdg-open")
        return LaunchResult(False, "xdg-open", "xdg-open not found")
    except OSError as e:
        return LaunchResult(False, "os-open", str(e))


def open_in_obsidian(target_path: Path) -> LaunchResult:
    """Open a wiki note in Obsidian via the registered obsidian:// handler."""
    result = open_external_url(obsidian_uri_for_path(target_path))
    if result.launched:
        return result

    obsidian_bin = shutil.which("obsidian")
    if obsidian_bin:
        try:
            subprocess.Popen(
                [obsidian_bin, str(target_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return LaunchResult(True, "obsidian")
        except OSError as e:
            return LaunchResult(False, "obsidian", str(e))

    return result


def detect_lan_urls(port: int) -> list[str]:
    """Return likely shareable LAN URLs for this machine."""
    ips: set[str] = set()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass

    try:
        hostname = socket.gethostname()
        for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(
            hostname,
            None,
            family=socket.AF_INET,
        ):
            if family != socket.AF_INET:
                continue
            ip = sockaddr[0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass

    return [f"http://{ip}:{port}" for ip in sorted(ips)]
