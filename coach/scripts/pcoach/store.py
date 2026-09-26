"""Local storage for Prompt Coach: one small state file + an append-only event log.

Everything lives in ~/.prompt-coach (override with PROMPT_COACH_HOME). Nothing
here ever stores prompt text: only counts, small scores, file *kinds*, and
filenames of documents the AI generated (for de-duplication).

Writes are atomic (temp file + os.replace) so a crash or two hooks racing
cannot leave a half-written state file.
"""

import json
import os
import tempfile
import time

VERSION = 1
MAX_EVENT_DAYS = 180
MAX_GENS = 40
MAX_SESSIONS = 25


def home():
    return os.environ.get("PROMPT_COACH_HOME") or os.path.join(os.path.expanduser("~"), ".prompt-coach")


def _path(name):
    return os.path.join(home(), name)


def now():
    return time.time()


def day_of(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def default_state():
    t = now()
    return {
        "version": VERSION,
        "created": t,
        "settings": {"enabled": True, "intensity": "normal", "paused_until": 0, "toasts": "auto"},
        "xp": 0,
        "level": 1,
        "streak": {"count": 0, "best": 0, "last_day": ""},
        "achievements": {},
        "toasts": [],
        "coach": {"prompts_since": 0, "last_ts": 0, "lessons": [], "last_focus": ""},
        "gens": [],
        "sessions": {},
        "recent": [],
        "totals": {"prompts": 0, "coached": 0, "revisions": 0, "first_drafts_accepted": 0,
                   "rich_prompts": 0, "verifies": 0, "sensitive": 0, "docs": 0},
    }


def _merge_defaults(state, defaults):
    for key, value in defaults.items():
        if key not in state:
            state[key] = value
        elif isinstance(value, dict) and isinstance(state[key], dict):
            _merge_defaults(state[key], value)
    return state


def _read_text(path):
    for attempt in range(4):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_state():
    try:
        state = json.loads(_read_text(_path("state.json")))
        if not isinstance(state, dict):
            raise ValueError("state is not an object")
        return _merge_defaults(state, default_state())
    except (OSError, ValueError):
        return default_state()


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        for attempt in range(6):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                # Windows: the target may be open in another process for a moment.
                if attempt == 5:
                    raise
                time.sleep(0.02 * (attempt + 1))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_state(state):
    # Bound the growth of the lists so the file stays tiny.
    state["gens"] = state["gens"][-MAX_GENS:]
    if len(state["sessions"]) > MAX_SESSIONS:
        keep = sorted(state["sessions"].items(), key=lambda kv: kv[1].get("last_ts", 0))[-MAX_SESSIONS:]
        state["sessions"] = dict(keep)
    state["coach"]["lessons"] = state["coach"]["lessons"][-40:]
    _atomic_write(_path("state.json"), json.dumps(state, indent=1, sort_keys=True))


def append_event(event):
    event = dict(event)
    event.setdefault("ts", now())
    os.makedirs(home(), exist_ok=True)
    with open(_path("events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def read_events(since_ts=0, tail_bytes=None):
    """Events at or after since_ts. With tail_bytes, only the end of the file is
    read (scoring only needs the most recent activity), which keeps every hook
    fast however long the history grows."""
    out = []
    try:
        with open(_path("events.jsonl"), "rb") as f:
            if tail_bytes:
                size = f.seek(0, os.SEEK_END)
                if size > tail_bytes:
                    f.seek(size - tail_bytes)
                    f.readline()          # drop the partial line we landed in
                else:
                    f.seek(0)
            else:
                f.seek(0)
            for raw in f:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("ts", 0) >= since_ts:
                    out.append(ev)
    except OSError:
        pass
    return out


RECENT_BYTES = 400_000


def prune_events(max_days=MAX_EVENT_DAYS):
    """Drop events older than max_days. Cheap: only rewrites when needed."""
    path = _path("events.jsonl")
    try:
        if os.path.getsize(path) < 200_000:
            return
    except OSError:
        return
    cutoff = now() - max_days * 86400
    keep = read_events(cutoff)
    _atomic_write(path, "".join(json.dumps(e, sort_keys=True) + "\n" for e in keep))


class lock:
    """Tiny cross-process lock (exclusive create of a lock file) so two Claude
    sessions updating the profile at once don't lose each other's writes.
    Waits briefly, and breaks a stale lock left by a crashed process."""

    def __init__(self, timeout=3.0, stale=10.0):
        self.timeout, self.stale = timeout, stale
        self.path = _path(".lock")
        self.held = False

    def __enter__(self):
        os.makedirs(home(), exist_ok=True)
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                self.held = True
                return self
            except (FileExistsError, PermissionError):
                # PermissionError: on Windows a lock file that is mid-delete refuses to open.
                try:
                    if time.time() - os.path.getmtime(self.path) > self.stale:
                        os.unlink(self.path)
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    return self          # give up waiting; proceed unlocked rather than block the session
                time.sleep(0.03)

    def __exit__(self, *exc):
        if self.held:
            try:
                os.unlink(self.path)
            except OSError:
                pass
        return False


def log_error(where, exc):
    try:
        os.makedirs(home(), exist_ok=True)
        with open(_path("errors.log"), "a", encoding="utf-8") as f:
            f.write("%s [%s] %r\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), where, exc))
    except OSError:
        pass


def reset():
    for name in ("state.json", "events.jsonl", "summary.md", "badge.svg"):
        try:
            os.unlink(_path(name))
        except OSError:
            pass
