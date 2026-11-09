"""Exhume: remember which graphics drivers you played on and bring back the last good one. No Qt in this module.

Honesty rules:
* Game Grave never downloads, installs or removes a driver. It reads the driver Windows reports, keeps a small local
  history, opens Device Manager (whose Roll Back Driver is Windows' own way back) and opens the vendor's official
  driver page. Nothing else.
* "Known good" is only ever set by the owner pressing the button. Game Grave does not guess that a driver works.
* The history file holds adapter names, versions and dates. Nothing leaves this PC.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path

DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
HISTORY_NAME = "driver-history.json"
HISTORY_LIMIT = 60

VENDOR_PAGES = {
    "nvidia": ("NVIDIA", "https://www.nvidia.com/en-us/drivers/"),
    "amd": ("AMD", "https://www.amd.com/en/support/download/drivers.html"),
    "intel": ("Intel", "https://www.intel.com/content/www/us/en/support/detect.html"),
}


@dataclass(frozen=True)
class Driver:
    adapter: str
    version: str
    date: str
    provider: str

    @property
    def vendor(self):
        text = (self.adapter + " " + self.provider).casefold()
        if "nvidia" in text:
            return "nvidia"
        if "amd" in text or "radeon" in text or "advanced micro devices" in text:
            return "amd"
        if "intel" in text:
            return "intel"
        return ""

    @property
    def friendly_version(self):
        """NVIDIA's own number (for example 560.94) from the Windows version 32.0.15.6094. Others stay as Windows says."""
        if self.vendor == "nvidia":
            digits = "".join(part for part in self.version.split(".")[2:] if part.isdigit())
            if len(digits) >= 5:
                tail = digits[-5:]
                return f"{int(tail[:3])}.{tail[3:]}"
        return self.version

    def label(self):
        friendly = self.friendly_version
        extra = f" (Windows version {self.version})" if friendly != self.version else ""
        return f"{self.adapter}: driver {friendly}{extra}"


def read_drivers(reg):
    """Display adapters Windows lists, from the registry. Returns [] when the registry is not available."""
    if reg is None:
        return []
    found = []
    for index in range(10):
        path = DISPLAY_CLASS + "\\" + f"{index:04d}"
        desc = reg.read("HKLM", path, "DriverDesc")
        version = reg.read("HKLM", path, "DriverVersion")
        if not desc or not version:
            continue
        date = reg.read("HKLM", path, "DriverDate")
        provider = reg.read("HKLM", path, "ProviderName")
        name = str(desc[0]).strip()
        if "microsoft basic" in name.casefold() or "remote display" in name.casefold():
            continue
        found.append(Driver(name, str(version[0]).strip(), str(date[0]).strip() if date else "",
                            str(provider[0]).strip() if provider else ""))
    unique = {}
    for driver in found:
        unique.setdefault((driver.adapter, driver.version), driver)
    return list(unique.values())


@dataclass
class Entry:
    adapter: str
    version: str
    date: str
    provider: str
    first_seen: str
    last_seen: str
    known_good: bool = False

    def driver(self):
        return Driver(self.adapter, self.version, self.date, self.provider)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_history(path):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = []
    for item in raw if isinstance(raw, list) else []:
        try:
            entries.append(Entry(str(item["adapter"]), str(item["version"]), str(item.get("date", "")),
                                 str(item.get("provider", "")), str(item.get("first_seen", "")),
                                 str(item.get("last_seen", "")), bool(item.get("known_good", False))))
        except (KeyError, TypeError):
            continue
    return entries[-HISTORY_LIMIT:]


def save_history(path, entries):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps([asdict(e) for e in entries[-HISTORY_LIMIT:]], indent=1), encoding="utf-8")
    temp.replace(path)


def record(entries, drivers, *, now=None):
    """Add drivers not seen before and refresh last_seen for current ones. Returns the new list."""
    stamp = now or _now()
    result = list(entries)
    for driver in drivers:
        match = next((e for e in result if e.adapter == driver.adapter and e.version == driver.version), None)
        if match:
            match.last_seen = stamp
        else:
            result.append(Entry(driver.adapter, driver.version, driver.date, driver.provider, stamp, stamp))
    return result[-HISTORY_LIMIT:]


def mark_known_good(entries, driver, good=True):
    for entry in entries:
        if entry.adapter == driver.adapter and entry.version == driver.version:
            entry.known_good = good
            return True
    return False


def last_known_good(entries, adapter, *, excluding=""):
    candidates = [e for e in entries if e.adapter == adapter and e.known_good and e.version != excluding]
    return candidates[-1] if candidates else None


def previous(entries, adapter, current_version):
    """The driver this adapter had before the current one, if Game Grave saw it."""
    older = [e for e in entries if e.adapter == adapter and e.version != current_version]
    return older[-1] if older else None


def advice(entries, driver):
    """Plain words for one adapter: what it runs now, what came before and what to do to go back."""
    lines = [driver.label()]
    current = next((e for e in entries if e.adapter == driver.adapter and e.version == driver.version), None)
    if current and current.known_good:
        lines.append("You marked this driver as known good.")
    good = last_known_good(entries, driver.adapter, excluding=driver.version)
    before = previous(entries, driver.adapter, driver.version)
    if good:
        lines.append(f"Last known good: {good.driver().friendly_version}, marked by you (seen {good.last_seen}).")
    elif before:
        lines.append(f"Before this you had {before.driver().friendly_version} (seen {before.last_seen}). "
                     "You did not mark it known good.")
    else:
        lines.append("Game Grave has not seen another driver for this card yet, so there is nothing to go back to here.")
    if good or before:
        lines.append("To go back: Device Manager > Display adapters > this card > Properties > Driver > Roll Back "
                     "Driver. If that button is greyed out, download that version from the official page.")
    return lines


def vendor_page(driver):
    return VENDOR_PAGES.get(driver.vendor)
