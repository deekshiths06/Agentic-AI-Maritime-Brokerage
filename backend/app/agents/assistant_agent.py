# =========================================================
# MARITIME ASSISTANT AGENT
# =========================================================
# Purpose
# -------
# Answer a shipper's (or an administrator's) question about a
# REAL shipment by retrieving the ACTUAL structured results of
# the existing modules and handing those facts to Gemini for a
# natural language explanation.
#
# Grounding contract
# ------------------
# The assistant NEVER calculates or invents a business value.
# Every fact it can speak about is produced by an existing,
# unchanged module:
#
#   Route Agent    -> recommended route, score, reasons
#   Weather Agent  -> weather risk, risk reason, advisory
#   Customs Agent  -> customs status, compliance %, documents
#   Quotation      -> stored pricing / margin of a real record
#   Shipments      -> the stored shipment workflow status
#   Admin views    -> the existing admin collections
#
# This module is a READER. It never writes to MongoDB, never
# re-runs a route score, never re-prices a quotation and never
# changes a customs requirement.
#
# Flow
# ----
#   Question
#      |
#      v
#   Intent detection (deterministic, keyword based)
#      |
#      v
#   Context assembly from EXISTING project data
#   (scoped to the authenticated principal)
#      |
#      v
#   { facts, deterministic_answer }
#      |
#      v
#   Gemini explains the facts (optional)
#
# TWO KINDS OF CONTEXT
# --------------------
# 1. Stored results ("why was this route recommended?") come
#    from the caller's own records, exactly as before.
#
# 2. Project knowledge ("what does this project do?",
#    "explain the Route Agent") comes from the injected
#    `knowledge_provider`. That provider is built from
#    app/services/project_context.py, which imports the
#    agents' OWN constants, so a weather limit or a customs
#    control can never drift from the code that uses it.
#
# This module still imports nothing itself: the caller injects
# both the Customs Agent entry point and the knowledge
# provider, exactly as it injects `analyze`.
#
#
# DETERMINISTIC ANSWER ALWAYS EXISTS
# ----------------------------------
# `deterministic_answer` is written only from the retrieved
# facts. It is returned even when Gemini is unconfigured,
# unreachable or slow, so the assistant degrades to a correct,
# plain answer instead of failing.
#
# SECURITY
# --------
# * The caller passes ONLY records the backend already scoped
#   to the authenticated principal (the user's own shipments
#   and route history, or the admin-only collections).
# * A normal user never receives another user's data, admin
#   counters, or internal margin figures, because those fields
#   are simply never placed in the user fact set.
# * No credential, key, secret or connection string is ever
#   read by this module.
# =========================================================

import logging

from app.agents.assistant_scope import (
    REFUSAL_ANSWER,
    SCOPE_BUSINESS,
    classify_question,
)


logger = logging.getLogger("uvicorn.error")


# =========================================================
# SCOPE GATE
# =========================================================
# Every question is classified BEFORE any intent detection,
# any database read and any Gemini call. A question about
# code, an internal detail or an unrelated topic is refused
# here, so a refused question can never reach a data source or
# the explanation service.
#
# The refusal is returned in the same shape as every other
# answer, so the caller needs no special case. `scope` is
# reported separately for the caller's own bookkeeping.

def _refusal(question, scope):
    """Refusal payload for an out-of-scope question."""

    return {
        "intents": ["refused"],
        "focus": {
            "has_shipment": False,
            "has_route_analysis": False,
            "shipment_count": 0,
            "route_analysis_count": 0,
        },
        "facts": {
            "refusal": {
                "reason": REFUSAL_ANSWER,
            },
        },
        "deterministic_answer": REFUSAL_ANSWER,
        "scope": scope,
        "out_of_scope": True,
    }


# =========================================================
# INTENTS
# =========================================================
# The platform questions map onto a small, fixed set of
# intents. Every intent maps onto a section of real project
# data, so an unrecognised question degrades to a "not
# available" answer rather than to a guess.

INTENT_ROUTE = "route"
INTENT_CARGO = "cargo"
INTENT_WEATHER = "weather_risk"
INTENT_CUSTOMS = "customs"
INTENT_QUOTATION = "quotation"
INTENT_SHIPMENT = "shipment_status"
INTENT_PLATFORM_USE = "platform_use"
INTENT_ADMIN_STATS = "admin_stats"
INTENT_ADMIN_CUSTOMS = "admin_customs"
INTENT_ADMIN_QUOTATIONS = "admin_quotations"
INTENT_ADMIN_LOGINS = "admin_logins"
INTENT_ADMIN_HEALTH = "admin_health"
INTENT_HELP = "help"

# Keyword tables. Order does not decide the winner: a question
# can legitimately need several sections, so every matching
# intent is collected and each one contributes its facts.

INTENT_KEYWORDS = {

    # -------------------------------------------------
    # USER INTENTS
    # -------------------------------------------------

    INTENT_CUSTOMS: (
        "customs",
        "custom",
        "certificate of origin",
        "certificate",
        "packing list",
        "commercial invoice",
        "hs code",
        "hscode",
        "harmonised",
        "harmonized",
        "restricted cargo",
        "clearance",
        "compliance",
        "document",
        "paperwork",
    ),

    INTENT_WEATHER: (
        "weather",
        "risk",
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
    ),

    INTENT_QUOTATION: (
        "quotation",
        "quote",
        "pricing",
        "price",
        "cost",
        "how much",
        "total",
        "charge",
        "freight",
        "surcharge",
        "margin",
        "invoice",
        "pay",
        "expensive",
        "cheap",
    ),

    INTENT_SHIPMENT: (
        "shipment",
        "shipment status",
        "status of my",
        "where is my",
        "delivered",
        "delivery",
        "in transit",
        "booking",
        "tracking",
        "cargo ready",
        "vessel departed",
    ),

    INTENT_ROUTE: (
        "route",
        "recommend",
        "best route",
        "which route",
        "alternative",
        "transit",
        "transshipment",
        "distance",
        "eta",
        "fastest",
        "direct",
    ),

    INTENT_CARGO: (
        "cargo",
        "cargo type",
        "cargo subtype",
        "container",
        "containers",
        "reefer",
        "dry cargo",
        "general cargo",
        "bulk",
        "hazardous",
        "perishable",
        "liquid cargo",
        "grain",
        "chemical",
        "machinery",
        "textile",
        "what can i ship",
        "can i ship",
        "what cargo",
        "goods",
        "commodity",
    ),

    INTENT_PLATFORM_USE: (
        "how do i",
        "how to",
        "how can i",
        "where can i",
        "what should i",
        "how do we",
        "where do i",
        "steps to",
        "walk me through",
        "guide me",
        "get started",
        "navigate",
        "use the platform",
        "route intelligence",
        "route history",
        "find my",
        "open my",
        "check my",
        "submit my",
        "feedback",
    ),

    # -------------------------------------------------
    # ADMIN INTENTS
    # -------------------------------------------------

    INTENT_ADMIN_STATS: (
        "how many users",
        "active users",
        "total users",
        "how many shipments",
        "active shipments",
        "how many",
        "user count",
        "shipment count",
        "platform stats",
        "analytics",
        "overview",
    ),

    INTENT_ADMIN_CUSTOMS: (
        "customs warning",
        "customs issue",
        "customs problem",
        "customs alert",
        "customs dataset",
        "customs record",
        "customs status",
        "action required",
    ),

    INTENT_ADMIN_QUOTATIONS: (
        "quotation activity",
        "recent quotation",
        "recent quote",
        "quotation trend",
        "quotations today",
    ),

    INTENT_ADMIN_LOGINS: (
        "logged in",
        "login today",
        "logins today",
        "sign in today",
        "login activity",
    ),

    INTENT_ADMIN_HEALTH: (
        "system",
        "system issue",
        "system health",
        "any issues",
        "error",
        "healthy",
        "outage",
        "down",
        "working",
    ),
}


# Admin-only intents. A user question containing one of these
# keywords is never answered with admin data; the intent is
# simply dropped before the facts are assembled.

ADMIN_ONLY_INTENTS = {
    INTENT_ADMIN_STATS,
    INTENT_ADMIN_CUSTOMS,
    INTENT_ADMIN_QUOTATIONS,
    INTENT_ADMIN_LOGINS,
    INTENT_ADMIN_HEALTH,
}


# A general question (a greeting, or "what can you do")
# carries no topic. It is answered with the capability
# description instead of every section of the record.

GENERAL_KEYWORDS = (
    "hello",
    "hi ",
    "hey",
    "help",
    "what can you",
    "what do you",
    "who are you",
    "what are you",
    "capabilities",
    "good morning",
    "good afternoon",
    "good evening",
)


# =========================================================
# SMALL FORMAT HELPERS
# =========================================================

def _text(value, fallback="-"):

    """Trimmed string for a fact value."""

    cleaned = str(
        value if value is not None else ""
    ).strip()

    return cleaned or fallback


def _number(value):

    """Finite float, or None. Never raises."""

    if value is None or isinstance(value, bool):

        return None

    try:

        number = float(value)

    except (TypeError, ValueError):

        return None

    if number != number or number in (
        float("inf"), float("-inf")
    ):

        return None

    return number


def _money(value):

    """USD amount as it appears in the existing quotation UI."""

    number = _number(value)

    if number is None:

        return None

    return f"${number:,.2f}"


def _integer(value):

    """Integer text for counters and durations."""

    number = _number(value)

    if number is None:

        return None

    return str(int(round(number)))


def _percent(value):

    """Percentage text."""

    number = _number(value)

    if number is None:

        return None

    return f"{number:g}%"


def _list(values, limit=None):

    """Readable list text, never None."""

    items = [
        _text(item, "")
        for item in (values or [])
    ]

    items = [item for item in items if item]

    if not items:

        return None

    if limit:

        items = items[:limit]

    return ", ".join(items)


# =========================================================
# INTENT DETECTION
# =========================================================

def detect_intents(question, allow_admin=False):

    """
    Return every intent implied by a question.

    Parameters
    ----------
    question : str
        The raw user (or admin) question.
    allow_admin : bool
        True only for an authenticated administrator. Admin
        intents are discarded when this is False, so a normal
        user can never trigger an admin data lookup.

    Returns
    -------
    list[str]
    """

    text = str(question or "").strip().lower()

    matched = []

    for intent, keywords in INTENT_KEYWORDS.items():

        if not allow_admin and intent in ADMIN_ONLY_INTENTS:

            continue

        if any(keyword in text for keyword in keywords):

            matched.append(intent)

    # -------------------------------------------------
    # GENERAL QUESTION SHORT-CIRCUIT
    #
    # A greeting or a "what can you do" question has no
    # topic, so it must not be answered by dumping every
    # section of the record.
    # -------------------------------------------------

    if any(keyword in text for keyword in GENERAL_KEYWORDS):

        return [INTENT_HELP]

    return matched


# =========================================================
# FOCUS RECORD SELECTION
# =========================================================
# "Why was THIS route recommended?" only means something for
# one shipment. The focus record is chosen in this order:
#
#   1. an explicitly referenced shipment id
#   2. an explicitly referenced route id
#   3. the most recent shipment
#   4. the most recent route analysis
#
# When nothing is available the assistant says so instead of
# describing a shipment that does not exist.

def select_focus_record(
    shipments,
    history,
    shipment_id="",
    route_id=""
):

    """
    Choose the shipment the question is about.

    Returns
    -------
    (shipment | None, history_record | None)
    """

    wanted_shipment = str(shipment_id or "").strip()

    wanted_route = str(route_id or "").strip()

    chosen_shipment = None

    # -------------------------------------------------
    # AN EXPLICIT REFERENCE THAT MATCHES NOTHING STAYS UNMATCHED
    #
    # When the caller names a shipment or a route and neither is
    # in their own records, the assistant must not silently fall
    # back to their most recent shipment and answer about that
    # instead. The question was about a specific thing, so the
    # honest answer is that it was not found.
    # -------------------------------------------------

    explicit_reference_missed = False

    if wanted_shipment:

        for shipment in shipments or []:

            if str(
                shipment.get("shipment_id", "")
            ).strip() == wanted_shipment:

                chosen_shipment = shipment
                break

        if chosen_shipment is None:

            explicit_reference_missed = True

    if (
        chosen_shipment is None
        and not explicit_reference_missed
        and wanted_route
    ):

        for shipment in shipments or []:

            if str(
                shipment.get("route_id", "")
            ).strip() == wanted_route:

                chosen_shipment = shipment
                break

        if chosen_shipment is None:

            explicit_reference_missed = True

    if (
        chosen_shipment is None
        and not explicit_reference_missed
        and shipments
    ):

        chosen_shipment = shipments[0]

    # -------------------------------------------------
    # LINKED ROUTE ANALYSIS
    #
    # The quotation of a shipment lives on its route analysis
    # record, so the matching history record is preferred
    # when one exists.
    # -------------------------------------------------

    chosen_history = None

    linked_ids = []

    if chosen_shipment:

        linked_ids.append(_text(
            chosen_shipment.get("quotation_id"), ""
        ))

        linked_ids.append(_text(
            chosen_shipment.get("route_id"), ""
        ))

    if wanted_route:

        linked_ids.append(wanted_route)

    for link in linked_ids:

        if not link:

            continue

        for record in history or []:

            if _text(record.get("record_id"), "") == link:

                chosen_history = record
                break

            if _text(record.get("route_id"), "") == link:

                chosen_history = record
                break

        if chosen_history:

            break

    if (
        chosen_history is None
        and chosen_shipment is None
        and history
        and not explicit_reference_missed
    ):

        chosen_history = history[0]

    if (
        chosen_history is None
        and chosen_shipment is not None
        and history
    ):

        chosen_history = history[0]

    return chosen_shipment, chosen_history


# =========================================================
# FACT BUILDERS - ROUTE
# =========================================================
# Read-only projection of what the Route Agent already
# returned. No score is recomputed.

def build_route_facts(
    shipment,
    history_record,
    reference=None
):

    """Route Agent facts for the focus shipment."""

    source = shipment or history_record or {}

    recommended = None

    if history_record:

        recommended = {
            "route_id": history_record.get("route_id"),
            "route_name": history_record.get("route_name"),
            "transit_days": history_record.get("transit_days"),
            "distance_nm": history_record.get("distance_nm"),
            "transshipments": history_record.get(
                "transshipments"
            ),
            "route_score": history_record.get("route_score"),
            "routes_evaluated": history_record.get(
                "total_available_routes"
            ),
        }

    facts = {
        "origin": _text(source.get("origin"), None),
        "destination": _text(
            source.get("destination"), None
        ),
        "cargo_type": _text(source.get("cargo_type"), None),
        "cargo_subtype": _text(
            source.get("cargo_subtype"), None
        ),
        "containers": _integer(source.get("containers")),
        "recommended_route": recommended,

        # The Route Agent's own `reasons` list is stored by
        # the existing history record. It is echoed only when
        # present so the assistant explains the real ranking
        # narrative.
        "recommendation_reasons": (
            history_record.get("route_reasons")
            if isinstance(
                history_record, dict
            )
            else None
        ),

        # The full ranked list is NOT stored on the history
        # record, only the recommended route. Saying so keeps
        # the assistant from inventing a comparison it does
        # not have.
        "alternatives_available": False,
        "alternatives_note": (
            "Only the recommended route is stored on this "
            "record, so there are no alternative routes to "
            "compare against. The number of routes that were "
            "evaluated and the reasons recorded when it was "
            "chosen are the stored comparison."
        ),
    }

    if reference:

        facts["decision_reference"] = reference

    return facts


def route_answer(facts):

    """Deterministic route explanation."""

    recommended = facts.get("recommended_route") or {}

    origin = facts.get("origin")
    destination = facts.get("destination")

    if not recommended.get("route_id"):

        return (
            "I do not have a route analysis to explain yet. "
            "Run a route analysis from Route Intelligence and "
            "I can walk you through the recommendation."
        )

    lane = f"{origin} to {destination}"

    route_name = _text(recommended.get("route_name"), "")

    # The stored route_name repeats the lane, so it is only
    # used when it adds something the lane does not already
    # say.
    if route_name.lower() == lane.lower():

        route_name = ""

    headline = (
        f"Your recommended route for {lane} is "
        f"{_text(recommended.get('route_id'))}"
    )

    if route_name:

        headline += f", {route_name}"

    parts = [headline + "."]

    details = []

    transit = _integer(recommended.get("transit_days"))

    if transit:

        details.append(f"{transit} days transit")

    distance = _integer(recommended.get("distance_nm"))

    if distance:

        details.append(f"{distance} nautical miles")

    transshipments = _integer(
        recommended.get("transshipments")
    )

    if transshipments is not None:

        details.append(
            f"{transshipments} transshipment"
            f"{'s' if transshipments != '1' else ''}"
        )

    score = _number(recommended.get("route_score"))

    if score is not None:

        details.append(f"route score {score:g}")

    if details:

        parts.append(
            " It shows " + ", ".join(details) + "."
        )

    evaluated = _integer(recommended.get("routes_evaluated"))

    # The quotation history record does not always store the
    # evaluated route count, so the sentence is only added
    # when a real count greater than zero is present.
    evaluated_count = _number(evaluated)

    if evaluated_count:

        parts.append(
            f" {evaluated} available "
            f"route{'s' if evaluated != '1' else ''} "
            "were available on this lane for this shipment, "
            "and this one was selected."
        )

    parts.append(
        " The route score is calculated from transit time, "
        "sailing distance and the number of transshipments, "
        "and it was not changed when this result was stored."
    )

    reasons = facts.get("recommendation_reasons")

    if reasons:

        parts.append(
            "Why it was chosen: "
            + " ".join(_text(r, "") for r in reasons)
        )

    return " ".join(parts)


# =========================================================
# FACT BUILDERS - WEATHER / RISK
# =========================================================
# Read-only projection of the Weather Agent result that the
# existing shipment and history serializers already embed.

def build_weather_facts(source, reference=None):

    """Weather Agent facts for the focus shipment."""

    weather = (
        source.get("weather")
        if isinstance(source, dict)
        else None
    )

    if not isinstance(weather, dict) or not weather:

        return {
            "available": False,
            "message": (
                "No weather analysis is stored for this "
                "shipment."
            ),
        }

    # -------------------------------------------------
    # TWO STORED WEATHER SHAPES ARE ACCEPTED
    #
    # The existing shipment and history serializers embed the
    # COMPACT Weather Agent summary (weather_for_route), which
    # carries no `available` flag because it is already
    # filtered to matching routes, while a full Weather Agent
    # payload carries one. Neither shape is modified here.
    # -------------------------------------------------

    if weather.get("available") is False:

        return {
            "available": False,
            "message": _text(
                weather.get("message"),
                "Weather information is not available for "
                "this route."
            ),
        }

    if not _text(weather.get("weather_risk"), ""):

        return {
            "available": False,
            "message": (
                "Weather information is not available for "
                "this route."
            ),
        }

    risk_factors = []

    for factor in weather.get("risk_factors") or []:

        if not isinstance(factor, dict):

            continue

        risk_factors.append({
            "parameter": _text(factor.get("parameter"), None),
            "value": _text(factor.get("value"), None),
            "grade": _text(
                factor.get("severity_label"), None
            ),
            "severity": _integer(factor.get("severity")),
        })

    origin = _text(weather.get("origin"), "")

    destination = _text(weather.get("destination"), "")

    if not (origin and destination):

        origin = _text((source or {}).get("origin"), "")

        destination = _text(
            (source or {}).get("destination"), ""
        )

    facts = {
        "available": True,
        "route_id": _text(weather.get("route_id"), None),
        "origin": origin or None,
        "destination": destination or None,
        "weather_risk": _text(
            weather.get("weather_risk"), "UNKNOWN"
        ),
        "risk_reason": _text(weather.get("risk_reason"), None),
        "advisory": _text(weather.get("advisory"), None),
        "storm_risk": _text(weather.get("storm_risk"), None),
        "wind_speed_knots": _integer(
            weather.get("wind_speed_knots")
        ),
        "wave_height_m": _text(
            weather.get("wave_height_m"), None
        ),
        "rainfall_mm": _integer(weather.get("rainfall_mm")),
        "visibility_km": _text(
            weather.get("visibility_km"), None
        ),
        "weather_condition": _text(
            weather.get("weather_condition"), None
        ),
        "risk_factors": risk_factors,

        # The compact stored payload does not carry the
        # thresholds, so they are attached from the injected
        # reference (built from the Weather Agent's own
        # RISK_THRESHOLDS). The stored grade is never
        # recomputed from them.
        "thresholds": (
            (reference or {}).get("thresholds")
            if isinstance(reference, dict)
            else None
        ),
        "data_source": (
            (reference or {}).get("data_source")
            if isinstance(reference, dict)
            else None
        ),
        "data_note": (
            (reference or {}).get("data_note")
            if isinstance(reference, dict)
            else None
        ),
    }

    if reference:

        facts["decision_reference"] = reference

    return facts


def weather_answer(facts):

    """Deterministic weather / risk explanation."""

    if not facts.get("available"):

        return _text(
            facts.get("message"),
            NO_ROUTE_ANSWER + " "
            "The weather risk is information for your planning. "
            "It does not change your recommended route and it "
            "does not change your quotation."
        )

    lane = f"{facts.get('origin')} to {facts.get('destination')}"

    parts = [
        "The weather risk on the "
        f"{lane} route is "
        f"{_text(facts.get('weather_risk'))}."
    ]

    condition = _text(facts.get("weather_condition"), "")

    if condition:

        parts.append(f"Current condition: {condition}.")

    readings = []

    wind = _integer(facts.get("wind_speed_knots"))

    if wind:

        readings.append(f"wind {wind} knots")

    wave = _text(facts.get("wave_height_m"), "")

    if wave:

        readings.append(f"wave height {wave} m")

    rain = _integer(facts.get("rainfall_mm"))

    if rain:

        readings.append(f"rainfall {rain} mm")

    visibility = _text(facts.get("visibility_km"), "")

    if visibility:

        readings.append(f"visibility {visibility} km")

    storm = _text(facts.get("storm_risk"), "")

    if storm:

        readings.append(f"storm risk {storm}")

    if readings:

        parts.append(
            "Readings: " + ", ".join(readings) + "."
        )

    reason = _text(facts.get("risk_reason"), "")

    if reason:

        # The stored reason is a whole sentence that may already
        # end in a full stop, so it is trimmed before it is
        # appended. That keeps one clean sentence boundary
        # instead of a doubled full stop.

        reason_clean = str(reason).rstrip(". ")

        full = " ".join(parts)

        if reason_clean and reason_clean not in full:

            parts.append(f"Basis: {reason_clean}.")

    advisory = _text(facts.get("advisory"), "")

    if advisory:

        parts.append(
            "Advisory: "
            + str(advisory).rstrip(". ")
            + "."
        )

    return " ".join(parts)


# =========================================================
# FACT BUILDERS - CUSTOMS
# =========================================================
# The Customs Agent result for the focus shipment. It is
# resolved by the SAME Customs Agent the UI uses, with the
# same four key match (origin + destination + cargo type +
# cargo subtype), so the assistant can never describe a
# different customs record than the Customs Compliance card.

def build_customs_facts(
    shipment,
    history_record,
    analyze,
    reference=None
):

    """Customs Agent facts for the focus shipment."""

    source = shipment or history_record or {}

    origin = _text(source.get("origin"), "")
    destination = _text(source.get("destination"), "")
    cargo_type = _text(source.get("cargo_type"), "")
    cargo_subtype = _text(source.get("cargo_subtype"), "")
    route_id = _text(source.get("route_id"), "")

    # -------------------------------------------------
    # INSUFFICIENT INFORMATION
    #
    # Missing cargo subtype is a normal answer, not an
    # error, and is reported plainly.
    # -------------------------------------------------

    missing = []

    if not origin:

        missing.append("origin")

    if not destination:

        missing.append("destination")

    if not cargo_type:

        missing.append("cargo type")

    if not cargo_subtype:

        missing.append("cargo subtype")

    if missing:

        return {
            "available": False,
            "reason": "incomplete_shipment",
            "message": (
                "I cannot retrieve customs requirements yet "
                "because this shipment is missing its "
                + ", ".join(missing)
                + ". Customs requirements are matched on "
                "origin, destination, cargo type and cargo "
                "subtype. Run a route analysis with a cargo "
                "subtype selected and I can check the customs "
                "position."
            ),
        }

    result = analyze(
        origin=origin,
        destination=destination,
        cargo_type=cargo_type,
        cargo_subtype=cargo_subtype,
        route_id=route_id
    )

    if not isinstance(result, dict):

        return {
            "available": False,
            "reason": "no_record",
            "message": (
                "Customs information is unavailable for "
                "this shipment."
            ),
        }

    if not result.get("available"):

        return {
            "available": False,
            "reason": result.get(
                "match_type", "no_match"
            ),
            "message": _text(
                result.get("message"),
                "Customs information is unavailable for "
                "this shipment."
            ),
        }

    checklist = []

    for item in result.get("checklist") or []:

        if not isinstance(item, dict):

            continue

        checklist.append({
            "document": _text(item.get("label"), None),
            "requirement": _text(item.get("value"), None),
            "state": _text(item.get("state_label"), None),
        })

    missing_documents = []

    for item in result.get("missing") or []:

        if not isinstance(item, dict):

            continue

        missing_documents.append(
            _text(item.get("label"), "")
        )

    facts = {
        "available": True,
        "customs_id": _text(result.get("customs_id"), None),
        "route_id": _text(result.get("route_id"), None),
        "origin": _text(result.get("origin"), None),
        "destination": _text(
            result.get("destination"), None
        ),
        "cargo_type": _text(
            result.get("cargo_type"), None
        ),
        "cargo_subtype": _text(
            result.get("cargo_subtype"), None
        ),
        "customs_status": _text(
            result.get("customs_status"), None
        ),
        "compliance_percent": _percent(
            result.get("compliance_percent")
        ),
        "required_controls": _integer(
            result.get("required_controls")
        ),
        "satisfied_controls": _integer(
            result.get("satisfied_controls")
        ),
        "restricted_cargo": "Yes" if result.get(
            "restricted"
        ) else "No",
        "missing_documents": [
            item for item in missing_documents if item
        ],
        "document_checklist": checklist,
        "status_reasons": _list(
            result.get("status_reasons")
        ),
        "deterministic_advisory": _text(
            result.get("advisory"), None
        ),
        "compliance_basis": _text(
            result.get("compliance_basis"), None
        ),
    }

    if reference:

        facts["decision_reference"] = reference

    return facts


def customs_answer(facts):

    """Deterministic customs explanation."""

    if not facts.get("available"):

        return (
            f"{_text(facts.get('message'), 'Customs information is unavailable for this shipment.')}"
            " Route intelligence, pricing and quotations are "
            "unaffected."
        )

    lane = (
        f"{facts.get('origin')} to "
        f"{facts.get('destination')} carrying "
        f"{facts.get('cargo_subtype')} "
        f"{facts.get('cargo_type')} cargo"
    )

    parts = [
        f"For {lane}, the customs status is "
        f"{_text(facts.get('customs_status'))} with "
        f"document compliance at "
        f"{_text(facts.get('compliance_percent'), 'n/a')}."
    ]

    missing_documents = facts.get("missing_documents") or []

    if missing_documents:

        parts.append(
            "Missing documents: "
            + ", ".join(missing_documents)
            + "."
        )

    else:

        parts.append(
            "No customs document is outstanding for this "
            "shipment."
        )

    if facts.get("restricted_cargo") == "Yes":

        parts.append(
            "This cargo is restricted under destination "
            "country control, so the permit must be on hand "
            "before customs clearance."
        )

    reasons = facts.get("status_reasons")

    if reasons:
        # Reasons is a list from customs agent
        if isinstance(reasons, list):
            reason_clean = "; ".join(r.rstrip(". ") for r in reasons if r)
        else:
            reason_clean = str(reasons).rstrip(". ")
        # Avoid duplicating if already stated
        full_text = " ".join(parts)
        # Remove duplicates by checking each reason not in full? or just join carefully
        final_reasons = []
        for r in (reasons if isinstance(reasons, list) else [reasons]):
            r_clean = str(r).rstrip(". ")
            # Normalize spacing
            r_clean = " ".join(r_clean.split())
            if not r_clean:
                continue
            # Simple containment check - avoid if similar text appears
            if r_clean in full_text or r_clean[:60] in full_text:
                continue
            final_reasons.append(r_clean)
            full_text += " " + r_clean
        if final_reasons:
            parts.append(f"Basis: {'; '.join(final_reasons)}.")

    return " ".join(parts)


# =========================================================
# FACT BUILDERS - QUOTATION
# =========================================================
# Reads the pricing / margin ALREADY STORED on the route
# analysis record. Nothing is recalculated, and the internal
# cost and margin figures are never included for a normal
# user, because the existing user UI does not show them.

def build_quotation_facts(
    shipment,
    history_record,
    include_internal=False,
    reference=None
):

    """Stored quotation facts for the focus shipment."""

    source = history_record or {}

    quotation_found = False

    # -------------------------------------------------
    # STORED QUOTATION (route analysis record)
    # -------------------------------------------------

    pricing = source.get("pricing")

    margin = source.get("margin")

    if not isinstance(pricing, dict):

        pricing = {}

    if not isinstance(margin, dict):

        margin = {}

    if pricing or margin:

        quotation_found = True

    # -------------------------------------------------
    # SHIPMENT COPY
    #
    # A shipment keeps its own copy of the agreed quotation.
    # It is used when no route analysis record is available.
    # -------------------------------------------------

    if shipment:

        shipment_pricing = shipment.get("pricing")

        shipment_margin = shipment.get("margin")

        if not quotation_found:

            if isinstance(shipment_pricing, dict):

                pricing = shipment_pricing

            if isinstance(shipment_margin, dict):

                margin = shipment_margin

            quotation_found = bool(
                isinstance(shipment_pricing, dict)
                or isinstance(shipment_margin, dict)
            )

    if not quotation_found:

        return {
            "available": False,
            "message": (
                "No quotation has been generated for this "
                "shipment yet. Generate the quotation and I "
                "can explain the total and every component."
            ),
        }

    total = _money(
        margin.get("recommended_selling_price_usd")
    )

    facts = {
        "available": True,
        "currency": "USD",
        "total_quotation": total,
        "container_count": _integer(
            (shipment or {}).get("containers")
            or (history_record or {}).get("containers")
        ),
    }

    if include_internal:

        facts["pricing_breakdown"] = {
            "base_freight_usd": _money(
                pricing.get("base_freight_usd")
            ),
            "operating_cost_usd": _money(
                pricing.get("operating_cost_usd")
            ),
            "demand_adjusted_cost_usd": _money(
                pricing.get("demand_adjusted_cost_usd")
            ),
            "demand_factor": _text(
                pricing.get("demand_factor"), None
            ),
        }

        facts["margin_summary"] = {
            "target_margin_percent": _percent(
                margin.get("target_margin_percent")
            ),
            "expected_profit_usd": _money(
                margin.get("expected_profit_usd")
            ),
            "achieved_margin_percent": _percent(
                margin.get("achieved_margin_percent")
            ),
        }

    # The stored total is never recalculated. The reference
    # only carries the pipeline that produced it.
    if reference:

        facts["decision_reference"] = reference

    return facts


def quotation_answer(facts, include_internal=False):

    """Deterministic quotation explanation."""

    if not facts.get("available"):

        return (
            f"{_text(facts.get('message'), 'No quotation is available for this shipment.')}"
        )

    total = _text(facts.get("total_quotation"), "the agreed total")

    parts = [
        f"The total quotation for this shipment is {total}."
    ]

    containers = facts.get("container_count")

    if containers:

        parts.append(
            f"It covers {containers} container"
            f"{'s' if containers != '1' else ''}."
        )

    breakdown = facts.get("pricing_breakdown")

    if breakdown:

        components = []

        for label, key in (
            ("base freight", "base_freight_usd"),
            (
                "demand adjusted operating cost",
                "demand_adjusted_cost_usd",
            ),
        ):

            amount = breakdown.get(key)

            if amount:

                components.append(f"{label} {amount}")

        if components:

            parts.append(
                "Cost components used for this quotation: "
                + ", ".join(components)
                + "."
            )

        margin_summary = facts.get("margin_summary") or {}

        target_margin = margin_summary.get(
            "target_margin_percent"
        )

        if target_margin:

            parts.append(
                "A target margin of "
                f"{target_margin} is applied to the demand "
                "adjusted cost to arrive at the quoted "
                "selling price."
            )

    parts.append(
        "This is the stored quotation, unchanged. "
        "Explaining it never recalculates it."
    )

    return " ".join(parts)


# =========================================================
# FACT BUILDERS - SHIPMENT STATUS
# =========================================================

def build_shipment_facts(
    shipment,
    status_flow,
    reference=None
):

    """Stored shipment workflow facts."""

    if not shipment:

        return {
            "available": False,
            "message": (
                "You have no shipment on record yet. A "
                "shipment is created once an accepted "
                "quotation is approved by an administrator."
            ),
        }

    shipment_id = _text(shipment.get("shipment_id"), None)

    status = _text(shipment.get("status"), None)

    timeline = []

    for entry in shipment.get("status_history") or []:

        if not isinstance(entry, dict):

            continue

        timeline.append(
            f"{_text(entry.get('status'), 'unknown')} "
            f"on {_text(entry.get('at'), 'an unrecorded date')}"
        )

    try:

        position = list(status_flow).index(status) + 1

    except ValueError:

        position = None

    facts = {
        "available": True,
        "shipment_id": shipment_id,
        "status": status,
        "stage_position": _integer(position),
        "total_stages": _integer(len(status_flow or [])),
        "status_flow": list(status_flow or []),
        "origin": _text(shipment.get("origin"), None),
        "destination": _text(
            shipment.get("destination"), None
        ),
        "cargo_type": _text(
            shipment.get("cargo_type"), None
        ),
        "cargo_subtype": _text(
            shipment.get("cargo_subtype"), None
        ),
        "containers": _integer(shipment.get("containers")),
        "route_id": _text(shipment.get("route_id"), None),
        "route_name": _text(
            shipment.get("route_name"), None
        ),
        "transit_days": _integer(shipment.get("transit_days")),
        "distance_nm": _integer(
            shipment.get("distance_nm")
        ),
        "transshipments": _integer(
            shipment.get("transshipments")
        ),
        "quotation_id": _text(
            shipment.get("quotation_id"), None
        ),
        "created_at": _text(
            shipment.get("created_at"), None
        ),
        "status_history": timeline,

        # Honest statement of what tracking does and does not
        # hold, so the assistant never implies a live position.
        "location_note": (
            "This platform stores the shipment workflow, not a "
            "live location. There is no position, ETA or vessel "
            "name on the shipment record. Live vessel positions "
            "come from the separate AIS service behind the "
            "Maritime Route Map."
        ),
        "workflow_note": (
            "Shipment tracking in this platform is a "
            "simulated booking-to-delivery workflow. It is "
            "not live vessel tracking."
        ),
    }

    if reference:

        facts["decision_reference"] = reference

    return facts


def shipment_answer(facts):

    """Deterministic shipment status explanation."""

    if not facts.get("available"):

        return (
            f"{_text(facts.get('message'), 'You have no shipment on record yet.')}"
        )

    parts = [
        f"Shipment {_text(facts.get('shipment_id'))} from "
        f"{_text(facts.get('origin'))} to "
        f"{_text(facts.get('destination'))} is currently at "
        f"stage: {_text(facts.get('status'), 'unknown')}."
    ]

    position = facts.get("stage_position")
    total_stages = facts.get("total_stages")

    if position and total_stages:

        parts.append(
            f"That is stage {position} of {total_stages} in the "
            "booking-to-delivery workflow."
        )

    history = facts.get("status_history") or []

    if history:

        parts.append(
            "Progress so far: " + "; ".join(history) + "."
        )

    parts.append(_text(facts.get("workflow_note")))

    return " ".join(parts)


# =========================================================
# USER ASSISTANT
# =========================================================

HELP_ANSWER = (
    "I can help you with routes, cargo, customs, weather, "
    "quotations and shipments. I can explain how the platform "
    "works, and I can explain your own records using the "
    "results it has already stored: the recommended route and "
    "why it was chosen, the weather risk on that route, the "
    "customs requirements and any missing document, your "
    "quotation total, and your current shipment status. I only "
    "report information the platform has actually stored, so I "
    "never guess a number."
)

# =========================================================
# THE AGREED PLAIN MESSAGES
# =========================================================
# When there is nothing to report, the assistant says so in one
# short sentence. It never apologises at length, never blames
# an internal service, never names a file or field, and never
# hints at what caused the gap. Each situation has its own
# message so the customer is told which thing is missing.

RETRIEVAL_ANSWER = (
    "I couldn't retrieve that information right now. "
    "Please try again."
)

NO_SHIPMENT_ANSWER = (
    "I couldn't find a shipment matching your account."
)

NO_QUOTATION_ANSWER = (
    "I couldn't find a quotation for this request."
)

NO_ROUTE_ANSWER = (
    "I couldn't find a route result for this request."
)

NO_DATA_ANSWER = (
    "I couldn't find enough information to answer that "
    "accurately."
)

# Optional guidance, appended only where a next step genuinely
# helps and no stored value exists to report.

GET_STARTED_ANSWER = (
    " Run a route analysis from Route Intelligence, generate a "
    "quotation, or accept a quotation to create a shipment, and "
    "I can explain the results."
)


# =========================================================
# PROJECT KNOWLEDGE PROVIDER
# =========================================================
# The caller injects a callable built from
# app/services/project_context.py. It answers three questions
# at once:
#
#   * is this question about the platform rather than about
#     the caller's record?
#   * which project topics does it mention?
#   * which agent rule / threshold belongs to the data topic
#     that was actually retrieved?
#
# `intents` are passed in so the provider never needs its own
# copy of the intent keyword tables.
# =========================================================

def _project_context(
    knowledge_provider,
    question,
    scope,
    intents,
    status_flow
):

    """Call the injected knowledge provider, never raising."""

    if not knowledge_provider:
        return None

    try:

        context = knowledge_provider(
            question,
            scope=scope,
            intents=list(intents or []),
            status_flow=status_flow
        )

    except Exception as error:

        logger.warning(
            "Project knowledge unavailable: %s", error
        )

        return None

    if not isinstance(context, dict):
        return None

    return context


def _project_facts(context, mode="system"):

    """Project knowledge shaped for the facts payload."""

    knowledge = context.get("knowledge") or {}

    topics = list(context.get("topics") or [])

    return {
        "scope_of_answer": (
            "platform description"
            if mode == "system"
            else "platform description and stored record"
        ),
        "matched_topics": topics,
        "project_name": knowledge.get("project_name"),
        "purpose": knowledge.get("purpose"),
        "grounding_rule": knowledge.get("grounding_rule"),
        "sections": knowledge.get("sections") or {},
    }


def _project_answer(context, mode="system"):

    """Deterministic project explanation, or an empty string."""

    answer = str(
        (context or {}).get("deterministic_answer") or ""
    ).strip()

    if answer:
        return answer

    return ""


def answer_user_question(
    question,
    shipments,
    history,
    analyze,
    status_flow,
    shipment_id="",
    route_id="",
    knowledge_provider=None
):

    """
    Answer a shipper's question.

    Parameters
    ----------
    question : str
        Raw question text.
    shipments : list[dict]
        Shipment records already scoped to the authenticated
        user by the caller.
    history : list[dict]
        Route analysis records already scoped to the same
        user.
    analyze : callable
        The Customs Agent entry point, injected by the
        caller so this module never imports the agents.
    status_flow : list[str]
        The existing shipment status workflow.
    shipment_id, route_id : str
        Optional explicit reference from the UI.
    knowledge_provider : callable | None
        Injected project-knowledge resolver built from
        app/services/project_context.py. When it is absent
        the assistant behaves exactly as it did before.

    Returns
    -------
    dict
        {
          "intents": [...],
          "focus": {...},
          "facts": {...},
          "deterministic_answer": "...",
          "scope": "user"
        }
    """

    # -------------------------------------------------
    # SCOPE GATE
    #
    # Checked before intent detection, before any record is
    # read and before the explanation service is offered
    # anything. A refused question stops here.
    # -------------------------------------------------

    question_scope, marker = classify_question(question)

    if question_scope != SCOPE_BUSINESS:

        logger.info(
            "Assistant refused a %s question (marker=%s)",
            question_scope,
            marker
        )

        return _refusal(question, "user")

    intents = detect_intents(question, allow_admin=False)

    # -------------------------------------------------
    # PLATFORM QUESTION
    #
    # "What does this project do?" and "Explain the Route
    # Agent" are answered from the grounded project
    # knowledge only. The caller's own shipment numbers are
    # deliberately NOT mixed into a question about how the
    # platform works.
    # -------------------------------------------------

    project = _project_context(
        knowledge_provider,
        question,
        scope="user",
        intents=intents,
        status_flow=status_flow
    )

    owns_a_record = bool(shipments) or bool(history)

    # A question the ADMINISTRATOR area owns is never answered
    # with the caller's own record. "How many shipments are
    # active?" is a platform-wide counter, and "what can the
    # administrator see?" is the admin boundary. Substituting
    # the caller's single shipment for either would be a wrong
    # answer, so these keep the plain process/boundary answer.

    asks_admin_question = any(
        intent
        in detect_intents(question, allow_admin=True)
        for intent in ADMIN_ONLY_INTENTS
    )

    # -------------------------------------------------
    # A PLAIN DATA QUESTION, EITHER WAY
    #
    # "What is the weather risk?" names a topic but asks
    # neither "how does that work" nor "what is mine". The
    # business classifier cannot see the caller's records, so it
    # reports a pure process question.
    #
    #   * the caller owns a record -> the stored value is what
    #     was asked for, so the answer becomes mixed: the real
    #     value first, then the grounded explanation.
    #   * the caller owns nothing -> there is no value to report
    #     and the customer is waiting for an answer, not a
    #     lecture about the process, so the record path runs and
    #     gives the one short "not found" sentence.
    #
    # A genuine mechanism question, a usage question, an
    # overview question and an admin-area question are all left
    # as a pure process answer, and no data is ever invented.
    # -------------------------------------------------

    asks_for_a_value = (
        project.get("mode") == "system"
        and not asks_admin_question
        and project.get("mirrors_stored_value")
        and not project.get("admin_only")
        and not project.get("is_mechanism_question")
        and not project.get("is_usage_question")
        and not project.get("is_record_question")
    )

    plain_data_question = asks_for_a_value and owns_a_record

    if project and plain_data_question:

        project = dict(project, mode="mixed")

    if project and project.get("mode") == "system" and not (
        asks_for_a_value and not owns_a_record
    ):

        project_answer = _project_answer(project)

        if project_answer:

            return {
                "intents": list(intents) + ["project"],
                "focus": {
                    "shipment_id": _text(
                        shipment_id, None
                    ),
                    "route_id": _text(route_id, None),
                    "has_shipment": bool(shipments),
                    "has_route_analysis": bool(history),
                    "shipment_count": len(shipments),
                    "route_analysis_count": len(
                        history or []
                    ),
                },
                "facts": {
                    "project": _project_facts(
                        project, mode="system"
                    )
                },
                "deterministic_answer": project_answer,
                "scope": "user",
            }

    reference = (project or {}).get("agent_reference") or {}

    # -------------------------------------------------
    # GENERAL QUESTION
    #
    # A greeting or a "what can you do" question has no
    # topic. It is answered with the capability description
    # instead of dumping every section of the shipment.
    # -------------------------------------------------

    if not intents or INTENT_HELP in intents:

        return {
            "intents": [INTENT_HELP],
            "focus": {
                "has_shipment": bool(shipments),
                "has_route_analysis": bool(history),
                "shipment_count": len(shipments or []),
                "route_analysis_count": len(history or []),
            },
            "facts": {
                "capabilities": [
                    "recommended route and why it was chosen",
                    "weather risk on that route",
                    "customs requirements and missing documents",
                    "total quotation",
                    "current shipment status",
                ],
                "available_data": {
                    "shipment_count": str(
                        len(shipments or [])
                    ),
                    "route_analysis_count": str(
                        len(history or [])
                    ),
                },
            },
            "deterministic_answer": HELP_ANSWER,
            "scope": "user",
        }

    focus_shipment, focus_history = select_focus_record(
        shipments,
        history,
        shipment_id=shipment_id,
        route_id=route_id
    )

    facts = {}

    answers = []

    needs_route = (
        INTENT_ROUTE in intents
        or INTENT_QUOTATION in intents
    )

    if needs_route:

        route_facts = build_route_facts(
            focus_shipment,
            focus_history,
            reference=reference.get(INTENT_ROUTE)
        )

        facts["route"] = route_facts

        # A question that carries NO specific topic (a greeting
        # or a general "what can you do") must not trigger a
        # full dump of every section. Only a genuine route
        # question gets the route answer spoken.
        asking_route = (
            INTENT_ROUTE in intents
            and not (
                set(intents) & {
                    INTENT_WEATHER,
                    INTENT_CUSTOMS,
                    INTENT_QUOTATION,
                    INTENT_SHIPMENT,
                }
            )
        )

        if asking_route:

            answers.append(route_answer(route_facts))

    if INTENT_WEATHER in intents:

        weather_facts = build_weather_facts(
            focus_shipment or focus_history or {},
            reference=reference.get(INTENT_WEATHER)
        )

        facts["weather"] = weather_facts

        answers.append(weather_answer(weather_facts))

    if INTENT_CUSTOMS in intents:

        customs_facts = build_customs_facts(
            focus_shipment,
            focus_history,
            analyze,
            reference=reference.get(INTENT_CUSTOMS)
        )

        facts["customs"] = customs_facts

        answers.append(customs_answer(customs_facts))

    if INTENT_QUOTATION in intents:

        quotation_facts = build_quotation_facts(
            focus_shipment,
            focus_history,
            include_internal=False,
            reference=reference.get(INTENT_QUOTATION)
        )

        facts["quotation"] = quotation_facts

        answers.append(quotation_answer(quotation_facts))

    if INTENT_SHIPMENT in intents:

        shipment_facts = build_shipment_facts(
            focus_shipment,
            status_flow,
            reference=reference.get(INTENT_SHIPMENT)
        )

        facts["shipment"] = shipment_facts

        answers.append(shipment_answer(shipment_facts))

    focus = {
        "shipment_id": _text(
            (focus_shipment or {}).get("shipment_id"),
            None,
        ),
        "route_id": _text(
            (focus_shipment or {}).get("route_id")
            or (focus_history or {}).get("route_id"),
            None,
        ),
        "origin": _text(
            (focus_shipment or focus_history or {}).get(
                "origin"
            ),
            None,
        ),
        "destination": _text(
            (focus_shipment or focus_history or {}).get(
                "destination"
            ),
            None,
        ),
        "has_shipment": focus_shipment is not None,
        "has_route_analysis": focus_history is not None,
        "shipment_count": len(shipments or []),
    }

    # -------------------------------------------------
    # MIXED QUESTION
    #
    # "How is my quotation calculated?" asks about the
    # mechanism AND about the caller's record. The stored
    # record is spoken first, then the grounded description
    # of how the platform works.
    # -------------------------------------------------

    if project and project.get("mode") == "mixed":

        facts["project"] = _project_facts(
            project, mode="mixed"
        )

        mixed_answer = _project_answer(project)

        if mixed_answer:

            answers.append(mixed_answer)

    # -------------------------------------------------
    # NO USABLE ANSWER
    #
    # Nothing was stored for this customer, so the answer is
    # one short sentence naming what is missing. The next step
    # is offered once, because it is genuinely useful when the
    # account is empty.
    # -------------------------------------------------

    usable = [
        answer
        for answer in answers
        if answer
    ]

    if not usable or (
        not focus["has_shipment"]
        and not focus["has_route_analysis"]
    ):

        if INTENT_QUOTATION in intents:

            usable = [NO_QUOTATION_ANSWER]

        elif INTENT_SHIPMENT in intents:

            usable = [NO_SHIPMENT_ANSWER]

        elif INTENT_ROUTE in intents:

            usable = [NO_ROUTE_ANSWER]

        else:

            usable = [NO_DATA_ANSWER]

        usable = [
            usable[0] + GET_STARTED_ANSWER
        ]

    return {
        "intents": intents + (
            ["project"]
            if facts.get("project")
            else []
        ),
        "focus": focus,
        "facts": facts,
        "deterministic_answer": " ".join(usable),
        "scope": "user",
    }


# =========================================================
# ADMIN ASSISTANT
# =========================================================
# The admin assistant answers from the SAME collections the
# existing admin dashboard already reads. It adds no new
# collection and exposes no credential.

def build_admin_stats_facts(stats, shipments):

    """Admin platform counters."""

    shipment_list = shipments or []

    status_counts = {}

    for shipment in shipment_list:

        status = _text(shipment.get("status"), "Unknown")

        status_counts[status] = status_counts.get(
            status, 0
        ) + 1

    return {
        "total_users": _integer(stats.get("total_users")),
        "total_route_analyses": _integer(
            stats.get("total_route_analyses")
        ),
        "total_quotations": _integer(
            stats.get("total_quotations")
        ),
        "total_shipments": _integer(
            stats.get("total_shipments")
        ),
        "active_shipments": _integer(
            stats.get("active_shipments")
        ),
        "delivered_shipments": _integer(
            stats.get("delivered_shipments")
        ),
        "shipments_by_status": {
            status: str(count)
            for status, count in sorted(
                status_counts.items()
            )
        },
    }


def admin_stats_answer(facts):

    """Deterministic admin counters answer."""

    return (
        f"The platform currently has "
        f"{_text(facts.get('total_users'), '0')} registered "
        f"users, {_text(facts.get('total_route_analyses'), '0')} "
        f"route analyses, "
        f"{_text(facts.get('total_quotations'), '0')} generated "
        f"quotations, "
        f"{_text(facts.get('total_shipments'), '0')} shipments of "
        f"which {_text(facts.get('active_shipments'), '0')} are "
        f"still active and "
        f"{_text(facts.get('delivered_shipments'), '0')} have "
        "been delivered."
    )


def build_admin_customs_facts(
    customs_rows,
    shipments,
    analyze,
    reference=None
):

    """Admin customs monitoring facts."""

    rows = customs_rows or []

    status_counts = {}

    for row in rows:

        status = _text(row.get("customs_status"), "Unknown")

        status_counts[status] = status_counts.get(
            status, 0
        ) + 1

    # -------------------------------------------------
    # LIVE SHIPMENT CUSTOMS POSITION
    #
    # The Customs Agent is run for the shipments the admin
    # already monitors, so "which shipments have a customs
    # problem" is answered from the real module and not from
    # the static dataset alone.
    # -------------------------------------------------

    flagged = []

    for shipment in shipments or []:

        result = analyze(
            origin=shipment.get("origin"),
            destination=shipment.get("destination"),
            cargo_type=shipment.get("cargo_type"),
            cargo_subtype=shipment.get("cargo_subtype"),
            route_id=shipment.get("route_id"),
        )

        if not isinstance(result, dict) or not result.get(
            "available"
        ):

            continue

        status = _text(result.get("customs_status"), "")

        if status not in ("Warning", "Action Required"):

            continue

        flagged.append({
            "shipment_id": _text(
                shipment.get("shipment_id"), None
            ),
            "customs_status": status,
            "compliance_percent": _percent(
                result.get("compliance_percent")
            ),
            "missing_documents": [
                _text(item.get("label"), "")
                for item in result.get("missing") or []
                if isinstance(item, dict)
                and _text(item.get("label"), "")
            ],
        })

    facts = {
        "dataset_records": str(len(rows)),
        "records_by_status": {
            status: str(count)
            for status, count in sorted(
                status_counts.items()
            )
        },
        "flagged_shipments": flagged,
        "flagged_shipment_count": str(len(flagged)),
    }

    if reference:

        facts["decision_reference"] = reference

    return facts


def admin_customs_answer(facts):

    """Deterministic admin customs answer."""

    flagged = facts.get("flagged_shipments") or []

    if not flagged:

        return (
            "No shipment currently has a customs warning or an "
            "action-required customs status. The customs "
            f"dataset holds {facts.get('dataset_records')} "
            "route and cargo records, distributed as "
            f"{_list(list((facts.get('records_by_status') or {}).items())) or 'no statuses'}."
        )

    lines = [
        f"{len(flagged)} shipment"
        f"{'s' if len(flagged) != 1 else ''} "
        "currently "
        f"{'have' if len(flagged) != 1 else 'has'} a "
        "customs warning or action-required status:"
    ]

    for item in flagged[:10]:

        missing = _list(item.get("missing_documents"))

        lines.append(
            f"{_text(item.get('shipment_id'))} is "
            f"{_text(item.get('customs_status'))} at "
            f"{_text(item.get('compliance_percent'), 'n/a')} "
            "compliance"
            + (
                f", missing {missing}."
                if missing
                else "."
            )
        )

    if len(flagged) > 10:

        lines.append(
            f"{len(flagged) - 10} further shipment"
            f"{'s' if len(flagged) - 10 != 1 else ''} "
            "are flagged."
        )

    return " ".join(lines)


def build_admin_quotation_facts(quotations):

    """Admin recent quotation activity facts."""

    records = quotations or []

    recent = []

    total_value = 0.0

    counted_value = 0

    for record in records[:10]:

        margin = record.get("margin")

        margin = margin if isinstance(margin, dict) else {}

        amount = _number(
            margin.get("recommended_selling_price_usd")
        )

        if amount is not None:

            total_value += amount
            counted_value += 1

        recent.append({
            "created_at": _text(
                record.get("created_at"), None
            ),
            "origin": _text(record.get("origin"), None),
            "destination": _text(
                record.get("destination"), None
            ),
            "quotation_total": _money(
                margin.get(
                    "recommended_selling_price_usd"
                )
            ),
            "approval_status": _text(
                record.get("approval_status")
                or "not submitted",
                None,
            ),
        })

    return {
        "quotation_count": str(len(records)),
        "recent_quotations": recent,
        "recent_total_usd": (
            _money(total_value) if counted_value else None
        ),
        "recent_average_usd": (
            _money(total_value / counted_value)
            if counted_value
            else None
        ),
    }


def admin_quotation_answer(facts):

    """Deterministic admin quotation activity answer."""

    recent = facts.get("recent_quotations") or []

    headline = (
        f"There are {facts.get('quotation_count')} generated "
        f"quotations on record"
    )

    average = facts.get("recent_average_usd")

    if average:

        headline += (
            f", and the {len(recent)} most recent total "
            f"{average} on average"
        )

    parts = [headline + "."]

    for item in recent[:5]:

        parts.append(
            f"{_text(item.get('origin'))} to "
            f"{_text(item.get('destination'))}: "
            f"{_text(item.get('quotation_total'), 'no total')} "
            f"on {_text(item.get('created_at'), 'an unrecorded date')} "
            f"({_text(item.get('approval_status'), 'not submitted')})."
        )

    return " ".join(parts)


def build_admin_login_facts(users_logged_in_today, users_total):

    """Admin login activity facts."""

    return {
        "users_logged_in_today": str(users_logged_in_today),
        "total_users": str(users_total),
    }


def admin_login_answer(facts):

    """Deterministic admin login activity answer."""

    return (
        f"{facts.get('users_logged_in_today')} of "
        f"{facts.get('total_users')} registered users "
        "signed in today."
    )


def build_admin_health_facts(health):

    """Admin system health facts."""

    return {
        "database": _text(
            health.get("database"), "unknown"
        ),
        "routes_dataset": _text(
            health.get("routes_dataset"), "unknown"
        ),
        "weather_dataset": _text(
            health.get("weather_dataset"), "unknown"
        ),
        "customs_dataset": _text(
            health.get("customs_dataset"), "unknown"
        ),
        "ais_provider": _text(
            health.get("ais_provider"), "unknown"
        ),
        "ai_advisory_layer": _text(
            health.get("ai_advisory_layer"), "unknown"
        ),
        "issues": _list(health.get("issues")),
    }


def admin_health_answer(facts):

    """Deterministic admin system health answer."""

    healthy = []

    issues = []

    for label, key in (
        ("database", "database"),
        ("routes dataset", "routes_dataset"),
        ("weather dataset", "weather_dataset"),
        ("customs dataset", "customs_dataset"),
        ("AIS provider", "ais_provider"),
        ("AI advisory layer", "ai_advisory_layer"),
    ):

        value = _text(facts.get(key), "unknown")

        if value.lower() in (
            "ok", "connected", "available",
            "configured", "not configured",
        ):

            healthy.append(f"{label}: {value}")

        else:

            issues.append(f"{label}: {value}")

    parts = []

    if healthy:

        parts.append(
            "Reporting normally: " + "; ".join(healthy) + "."
        )

    reported = facts.get("issues")

    # A trailing period on an already punctuated issue
    # sentence is avoided so the report reads cleanly.

    if reported:

        reported = reported.rstrip(". ")

        parts.append(
            "Attention needed: " + reported + "."
        )

    elif issues:

        parts.append(
            "Attention needed: "
            + "; ".join(issues).rstrip(". ")
            + "."
        )

    else:

        parts.append(
            "No system issue is currently detected."
        )

    return " ".join(parts)


ADMIN_HELP_ANSWER = (
    "I can answer from the platform data the admin "
    "dashboard already monitors: user and shipment counts, "
    "customs warnings on live shipments, recent quotation "
    "activity, how many users signed in today, and the "
    "current system health. I can also explain the business "
    "processes behind them: the quotation and approval flow, "
    "how a route is recommended, how weather and customs are "
    "assessed, how a quotation is priced, and how a shipment "
    "moves through its stages. I only report stored values "
    "and rules the platform actually applies."
)


def answer_admin_question(
    question,
    stats,
    shipments,
    quotations,
    customs_rows,
    users_logged_in_today,
    users_total,
    health,
    analyze,
    status_flow,
    shipment_id="",
    route_id="",
    knowledge_provider=None
):

    """
    Answer an administrator's question from the existing
    admin collections.
    """

    # -------------------------------------------------
    # SCOPE GATE
    #
    # An administrator is still a customer-facing user of
    # the business, so the same gate applies. Administrator
    # status widens which DATA may be read; it never widens
    # the subject matter.
    # -------------------------------------------------

    question_scope, marker = classify_question(question)

    if question_scope != SCOPE_BUSINESS:

        logger.info(
            "Admin assistant refused a %s question (marker=%s)",
            question_scope,
            marker
        )

        return _refusal(question, "admin")

    intents = detect_intents(question, allow_admin=True)

    # -------------------------------------------------
    # PLATFORM QUESTION
    #
    # An administrator asking how the platform or the admin
    # area works is answered from the grounded project
    # knowledge. The generic word "system" must not drag the
    # system-health counters into a question about design.
    #
    # A question that asks for a concrete platform-wide
    # NUMBER is not a description question. "How many
    # shipments are active" mentions "shipment", but the real
    # question is the counter, so a detected admin intent
    # always wins over a general description.
    # -------------------------------------------------

    project = _project_context(
        knowledge_provider,
        question,
        scope="admin",
        intents=intents,
        status_flow=status_flow
    )

    asking_for_admin_data = any(
        intent in ADMIN_ONLY_INTENTS
        for intent in intents
    )

    if (
        project
        and project.get("mode") == "system"
        and not asking_for_admin_data
    ):

        project_answer = _project_answer(project)

        if project_answer:

            return {
                "intents": list(intents) + ["project"],
                "focus": {
                    "shipment_id": _text(shipment_id, None),
                    "route_id": _text(route_id, None),
                },
                "facts": {
                    "project": _project_facts(
                        project, mode="system"
                    )
                },
                "deterministic_answer": project_answer,
                "scope": "admin",
            }

    reference = (project or {}).get("agent_reference") or {}

    # -------------------------------------------------
    # GENERAL QUESTION
    # -------------------------------------------------

    if not intents or INTENT_HELP in intents:

        return {
            "intents": [INTENT_HELP],
            "focus": {
                "shipment_id": _text(shipment_id, None),
                "route_id": _text(route_id, None),
            },
            "facts": {
                "capabilities": [
                    "user and shipment counters",
                    "customs warnings on live shipments",
                    "recent quotation activity",
                    "users who signed in today",
                    "current system health",
                    "how this platform and this admin area work",
                ],
            },
            "deterministic_answer": ADMIN_HELP_ANSWER,
            "scope": "admin",
        }

    admin_intents = [
        intent
        for intent in intents
        if intent in ADMIN_ONLY_INTENTS
    ]

    # A question that only matches a shipment topic still gets
    # the shipment-scoped answer, using the admin's own view.

    shipment_intents = [
        intent
        for intent in intents
        if intent in (
            INTENT_ROUTE,
            INTENT_WEATHER,
            INTENT_CUSTOMS,
            INTENT_QUOTATION,
            INTENT_SHIPMENT,
        )
    ]

    # -------------------------------------------------
    # PLATFORM-WIDE QUESTION SUPERSEDES THE SINGLE
    # SHIPMENT ANSWER
    #
    # "Which shipments have customs warnings?" matches both
    # the customs topic and the admin customs intent. The
    # admin intent is the real question, so the shipment
    # scoped customs answer is not appended as well and the
    # answer is not diluted.
    # -------------------------------------------------

    if INTENT_ADMIN_CUSTOMS in admin_intents:

        shipment_intents = [
            intent
            for intent in shipment_intents
            if intent
            not in (INTENT_CUSTOMS, INTENT_SHIPMENT)
        ]

    if INTENT_ADMIN_QUOTATIONS in admin_intents:

        shipment_intents = [
            intent
            for intent in shipment_intents
            if intent != INTENT_QUOTATION
        ]

    # "How many active shipments are there?" contains the
    # word "shipment", so it also matches the shipment topic.
    # The platform counter is the real question.

    if INTENT_ADMIN_STATS in admin_intents:

        shipment_intents = [
            intent
            for intent in shipment_intents
            if intent != INTENT_SHIPMENT
        ]

    # "How many users logged in today?" contains "how many",
    # so it also matches the platform counter intent. The
    # login question is the real one.

    if INTENT_ADMIN_LOGINS in admin_intents:

        admin_intents = [
            intent
            for intent in admin_intents
            if intent != INTENT_ADMIN_STATS
        ]

    facts = {}

    answers = []

    if INTENT_ADMIN_STATS in admin_intents:

        stats_facts = build_admin_stats_facts(
            stats, shipments
        )

        facts["admin_stats"] = stats_facts

        answers.append(admin_stats_answer(stats_facts))

    if INTENT_ADMIN_CUSTOMS in admin_intents:

        customs_facts = build_admin_customs_facts(
            customs_rows,
            shipments,
            analyze,
            reference=reference.get(INTENT_ADMIN_CUSTOMS)
        )

        facts["admin_customs"] = customs_facts

        answers.append(admin_customs_answer(customs_facts))

    if INTENT_ADMIN_QUOTATIONS in admin_intents:

        quotation_facts = build_admin_quotations_facts_safe(
            quotations
        )

        facts["admin_quotations"] = quotation_facts

        answers.append(
            admin_quotation_answer(quotation_facts)
        )

    if INTENT_ADMIN_LOGINS in admin_intents:

        login_facts = build_admin_login_facts(
            users_logged_in_today, users_total
        )

        facts["admin_logins"] = login_facts

        answers.append(admin_login_answer(login_facts))

    if INTENT_ADMIN_HEALTH in admin_intents:

        health_facts = build_admin_health_facts(health)

        facts["admin_health"] = health_facts

        answers.append(admin_health_answer(health_facts))

    # -------------------------------------------------
    # SHIPMENT SCOPED QUESTIONS
    # -------------------------------------------------

    if shipment_intents:

        focus_shipment, focus_history = select_focus_record(
            shipments,
            [],
            shipment_id=shipment_id,
            route_id=route_id,
        )

        for intent in shipment_intents:

            if intent == INTENT_CUSTOMS:

                customs_facts = build_customs_facts(
                    focus_shipment,
                    focus_history,
                    analyze,
                    reference=reference.get(INTENT_CUSTOMS)
                )

                facts["customs"] = customs_facts

                answers.append(customs_answer(customs_facts))

            elif intent == INTENT_WEATHER:

                weather_facts = build_weather_facts(
                    focus_shipment or {},
                    reference=reference.get(INTENT_WEATHER)
                )

                facts["weather"] = weather_facts

                answers.append(
                    weather_answer(weather_facts)
                )

            elif intent == INTENT_SHIPMENT:

                shipment_facts = build_shipment_facts(
                    focus_shipment,
                    status_flow,
                    reference=reference.get(INTENT_SHIPMENT)
                )

                facts["shipment"] = shipment_facts

                answers.append(
                    shipment_answer(shipment_facts)
                )

            elif intent == INTENT_QUOTATION:

                quotation_facts = build_quotation_facts(
                    focus_shipment,
                    focus_history,
                    include_internal=True,
                    reference=reference.get(INTENT_QUOTATION),
                )

                facts["quotation"] = quotation_facts

                answers.append(
                    quotation_answer(
                        quotation_facts,
                        include_internal=True,
                    )
                )

            elif intent == INTENT_ROUTE:

                route_facts = build_route_facts(
                    focus_shipment,
                    focus_history,
                    reference=reference.get(INTENT_ROUTE)
                )

                facts["route"] = route_facts

                answers.append(route_answer(route_facts))

    # A mixed administrator question ("how does my quotation
    # get calculated?") is answered with the live data first
    # and the grounded mechanism afterwards.

    if project and project.get("mode") == "mixed":

        facts["project"] = _project_facts(
            project, mode="mixed"
        )

        mixed_answer = _project_answer(project)

        if mixed_answer:

            answers.append(mixed_answer)

    usable = [
        answer for answer in answers if answer
    ]

    if not usable:

        usable = [ADMIN_HELP_ANSWER]

    return {
        "intents": admin_intents + shipment_intents + (
            ["project"]
            if facts.get("project")
            else []
        ),
        "focus": {
            "shipment_id": _text(
                shipment_id, None
            ),
            "route_id": _text(route_id, None),
        },
        "facts": facts,
        "deterministic_answer": " ".join(usable),
        "scope": "admin",
    }


def build_admin_quotations_facts_safe(quotations):

    """Small wrapper kept separate for readability."""

    return build_admin_quotation_facts(quotations)