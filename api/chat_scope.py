"""
Scope lock for the chat assistant. Every user message is classified here,
by keyword and pattern only, before any model call. Only messages that land
in an allowed bucket go further; anything else gets a fixed reply and no
model call.

Allowed buckets: plan_request, weather_question, heat_safety_question,
rules_question, about_harara, emergency. Everything else, including
prompt-injection attempts, is out_of_scope.

Also here: the output scope guard that runs on any model reply before it
reaches the user, the fixed out-of-scope reply, the KB-grounded emergency
reply, and a refusal counter that records bucket counts only, never text.
"""

from __future__ import annotations

import re
from collections import Counter

from api import kb

# A message longer than this is not a heat-safety question or a shift
# description; refuse it politely rather than forward it.
MAX_MESSAGE_CHARS = 1200

OUT_OF_SCOPE_REPLY = (
    "I only help with heat, weather, outdoor-work rules, and planning a shift. "
    "I can't help with that."
)
NO_MATCH_REPLY = (
    "I don't have that. I can explain WBGT and heat illness, cover "
    "acclimatisation and first response, check the forecast or whether it is "
    "safe to work outside right now, give the Qatar rule, and plan a shift."
)

ALLOWED = (
    "plan_request", "weather_question", "heat_safety_question",
    "rules_question", "about_harara", "emergency",
)

# --------------------------------------------------------------- patterns
_INJECTION = re.compile(
    r"ignore (?:all |your |the |previous |prior |above )*(?:instructions|prompts?|rules?)"
    r"|disregard (?:all |the |any |previous )*(?:instructions|rules?|above)"
    r"|forget (?:everything|all|your|the) (?:above|instructions|rules?|prompt)"
    r"|you are (?:now|actually) (?:a|an|not)"
    r"|(?:new|updated|real) (?:system )?(?:prompt|instructions?)\s*[:=]"
    r"|(?:reveal|show|print|repeat|output) (?:me )?(?:your |the )?(?:system )?(?:prompt|instructions?)"
    r"|what (?:is|are) your (?:system )?(?:prompt|instructions?)"
    r"|act as (?:a|an|if)|pretend (?:to be|you are)|role[- ]?play"
    r"|jailbreak|\bDAN\b|developer mode|\bsudo\b"
    r"|</?(?:system|assistant|user|im_start|im_end)>|\[/?INST\]"
    r"|base64|rot13",
    re.I,
)

# Unambiguous distress: a person in this state is a medical emergency
# regardless of surrounding words.
_EMERGENCY_HARD = re.compile(
    r"\b(?:passed out|pass(?:ing)? out|faint(?:ed|ing)|unconscious|unresponsive"
    r"|collaps(?:e|ed|ing)|convuls(?:e|ed|ing|ion)|seiz(?:ure|ing)"
    r"|having a (?:seizure|fit)|stopped sweating|no longer sweating"
    r"|won'?t wake|can'?t wake|wouldn'?t wake|gone limp|stopped responding"
    r"|not responding)\b",
    re.I,
)
# Needs a person as the subject to count (so "what is heat stroke" or "I'm
# confused about the chart" do not trip it).
_EMERGENCY_SOFT = re.compile(
    r"\b(?:heat ?stroke|sun ?stroke|confus(?:ed|ion)|disorient|delirious"
    r"|slurr(?:ed|ing) (?:speech|words)?"
    r"|vomit(?:ing|ed)?|throwing up|threw up|being sick"
    r"|dizzy and|very hot (?:and )?dry skin|hot dry skin|skin (?:is )?hot and dry"
    r"|burning up|stumbling|can'?t stand)\b",
    re.I,
)
# An informational question about a condition, not a report of one happening.
_DEFINITIONAL = re.compile(
    r"\b(?:what(?:'?s| is| are)|whats|difference between|\bvs\.?\b|versus"
    r"|explain|define|definition|meaning of|tell me about|what does .* mean"
    r"|how (?:do|would) (?:you|i|we) (?:treat|spot|recognise|recognize|tell|handle)"
    r"|signs of|symptoms of|first aid for|what to do (?:for|about|if))\b",
    re.I,
)
_PERSON = re.compile(
    r"\b(?:he|she|they|him|her|them|his|their|worker|co[- ]?worker|colleague|mate"
    r"|guy|man|woman|someone|somebody|somone|friend|labou?rer|crew|team|"
    r"a person|the person|another)\b",
    re.I,
)

_OFF_TOPIC = re.compile(
    r"\b(?:code|coding|program(?:ming)?|python|javascript|typescript|java|c\+\+"
    r"|regex|function|algorithm|debug|compile|sql|leetcode"
    r"|essay|paragraph|paraphrase|summar(?:y|ise|ize) this|write me|write a"
    r"|poem|haiku|sonnet|story|joke|riddle|rap|lyrics|screenplay"
    r"|recipe|cook|bake|meal plan|workout plan|diet"
    r"|translate|translation|in (?:french|spanish|arabic|german|hindi|urdu)"
    r"|homework|assignment|exam|quiz"
    r"|math|maths|equation|integral|derivative|calculus|algebra|solve for"
    r"|\d\s*[-+*/x×]\s*\d"
    r"|capital of|president of|prime minister|who won|world cup|election"
    r"|stock|shares|crypto|bitcoin|ethereum|invest|price of"
    r"|movie|film|tv show|netflix|song|album|celebrity"
    r"|dating|relationship advice|horoscope|astrology|tarot"
    r"|hack|exploit|malware|phishing|bypass)\b",
    re.I,
)

# An explicit ask to build or change a plan. Strong signal: checked before the
# topic gates so "plan tomorrow ..." is not swallowed by the weather pattern.
_PLAN_ASK = re.compile(
    r"\bplan (?:tomorrow|today|the day|a day|my day|our day|a shift|the shift|for|this)\b"
    r"|\bre[- ]?plan\b|\breplan\b"
    r"|\bschedule (?:the|a|my|our|this|tomorrow|today|next|a shift)\b"
    r"|\bbuild (?:me )?(?:a|the) plan\b"
    r"|\bwork out (?:the|a) (?:day|shift|plan)\b"
    r"|\blay out the (?:day|shift)\b"
    r"|\b(?:plan|schedule) (?:a |the )?shift\b"
    r"|\bshift for (?:a|the|my|our|us|\d)\b",
    re.I,
)
# Looser shift-description words: a described job with no "plan" verb still
# routes to the planner, but only after the topic questions have had a turn.
_PLAN_VERB = re.compile(
    r"\b(crew of \d|work[- ]?hours?|pour (?:concrete|footings)|dig(?:ging)?|"
    r"concrete pour|scaffold(?:ing)?|rebar|steel fixing|lifting operation|"
    r"labou?r(?:er|ers)? on site|excavat)\b",
    re.I,
)

_RULES = re.compile(
    r"\b(rule|rules|law|laws|legal|regulation|statute|decision ?17|17/2021"
    r"|midday (?:break|ban|rest)|work(?:ing)? hours? (?:law|rule|limit)"
    r"|allowed to work|permitted to work|when (?:can|must|do) (?:we|they|i) stop"
    r"|labou?r (?:law|ministry|code)|ministerial|mohre|mhrsd)\b",
    re.I,
)
_JURISDICTION = re.compile(
    r"\b(qatar|doha|lusail|uae|u\.a\.e|emirat|dubai|abu dhabi|sharjah|ajman"
    r"|saudi|k\.s\.a|ksa|riyadh|jeddah|dammam|bahrain|manama|kuwait|oman|muscat)\b",
    re.I,
)

_ABOUT = re.compile(
    r"\bharara\b"
    r"|\bwho (?:are|made|built|designed) you\b"
    r"|\bwhat (?:are|is) (?:you|this|it)\b"
    r"|\bwhat can you (?:do|help)\b"
    r"|\bhow (?:do|does) (?:you|this|it) work\b"
    r"|\byour (?:limitations|limits|caveats)\b"
    r"|\bare you (?:an? )?(?:ai|bot|model|human|real)\b"
    r"|\bis this (?:an? )?(?:ai|bot|prototype)\b",
    re.I,
)

_HEAT_SAFETY = re.compile(
    r"\b(wbgt|wet[- ]?bulb|globe temperature|heat[- ]?stress|heat[- ]?strain"
    r"|heat (?:illness|exhaustion|stroke|cramps?|rash|dose|load)"
    r"|retained (?:heat )?load|cumulative exposure"
    r"|acclimati[sz]|dehydrat|hydrat|drink(?:ing)? water|electrolyte|salt tablet"
    r"|first aid|first response|cool (?:the|a|him|her|them|down)|shade break"
    r"|core temperature|sweat(?:ing)?|sun ?stroke)\b",
    re.I,
)

_WEATHER_NOW = re.compile(
    r"\b(right now|at the moment|currently|as of now|this hour"
    r"|is it safe to work|safe to work (?:outside|now|today|right now)"
    r"|how hot is it|conditions? (?:now|right now|today|outside)|nowcast"
    r"|can (?:we|they|i) work (?:now|outside|today)"
    r"|coolest (?:hours?|window|time)|when (?:does|will) it (?:cool|get cooler)"
    r"|when (?:does|will) wbgt (?:cross|hit|reach|drop))\b",
    re.I,
)

_WEATHER = re.compile(
    r"\b(weather|forecast|outlook|hotter|cooler|cool(?:est|er)|hott?est"
    r"|this week|next (?:few )?days|coming days|rest of the week|tomorrow"
    r"|compared? to the week|wbgt (?:this|next|over|tomorrow|today|trend)"
    r"|which day|worst day|best day|how hot"
    r"|(?:heat|wbgt|temperature)? ?trend|been (?:getting |increasing)|getting (?:hotter|warmer)"
    r"|increasing (?:here|over)|over the years|year[- ]on[- ]year|warming"
    r"|climate|unusual(?:ly)? (?:hot|warm|heat|for)|record heat|typical for)\b",
    re.I,
)

_GREETING = re.compile(
    r"^\s*(hi|hey+|hello|yo|sup|salaam|salam|good (morning|afternoon|evening)"
    r"|thanks|thank you|cheers|ok|okay|cool|nice|great)\b[\s!.]*$",
    re.I,
)
_QUESTIONISH = re.compile(r"\?\s*$|^\s*(what|why|how|when|which|is|are|can|could|do|does|should)\b", re.I)


def classify(text: str, *, schedule_hint: bool = False,
             gathering: bool = False) -> str:
    """Bucket a user message. Order matters: injection and emergency win over
    everything, then an in-progress plan, then the topic gates."""
    t = (text or "").strip()
    if not t or len(t) > MAX_MESSAGE_CHARS:
        return "out_of_scope"
    if _INJECTION.search(t):
        return "out_of_scope"
    _distress = _EMERGENCY_HARD.search(t) or (
        _EMERGENCY_SOFT.search(t) and _PERSON.search(t))
    if _distress and not (_DEFINITIONAL.search(t) and not _PERSON.search(t)):
        return "emergency"
    # a strong plan signal (the caller already parsed the request, we are
    # mid-gather, or an explicit "plan / schedule this" verb)
    if gathering or schedule_hint or _PLAN_ASK.search(t):
        return "plan_request"
    if _OFF_TOPIC.search(t):
        return "out_of_scope"
    # topic questions win over the loose shift-description words below
    if _WEATHER_NOW.search(t):
        return "weather_question"
    if _RULES.search(t) or (_JURISDICTION.search(t)
                            and not _WEATHER.search(t) and not _HEAT_SAFETY.search(t)
                            and re.search(r"\b(work|hours?|ban|break|stop|allowed)\b", t, re.I)):
        return "rules_question"
    if _WEATHER.search(t):
        return "weather_question"
    if _ABOUT.search(t):
        return "about_harara"
    if _HEAT_SAFETY.search(t):
        return "heat_safety_question"
    # a described shift with no "plan" verb ("pour concrete 8h tomorrow, heavy
    # crew, Lusail") still routes to the planner
    if _PLAN_VERB.search(t):
        return "plan_request"
    if _GREETING.match(t):
        return "about_harara"
    if _QUESTIONISH.search(t):
        # a question we cannot place: let the KB decide, it returns nothing for
        # anything off-topic and the caller then gives the fixed reply.
        return "heat_safety_question"
    return "out_of_scope"


# --------------------------------------------------------------- output guard
_OUTPUT_BAD = re.compile(
    r"```|~~~|<\?php|\bdef \w+\s*\(|\bclass \w+\s*[:(]|\bimport \w+|#include"
    r"|console\.log|System\.out|printf\s*\(|SELECT\s+.+\s+FROM\s"
    r"|as an? (?:ai|language model|large language model)"
    r"|\bhere(?:'s| is) (?:a|the|your) (?:poem|haiku|recipe|essay|story|joke|translation|code)\b"
    r"|lorem ipsum",
    re.I,
)


def output_in_scope(text: str) -> bool:
    """Runs on every model reply before it reaches the user, alongside the
    numeric guard. False means the reply drifted out of the allowed domains
    or into a format the assistant never produces."""
    return not _OUTPUT_BAD.search(text or "")


# --------------------------------------------------------------- emergency
def emergency_reply() -> tuple[str, str, str]:
    """(banner, first-response body, source). Fixed text from the KB entry,
    never model-improvised."""
    e = kb.get("emergency-first-response") or {}
    return (
        e.get("banner", "This can be a medical emergency. Call the local "
                        "emergency number now."),
        e.get("text", ""),
        e.get("source", ""),
    )


# --------------------------------------------------------------- refusal log
_counts: Counter = Counter()


def note(bucket: str) -> None:
    """Record that a message fell in this bucket. Counts only, no text."""
    _counts[bucket] += 1


def counts() -> dict:
    return dict(_counts)


def reset_counts() -> None:
    _counts.clear()
