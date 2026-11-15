"""Qt-free follow-ups: "proceed", "yes", "go ahead", "do it" act on the last thing the assistant offered in this chat.

- After "turn on running tools to do this": turn it on and make the plan (nothing changes until Run all).
- After a plan that is waiting: press Run all (its one confirmation still comes first).
- After a walkthrough with "Do it for me": ask for that.
"No" / "cancel" never changes anything; it only says nothing was done.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_GO = re.compile(r"^(ok(ay)?|k|yes|yeah|yep|yup|ya|sure|please|pls|go|go ahead|go for it|proceed|continue|do it|do that|"
                 r"run it|run that|run all|start|start it|let'?s go|let'?s do it|sounds good|that'?s fine|fine|confirm|"
                 r"confirmed|turn it on|switch it on|enable it|approved?|make it so|send it|yes please|please do|"
                 r"carry on|execute|go on)\b")
_NO = re.compile(r"^(no|nope|nah|cancel|stop|never ?mind|don'?t|do not|forget it|not now)\b")


def _clean(text):
    t = " ".join(str(text or "").casefold().replace("’", "'").split())
    return re.sub(r"[.!?,]+$", "", t)


def is_go_ahead(text):
    t = _clean(text)
    return bool(t) and len(t.split()) <= 7 and bool(_GO.match(t)) and not _NO.match(t)


def is_no(text):
    t = _clean(text)
    return bool(t) and len(t.split()) <= 6 and bool(_NO.match(t))


@dataclass
class Offer:
    kind: str            # "turn_on", "plan", "do"
    request: str = ""    # the user's request the offer came from, or the Do it for me request
    plan_id: str = ""


def last_offer(chat):
    """What the newest assistant message offered, looking only at that message."""
    messages = (chat or {}).get("messages") or []
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        if message.get("role") != "assistant":
            continue
        question = messages[i - 1].get("text", "") if i > 0 and messages[i - 1].get("role") == "user" else ""
        answer = message.get("answer") or {}
        plan = message.get("plan") or {}
        intent = answer.get("intent", "")
        if intent == "autopilot_off" and plan:
            return Offer("turn_on", question)
        if intent == "autopilot" and plan:
            pending = [s for s in plan.get("steps", []) if s.get("ticked") and s.get("status") in ("waiting", "ready")]
            return Offer("plan", question, str(plan.get("id", ""))) if pending else None
        for label, target in answer.get("handoffs", []) or []:
            if label == "Do it for me" and str(target).startswith("ask:"):
                return Offer("do", str(target)[4:])
        return None
    return None


NOTHING = ("I'm not sure what to go ahead with. Ask me for something, like \"clean up my temp files\" or \"fix Elden Ring\", "
           "and I'll show a plan first.")
STALE = "That plan is from before Game Grave was restarted, so it can't run now. Ask again and I'll plan it fresh."
RUNNING = "Running the plan above. Check the changes in the window that opened; nothing changes until you confirm."
DECLINED = "Okay, I didn't do anything."
