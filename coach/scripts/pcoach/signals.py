"""Signal detection: what does one prompt reveal about how someone uses AI?

Pure functions, standard library only, no I/O. Everything here is a heuristic
and is documented as one: we score *habits* (did you say who it's for? did you
revise the draft?), not whether the prompt is "good" in some absolute sense.

Privacy: these functions read prompt text but return only small numbers and
flags. Callers must never persist the text itself.
"""

import os
import re

WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


def words(text):
    return WORD_RE.findall(text or "")


def _any(patterns, text):
    return sum(1 for p in patterns if re.search(p, text, re.I))


# --- cue lists ---------------------------------------------------------------
# Each entry is one *kind* of context, so a prompt is credited for covering
# different angles rather than for repeating one word.

PURPOSE_CUES = [
    r"\bgoal\b", r"\bpurpose\b", r"\bso (that|i can|we can|they can)\b",
    r"\bin order to\b", r"\bi need (it|this|to)\b", r"\bi want (it|this|to)\b",
    r"\bto (persuade|convince|explain|teach|summari[sz]e|impress|inform|decide|"
    r"pitch|announce|apply|justify|negotiate)\b",
    r"\bbecause\b", r"\bthe point\b",
]
AUDIENCE_CUES = [
    r"\baudience\b", r"\bfor (my|our|a|an|the) (boss|manager|team|client|customer|"
    r"class|professor|students?|board|investors?|parents?|kids?|executives?|"
    r"leadership|committee|readers?|audience|staff|department|recruiter|hiring)\b",
    r"\bwho (will|is going to|is)\b.{0,30}\b(read|see|use|present)\b",
    r"\b(they|readers?|the audience) (need|want|will|already|don'?t)\b",
    r"\bnon-?technical\b", r"\bbeginners?\b", r"\bexperts?\b",
    r"\bfor (a|an) [a-z]+ (audience|meeting|presentation|room|crowd)\b",
]
SITUATION_CUES = [
    r"\bi(?:'m| am) (a|an|the|working|trying|preparing|writing|planning|leading|"
    r"applying|new|in charge)\b",
    r"\bwe(?:'re| are) (a|an|the|working|trying|preparing|planning|launching)\b",
    r"\bmy (role|job|company|team|project|situation|class|business|department)\b",
    r"\bat (my|our) (company|job|work|school|firm|org)\b",
    r"\bcurrently\b", r"\bright now\b", r"\bwe (have|need|are)\b",
]
BACKGROUND_CUES = [
    r"\bbackground\b", r"\bcontext\b", r"\bhere(?:'s| is| are) (the|some|my|our)\b",
    r"\bfor example\b", r"\bfor instance\b", r"\bsuch as\b", r"\blast (quarter|year|"
    r"month|week)\b", r"\battached\b", r"\bbelow\b", r"\bpreviously\b", r"\bso far\b",
    r"\bthe (data|numbers|notes|report|draft|email|thread|meeting) (say|show|says|"
    r"shows|is|are)\b",
]

FORMAT_CUES = [
    r"\bbullets?\b", r"\btable\b", r"\bslides?\b", r"\boutline\b", r"\bparagraphs?\b",
    r"\bsentences?\b", r"\bmemo\b", r"\bone[- ]page(r)?\b", r"\bformat\b", r"\bheadings?\b",
    r"\bsections?\b", r"\bcsv\b", r"\bjson\b", r"\bchecklist\b", r"\btemplate\b",
    r"\bstep[- ]by[- ]step\b", r"\bshort\b", r"\bconcise\b", r"\bbrief\b",
]
TONE_CUES = [
    r"\btone\b", r"\bformal\b", r"\bcasual\b", r"\bfriendly\b", r"\bprofessional\b",
    r"\bwarm\b", r"\bconfident\b", r"\bplain (english|language)\b", r"\bpersuasive\b",
    r"\bin the style of\b", r"\bvoice\b",
]
CONSTRAINT_CUES = [
    r"\bdon'?t\b", r"\bdo not\b", r"\bavoid\b", r"\bwithout\b", r"\bmust\b",
    r"\bonly\b", r"\bat (most|least)\b", r"\bno more than\b", r"\blimit\b",
    r"\bunder \d", r"\bbetween \d", r"\bdeadline\b", r"\bmax(imum)?\b", r"\bmin(imum)?\b",
]
NUMERIC_SPEC = re.compile(
    r"\b\d+\s*(-|to)?\s*\d*\s*(words?|slides?|bullets?|pages?|minutes?|mins?|"
    r"sentences?|paragraphs?|items?|points?|lines?|sections?|examples?|options?)\b", re.I)

VERIFY_CUES = [
    r"\bsources?\b", r"\bcite\b", r"\bcitations?\b", r"\bdouble[- ]?check\b",
    r"\bverify\b", r"\bfact[- ]?check\b", r"\bhow sure\b", r"\bconfidence\b",
    r"\bif you(?:'re| are) not sure\b", r"\bdon'?t make (anything )?up\b",
    r"\bdo not make (anything )?up\b", r"\bsay (so )?if you don'?t know\b",
    r"\bevidence\b", r"\bwhat could be wrong\b", r"\bpoke holes\b", r"\bcritique\b",
    r"\bwhat am i missing\b", r"\bpush back\b", r"\bdevil'?s advocate\b",
]

# --- refinement / follow-up detection ----------------------------------------

REFINE_CUES = [
    r"\b(change|shorter|longer|shorten|lengthen|tighten|expand|revise|update|fix|"
    r"adjust|swap|replace|rework|redo|simplify|polish|improve|edit|trim|cut|"
    r"rephrase|reword|reorder|rearrange|punch(ier| up)|soften|strengthen)\b",
    r"\bmake (it|this|that|the|them)\b", r"\b(more|less|too|bit more|bit less)\b",
    r"\binstead\b", r"\b(slide|page|section|paragraph|bullet|heading|title|intro|"
    r"conclusion|opening|ending|table|chart)\s*\d*\b",
    r"\b(add|remove|drop|include|mention)\b", r"\bnot quite\b", r"\bgood but\b",
    r"\bcan you (also|change|make|add|remove|tweak)\b", r"\btweak\b",
]
NEW_TASK_START = re.compile(
    r"^\s*(now |next |ok(ay)?,? |ok now )?(write|create|make me|draft|build|generate|"
    r"prepare|design|help me (write|create|plan|draft|build)|i need (a|an|you to) "
    r"(write|create|draft|build|make))\b", re.I)
REFERS_BACK = re.compile(
    r"\b(it|this|that|these|those|the (doc|document|deck|slides?|presentation|"
    r"pdf|report|memo|draft|file|spreadsheet|email|letter|summary))\b", re.I)
FOLLOWUP_START = re.compile(
    r"^\s*(also|and|then|now|ok(ay)?|yes|yeah|no|thanks|thank you|great|good|nice|"
    r"perfect|actually|wait|hmm|but|can you (also|now)|what about|how about)\b", re.I)
VAGUE_REFINE = re.compile(
    r"^\s*(make it better|improve it|improve this|fix it|better|try again|redo( it)?|"
    r"again|do it again|make it good|make it nicer|polish it|more)\W*$", re.I)

# --- feature use ---------------------------------------------------------------

FILE_REF = re.compile(
    r"(@[\w./\\-]+|\b[\w./\\-]+\.(docx?|pptx?|pdf|xlsx?|csv|md|txt|key|pages)\b|"
    r"\battached\b|\bthe (file|document|deck|spreadsheet|folder)\b|\bmy (doc|document|"
    r"deck|spreadsheet|file|slides)\b)", re.I)
EDIT_IN_PLACE = re.compile(
    r"\b(edit|update|change|revise|fix|add to|adjust)\b.{0,25}\b(the|my|this) "
    r"(file|doc|document|deck|presentation|slides?|spreadsheet|report)\b|\bin place\b", re.I)
PASTE_VERBS = re.compile(
    r"\b(rewrite|edit|proofread|improve|summari[sz]e|fix|shorten|polish|translate|"
    r"critique|review)\b", re.I)

# --- sensitive data ------------------------------------------------------------

SENSITIVE_PATTERNS = {
    "api_key": re.compile(
        r"\b(sk-[A-Za-z0-9_\-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|"
        r"xox[abprs]-[A-Za-z0-9\-]{10,}|AIza[0-9A-Za-z_\-]{30,})"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "password": re.compile(r"\b(password|passwd|pwd)\b\s*(is|:|=)\s*\S+", re.I),
    "confidential_marker": re.compile(
        r"\b(confidential|internal use only|do not distribute|proprietary|under nda|"
        r"attorney[- ]client)\b", re.I),
}
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,16}\b")


def _luhn(number):
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 16:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_sensitive(text):
    """Return a sorted list of category names found. Never returns the matches."""
    found = set()
    for name, pattern in SENSITIVE_PATTERNS.items():
        if pattern.search(text or ""):
            found.add(name)
    for m in CARD_RE.finditer(text or ""):
        if _luhn(m.group(0)):
            found.add("card_number")
            break
    return sorted(found)


# --- scoring one prompt ----------------------------------------------------------

def context_score(text):
    """0..1: did the person give the AI something to work with?

    Rewards length up to ~45 words and *variety* of context (purpose,
    audience, situation, background). Very short prompts are capped low.
    """
    w = len(words(text))
    if w == 0:
        return 0.0
    kinds = sum(1 for group in (PURPOSE_CUES, AUDIENCE_CUES, SITUATION_CUES, BACKGROUND_CUES)
                if _any(group, text) > 0)
    score = min(1.0, w / 45.0) * 0.4 + min(kinds, 3) * 0.2
    if w < 6:
        score = min(score, 0.15)
    return round(min(score, 1.0), 3)


def precision_score(text):
    """0..1: did they say what a good answer looks like (format, tone, limits)?"""
    score = 0.0
    if _any(FORMAT_CUES, text):
        score += 0.45
    if _any(TONE_CUES, text):
        score += 0.2
    if _any(CONSTRAINT_CUES, text):
        score += 0.2
    if NUMERIC_SPEC.search(text or ""):
        score += 0.25
    return round(min(score, 1.0), 3)


def has_verification(text):
    return _any(VERIFY_CUES, text) > 0


def feature_signal(text):
    """+1 uses the right feature (file reference / edit in place), 0 for the
    classic copy-paste-a-wall-of-text habit, None when not applicable."""
    w = len(words(text))
    if EDIT_IN_PLACE.search(text or "") or FILE_REF.search(text or ""):
        return 1.0
    if w > 350 and PASTE_VERBS.search(text or ""):
        return 0.0
    return None


def is_refinement(text):
    """Does this read like a revision of something already produced?"""
    w = len(words(text))
    if w == 0 or w > 90:
        return False
    if NEW_TASK_START.search(text) and not REFERS_BACK.search(text):
        return False
    if VAGUE_REFINE.search(text):
        return True
    return _any(REFINE_CUES, text) > 0


def is_vague_refinement(text):
    if VAGUE_REFINE.search(text or ""):
        return True
    return len(words(text)) <= 3 and not re.search(r"\d", text or "")


def is_trivial(text):
    """Too short/ceremonial to be worth scoring (yes, thanks, ok...)."""
    t = (text or "").strip()
    if not t or t.startswith("/"):
        return True
    if len(words(t)) <= 2 and not is_refinement(t):
        return True
    return False


def classify_kind(text, prompts_in_session, has_pending_gen):
    """'new' | 'followup' | 'refine'."""
    if has_pending_gen and is_refinement(text):
        return "refine"
    if prompts_in_session == 0:
        return "new"
    w = len(words(text))
    if NEW_TASK_START.search(text) and w > 6:
        return "new"
    if w <= 25 or FOLLOWUP_START.search(text):
        return "followup"
    return "new"


def analyze_prompt(text, prompts_in_session=0, has_pending_gen=False):
    kind = classify_kind(text, prompts_in_session, has_pending_gen)
    result = {
        "kind": kind,
        "words": len(words(text)),
        "context": context_score(text),
        "precision": precision_score(text),
        "verify": has_verification(text),
        "feature": feature_signal(text),
        "sensitive": find_sensitive(text),
    }
    if kind == "refine":
        result["vague_refine"] = is_vague_refinement(text)
    return result


# --- documents ---------------------------------------------------------------------

DOC_EXTS = {
    ".docx": "document", ".doc": "document", ".pptx": "deck", ".ppt": "deck",
    ".pdf": "PDF", ".xlsx": "spreadsheet", ".xls": "spreadsheet", ".odt": "document",
    ".odp": "deck", ".ods": "spreadsheet", ".rtf": "document", ".key": "deck",
    ".pages": "document", ".numbers": "spreadsheet",
}
SOFT_DOC_EXTS = {".md": "document", ".html": "page", ".htm": "page", ".txt": "document"}
_EXT_ALT = r"(?:docx?|pptx?|pdf|xlsx?|odt|odp|ods|rtf|key|pages|numbers)"
_QUOTED_DOC = re.compile(r"""["']([^"'
]+?\.""" + _EXT_ALT + r""")["']""", re.I)
_BARE_DOC = re.compile(r"""(?<![\w./\:~-])([\w./\:~-]+?\.""" + _EXT_ALT + r""")(?![\w])""", re.I)


def doc_kind_for_path(path, soft_min_chars=0, content_len=0):
    ext = os.path.splitext(path or "")[1].lower()
    if ext in DOC_EXTS:
        return DOC_EXTS[ext]
    if ext in SOFT_DOC_EXTS and content_len >= soft_min_chars > 0:
        return SOFT_DOC_EXTS[ext]
    return None


def doc_paths_in_command(command):
    """Document filenames mentioned in a shell command (e.g. a script that
    saves a .pptx). Quoted names may contain spaces; bare names may not.
    Returns unique candidates in order of appearance."""
    found, quoted_spans = [], []
    for m in _QUOTED_DOC.finditer(command or ""):
        found.append((m.start(1), m.group(1).strip()))
        quoted_spans.append((m.start(1), m.end(1)))
    for m in _BARE_DOC.finditer(command or ""):
        if any(a <= m.start(1) < b for a, b in quoted_spans):
            continue  # already captured as part of a quoted name with spaces
        found.append((m.start(1), m.group(1).strip()))
    found.sort()
    seen, out = set(), []
    for _pos, p in found:
        if p and p not in seen and len(p) < 260:
            seen.add(p)
            out.append(p)
    return out
