# =========================================================
# WEATHER AGENT
# =========================================================
# Responsibility:
# "What are the weather conditions on the selected maritime
#  route, and how risky are they for this shipment?"
#
# The Weather Agent is an INDEPENDENT INTELLIGENCE MODULE.
# It never selects a route, never changes a route score and
# never touches pricing, margin, quotations or shipments.
#
# Flow
# ----
#   Selected route (route_id or origin/destination)
#            |
#            v
#   Weather Dataset  (backend/app/weather.csv)
#            |
#            v
#   Weather Risk Assessment (deterministic thresholds)
#            |
#            v
#   Structured weather result (values + risk + reason)
#
# DATASET-DRIVEN, NOT HARD-CODED
# ------------------------------
# No route-specific weather value is written in this file.
# Every number returned by the agent is read from
# weather.csv at request time, and new routes / new weather
# records can be added to that CSV without changing a single
# line of this agent.
#
# The dataset is STATIC PROJECT REFERENCE DATA. It is not a
# live weather feed, no external weather API is used and no
# API key is required.
#
# FAIL-SAFE BY DESIGN
# -------------------
# A missing dataset, a malformed row or an unknown route
# never raises through the application. The agent returns a
# structured "not available" result so Route Intelligence,
# the Maritime Route Map, quotations and shipments keep
# working exactly as before.
# =========================================================

import logging
import math
import os
import threading

import pandas as pd


logger = logging.getLogger("uvicorn.error")


# =========================================================
# DATASET
# =========================================================

WEATHER_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "weather.csv"
)

# Human readable label. This data is reference data that
# ships with the project - it is never presented as live.
WEATHER_DATA_SOURCE = (
    "weather.csv (static project reference dataset)"
)

WEATHER_DATA_NOTE = (
    "Reference weather data stored with the project. "
    "This is not a live weather feed."
)

REQUIRED_COLUMNS = [
    "route_id",
    "origin",
    "destination",
    "storm_risk",
    "wind_speed_knots",
    "wave_height_m",
    "rainfall_mm",
    "visibility_km",
    "weather_condition",
]

NUMERIC_COLUMNS = [
    "wind_speed_knots",
    "wave_height_m",
    "rainfall_mm",
    "visibility_km",
]

TEXT_COLUMNS = [
    "route_id",
    "origin",
    "destination",
    "storm_risk",
    "weather_condition",
]


# =========================================================
# WEATHER RISK THRESHOLDS
# =========================================================
# Every monitored parameter is graded on the same 3-level
# scale:
#
#   0 = NORMAL    (normal sailing conditions)
#   1 = MODERATE  (caution advised)
#   2 = SEVERE    (conditions degrade the voyage)
#
# The overall weather risk is the HIGHEST grade observed in
# any monitored parameter, so a route can never look safer
# than its worst condition.
#
# The limits below are ordinary open-water sailing limits
# (Beaufort / WMO sea-state equivalents) and are returned in
# every response so the classification stays explainable.
# =========================================================

WIND_LOW_LIMIT_KNOTS = 25.0          # < 25  -> normal
WIND_SEVERE_LIMIT_KNOTS = 35.0       # >= 35 -> severe

WAVE_LOW_LIMIT_M = 2.0               # < 2.0  -> normal
WAVE_SEVERE_LIMIT_M = 4.0            # >= 4.0 -> severe

RAIN_LOW_LIMIT_MM = 10.0             # < 10  -> normal
RAIN_SEVERE_LIMIT_MM = 40.0          # >= 40 -> severe

VISIBILITY_LOW_LIMIT_KM = 10.0       # >= 10 -> normal
VISIBILITY_SEVERE_LIMIT_KM = 5.0     # < 5   -> severe

# Dataset storm_risk vocabulary -> grade.
STORM_RISK_GRADES = {
    "low": 0,
    "none": 0,
    "minimal": 0,
    "moderate": 1,
    "elevated": 1,
    "high": 2,
    "severe": 2,
    "extreme": 2,
}

SEVERITY_LABELS = {
    0: "normal",
    1: "moderate",
    2: "severe",
}

RISK_LEVELS = {
    0: "LOW",
    1: "MEDIUM",
    2: "HIGH",
}

RISK_SUMMARIES = {
    0: "Normal weather conditions.",
    1: "Moderate weather conditions detected.",
    2: "Severe weather conditions detected.",
}

RISK_ADVISORIES = {
    0: (
        "Normal weather conditions. No weather-related "
        "delay is expected for this voyage."
    ),
    1: (
        "Moderate weather conditions. Allow some "
        "contingency time for the voyage."
    ),
    2: (
        "Severe weather conditions. Plan extra contingency "
        "time and monitor the voyage closely."
    ),
}

# Exposed with every response so the mentor can always see
# the limits behind the LOW / MEDIUM / HIGH decision.
RISK_THRESHOLDS = {
    "wind_speed_knots": {
        "unit": "knots",
        "normal_below": WIND_LOW_LIMIT_KNOTS,
        "severe_at_or_above": WIND_SEVERE_LIMIT_KNOTS,
    },
    "wave_height_m": {
        "unit": "m",
        "normal_below": WAVE_LOW_LIMIT_M,
        "severe_at_or_above": WAVE_SEVERE_LIMIT_M,
    },
    "rainfall_mm": {
        "unit": "mm",
        "normal_below": RAIN_LOW_LIMIT_MM,
        "severe_at_or_above": RAIN_SEVERE_LIMIT_MM,
    },
    "visibility_km": {
        "unit": "km",
        "normal_at_or_above": VISIBILITY_LOW_LIMIT_KM,
        "severe_below": VISIBILITY_SEVERE_LIMIT_KM,
    },
    "storm_risk": {
        "normal": ["low", "none", "minimal"],
        "moderate": ["moderate", "elevated"],
        "severe": ["high", "severe", "extreme"],
    },
}


# =========================================================
# DATASET CACHE
# =========================================================
# The dataset is read once and kept in memory. It is
# reloaded automatically when weather.csv changes on disk,
# so new records are picked up without restarting the
# backend.
# =========================================================

_cache_lock = threading.Lock()

_weather_cache = {
    "signature": None,
    "frame": None,
    "by_route_id": {},
    "corridors": {},
    "error": None,
}


def _dataset_signature():

    try:

        stat = os.stat(WEATHER_CSV_PATH)

    except OSError:

        return None

    return (stat.st_mtime, stat.st_size)


def _clean_frame(df):
    """
    Normalize the dataset: lowercase column names, trimmed
    text values, numeric parameters and a dropped route_id
    index. Malformed rows are skipped, never fatal.
    """

    df.columns = (
        df.columns.str.strip().str.lower()
    )

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "weather.csv is missing required column(s): "
            + ", ".join(missing)
        )

    df = df.copy()

    for column in TEXT_COLUMNS:
        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

    df = df[df["route_id"] != ""].copy()

    return df


def load_weather_data():
    """
    Return the weather dataset as a DataFrame.

    Never raises: a missing or unreadable dataset resolves to
    an empty frame so callers can degrade gracefully.
    """

    signature = _dataset_signature()

    with _cache_lock:

        if (
            _weather_cache["frame"] is not None
            and _weather_cache["signature"] == signature
        ):

            return _weather_cache["frame"]

    error = None
    frame = None

    try:

        if signature is None:

            raise FileNotFoundError(
                f"weather.csv was not found at "
                f"{WEATHER_CSV_PATH}"
            )

        frame = _clean_frame(
            pd.read_csv(WEATHER_CSV_PATH)
        )

    except Exception as load_error:

        logger.warning(
            "Weather dataset unavailable: %s", load_error
        )

        error = str(load_error)
        frame = pd.DataFrame(
            columns=REQUIRED_COLUMNS
        )

    by_route_id = {}

    corridors = {}

    if frame is not None and not frame.empty:

        for _, row in frame.iterrows():

            record = row.to_dict()

            by_route_id.setdefault(
                str(record["route_id"]).lower(),
                record
            )

            key = (
                str(record["origin"]).strip().lower(),
                str(record["destination"]).strip().lower()
            )

            corridors.setdefault(key, []).append(record)

    with _cache_lock:

        _weather_cache["signature"] = signature
        _weather_cache["frame"] = frame
        _weather_cache["by_route_id"] = by_route_id
        _weather_cache["corridors"] = corridors
        _weather_cache["error"] = error

    return frame


def _cache_error():

    with _cache_lock:

        return _weather_cache["error"]


# =========================================================
# SAFE VALUE HELPERS
# =========================================================

def _safe_text(record, field, fallback=""):

    value = record.get(field)

    if value is None:
        return fallback

    text = str(value).strip()

    if not text or text.lower() == "nan":
        return fallback

    return text


def _safe_number(record, field):

    """
    Return a float for a numeric weather field, or None
    when the value is missing or malformed.
    """

    value = record.get(field)

    if value is None:
        return None

    try:

        number = float(value)

    except (TypeError, ValueError):

        return None

    if math.isnan(number) or math.isinf(number):
        return None

    return number


def _normalize(value):

    return str(value or "").strip().lower()


# =========================================================
# WEATHER RISK ASSESSMENT
# =========================================================
# Deterministic and fully explainable: each parameter is
# graded 0/1/2 and the overall risk is the highest grade.
# Missing parameters are skipped and reported in data_notes
# instead of silently lowering the risk.
# =========================================================

def _grade_wind(value):

    if value < WIND_LOW_LIMIT_KNOTS:
        return 0

    if value < WIND_SEVERE_LIMIT_KNOTS:
        return 1

    return 2


def _grade_wave(value):

    if value < WAVE_LOW_LIMIT_M:
        return 0

    if value < WAVE_SEVERE_LIMIT_M:
        return 1

    return 2


def _grade_rain(value):

    if value < RAIN_LOW_LIMIT_MM:
        return 0

    if value < RAIN_SEVERE_LIMIT_MM:
        return 1

    return 2


def _grade_visibility(value):
    """Visibility is inverted: less visibility is worse."""

    if value >= VISIBILITY_LOW_LIMIT_KM:
        return 0

    if value >= VISIBILITY_SEVERE_LIMIT_KM:
        return 1

    return 2


def _grade_storm(value):

    if not value:
        return None

    return STORM_RISK_GRADES.get(
        _normalize(value)
    )


GRADERS = {
    "wind_speed_knots": _grade_wind,
    "wave_height_m": _grade_wave,
    "rainfall_mm": _grade_rain,
    "visibility_km": _grade_visibility,
    "storm_risk": _grade_storm,
}

PARAMETER_LABELS = {
    "wind_speed_knots": "Wind speed",
    "wave_height_m": "Wave height",
    "rainfall_mm": "Rainfall",
    "visibility_km": "Visibility",
    "storm_risk": "Storm risk",
}

PARAMETER_UNITS = {
    "wind_speed_knots": "knots",
    "wave_height_m": "m",
    "rainfall_mm": "mm",
    "visibility_km": "km",
    "storm_risk": "",
}

# Lower-case wording used inside the generated explanation.
PARAMETER_PHRASES = {
    "wind_speed_knots": "wind",
    "wave_height_m": "waves",
    "rainfall_mm": "rainfall",
    "visibility_km": "visibility",
    "storm_risk": "storm risk",
}


def _format_value(parameter, value):

    if value is None:
        return "n/a"

    if parameter == "wind_speed_knots":
        return f"{int(round(value))} knots"

    if parameter == "wave_height_m":
        return f"{round(value, 1)} m"

    if parameter == "rainfall_mm":
        return f"{int(round(value))} mm"

    if parameter == "visibility_km":
        return f"{round(value, 1)} km"

    return str(value)


def _grade_band(parameter, grade):
    """Readable band text for one graded parameter."""

    if parameter == "wind_speed_knots":
        if grade == 0:
            return f"below {int(WIND_LOW_LIMIT_KNOTS)} kn"
        if grade == 1:
            return (
                f"{int(WIND_LOW_LIMIT_KNOTS)}-"
                f"{int(WIND_SEVERE_LIMIT_KNOTS) - 1} kn"
            )
        return f"{int(WIND_SEVERE_LIMIT_KNOTS)} kn or above"

    if parameter == "wave_height_m":
        if grade == 0:
            return f"below {WAVE_LOW_LIMIT_M} m"
        if grade == 1:
            return f"{WAVE_LOW_LIMIT_M}-{WAVE_SEVERE_LIMIT_M - 0.1} m"
        return f"{WAVE_SEVERE_LIMIT_M} m or above"

    if parameter == "rainfall_mm":
        if grade == 0:
            return f"below {int(RAIN_LOW_LIMIT_MM)} mm"
        if grade == 1:
            return (
                f"{int(RAIN_LOW_LIMIT_MM)}-"
                f"{int(RAIN_SEVERE_LIMIT_MM) - 1} mm"
            )
        return f"{int(RAIN_SEVERE_LIMIT_MM)} mm or above"

    if parameter == "visibility_km":
        if grade == 0:
            return f"{VISIBILITY_LOW_LIMIT_KM} km or above"
        if grade == 1:
            return (
                f"{VISIBILITY_SEVERE_LIMIT_KM}-"
                f"{VISIBILITY_LOW_LIMIT_KM - 0.1} km"
            )
        return f"below {VISIBILITY_SEVERE_LIMIT_KM} km"

    bands = RISK_THRESHOLDS["storm_risk"]

    if grade == 0:
        return f"{'/'.join(bands['normal'])}"

    if grade == 1:
        return f"{'/'.join(bands['moderate'])}"

    return f"{'/'.join(bands['severe'])}"


def _build_risk_reason(factors, corridor_label):
    """
    Build one plain-English sentence that explains exactly
    why the route received its risk level.
    """

    def _phrase(factor):
        return (
            f"{PARAMETER_PHRASES[factor['parameter']]} "
            f"{factor['display']}"
        )

    def _join(items):
        if not items:
            return ""

        if len(items) == 1:
            return items[0]

        return ", ".join(items[:-1]) + f" and {items[-1]}"

    severe = [
        factor for factor in factors
        if factor["severity"] == 2
    ]

    moderate = [
        factor for factor in factors
        if factor["severity"] == 1
    ]

    if severe:

        return (
            f"{RISK_SUMMARIES[2]} "
            f"{_join([_phrase(f) for f in severe[:3]])} "
            f"recorded for {corridor_label}."
        )

    if moderate:

        return (
            f"{RISK_SUMMARIES[1]} "
            f"{_join([_phrase(f) for f in moderate[:3]])} "
            f"recorded for {corridor_label}."
        )

    readings = _join([_phrase(f) for f in factors])

    readings = readings[:1].upper() + readings[1:]

    return (
        f"{RISK_SUMMARIES[0]} "
        f"{readings} "
        f"are all within normal sailing limits for "
        f"{corridor_label}."
    )


def _assess(record, corridor_label, extra_notes=None):
    """
    Grade every weather parameter of one record and return
    the weather risk level with its explanation.
    """

    data_notes = list(extra_notes or [])

    factors = []

    for parameter in (
        "storm_risk",
        "wind_speed_knots",
        "wave_height_m",
        "rainfall_mm",
        "visibility_km",
    ):

        if parameter == "storm_risk":

            raw_value = _safe_text(record, "storm_risk")
            numeric_value = None

        else:

            numeric_value = _safe_number(record, parameter)
            raw_value = (
                _format_value(parameter, numeric_value)
                if numeric_value is not None
                else None
            )

        grade = GRADERS[parameter](
            raw_value if parameter == "storm_risk"
            else numeric_value
        )

        if grade is None:

            data_notes.append(
                f"{PARAMETER_LABELS[parameter]} is missing "
                "for this record and was not graded."
            )

            continue

        factors.append({
            "parameter": parameter,
            "label": PARAMETER_LABELS[parameter],
            "unit": PARAMETER_UNITS[parameter],
            "value": (
                raw_value
                if parameter == "storm_risk"
                else (
                    int(round(numeric_value))
                    if parameter in (
                        "wind_speed_knots", "rainfall_mm"
                    )
                    else round(numeric_value, 1)
                )
            ),
            "display": (
                raw_value
                if parameter == "storm_risk"
                else _format_value(
                    parameter, numeric_value
                )
            ),
            "severity": grade,
            "severity_label": SEVERITY_LABELS[grade],
            "band": _grade_band(parameter, grade),
        })

    if not factors:

        # Every parameter is missing: the record exists but
        # carries no usable weather values.
        return {
            "available": False,
            "weather_risk": "UNKNOWN",
            "risk_reason": (
                "Weather information is not available for "
                "this route."
            ),
            "advisory": (
                "Weather information is not available for "
                "this route."
            ),
            "risk_factors": [],
            "data_notes": data_notes,
        }

    grade = max(factor["severity"] for factor in factors)

    return {
        "available": True,
        "weather_risk": RISK_LEVELS[grade],
        "risk_reason": _build_risk_reason(
            factors, corridor_label
        ),
        "advisory": RISK_ADVISORIES[grade],
        "risk_factors": factors,
        "data_notes": data_notes,
    }


# =========================================================
# RESULT BUILDER
# =========================================================

NOT_AVAILABLE_MESSAGE = (
    "Weather information is not available for this route."
)


def _unavailable(status, message, **extra):
    """Standard graceful 'no weather' payload."""

    payload = {
        "status": status,
        "available": False,
        "data_source": WEATHER_DATA_SOURCE,
        "data_note": WEATHER_DATA_NOTE,
        "message": message,
        "route_id": None,
        "origin": None,
        "destination": None,
        "storm_risk": None,
        "wind_speed_knots": None,
        "wave_height_m": None,
        "rainfall_mm": None,
        "visibility_km": None,
        "weather_condition": None,
        "weather_risk": "UNKNOWN",
        "risk_reason": NOT_AVAILABLE_MESSAGE,
        "advisory": NOT_AVAILABLE_MESSAGE,
        "risk_factors": [],
        "data_notes": [],
    }

    payload.update(extra)

    return payload


def _build_result(record, match_type, extra=None):
    """
    Turn one dataset record into the structured weather
    result returned by the API.
    """

    origin = _safe_text(record, "origin")
    destination = _safe_text(record, "destination")

    corridor_label = f"{origin} to {destination}".strip()

    assessment = _assess(record, corridor_label)

    wind = _safe_number(record, "wind_speed_knots")
    wave = _safe_number(record, "wave_height_m")
    rain = _safe_number(record, "rainfall_mm")
    visibility = _safe_number(record, "visibility_km")

    result = {
        "status": "success" if assessment["available"]
                  else "no_data",

        "available": assessment["available"],

        "match_type": match_type,

        "route_id": _safe_text(record, "route_id") or None,

        "origin": origin or None,
        "destination": destination or None,

        # -------------------------------------------
        # ORIGINAL DATASET VALUES
        # -------------------------------------------

        "storm_risk": _safe_text(record, "storm_risk") or None,

        "wind_speed_knots": (
            int(round(wind)) if wind is not None else None
        ),

        "wave_height_m": (
            round(wave, 1) if wave is not None else None
        ),

        "rainfall_mm": (
            int(round(rain)) if rain is not None else None
        ),

        "visibility_km": (
            round(visibility, 1)
            if visibility is not None
            else None
        ),

        "weather_condition": (
            _safe_text(record, "weather_condition") or None
        ),

        # -------------------------------------------
        # CALCULATED WEATHER RISK
        # -------------------------------------------

        "weather_risk": assessment["weather_risk"],
        "risk_reason": assessment["risk_reason"],
        "advisory": assessment["advisory"],
        "risk_factors": assessment["risk_factors"],

        "thresholds": RISK_THRESHOLDS,

        "data_source": WEATHER_DATA_SOURCE,
        "data_note": WEATHER_DATA_NOTE,
        "data_notes": assessment["data_notes"],
    }

    if extra:
        result.update(extra)

    return result


# =========================================================
# CORRIDOR AGGREGATION
# =========================================================
# When only origin + destination are known, every weather
# record on that corridor is combined into one corridor-level
# assessment (worst storm exposure, average wind / wave /
# rainfall, lowest visibility) so the answer stays
# deterministic and explainable.
# =========================================================

def _aggregate_corridor(records):
    """Average the numeric parameters of one corridor."""

    aggregate = {
        "origin": _safe_text(records[0], "origin"),
        "destination": _safe_text(records[0], "destination"),
    }

    storm_grade = -1
    storm_value = ""

    for record in records:

        storm = _safe_text(record, "storm_risk")

        grade = STORM_RISK_GRADES.get(_normalize(storm))

        if grade is not None and grade > storm_grade:
            storm_grade = grade
            storm_value = storm

        for column in NUMERIC_COLUMNS:
            value = _safe_number(record, column)

            if value is None:
                continue

            if column not in aggregate:
                aggregate[column] = []
                aggregate[f"{column}__count"] = 0

            aggregate[column].append(value)
            aggregate[f"{column}__count"] += 1

    for column in NUMERIC_COLUMNS:

        values = aggregate.get(column)

        if not values:
            aggregate[column] = None
            aggregate.pop(f"{column}__count", None)
            continue

        if column == "visibility_km":
            aggregate[column] = min(values)
        else:
            aggregate[column] = (
                sum(values) / len(values)
            )

    aggregate["storm_risk"] = storm_value or None

    conditions = [
        _safe_text(record, "weather_condition")
        for record in records
    ]

    conditions = [
        condition for condition in conditions
        if condition
    ]

    aggregate["weather_condition"] = (
        max(set(conditions), key=conditions.count)
        if conditions
        else None
    )

    return aggregate


# =========================================================
# PUBLIC API
# =========================================================

def analyze_weather(
    route_id=None,
    origin=None,
    destination=None
):
    """
    Analyze the weather on a single maritime route.

    The route is identified by route_id (preferred, it comes
    straight from the Route Agent) or by origin +
    destination.

    Returns a structured weather result. Never raises for a
    missing dataset, an unknown route or a malformed row -
    those cases return an "available: False" payload with the
    standard not-available message.

    Raises
    ------
    ValueError
        Only when no usable route identifier was supplied.
    """

    route_id_clean = str(route_id or "").strip()
    origin_clean = str(origin or "").strip()
    destination_clean = str(destination or "").strip()

    if not route_id_clean and not (
        origin_clean and destination_clean
    ):

        raise ValueError(
            "A route_id, or an origin and destination pair, "
            "is required to analyze weather."
        )

    load_weather_data()

    dataset_error = _cache_error()

    if dataset_error:

        return _unavailable(
            "dataset_unavailable",
            "Weather information is not available for "
            "this route.",
            error_detail=dataset_error
        )

    # -----------------------------------------------------
    # LOOKUP BY ROUTE_ID (preferred - Route Agent output)
    # -----------------------------------------------------

    if route_id_clean:

        with _cache_lock:

            record = _weather_cache["by_route_id"].get(
                route_id_clean.lower()
            )

        if record is not None:

            return _build_result(record, "route_id")

        if not (origin_clean and destination_clean):

            return _unavailable(
                "not_found",
                NOT_AVAILABLE_MESSAGE,
                route_id=route_id_clean,
                origin=origin_clean or None,
                destination=destination_clean or None
            )

    # -----------------------------------------------------
    # LOOKUP BY CORRIDOR
    # -----------------------------------------------------

    with _cache_lock:

        corridor_records = _weather_cache["corridors"].get(
            (
                origin_clean.lower(),
                destination_clean.lower()
            ),
            []
        )

    if not corridor_records:

        return _unavailable(
            "not_found",
            NOT_AVAILABLE_MESSAGE,
            route_id=route_id_clean or None,
            origin=origin_clean or None,
            destination=destination_clean or None
        )

    aggregate = _aggregate_corridor(corridor_records)

    return _build_result(
        aggregate,
        "corridor",
        extra={
            "matched_route_count": len(corridor_records),
            "matched_route_ids": [
                _safe_text(record, "route_id")
                for record in corridor_records
            ],
        }
    )


def analyze_routes_weather(route_ids):
    """
    Analyze the weather of several routes at once.

    Used to show weather intelligence for the recommended
    route together with its alternative routes. Routes
    without a weather record are reported as not available
    instead of being dropped, so the caller can always show
    a complete list.
    """

    results = []

    seen = set()

    for route_id in route_ids or []:

        route_id_clean = str(route_id or "").strip()

        if not route_id_clean or route_id_clean in seen:
            continue

        seen.add(route_id_clean)

        results.append(
            analyze_weather(route_id=route_id_clean)
        )

    return results


def weather_for_route(route_id):
    """
    Compact weather summary for a single route_id, or None
    when no weather record exists. Used by the admin views,
    which must never fail because of the weather module.
    """

    route_id_clean = str(route_id or "").strip()

    if not route_id_clean:
        return None

    try:

        result = analyze_weather(route_id=route_id_clean)

    except Exception as error:

        logger.warning(
            "Weather lookup failed for route %s: %s",
            route_id_clean, error
        )

        return None

    if not result.get("available"):

        return None

    return {
        "weather_risk": result.get("weather_risk"),
        "storm_risk": result.get("storm_risk"),
        "wind_speed_knots": result.get("wind_speed_knots"),
        "wave_height_m": result.get("wave_height_m"),
        "weather_condition": result.get(
            "weather_condition"
        ),
        "risk_reason": result.get("risk_reason"),
    }


def get_weather_summary():
    """
    Dataset coverage information. Used by the Weather API so
    the full route coverage of the module is visible.
    """

    frame = load_weather_data()

    if frame is None or frame.empty:

        return {
            "status": (
                "unavailable" if _cache_error()
                else "empty"
            ),
            "data_source": WEATHER_DATA_SOURCE,
            "data_note": WEATHER_DATA_NOTE,
            "message": NOT_AVAILABLE_MESSAGE,
            "total_records": 0,
            "total_routes_covered": 0,
            "total_corridors": 0,
            "columns": list(REQUIRED_COLUMNS),
            "storm_risk_distribution": {},
            "weather_condition_distribution": {},
            "thresholds": RISK_THRESHOLDS,
        }

    corridors = frame.groupby(
        ["origin", "destination"]
    ).ngroups

    def _distribution(column):
        counts = (
            frame[column]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "Unknown")
            .value_counts()
            .to_dict()
        )

        return {
            str(key): int(value)
            for key, value in counts.items()
        }

    return {
        "status": "success",
        "available": True,
        "data_source": WEATHER_DATA_SOURCE,
        "data_note": WEATHER_DATA_NOTE,
        "total_records": int(len(frame)),
        "total_routes_covered": int(
            frame["route_id"].nunique()
        ),
        "total_corridors": int(corridors),
        "columns": list(frame.columns),
        "storm_risk_distribution": _distribution(
            "storm_risk"
        ),
        "weather_condition_distribution": _distribution(
            "weather_condition"
        ),
        "thresholds": RISK_THRESHOLDS,
    }
