import os

import pandas as pd


# =========================================================
# COST & SUSTAINABILITY AGENT
# =========================================================
# Responsibility:
#   "How sustainable is this voyage?"
#
# The agent grades a single voyage on four operational
# factors and returns one overall sustainability score out of
# 100, a CII-style category letter and a plain-language rating
# label, plus every component score and the arithmetic that
# combines them.
#
# IMPORTANT - PROVENANCE OF THE RULES
# ------------------------------------
# The project README documents this agent as a four-factor,
# weighted, rule-based scorer:
#
#   | Factor                         | Weight |
#   |--------------------------------|--------|
#   | Emission intensity             |  40%   |
#   | Speed-to-efficiency            |  25%   |
#   | Port waiting and idle time     |  15%   |
#   | Fuel and technology tier        |  20%   |
#
# The README states the weights and the general process but
# does NOT contain the numeric point bands. The exact
# breakpoints and point tables below are therefore authored
# here and are clearly documented so every score can be
# explained and audited. They do not silently change any
# other agent's behaviour: this module is purely additive and
# reads only routes.csv.
#
# The agent NEVER replaces, re-scores or overrides the Route,
# Pricing or Margin agents.
#
# GENERAL PROCESS (matches the README)
# ------------------------------------
#   1. Read the relevant voyage and fuel inputs.
#   2. Calculate the emission-intensity score.
#   3. Calculate the speed-efficiency score.
#   4. Calculate the port-waiting score.
#   5. Assign fuel-category points.
#   6. Combine the component scores with the weights and apply
#      the configured score limits (0 - 100).
#   7. Assign a category letter and rating label.
#   8. Return the total and component-level results.
#
# MISSING DATA
# ------------
# Each factor is optional. When an input is genuinely not
# available the factor is marked unavailable, its weight is
# removed from the total and the remaining weights are
# renormalised, so a partial score is still honest and
# explainable. When NO factor can be scored the agent returns
# status "insufficient_data" instead of inventing a number.
# =========================================================


# =========================================================
# DATASET PATH
# =========================================================
# Resolved from this module's own location so routes.csv is
# found no matter which directory the backend was started
# from. The dataset itself stays exactly where it is.

ROUTES_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "routes.csv"
)


# =========================================================
# FACTOR WEIGHTS (from the README)
# =========================================================
# The weights are exactly the four values documented in the
# project README. They sum to 1.0.

FACTOR_WEIGHTS = {
    "emission_intensity": 0.40,
    "speed_efficiency": 0.25,
    "port_waiting": 0.15,
    "fuel_tier": 0.20,
}


# =========================================================
# EMISSION INTENSITY BANDS
# =========================================================
# Input unit: kilograms of CO2 per nautical mile
# (derived from the dataset as estimated_co2_kg / distance_nm).
# Lower is better. A voyage at or below EMISSION_BEST kg/nm
# scores the full 100 points; at or above EMISSION_WORST it
# scores 0. Between the two the score falls linearly. This is
# the same shape the CII-style banding uses: best-in-class
# gets top marks and the worst case gets none.

EMISSION_BEST_KG_PER_NM = 8.0
EMISSION_WORST_KG_PER_NM = 18.0


# =========================================================
# SPEED-EFFICIENCY BAND
# =========================================================
# Input unit: average sailing speed in knots
# (derived from the dataset as distance_nm / (transit_days*24)).
#
# A moderate service speed is the most efficient compromise
# between fuel burned per day and cargo delivered per day.
# The band 14-18 knots scores the full 100 points. Below the
# band (over-slow steaming) and above the band (over-fast
# steaming) points are deducted linearly at the rates below.
# The deduction is capped at 0 by the score limits.

SPEED_OPTIMAL_MIN_KNOTS = 14.0
SPEED_OPTIMAL_MAX_KNOTS = 18.0
SPEED_UNDER_PENALTY_PER_KNOT = 5.0
SPEED_OVER_PENALTY_PER_KNOT = 4.0


# =========================================================
# PORT WAITING BANDS
# =========================================================
# Input unit: total port waiting / idle hours for the voyage.
# Lower is better. At or below WAIT_BEST_HOURS scores 100;
# at or above WAIT_WORST_HOURS scores 0; linear in between.

WAIT_BEST_HOURS = 6.0
WAIT_WORST_HOURS = 48.0


# =========================================================
# FUEL / TECHNOLOGY TIER POINTS
# =========================================================
# Input: an explicit fuel type, or a vessel_type from
# routes.csv. Cleaner fuels and newer "eco" vessel classes
# score higher. Unknown values count as unavailable.

FUEL_TYPE_POINTS = {
    "lng": 100.0,
    "liquefied natural gas": 100.0,
    "methanol": 95.0,
    "lpg": 90.0,
    "biofuel": 88.0,
    "vlsfo": 72.0,
    "very low sulphur fuel oil": 72.0,
    "mgo": 66.0,
    "marine gas oil": 66.0,
    "hfo": 42.0,
    "heavy fuel oil": 42.0,
}

VESSEL_TYPE_POINTS = {
    "eco container ship": 100.0,
    "container ship": 80.0,
    "large container ship": 65.0,
    "panamax container ship": 55.0,
    "post-panamax container ship": 50.0,
    "feeder + mainline": 45.0,
}


# =========================================================
# CATEGORY / RATING THRESHOLDS
# =========================================================
# Evaluated top to bottom: the first threshold the overall
# score meets or exceeds wins. CII-style A-E letters with a
# plain-language label.

CATEGORY_THRESHOLDS = (
    (85.0, "A", "Excellent"),
    (70.0, "B", "Good"),
    (55.0, "C", "Moderate"),
    (40.0, "D", "Needs Improvement"),
    (0.0, "E", "Poor"),
)


# =========================================================
# INDICATIVE PORT WAIT ESTIMATE
# =========================================================
# routes.csv does NOT store measured waiting hours. When the
# caller does not supply port_wait_hours, the agent derives an
# INDICATIVE estimate from the port congestion level and the
# number of port calls the voyage makes. This is a modelled
# estimate for the scoring exercise, never a real-time
# measurement, and the result marks it as "estimated".

CONGESTION_WAIT_HOURS = {
    "low": 4.0,
    "moderate": 14.0,
    "high": 30.0,
}

WAIT_PER_EXTRA_PORT_HOURS = 2.0


# =========================================================
# SCORE LIMITS
# =========================================================

SCORE_MIN = 0.0
SCORE_MAX = 100.0


# =========================================================
# SMALL NUMERIC HELPERS
# =========================================================

def _clamp_score(value):
    """Clamp a points value into the configured 0-100 range."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:  # NaN
        return None

    return max(SCORE_MIN, min(SCORE_MAX, number))


def _is_number(value):
    """True when value is a real, finite number."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return False

    if number != number:  # NaN
        return False

    return number not in (float("inf"), float("-inf"))


def _round(value, places=1):
    if value is None:
        return None

    return round(float(value), places)


# =========================================================
# COMPONENT SCORING FUNCTIONS
# =========================================================

def score_emission_intensity(emission_intensity):
    """
    Emission-intensity points (0-100), lower intensity better.

    Formula (piecewise linear):
        <= EMISSION_BEST            -> 100
        >= EMISSION_WORST           -> 0
        otherwise                   -> 100 * (WORST - x) /
                                       (WORST - BEST)
    Returns None when the input is not a usable number.
    """

    if not _is_number(emission_intensity):
        return None

    intensity = float(emission_intensity)

    if intensity <= EMISSION_BEST_KG_PER_NM:
        return 100.0

    if intensity >= EMISSION_WORST_KG_PER_NM:
        return 0.0

    span = (
        EMISSION_WORST_KG_PER_NM
        - EMISSION_BEST_KG_PER_NM
    )

    return (
        100.0
        * (EMISSION_WORST_KG_PER_NM - intensity)
        / span
    )


def score_speed_efficiency(average_speed_knots):
    """
    Speed-efficiency points (0-100).

    Formula (banded linear penalty):
        inside 14-18 knots          -> 100
        below band                  -> 100 - (min - v) * 5
        above band                  -> 100 - (v - max) * 4
    The result is clamped to 0-100. Returns None when the
    input is not a usable number.
    """

    if not _is_number(average_speed_knots):
        return None

    speed = float(average_speed_knots)

    if SPEED_OPTIMAL_MIN_KNOTS <= speed <= SPEED_OPTIMAL_MAX_KNOTS:
        return 100.0

    if speed < SPEED_OPTIMAL_MIN_KNOTS:

        penalty = (
            SPEED_OPTIMAL_MIN_KNOTS - speed
        ) * SPEED_UNDER_PENALTY_PER_KNOT

    else:

        penalty = (
            speed - SPEED_OPTIMAL_MAX_KNOTS
        ) * SPEED_OVER_PENALTY_PER_KNOT

    return _clamp_score(100.0 - penalty)


def score_port_waiting(port_wait_hours):
    """
    Port waiting / idle points (0-100), lower waiting better.

    Formula (piecewise linear):
        <= WAIT_BEST_HOURS          -> 100
        >= WAIT_WORST_HOURS         -> 0
        otherwise                   -> 100 * (WORST - x) /
                                       (WORST - BEST)
    Returns None when the input is not a usable number.
    """

    if not _is_number(port_wait_hours):
        return None

    hours = float(port_wait_hours)

    if hours < 0:
        hours = 0.0

    if hours <= WAIT_BEST_HOURS:
        return 100.0

    if hours >= WAIT_WORST_HOURS:
        return 0.0

    span = WAIT_WORST_HOURS - WAIT_BEST_HOURS

    return (
        100.0
        * (WAIT_WORST_HOURS - hours)
        / span
    )


def score_fuel_tier(fuel_type=None, vessel_type=None):
    """
    Fuel / technology tier points (0-100).

    An explicit fuel_type is preferred and matched against
    FUEL_TYPE_POINTS. Otherwise the routes.csv vessel_type is
    matched against VESSEL_TYPE_POINTS. Unknown / missing
    values return (None, source) so the factor is treated as
    unavailable rather than scored.

    Returns a tuple (points, source) where source describes
    which input produced the score.
    """

    if fuel_type:

        key = str(fuel_type).strip().lower()

        if key in FUEL_TYPE_POINTS:

            return FUEL_TYPE_POINTS[key], "fuel_type"

    if vessel_type:

        key = str(vessel_type).strip().lower()

        if key in VESSEL_TYPE_POINTS:

            return VESSEL_TYPE_POINTS[key], "vessel_type"

    return None, None


# =========================================================
# DERIVE INPUTS FROM ROUTES.CSV
# =========================================================
# Everything below reads existing columns from routes.csv
# only. Nothing is fabricated: a derived value is only
# produced when the underlying column is present and numeric.

def load_routes():
    """Load routes.csv with cleaned column names."""

    df = pd.read_csv(ROUTES_CSV_PATH)

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
    )

    return df


def _safe_number(row, column):
    """Return a finite float from a row/column or None."""

    if column not in row:
        return None

    value = row.get(column)

    if value is None or pd.isna(value):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    return number


def _safe_text(row, column):
    if column not in row:
        return ""

    value = row.get(column)

    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def derive_wait_hours(
    congestion_level,
    port_calls
):
    """
    Indicative waiting hours from congestion + port calls.

    This is a MODELLED estimate, never a measurement. It is
    only used when the caller does not provide a real
    port_wait_hours value.
    """

    hours = 0.0
    known = False

    key = str(congestion_level or "").strip().lower()

    if key in CONGESTION_WAIT_HOURS:
        hours += CONGESTION_WAIT_HOURS[key]
        known = True

    if _is_number(port_calls):

        extra_ports = max(0.0, float(port_calls) - 2.0)

        hours += extra_ports * WAIT_PER_EXTRA_PORT_HOURS
        known = True

    if not known:
        return None

    return hours


def derive_route_inputs(route_id):
    """
    Look up one route in routes.csv and derive the
    sustainability inputs that the dataset can actually
    support.

    Returns a dict of raw inputs and their provenance, or an
    empty dict when the route is unknown. Never raises for a
    missing route: the caller reports it as missing data.
    """

    route_id = str(route_id or "").strip()

    if not route_id:
        return {}

    try:

        df = load_routes()

    except Exception:
        return {}

    match = df[df["route_id"].astype(str).str.strip() == route_id]

    if match.empty:
        return {}

    row = match.iloc[0]

    distance_nm = _safe_number(row, "distance_nm")
    transit_days = _safe_number(row, "transit_days")
    estimated_co2_kg = _safe_number(row, "estimated_co2_kg")
    port_calls = _safe_number(row, "port_calls")

    inputs = {
        "route_id": route_id,
        "origin": _safe_text(row, "origin"),
        "destination": _safe_text(row, "destination"),
        "vessel_type": _safe_text(row, "vessel_type"),
        "congestion_level": _safe_text(row, "congestion_level"),
    }

    # -----------------------------------------------
    # EMISSION INTENSITY (kg CO2 per nautical mile)
    # -----------------------------------------------

    if (
        estimated_co2_kg is not None
        and distance_nm is not None
        and distance_nm > 0
    ):

        inputs["emission_intensity"] = (
            estimated_co2_kg / distance_nm
        )

    # -----------------------------------------------
    # AVERAGE SPEED (knots)
    # -----------------------------------------------

    if (
        distance_nm is not None
        and transit_days is not None
        and transit_days > 0
    ):

        inputs["average_speed_knots"] = (
            distance_nm / (transit_days * 24.0)
        )

    # -----------------------------------------------
    # INDICATIVE PORT WAIT (modelled, not measured)
    # -----------------------------------------------

    wait = derive_wait_hours(
        inputs.get("congestion_level"), port_calls
    )

    if wait is not None:

        inputs["port_wait_hours"] = wait
        inputs["port_wait_estimated"] = True

    return inputs


# =========================================================
# THE AGENT
# =========================================================

class CostSustainabilityAgent:
    """
    Rule-based four-factor voyage sustainability scorer.

    Usage:
        agent = CostSustainabilityAgent()
        result = agent.calculate_sustainability_score(
            route_id="R00001"
        )
    """

    name = "cost_sustainability"
    display_name = "Cost & Sustainability Agent"

    @property
    def weights(self):
        return dict(FACTOR_WEIGHTS)

    def calculate_sustainability_score(
        self,
        route_id="",
        emission_intensity=None,
        average_speed_knots=None,
        port_wait_hours=None,
        fuel_type="",
        vessel_type=""
    ):
        """
        Score a voyage on emission intensity, speed
        efficiency, port waiting and fuel tier.

        Explicit values always win. Any value that is still
        missing is derived from routes.csv when route_id is
        supplied. Factors that remain unavailable are excluded
        and the remaining weights are renormalised.

        Raises ValueError only when no factor can be scored at
        all (status "insufficient_data" is returned instead in
        the endpoint layer).
        """

        derived = {}

        if route_id:

            derived = derive_route_inputs(route_id)

            if not derived:

                # Unknown route: still allow explicit inputs to
                # score, but record that the lookup failed.
                derived = {"route_id": str(route_id).strip()}

        source = {}

        # -----------------------------------------------
        # RESOLVE EACH INPUT (explicit first, derived next)
        # -----------------------------------------------

        def _resolve(explicit, key):
            nonlocal source
            if _is_number(explicit):
                return float(explicit)
            if key in derived and _is_number(derived[key]):
                return float(derived[key])
            return None

        resolved_emission = _resolve(
            emission_intensity, "emission_intensity"
        )
        resolved_speed = _resolve(
            average_speed_knots, "average_speed_knots"
        )
        resolved_wait = _resolve(
            port_wait_hours, "port_wait_hours"
        )

        # -----------------------------------------------
        # FUEL TIER
        # -----------------------------------------------

        resolved_vessel = (
            str(vessel_type).strip()
            or str(derived.get("vessel_type", "")).strip()
        )

        fuel_points, fuel_source = score_fuel_tier(
            fuel_type=fuel_type,
            vessel_type=resolved_vessel,
        )

        # -----------------------------------------------
        # COMPONENT SCORES
        # -----------------------------------------------

        emission_points = score_emission_intensity(
            resolved_emission
        )
        speed_points = score_speed_efficiency(resolved_speed)
        wait_points = score_port_waiting(resolved_wait)

        components = {
            "emission_intensity": {
                "label": "Emission Intensity",
                "points": _round(emission_points),
                "available": emission_points is not None,
                "input": _round(resolved_emission, 2),
                "unit": "kg CO2 / nm",
                "source": (
                    "derived from dataset"
                    if emission_intensity is None
                    and resolved_emission is not None
                    else (
                        "provided"
                        if resolved_emission is not None
                        else None
                    )
                ),
            },
            "speed_efficiency": {
                "label": "Speed Efficiency",
                "points": _round(speed_points),
                "available": speed_points is not None,
                "input": _round(resolved_speed, 2),
                "unit": "knots",
                "source": (
                    "derived from dataset"
                    if average_speed_knots is None
                    and resolved_speed is not None
                    else (
                        "provided"
                        if resolved_speed is not None
                        else None
                    )
                ),
            },
            "port_waiting": {
                "label": "Port Waiting / Idle",
                "points": _round(wait_points),
                "available": wait_points is not None,
                "input": _round(resolved_wait, 1),
                "unit": "hours",
                "source": (
                    "estimated from congestion"
                    if port_wait_hours is None
                    and resolved_wait is not None
                    and derived.get("port_wait_estimated")
                    else (
                        "provided"
                        if resolved_wait is not None
                        else None
                    )
                ),
            },
            "fuel_tier": {
                "label": "Fuel / Technology Tier",
                "points": _round(fuel_points),
                "available": fuel_points is not None,
                "input": (
                    str(fuel_type).strip()
                    or resolved_vessel
                    or None
                ),
                "unit": "tier",
                "source": fuel_source,
            },
        }

        # -----------------------------------------------
        # WEIGHTED TOTAL (renormalised over available factors)
        # -----------------------------------------------

        available_weight = 0.0
        weighted_sum = 0.0

        for key, weight in FACTOR_WEIGHTS.items():

            component = components[key]

            component["weight"] = weight

            if component["available"]:
                available_weight += weight
                weighted_sum += component["points"] * weight

        missing_inputs = [
            components[key]["label"]
            for key in FACTOR_WEIGHTS
            if not components[key]["available"]
        ]

        if available_weight <= 0:

            return {
                "status": "insufficient_data",
                "agent": self.name,
                "agent_label": self.display_name,
                "route_id": str(route_id or "").strip(),
                "sustainability_score": None,
                "category": None,
                "rating_label": None,
                "components": components,
                "weights": dict(FACTOR_WEIGHTS),
                "missing_inputs": missing_inputs,
                "explanation": (
                    "Not enough voyage data is available to "
                    "calculate a sustainability score. Provide "
                    "emission intensity, average speed, port "
                    "waiting time or a fuel/vessel tier."
                ),
                "formula_explanation": self.formula_explanation(),
                "data_note": self.data_note(),
            }

        sustainability_score = weighted_sum / available_weight

        # -----------------------------------------------
        # ATTACH WEIGHTED CONTRIBUTIONS AS PERCENT OF TOTAL
        # -----------------------------------------------

        for key, weight in FACTOR_WEIGHTS.items():

            component = components[key]

            if component["available"]:

                contribution = (
                    component["points"] * weight
                    / available_weight
                )

                component["weighted_points"] = _round(
                    contribution
                )

                component["effective_weight"] = _round(
                    weight / available_weight, 3
                )

            else:

                component["weighted_points"] = None
                component["effective_weight"] = 0.0

        category, rating_label = self.classify(
            sustainability_score
        )

        return {
            "status": "success",
            "agent": self.name,
            "agent_label": self.display_name,
            "route_id": str(route_id or "").strip(),
            "sustainability_score": _round(
                sustainability_score
            ),
            "max_score": int(SCORE_MAX),
            "category": category,
            "rating_label": rating_label,
            "components": components,
            "weights": dict(FACTOR_WEIGHTS),
            "missing_inputs": missing_inputs,
            "explanation": self.explain(
                sustainability_score,
                category,
                rating_label,
                available_weight,
                missing_inputs,
            ),
            "formula_explanation": self.formula_explanation(),
            "data_note": self.data_note(),
        }

    # -----------------------------------------------------
    # CLASSIFICATION
    # -----------------------------------------------------

    @staticmethod
    def classify(score):
        """Return (category letter, rating label) for a score."""

        for threshold, category, label in CATEGORY_THRESHOLDS:

            if score >= threshold:

                return category, label

        return CATEGORY_THRESHOLDS[-1][1], CATEGORY_THRESHOLDS[-1][2]

    # -----------------------------------------------------
    # EXPLANATIONS
    # -----------------------------------------------------

    @staticmethod
    def explain(
        score,
        category,
        rating_label,
        available_weight,
        missing_inputs
    ):
        """Short plain-language reading of the result."""

        parts = [
            f"The voyage scores {round(float(score), 1)} out of "
            f"100, giving category {category} ({rating_label})."
        ]

        if available_weight < 1.0:

            scored = [
                key
                for key in FACTOR_WEIGHTS
            ]

            parts.append(
                "The score combines the four weighted factors "
                "after renormalising for the factors that could "
                "not be scored."
            )

        if missing_inputs:

            parts.append(
                "Unavailable factor(s): "
                + ", ".join(missing_inputs)
                + "."
            )

        return " ".join(parts)

    @staticmethod
    def formula_explanation():
        """The weighted formula, as a readable string."""

        return (
            "Overall score = "
            "40% x Emission Intensity + "
            "25% x Speed Efficiency + "
            "15% x Port Waiting + "
            "20% x Fuel/Technology Tier. "
            "Each factor is first scored 0-100 from its own "
            "documented bands, then the weighted average is "
            "taken. When a factor has no data its weight is "
            "removed and the remaining weights are renormalised."
        )

    @staticmethod
    def data_note():
        """Honest statement of where the numbers come from."""

        return (
            "Inputs are derived from the project routes.csv "
            "dataset (estimated CO2, sailing distance, transit "
            "days, port calls, congestion and vessel type). "
            "Port waiting is an indicative estimate from "
            "congestion and port calls when no measured value "
            "is supplied. This is a rule-based project score, "
            "not an official IMO/CII regulatory rating and not "
            "a real-time emissions measurement."
        )


# =========================================================
# MODULE-LEVEL CONVENIENCE FUNCTION
# =========================================================
# Mirrors the other agents, which expose a plain function
# around their class.

def calculate_sustainability_score(**kwargs):
    """Convenience wrapper around CostSustainabilityAgent."""

    return CostSustainabilityAgent().calculate_sustainability_score(
        **kwargs
    )
