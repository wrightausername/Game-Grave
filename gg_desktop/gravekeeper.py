"""The Gravekeeper: the local AI as the one talking in the AI Assistant. Pure: no Qt, no files, no network.

When the local AI is switched on, every chat message goes to the model with the whole conversation. Game Grave's
canned paths (plans, undo, notes, fix history, buttons, charts) become tools the model chooses, so it holds a real
conversation instead of handing the chat to scripted replies. What it can change is unchanged: a tool here only asks
Game Grave to show something or to propose a plan; nothing on the PC changes without the plan's one OK (Run all).

Game Grave's own checks still run on every reply in code (`local_ai_prompt.clean_reply`, `local_ai_tools.problems`):
nothing is called safe to delete, no space is called freed, no change is reported as done, and sizes and installed
games must match the data. So the prompt can talk to the model like a colleague instead of a rule book.

Tools that change what the user sees add an effect to `ctx.effects`; the Qt layer applies them on the main thread.
"""
from __future__ import annotations

import json
import re

from gg_desktop import local_ai_tools as lookups

PERSONA = (
    "You are the Gravekeeper, the assistant built into Game Grave, a Windows app for PC gamers (games, storage, mods, "
    "crashes and the PC itself). You talk like a friend who has fixed gaming PCs for years: relaxed, a little dry, warm, "
    "never stiff or salesy. Keep replies short (two to five sentences) unless you're walking someone through a fix. "
    "Plain text only: no markdown, no headings, no em dashes.\n\n"
    "How you work:\n"
    "- You can look things up on this PC with your tools. Check before you answer anything about this PC, a game on "
    "it, or a problem, and mention briefly what you checked (\"Your crash records show...\").\n"
    "- Fix problems like a good technician: the most likely cause first, one thing at a time, ask whether it worked, "
    "then the next. Don't repeat a fix that already failed. Never claim a cause is certain.\n"
    "- When the user wants something done that Game Grave can do, propose it with make_plan (or undo_last, "
    "run_waiting_plan, turn_on_running_tools). They see the plan and press OK; nothing changes before that, so never "
    "say it's done.\n"
    "- Talk about games freely: what to play, whether a game is any good, modding advice, settings, co-op picks. "
    "General knowledge is fine; just never invent facts about this PC (games, sizes, files, mods, dates).\n"
    "- Unsure what they mean? Ask one short question. Don't know? Say so and suggest the best next step.\n"
    "- Never say something is safe to delete. Sizes are what the scans reported. Never say space was freed.\n"
    "- Offer a button (offer_button) when the user will want to open a tab or tool; show a chart (show_chart) or a "
    "game card (show_game) when a picture says it better. Don't name your tools to the user."
)

# Words people use to correct the last answer ("no, that's wrong"), kept as a lesson for next time.
CORRECTION = re.compile(r"^\s*(no[,.! ]|nope|wrong|that'?s (not|wrong|incorrect)|that isn'?t|incorrect|not true|"
                        r"you'?re wrong|actually[, ])", re.I)
MAX_LESSONS = 12
LESSONS_KEY = "assistant_lessons"

CHARTS = {"space": "where the space goes (biggest games, caches, old files, captures)",
          "drives": "every drive's used and free space",
          "games": "the biggest games"}
LINK_HOSTS = ("pcgamingwiki.com", "store.steampowered.com", "nexusmods.com")


# ------------------------------------------------------------------ the tools only the Gravekeeper has
def _effect(ctx, *item):
    effects = getattr(ctx, "effects", None)
    if effects is not None and item not in effects and len(effects) < 8:
        effects.append(item)


def remember(ctx, note=""):
    note = " ".join(str(note).split())[:300]
    if not note:
        return {"error": "Nothing to remember."}
    _effect(ctx, "note_add", note)
    return {"saved": note, "note": "Kept on this PC only."}


def forget(ctx, what=""):
    what = " ".join(str(what).split())[:200]
    if not what:
        return {"error": "Say which note to forget, or 'all'."}
    _effect(ctx, "note_forget", what)
    return {"forgetting": what}


def undo_last(ctx):
    preview = getattr(ctx, "undo_preview", "") or ""
    if not preview:
        return {"note": "There is no finished plan in this chat that Game Grave can put back. Undo Center has the "
                        "Recycle Bin history."}
    _effect(ctx, "undo")
    return {"will_show": preview, "note": "The undo plan appears in the chat and waits for the user's OK."}


def run_waiting_plan(ctx):
    waiting = getattr(ctx, "waiting_plan", "") or ""
    if not waiting:
        return {"note": "No plan is waiting in this chat."}
    _effect(ctx, "run_plan")
    return {"running": waiting, "note": "Game Grave asks the user to confirm every change first."}


def turn_on_running_tools(ctx):
    if getattr(ctx, "tools_on", False):
        return {"note": "Running tools is already on."}
    pending = getattr(ctx, "tools_off_request", "") or ""
    _effect(ctx, "tools_on")
    return {"turned_on_for": pending or "the next plan",
            "note": "Plans still wait for the user's OK (Run all) before anything changes."}


def record_fix_result(ctx, game="", worked="", what=""):
    g = lookups.find_game(ctx.facts, game)
    name = g.name if g is not None else " ".join(str(game).split())[:80]
    if not name:
        return {"error": "Which game?"}
    ok = str(worked).strip().casefold() in ("true", "yes", "1", "fixed", "worked")
    _effect(ctx, "fix_result", name, ok, " ".join(str(what).split())[:160])
    return {"recorded": name, "worked": ok}


def offer_button(ctx, label="", opens=""):
    target = resolve_target(opens)
    if not target:
        return {"error": f"Game Grave has no tab or tool called {opens}."}
    text = " ".join(str(label).split())[:40] or "Open " + target[1]
    _effect(ctx, "button", text, target[0])
    return {"button": text}


def show_chart(ctx, kind="space"):
    kind = str(kind).strip().casefold()
    if kind not in CHARTS:
        return {"error": "Charts: " + ", ".join(CHARTS)}
    _effect(ctx, "chart", kind)
    return {"showing": CHARTS[kind], "note": "Drawn from the scanned figures; don't repeat every number."}


def show_game(ctx, name=""):
    g = lookups.find_game(ctx.facts, name)
    if g is None:
        return {"error": f"{name} isn't one of the installed games."}
    _effect(ctx, "game_card", g.name)
    return {"showing": g.name}


def game_page(ctx, name=""):
    """A link to the game's PCGamingWiki page (known issues and fixes). The wiki's text is not copied into Game Grave:
    its licence is non-commercial, so the user opens the page themselves."""
    g = lookups.find_game(ctx.facts, name)
    title = g.name if g is not None else " ".join(str(name).split())[:80]
    if not title:
        return {"error": "Which game?"}
    app_id = str(getattr(g, "app_id", "") or "") if g is not None and getattr(g, "launcher", "") == "Steam" else ""
    url = (f"https://pcgamingwiki.com/api/appid.php?appid={app_id}" if app_id.isdigit()
           else "https://www.pcgamingwiki.com/w/index.php?search=" + re.sub(r"\s+", "+", re.sub(r"[^\w\s:'-]", "", title)))
    _effect(ctx, "link", f"{title} on PCGamingWiki", url)
    return {"button_shown": f"{title} on PCGamingWiki",
            "note": "PCGamingWiki lists known issues and fixes for the PC version. Tell the user what the page is good "
                    "for; you can't read it yourself."}


def what_to_play(ctx, mood=""):
    """Installed games for a pick: when each was last played, size, and Steam's co-op tags where Game Grave has them."""
    f = ctx.facts
    modes = getattr(ctx, "modes", None)
    modes = modes() if callable(modes) else (modes or {})
    rows = []
    for g in list(getattr(f, "games", ()) or ())[:120]:
        days = lookups._days(g.last_played_at, f.now) if g.last_played_at else None
        row = {"game": g.name, "last_played": f"{days} days ago" if days is not None else "never or unknown",
               "size": lookups._size(g.size_bytes) if g.size_bytes else "unknown"}
        tags = modes.get(str(getattr(g, "app_id", "") or "")) if modes else None
        if tags:
            row["modes"] = list(tags)
        rows.append(row)
    rows.sort(key=lambda r: (r["last_played"] != "never or unknown", r["game"]))
    return {"mood": mood, "installed": rows[:60], "count": len(rows),
            "note": "Pick from these. Use what you know about the games themselves (genre, length, co-op) and say why."}


def past_chats(ctx, query=""):
    """Earlier conversations in this assistant that mention the words (titles, questions, answers)."""
    chats = getattr(ctx, "all_chats", None) or []
    words = [w for w in str(query).casefold().split() if len(w) > 2][:6]
    found = []
    for chat in chats:
        if chat.get("id") == getattr(ctx, "chat_id", None):
            continue
        for m in chat.get("messages") or []:
            text = str(m.get("text") or "")
            if words and all(w in text.casefold() for w in words):
                found.append({"chat": chat.get("title", ""), "role": m.get("role"), "said": text[:300]})
                break
        if len(found) >= 6:
            break
    return {"matches": found} if found else {"note": "Nothing in earlier chats mentions that."}


AGENT_TOOLS = {"remember": remember, "forget": forget, "undo_last": undo_last, "run_waiting_plan": run_waiting_plan,
               "turn_on_running_tools": turn_on_running_tools, "record_fix_result": record_fix_result,
               "offer_button": offer_button, "show_chart": show_chart, "show_game": show_game, "game_page": game_page,
               "what_to_play": what_to_play, "past_chats": past_chats}
DOING = {"what_to_play": "your library", "past_chats": "our earlier chats", "game_page": "the game's wiki page"}


def resolve_target(name):
    """(route or tool key, shown name) for a tab or a Game Grave tool, or None."""
    from gg_desktop import nav_groups
    from gg_desktop import assistant_features as features
    want = re.sub(r"[^a-z0-9]+", " ", str(name or "").casefold()).strip()
    if not want:
        return None
    for route in nav_groups.routes():
        shown = nav_groups.display_name(route)
        if want in (shown.casefold(), route.casefold()):
            return route, shown
    for f in features.FEATURES:
        if want == re.sub(r"[^a-z0-9]+", " ", f.title.casefold()).strip() and f.opens:
            return "tool:" + f.key, f.title
    for f in features.FEATURES:
        if want in f.title.casefold() and f.opens:
            return "tool:" + f.key, f.title
    return None


def _p(description, kind="string", optional=False, **extra):
    return dict({"type": kind, "description": description, "optional": optional}, **extra)


def agent_specs(ctx=None):
    """Every lookup, make_plan, and the Gravekeeper's own tools."""
    specs = lookups.tool_specs()
    specs += [
        lookups._fn("what_to_play", "The installed games with when each was last played, size and co-op tags, to "
                    "suggest what to play.", mood=_p("What they're in the mood for, if they said", optional=True)),
        lookups._fn("game_page", "Show a button to the game's PCGamingWiki page (known issues and fixes for the PC "
                    "version).", name=_p("The game")),
        lookups._fn("past_chats", "Search earlier conversations with this user.", query=_p("Words to look for")),
        lookups._fn("remember", "Keep a note the user asked you to remember (kept on this PC).",
                    note=_p("The note, in the user's words")),
        lookups._fn("forget", "Forget one of the user's notes, or all of them.", what=_p("Words from the note, or all")),
        lookups._fn("undo_last", "Propose putting back what the last finished plan in this chat changed (waits for OK)."),
        lookups._fn("run_waiting_plan", "Press Run all on the plan waiting in this chat (Game Grave still asks the user "
                    "to confirm). Only when the user said to go ahead."),
        lookups._fn("turn_on_running_tools", "Switch on 'Let the assistant run tools' because the user asked you to go "
                    "ahead with a plan while it was off."),
        lookups._fn("record_fix_result", "Note whether a fix worked for a game.", game=_p("The game"),
                    worked=_p("yes or no"), what=_p("What was tried", optional=True)),
        lookups._fn("offer_button", "Show a button that opens a Game Grave tab or tool.", label=_p("Button text, short"),
                    opens=_p("The tab or tool, e.g. Graveyard, Fix Kit, Crash Doctor, Game Optimizer")),
        lookups._fn("show_chart", "Show a chart in the chat.", kind=_p("space, drives or games", enum=list(CHARTS))),
        lookups._fn("show_game", "Show the game's card (artwork, size, last played).", name=_p("The game")),
    ]
    for s in specs:   # the lookups' own helper already removed "optional"; ours are cleaned the same way
        props = s["function"]["parameters"]["properties"]
        required = [k for k, v in props.items() if not v.pop("optional", False)] if any(
            "optional" in v for v in props.values()) else s["function"]["parameters"].get("required", [])
        s["function"]["parameters"]["required"] = required
    return specs


def run(ctx, name, arguments):
    func = AGENT_TOOLS.get(name)
    if func is None:
        return lookups.run(ctx, name, arguments)
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except ValueError:
            arguments = {}
    arguments = arguments if isinstance(arguments, dict) else {}
    allowed = func.__code__.co_varnames[1:func.__code__.co_argcount]
    try:
        result = func(ctx, **{k: v for k, v in arguments.items() if k in allowed})
    except Exception as exc:
        result = {"error": f"That didn't work: {exc}"}
    return lookups.fit(result)


def doing(name):
    if name in DOING:
        return "Looking at " + DOING[name] + "…"
    return lookups.doing(name).replace("Checking ", "Looking at ", 1)


# ------------------------------------------------------------------ what the model is told
def lessons_text(settings):
    rows = list((settings or {}).get(LESSONS_KEY) or [])[-6:]
    lines = []
    for r in rows:
        if r.get("correction"):
            lines.append(f"- Asked \"{r.get('question', '')[:120]}\", you said \"{r.get('wrong', '')[:160]}\"; the user "
                         f"corrected you: \"{r.get('correction', '')[:200]}\"")
        else:
            lines.append(f"- Asked \"{r.get('question', '')[:120]}\", your answer \"{r.get('wrong', '')[:160]}\" was "
                         "marked not helpful.")
    return "\n".join(lines)


def add_lesson(settings, question, wrong, correction=""):
    rows = list((settings or {}).get(LESSONS_KEY) or [])[-(MAX_LESSONS - 1):]
    rows.append({"question": str(question)[:300], "wrong": str(wrong)[:400], "correction": str(correction)[:400]})
    return dict(settings, **{LESSONS_KEY: rows})


def memory_text(chats, current_id, fix_history):
    """What the Gravekeeper remembers from other chats: recent topics and what was tried for which game."""
    lines = []
    others = [c for c in chats or [] if c.get("id") != current_id and c.get("messages")]
    others.sort(key=lambda c: -(c.get("updated") or 0))
    for c in others[:8]:
        first = next((m.get("text", "") for m in c["messages"] if m.get("role") == "user"), "")
        lines.append(f"- Earlier chat \"{str(c.get('title', ''))[:60]}\": they asked \"{str(first)[:140]}\"")
    for game, rows in list((fix_history or {}).items())[:10]:
        last = (rows or [])[-3:]
        if last:
            lines.append(f"- {game}: tried " + "; ".join(f"{r.get('tried', '')[:60]} ({r.get('result', '')})"
                                                          for r in last))
    return "\n".join(lines)


def messages(question, facts, history, ctx, think=False, notes="", level="", memory="", lessons="", image=None):
    """The chat for llama-server: who it is, the PC in short, what it remembers, the real conversation, the question."""
    from gg_desktop import local_ai_prompt as prompt
    digest = prompt.facts_digest(facts, limit=30, cap=7000, tools=True)
    parts = [PERSONA, f"Today is {lookups.today()}. " + lookups.screen_line(ctx.screen),
             "This PC in short (look up anything else):\n" + digest,
             "What Game Grave can do and where:\n" + prompt.feature_list(),
             "Plans you can propose with make_plan: " + "; ".join(f"{k} ({v})" for k, v in lookups.JOBS.items())]
    if getattr(ctx, "waiting_plan", ""):
        parts.append("A plan is waiting for the user's OK in this chat: " + ctx.waiting_plan)
    if getattr(ctx, "tools_off_request", ""):
        parts.append("Running tools is off, so the last plan was only a preview: " + ctx.tools_off_request)
    if memory:
        parts.append("What you remember from before (bring it up only when it helps):\n" + memory[:2500])
    if notes:
        parts.append("Things the user asked you to remember:\n" + notes[:2000])
    if lessons:
        parts.append("Mistakes you made before; don't repeat them:\n" + lessons[:2000])
    if level:
        parts.append("How to explain: " + level)
    out = [{"role": "system", "content": "\n\n".join(p for p in parts if p)}]
    for q, a in list(history)[-10:]:
        out += [{"role": "user", "content": str(q)[:1200]}, {"role": "assistant", "content": str(a)[:1600]}]
    ask = str(question)[:3500]
    if image:
        out.append({"role": "user", "content": [{"type": "text", "text": ask},
                                                {"type": "image_url", "image_url": {"url": image}}]})
    else:
        out.append({"role": "user", "content": ask})
    return out


def asked_not_told(text):
    """True for a plain question ("what are temp files?"), which is answered, never turned into a plan. Anything that
    asks for something to be done ("sort it out", "can you clean my temp files?") may become a plan."""
    from gg_desktop import autopilot_core as core
    t = " ".join(str(text or "").casefold().split())
    if core.is_request(t):
        return False
    return t.endswith("?") or bool(core._QUESTION.match(t))


# ------------------------------------------------------------------ one turn
MAX_ROUNDS = 6
_PROMISE = re.compile(r"\b(let me|i'?ll|i will|i'?m going to) (check|look|find|see|pull|get)\b", re.I)


def turn(server, question, facts, history, ctx, think=False, events=None, image=None, settings=None, lookups_first=True):
    """One reply from the Gravekeeper. Returns dict(text, jobs, summary, effects, results, looked, unchecked)."""
    from gg_desktop import local_ai_prompt as prompt
    from gg_desktop import assistant_memory as memory
    events = events or (lambda kind, text: None)
    settings = settings if settings is not None else (getattr(ctx, "settings", None) or {})
    if getattr(ctx, "effects", None) is None:
        ctx.effects = []
    msgs = messages(question, facts, history, ctx, think=think, notes=memory.notes_text(settings),
                    level=memory.level_text(settings), memory=getattr(ctx, "memory", ""),
                    lessons=lessons_text(settings), image=image)
    first = lookups.prefetch(question, ctx) if lookups_first else []
    for fn, _a in first:
        events("look", doing(fn))
    msgs, results, _checked = lookups.with_prefetch(msgs, ctx, first)
    looked = [fn for fn, _a in first]
    tools = agent_specs(ctx)
    from gg_desktop import autopilot_core as core
    budget = dict(max_tokens=2600, timeout=420) if think else dict(max_tokens=1000, timeout=240)
    shrunk = {"on": False}
    stream = {"on_text": lambda text: events("text", text)} if events else {}

    def ask(m, offer):
        try:
            return server.chat_message(lookups._shrink(m) if shrunk["on"] else m, offer, think=think, **budget, **stream)
        except Exception as exc:
            if "400" not in str(exc) or shrunk["on"]:
                raise
            shrunk["on"] = True
            return server.chat_message(lookups._shrink(m), offer, think=think, **budget, **stream)
    result = {"text": "", "jobs": None, "summary": "", "effects": ctx.effects, "results": results, "looked": looked,
              "unchecked": []}
    nudged = False
    for round_no in range(MAX_ROUNDS + 1):
        offer = tools if round_no < MAX_ROUNDS else None
        reply = ask(msgs, offer) or {}
        calls = lookups.calls_in(reply)
        said = lookups._TEXT_CALL.sub("", str(reply.get("content") or "")).strip()
        if not calls and offer is not None and not nudged and _PROMISE.search(said) and len(said) < 200:
            nudged = True
            msgs += [{"role": "assistant", "content": said}, {"role": "user", "content": "Go ahead and look."}]
            continue
        if not calls or offer is None or (result["jobs"] and all(n == "make_plan" for _c, n, _a in calls)):
            result["text"] = said           # (a second make_plan after the plan is set is taken as the end)
            break
        shown = prompt.clean_reply(said)
        if shown:
            events("say", shown)                 # "Let me check your crash records…" in its own words
        msgs.append({"role": "assistant", "content": reply.get("content") or "",
                     "tool_calls": [{"id": cid, "type": "function", "function": {
                         "name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}
                         for cid, name, args in calls]})
        for cid, name, args in calls:
            if name == "make_plan":
                data = args if isinstance(args, dict) else lookups._json(args)
                if asked_not_told(question) and not getattr(ctx, "allow_plans", False):
                    content = json.dumps({"note": "That was a question, not a request to do something. Answer it; "
                                                  "offer the plan in words if it would help."})
                else:
                    steps, dropped = lookups.plan_steps(data.get("jobs") or [])
                    if steps:
                        result["jobs"] = data.get("jobs") or []
                        result["summary"] = str(data.get("summary") or "")[:300]
                    content = json.dumps({"planned": [s.title for s in steps], "dropped": dropped,
                                          "note": "The plan is shown to the user and waits for their OK. Say what "
                                                  "it will do in a sentence; don't say it's done."})
                msgs.append({"role": "tool", "tool_call_id": cid, "name": name, "content": content})
                continue
            looked.append(name)
            events("look", doing(name))
            out = run(ctx, name, args)
            results.append(out)
            msgs.append({"role": "tool", "tool_call_id": cid, "name": name, "content": out})
    raw = result["text"]
    if not raw.strip() and not result["jobs"]:
        raw = server.chat(msgs + [{"role": "user", "content": "Reply to me now in plain words."}],
                          max_tokens=700, timeout=240, think=False) or ""
        result["blank"] = not raw.strip()
    text = prompt.clean_reply(raw)
    if not text and raw.strip() and not result["jobs"]:
        retry = msgs + [{"role": "assistant", "content": "…"}, {"role": "user", "content": prompt.RETRY_NOTE}]
        text = prompt.clean_reply(server.chat(retry, max_tokens=900, timeout=240, think=False))
        result["broke_rules"] = not text
    wrong = lookups.problems(text, facts, results) if text else []
    if wrong:
        fix = msgs + [{"role": "assistant", "content": text},
                      {"role": "user", "content": lookups.FIX_NOTE.format(problems="; ".join(wrong))}]
        again = prompt.clean_reply(server.chat(fix, max_tokens=900, timeout=240, think=False))
        still = lookups.problems(again, facts, results) if again else wrong
        text = again if again and len(still) < len(wrong) else text
        result["unchecked"] = still if again else wrong
    if not text and result["jobs"]:
        text = (result["summary"] or "Here's the plan.") + " Nothing changes until you press OK."
    result["text"] = text
    return result
