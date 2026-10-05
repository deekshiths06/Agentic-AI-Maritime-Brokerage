# =========================================================
# AGENT REGRESSION TESTS
# =========================================================
# These tests are the safety net for the assistant.
#
# The assistant now DESCRIBES the route score, the weather
# limits, the customs controls and the pricing arithmetic.
# Every description it gives must match the module that
# actually runs, so these tests assert the real behaviour
# against the real datasets.
#
# If any of these fail, an agent changed and the assistant's
# project knowledge must be re-checked before shipping.
#
# Run with:
#   cd backend
#   venv\Scripts\python.exe -m unittest discover -s tests -v
# =========================================================

import unittest

from support import BACKEND_ROOT  # noqa: F401  (sets sys.path)

from app.agents.customs_agent import (
    STATUS_SEQUENCE,
    TRACKED_CONTROLS,
    analyze_customs,
)
from app.agents.margin_agent import calculate_margin
from app.agents.pricing_agent import calculate_pricing
from app.agents.route_agent import analyze_route
from app.agents.weather_agent import (
    RISK_LEVELS,
    RISK_THRESHOLDS,
    analyze_weather,
)
from app.services import project_context


class RouteAgentRegression(unittest.TestCase):

    def setUp(self):

        self.result = analyze_route(
            origin="Mumbai",
            destination="Kochi",
            cargo_type="Perishable",
            cargo_subtype="Fresh Fruits",
            containers=2
        )

    def test_route_agent_still_returns_a_ranking(self):

        self.assertEqual(
            self.result.get("status"), "Recommended"
        )

        self.assertTrue(self.result.get("routes"))

        self.assertEqual(
            self.result["routes"][0]["rank"], 1
        )

        self.assertEqual(
            self.result["routes"][0]["recommendation"],
            "recommended"
        )

    def test_documented_score_formula_is_the_real_one(self):

        """
        The assistant states the score formula verbatim. This
        test recomputes it from the returned metrics so the
        description can never drift from the agent.
        """

        routes = self.result["routes"]

        max_transit = max(
            route["transit_days"] for route in routes
        )

        max_distance = max(
            route["distance_nm"] for route in routes
        )

        max_transshipments = max(
            route["transshipments"] for route in routes
        )

        for route in routes:

            expected = (
                (max_transit - route["transit_days"]) * 5
                + (max_distance - route["distance_nm"]) / 100
                + (
                    max_transshipments - route["transshipments"]
                ) * 10
            )

            self.assertAlmostEqual(
                route["score"], expected, places=2
            )

    def test_documented_formula_text_matches_the_real_weights(self):

        reference = project_context.route_reference()

        self.assertEqual(
            reference["score_weights"]["transit_days"], 5
        )

        self.assertEqual(
            reference["score_weights"]["transshipments"], 10
        )

        self.assertEqual(
            reference["score_weights"]["distance_nm"],
            "1/100",
        )

    def test_route_agent_still_rejects_invalid_input(self):

        for bad in (0, -3, "abc"):

            with self.assertRaises(ValueError):
                analyze_route(
                    origin="Mumbai",
                    destination="Kochi",
                    cargo_type="Perishable",
                    cargo_subtype="Fresh Fruits",
                    containers=bad
                )

        with self.assertRaises(ValueError):
            analyze_route(
                origin="",
                destination="Kochi",
                cargo_type="Perishable",
                cargo_subtype="Fresh Fruits",
                containers=1
            )


class WeatherAgentRegression(unittest.TestCase):

    def test_weather_agent_still_grades_the_route(self):

        result = analyze_weather(route_id="R00001")

        self.assertTrue(result.get("available"))

        self.assertEqual(result["route_id"], "R00001")

        self.assertIn(
            result["weather_risk"],
            RISK_LEVELS.values()
        )

    def test_stored_grade_follows_the_documented_thresholds(self):

        """
        LOW must mean every parameter was graded normal under
        the limits the assistant quotes.
        """

        result = analyze_weather(route_id="R00001")

        thresholds = RISK_THRESHOLDS

        self.assertLess(
            result["wind_speed_knots"],
            thresholds["wind_speed_knots"][
                "severe_at_or_above"
            ],
        )

        self.assertLess(
            result["wave_height_m"],
            thresholds["wave_height_m"][
                "severe_at_or_above"
            ],
        )

        self.assertLess(
            result["rainfall_mm"],
            thresholds["rainfall_mm"][
                "severe_at_or_above"
            ],
        )

        self.assertGreaterEqual(
            result["visibility_km"],
            thresholds["visibility_km"][
                "normal_at_or_above"
            ],
        )

        self.assertEqual(result["weather_risk"], "LOW")

    def test_weather_reference_reports_the_real_thresholds(self):

        reference = project_context.weather_reference()

        self.assertEqual(
            reference["thresholds"], RISK_THRESHOLDS
        )

        self.assertEqual(
            reference["risk_levels"]["0"], RISK_LEVELS[0]
        )

        self.assertIn(
            "not a live weather feed",
            str(reference["data_note"]).lower()
        )


class CustomsAgentRegression(unittest.TestCase):

    def test_customs_agent_still_matches_the_four_keys(self):

        result = analyze_customs(
            origin="Mumbai",
            destination="Kochi",
            cargo_type="Perishable",
            cargo_subtype="Fresh Fruits",
            route_id="R00001"
        )

        self.assertTrue(result.get("available"))

        self.assertEqual(
            result["customs_status"], "Valid"
        )

        self.assertEqual(
            result["compliance_percent"], 100
        )

    def test_customs_reference_reports_the_real_controls(self):

        reference = project_context.customs_reference()

        self.assertEqual(
            [control["key"] for control in reference[
                "tracked_controls"
            ]],
            [control["key"] for control in TRACKED_CONTROLS],
        )

        self.assertEqual(
            reference["status_sequence"],
            list(STATUS_SEQUENCE),
        )

        self.assertEqual(
            reference["match_keys"],
            [
                "origin",
                "destination",
                "cargo_type",
                "cargo_subtype",
            ],
        )


class PricingRegression(unittest.TestCase):

    def test_pricing_still_follows_the_documented_formula(self):

        """
        The assistant quotes the operating cost formula. The
        components returned by the agent are already
        multiplied by the container count, so the shipment cost
        is their sum, and the per-container figure times the
        container count must agree.
        """

        pricing = calculate_pricing(
            route_id="R00001",
            containers=2,
            base_freight=2000.0
        )

        components = (
            pricing["base_freight_usd"]
            + pricing["fuel_surcharge_usd"]
            + pricing["port_charge_usd"]
            + pricing["risk_surcharge_usd"]
        )

        self.assertAlmostEqual(
            pricing["operating_cost_usd"],
            components,
            places=2
        )

        self.assertAlmostEqual(
            pricing["operating_cost_usd"],
            pricing["operating_cost_per_container_usd"] * 2,
            places=2
        )

        self.assertAlmostEqual(
            pricing["demand_adjusted_cost_usd"],
            pricing["operating_cost_usd"]
            * pricing["demand_factor"],
            places=2,
        )

    def test_pricing_scales_linearly_with_containers(self):

        one = calculate_pricing(
            route_id="R00001",
            containers=1,
            base_freight=2000.0
        )

        two = calculate_pricing(
            route_id="R00001",
            containers=2,
            base_freight=2000.0
        )

        self.assertAlmostEqual(
            two["operating_cost_usd"],
            one["operating_cost_usd"] * 2,
            places=2
        )

    def test_margin_still_treats_the_target_as_a_margin(self):

        margin = calculate_margin(
            cost=5172.0,
            target_margin_percent=15.0
        )

        expected = (5172.0 * 100) / (100 - 15.0)

        self.assertAlmostEqual(
            margin["recommended_selling_price_usd"],
            expected,
            places=2
        )

        self.assertAlmostEqual(
            margin["achieved_margin_percent"],
            15.0,
            places=2
        )

    def test_pricing_reference_matches_the_real_formulas(self):

        reference = project_context.pricing_reference()

        self.assertIn(
            "* containers",
            reference["operating_cost_formula"]
        )

        self.assertIn(
            "demand_factor",
            reference["demand_adjusted_cost_formula"]
        )

        self.assertIn(
            "100 - target_margin_percent",
            reference["selling_price_formula"]
        )


if __name__ == "__main__":

    unittest.main()