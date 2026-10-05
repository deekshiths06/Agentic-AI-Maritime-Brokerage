# =========================================================
# TEST SUPPORT
# =========================================================
# Shared fixtures for the assistant test suite.
#
# The records below use the EXACT field names the existing
# `_serialize_shipment` and `_serialize_history_record`
# functions produce, so the assistant is exercised against the
# real payload shape rather than a convenient one.
#
# The values mirror a real analysis of the Mumbai -> Kochi
# lane for two containers of perishable cargo, so the figures
# in the tests are the figures the agents actually produce.
# =========================================================

import os
import sys


# Allow `python -m unittest discover -s tests` to import the
# application modules from the backend root.

BACKEND_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

if BACKEND_ROOT not in sys.path:

    sys.path.insert(0, BACKEND_ROOT)


OWNER_ID = "USR-OWNER-0001"
OTHER_USER_ID = "USR-OTHER-0002"

ADMIN_STATS = {
    "total_users": 4,
    "total_shipments": 2,
    "total_quotations": 3,
    "active_shipments": 1,
}

STATUS_FLOW = [
    "Shipment Created",
    "Cargo Loaded",
    "Vessel Departed",
    "In Transit",
    "Arrived at Port",
    "Customs Cleared",
    "Delivered",
]


HISTORY_RECORD = {
    "id": "history-owner-0001",
    "user_id": OWNER_ID,
    "user_contact": "owner@example.com",
    "user_name": "Shipper One",
    "origin": "Mumbai",
    "destination": "Kochi",
    "cargo_type": "Perishable",
    "cargo_subtype": "Fresh Fruits",
    "containers": 2,
    "route_id": "R00001",
    "route_name": "Economy Service",
    "transit_days": 9,
    "distance_nm": 4547,
    "transshipments": 1,
    "route_score": 21.27,
    "total_available_routes": 2,
    "route_reasons": [
        "Lower sailing distance compared with alternative "
        "routes.",
        "Fewer transshipment stops reduce handling "
        "complexity.",
        "2 available routes were evaluated for this "
        "shipment.",
    ],
    "weather": {
        "route_id": "R00001",
        "origin": "Mumbai",
        "destination": "Kochi",
        "weather_risk": "LOW",
        "risk_reason": (
            "Normal weather conditions. Storm risk Low, wind "
            "14 knots, waves 1.0 m, rainfall 2 mm and "
            "visibility 17.4 km are all within normal "
            "sailing limits."
        ),
        "advisory": (
            "Normal weather conditions. No weather-related "
            "delay is expected for this voyage."
        ),
        "storm_risk": "Low",
        "wind_speed_knots": 14,
        "wave_height_m": 1.0,
        "rainfall_mm": 2,
        "visibility_km": 17.4,
        "weather_condition": "Fair",
    },
    "customs": {
        "customs_id": "C00001",
        "route_id": "R00001",
        "customs_status": "Valid",
        "compliance_percent": 100,
        "missing": [],
    },
    "pricing": {
        "containers": 2,
        "base_freight_usd": 4722.0,
        "base_freight_per_container_usd": 2361.0,
        "fuel_surcharge_usd": 200.0,
        "port_charge_usd": 150.0,
        "risk_surcharge_usd": 100.0,
        "demand_factor": 1.0,
        "operating_cost_usd": 5172.0,
        "demand_adjusted_cost_usd": 5172.0,
        "target_margin_percent": 15.0,
    },
    "margin": {
        "target_margin_percent": 15.0,
        "recommended_selling_price_usd": 6084.71,
        "expected_profit_usd": 912.71,
        "achieved_margin_percent": 15.0,
    },
    "created_at": "2026-01-05T09:30:00+00:00",
}


SHIPMENT_RECORD = {
    "shipment_id": "SHP-1001",
    "user_id": OWNER_ID,
    "user_contact": "owner@example.com",
    "user_name": "Shipper One",
    "origin": "Mumbai",
    "destination": "Kochi",
    "cargo_type": "Perishable",
    "cargo_subtype": "Fresh Fruits",
    "containers": 2,
    "route_id": "R00001",
    "route_name": "Economy Service",
    "transit_days": 9,
    "distance_nm": 4547,
    "transshipments": 1,
    "quotation_id": "history-owner-0001",
    "pricing": HISTORY_RECORD["pricing"],
    "margin": HISTORY_RECORD["margin"],
    "weather": HISTORY_RECORD["weather"],
    "status": "In Transit",
    "status_history": [
        {
            "status": "Shipment Created",
            "at": "2026-01-06T10:00:00+00:00",
        },
        {
            "status": "Cargo Loaded",
            "at": "2026-01-07T08:15:00+00:00",
        },
        {
            "status": "Vessel Departed",
            "at": "2026-01-08T06:00:00+00:00",
        },
        {
            "status": "In Transit",
            "at": "2026-01-09T04:20:00+00:00",
        },
    ],
    "created_at": "2026-01-06T09:55:00+00:00",
}


# A record belonging to a DIFFERENT customer. It must never
# reach a user's fact set, and it is used to prove that.

FOREIGN_SHIPMENT_RECORD = dict(
    SHIPMENT_RECORD,
    shipment_id="SHP-2002",
    user_id=OTHER_USER_ID,
    user_contact="other@example.com",
    user_name="Someone Else",
    destination="Hamburg",
)


ADMIN_QUOTATIONS = [
    HISTORY_RECORD,
    dict(
        HISTORY_RECORD,
        id="history-other-0002",
        user_id=OTHER_USER_ID,
        user_name="Someone Else",
        status="pending",
    ),
]

ADMIN_CUSTOMS_ROWS = [
    {
        "customs_id": "C00001",
        "route_id": "R00001",
        "origin": "Mumbai",
        "destination": "Kochi",
        "cargo_type": "Perishable",
        "cargo_subtype": "Fresh Fruits",
        "customs_status": "Valid",
        "compliance_percent": 100,
    },
    {
        "customs_id": "C00007",
        "route_id": "R00007",
        "origin": "Chennai",
        "destination": "Dubai",
        "cargo_type": "Hazardous",
        "cargo_subtype": "Chemicals",
        "customs_status": "Action Required",
        "compliance_percent": 40,
    },
]

ADMIN_HEALTH = {
    "database": {
        "status": "ok",
        "detail": "connected",
    },
    "routes_dataset": {
        "status": "ok",
        "detail": "loaded",
    },
    "weather_dataset": {
        "status": "ok",
        "detail": "loaded",
    },
    "customs_dataset": {
        "status": "ok",
        "detail": "loaded",
    },
}


def no_secrets(text):
    """
    Fail if a payload contains something that must never be
    returned to a caller.
    """

    lowered = str(text or "").lower()

    forbidden = (
        "gemini_api_key",
        "ais_api_key",
        "jwt_secret",
        "admin_password",
        "mongodb_uri",
        "password\":",
        "\"password\"",
        "bcrypt",
        "authorization",
    )

    for marker in forbidden:

        if marker in lowered:
            return marker

    return None