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


CODE_STRONG = re.compile(
    r"(```|\b[\w./\-]+\.(py|js|jsx|ts|tsx|java|kt|swift|c|cc|cpp|h|hpp|rs|go|rb|php|cs|sh|ps1|sql|"
    r"json|ya?ml|toml|css|scss|vue|ipynb)\b|\bTraceback\b|\bstack ?trace\b|\bnpm (install|run|test)\b|"
    r"\bpip install\b|\bgit (commit|push|pull|rebase|merge|checkout|diff)\b)", re.I)
CODE_WEAK = re.compile(
    r"\b(function|variable|bug|debug|compile|refactor|repo(sitory)?|pull request|unit tests?|"
    r"api endpoint|regex|typescript|javascript|python|dockerfile|exception|null pointer|"
    r"segfault|linter|dependency|dependencies|lint)\b", re.I)


def is_coding_prompt(text):
    """Coding work isn't this coach's audience (everyday non-technical tasks), so
    such prompts are left out of scoring and coaching rather than being judged
    by rules that don't fit them."""
    t = text or ""
    if CODE_STRONG.search(t):
        return True
    return len(set(m.group(0).lower() for m in CODE_WEAK.finditer(t))) >= 2


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
    # "write me a poem about autumn" starts new work even when short; "write it shorter" doesn't.
    if NEW_TASK_START.search(text) and (w > 6 or (w >= 3 and not REFERS_BACK.search(text))):
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
    result["triggers"] = detect_triggers(text, result)
    return result


# --- recommendation triggers -------------------------------------------------------
# Named detectors that the recommendation library refers to with `detect: <name>`.
# Each one looks at a single message and answers "is this trigger happening?".
# They lean towards precision: a missed trigger costs nothing, a wrong one is
# a coaching moment that doesn't fit.

CREATE_VERB = re.compile(
    r"\b(write|draft|create|prepare|compose|put together|make me|generate|come up with)\b", re.I)
_NOUNS = (r"emails?|memo|posts?|deck|presentation|slides|report|letter|announcement|summary|proposal|"
          r"article|blog( post)?|newsletter|speech|message|update|bio|description|policy|guide|document|flyer|"
          r"pitch|agenda|brief|one[- ]pager|press release|cover letter|toast|invitation|faq|poem|story|caption|"
          r"script|essay|resume|résumé|note|notice|application|plan|handbook|statement|white ?paper|paper|"
          r"case study|playbook|manual|agreement|contract|proposal")
CONTENT_NOUN = re.compile(r"\b(" + _NOUNS + r")\b", re.I)
# "write a short welcome email" / "draft the memo": the verb governs the noun, a few words apart at most.
# ("make the proposal more compelling" is a revision, not a new piece of content.)
CONTENT_REQUEST = re.compile(
    r"\b(write|draft|create|prepare|compose|put together|make me|generate)\s+(me\s+|us\s+)?"
    r"(a|an|the|my|our|some|this|that|\d+)?\s*([\w',-]+\s+){0,4}?(" + _NOUNS + r")\b", re.I)
# Broader than the scoring cues: any named reader counts as saying who it's for.
AUDIENCE_ANY = re.compile(
    r"\b(for|to) (my|our|the|a|an|his|her|their|all|new|every)?\s*([\w'-]+\s+){0,2}?(team|customers?|clients?|"
    r"mentor|boss|manager|colleagues?|coworkers?|employees?|staff|hires|students?|parents?|board|investors?|"
    r"audience|attendees|members|users|readers|community|family|friends?|sister|brother|wife|husband|"
    r"partner|mom|dad|kids?|volunteers|donors|patients|vendors|partners|leadership|execs?|executives|"
    r"recruiters?|hiring manager|committee|landlord|neighbou?rs?|teacher|professor|doctor|ceo|cfo|hr|"
    r"everyone|whoever|stakeholders|shareholders|public|guests|followers|subscribers|program|conference)\b|"
    r"\b(recent grads|non-?technical|beginners?|experts?|audience|out[- ]of[- ]office|auto-?reply)\b", re.I)
PURPOSE_ANY = re.compile(
    r"\bso (that )?(they|he|she|we|i|people|attendees|readers|everyone|it|the \w+) |"
    # "so staff stop parking there", "so the team can plan": a purpose clause with any subject
    r"\bso (that )?[a-z']+ (can|could|will|won'?t|stop|stops|know|knows|don'?t|doesn'?t|have|has|get|gets|"
    r"understand|understands|see|sees|feel|feels|remember|remembers|start|starts)\b|"
    r"\b(to (persuade|convince|explain|teach|announce|apply|justify|negotiate|thank|apologi[sz]e|invite|"
    r"welcome|remind|recruit|celebrate|inform|update)|goal|purpose|because|in order to)\b|"
    r"\b(thank[- ]you|toast|apology|agreement|contract|press release|announcement|reminder|out[- ]of[- ]office|auto-?reply|condolence|invitation|cover letter|resignation|congratulat\w*|welcome|"
    r"wedding|birthday|retirement|interview|farewell|handover|hand-?off|fundrais\w*)\b|"
    r"\bfor (the|our|my|a|an) ([\w-]+ ){0,2}(sale|event|party|meeting|launch|fundraiser|conference|workshop|"
    r"webinar|campaign|offsite|drive|open house|reunion|gala)\b|"
    r"\b(asking|ask|telling|encourag\w*|invit\w*|remind\w*|urging) (them|people|everyone|members|readers|"
    r"customers|staff|employees|volunteers|parents) to\b|"
    # a situation stated up front ("we had a data breach, draft a notice") makes the purpose plain
    r"^\s*(we|i) (had|have|just|got|are|am|'re|'m)\b|^\s*(there was|there's been|after|following)\b", re.I)
SHAPE_SPEC = re.compile(
    r"\b(bullets?|table|outline|paragraphs?|sentences?|one[- ]page(r)?|short|brief|concise|long|detailed|"
    r"headings?|sections?|under \d+|at most|no more than|format|template|step[- ]by[- ]step)\b|\d", re.I)
MATERIAL_GIVEN = re.compile(r"\b(here (is|are)|here's|below|attached|these notes|the notes|following)\b", re.I)
VAGUE_VERB = re.compile(
    r"\b(help( me)?( with)?|improve|handle|deal with|work on|look (at|into)|sort out|fix up|"
    r"do something (with|about)|make (it|this) better|figure out)\b", re.I)
PRIORITY_GROUPS = {
    "speed": r"\b(fast|quick(ly)?|asap|urgent(ly)?|right away|today)\b",
    "accuracy": r"\b(accurate|precise|exact|correct|error[- ]free)\b",
    "creativity": r"\b(creative|original|bold|fresh|out of the box)\b",
    "cost": r"\b(cheap|low[- ]cost|budget|affordable|inexpensive)\b",
    "completeness": r"\b(comprehensive|complete|thorough|exhaustive|detailed|in[- ]depth|everything|all the details)\b",
    "brevity": r"\b(short|brief|concise|one[- ]page|quick read)\b",
}
COMMON_CAPS = {
    "AI", "I", "OK", "US", "USA", "UK", "EU", "CEO", "CFO", "CTO", "COO", "CMO", "HR", "IT", "PDF", "FAQ",
    "PR", "ASAP", "FYI", "TV", "CSV", "URL", "KPI", "KPIS", "ROI", "LLC", "INC", "AM", "PM", "NYC", "UN",
    "NDA", "VP", "SVP", "EVP", "MBA", "PHD", "TBD", "ETA", "RSVP", "DM", "OOO", "Q1", "Q2", "Q3", "Q4",
    "B2B", "B2C", "PPT", "PPTX", "DOCX", "XLSX", "SMS", "AND", "OR", "THE", "NOT", "NO", "YES", "ID",
}
CAPS_TOKEN = re.compile(r"\b[A-Z][A-Z0-9&]{1,6}s?\b")
SUBJECTIVE = re.compile(
    r"\b(brief|short|professional|comprehensive|engaging|compelling|polished|catchy|punchy|punchier|snappier|"
    r"impactful|high[- ]quality|detailed|thorough|exhaustive|concise|clear|modern|clean|sleek|simple|more (engaging|"
    r"exciting|interesting|professional|polished|compelling|impactful))\b", re.I)
STYLE_REF = re.compile(
    r"\b(in the style of|same (style|format|tone|layout) as|like (our|my|the) (last|previous|usual|other)|"
    r"match(es|ing)? (our|my|the) (style|format|tone|template|brand|voice)|house style|brand voice|"
    r"our usual (style|format|tone)|like the one (in|from) (my|our) (last|previous|other)|the way (we|i) (usually|normally|always))\b", re.I)
EXAMPLE_GIVEN = re.compile(
    r"\b(example|sample|for instance|e\.g\.|here(?:'s| is| are) (one|what|last|the|my|our|this|a|an|two|three|some)\b|"
    r"below|attached|like this:)", re.I)
TASK_VERBS = ("write", "summarize", "summarise", "analyze", "analyse", "compare", "draft", "create",
              "research", "review", "translate", "plan", "calculate", "list", "outline", "edit", "rewrite",
              "find", "design", "recommend", "explain", "prepare", "build", "check", "organize", "schedule")
# A task verb only counts when it starts a clause ("summarize X, then compare Y"),
# not when it's a noun ("a business plan", "an outline for me").
TASK_VERB_RE = re.compile(
    r"(?:^|[,;:.]\s*|\b(?:and|then|also|please|to|first|finally|next|lastly)\s+)(" + "|".join(TASK_VERBS) + r")\b", re.I | re.M)
QUESTION_START = re.compile(
    r"^\s*(what|what's|who|when|where|which|how (many|much|often|long|big|old)|is|are|was|were|did|does|"
    r"is it true)\b", re.I)
OPINION_Q = re.compile(
    r"^\s*(what (do|would|should|could) (you|i|we)|what'?s (your|a good|the best)|how (do|can|should|would) "
    r"(i|we|you)|is (this|that|my)|is it (?!true)|are (these|those|my))\b|\b(you think|your opinion|your thoughts|should i|should we|which is better|better for me|"
    r"(a|the) (polite|good|nice|best|kind|professional) way|best way to)\b", re.I)
FACT_TOPIC = re.compile(
    r"\b(statistics|stats on|research (shows|says|on)|studies (show|on)|data on|facts about|history of|"
    r"what percentage)\b", re.I)
SOURCE_GIVEN = re.compile(r"\b(sources?|cite|citations?|according to|link|attached|below|this (article|report|doc))\b", re.I)
INTERNAL_POLICY = re.compile(
    r"\b((our|my|the company'?s?|company|hr|internal|team'?s?) (policy|policies|procedures?|process|handbook|"
    r"guidelines|rules|benefits|pto|leave policy|expense policy|reimbursement|travel policy|org chart|"
    r"approval process)|(pto|expense|travel|leave|remote work|return to office) policy)\b", re.I)
CURRENT_INFO = re.compile(
    r"\b(latest|most recent|up[- ]to[- ]date|today'?s|breaking|news|"
    r"current (price|rate|status|version|state|trends?|events|ceo|law|laws|rules|regulations|guidance|"
    r"interest rate|exchange rate|minimum wage|population|inflation|mortgage rates?|gas prices?)|stock price|"
    r"(minimum wage|inflation rate|unemployment rate) (in|for|this)|right now in|as of (today|now))\b", re.I)
CALC_WORDS = re.compile(
    r"\b(calculate|compute|total|sum|add up|average|mean|median|percent(age)?|growth rate|roi|margin|"
    r"convert|how much (will|would|does|do)|break[- ]?even)\b", re.I)
ARITHMETIC = re.compile(r"\d(\.\d+)?\s*%\s*of\s*\$?\d|\d\s*[x×*÷+]\s*\d|\bconvert\b.{0,30}\d")
NUMBER = re.compile(r"(?<![A-Za-z])\$?\d[\d,]*(\.\d+)?%?")
CONSEQUENTIAL = re.compile(
    r"\b(legal(ly)?|lawsuit|sue|court|contract|liabilit(y|ies)|immigration|visa|diagnos(is|e|ed)|symptoms?|"
    r"medication|dosage|prescription|treatment plan|tax (return|filing|advice)|irs|invest(ment)? advice|"
    r"retirement savings|roth|ira|401\(?k\)?|pension|severance|side effects|prescribed|\d+ ?mg|lawyer|"
    r"attorney|divorce|custody|eviction|mortgage|loan application|terminat(e|ion|ing)|fire (him|her|them|an employee|someone)|"
    r"lay ?offs?|laying off|performance (review|improvement plan)|disciplinary|hiring decision|salary offer|"
    r"security (breach|incident)|data breach|compliance)\b", re.I)
TONE_FEEDBACK = re.compile(
    r"\b(too (formal|casual|stiff|salesy|robotic|wordy|corporate|cheesy|informal|harsh|stuffy|fluffy|generic)|"
    r"doesn'?t sound like (me|us)|not my (voice|style|tone)|tone is (off|wrong|not right)|"
    r"sounds (like a robot|robotic|like ai|fake|generic|cheesy|stiff))\b", re.I)
SINGLE_OPTION = re.compile(
    r"\b(give me|suggest|come up with|think of|what'?s|need) (a|an|one) (good |catchy |short )?"
    r"(idea|name|title|tagline|slogan|headline|subject line|theme|option|topic|hook)\b", re.I)
LONG_DOC_NOUN = re.compile(
    r"\b(proposal|white ?paper|business plan|strategy (doc|document|paper)|handbook|thesis|manual|e-?book|"
    r"playbook|grant application|annual report|research report)\b", re.I)
LONG_LENGTH = re.compile(r"\b(\d{1,3}(,\d{3})+|\d{4,}|[5-9]\d{2})[- ]words?\b|\b([3-9]|\d{2,}) pages?\b", re.I)
OUTLINE = re.compile(r"\b(outline|table of contents|sections?:|structure)\b", re.I)
STRUCTURED = re.compile(r"\b(json|csv|xml|import (it |them )?into|upload (it |them )?to|spreadsheet|database|crm)\b", re.I)
STRUCTURED_ASK = re.compile(
    r"\b(export|convert|turn|put|save|format|output|give me|make|create|build|as)\b.{0,40}\b(json|csv|xml|spreadsheet|"
    r"database|crm)\b|\b(import|upload)\b", re.I)
SCHEMA_GIVEN = re.compile(r"\b(columns?|fields?|schema|headers?|keys?)\b", re.I)
MISSED = re.compile(
    r"\b(you (forgot|missed|left out|didn'?t include|still didn'?t|ignored|keep forgetting)|still (missing|"
    r"not there|doesn'?t have)|i (already|just) (said|asked|told you)|as i (said|asked)|again you|"
    r"where(?:'s| is) the)\b", re.I)
MANUAL_EDITS = re.compile(
    r"\b(i(?:'ve| have)? (fixed|edited|changed|rewrote|cleaned up|tweaked|reworded|corrected) (it|this|that|"
    r"the \w+|a few)( \w+)? (myself|by hand|manually|in (word|google docs|outlook))|copied (it|this) (into|to) "
    r"(word|google docs|excel|outlook)|i always have to (change|fix|edit))\b", re.I)
EXTERNAL_ACTION = re.compile(
    r"^\s*(please |can you |could you |go ahead and |now |ok(ay)?,? )?(send|post|publish|delete|remove|cancel|"
    r"purchase|buy|order|book|deploy|submit|share|email|reply to|forward|schedule)\b", re.I)
IRREVERSIBLE = re.compile(
    r"\b((delete|remove|wipe|erase|overwrite|purge|clear|cancel) (all|every|everything|them all|the whole)|"
    r"permanently|can'?t be undone|cannot be undone|no backup|without (a )?backup|"
    r"(don'?t|do not) have (a |any )?backups?)\b", re.I)
REMEMBER = re.compile(
    r"\b(remember (that|this|my|i)|from now on|going forward|in (the )?future,? (always|please|use)|"
    r"every time you|always (use|write|format|call me|sign))\b", re.I)
REPEATED_TASK = re.compile(
    r"\b((every|each) (week|day|month|morning|monday|tuesday|wednesday|thursday|friday|quarter|time i)|weekly|"
    r"monthly|again this (week|month)|as usual|like (last|every) (week|month|time)|same as last "
    r"(week|month|time)|i do this (a lot|all the time|every))\b", re.I)
HANDOFF = re.compile(
    r"\b(hand(ing)? (this |it )?off|handover|hand (it |this )?over|pass(ing)? (this|it) (on|to)|tak(e|es|ing) "
    r"over (from me|my)|while i'?m (out|away|on leave|on vacation|off)|covering for me|my (backup|replacement|cover)|brief (my|a|the) "
    r"(colleague|replacement|team|successor))\b", re.I)


def _content_request(text):
    return bool(CONTENT_REQUEST.search(text))


def _bare_content_request(text, analysis):
    """A short request for new content with no material supplied: the moment
    when naming the reader, the goal or the shape helps most."""
    return _content_request(text) and analysis["words"] <= 30 and not MATERIAL_GIVEN.search(text)


_POSITION = re.compile(r"\b(slide|page|section|paragraph|step|option|version|q)\s*\d+\b", re.I)


def _has_quantity(text):
    """A number that sets a size ("3 paragraphs", "10 ideas"), not one that
    points at a place ("slide 3")."""
    return bool(re.search(r"\d", _POSITION.sub(" ", text)))


def _factual_question(text, analysis):
    if SOURCE_GIVEN.search(text) or analysis["verify"] or FILE_REF.search(text):
        return False
    if FACT_TOPIC.search(text):
        return True
    return bool(QUESTION_START.search(text)) and not OPINION_Q.search(text) and analysis["words"] <= 30


def _jargon(text):
    caps = {m.group(0).rstrip("s").upper() for m in CAPS_TOKEN.finditer(text)
            if m.group(0).upper() not in COMMON_CAPS and m.group(0).rstrip("s").upper() not in COMMON_CAPS}
    return len(caps) >= 2


def _competing(text):
    groups = {g for g, p in PRIORITY_GROUPS.items() if re.search(p, text, re.I)}
    return len(groups) >= 3 or {"brevity", "completeness"} <= groups


def _multi_task(text):
    verbs = {m.group(1).lower() for m in TASK_VERB_RE.finditer(text)}
    numbered = len(re.findall(r"(?m)^\s*(\d+[.)]|[-*•])\s+\w+", text))
    return len(verbs) >= 3 or (numbered >= 3 and len(verbs) >= 2)


# name -> (message kinds it applies to, test). Kinds: new, followup, refine.
NEW, ANY = ("new",), ("new", "followup", "refine")
DETECTORS = {
    "vague_goal": (NEW, lambda t, a: bool(VAGUE_VERB.search(t)) and a["precision"] < 0.3 and a["words"] >= 2
                   and a["words"] < 25 and not CREATE_VERB.search(t) and not QUESTION_START.search(t)
                   and not re.match(r"\s*(how|why|what|who|when|where|which)\b", t, re.I)),
    "no_audience": (NEW, lambda t, a: _bare_content_request(t, a) and not _any(AUDIENCE_CUES, t)
                    and not AUDIENCE_ANY.search(t)),
    "no_purpose": (NEW, lambda t, a: _bare_content_request(t, a) and not _any(PURPOSE_CUES, t)
                   and not (SHAPE_SPEC.search(t) and _any(TONE_CUES, t))
                   and not PURPOSE_ANY.search(t)),
    "no_format": (NEW, lambda t, a: _bare_content_request(t, a) and not SHAPE_SPEC.search(t)
                  and not _any(TONE_CUES, t)),
    "competing_goals": (NEW, lambda t, a: _competing(t)),
    "jargon": (NEW, lambda t, a: _jargon(t)),
    "subjective": (("new", "followup"), lambda t, a: bool(SUBJECTIVE.search(t)) and not _has_quantity(t)),
    "style_no_example": (NEW, lambda t, a: bool(STYLE_REF.search(t)) and not EXAMPLE_GIVEN.search(t)
                         and not FILE_REF.search(t)),
    "long_prompt": (NEW, lambda t, a: a["words"] > 400 and not FILE_REF.search(t)),
    "multi_task": (NEW, lambda t, a: _multi_task(t)),
    "factual_question": (NEW, _factual_question),
    "internal_policy": (("new", "followup"), lambda t, a: bool(INTERNAL_POLICY.search(t)) and not FILE_REF.search(t)),
    "current_info": (("new", "followup"), lambda t, a: bool(CURRENT_INFO.search(t))),
    "calculations": (ANY, lambda t, a: (bool(CALC_WORDS.search(t)) and len(NUMBER.findall(t)) >= 2
                                          or bool(ARITHMETIC.search(t)))
                     and not a["verify"] and not re.search(r"\b(check|verify|confirm)\b", t, re.I)),
    "consequential": (ANY, lambda t, a: bool(CONSEQUENTIAL.search(t))),
    "sensitive": (ANY, lambda t, a: bool(a.get("sensitive"))),
    "tone_feedback": (ANY, lambda t, a: bool(TONE_FEEDBACK.search(t))),
    "single_option": (NEW, lambda t, a: bool(SINGLE_OPTION.search(t))),
    "long_document": (NEW, lambda t, a: bool(CONTENT_REQUEST.search(t)) and bool(LONG_DOC_NOUN.search(t)
                      or LONG_LENGTH.search(t)) and not OUTLINE.search(t)),
    "structured_output": (NEW, lambda t, a: bool(STRUCTURED.search(t)) and bool(STRUCTURED_ASK.search(t)) and not SCHEMA_GIVEN.search(t)),
    "missed_requirement": (ANY, lambda t, a: bool(MISSED.search(t))),
    "manual_edits": (ANY, lambda t, a: bool(MANUAL_EDITS.search(t))),
    "external_action": (ANY, lambda t, a: bool(EXTERNAL_ACTION.search(t))),
    "irreversible": (ANY, lambda t, a: bool(IRREVERSIBLE.search(t))),
    "remember_pref": (ANY, lambda t, a: bool(REMEMBER.search(t))),
    "repeated_task": (ANY, lambda t, a: bool(REPEATED_TASK.search(t))),
    "handoff": (ANY, lambda t, a: bool(HANDOFF.search(t))),
}


# A clear yes may carry extra detail ("yes, it's for the board"). "ok" / "please" are
# weaker: "ok make the tone warmer" is a new instruction, not a yes to the coach, so
# they only count when nothing but pleasantries follow.
ACCEPT = re.compile(
    r"^\s*(yes|yeah|yep|yup|sure|please do|go (ahead|for it)|do it|do that|let'?s (do (it|that)|try it)|"
    r"sounds good|absolutely|definitely|that would (help|be great)|y)\b", re.I)
WEAK_ACCEPT = re.compile(r"^\s*(ok(ay)?|please|let'?s go|great|perfect|cool)\b(?P<rest>.*)$", re.I | re.S)
FILLER = {"please", "thanks", "thank", "you", "go", "ahead", "do", "it", "that", "sure", "yes", "ok", "okay",
          "sounds", "good", "great", "perfect", "let's", "lets", "and", "the", "offer", "would", "be", "help",
          "i'd", "like", "love", "to", "that's", "a", "idea", "cool", "fine", "then", "so", "yeah"}
DECLINE = re.compile(r"^\s*(no|nope|nah|not now|no thanks|skip( it)?|don'?t bother|maybe later|i'?m good)\b", re.I)


MISFIT = re.compile(
    r"\b((that|this|it|the tip)('s| is)? (doesn'?t|does not|didn'?t|did not) (apply|fit|make sense|help)|"
    r"not (relevant|helpful|applicable|useful)|irrelevant|wrong (tip|suggestion|advice)|"
    r"stop (suggesting|telling me|asking)|(that|this) (tip|suggestion|coaching) (is|was) (useless|unhelpful|off))\b",
    re.I)


def is_misfit(text):
    """The user says the coach's tip didn't fit their situation (a false positive)."""
    return len(words(text)) <= 15 and bool(MISFIT.search(text or ""))


def is_acceptance(text):
    """A short yes to the coach's offer ("yes please", "sure, go ahead")."""
    t = text or ""
    if len(words(t)) > 12 or DECLINE.search(t):
        return False
    if ACCEPT.search(t):
        return True
    weak = WEAK_ACCEPT.match(t)
    return bool(weak) and all(w.lower() in FILLER for w in words(weak.group("rest")))


def is_decline(text):
    return len(words(text)) <= 12 and bool(DECLINE.search(text or ""))


# When a specific trigger fires, the generic ones it covers are dropped: "what is
# our PTO policy" is about the internal source, not facts in general, and a
# 20-page plan needs an outline before it needs a named reader.
SUPERSEDES = {
    "internal_policy": ("factual_question",),
    "current_info": ("factual_question",),
    "calculations": ("factual_question",),
    "long_document": ("no_audience", "no_purpose", "no_format"),
    "multi_task": ("no_audience", "no_purpose", "no_format"),
    "competing_goals": ("no_audience", "no_purpose", "no_format"),
}


def detect_triggers(text, analysis):
    """Names of the detectors that fire for this message (sorted). Like the rest
    of this module it returns only names, never any of the text."""
    fired = set()
    kind = analysis.get("kind", "new")
    for name, (kinds, test) in DETECTORS.items():
        if kind in kinds and test(text or "", analysis):
            fired.add(name)
    for specific, generic in SUPERSEDES.items():
        if specific in fired:
            fired.difference_update(generic)
    return sorted(fired)


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
