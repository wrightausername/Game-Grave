"""Real Steam trailers on a real Windows PC: what Steam's store answer gives for movies today, and which of those
links Qt's video player (the same one bundled in Game Grave) actually plays.

Checks a few well-known games. For each trailer it tries, in order: the link Game Grave picks (deals_core.parse_media),
Steam's HLS stream, its DASH stream, the short mp4 preview if there is one, and the HLS stream saved to a local folder
first. A link "plays" when the player reports real video and the position moves past one second.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

GAMES = (1245620, 730, 292030, 1091500)  # Elden Ring, Counter-Strike 2, The Witcher 3, Cyberpunk 2077
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GameGrave-check"


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as answer:
        return answer.read()


def save_hls_locally(master_url, folder, segments=6):
    """Saves the lowest video variant (plus audio if separate) of an HLS stream, a few segments, as local playlists."""
    folder.mkdir(parents=True, exist_ok=True)
    master = get(master_url).decode("utf-8", "replace")
    lines = master.splitlines()
    variants, audio = [], None
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            bw = re.search(r"BANDWIDTH=(\d+)", line)
            if i + 1 < len(lines):
                variants.append((int(bw.group(1)) if bw else 0, lines[i + 1].strip()))
        if line.startswith("#EXT-X-MEDIA") and "TYPE=AUDIO" in line and audio is None:
            m = re.search(r'URI="([^"]+)"', line)
            audio = m.group(1) if m else None
    if not variants:
        raise RuntimeError("no variants in master playlist: " + master[:300])
    variants.sort()

    def keep(rel, name):
        url = urllib.parse.urljoin(master_url, rel)
        text = get(url).decode("utf-8", "replace")
        out, count = [], 0
        for line in text.splitlines():
            m = re.search(r'URI="([^"]+)"', line)
            if line.startswith("#EXT-X-MAP") and m:
                local = f"{name}_init.mp4"
                (folder / local).write_bytes(get(urllib.parse.urljoin(url, m.group(1))))
                line = line.replace(m.group(1), local)
            elif line and not line.startswith("#"):
                if count >= segments:
                    continue
                local = f"{name}_{count}" + Path(urllib.parse.urlparse(line).path).suffix
                (folder / local).write_bytes(get(urllib.parse.urljoin(url, line)))
                line, count = local, count + 1
            out.append(line)
        if "#EXT-X-ENDLIST" not in text:
            out.append("#EXT-X-ENDLIST")
        (folder / f"{name}.m3u8").write_text("\n".join(out), encoding="utf-8")
        return f"{name}.m3u8"

    video = keep(variants[0][1], "video")
    new = [line for line in lines if not line.startswith("#EXT-X-STREAM-INF") and line.strip() and line.startswith("#")
           and not line.startswith("#EXT-X-MEDIA")]
    if audio:
        a = keep(audio, "audio")
        new.append(f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="a",DEFAULT=YES,URI="{a}"')
        new.append(f'#EXT-X-STREAM-INF:BANDWIDTH={variants[0][0]},AUDIO="a"')
    else:
        new.append(f"#EXT-X-STREAM-INF:BANDWIDTH={variants[0][0]}")
    new.append(video)
    (folder / "master.m3u8").write_text("\n".join(new), encoding="utf-8")
    return folder / "master.m3u8", folder / video, sorted(p.name for p in folder.iterdir())


def try_play(app, url, seconds=25):
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    view = QVideoWidget()
    view.resize(640, 360)
    view.show()
    player = QMediaPlayer()
    sound = QAudioOutput()
    sound.setVolume(0)
    player.setAudioOutput(sound)
    player.setVideoOutput(view)
    errors = []
    player.errorOccurred.connect(lambda e, text: errors.append(f"{e}: {text}"))
    source = QUrl.fromLocalFile(str(url)) if isinstance(url, Path) else QUrl(url)
    player.setSource(source)
    player.play()
    end = time.time() + seconds
    while time.time() < end and not errors and player.position() < 1500:
        app.processEvents()
        time.sleep(0.05)
    result = {"position_ms": player.position(), "video": player.hasVideo(), "audio": player.hasAudio(),
              "status": str(player.mediaStatus()), "errors": errors[:3]}
    player.stop()
    view.close()
    player.deleteLater()
    view.deleteLater()
    app.processEvents()
    result["plays"] = result["position_ms"] >= 1000 and result["video"] and not errors
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scratch = rw.isolate("gg-trailers-")
    report = rw.Report("trailers_real", args.output)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from PySide6.QtMultimedia import QMediaFormat
    report.note("Qt video formats", decoders=[str(f) for f in QMediaFormat().supportedFileFormats(QMediaFormat.Decode)])
    from gg_desktop import deals_core as dc
    any_game_plays = False
    for app_id in GAMES:
        try:
            data = json.loads(get(dc.media_url(app_id)))
        except Exception as error:  # noqa: BLE001
            report.note(f"{app_id}: store answer failed", error=repr(error))
            continue
        movies = ((data.get(str(app_id)) or {}).get("data") or {}).get("movies") or []
        if not movies:
            report.note(f"{app_id}: no movies")
            continue
        report.note(f"{app_id}: first movie as Steam sends it", movie=movies[0])
        _shots, picked = dc.parse_media(data, app_id)
        first = movies[0]
        tries = []
        if picked:
            tries.append(("Game Grave's pick", picked[0][2]))
        for key in ("hls_h264", "dash_h264", "dash_av1"):
            if isinstance(first.get(key), str):
                tries.append((key, first[key]))
        for key in ("mp4", "webm"):
            if isinstance(first.get(key), dict):
                tries.append((key, first[key].get("max") or first[key].get("480")))
        micro = first.get("microtrailer") or {}
        if isinstance(micro, dict) and micro:
            tries.append(("microtrailer", json.dumps(micro)[:300]))
        for name, url in tries:
            if not isinstance(url, str) or not url.startswith("http"):
                report.note(f"{app_id} {name}: not a link", value=str(url)[:300])
                continue
            result = try_play(app, url)
            report.note(f"{app_id} {name}", url=url, **result)
            any_game_plays = any_game_plays or (name == "Game Grave's pick" and result["plays"])
        if isinstance(first.get("hls_h264"), str):
            try:
                master, video, files = save_hls_locally(first["hls_h264"], scratch / f"hls_{app_id}")
                report.note(f"{app_id} HLS saved locally", files=files[:20])
                report.note(f"{app_id} local master playlist", **try_play(app, master))
                report.note(f"{app_id} local video playlist", **try_play(app, video))
            except Exception as error:  # noqa: BLE001
                report.note(f"{app_id} HLS saved locally failed", error=repr(error))
    report.check("Game Grave's trailer link plays for at least one well-known game", any_game_plays)
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
