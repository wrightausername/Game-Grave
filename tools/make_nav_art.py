"""Generate the subtle abstract gaming backdrop at the bottom of the sidebar. Run: python3 tools/make_nav_art.py
Needs rsvg-convert. Deterministic. Writes a transparent 1184x960 PNG (gg_desktop/assets/brand/nav_backdrop.png).
The top third is fully transparent, so the picture fades into the sidebar and never touches the menu buttons."""
from pathlib import Path
import random
import subprocess

W, H = 1184, 960
OUT = Path(__file__).resolve().parents[1] / "gg_desktop" / "assets" / "brand" / "nav_backdrop.png"
PAD = ("M120 0 H400 Q470 0 500 90 L540 230 Q560 300 500 300 Q450 300 420 240 L390 190 H130 L100 240 "
       "Q70 300 20 300 Q-40 300 -20 230 L20 90 Q50 0 120 0Z")


def build():
    r = random.Random(3)
    traces = []
    for i in range(14):
        y = 380 + i * 40 + r.uniform(-8, 8)
        x = r.uniform(-40, 200)
        pts = [(x, y)]
        for _ in range(r.randint(2, 4)):
            x += r.uniform(90, 260)
            pts.append((x, pts[-1][1]))
            y = pts[-1][1] + r.choice((-1, 1)) * r.uniform(30, 80)
            pts.append((x + r.uniform(30, 70), y))
            x = pts[-1][0]
        d = "M" + " L".join(f"{px:.0f} {py:.0f}" for px, py in pts)
        tone = "#13bcf5" if i % 5 == 0 else "#ff2a4d"
        traces.append(f'<path d="{d}" fill="none" stroke="{tone}" stroke-width="3" opacity=".5"/>'
                      f'<circle cx="{pts[-1][0]:.0f}" cy="{pts[-1][1]:.0f}" r="7" fill="{tone}" opacity=".8"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
 <linearGradient id="up" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".34" stop-color="#fff" stop-opacity="0"/><stop offset=".78" stop-color="#fff" stop-opacity=".8"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>
 <linearGradient id="side" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="1"/><stop offset="1" stop-color="#fff" stop-opacity=".35"/></linearGradient>
 <mask id="fade" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="url(#up)"/></mask>
 <mask id="fadeside" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="url(#side)"/></mask>
 <radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ff2a4d" stop-opacity=".30"/><stop offset=".6" stop-color="#b3112b" stop-opacity=".09"/><stop offset="1" stop-color="#b3112b" stop-opacity="0"/></radialGradient>
 <pattern id="hex" width="104" height="180" patternUnits="userSpaceOnUse">
  <path d="M52 0 L104 30 V90 L52 120 L0 90 V30 Z M52 120 V180 M0 90 L-52 120 M104 90 L156 120" fill="none" stroke="#ff2a4d" stroke-width="2.5" stroke-opacity=".38"/>
 </pattern>
</defs>
<g mask="url(#fade)">
 <g mask="url(#fadeside)">
  <ellipse cx="260" cy="880" rx="700" ry="420" fill="url(#glow)"/>
  <rect width="{W}" height="{H}" fill="url(#hex)"/>
  {"".join(traces)}
 </g>
 <g transform="translate(150 470) scale(1.55)" fill="none" stroke="#ff2a4d" stroke-opacity=".30" stroke-width="3.5">
  <path d="{PAD}"/><circle cx="110" cy="95" r="50"/><path d="M110 70 V120 M85 95 H135"/>
  <circle cx="410" cy="55" r="17"/><circle cx="455" cy="97" r="17"/><circle cx="365" cy="97" r="17"/><circle cx="410" cy="140" r="17"/>
  <circle cx="190" cy="150" r="30"/><circle cx="330" cy="150" r="30"/>
 </g>
</g>
</svg>"""


if __name__ == "__main__":
    svg = OUT.with_suffix(".svg")
    svg.write_text(build())
    subprocess.run(["rsvg-convert", "-w", str(W), str(svg), "-o", str(OUT)], check=True)
    svg.unlink()
    print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
