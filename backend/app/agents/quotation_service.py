# =========================================================
# QUOTATION SERVICE
# =========================================================
# Orchestrates the multi-agent pricing pipeline:
#
# Customer Request
#         |
#         v
# Route Agent         -> Recommended Route + Base Freight
#         |
#         v
# Pricing Agent       -> Operating Cost + Demand Adjusted Cost
#         |
#         v
# Margin Agent        -> Recommended Selling Price
#         |
#         v
# Final Quotation     -> Complete pricing breakdown
#
# Each agent has a single responsibility:
#   Route Agent:   "What is the best route?"
#   Pricing Agent: "What does the selected route cost?"
#   Margin Agent:  "What selling price gives the margin?"
# =========================================================

import pandas as pd
import os

from app.agents.route_agent import (
    load_routes,
    analyze_route
)
from app.agents.pricing_agent import (
    calculate_pricing
)
from app.agents.margin_agent import (
    calculate_margin
)


# =========================================================
# EXTRACT BASE FREIGHT FROM ROUTES.CSV
# =========================================================
# The route_agent returns route details but does not
# include freight_cost_usd. We look it up separately
# from routes.csv using the recommended route_id.
# =========================================================

def _get_base_freight(route_id: str) -> float:
    """
    Look up the base freight cost for a given route_id
    from routes.csv.
    """

    df = load_routes()

    match = df[df["route_id"] == route_id]

    if match.empty:
        raise ValueError(
            f"Route '{route_id}' not found in routes.csv."
        )

    row = match.iloc[0]

    freight = row.get("freight_cost_usd")

    if freight is None or pd.isna(freight):
        raise ValueError(
            f"No freight cost available for route "
            f"'{route_id}'."
        )

    return float(freight)


# =========================================================
# ALTERNATIVE ROUTES WITH PRICING
# =========================================================

def _get_alternative_routes_with_pricing(
    route_result: dict,
    recommended_route_id: str
):
    """
    Build a list of alternative routes with their
    pricing data for comparison.
    """

    all_routes = route_result.get("routes", [])

    alternatives = []

    for route in all_routes:
        rid = str(route.get("route_id", "")).strip()

        if rid == recommended_route_id:
            continue

        try:
            pricing = calculate_pricing(
                rid,
                _get_base_freight(rid)
            )
        except Exception:
            pricing = None

        alt_entry = {
            "route_id": rid,
            "route_name": route.get("route", ""),
            "transit_days": route.get("transit_days"),
            "distance_nm": route.get("distance_nm"),
            "transshipments": route.get(
                "transshipments"
            ),
            "score": route.get("score"),
        }

        if pricing and pricing.get("status") == "success":
            alt_entry["base_freight_usd"] = pricing[
                "base_freight_usd"
            ]
            alt_entry["operating_cost_usd"] = pricing[
                "operating_cost_usd"
            ]
            alt_entry["demand_adjusted_cost_usd"] = (
                pricing["demand_adjusted_cost_usd"]
            )
        else:
            alt_entry["base_freight_usd"] = None
            alt_entry["operating_cost_usd"] = None
            alt_entry["demand_adjusted_cost_usd"] = None

        alternatives.append(alt_entry)

    return alternatives


# =========================================================
# GENERATE QUOTATION
# =========================================================

def generate_quotation(
    origin: str,
    destination: str,
    cargo_type: str,
    cargo_subtype: str,
    containers: int
):
    """
    Generate a complete dynamic quotation by orchestrating
    the Route Agent, Pricing Agent, and Margin Agent.

    Parameters
    ----------
    origin : str
        Origin port.
    destination : str
        Destination port.
    cargo_type : str
        Cargo type.
    cargo_subtype : str
        Cargo subtype.
    containers : int
        Number of containers.

    Returns
    -------
    dict
        Complete quotation with all pricing breakdowns.
    """

    try:

        # -----------------------------------------------
        # STEP 1: ROUTE AGENT
        # "What is the best route?"
        # -----------------------------------------------

        route_result = analyze_route(
            origin,
            destination,
            cargo_type,
            cargo_subtype,
            containers
        )

        recommended = route_result.get(
            "recommended_route"
        )

        if not recommended:
            raise ValueError(
                "Route Agent did not return a "
                "recommended route."
            )

        recommended_route_id = str(
            recommended.get("route_id", "")
        ).strip()

        if not recommended_route_id:
            raise ValueError(
                "Recommended route has no route_id."
            )

        # -----------------------------------------------
        # STEP 2: GET BASE FREIGHT
        # -----------------------------------------------

        base_freight = _get_base_freight(
            recommended_route_id
        )

        # -----------------------------------------------
        # STEP 3: PRICING AGENT
        # "What does the selected route cost?"
        # -----------------------------------------------

        pricing_result = calculate_pricing(
            recommended_route_id,
            base_freight
        )

        if pricing_result.get("status") != "success":
            raise ValueError(
                "Pricing Agent failed to calculate cost."
            )

        demand_adjusted_cost = pricing_result[
            "demand_adjusted_cost_usd"
        ]

        target_margin = pricing_result[
            "target_margin_percent"
        ]

        # -----------------------------------------------
        # STEP 4: MARGIN AGENT
        # "What selling price gives us the margin?"
        # -----------------------------------------------

        margin_result = calculate_margin(
            demand_adjusted_cost,
            target_margin
        )

        if margin_result.get("status") != "success":
            raise ValueError(
                "Margin Agent failed to calculate "
                "selling price."
            )

        # -----------------------------------------------
        # STEP 5: ALTERNATIVE ROUTES
        # -----------------------------------------------

        alternatives = (
            _get_alternative_routes_with_pricing(
                route_result,
                recommended_route_id
            )
        )

        # -----------------------------------------------
        # STEP 6: FINAL QUOTATION
        # -----------------------------------------------

        quotation = {

            # -------------------------------------------
            # SHIPMENT DETAILS
            # -------------------------------------------

            "shipment": {
                "origin": origin,
                "destination": destination,
                "cargo_type": cargo_type,
                "cargo_subtype": cargo_subtype,
                "containers": containers
            },

            # -------------------------------------------
            # RECOMMENDED ROUTE
            # -------------------------------------------

            "route": {
                "route_id": recommended_route_id,
                "route_name": recommended.get(
                    "route", ""
                ),
                "transit_days": recommended.get(
                    "transit_days"
                ),
                "distance_nm": recommended.get(
                    "distance_nm"
                ),
                "transshipments": recommended.get(
                    "transshipments"
                ),
                "route_score": recommended.get("score"),
            },

            # -------------------------------------------
            # PRICING BREAKDOWN
            # -------------------------------------------

            "pricing": {
                "base_freight_usd": pricing_result[
                    "base_freight_usd"
                ],
                "fuel_surcharge_usd": pricing_result[
                    "fuel_surcharge_usd"
                ],
                "port_charge_usd": pricing_result[
                    "port_charge_usd"
                ],
                "risk_surcharge_usd": pricing_result[
                    "risk_surcharge_usd"
                ],
                "demand_factor": pricing_result[
                    "demand_factor"
                ],
                "operating_cost_usd": pricing_result[
                    "operating_cost_usd"
                ],
                "demand_adjusted_cost_usd":
                    demand_adjusted_cost,
            },

            # -------------------------------------------
            # MARGIN OPTIMIZATION
            # -------------------------------------------

            "margin": {
                "target_margin_percent": target_margin,
                "recommended_selling_price_usd":
                    margin_result[
                        "recommended_selling_price_usd"
                    ],
                "expected_profit_usd":
                    margin_result["expected_profit_usd"],
                "achieved_margin_percent":
                    margin_result[
                        "achieved_margin_percent"
                    ],
            },

            # -------------------------------------------
            # ALTERNATIVE ROUTES
            # -------------------------------------------

            "alternative_routes": alternatives,

            # -------------------------------------------
            # ROUTE ANALYSIS REASONS
            # -------------------------------------------

            "reasons": route_result.get("reasons", []),

            # -------------------------------------------
            # STATUS
            # -------------------------------------------

            "status": "success"
        }

        return quotation

    except ValueError:
        raise

    except Exception as error:
        raise ValueError(
            f"Quotation generation failed: {str(error)}"
        )
