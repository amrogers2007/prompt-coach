"""Claude hook handlers: SessionStart, UserPromptSubmit, PostToolUse.

Each handler takes the hook's stdin JSON (already parsed) and returns a dict to
print as the hook's JSON output, or None for "say nothing". Handlers must
never raise into the user's session; the entry point wraps them and swallows
errors (logged to ~/.prompt-coach/errors.log).

Output contract (Claude Code hooks):
  systemMessage                       -> shown to the *user* (our toasts)
  hookSpecificOutput.additionalContext -> given to *Claude* (our coaching)
"""

import hashlib
import os
import random
import re
import tempfile

from . import cadence, game, lessons, scoring, signals, store

GEN_REFINE_CREDIT_MAX = 2       # a doc is "fully iterated" after this many revisions
PENDING_STALE_SECONDS = 60 * 60  # an un-revised draft is "accepted" after an hour
NUDGE_COOLDOWN_SECONDS = 90
OFFER_TTL_SECONDS = 30 * 60      # a coaching offer can be accepted within this long
OFFER_ACCEPTED_XP = 5
DECLINES_BEFORE_MUTE = 2                 # two "no thanks" to the same tip mutes it...
DECLINE_MUTE_SECONDS = 14 * 86400        # ...for two weeks
MISFIT_MUTE_SECONDS = 30 * 86400         # "that doesn't apply" mutes it for a month

_rng = random.Random()


def _in_holdout(state, lesson, reason, detected, matched):
    """Randomized holdout for pilots (settings: experiment <percent>).

    Randomization is per user *and issue*: the first time an issue (trigger) is
    spotted it is assigned for good to 'coach' or 'holdout'. Holding back single
    moments instead would contaminate the comparison, because a user coached on
    an issue once is no longer an untreated control for it. Safety and other
    urgent tips are never withheld."""
    share = float(state["settings"].get("holdout", 0) or 0)
    if share <= 0 or not detected or not matched or lesson.get("urgent") or reason in ("safety", "urgent"):
        return False
    arms = state["coach"].setdefault("arms", {})
    issue = matched[0]
    if issue not in arms:
        arms[issue] = "holdout" if _rng.random() < share else "coach"
    return arms[issue] == "holdout"


# --- helpers -------------------------------------------------------------------------

def _session(state, sid, ts):
    s = state["sessions"].setdefault(sid, {"prompts": 0, "pending_gen": None,
                                           "last_ts": ts, "coached_this_turn": False,
                                           "last_nudge_ts": 0})
    s["last_ts"] = ts
    return s


def _gen_by_id(state, gid):
    for g in state["gens"]:
        if g["id"] == gid:
            return g
    return None


def _path_key(path):
    norm = os.path.normcase(os.path.abspath(path or ""))
    return hashlib.sha1(norm.encode("utf-8", "replace")).hexdigest()[:10]


def _resolve_gen(state, gen, ts, accepted_first_draft):
    if gen is None or gen.get("resolved"):
        return
    gen["resolved"] = True
    gen["resolved_ts"] = ts
    if accepted_first_draft:
        state["totals"]["first_drafts_accepted"] += 1
    store.append_event({"type": "gen_resolved", "gen": gen["id"], "revisions": gen["revisions"],
                        "accepted_first_draft": bool(accepted_first_draft), "ts": ts})


def _expire_pending(state, session, ts):
    gid = session.get("pending_gen")
    if not gid:
        return
    gen = _gen_by_id(state, gid)
    if gen is None:
        session["pending_gen"] = None
        return
    if ts - gen["ts"] > PENDING_STALE_SECONDS:
        _resolve_gen(state, gen, ts, accepted_first_draft=gen["revisions"] == 0)
        session["pending_gen"] = None


def delivery_mode(settings):
    """How short status messages (welcome, level-ups, streaks) reach the user.

    'system': the hook's systemMessage, which the terminal shows directly.
    'chat':   Claude says it in its reply. The Claude desktop app records a
              hook's systemMessage but doesn't display it, so there the coach
              has to speak through the conversation to be seen at all.
    'auto' (default) picks 'chat' inside the desktop app, 'system' elsewhere.
    """
    mode = settings.get("toasts", "auto")
    if mode in ("system", "chat"):
        return mode
    entry = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")
    return "chat" if entry.startswith("claude-desktop") else "system"


def refresh_saved_pages():
    """The dashboard and the summary are files on disk. Once the user has made
    them, keep them current, so an open tab or a bookmark never shows an old
    streak or score. Never creates them, and never lets a failure reach the session."""
    try:
        from . import dashboard, report
        if os.path.exists(dashboard.default_path()):
            dashboard.write(open_browser=False)
        if os.path.exists(os.path.join(store.home(), "summary.md")):
            report.write_shareables(report.build())
    except Exception as exc:  # noqa: BLE001  (a convenience; the coaching itself already happened)
        store.log_error("refresh", exc)


def _output(system_lines=None, context=None, event="UserPromptSubmit", mode="system", where="end"):
    out = {}
    text = "Prompt Coach: " + " ".join(system_lines) if system_lines else ""
    if text and mode == "chat":
        place = ("at the very start of your FIRST reply in this conversation, whatever the user asks (put the note "
                 "first, then answer their request normally)"
                 if where == "start" else "at the very end of your reply, after everything else")
        note = ("[Prompt Coach: status note]\nInclude this exact one-line note %s, on its own line and in italics. "
                "It is a friendly status message for the user, not part of your answer, so do not comment on it:\n*%s*"
                % (place, text))
        context = (context + "\n\n" + note) if context else note
    elif text:
        out["systemMessage"] = text
    if context:
        out["hookSpecificOutput"] = {"hookEventName": event, "additionalContext": context}
    return out or None


# --- SessionStart -------------------------------------------------------------------------

def handle_session(payload, delivery=None):
    ts = store.now()
    state = store.load_state()
    sid = payload.get("session_id") or "unknown"
    session = _session(state, sid, ts)
    session["prompts"] = 0
    session["pending_gen"] = None
    session["urgent_shown"] = []
    session.pop("offer", None)
    store.prune_events()

    events = store.read_events(tail_bytes=store.RECENT_BYTES)
    m = scoring.compute_metrics(events, state["gens"])
    level = scoring.resolve_level(m, state["level"])
    state["level"] = level
    store.save_state(state)

    if not state["settings"].get("enabled", True):
        return None

    refresh_saved_pages()
    mode = delivery or delivery_mode(state["settings"])
    lines = []
    if not state.get("welcomed"):
        lines.append("I'm your AI coach. Just work as usual; every so often I'll ask a question to help you "
                     "get more out of AI. Type /prompt-coach:score any time to see your level.")
        state["welcomed"] = True
        store.save_state(state)
    else:
        # Every session opens with the coach introducing itself, so it is always clear it is on.
        streak = game.streak_status(state, ts)
        bits = ["%s (Level %d of 4)" % (game.level_name(level), level)]
        if streak["count"] >= 1 and not streak["today"]:
            # Today isn't counted yet: say what moves the number, so it doesn't look stuck.
            bits.append("%d-day streak, and a well-set-up request today makes it %d"
                        % (streak["count"], streak["count"] + 1))
        elif streak["count"] >= 2:
            bits.append("%d-day streak" % streak["count"])
        lines.append("Welcome back, I'm your AI coach (%s). I'll pop in with a question now and then "
                     "to help you get more out of AI." % ", ".join(bits))

    context = (
        "Prompt Coach is active for this user, a non-technical professional learning to use AI well. "
        "A coaching hook may occasionally send you a '[Prompt Coach: ...]' instruction for a specific reply; "
        "follow those when they appear, and otherwise just be helpful as normal. "
        "Current level: %s." % game.level_name(level)
    )
    return _output(lines, context, "SessionStart", mode, where="start")


def choose_skill(reason, analysis, metrics, level, last_focus):
    """Pick the habit to coach. Reacts to what the user just did first, then to
    their weakest habit overall, and avoids coaching the same habit twice in a row."""
    if reason == "safety":
        return "safety"
    if reason == "low_context":
        return "context"

    candidates = []
    kind = analysis["kind"]
    if kind == "new":
        if analysis["context"] < 0.5:
            candidates.append("context")
        if analysis["precision"] < 0.3:
            candidates.append("precision")
        if analysis.get("feature") == 0.0:
            candidates.append("feature")
    elif kind == "refine" and analysis.get("vague_refine"):
        candidates.append("iteration")

    comps = metrics.get("components", {})
    ranked = sorted((k for k in comps if k != "consistency"), key=lambda k: comps[k]["value"])
    for k in ranked:
        candidates.append(lessons.COMPONENT_TO_SKILL.get(k, "context"))
    candidates.append("context")

    ordered = []
    for c in candidates:
        if c not in ordered:
            ordered.append(c)
    for c in ordered:
        if c != last_focus:
            return "advanced" if (level >= 3 and c == last_focus) else c
    return ordered[0]


# --- UserPromptSubmit ---------------------------------------------------------------------

def _already_handled(state, text, ts, source):
    """The same message can reach us twice when both the hooks (Code tab) and the
    desktop helper (chat tools) are active. The first channel to see it wins."""
    digest = hashlib.sha1(text.strip().encode("utf-8", "replace")).hexdigest()[:12]
    recent = [r for r in state.get("recent", []) if ts - r[1] < 120]
    seen_elsewhere = any(r[0] == digest and r[2] != source for r in recent)
    if not any(r[0] == digest and r[2] == source for r in recent):
        recent.append([digest, ts, source])
    state["recent"] = recent[-20:]
    return seen_elsewhere


def seen_by_other_channel(text, source):
    """True if the other channel already handled this very message (read-only)."""
    digest = hashlib.sha1((text or "").strip().encode("utf-8", "replace")).hexdigest()[:12]
    ts = store.now()
    return any(r[0] == digest and r[2] != source and ts - r[1] < 120
               for r in store.load_state().get("recent", []))


def _take_offer(state, session, text, ts):
    """The coach's last offer is only answerable by the very next message. A yes
    returns the follow-up instruction (the AI carries out the recommendation);
    anything else just lets the offer lapse."""
    offer = session.pop("offer", None)
    if not offer or ts - offer.get("ts", 0) > OFFER_TTL_SECONDS:
        return None
    coach = state["coach"]
    lesson_id = offer["ids"][0]
    if signals.is_misfit(text):
        # The tip didn't fit: a false positive. Never repeat it for a month, and say so.
        entry = lessons.get(lesson_id)
        if not (entry and entry["urgent"]):      # safety tips are recorded but never silenced
            coach["muted"][lesson_id] = ts + MISFIT_MUTE_SECONDS
        store.append_event({"type": "offer_misfit", "lesson": lesson_id, "ts": ts})
        return lessons.misfit_instruction()
    if signals.is_decline(text):
        declines = coach["declines"].get(lesson_id, 0) + 1
        coach["declines"][lesson_id] = declines
        if declines >= DECLINES_BEFORE_MUTE:
            coach["muted"][lesson_id] = ts + DECLINE_MUTE_SECONDS
            coach["declines"][lesson_id] = 0
        store.append_event({"type": "offer_declined", "lesson": lesson_id, "ts": ts})
        return None
    if not signals.is_acceptance(text):
        return None
    entries = [e for e in (lessons.get(i) for i in offer["ids"]) if e]
    if not entries:
        return None
    state["totals"]["offers_accepted"] += 1
    state["xp"] += OFFER_ACCEPTED_XP
    store.append_event({"type": "offer_accepted", "lesson": entries[0]["id"], "skill": entries[0]["skill"], "ts": ts})
    return lessons.followup_instruction(entries)


def handle_prompt(payload, delivery=None, source="hook"):
    text = payload.get("prompt") or ""
    ts = store.now()
    sid = payload.get("session_id") or "unknown"

    if signals.is_coding_prompt(text):
        return None
    trivial = signals.is_trivial(text)
    answer = signals.is_acceptance(text) or signals.is_decline(text) or signals.is_misfit(text)
    if trivial and not answer:
        return None

    state = store.load_state()
    if not state["settings"].get("enabled", True):
        return None

    if trivial or (answer and len(signals.words(text)) <= 6):
        # A bare "yes" / "no thanks" / "that doesn't apply": an answer to the coach, not work to score.
        session = state["sessions"].get(sid)
        if not session or not session.get("offer"):
            return None
        followup = _take_offer(state, session, text, ts)
        lines = game.toast_lines(0, None, game.check_achievements(state, ts), state["level"]) if followup else []
        store.save_state(state)
        if not followup:
            return None
        return _output(lines, followup, "UserPromptSubmit", delivery or delivery_mode(state["settings"]))

    if _already_handled(state, text, ts, source):
        store.save_state(state)
        return None

    session = _session(state, sid, ts)
    session["coached_this_turn"] = False
    followup = _take_offer(state, session, text, ts)
    _expire_pending(state, session, ts)

    pending_gid = session.get("pending_gen")
    gen = _gen_by_id(state, pending_gid) if pending_gid else None
    analysis = signals.analyze_prompt(text, session["prompts"], gen is not None and not gen.get("resolved"))
    session["prompts"] += 1

    # -- iteration bookkeeping -----------------------------------------------------------
    if gen is not None and not gen.get("resolved"):
        if analysis["kind"] == "refine":
            gen["revisions"] += 1
            if analysis.get("vague_refine"):
                gen["vague_revs"] = gen.get("vague_revs", 0) + 1
            state["totals"]["revisions"] += 1
            store.append_event({"type": "revision", "gen": gen["id"], "ts": ts,
                                "vague": bool(analysis.get("vague_refine"))})
            if gen["revisions"] >= GEN_REFINE_CREDIT_MAX:
                _resolve_gen(state, gen, ts, accepted_first_draft=False)
                session["pending_gen"] = None
        else:
            # Moved on to something else: the first draft was accepted as-is (or
            # revised fewer times than the full-credit threshold).
            _resolve_gen(state, gen, ts, accepted_first_draft=gen["revisions"] == 0)
            session["pending_gen"] = None

    # -- record the prompt event (signals only; never the text) -------------------------
    event = {"type": "prompt", "ts": ts, "day": store.day_of(ts), "session": sid[:8],
             "kind": analysis["kind"], "words": analysis["words"],
             "context": analysis["context"], "precision": analysis["precision"],
             "verify": analysis["verify"], "feature": analysis["feature"],
             "sensitive": analysis["sensitive"], "triggers": analysis["triggers"]}
    store.append_event(event)

    totals = state["totals"]
    totals["prompts"] += 1
    if analysis["kind"] == "new" and analysis["context"] >= 0.7:
        totals["rich_prompts"] += 1
    if analysis["verify"]:
        totals["verifies"] += 1
    if analysis["sensitive"]:
        totals["sensitive"] += 1
    state["xp"] += game.xp_for_prompt(analysis)

    streak_grew = game.touch_streak(state, ts) if game.is_good_habit(analysis) else None

    # -- level (rolling window, can go down) ---------------------------------------------
    events = store.read_events(tail_bytes=store.RECENT_BYTES)
    metrics = scoring.compute_metrics(events, state["gens"])
    old_level = state["level"]
    level = scoring.resolve_level(metrics, old_level)
    state["level"] = level
    if level > old_level:
        game.level_up_achievement(state, level, ts)
    new_achievements = game.check_achievements(state, ts)

    # -- coaching decision -----------------------------------------------------------------
    coach = state["coach"]
    # An urgent tip is said once per conversation; repeating it every other message is nagging.
    said_once = set(session.get("urgent_shown", []))
    urgent = lessons.urgent_hit(analysis["triggers"], level, blocked=said_once)
    if followup:
        should, reason = False, "followup"   # they're acting on the last offer; don't stack a new one
    else:
        should, reason = cadence.decide(state, analysis, level, ts, urgent=urgent is not None)
    context = followup
    lesson = None
    if should:
        skill = urgent["skill"] if reason == "urgent" else \
            choose_skill(reason, analysis, metrics, level, coach["last_focus"])
        recent_ids = [l["id"] for l in coach["lessons"]]
        muted = {i for i, until in coach["muted"].items() if until > ts} | said_once
        lesson, alternatives, detected = lessons.choose(skill, level, analysis["triggers"], recent_ids,
                                                        coach["last_focus"], blocked=muted)
    if (lesson is not None and not detected and reason != "safety" and analysis["kind"] != "new"
            and not analysis.get("vague_refine")):
        lesson = None   # generic tips only go with new requests, never mid-edit
    matched = sorted(set(lesson["detect"]) & set(analysis["triggers"])) if lesson else []
    held_out = lesson is not None and _in_holdout(state, lesson, reason, detected, matched)
    if held_out:
        # Pilot experiment: a random share of detected moments get no coaching, so the
        # coached ones can be compared against them. Timed exactly like a real moment.
        coach["prompts_since"] = 0
        coach["last_ts"] = ts
        coach["lessons"].append({"id": lesson["id"], "ts": ts})
        store.append_event({"type": "coach_holdout", "ts": ts, "lesson": lesson["id"],
                            "skill": lesson["skill"], "triggers": matched})
        lesson, should = None, False
    if lesson is not None:
        question = lessons.question_for(lesson, totals["coached"])
        note = lessons.personal_note(lesson["skill"], metrics, state["gens"])
        context = lessons.coach_instruction(lesson, question, reason, game.level_name(level), note,
                                            alternatives, detected)
        coach["prompts_since"] = 0
        coach["last_ts"] = ts
        coach["last_focus"] = lesson["skill"]
        coach["lessons"].append({"id": lesson["id"], "ts": ts})
        totals["coached"] += 1
        session["coached_this_turn"] = True
        session["offer"] = {"ids": [lesson["id"]] + [a["id"] for a in alternatives], "ts": ts}
        coach["last_moment"] = {"id": lesson["id"], "ts": ts, "triggers": matched, "reason": reason}
        if lesson["urgent"]:
            session.setdefault("urgent_shown", []).append(lesson["id"])
        store.append_event({"type": "coach", "ts": ts, "reason": reason, "lesson": lesson["id"],
                            "skill": lesson["skill"], "detected": detected, "triggers": matched})
    else:
        should = False
        if not held_out:
            coach["prompts_since"] += 1

    lines = game.toast_lines(level - old_level, streak_grew, new_achievements, level)
    if analysis["sensitive"] and should:
        lines.insert(0, "Heads up: that message looks like it includes sensitive information.")
        lines = lines[:2]

    store.save_state(state)
    if streak_grew or level != old_level or new_achievements:
        refresh_saved_pages()
    return _output(lines, context, "UserPromptSubmit", delivery or delivery_mode(state["settings"]))


# --- PostToolUse ----------------------------------------------------------------------------

_WRITES = re.compile(
    r"(\.save\(|\bsave\b|\bwrite\b|\bexport\b|\bconvert\b|pandoc|soffice|libreoffice|"
    r"\s-o\s|--output|>\s*\S|\bbuild\b|\bcreate\b|\bgenerate\b|\brender\b|\bcp\b|\bmv\b)", re.I)
_DOC_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash")


def _is_scratch_text(path):
    """A text-type file (.md/.txt/.html) Claude wrote in a temp or scratchpad folder is its
    own working note (a commit message, a draft plan), not a document the user asked for."""
    if os.path.splitext(path or "")[1].lower() not in signals.SOFT_DOC_EXTS:
        return False
    full = os.path.normcase(os.path.abspath(path))
    parts = full.replace("\\", "/").split("/")
    if "scratchpad" in parts or ".claude" in parts:     # .claude: Claude's own memory and settings notes
        return True
    temps = {tempfile.gettempdir(), os.environ.get("TEMP", ""), os.environ.get("TMP", ""), "/tmp"}
    for t in temps:
        if t:
            root = os.path.normcase(os.path.abspath(t))
            if full.startswith(root.rstrip("\\/") + os.sep):
                return True
    return False


def _candidate_docs(payload):
    """(path, kind) for documents the tool call produced or changed."""
    name = payload.get("tool_name") or ""
    tin = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    out = []
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = tin.get("file_path") or tin.get("notebook_path") or ""
        content = tin.get("content") or tin.get("new_string") or ""
        kind = signals.doc_kind_for_path(path, soft_min_chars=1500, content_len=len(content)) \
            if name == "Write" else signals.doc_kind_for_path(path)
        if kind and not _is_scratch_text(path):
            out.append((path, kind))
    elif name == "Bash":
        command = tin.get("command") or ""
        # Only commands that plausibly *write* a document (a script that saves a
        # .pptx, pandoc/soffice conversions, redirects), not ones that just read one.
        if not _WRITES.search(command):
            return out
        for p in signals.doc_paths_in_command(command):
            full = p if os.path.isabs(p) else os.path.join(cwd, p)
            try:
                fresh = (store.now() - os.path.getmtime(full)) < 180
            except OSError:
                fresh = False
            kind = signals.doc_kind_for_path(p)
            if kind and fresh:
                out.append((full, kind))
    return out


def handle_tool(payload, delivery=None):
    if (payload.get("tool_name") or "") not in _DOC_TOOLS:
        return None
    docs = _candidate_docs(payload)
    if not docs:
        return None
    path, kind = docs[0]
    return document_flow(payload.get("session_id") or "unknown", path, kind)


DOC_KINDS = {"deck": "deck", "slides": "deck", "presentation": "deck", "powerpoint": "deck",
             "document": "document", "doc": "document", "report": "document", "memo": "document", "letter": "document",
             "pdf": "PDF", "spreadsheet": "spreadsheet", "sheet": "spreadsheet", "excel": "spreadsheet",
             "page": "page", "html": "page", "text": "document"}


def handle_document(payload):
    """A document was produced by some route that has no file hook (chat artifacts,
    files made through connectors...). payload: {session_id, name, kind}."""
    kind = DOC_KINDS.get(str(payload.get("kind") or "document").strip().lower(), "document")
    name = str(payload.get("name") or kind)
    return document_flow(payload.get("session_id") or "unknown", name, kind)


def document_flow(sid, path, kind):
    ts = store.now()
    state = store.load_state()
    if not state["settings"].get("enabled", True):
        return None
    session = _session(state, sid, ts)
    key = _path_key(path)

    # A draft is awaiting feedback and the user just asked for a revision: this
    # write is the revised version (possibly saved under a new filename), so it
    # belongs to the same lineage rather than starting a new draft.
    pending = _gen_by_id(state, session.get("pending_gen")) if session.get("pending_gen") else None
    if pending is not None and not pending.get("resolved") and pending["revisions"] >= 1:
        context = None
        if (not cadence.is_paused(state["settings"], ts) and pending["revisions"] == 1
                and ts - session.get("last_nudge_ts", 0) > NUDGE_COOLDOWN_SECONDS):
            context = lessons.revision_nudge_instruction(pending["kind"])
            session["last_nudge_ts"] = ts
            session.pop("offer", None)   # this question replaces the coach's offer in the reply
            store.append_event({"type": "nudge", "gen": pending["id"], "ts": ts, "second_pass": True})
        store.save_state(state)
        return _output(None, context, "PostToolUse")

    existing = None
    for g in reversed(state["gens"]):
        if g["key"] == key and ts - g["ts"] < 6 * 3600 and g.get("session") == sid[:8]:
            existing = g
            break

    if existing is not None:
        # Same document being rewritten (a revision in progress): no new draft.
        store.save_state(state)
        return None

    gid = "g%d" % int(ts * 1000)
    gen = {"id": gid, "key": key, "kind": kind, "ts": ts, "revisions": 0, "vague_revs": 0,
           "resolved": False, "session": sid[:8]}
    state["gens"].append(gen)
    state["totals"]["docs"] += 1
    session["pending_gen"] = gid
    store.append_event({"type": "gen", "gen": gid, "kind": kind, "ts": ts})

    context = None
    if not cadence.is_paused(state["settings"], ts) and ts - session.get("last_nudge_ts", 0) > NUDGE_COOLDOWN_SECONDS:
        name = os.path.basename(path) or kind
        context = lessons.draft_nudge_instruction(kind, name)
        session["last_nudge_ts"] = ts
        session.pop("offer", None)       # this question replaces the coach's offer in the reply
        state["coach"]["prompts_since"] = 0
        state["coach"]["last_ts"] = ts
        state["totals"]["coached"] += 1
        store.append_event({"type": "nudge", "gen": gid, "ts": ts})
    store.save_state(state)
    return _output(None, context, "PostToolUse")
