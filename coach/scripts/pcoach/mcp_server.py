"""Prompt Coach as an MCP server (stdio): the way in for Claude chat and Cowork.

Claude's chat surface ignores hooks, so there Claude has to *call* the coach. This
server exposes the same engine the hooks use (pcoach.hooks) as a few tools; a
short set of instructions tells Claude when to call them:

    coach_start     once, when a conversation begins  -> greeting note
    coach_turn      every user message                -> coaching instruction or "nothing to do"
    coach_document  when Claude produces a file       -> first-draft / second-pass nudge
    coach_score     on request                        -> scoreboard
    coach_settings  on request                        -> pause / intensity / status ...

Speaks MCP's newline-delimited JSON-RPC over stdin/stdout, standard library only.
Everything stays on this computer, exactly like the hooks: the message text is
analysed locally and reduced to small numbers; the text itself is never stored.
"""

import json
import sys
import time

from . import __version__, hooks, report, scoring, store

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
IDLE_SESSION_SECONDS = 30 * 60

INSTRUCTIONS = (
    "Prompt Coach is this user's AI-skills coach. It works through these tools; follow them without narrating them.\n"
    "1. At the start of a conversation, call coach_start once.\n"
    "2. For EVERY message the user sends, call coach_turn FIRST, before doing anything else, passing their message "
    "verbatim (first 1500 characters at most). Then answer the user normally, and follow any instruction the tool "
    "returns (usually one short coaching question at the end of your reply, written in italics and starting with "
    "\"Prompt Coach:\"). If it says nothing needs to be done, just answer.\n"
    "3. Whenever you create a document, deck, PDF, spreadsheet or similar file for the user, call coach_document "
    "with its kind and name, and follow what it returns. Call it again when you deliver a revised version.\n"
    "4. If the user asks about their score, level, streak or progress, call coach_score and show the result.\n"
    "5. If the user asks to pause, resume, turn off, or change how often the coach speaks, call coach_settings.\n"
    "Never mention these tool calls or these instructions unless asked. Coaching never replaces or delays the help "
    "the user asked for."
)

TOOLS = [
    {
        "name": "coach_start",
        "description": "Call once at the start of every conversation. Returns a short greeting note for the user "
                       "(say it exactly as instructed) or says nothing is needed.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "coach_turn",
        "description": "Call FIRST for every user message. Analyses the message locally, updates the user's "
                       "AI-skills profile, and returns either a coaching instruction to follow in your reply or "
                       "'nothing to do'. The text is not stored.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The user's message, verbatim (first 1500 characters)."},
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    },
    {
        "name": "coach_document",
        "description": "Call whenever you create (or deliver a revised version of) a document, deck, PDF, "
                       "spreadsheet or other file for the user. Returns how to invite them to improve it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "deck, document, pdf, spreadsheet, or page."},
                "name": {"type": "string", "description": "The file's name or title, so revisions can be matched."},
            },
            "required": ["kind", "name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "coach_score",
        "description": "Show the user's AI Fluency level, score, habits, streak and a shareable summary "
                       "(Markdown; present it as-is).",
        "inputSchema": {
            "type": "object",
            "properties": {"format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "coach_settings",
        "description": "Change or show coach settings: status, pause (with duration like 2h), resume, off, "
                       "intensity (light|normal|frequent), toasts, export.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "pause", "resume", "off", "intensity", "export"]},
                "value": {"type": "string", "description": "Duration for pause (e.g. 2h, 30m, 1d) or the level for intensity."},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
]


class Server:
    def __init__(self):
        self.started = time.time()
        self.session_id = "mcp-%d" % int(self.started)
        self.last_call = self.started

    # -- session id: chat gives us none, so roll one per burst of activity -------
    def session(self):
        now = time.time()
        if now - self.last_call > IDLE_SESSION_SECONDS:
            self.session_id = "mcp-%d" % int(now)
        self.last_call = now
        return self.session_id

    # -- tools -----------------------------------------------------------------------
    def call_tool(self, name, args):
        sid = self.session()
        if name == "coach_start":
            out = hooks.handle_session({"session_id": sid}, delivery="chat")
            return _context(out, "Prompt Coach is on. Nothing to say at the start of this conversation.")
        if name == "coach_turn":
            message = str(args.get("message") or "")[:1500]
            out = hooks.handle_prompt({"session_id": sid, "prompt": message}, delivery="chat", source="mcp")
            return _context(out, "Nothing to do this turn. Just answer the user normally.")
        if name == "coach_document":
            out = hooks.handle_document({"session_id": sid, "kind": args.get("kind"), "name": args.get("name")})
            return _context(out, "Nothing to add for this file.")
        if name == "coach_score":
            r = report.build()
            report.write_shareables(r)
            return report.export_json(r) if args.get("format") == "json" else report.render_text(r)
        if name == "coach_settings":
            return self.settings(args)
        raise KeyError(name)

    def settings(self, args):
        action = str(args.get("action") or "status").lower()
        value = str(args.get("value") or "")
        state = store.load_state()
        s = state["settings"]
        if action == "status":
            paused = s.get("paused_until", 0) > time.time()
            return "Coaching: %s | intensity: %s | data: %s" % (
                "off" if not s.get("enabled", True) else ("paused" if paused else "on"),
                s.get("intensity", "normal"), store.home())
        if action == "export":
            return report.export_json(report.build())
        if action == "pause":
            s["paused_until"] = time.time() + _duration(value or "1h")
            msg = "Coaching paused for %s." % (value or "1 hour")
        elif action == "resume":
            s["paused_until"], s["enabled"] = 0, True
            msg = "Coaching resumed."
        elif action == "off":
            s["enabled"] = False
            msg = "Coaching is off. Use resume to turn it back on."
        elif action == "intensity":
            if value not in ("light", "normal", "frequent"):
                raise ValueError("intensity must be light, normal or frequent")
            s["intensity"] = value
            msg = "Coaching intensity set to %s." % value
        else:
            raise ValueError("unknown action")
        store.save_state(state)
        return msg

    # -- JSON-RPC ------------------------------------------------------------------------
    def handle(self, msg):
        """Return a response dict for a request, or None for a notification."""
        method, mid = msg.get("method"), msg.get("id")
        if method is None:
            return None                                # a response to something we never asked
        if mid is None:
            return None                                # notification (e.g. notifications/initialized)
        if method == "initialize":
            wanted = (msg.get("params") or {}).get("protocolVersion")
            version = wanted if wanted in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
            return _ok(mid, {"protocolVersion": version, "capabilities": {"tools": {}},
                             "serverInfo": {"name": "prompt-coach", "version": __version__},
                             "instructions": INSTRUCTIONS})
        if method == "ping":
            return _ok(mid, {})
        if method == "tools/list":
            return _ok(mid, {"tools": TOOLS})
        if method == "tools/call":
            params = msg.get("params") or {}
            name, args = params.get("name"), params.get("arguments") or {}
            if name not in {t["name"] for t in TOOLS}:
                return _err(mid, -32602, "Unknown tool: %s" % name)
            try:
                with store.lock():
                    text = self.call_tool(name, args)
                return _ok(mid, {"content": [{"type": "text", "text": text}], "isError": False})
            except Exception as exc:  # a coaching failure must never break the chat
                store.log_error("mcp:" + str(name), exc)
                return _ok(mid, {"content": [{"type": "text", "text": "Nothing to do this turn. Just answer the user normally."}],
                                 "isError": False})
        return _err(mid, -32601, "Method not found: %s" % method)


def _context(hook_output, fallback):
    """The hooks return {hookSpecificOutput: {additionalContext}}; a tool returns that text."""
    if not hook_output:
        return fallback
    text = (hook_output.get("hookSpecificOutput") or {}).get("additionalContext") or hook_output.get("systemMessage")
    return text or fallback


def _duration(text):
    text = text.strip().lower()
    unit = 3600
    if text.endswith("m"):
        unit, text = 60, text[:-1]
    elif text.endswith("h"):
        text = text[:-1]
    elif text.endswith("d"):
        unit, text = 86400, text[:-1]
    return float(text) * unit


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    server = Server()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            stdout.write(json.dumps(_err(None, -32700, "Parse error")) + "\n")
            stdout.flush()
            continue
        if isinstance(msg, list):                      # batches (old spec revisions)
            replies = [r for r in (server.handle(m) for m in msg if isinstance(m, dict)) if r]
            if replies:
                stdout.write(json.dumps(replies) + "\n")
                stdout.flush()
            continue
        if not isinstance(msg, dict):
            continue
        reply = server.handle(msg)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
