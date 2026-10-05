# =========================================================
# BUSINESS KNOWLEDGE FOR THE MARITIME AI ASSISTANT
# =========================================================
# Purpose
# -------
# This module is the SINGLE place where the Maritime AI
# Assistant is told what this platform DOES for a customer,
# in plain business language.
#
# It is NOT developer documentation. It deliberately contains
# no API names, no framework names, no database structure, no
# file or folder names, no environment variables, no source
# code, no algorithms written as code, no logs and no model
# names. A question about any of those is refused before this
# module is ever consulted (see app/agents/assistant_scope.py).
#
# GROUNDING CONTRACT
# ------------------
# Every business rule stated here is IMPORTED from the agent
# that actually applies it, so a description can never drift
# from the behaviour it explains:
#
#   Weather Agent -> the real risk limits and risk levels
#   Customs Agent -> the real tracked documents and statuses
#   Route Agent   -> the real cargo categories and ranking rule
#
# Values that genuinely live in the API layer (the shipment
# status workflow) are INJECTED by the caller instead of being
# copied, so there is one source of truth.
#
# WHAT THIS MODULE IS NOT
# -----------------------
# It computes no route score, no weather risk, no customs
# status, no price and no margin. It never reads or writes the
# database and it never calls Gemini. Every business VALUE in
# an answer still comes from an existing, unchanged module.
#
# SCOPE
# -----
# A normal customer never receives administrator-only content.
# =========================================================

import re


# =========================================================
# GROUNDED CONSTANTS IMPORTED FROM THE EXISTING AGENTS
# =========================================================
# Read-only references to the real modules. No agent logic is
# called, subclassed or wrapped, and nothing here can change an
# agent's behaviour.

from app.agents.route_agent import (
    CARGO_TYPE_MAPPING,
    load_routes,
)
from app.agents.weather_agent import (
    RISK_ADVISORIES,
    RISK_LEVELS,
    RISK_SUMMARIES,
    RISK_THRESHOLDS,
    STORM_RISK_GRADES,
)
from app.agents.customs_agent import (
    RESTRICTED_CONTROL_LABEL,
    STATUS_SEQUENCE,
    TRACKED_CONTROLS,
    TRACKED_CONTROL_COUNT,
)


# The agent's own data note names the internal dataset it was
# derived from, so it is not repeated to customers. The honest
# part of it is kept: these requirements are reference
# information, not an official customs feed, and a licensed
# broker has to confirm them.

CUSTOMS_REFERENCE_NOTE = (
    "These requirements come from the reference customs "
    "information held by the platform. They are not an "
    "official customs authority feed, so always confirm them "
    "with a licensed customs broker before you rely on them."
)

WEATHER_REFERENCE_NOTE = (
    "The readings come from the reference weather "
    "information held by the platform. It is not a live "
    "weather feed, it is reference data rather than a live "
    "forecast."
)


# The route score weights the agent applies inline while
# scoring a lane. They are reproduced here so an explanation
# can quote the real weighting, and the regression suite locks
# them against the agent's scoring expression. Higher is
# better for every factor.

ROUTE_SCORE_WEIGHTS = {
    "transit_days": 5,
    "distance_nm": "1/100",
    "transshipments": 10,
}

# The pricing steps the agent applies. These name the agent's
# own quantities so a description cannot drift from the
# calculation; they are grounding material for an explanation
# and are never shown to a customer as-is.

PRICING_FORMULAS = {
    "operating_cost_formula": (
        "operating_cost = "
        "(base_freight + fuel_surcharge + port_charge "
        "+ risk_surcharge) * containers"
    ),
    "demand_adjusted_cost_formula": (
        "demand_adjusted_cost = "
        "operating_cost * demand_factor"
    ),
    "selling_price_formula": (
        "selling_price = "
        "demand_adjusted_cost "
        "/ (100 - target_margin_percent) * 100"
    ),
}


# =========================================================
# PLATFORM IDENTITY
# =========================================================

PLATFORM_NAME = "Maritime Brokerage Platform"

PLATFORM_PURPOSE = (
    "This platform helps a shipper plan and book a container "
    "movement. You enter an origin port, a destination port, "
    "a cargo type, a cargo subtype and a number of containers. "
    "The platform then shows you the shipping routes available "
    "on that lane, the recommended route and why it was "
    "recommended, the weather risk on that route, the customs "
    "documents the lane requires, a priced quotation, and "
    "afterwards the status of your shipment."
)

GROUNDING_RULE = (
    "The platform's own records are the source of truth. "
    "Only explain information supplied to you. Never invent "
    "missing information. Never guess a shipment, quotation, "
    "route, weather condition or customs status. If the "
    "requested information is unavailable, say plainly that it "
    "is unavailable."
)


# =========================================================
# TOPIC IDENTIFIERS
# =========================================================
# Business topics only. There is no topic for code, framework,
# database, authentication or the explanation service, because
# those questions are refused before a topic is ever selected.

TOPIC_OVERVIEW = "platform_overview"
TOPIC_ROUTE = "route_recommendation"
TOPIC_WEATHER = "weather_check"
TOPIC_CUSTOMS = "customs_check"
TOPIC_CARGO = "cargo"
TOPIC_PRICING = "quotation"
TOPIC_SHIPMENT = "shipment_tracking"
TOPIC_PLATFORM_USE = "using_the_platform"
TOPIC_ADMIN_AREA = "administrator_area"


# Content a normal customer is never given. The caller is told
# the area exists and is access controlled, and nothing more.

ADMIN_ONLY_TOPICS = {
    TOPIC_ADMIN_AREA,
}

ADMIN_BOUNDARY_NOTE = (
    "Some parts of the platform are handled by an "
    "administrator and are not available on your account. Your "
    "quotation has to be approved by an administrator before a "
    "shipment is created."
)


# Topics that describe one part of the business. The same
# words ("route", "customs", "shipment") are used both for
# "how does this work?" and for "what is mine?", so these are
# suppressed when the question is clearly about the customer's
# own record.

DATA_MIRRORING_TOPICS = {
    TOPIC_ROUTE,
    TOPIC_WEATHER,
    TOPIC_CUSTOMS,
    TOPIC_CARGO,
    TOPIC_PRICING,
    TOPIC_SHIPMENT,
}


# =========================================================
# SMALL FORMATTING HELPERS
# =========================================================

def _number(value):
    """Render a number without a trailing '.0'."""

    if isinstance(value, bool):
        return str(value)

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        return f"{value:g}"

    return str(value)


def _bullets(items):
    """Join a list into a single readable sentence list."""

    cleaned = [
        str(item).strip()
        for item in items or []
        if str(item or "").strip()
    ]

    if not cleaned:
        return ""

    return "; ".join(cleaned)


def _bullets_sentence(items):
    """
    Join a list into one sentence that ends in a single full stop.

    Some of the lists are built from text that already ends in a
    full stop. Trimming the joined text first means the reader
    never sees a doubled full stop such as "voyage closely..".
    """

    text = _bullets(items)

    if not text:
        return ""

    return text.rstrip(". ") + "."


def _dedupe(items):
    """Keep order, drop repeats and blanks."""

    seen = set()
    result = []

    for item in items or []:

        text = str(item or "").strip()

        if not text or text in seen:
            continue

        seen.add(text)
        result.append(text)

    return result


# =========================================================
# CARGO DATA - READ FROM THE EXISTING ROUTE DATA
# =========================================================
# The cargo types and subtypes a customer can choose come from
# the same route data the route analysis already uses, so the
# list can never offer a cargo the platform cannot route.

_CARGO_CACHE = {"signature": None, "payload": None}


def cargo_options():
    """
    Cargo types and subtypes the platform can actually route.

    Returns a list of {"cargo_type", "subtypes"} entries. A
    dataset that cannot be read yields an empty list, which the
    caller reports as unavailable rather than guessing.
    """

    try:

        df = load_routes()

    except Exception:

        return _CARGO_CACHE.get("payload") or []

    try:

        signature = (
            len(df),
            df["cargo_type"].nunique(),
        )

        if _CARGO_CACHE.get("signature") == signature:

            return _CARGO_CACHE["payload"]

        options = []

        for cargo_type in sorted(
            df["cargo_type"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        ):

            if not cargo_type:
                continue

            subtypes = sorted(
                set(
                    df.loc[
                        df["cargo_type"].astype(str).str.strip()
                        == cargo_type,
                        "cargo_subtype",
                    ]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .tolist()
                )
            )

            options.append({
                "cargo_type": cargo_type,
                "subtypes": [
                    subtype
                    for subtype in subtypes
                    if subtype
                ],
            })

        _CARGO_CACHE["signature"] = signature
        _CARGO_CACHE["payload"] = options

        return options

    except Exception:

        return _CARGO_CACHE.get("payload") or []


def cargo_option_sentences():
    """One readable sentence per cargo type."""

    return [
        f"{option['cargo_type']} ({_bullets(option['subtypes'])})"
        for option in cargo_options()
    ]


def cargo_category_sentences():
    """How free-text cargo words are grouped, in plain English."""

    grouped = {}

    for keyword, category in (
        CARGO_TYPE_MAPPING or {}
    ).items():

        grouped.setdefault(category, []).append(keyword)

    return [
        f"{category}: {_bullets(sorted(words))}"
        for category, words in sorted(grouped.items())
    ]


# =========================================================
# BUSINESS RULES RENDERED FROM THE AGENTS' OWN CONSTANTS
# =========================================================

def weather_limit_sentences():
    """Every weather limit, in plain sailing English."""

    sentences = []

    for name, rule in (RISK_THRESHOLDS or {}).items():

        label = str(name).replace("_", " ")

        unit = rule.get("unit", "")

        if "severe_at_or_above" in rule:

            sentences.append(
                f"{label} is normal below "
                f"{_number(rule.get('normal_below'))} {unit} "
                f"and severe at or above "
                f"{_number(rule.get('severe_at_or_above'))} "
                f"{unit}"
            )

        elif "severe_below" in rule:

            sentences.append(
                f"{label} is normal at or above "
                f"{_number(rule.get('normal_at_or_above'))} "
                f"{unit} and severe below "
                f"{_number(rule.get('severe_below'))} {unit}"
            )

        else:

            groups = _bullets([
                (
                    f"{group_name}: "
                    + _bullets(words)
                )
                for group_name, words in rule.items()
            ])

            sentences.append(
                f"{label} is graded by the recorded "
                f"description ({groups})"
            )

    return sentences


def weather_risk_meaning_sentences():
    """What Low, Medium and High mean, from the agent itself."""

    return [
        (
            f"{RISK_LEVELS.get(level)} means "
            f"{str(RISK_SUMMARIES.get(level, '')).rstrip('. ').lower()}"
            f" The advice is: "
            f"{str(RISK_ADVISORIES.get(level, ''))}"
        )
        for level in sorted(RISK_LEVELS or {})
    ]


def customs_document_sentences():
    """The documents the customs check tracks, in plain English."""

    return [
        (
            f"{control.get('label')}: "
            f"{str(control.get('description')).rstrip('. ')}."
            f" A missing "
            f"{str(control.get('label')).lower()}"
            + (
                " stops customs clearance for this shipment."
                if control.get("critical")
                else " should be arranged, but does not stop "
                     "clearance on its own."
            )
        )
        for control in (TRACKED_CONTROLS or [])
    ]


def customs_status_meaning_sentences():
    """What each customs status means for the customer."""

    meanings = {
        "Valid": (
            "every document this lane and cargo requires is "
            "in place"
        ),
        "Warning": (
            "the shipment can proceed, but something needs your "
            "attention before clearance"
        ),
        "Action Required": (
            "clearance is on hold until the outstanding "
            "requirements are resolved"
        ),
    }

    return [
        f"{status}: {meanings.get(status, 'see the document checklist')}"
        for status in (STATUS_SEQUENCE or [])
    ]


# =========================================================
# TOPIC DEFINITIONS
# =========================================================
# `summary` is the sentence the assistant can always say without
# any lookup. `details` is the richer business description
# handed to the explanation layer. Both describe real, current
# behaviour and neither contains a technical term.
# =========================================================

def _overview_topic():
    return {
        "title": "What this platform does",
        "summary": PLATFORM_PURPOSE,
        "details": [
            PLATFORM_PURPOSE,
            "You start with a route analysis. You give an "
            "origin port, a destination port, a cargo type, a "
            "cargo subtype and how many containers you are "
            "shipping, and the platform shows the routes "
            "available on that lane with one of them "
            "recommended.",
            "Alongside the route you get a weather risk for "
            "that route and a customs check for the lane and "
            "cargo, so you can see the sailing conditions and "
            "the documents you will need.",
            "You then generate a quotation from the "
            "recommended route. When you accept it, an "
            "administrator approves it and your shipment is "
            "created and moved through the shipping stages.",
        ],
    }


def _route_topic():
    return {
        "title": "How a route is recommended",
        "summary": (
            "The platform compares every shipping route "
            "available between your two ports for your cargo "
            "and recommends the strongest one. It favours a "
            "shorter transit time first, then a shorter "
            "sailing distance, then fewer transshipment "
            "stops, because each of those reduces the time "
            "and the handling your cargo goes through."
        ),
        "details": [
            "You need an origin port, a destination port, a "
            "cargo type, a cargo subtype and a container count "
            "of at least one.",
            "Only ports that the platform actually serves can "
            "be selected.",
            "Every route on your lane that carries your cargo "
            "is scored. The recommendation is the highest "
            "scoring route, and the other routes on the lane "
            "are shown to you as alternatives so you can "
            "compare transit time, distance and the number of "
            "transshipment stops.",
            "Transshipment stops are the intermediate ports "
            "where cargo changes vessel. More stops usually "
            "means more time and more handling risk.",
            "The cargo type groups your shipment into one of "
            "the platform's cargo categories. Common cargo "
            "words are grouped as follows: "
            + _bullets_sentence(cargo_category_sentences()),
            "The recommendation never changes your cargo and "
            "never changes your quotation.",
        ],
    }


def _weather_topic():
    return {
        "title": "How the weather risk is worked out",
        "summary": (
            "The platform checks five sailing conditions on "
            "your route - wind speed, wave height, rainfall, "
            "visibility and storm risk - and rates each one. "
            "The overall weather risk is the worst of the five, "
            "reported as Low, Medium or High."
        ),
        "details": [
            "The readings come from the reference weather "
            "information the platform holds. It is "
            "reference data, not a live forecast feed.",
            "The limits used are: "
+ _bullets_sentence(weather_limit_sentences()),
            "What the levels mean: "
+ _bullets_sentence(weather_risk_meaning_sentences()),
            "The weather risk is information for your "
            "planning. It does not change your recommended "
            "route and it does not change your quotation.",
        ],
    }


def _customs_topic():
    return {
        "title": "How the customs check works",
        "summary": (
            "The platform checks which customs documents your "
            "lane and cargo require and tells you whether the "
            "shipment is clear, needs attention, or is on hold."
        ),
        "details": [
            "The check is matched on your origin port, "
            "destination port, cargo type and cargo subtype "
            "together. A port pair on its own is not enough, "
            "so the answer always matches your exact cargo.",
            "Documents checked for this lane: "
            + _bullets_sentence(customs_document_sentences()),
            (
                "Restricted cargo additionally needs a "
                f"{RESTRICTED_CONTROL_LABEL}, which brings the "
                f"total to {TRACKED_CONTROL_COUNT} checks."
            ),
            "Your document compliance is the share of those "
            "checks that are satisfied.",
            "What each status means: "
            + _bullets_sentence(
                customs_status_meaning_sentences()
            ),
            CUSTOMS_REFERENCE_NOTE,
        ],
    }


def _cargo_topic():
    return {
        "title": "Cargo you can ship",
        "summary": (
            "You choose a cargo type and then a cargo subtype "
            "that matches your goods. The platform can only "
            "route cargo it holds data for, so if your goods "
            "are not listed, that lane and cargo cannot be "
            "analysed."
        ),
        "details": [
            "Cargo types and the subtypes available under each "
            "one: "
            + _bullets_sentence(
                cargo_option_sentences()
                or ["cargo options are temporarily unavailable"]
            ),
            "The cargo subtype is what tells the platform which "
            "goods are moving. It decides which customs "
            "requirements apply and which routes on your lane "
            "can carry your shipment.",
            "If you are unsure which subtype fits, choose the "
            "one closest to the goods you are shipping and "
            "check the customs result before you book.",
        ],
    }


def _pricing_topic():
    return {
        "title": "How a quotation is built",
        "summary": (
            "A quotation is the total cost of moving your "
            "containers on the recommended route. It starts "
            "from the base freight for that route, adds the fuel, "
            "port and risk charges, adjusts for current demand "
            "on the route, and then adds the platform's margin "
            "to give you a quoted selling price."
        ),
        "details": [
            "Every rate is per container, so a quotation for "
            "more than one container scales in proportion to "
            "the number of containers.",
            "The quotation is fixed for your request. The "
            "route, weather and customs checks do not change "
            "it after it has been produced.",
            "You see the total, the number of containers and "
            "the route it covers.",
            "When you accept a quotation it goes for "
            "administrator approval. Once it is approved your "
            "shipment is created and you can track it.",
        ],
    }


def _shipment_topic(status_flow=None):
    flow = list(status_flow or [])

    return {
        "title": "How shipment tracking works",
        "summary": (
            "A shipment exists once your quotation has been "
            "accepted and approved. From then on you can follow "
            "it stage by stage from booking through to delivery."
        ),
        "details": [
            "The stages a shipment moves through are: "
            + _bullets_sentence(flow),
            "Each stage is recorded with a date, so you can "
            "see how far your shipment has progressed and when "
            "it reached its current stage.",
            "Your shipment keeps a copy of the quotation you "
            "accepted, the route it is using, the weather "
            "assessment for that route and the customs "
            "assessment, so you can always see why it was "
            "booked the way it was.",
            "What tracking does not include: your shipment "
            "record holds no live position, no live estimated "
            "arrival time and no vessel name. It is a "
            "booking-to-delivery progress record, not a live "
            "position feed.",
        ],
    }


def _platform_use_topic():
    return {
        "title": "Using this platform",
        "summary": (
            "Open Route Intelligence to run a route analysis, "
            "Route History to review or reuse an analysis you "
            "have already run, Quotation to price it, and "
            "Shipments to follow your shipment once it has "
            "been approved."
        ),
        "details": [
            "To analyse a route: open Route Intelligence, "
            "choose your origin port and destination port, "
            "choose your cargo type and cargo subtype, enter "
            "how many containers you are shipping, and run the "
            "analysis. You get the recommended route, the "
            "alternatives, the weather risk and the customs "
            "check for that lane.",
            "To get a quotation: open a saved analysis from "
            "Route History and generate the quotation from it. "
            "The quotation is built from the recommended route "
            "on that analysis.",
            "To check customs requirements: run a route "
            "analysis with a cargo subtype selected. The "
            "customs check needs the origin, destination, "
            "cargo type and cargo subtype, so it appears "
            "alongside the route result.",
            "To check your shipment: open Shipments. Each of "
            "your shipments shows its current stage and the "
            "date it reached that stage.",
            "To understand the weather risk: look at the "
            "weather result on your route analysis. It shows "
            "the overall risk, the individual readings and what "
            "that level means for your sailing.",
            "To send us feedback, use the Feedback page. Your "
            "rating and comment go to the platform "
            "administrators.",
        ],
    }


def _admin_area_topic():
    return {
        "title": "Administrator area",
        "summary": (
            "An administrator approves quotations, moves "
            "shipments through their stages, and reviews "
            "customs, pricing, customer and feedback "
            "information for the whole platform."
        ),
        "details": [
            "Quotations waiting for approval, with the ability "
            "to approve them, which creates the shipment, or "
            "reject them with a reason.",
            "Every shipment on the platform, with the ability "
            "to move it to the next stage.",
            "Pricing and margin information for every route.",
            "Customs requirements for every lane and cargo.",
            "Customer accounts and the feedback they have "
            "submitted.",
        ],
    }


TOPIC_BUILDERS = {
    TOPIC_OVERVIEW: _overview_topic,
    TOPIC_ROUTE: _route_topic,
    TOPIC_WEATHER: _weather_topic,
    TOPIC_CUSTOMS: _customs_topic,
    TOPIC_CARGO: _cargo_topic,
    TOPIC_PRICING: _pricing_topic,
    TOPIC_SHIPMENT: _shipment_topic,
    TOPIC_PLATFORM_USE: _platform_use_topic,
    TOPIC_ADMIN_AREA: _admin_area_topic,
}


# =========================================================
# QUESTION CLASSIFICATION
# =========================================================
# The same words mean two different things. "Route" can be a
# business process ("how does the route recommendation work?")
# or a value belonging to the customer ("why was this route
# recommended?"). The markers below separate the two
# deterministically.

# Words that mean "the business process itself".

MECHANISM_MARKERS = (
    "how does",
    "how do i",
    "how do",
    "how can",
    "how to",
    "how is",
    "how are",
    "why is",
    "why does",
    "why do",
    "what does",
    "what do",
    "explain",
    "describe",
    "what happens",
    "tell me",
    "walk me through",
    "guide",
    "steps",
    "process",
    "mean",
    "means",
    "meaning",
    "understand",
    "work",
    "works",
    "working",
    "calculated",
    "why",
)

# Words that mean "the customer's own stored record". These are
# deliberately narrow. "do i need" is not here, because it asks
# about a business requirement rather than about a stored
# value.

RECORD_MARKERS = (
    "my ",
    "mine",
    "this route",
    "this shipment",
    "this quotation",
    "this cargo",
    "this booking",
    "was recommended",
    "was chosen",
    "for me",
    "do i have",
    "have i",
    "did i",
    "am i tracking",
    "missing",
    "give me",
    "show me",
    "latest",
    "recent",
    "currently",
    "right now",
    "at the moment",
)


def _contains_any(question, markers):

    for marker in markers or ():

        if marker in question:
            return True

    return False


def _is_mechanism_question(question):

    return _contains_any(question, MECHANISM_MARKERS)


def _is_record_question(question):

    return _contains_any(question, RECORD_MARKERS)


# Platform-usage shape. These questions ask where to click, so
# they are answered with guidance rather than with the
# customer's stored numbers.

USAGE_PATTERNS = (
    re.compile(r"^how\s+(?:do|can|would|should|might)\s+i\b"),
    re.compile(r"^how\s+to\b"),
    re.compile(r"^where\s+(?:can|do|should)\s+i\b"),
    re.compile(r"^what\s+should\s+i\b"),
    re.compile(r"^(?:guide|walk|take)\s+me\b"),
    re.compile(r"^can\s+you\s+(?:show|tell|guide|walk)\b"),
    re.compile(r"^help\s+me\b"),
    re.compile(r"^steps?\s+to\b"),
)


def is_usage_question(question):
    """True when the question asks how to use the platform."""

    text = str(question or "").strip().lower()

    return any(
        pattern.match(text)
        for pattern in USAGE_PATTERNS
    )


# Topic keyword tables. These name a BUSINESS topic.

TOPIC_KEYWORDS = {

    TOPIC_OVERVIEW: (
        "what does this platform",
        "what can this platform",
        "what can the platform",
        "what can i do",
        "what can i ask",
        "what do i do",
        "what is this platform",
        "what is the platform",
        "capabilities",
        "help me",
        "how can i use",
        "what are the options",
        "what services",
    ),

    TOPIC_ROUTE: (
        "route",
        "transit",
        "transshipment",
        "distance",
        "direct sailing",
        "alternative",
        "how many days",
        "how long",
        "eta",
        "faster",
        "fastest",
        "shorter",
        "best option",
        "lane",
    ),

    TOPIC_WEATHER: (
        "weather",
        "storm",
        "wind",
        "wave",
        "rain",
        "rainfall",
        "cyclone",
        "typhoon",
        "hurricane",
        "rough",
        "visibility",
        "sea state",
        "forecast",
        "sailing condition",
    ),

    TOPIC_CUSTOMS: (
        "customs",
        "certificate of origin",
        "packing list",
        "commercial invoice",
        "hs code",
        "hscode",
        "restricted",
        "clearance",
        "cleared",
        "compliance",
        "custom",
        "permit",
        "duty",
        "tariff",
        "broker",
    ),

    TOPIC_CARGO: (
        "cargo",
        "cargo type",
        "cargo subtype",
        "container",
        "containers",
        "reefer",
        "dry cargo",
        "liquid",
        "grain",
        "chemical",
        "machinery",
        "textile",
        "perishable",
        "hazardous",
        "bulk",
        "general cargo",
        "what can i ship",
        "can i ship",
    ),

    TOPIC_PRICING: (
        "quotation",
        "quote",
        "pricing",
        "price",
        "cost",
        "costs",
        "how much",
        "charge",
        "charges",
        "freight",
        "surcharge",
        "invoice",
        "total",
        "expensive",
        "cheapest",
        "accept",
    ),

    TOPIC_SHIPMENT: (
        "shipment",
        "shipping",
        "delivery",
        "delivered",
        "deliver",
        "tracking",
        "track",
        "consignment",
        "booking",
        "cargo ready",
        "vessel departed",
        "arrived",
        "where is",
    ),

    TOPIC_PLATFORM_USE: (
        "how do i",
        "how to",
        "how can i",
        "where can i",
        "what should i",
        "steps",
        "guide",
        "get started",
        "walk me through",
        "navigate",
        "use the platform",
        "on this platform",
        "find my",
        "open my",
        "check my",
        "submit my",
    ),

    TOPIC_ADMIN_AREA: (
        "admin",
        "administrator",
        "approval",
        "approve",
        "reject",
        "moderator",
        "escalate",
    ),
}


def select_topics(question, scope="user"):
    """Which business topics does this question mention?"""

    text = str(question or "").strip().lower()

    if not text:
        return []

    matched = []

    for topic, keywords in TOPIC_KEYWORDS.items():

        if any(
            keyword in text
            for keyword in keywords
        ):
            matched.append(topic)

    return matched


def classify_project_question(question, scope="user"):
    """
    Decide how the business knowledge relates to the question.

    mode
    ----
    "system"
        The question is about how the business process works.
        Only the business description is answered, so a
        question about the route recommendation is never
        diluted with the customer's own numbers.

    "mixed"
        The question mentions both the process and the
        customer's own record. Both are answered, the stored
        record first.

    "none"
        The question is not about the process. The existing
        data behaviour is unchanged.
    """

    text = str(question or "").strip().lower()

    if is_usage_question(text):

        return {
            "topics": [TOPIC_PLATFORM_USE],
            "mode": "system",
            "is_record_question": False,
            "is_mechanism_question": True,
            "is_usage_question": True,
        }

    topics = select_topics(text, scope=scope)

    if not topics:
        return {
            "topics": [],
            "mode": "none",
            "is_record_question": _is_record_question(text),
            "is_mechanism_question": _is_mechanism_question(text),
            "is_usage_question": False,
        }

    is_record = _is_record_question(text)

    # A question that names a topic but asks NEITHER "how does
    # this work" NOR "what is mine" is a plain question about a
    # business value, so it is reported as "system" WITHOUT the
    # mechanism flag being set. The assistant upgrades it to
    # "mixed" when the caller owns a record, which keeps the
    # stored value first. A customer with no records still gets
    # the plain explanation.

    mode = "mixed" if is_record else "system"

    # A genuine question about the customer's own record is
    # answered with the stored value, not with a description
    # of the process that produced it.

    if mode == "mixed":

        topics = [
            topic
            for topic in topics
            if topic not in DATA_MIRRORING_TOPICS
        ]

    if not topics:
        mode = "none"

    return {
        "topics": topics,
        "mode": mode,
        "is_record_question": is_record,
        "is_mechanism_question": _is_mechanism_question(text),
        "is_usage_question": False,
    }


# =========================================================
# KNOWLEDGE ASSEMBLY
# =========================================================

def _build_topic(topic, scope, status_flow=None):
    """
    Render one topic, withholding admin-only content from a
    normal customer.
    """

    if topic in ADMIN_ONLY_TOPICS and scope != "admin":

        return {
            "title": "Administrator area",
            "summary": ADMIN_BOUNDARY_NOTE,
            "details": [ADMIN_BOUNDARY_NOTE],
            "restricted": True,
        }

    builder = TOPIC_BUILDERS.get(topic)

    if not builder:
        return None

    if topic == TOPIC_SHIPMENT:

        content = builder(status_flow=status_flow)

    else:

        content = builder()

    content = dict(content or {})
    content["restricted"] = False

    return content


def build_project_knowledge(
    question,
    scope="user",
    status_flow=None
):
    """
    Build the business description for one question.

    Returns
    -------
    dict
        {
          "mode": "system" | "mixed" | "none",
          "topics": [...],
          "admin_only": bool,
          "mirrors_stored_value": bool,
          "is_record_question": bool,
          "is_mechanism_question": bool,
          "is_usage_question": bool,
          "project_name": str,
          "purpose": str,
          "grounding_rule": str,
          "sections": {topic: {...}},
          "deterministic_answer": str | None
        }
    """

    classification = classify_project_question(
        question, scope=scope
    )

    topics = classification["topics"]

    # A customer asking about the administrator area is told the
    # boundary, not the contents of that area.

    if scope != "admin" and any(
        topic in ADMIN_ONLY_TOPICS
        for topic in topics
    ):

        sections = _ordered_sections(
            [TOPIC_ADMIN_AREA],
            scope,
            status_flow,
        )

    elif topics:

        sections = _ordered_sections(
            topics, scope, status_flow
        )

    else:

        sections = {}

    return {
        "mode": classification["mode"],
        "topics": topics,
        "admin_only": any(
            topic in ADMIN_ONLY_TOPICS
            for topic in topics
        ),
        "mirrors_stored_value": any(
            topic in DATA_MIRRORING_TOPICS
            for topic in topics
        ),
        "is_record_question": bool(
            classification["is_record_question"]
        ),
        "is_mechanism_question": bool(
            classification["is_mechanism_question"]
        ),
        "is_usage_question": bool(
            classification["is_usage_question"]
        ),
        "project_name": PLATFORM_NAME,
        "purpose": PLATFORM_PURPOSE,
        "grounding_rule": GROUNDING_RULE,
        "sections": sections,
        "deterministic_answer": _deterministic_answer(
            sections
        ),
    }


def _ordered_sections(topic_keys, scope, status_flow):
    """Render the selected topics in a stable, readable order."""

    rendered = {}

    for topic in topic_keys:

        section = _build_topic(
            topic, scope=scope, status_flow=status_flow
        )

        if section:
            rendered[topic] = section

    return rendered


def _deterministic_answer(sections):
    """
    One clear answer built from the selected topics.

    The summary opens the answer and the grounded details
    follow, so the customer gets the actual limits, documents,
    stages and cargo values rather than a promise that the
    information exists.
    """

    if not sections:
        return ""

    parts = []

    for section in sections.values():

        summary = str(
            section.get("summary") or ""
        ).strip()

        if summary and summary not in parts:
            parts.append(summary)

        for detail in section.get("details") or []:

            text = str(detail or "").strip()

            if text and text not in parts:
                parts.append(text)

    if not parts:
        return ""

    return " ".join(parts)


# =========================================================
# BUSINESS RULE BLOCKS
# =========================================================
# Attached beside the customer's stored values so an
# explanation can always quote the ACTUAL rule or limit that
# produced the value. Every entry is written in business
# language: no field names, no formulas, no file names.

def route_reference():
    return {
        "rule": (
            "The recommended route is the highest scoring "
            "route available on the lane for your cargo. The "
            "score favours a shorter transit time first, then "
            "a shorter sailing distance, then fewer "
            "transshipment stops."
        ),
        "score_weights": dict(ROUTE_SCORE_WEIGHTS),
        "weighing": [
            "shorter transit time is the strongest factor",
            "fewer transshipment stops is the next strongest",
            "a shorter sailing distance also improves the "
            "score",
        ],
        "transshipment_note": (
            "A transshipment is an intermediate port where "
            "cargo changes vessel. More stops usually means "
            "more time in transit and more handling."
        ),
        "tie_breakers": [
            "shorter transit time",
            "shorter sailing distance",
            "fewer transshipment stops",
        ],
        "cargo_categories": cargo_category_sentences(),
        "note": (
            "Only the recommended route is stored for a "
            "completed analysis, so alternative routes cannot "
            "be compared afterwards unless the analysis that "
            "produced them is reopened."
        ),
    }


def weather_reference():
    return {
        "measured_readings": [
            "wind speed",
            "wave height",
            "rainfall",
            "visibility",
            "storm risk",
        ],
        "limits": weather_limit_sentences(),
        "thresholds": dict(RISK_THRESHOLDS),
        "risk_levels": {
            str(level): RISK_LEVELS.get(level)
            for level in sorted(RISK_LEVELS or {})
        },
        "what_the_levels_mean": weather_risk_meaning_sentences(),
        "advice_by_level": {
            str(level): str(RISK_ADVISORIES.get(level, ""))
            for level in sorted(RISK_LEVELS or {})
        },
        "rule": (
            "each reading is graded, and the overall weather "
            "risk is the worst of the five readings, reported "
            "as Low, Medium or High"
        ),
        "data_note": WEATHER_REFERENCE_NOTE,
    }


def customs_reference():
    return {
        "match_keys": [
            "origin",
            "destination",
            "cargo_type",
            "cargo_subtype",
        ],
        "match_rule": (
            "all four must match, so two shipments on the "
            "same lane carrying different cargo are never "
            "given the same answer"
        ),
        "tracked_controls": [
            {
                "key": control.get("key"),
                "label": control.get("label"),
                "description": control.get("description"),
                "critical": bool(control.get("critical")),
            }
            for control in (TRACKED_CONTROLS or [])
        ],
        "document_count": TRACKED_CONTROL_COUNT,
        "restricted_document": RESTRICTED_CONTROL_LABEL,
        "compliance_rule": (
            "document compliance is the share of the required "
            "checks that are satisfied"
        ),
        "status_sequence": list(STATUS_SEQUENCE or []),
        "status_meaning": customs_status_meaning_sentences(),
        "status_rule": (
            "a missing critical document stops clearance, "
            "other missing documents raise a warning, and a "
            "complete shipment is valid"
        ),
        "data_note": CUSTOMS_REFERENCE_NOTE,
    }


def cargo_reference():
    return {
        "cargo_types": cargo_options(),
        "how_cargo_is_used": (
            "the cargo type places your shipment in one of the "
            "platform's cargo categories, and the cargo "
            "subtype decides which customs requirements apply "
            "and which routes on your lane can carry it"
        ),
    }


def pricing_reference():
    reference = {
        "how_the_total_is_built": [
            "the base freight for the recommended route",
            "plus the fuel surcharge, the port charge and the "
            "risk surcharge for that route",
            "adjusted for the current demand on the route",
            "then the platform's margin is added to give the "
            "quoted total",
        ],
        "per_container_rule": (
            "every rate is per container, so the quotation "
            "scales in proportion to the number of containers"
        ),
        "fixed_rule": (
            "a quotation does not change after it has been "
            "produced, and the route, weather and customs "
            "checks do not change it"
        ),
        "after_accepting": (
            "an accepted quotation goes for administrator "
            "approval. Once it is approved, the shipment is "
            "created and can be tracked."
        ),
    }

    reference.update(PRICING_FORMULAS)

    return reference


def shipment_reference(status_flow=None):
    return {
        "status_flow": list(status_flow or []),
        "how_progress_is_recorded": (
            "every stage change is recorded with the stage and "
            "the date it happened, and that history is what you "
            "see on your shipment"
        ),
        "what_it_does_not_show": (
            "a shipment record holds no live position, no live "
            "estimated arrival time and no vessel name. It is "
            "a booking-to-delivery progress record, not a "
            "live position feed."
        ),
    }


def platform_use_reference():
    return {
        "pages": [
            "Route Intelligence - run a route analysis",
            "Route History - review an analysis and generate a "
            "quotation from it",
            "Quotation - the priced offer, which you can accept",
            "Shipments - follow your shipment stage by stage",
            "Feedback - rate the platform and send a comment",
        ],
        "rule": (
            "a route analysis needs an origin port, a "
            "destination port, a cargo type, a cargo subtype "
            "and a container count"
        ),
    }


REFERENCE_BUILDERS = {
    TOPIC_ROUTE: route_reference,
    TOPIC_WEATHER: weather_reference,
    TOPIC_CUSTOMS: customs_reference,
    TOPIC_CARGO: cargo_reference,
    TOPIC_PRICING: pricing_reference,
    TOPIC_SHIPMENT: shipment_reference,
    TOPIC_PLATFORM_USE: platform_use_reference,
}


# Keys that reproduce an agent's own internals exactly. They
# exist so the agent regression suite can prove a description
# has not drifted from the code it explains, but they name
# internal quantities and so they are removed before a
# reference is handed to the explanation layer or returned in
# a response.

INTERNAL_REFERENCE_KEYS = (
    "score_weights",
    "thresholds",
    "operating_cost_formula",
    "demand_adjusted_cost_formula",
    "selling_price_formula",
)


def _customer_safe_reference(reference):
    """Strip the agent's internal quantities from a reference."""

    if not isinstance(reference, dict):
        return reference

    safe = {
        key: value
        for key, value in reference.items()
        if key not in INTERNAL_REFERENCE_KEYS
    }

    # The document list keeps its business label and meaning,
    # but not the internal column key it is stored under.

    controls = safe.get("tracked_controls")

    if isinstance(controls, list):

        safe["tracked_controls"] = [
            {
                "label": control.get("label"),
                "description": control.get("description"),
                "critical": control.get("critical"),
            }
            for control in controls
            if isinstance(control, dict)
        ]

    # The customs match keys are internal field names; the
    # business meaning is already in `match_rule`.

    safe.pop("match_keys", None)

    return safe


def build_agent_reference(
    question,
    scope="user",
    status_flow=None,
    intents=()
):
    """
    Which business rule belongs to the topic that was actually
    retrieved?

    `intents` are passed in so this module never needs its own
    copy of the intent keyword tables.

    The agent's internal quantities are always removed, so the
    result is safe to hand to the explanation layer and to
    return in a response. The exact constants stay available
    through the individual `*_reference()` functions, which the
    agent regression suite calls directly.
    """

    if not intents:

        return {}

    references = {}

    for intent in intents or ():

        builder = REFERENCE_BUILDERS.get(intent)

        if not builder:
            continue

        try:

            if intent == TOPIC_SHIPMENT:

                references[intent] = builder(
                    status_flow=status_flow
                )

            else:

                references[intent] = builder()

        except Exception:

            references[intent] = None

    return {
        intent: _customer_safe_reference(value)
        for intent, value in references.items()
        if value
    }