"""The recommendation library: coach/library/recommendations.md.

Each entry is one best practice in three parts: *when* (what the user is doing
that triggers it), *recommend* (what the coach offers) and *action* (what the AI
does if the user takes the offer). The file is plain Markdown so anyone can add
to it; this module parses and checks it. See the file's header for the format.
"""

import os
import re

SKILLS = ("context", "iteration", "precision", "verification", "feature", "safety", "advanced")
REQUIRED = ("title", "skill", "when", "recommend", "action")
KNOWN_FIELDS = set(REQUIRED) | {"detect", "levels", "why", "urgent", "sources", "stage"}
SPECIAL_DETECT = ("ai", "general")

_FIELD = re.compile(r"^\s*[-*]\s+([A-Za-z_]+)\s*:\s*(.*)$")
_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def default_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "library", "recommendations.md")


def parse(text):
    """Return (entries, problems). Entries are dicts; problems are human-readable
    strings naming the entry. A broken entry is dropped, never fatal."""
    entries, problems = [], []
    stage, cur = "", None

    def finish(raw):
        if raw is None or not raw["fields"]:
            return   # a heading with no "- field:" lines is just notes
        entry, bad = _build(raw)
        problems.extend("%s: %s" % (raw["id"], b) for b in bad)
        if entry is not None:
            entries.append(entry)

    for line in (text or "").splitlines():
        if line.startswith("# "):
            finish(cur)
            cur = None
            stage = line[2:].strip()
        elif line.startswith("## "):
            finish(cur)
            cur = {"id": line[3:].strip(), "stage": stage, "fields": [], "line": line}
        elif cur is not None:
            m = _FIELD.match(line)
            if m:
                cur["fields"].append((m.group(1).lower(), m.group(2).strip()))
    finish(cur)

    seen = set()
    for e in list(entries):
        if e["id"] in seen:
            problems.append("%s: the id is used more than once (only the first is kept)" % e["id"])
            entries.remove(e)
        seen.add(e["id"])
    return entries, problems


def _levels(value):
    m = re.match(r"^\s*([1-4])\s*(?:-\s*([1-4]))?\s*$", value or "1-4")
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2) or lo)
    return (lo, hi) if lo <= hi else None


def _build(raw):
    fields, bad = {}, []
    recs = []
    for key, value in raw["fields"]:
        if key not in KNOWN_FIELDS:
            bad.append("unknown field '%s' (ignored)" % key)
            continue
        if key == "recommend":
            if value:
                recs.append(value)
        else:
            fields[key] = value
    if not _ID.match(raw["id"]):
        bad.append("the id should be lowercase words joined by dashes")
    missing = [k for k in REQUIRED if not (recs if k == "recommend" else fields.get(k))]
    if missing:
        bad.append("missing %s (entry skipped)" % ", ".join(missing))
        return None, bad
    skill = fields["skill"].lower()
    if skill not in SKILLS:
        bad.append("skill '%s' is not one of %s (entry skipped)" % (skill, ", ".join(SKILLS)))
        return None, bad
    levels = _levels(fields.get("levels"))
    if levels is None:
        bad.append("levels '%s' should look like 1-4 (using 1-4)" % fields.get("levels"))
        levels = (1, 4)
    detect = [d.strip().lower() for d in re.split(r"[,\s]+", fields.get("detect") or "ai") if d.strip()]
    entry = {
        "id": raw["id"],
        "title": fields["title"],
        "skill": skill,
        "stage": fields.get("stage") or raw["stage"],
        "levels": levels,
        "detect": detect or ["ai"],
        "when": fields["when"],
        "why": fields.get("why", ""),
        "recommend": recs,
        "questions": recs,          # older name, kept for callers that still use it
        "action": fields["action"],
        "urgent": (fields.get("urgent", "").lower() in ("yes", "true", "1")),
        "sources": (fields.get("sources") or "").split(),
    }
    return entry, bad


def _read(path):
    """(text, problem). Accepts UTF-8 with or without a byte-order mark; a file saved
    as Windows "ANSI" (Notepad's old default) is read anyway and flagged."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), ("the file isn't saved as UTF-8; it was read as Windows text, "
                                                        "but please re-save it as UTF-8")


_cache = {"key": None, "entries": [], "problems": []}


def load(path=None):
    """Entries from the library file, re-read whenever the file changes. A
    missing or unreadable file yields an empty library (coaching goes quiet
    rather than breaking the user's session)."""
    path = path or default_path()
    try:
        st = os.stat(path)
        key = (path, st.st_mtime, st.st_size)
    except OSError:
        return []
    if _cache["key"] != key:
        try:
            text, _problem = _read(path)
        except OSError:
            return []
        entries, problems = parse(text)
        _cache.update(key=key, entries=entries, problems=problems)
    return _cache["entries"]


def check(path=None, detectors=()):
    """(entries, problems) for the `coach.py library` command, including
    detector names that don't exist."""
    path = path or default_path()
    try:
        text, encoding_problem = _read(path)
    except OSError as exc:
        return [], ["cannot read %s (%s)" % (path, exc)]
    entries, problems = parse(text)
    if encoding_problem:
        problems.insert(0, encoding_problem)
    known = set(detectors) | set(SPECIAL_DETECT)
    for e in entries:
        for d in e["detect"]:
            if d not in known:
                problems.append("%s: unknown detector '%s' (it will never fire)" % (e["id"], d))
    return entries, problems
