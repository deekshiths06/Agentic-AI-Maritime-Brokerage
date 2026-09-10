# =========================================================
# PRICING DATASET GENERATOR (Milestone 2)
# =========================================================
# Generates a COMPLETE pricing.csv so every route_id that
# exists in routes.csv has exactly one pricing record.
#
# RULES
# ------
# - Fully deterministic. No random values. Re-running this
#   script always produces the identical pricing.csv.
# - Existing pricing records are PRESERVED exactly
#   (route_ids R00001..R00160 / P00001..P00160).
# - Missing routes continue the pricing_id sequence from
#   P00161 onwards, ordered by route_id.
# - route_id match / values are trimmed of whitespace.
# - routes.csv is never modified.
#
# DETERMINISTIC DATA-GENERATION RULES
# ------------------------------------
# These rules only produce pricing DATA values. They do NOT
# replace the Pricing Agent / Margin Agent formulas in
# pricing_agent.py and margin_agent.py.
#
# 1) fuel_surcharge_usd
#    Derived from routes.csv fuel_surcharge_usd
#    (range 55..1173), normalized into the existing pricing
#    dataset range [65, 210], rounded to the nearest 5.
#
# 2) port_charge_usd
#    Derived from routes.csv port_handling_usd
#    (range 220..1017), normalized into the existing pricing
#    dataset range [45, 160], rounded to nearest 5.
#
# 3) demand_factor
#    Base 1.00, adjusted deterministically by:
#      congestion_level : Low -0.05 | Moderate 0.00 | High +0.05
#      route_availability: Available 0.00 | Limited +0.05 |
#                          Waitlist +0.10
#      service_frequency: Daily -0.05 | 3 sailings/week 0.00 |
#                         Every 2 days 0.00 | Weekly +0.05
#    Clamped to [0.90, 1.15] in 0.05 steps.
#
# 4) risk_surcharge_usd
#    weather_risk base : Low 25 | Moderate 45 | Elevated 65
#    + congestion_level: Low 0 | Moderate 10 | High 20
#    + transshipments  : +5 each (capped at +30)
#    Range [25, 135]. Consistent with existing data.
#
# 5) target_margin_percent
#    Base 15, adjusted by cargo_type:
#      Bulk -3 | General Cargo -1 | Containerized 0 |
#      Perishable +2 | Hazardous +3
#    +1 if weather_risk Elevated, +1 if congestion High,
#    +1 if transshipments >= 2.
#    Clamped to [12, 20].
# =========================================================

import os
import re

import pandas as pd


def _clamp(value, low, high):
    return max(low, min(high, value))


def _round5(value):
    return int(round(value / 5.0) * 5)


def _load_routes():
    routes_path = os.path.join(
        os.path.dirname(__file__), "..", "routes.csv"
    )
    if not os.path.exists(routes_path):
        raise FileNotFoundError(
            f"routes.csv not found at {routes_path}"
        )
    df = pd.read_csv(routes_path)
    df = df.copy()
    for col in [
        "route_id",
        "cargo_type",
        "weather_risk",
        "congestion_level",
        "route_availability",
        "service_frequency",
    ]:
        if col in df.columns:
            df[col] = (
                df[col].fillna("").astype(str).str.strip()
            )
    for col in [
        "fuel_surcharge_usd",
        "port_handling_usd",
        "transshipments",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col], errors="coerce"
            )
    return df


def _load_existing_pricing():
    pricing_path = os.path.join(
        os.path.dirname(__file__), "pricing.csv"
    )
    if not os.path.exists(pricing_path):
        return None
    df = pd.read_csv(pricing_path)
    df = df.copy()
    df["route_id"] = (
        df["route_id"].fillna("").astype(str).str.strip()
    )
    return df


# ------------------------------------------------
# PRICING COMPONENT RULES
# ------------------------------------------------

FUEL_SRC_MIN = 55.0
FUEL_SRC_MAX = 1173.0
FUEL_RANGE = FUEL_SRC_MAX - FUEL_SRC_MIN
FUEL_VALUE_MIN = 65
FUEL_VALUE_MAX = 210

PORT_SRC_MIN = 220.0
PORT_SRC_MAX = 1017.0
PORT_RANGE = PORT_SRC_MAX - PORT_SRC_MIN
PORT_VALUE_MIN = 45
PORT_VALUE_MAX = 160

WEATHER_BASE = {
    "low": 25,
    "moderate": 45,
    "elevated": 65,
}

CONGESTION_RISK_ADJ = {
    "": 0,
    "low": 0,
    "moderate": 10,
    "high": 20,
}

CONGESTION_DEMAND_ADJ = {
    "": 0.00,
    "low": -0.05,
    "moderate": 0.00,
    "high": 0.05,
}

AVAILABILITY_DEMAND_ADJ = {
    "": 0.00,
    "available": 0.00,
    "limited": 0.05,
    "waitlist": 0.10,
}

FREQUENCY_DEMAND_ADJ = {
    "": 0.00,
    "daily": -0.05,
    "3 sailings/week": 0.00,
    "every 2 days": 0.00,
    "weekly": 0.05,
}

CARGO_MARGIN_ADJ = {
    "": 0,
    "bulk": -3,
    "general cargo": -1,
    "containerized": 0,
    "perishable": 2,
    "hazardous": 3,
}


def _generate_fuel(route_fuel):
    pct = _clamp(
        (route_fuel - FUEL_SRC_MIN) / FUEL_RANGE, 0.0, 1.0
    )
    return _round5(
        FUEL_VALUE_MIN + pct * (FUEL_VALUE_MAX - FUEL_VALUE_MIN)
    )


def _generate_port(port_handling):
    pct = _clamp(
        (port_handling - PORT_SRC_MIN) / PORT_RANGE, 0.0, 1.0
    )
    return _round5(
        PORT_VALUE_MIN + pct * (PORT_VALUE_MAX - PORT_VALUE_MIN)
    )


def _generate_demand_factor(route):
    congestion = route.get(
        "congestion_level", ""
    ).lower()
    availability = route.get(
        "route_availability", ""
    ).lower()
    frequency = route.get(
        "service_frequency", ""
    ).lower()

    demand = (
        1.00
        + CONGESTION_DEMAND_ADJ.get(congestion, 0.00)
        + AVAILABILITY_DEMAND_ADJ.get(availability, 0.00)
        + FREQUENCY_DEMAND_ADJ.get(frequency, 0.00)
    )

    demand = _clamp(demand, 0.90, 1.15)
    return round(demand * 20) / 20.0


def _generate_risk(route):
    weather = route.get(
        "weather_risk", ""
    ).lower()
    congestion = route.get(
        "congestion_level", ""
    ).lower()
    transshipments = route.get(
        "transshipments"
    )
    if pd.isna(transshipments) or transshipments is None:
        transshipments = 0
    transshipments = int(transshipments)

    risk = (
        WEATHER_BASE.get(weather, 25)
        + CONGESTION_RISK_ADJ.get(congestion, 0)
        + min(transshipments, 6) * 5
    )
    return _clamp(risk, 25, 135)


def _generate_margin(route):
    cargo = route.get("cargo_type", "").lower()
    weather = route.get(
        "weather_risk", ""
    ).lower()
    congestion = route.get(
        "congestion_level", ""
    ).lower()
    transshipments = route.get(
        "transshipments"
    )
    if pd.isna(transshipments) or transshipments is None:
        transshipments = 0
    transshipments = int(transshipments)

    margin = 15 + CARGO_MARGIN_ADJ.get(cargo, 0)
    if weather == "elevated":
        margin += 1
    if congestion == "high":
        margin += 1
    if transshipments >= 2:
        margin += 1
    return _clamp(margin, 12, 20)


# ------------------------------------------------
# MAIN GENERATOR
# ------------------------------------------------

def generate_pricing_csv():
    routes = _load_routes()
    existing = _load_existing_pricing()

    # Sort deterministically by route_id so output order
    # (and therefore pricing_id sequence) is stable.
    routes = routes.sort_values("route_id").reset_index(
        drop=True
    )

    # Existing pricing keyed by route_id (first occurrence).
    existing_by_route = {}
    if existing is not None:
        existing = existing.drop_duplicates(subset="route_id")
        for _, row in existing.iterrows():
            existing_by_route[
                str(row["route_id"]).strip()
            ] = row

    # Find the next free pricing_id number.
    max_existing_num = 0
    if existing is not None:
        for pid in existing["pricing_id"].astype(str):
            m = re.match(r"^P(\d+)$", pid.strip())
            if m:
                max_existing_num = max(
                    max_existing_num, int(m.group(1))
                )
    next_pricing_num = max_existing_num + 1

    records = []
    used_route_ids = set()
    used_pricing_ids = set()

    for _, route in routes.iterrows():
        route_id = str(route["route_id"]).strip()

        if route_id in used_route_ids:
            continue

        used_route_ids.add(route_id)

        existing_rec = existing_by_route.get(route_id)

        if existing_rec is not None:
            # Preserve existing pricing record exactly.
            records.append({
                "pricing_id": str(
                    existing_rec["pricing_id"]
                ).strip(),
                "route_id": route_id,
                "fuel_surcharge_usd": float(
                    existing_rec["fuel_surcharge_usd"]
                ),
                "port_charge_usd": float(
                    existing_rec["port_charge_usd"]
                ),
                "demand_factor": float(
                    existing_rec["demand_factor"]
                ),
                "risk_surcharge_usd": float(
                    existing_rec["risk_surcharge_usd"]
                ),
                "target_margin_percent": float(
                    existing_rec["target_margin_percent"]
                ),
            })
            continue

        # Generate deterministic values for missing routes.
        route_fuel = route.get("fuel_surcharge_usd", 0)
        if pd.isna(route_fuel) or route_fuel is None:
            route_fuel = 0
        route_fuel = float(route_fuel)

        port_handling = route.get("port_handling_usd", 0)
        if pd.isna(port_handling) or port_handling is None:
            port_handling = 0
        port_handling = float(port_handling)

        fuel = _generate_fuel(route_fuel)
        port = _generate_port(port_handling)
        demand = _generate_demand_factor(route)
        risk = _generate_risk(route)
        margin = _generate_margin(route)

        pricing_id = f"P{next_pricing_num:05d}"
        next_pricing_num += 1

        records.append({
            "pricing_id": pricing_id,
            "route_id": route_id,
            "fuel_surcharge_usd": fuel,
            "port_charge_usd": port,
            "demand_factor": demand,
            "risk_surcharge_usd": risk,
            "target_margin_percent": margin,
        })

    out = pd.DataFrame(records, columns=[
        "pricing_id",
        "route_id",
        "fuel_surcharge_usd",
        "port_charge_usd",
        "demand_factor",
        "risk_surcharge_usd",
        "target_margin_percent",
    ])

    # Guarantee uniqueness either way.
    out = out.drop_duplicates(
        subset=["route_id"], keep="first"
    )
    out = out.drop_duplicates(
        subset=["pricing_id"], keep="first"
    )

    pricing_path = os.path.join(
        os.path.dirname(__file__), "pricing.csv"
    )
    out.to_csv(pricing_path, index=False)

    return out


if __name__ == "__main__":
    result = generate_pricing_csv()
    print(f"pricing.csv written: {len(result)} records")
    print(
        "pricing_id range: "
        f"{result['pricing_id'].iloc[0]} .. "
        f"{result['pricing_id'].iloc[-1]}"
    )