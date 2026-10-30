"""Game Grave's lightweight, accessible, game-aware visual explainers.

Native Tkinter canvas artwork, not stock images or decorative downloads.
The graphs are visual aids only: the same information is available as text.
No scan, file change, autoplay, animation or network request occurs here.
"""
from __future__ import annotations

import tkinter as tk

MIN_WIDTH = 270


def dna_counts(dna: dict) -> dict:
    """Ground all labels in the existing read-only DNA graph."""
    games = dna.get("games", [])
    unresolved = dna.get("unresolved", [])
    associated = sum(len(game.get("assets", [])) for game in games)
    ambiguous = sum(bool(x.get("ambiguous")) for x in unresolved)
    return {
        "games": len(games), "associated": associated,
        "review": len(unresolved), "ambiguous": ambiguous,
        "authorized_removal": 0,
    }


def flow_steps() -> tuple[tuple[str, str], ...]:
    """No part of the visual may claim that ownership permits cleanup."""
    return (
        ("FIND", "Recognize local storage"),
        ("MATCH", "Check verified evidence"),
        ("PROTECT", "Never assume unused"),
    )


def _round(canvas, x0, y0, x1, y1, r, *, fill, outline, width=1):
    """Anti-aliased-style rounded card outline using native canvas curves."""
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    coords = [
        x0+r,y0, x1-r,y0, x1,y0, x1,y0+r, x1,y1-r,
        x1,y1, x1-r,y1, x0+r,y1, x0,y1, x0,y1-r, x0,y0+r,
        x0,y0
    ]
    return canvas.create_polygon(coords, fill=fill, outline=outline,
                                 width=width, smooth=True, splinesteps=18)


def _node(canvas, box, title, value, detail, palette, tint):
    x0,y0,x1,y1 = box
    _round(canvas,x0,y0,x1,y1,13,fill=palette["raised"],outline=palette["line"])
    canvas.create_rectangle(x0+11, y0+14, x0+14, y1-14,
                            fill=tint, outline="")
    cx=(x0+x1)/2
    canvas.create_text(cx, y0+20, text=title, fill=palette["muted"],
                       font=("Segoe UI Semibold", 9), anchor="center")
    canvas.create_text(cx, y0+48, text=str(value), fill=tint,
                       font=("Segoe UI Semibold", 23), anchor="center")
    canvas.create_text(cx, y1-15, text=detail, fill=palette["text"],
                       font=("Segoe UI", 8), anchor="center")


def _connector(canvas, coords, color, dashed=False):
    canvas.create_line(*coords, fill=color, width=2, smooth=True,
                       dash=(4,4) if dashed else (),
                       arrow="last", arrowshape=(7,9,3))


def _dna_draw(canvas, width, counts, colors):
    canvas.delete("all")
    width=max(MIN_WIDTH,width)
    canvas.configure(bg=colors["panel"])
    wide=width>=675
    canvas.configure(height=198 if wide else 218)
    if wide:
        left=(14,55,183,137)
        center_x=round(width*0.37)
        middle1=(center_x,10,center_x+185,91)
        middle2=(center_x,106,center_x+185,187)
        end=(width-184,55,width-14,137)
        _connector(canvas,[left[2]+3,92,center_x-18,50,middle1[0]-3,50],colors["accent"])
        _connector(canvas,[left[2]+3,111,center_x-18,146,middle2[0]-3,146],colors["warn"],True)
        _connector(canvas,[middle1[2]+3,54,width-206,93,end[0]-3,94],colors["accent"])
        _connector(canvas,[middle2[2]+3,146,width-206,108,end[0]-3,108],colors["warn"],True)
        _node(canvas,left,"GAME RECORDS",counts["games"],"Manifest / inventory",colors,colors["blue"])
        _node(canvas,middle1,"LINKED MOD STORAGE",counts["associated"],"Evidence match",colors,colors["accent"])
        _node(canvas,middle2,"NEEDS REVIEW",counts["review"],"Owner unknown",colors,colors["warn"])
        _node(canvas,end,"SAFE BY DEFAULT","0","Automatic removals",colors,colors["blue"])
    else:
        gap=10
        half=(width-30-gap)/2
        a=(10,8,10+half,101)
        b=(20+half,8,20+half*2,101)
        c=(10,113,10+half,206)
        d=(20+half,113,20+half*2,206)
        _node(canvas,a,"GAME RECORDS",counts["games"],"Known locations",colors,colors["blue"])
        _node(canvas,b,"LINKED MODS",counts["associated"],"Evidence matches",colors,colors["accent"])
        _node(canvas,c,"REVIEW",counts["review"],"Ownership unknown",colors,colors["warn"])
        _node(canvas,d,"AUTO REMOVED","0","Everything protected",colors,colors["blue"])


def dna_visual(parent, dna: dict, *, palette: dict, scanned: bool = True) -> tk.Frame:
    """Create a responsive map of observed/unknown/protected relationships."""
    counts=dna_counts(dna)
    root=tk.Frame(parent,bg=palette["panel"])
    heading=tk.Frame(root,bg=palette["panel"])
    heading.pack(fill="x")
    tk.Label(heading,text="GAME DNA  /  RELATIONSHIP MAP",
             fg=palette["text"],bg=palette["panel"],
             font=("Segoe UI Semibold",11)).pack(side="left")
    tk.Label(heading,text="SCAN SNAPSHOT" if scanned else "NOT YET SCANNED",
             fg=palette["accent"] if scanned else palette["warn"],
             bg=palette["panel"],font=("Segoe UI",8)).pack(side="right")
    canvas=tk.Canvas(root,bg=palette["panel"],highlightthickness=0,
                     borderwidth=0,height=198)
    canvas.pack(fill="x",pady=(6,2))
    last={"width":None}
    def paint(event=None):
        width=canvas.winfo_width()
        if width<MIN_WIDTH:
            return
        if width==last["width"]:
            return
        last["width"]=width
        _dna_draw(canvas,width,counts,palette)
    canvas.bind("<Configure>",paint)
    tk.Label(root,text=(
        "Solid line = recorded association. Dotted line = uncertain ownership. "
        "Both remain protected. This is NOT a deletion map."),
        fg=palette["muted"],bg=palette["panel"],anchor="w",
        font=("Segoe UI",9),wraplength=610,justify="left"
    ).pack(fill="x",pady=(1,0))
    return root


def _steps_draw(canvas, width, palette):
    canvas.delete("all")
    width=max(MIN_WIDTH,width)
    canvas.configure(bg=palette["panel"])
    wide=width>=520
    steps=flow_steps()
    if wide:
        canvas.configure(height=89)
        gap=25
        cell=max(80,(width-32-2*gap)/3)
        for i,(name,description) in enumerate(steps):
            x=10+i*(cell+gap)
            _round(canvas,x,5,x+cell,84,12,fill=palette["raised"],
                   outline=palette["line"])
            canvas.create_text(x+cell/2,29,text=f"0{i+1}  {name}",
                               fill=(palette["accent"] if i==1 else palette["blue"]),
                               font=("Segoe UI Semibold",11))
            canvas.create_text(x+cell/2,58,text=description,fill=palette["text"],
                               font=("Segoe UI",9))
            if i<2:
                _connector(canvas,[x+cell+3,44,x+cell+gap-4,44],palette["muted"])
    else:
        canvas.configure(height=138)
        for i,(name,description) in enumerate(steps):
            y=3+i*46
            _round(canvas,8,y,width-8,y+39,9,fill=palette["raised"],
                   outline=palette["line"])
            canvas.create_text(24,y+19,text=f"0{i+1}  {name}",anchor="w",
                               fill=palette["accent"] if i==1 else palette["blue"],
                               font=("Segoe UI Semibold",10))
            canvas.create_text(width-19,y+19,text=description,anchor="e",
                               fill=palette["text"],font=("Segoe UI",9))


def mod_radar_visual(parent, *, palette: dict) -> tk.Frame:
    """Explain scanner workflow, without asserting any item is unused."""
    root=tk.Frame(parent,bg=palette["panel"])
    tk.Label(root,text="HOW MOD RADAR THINKS",bg=palette["panel"],fg=palette["text"],
             font=("Segoe UI Semibold",11),anchor="w").pack(fill="x")
    canvas=tk.Canvas(root,bg=palette["panel"],height=89,highlightthickness=0)
    canvas.pack(fill="x",pady=(4,3))
    last={"width":None}
    def paint(event=None):
        w=canvas.winfo_width()
        if w<MIN_WIDTH or w==last["width"]:
            return
        last["width"]=w
        _steps_draw(canvas,w,palette)
    canvas.bind("<Configure>",paint)
    tk.Label(root,text="Old, disabled or unmatched never means safe to delete. Review before any cleanup.",
             bg=palette["panel"],fg=palette["muted"],wraplength=650,
             justify="left",anchor="w",font=("Segoe UI",9)).pack(fill="x")
    return root
