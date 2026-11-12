"""Latest graphics driver from the card maker, and firmware facts. Network only on the owner's press.

* NVIDIA: NVIDIA's own driver lookup (the service behind nvidia.com/drivers): the card's product IDs from NVIDIA's product
  list, then the newest WHQL Game Ready (DCH) driver for Windows 10/11 64-bit for that card.
* AMD: the version file AMD Software: Adrenalin itself reads to check for updates (drivers.amd.com), over https.
* Intel: Intel publishes no version a program can read, so the tab shows the installed version and links Intel's assistant.

Versions are compared as numbers, NVIDIA's in its own "560.94" form (from Windows' 32.0.15.6094). When a maker's answer
can't be read, the tab says so; it never guesses that a driver is outdated. Nothing is downloaded or installed from here:
the maker's page or app does that.

Firmware: the BIOS/UEFI version and date, the board or PC model, and each drive's firmware revision are read from Windows.
There is no shared list of the newest firmware for every board and drive, so firmware is never called outdated; an old BIOS
date is a hint, and the tab names the maker's own support page or tool. Firmware updates that Windows Update offers appear
in the update list like drivers, marked Firmware.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

VENDOR_HOSTS = ("gfwsl.geforce.com", "www.nvidia.com", "nvidia.com", "drivers.amd.com")
NVIDIA_PRODUCTS = "https://www.nvidia.com/Download/API/lookupValueSearch.aspx?TypeID=3"
NVIDIA_LOOKUP = ("https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php"
                 "?func=DriverManualLookup&psid={psid}&pfid={pfid}&osID=57&languageCode=1033&beta=0&isWHQL=1"
                 "&dltype=-1&dch=1&upCRD=0&qnf=0&sort1=0&numberOfResults=1")
AMD_VERSION = "https://drivers.amd.com/drivers/installer/json/version.json"
PAGES = {"NVIDIA": ("NVIDIA App", "https://www.nvidia.com/en-us/software/nvidia-app/"),
         "AMD": ("AMD Software: Adrenalin", "https://www.amd.com/en/support/download/drivers.html"),
         "Intel": ("Intel Driver & Support Assistant", "https://www.intel.com/content/www/us/en/support/detect.html")}


class VendorError(RuntimeError):
    pass


def maker_of(name: str) -> str:
    low = (name or "").casefold()
    if any(w in low for w in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
        return "NVIDIA"
    if any(w in low for w in ("amd", "radeon", "ati ")):
        return "AMD"
    if any(w in low for w in ("intel", "arc ", "iris", "uhd graphics")):
        return "Intel"
    return ""


# ------------------------------------------------------------------ versions
def nvidia_version(windows_version: str) -> str:
    """Windows' 32.0.15.6094 -> NVIDIA's 560.94 (the last five digits of the last two parts)."""
    parts = str(windows_version or "").split(".")
    if len(parts) < 4 or not all(p.isdigit() for p in parts[-2:]):
        return ""
    digits = (parts[-2] + parts[-1].rjust(4, "0"))[-5:]
    return f"{int(digits[:3])}.{digits[3:]}"


def as_tuple(version: str):
    return tuple(int(x) for x in re.findall(r"\d+", str(version or "")))


def newer(latest: str, installed: str) -> bool | None:
    a, b = as_tuple(latest), as_tuple(installed)
    if not a or not b:
        return None
    return a > b


@dataclass(frozen=True)
class GraphicsCheck:
    card: str
    maker: str
    installed: str          # in the maker's own form when known
    installed_date: str
    latest: str = ""
    latest_date: str = ""
    latest_name: str = ""
    page: str = ""
    note: str = ""

    @property
    def outdated(self):
        return newer(self.latest, self.installed) if self.latest else None

    @property
    def summary(self):
        if self.latest and self.outdated:
            return (f"{self.maker} has a newer driver: {self.latest}" + (f" ({self.latest_date})" if self.latest_date else "")
                    + f". You have {self.installed}.")
        if self.latest and self.outdated is False:
            return f"Up to date: {self.installed} is {self.maker}'s newest driver."
        return self.note or f"Installed: {self.installed or 'unknown'}" + (f" ({self.installed_date})" if self.installed_date else "")


# ------------------------------------------------------------------ network (allowlisted)
def _allowed(url):
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in VENDOR_HOSTS)


def _get(url, opener=None, timeout=20, limit=8_000_000):
    if not _allowed(url):
        raise VendorError("Only NVIDIA's and AMD's own sites are asked.")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 GameGrave", "Accept": "*/*"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            return response.read(limit).decode("utf-8", "replace")
    except OSError as problem:
        raise VendorError(f"couldn't reach {urllib.parse.urlsplit(url).hostname}") from problem


def _clean_name(text):
    return re.sub(r"\s+", " ", re.sub(r"(?i)\b(nvidia|laptop gpu|notebook|graphics|\(tm\)|\(r\))\b", " ", text)).strip().casefold()


def nvidia_ids(card: str, products_xml: str):
    """(psid, pfid) of the NVIDIA product whose name matches the card, notebook versions for 'Laptop GPU' cards."""
    root = ET.fromstring(products_xml)
    want = _clean_name(card)
    laptop = "laptop" in card.casefold() or "notebook" in card.casefold()
    best = None
    for item in root.iter("LookupValue"):
        name = (item.findtext("Name") or "").strip()
        value = (item.findtext("Value") or "").strip()
        parent = item.get("ParentID") or ""
        if not name or not value.isdigit() or not parent.isdigit():
            continue
        is_nb = "notebook" in name.casefold() or "laptop" in name.casefold()
        if _clean_name(name) == want and is_nb == laptop:
            return parent, value
        if _clean_name(name) == want and best is None:
            best = (parent, value)
    if best:
        return best
    raise VendorError(f"NVIDIA's product list has no '{card}'")


def parse_nvidia(text: str):
    data = json.loads(text)
    ids = data.get("IDS") or []
    if not ids:
        raise VendorError("NVIDIA listed no driver for this card")
    info = ids[0].get("downloadInfo") or {}
    version = str(info.get("Version") or "")
    if not as_tuple(version):
        raise VendorError("NVIDIA's answer had no version")
    when = str(info.get("ReleaseDateTime") or "")
    return version, _date(when), urllib.parse.unquote(str(info.get("Name") or "")).replace("+", " ")[:120]


def _date(text):
    for pattern, order in ((r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"), (r"(\d{1,2})/(\d{1,2})/(\d{4})", "mdy")):
        m = re.search(pattern, text)
        if m:
            parts = [int(x) for x in m.groups()]
            y, mo, d = parts if order == "ymd" else (parts[2], parts[0], parts[1])
            try:
                return date(y, mo, d).isoformat()
            except ValueError:
                pass
    m = re.search(r"([A-Z][a-z]{2})[a-z]* (\d{1,2}),? (\d{4})", text)
    if m:
        months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        if m.group(1) in months:
            try:
                return date(int(m.group(3)), months.index(m.group(1)) + 1, int(m.group(2))).isoformat()
            except ValueError:
                pass
    return ""


def parse_amd(text: str):
    """The newest Adrenalin release in AMD's version file: (public version, Windows driver store version or '')."""
    data = json.loads(text)
    found = []

    def walk(node):
        if isinstance(node, dict):
            low = {str(k).casefold(): v for k, v in node.items()}
            public = next((str(low[k]) for k in ("version", "releaseversion", "softwareversion", "displayversion")
                           if isinstance(low.get(k), (str, int, float)) and re.fullmatch(r"\d{2}\.\d{1,2}\.\d{1,2}(\.\d+)?", str(low[k]))), "")
            store = next((str(v) for k, v in low.items() if isinstance(v, str) and re.fullmatch(r"3\d\.0\.\d{5}\.\d{4}", v)), "")
            if public:
                found.append((public, store))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(data)
    if not found:
        raise VendorError("AMD's version file had no release number Game Grave recognises")
    return max(found, key=lambda f: as_tuple(f[0]))


def check_graphics(card: str, windows_version: str, driver_date: str, opener=None) -> GraphicsCheck:
    maker = maker_of(card)
    page = PAGES.get(maker, ("", ""))[1]
    if maker == "NVIDIA":
        installed = nvidia_version(windows_version) or windows_version
        try:
            psid, pfid = nvidia_ids(card, _get(NVIDIA_PRODUCTS, opener))
            version, when, name = parse_nvidia(_get(NVIDIA_LOOKUP.format(psid=psid, pfid=pfid), opener))
            return GraphicsCheck(card, maker, installed, driver_date, version, when, name, page)
        except (VendorError, ValueError, ET.ParseError) as problem:
            return GraphicsCheck(card, maker, installed, driver_date, page=page,
                                 note=f"Couldn't read NVIDIA's newest version ({problem}). You have {installed}.")
    if maker == "AMD":
        try:
            public, store = parse_amd(_get(AMD_VERSION, opener))
        except (VendorError, ValueError) as problem:
            return GraphicsCheck(card, maker, windows_version, driver_date, page=page,
                                 note=f"Couldn't read AMD's newest version ({problem}). You have driver {windows_version}.")
        if store:
            return GraphicsCheck(card, maker, windows_version, driver_date, store, "", f"Adrenalin {public}", page)
        return GraphicsCheck(card, maker, windows_version, driver_date, page=page,
                             note=f"AMD's newest Adrenalin is {public}. You have driver {windows_version}; open AMD Software "
                                  "to compare, since AMD's file doesn't give the matching Windows driver number.")
    if maker == "Intel":
        return GraphicsCheck(card, maker, windows_version, driver_date, page=page,
                             note=f"Intel doesn't publish a version Game Grave can read. You have {windows_version}"
                                  + (f" from {driver_date}" if driver_date else "") + "; Intel's assistant checks for newer.")
    return GraphicsCheck(card, maker or "Unknown", windows_version, driver_date,
                         note="Game Grave doesn't know this card's maker, so it can't look up a newer driver.")


# ------------------------------------------------------------------ firmware
FIRMWARE_SCRIPT = (
    "$b = Get-CimInstance Win32_BIOS | Select-Object -First 1; $m = Get-CimInstance Win32_BaseBoard | Select-Object -First 1; "
    "$c = Get-CimInstance Win32_ComputerSystem | Select-Object -First 1; "
    "$d = @(Get-CimInstance Win32_DiskDrive | ForEach-Object { [pscustomobject]@{ Model = $_.Model; Firmware = $_.FirmwareRevision; "
    "Interface = $_.InterfaceType; Size = [int64]$_.Size } }); "
    "[pscustomobject]@{ BiosVersion = $b.SMBIOSBIOSVersion; BiosMaker = $b.Manufacturer; "
    "BiosDate = $(if ($b.ReleaseDate) { $b.ReleaseDate.ToString('yyyy-MM-dd') } else { '' }); "
    "BoardMaker = $m.Manufacturer; Board = $m.Product; PcMaker = $c.Manufacturer; PcModel = $c.Model; Drives = $d } "
    "| ConvertTo-Json -Compress -Depth 4")

BOARD_PAGES = (("asus", "ASUS support", "https://www.asus.com/support/"), ("asustek", "ASUS support", "https://www.asus.com/support/"),
               ("micro-star", "MSI support", "https://www.msi.com/support"), ("msi", "MSI support", "https://www.msi.com/support"),
               ("gigabyte", "GIGABYTE support", "https://www.gigabyte.com/Support"),
               ("asrock", "ASRock support", "https://www.asrock.com/support/index.asp"),
               ("dell", "Dell support", "https://www.dell.com/support/home"), ("alienware", "Dell support", "https://www.dell.com/support/home"),
               ("hp", "HP support", "https://support.hp.com/drivers"), ("hewlett", "HP support", "https://support.hp.com/drivers"),
               ("lenovo", "Lenovo support", "https://pcsupport.lenovo.com/"), ("acer", "Acer support", "https://www.acer.com/support"),
               ("razer", "Razer support", "https://mysupport.razer.com/"), ("microsoft", "Surface updates", "https://support.microsoft.com/surface"))
DRIVE_TOOLS = (("samsung", "Samsung Magician"), ("wd", "WD Dashboard"), ("western digital", "WD Dashboard"),
               ("sandisk", "WD Dashboard"), ("crucial", "Crucial Storage Executive"), ("ct", "Crucial Storage Executive"),
               ("kingston", "Kingston SSD Manager"), ("seagate", "SeaTools"), ("sk hynix", "SK hynix Drive Manager"),
               ("hfs", "SK hynix Drive Manager"), ("solidigm", "Solidigm Storage Tool"), ("intel", "Solidigm Storage Tool"),
               ("corsair", "Corsair iCUE"), ("sabrent", "Sabrent Rocket Control Panel"), ("adata", "ADATA SSD ToolBox"),
               ("teamgroup", "T-Force SSD Toolbox"), ("toshiba", "SSD Utility"), ("kioxia", "SSD Utility"), ("micron", "Micron Storage Executive"))
OLD_BIOS_YEARS = 2


@dataclass(frozen=True)
class FirmwareFacts:
    bios_version: str
    bios_date: str
    board_maker: str
    board: str
    pc_maker: str
    pc_model: str
    drives: tuple   # (model, firmware revision, maker tool or "")

    @property
    def support(self):
        for maker in (self.pc_maker, self.board_maker):
            low = (maker or "").casefold()
            for key, name, url in BOARD_PAGES:
                if re.search(rf"\b{re.escape(key)}", low):
                    return name, url
        return "", ""

    @property
    def model(self):
        generic = ("system product name", "to be filled", "default string", "")
        pc = (self.pc_model or "").strip()
        if pc.casefold() not in generic and (self.pc_maker or "").casefold() not in generic:
            return f"{self.pc_maker} {pc}".strip()
        return f"{self.board_maker} {self.board}".strip()

    def bios_age(self, today=None):
        try:
            then = date.fromisoformat(self.bios_date)
        except ValueError:
            return None
        return ((today or date.today()) - then).days / 365.25


def drive_tool(model: str) -> str:
    low = (model or "").casefold()
    for key, tool in DRIVE_TOOLS:
        if re.search(rf"\b{re.escape(key)}", low):
            return tool
    return ""


def parse_firmware(text) -> FirmwareFacts:
    data = json.loads(text or "{}")
    if isinstance(data, list):
        data = data[0] if data else {}
    drives = data.get("Drives") or []
    if isinstance(drives, dict):
        drives = [drives]
    rows = tuple((str(d.get("Model") or "Drive").strip()[:80], str(d.get("Firmware") or "").strip()[:30],
                  drive_tool(str(d.get("Model") or ""))) for d in drives if isinstance(d, dict))
    return FirmwareFacts(str(data.get("BiosVersion") or "").strip()[:60], str(data.get("BiosDate") or "")[:10],
                         str(data.get("BoardMaker") or "").strip()[:60], str(data.get("Board") or "").strip()[:60],
                         str(data.get("PcMaker") or "").strip()[:60], str(data.get("PcModel") or "").strip()[:60], rows)
