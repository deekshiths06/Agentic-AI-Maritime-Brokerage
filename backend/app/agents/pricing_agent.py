import pandas as pd
import os


# =========================================================
# PRICING AGENT
# =========================================================
# Responsibility:
# "What does the selected shipment/route cost?"
#
# The Pricing Agent does NOT decide the route.
# It receives the route_id from the Route Agent and
# calculates cost based on pricing.csv data.
#
# Formulas (per milestone specification):
#
# operating_cost =
#     base_freight
#     + fuel_surcharge
#     + port_charge
#     + risk_surcharge
#
# demand_adjusted_cost =
#     operating_cost * demand_factor
#
# The target_margin_percent is read but NOT applied here.
# Margin calculation belongs to the Margin Agent.
# =========================================================


PRICING_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "pricing.csv"
)


def load_pricing_data():
    """Load and clean the pricing dataset."""

    df = pd.read_csv(PRICING_CSV_PATH)

    df.columns = df.columns.str.strip().str.lower()

    required_columns = [
        "pricing_id",
        "route_id",
        "fuel_surcharge_usd",
        "port_charge_usd",
        "demand_factor",
        "risk_surcharge_usd",
        "target_margin_percent"
    ]

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            "pricing.csv is missing required columns: "
            + ", ".join(missing)
        )

    text_columns = ["pricing_id", "route_id"]
    for col in text_columns:
        df[col] = (
            df[col]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    numeric_columns = [
        "fuel_surcharge_usd",
        "port_charge_usd",
        "demand_factor",
        "risk_surcharge_usd",
        "target_margin_percent"
    ]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required_columns)

    return df


def calculate_pricing(route_id: str, base_freight: float):
    """
    Calculate pricing for a given route.

    Parameters
    ----------
    route_id : str
        The route identifier from the Route Agent.
    base_freight : float
        The base freight cost from the Route Agent.

    Returns
    -------
    dict
        Structured pricing result with cost breakdown.
    """

    try:

        if not route_id:
            raise ValueError(
                "route_id is required for pricing calculation."
            )

        if base_freight is None or base_freight < 0:
            raise ValueError(
                "base_freight must be a non-negative number."
            )

        base_freight = float(base_freight)

        # -----------------------------------------------
        # LOAD PRICING DATA
        # -----------------------------------------------

        df = load_pricing_data()

        # -----------------------------------------------
        # FIND MATCHING PRICING RECORD
        # -----------------------------------------------

        route_id_clean = str(route_id).strip()

        match = df[df["route_id"] == route_id_clean]

        if match.empty:
            raise ValueError(
                f"No pricing record found for route "
                f"'{route_id_clean}'. Pricing data is "
                f"not available for this route."
            )

        record = match.iloc[0]

        # -----------------------------------------------
        # READ PRICING COMPONENTS
        # -----------------------------------------------

        fuel_surcharge = float(record["fuel_surcharge_usd"])
        port_charge = float(record["port_charge_usd"])
        risk_surcharge = float(record["risk_surcharge_usd"])
        demand_factor = float(record["demand_factor"])
        target_margin = float(record["target_margin_percent"])

        # -----------------------------------------------
        # VALIDATE VALUES
        # -----------------------------------------------

        if demand_factor <= 0:
            raise ValueError(
                f"Invalid demand_factor ({demand_factor}) "
                f"for route '{route_id_clean}'."
            )

        if target_margin < 0 or target_margin >= 100:
            raise ValueError(
                f"Invalid target_margin_percent "
                f"({target_margin}) for route "
                f"'{route_id_clean}'."
            )

        # -----------------------------------------------
        # OPERATING COST FORMULA
        # operating_cost =
        #     base_freight
        #     + fuel_surcharge
        #     + port_charge
        #     + risk_surcharge
        # -----------------------------------------------

        operating_cost = (
            base_freight
            + fuel_surcharge
            + port_charge
            + risk_surcharge
        )

        # -----------------------------------------------
        # DEMAND ADJUSTED COST FORMULA
        # demand_adjusted_cost =
        #     operating_cost * demand_factor
        # -----------------------------------------------

        demand_adjusted_cost = operating_cost * demand_factor

        # -----------------------------------------------
        # RETURN STRUCTURED RESULT
        # -----------------------------------------------

        return {
            "status": "success",
            "route_id": route_id_clean,
            "pricing_id": str(record["pricing_id"]),
            "base_freight_usd": round(base_freight, 2),
            "fuel_surcharge_usd": round(fuel_surcharge, 2),
            "port_charge_usd": round(port_charge, 2),
            "risk_surcharge_usd": round(risk_surcharge, 2),
            "demand_factor": round(demand_factor, 2),
            "target_margin_percent": round(target_margin, 2),
            "operating_cost_usd": round(operating_cost, 2),
            "demand_adjusted_cost_usd": round(
                demand_adjusted_cost, 2
            )
        }

    except ValueError:
        raise

    except FileNotFoundError:
        raise ValueError(
            "pricing.csv was not found. "
            "Please make sure it is inside "
            "backend/app/data/."
        )

    except Exception as error:
        raise ValueError(
            f"Pricing calculation failed: {str(error)}"
        )
