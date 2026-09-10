# =========================================================
# MARGIN AGENT
# =========================================================
# Responsibility:
# "What selling price provides the required margin?"
#
# The Margin Agent does NOT decide the route.
# It does NOT calculate operating costs.
# It receives the demand-adjusted cost from the Pricing Agent
# and the target margin, then determines the selling price.
#
# IMPORTANT: This agent uses MARGIN, NOT MARKUP.
#
# Margin definition:
#   margin_percent = profit / selling_price * 100
#   profit = selling_price - cost
#
# Derivation of selling_price from target margin:
#
#   margin = (selling_price - cost) / selling_price * 100
#   margin * selling_price = (selling_price - cost) * 100
#   margin * selling_price = selling_price * 100 - cost * 100
#   margin * selling_price - selling_price * 100 = -cost * 100
#   selling_price * (margin - 100) = -cost * 100
#   selling_price * (100 - margin) = cost * 100
#   selling_price = (cost * 100) / (100 - margin)
#
# This is mathematically derived from the margin formula.
# No arbitrary markup or additional formulas are used.
# =========================================================


def calculate_margin(
    cost: float,
    target_margin_percent: float
):
    """
    Calculate the recommended selling price based on
    the target profit margin.

    Parameters
    ----------
    cost : float
        The demand-adjusted cost from the Pricing Agent.
    target_margin_percent : float
        The desired margin as a percentage (e.g., 15.0
        means 15%).

    Returns
    -------
    dict
        Structured margin result with selling price
        and expected profit.
    """

    try:

        # -----------------------------------------------
        # VALIDATE INPUTS
        # -----------------------------------------------

        if cost is None or cost < 0:
            raise ValueError(
                "cost must be a non-negative number."
            )

        if target_margin_percent is None:
            raise ValueError(
                "target_margin_percent is required."
            )

        cost = float(cost)
        target_margin_percent = float(
            target_margin_percent
        )

        if target_margin_percent <= 0:
            raise ValueError(
                "target_margin_percent must be greater "
                "than zero."
            )

        if target_margin_percent >= 100:
            raise ValueError(
                "target_margin_percent must be less "
                "than 100."
            )

        # -----------------------------------------------
        # DERIVED FORMULA
        #
        # From: margin = profit / selling_price * 100
        #       profit = selling_price - cost
        #
        # We derive:
        #   selling_price = (cost * 100) / (100 - margin)
        #
        # Where margin is the target margin percentage.
        # -----------------------------------------------

        selling_price = (
            (cost * 100)
            /
            (100 - target_margin_percent)
        )

        # -----------------------------------------------
        # EXPECTED PROFIT
        # profit = selling_price - cost
        # -----------------------------------------------

        expected_profit = selling_price - cost

        # -----------------------------------------------
        # ACHIEVED MARGIN
        # margin = profit / selling_price * 100
        # -----------------------------------------------

        achieved_margin = (
            (expected_profit / selling_price) * 100
        )

        # -----------------------------------------------
        # RETURN STRUCTURED RESULT
        # -----------------------------------------------

        return {
            "status": "success",
            "cost_usd": round(cost, 2),
            "target_margin_percent": round(
                target_margin_percent, 2
            ),
            "recommended_selling_price_usd": round(
                selling_price, 2
            ),
            "expected_profit_usd": round(
                expected_profit, 2
            ),
            "achieved_margin_percent": round(
                achieved_margin, 2
            )
        }

    except ValueError:
        raise

    except Exception as error:
        raise ValueError(
            f"Margin calculation failed: {str(error)}"
        )
