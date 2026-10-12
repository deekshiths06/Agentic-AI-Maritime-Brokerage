# =========================================================
# FREIGHT INTELLIGENCE ENGINE (ORCHESTRATOR)
# =========================================================
# One business-facing call that runs the existing agents
# together for a single shipment:
#
#   Customer Request
#         |
#         v
# Route Agent    -> Recommended Route + Base Freight
#         |
#         v
# Pricing Agent  -> Operating Cost + Demand Adjusted Cost
#         |
#         v
# Margin Agent   -> Recommended Selling Price
#         |
#         v
# Weather Agent  -> Route weather risk      (optional layer)
# Customs Agent  -> Customs compliance      (optional layer)
#         |
#         v
# Freight Intelligence Report
#
# The orchestrator NEVER reimplements agent logic. It calls the
# exact same public functions the existing endpoints use
# (analyze_route, calculate_pricing, calculate_margin,
# analyze_weather, analyze_customs) through the existing
# generate_quotation pipeline, so a value returned here can
# never drift from what the customer sees in Route
# Intelligence or the Quotation screen.
#
# FAIL-SAFE
# Weather and customs are optional layers. When they are
# unavailable the report still succeeds and carries their
# "not available" payload, exactly like the dedicated
# endpoints. Only route + pricing + margin are authoritative:
# if the quotation pipeline fails, this engine fails with the
# same user-facing message the existing quotation endpoint
# returns.
# =========================================================

import logging

from app.agents.quotation_service import (
    generate_quotation
)
from app.agents.weather_agent import (
    analyze_weather
)
from app.agents.customs_agent import (
    analyze_customs
)


logger = logging.getLogger("uvicorn.error")


# =========================================================
# SAFE OPTIONAL LAYER
# =========================================================
# Runs one agent and degrades to a structured "not
# available" result. The optional layers must never abort the
# whole report.
# =========================================================

def _safe_layer(agent_name, loader):

    try:

        result = loader()

        return {
            "agent": agent_name,
            "status": "success",
            "available": True,
            "result": result
        }

    except Exception as error:

        logger.warning(
            "Freight Intelligence: %s unavailable: %s",
            agent_name,
            error
        )

        return {
            "agent": agent_name,
            "status": "not_available",
            "available": False,
            "message": (
                f"{agent_name} information is not available "
                "for this shipment."
            ),
            "result": None
        }


# =========================================================
# GENERATE FREIGHT INTELLIGENCE
# =========================================================

def generate_freight_intelligence(
    origin: str,
    destination: str,
    cargo_type: str,
    cargo_subtype: str,
    containers: int
):
    """
    Produce a complete Freight Intelligence report for one
    shipment by orchestrating the existing agents.

    The route, pricing, margin and alternative-route sections
    come unchanged from the existing quotation pipeline so the
    reported prices always match the customer's quotation.

    Weather and customs are resolved as optional layers: an
    unavailable dataset is reported as "not available" inside
    the report instead of failing the whole request.

    Raises
    ------
    ValueError
        When the authoritative route/pricing/margin pipeline
        fails, with the same user-facing message the existing
        quotation endpoint returns.
    """

    quotation = generate_quotation(
        origin,
        destination,
        cargo_type,
        cargo_subtype,
        containers
    )

    recommended_route = (quotation.get("route") or {})

    recommended_route_id = str(
        recommended_route.get("route_id", "")
    ).strip()

    agents = {
        "route": "success",
        "pricing": "success",
        "margin": "success",
        "weather": "not_available",
        "customs": "not_available"
    }

    # -------------------------------------------------
    # WEATHER AGENT (optional layer)
    # -------------------------------------------------

    weather_layer = _safe_layer(
        "weather",
        lambda: analyze_weather(
            route_id=recommended_route_id,
            origin=origin,
            destination=destination
        )
    )

    if weather_layer["available"]:

        agents["weather"] = "success"

    # -------------------------------------------------
    # CUSTOMS AGENT (optional layer)
    # -------------------------------------------------

    customs_layer = _safe_layer(
        "customs",
        lambda: analyze_customs(
            origin=origin,
            destination=destination,
            cargo_type=cargo_type,
            cargo_subtype=cargo_subtype,
            route_id=recommended_route_id
        )
    )

    if customs_layer["available"]:

        agents["customs"] = "success"

    # -------------------------------------------------
    # FREIGHT INTELLIGENCE REPORT
    # -------------------------------------------------

    margin = quotation.get("margin") or {}

    report = {
        "status": "success",

        # ---------------------------------------------
        # SHIPMENT
        # ---------------------------------------------

        "shipment": quotation.get("shipment", {}),

        # ---------------------------------------------
        # ROUTE INTELLIGENCE
        # ---------------------------------------------

        "route": {
            "recommended": {
                "route_id": recommended_route.get(
                    "route_id"
                ),
                "route_name": recommended_route.get(
                    "route_name"
                ),
                "transit_days": recommended_route.get(
                    "transit_days"
                ),
                "distance_nm": recommended_route.get(
                    "distance_nm"
                ),
                "transshipments": recommended_route.get(
                    "transshipments"
                ),
                "route_score": recommended_route.get(
                    "route_score"
                ),
            },
            "alternative_routes": quotation.get(
                "alternative_routes", []
            ),
            "total_available_routes": (
                len(quotation.get("alternative_routes", []))
                + 1
            ),
            "reasons": quotation.get("reasons", []),
        },

        # ---------------------------------------------
        # PRICING INTELLIGENCE
        # Mirrors the existing quotation structure exactly,
        # so the same customer/admins display rules apply.
        # ---------------------------------------------

        "pricing": quotation.get("pricing", {}),
        "margin": margin,
        "quotation_total_usd": margin.get(
            "recommended_selling_price_usd"
        ),

        # ---------------------------------------------
        # OPTIONAL INTELLIGENCE LAYERS
        # ---------------------------------------------

        "weather": weather_layer,
        "customs": customs_layer,
        "agents": agents,
    }

    return report