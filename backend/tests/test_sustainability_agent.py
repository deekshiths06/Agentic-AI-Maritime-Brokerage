# =========================================================
# COST & SUSTAINABILITY AGENT - TESTS
# =========================================================
# Covers the four-factor weighted scorer and its endpoint:
#
#   * valid voyage scoring against the real routes.csv
#   * the documented component bands and boundary values
#   * missing / invalid input handling
#   * the weighted total and category thresholds
#   * the /api/sustainability/analyze endpoint contract
#
# The agent's weights are the four values documented in the
# project README (emission 40%, speed 25%, waiting 15%, fuel
# 20%). The numeric point bands are the ones implemented in
# cost_sustainability_agent.py and every assertion below is
# recomputed from that module rather than hardcoded from a
# convenient number.
#
# Run with:
#   cd backend
#   venv\Scripts\python.exe -m unittest discover -s tests -v
# =========================================================

import unittest

from support import BACKEND_ROOT  # noqa: F401  (sets sys.path)

from fastapi import HTTPException

from app.agents.cost_sustainability_agent import (
    CATEGORY_THRESHOLDS,
    EMISSION_BEST_KG_PER_NM,
    EMISSION_WORST_KG_PER_NM,
    FACTOR_WEIGHTS,
    SPEED_OPTIMAL_MAX_KNOTS,
    SPEED_OPTIMAL_MIN_KNOTS,
    VESSEL_TYPE_POINTS,
    FUEL_TYPE_POINTS,
    WAIT_BEST_HOURS,
    WAIT_WORST_HOURS,
    CostSustainabilityAgent,
    calculate_sustainability_score,
    derive_route_inputs,
    score_emission_intensity,
    score_fuel_tier,
    score_port_waiting,
    score_speed_efficiency,
)

from app.models import SustainabilityAnalyzeRequest

from main import analyze_sustainability_route


# A real, known-good lane from routes.csv.
KNOWN_ROUTE_ID = "R00001"


class WeightsMatchTheReadme(unittest.TestCase):

    def test_weights_are_exactly_the_documented_values(self):

        self.assertEqual(
            FACTOR_WEIGHTS,
            {
                "emission_intensity": 0.40,
                "speed_efficiency": 0.25,
                "port_waiting": 0.15,
                "fuel_tier": 0.20,
            },
        )

    def test_weights_sum_to_one(self):

        self.assertAlmostEqual(
            sum(FACTOR_WEIGHTS.values()), 1.0, places=6
        )


class EmissionIntensityBands(unittest.TestCase):

    def test_best_case_scores_full_points(self):

        self.assertEqual(
            score_emission_intensity(
                EMISSION_BEST_KG_PER_NM
            ),
            100.0,
        )

        self.assertEqual(
            score_emission_intensity(
                EMISSION_BEST_KG_PER_NM - 1
            ),
            100.0,
        )

    def test_worst_case_scores_zero(self):

        self.assertEqual(
            score_emission_intensity(
                EMISSION_WORST_KG_PER_NM
            ),
            0.0,
        )

        self.assertEqual(
            score_emission_intensity(
                EMISSION_WORST_KG_PER_NM + 5
            ),
            0.0,
        )

    def test_midpoint_is_linear(self):

        midpoint = (
            EMISSION_BEST_KG_PER_NM
            + EMISSION_WORST_KG_PER_NM
        ) / 2

        self.assertAlmostEqual(
            score_emission_intensity(midpoint),
            50.0,
            places=6,
        )

    def test_missing_input_is_none(self):

        self.assertIsNone(score_emission_intensity(None))
        self.assertIsNone(score_emission_intensity("abc"))


class SpeedEfficiencyBands(unittest.TestCase):

    def test_inside_band_scores_full_points(self):

        self.assertEqual(
            score_speed_efficiency(SPEED_OPTIMAL_MIN_KNOTS),
            100.0,
        )

        self.assertEqual(
            score_speed_efficiency(SPEED_OPTIMAL_MAX_KNOTS),
            100.0,
        )

    def test_slower_than_band_deducts(self):

        # 1 knot below the band, 5 points per knot.
        self.assertAlmostEqual(
            score_speed_efficiency(
                SPEED_OPTIMAL_MIN_KNOTS - 1
            ),
            95.0,
            places=6,
        )

    def test_faster_than_band_deducts(self):

        # 2 knots above the band, 4 points per knot.
        self.assertAlmostEqual(
            score_speed_efficiency(
                SPEED_OPTIMAL_MAX_KNOTS + 2
            ),
            92.0,
            places=6,
        )

    def test_penalty_never_goes_below_zero(self):

        self.assertEqual(
            score_speed_efficiency(200.0), 0.0
        )

    def test_missing_input_is_none(self):

        self.assertIsNone(score_speed_efficiency(None))


class PortWaitingBands(unittest.TestCase):

    def test_best_case_full_points(self):

        self.assertEqual(
            score_port_waiting(WAIT_BEST_HOURS), 100.0
        )

        self.assertEqual(score_port_waiting(0), 100.0)

    def test_worst_case_zero_points(self):

        self.assertEqual(
            score_port_waiting(WAIT_WORST_HOURS), 0.0
        )

        self.assertEqual(score_port_waiting(500), 0.0)

    def test_negative_clamped_to_full_points(self):

        self.assertEqual(score_port_waiting(-9), 100.0)

    def test_missing_input_is_none(self):

        self.assertIsNone(score_port_waiting(None))


class FuelTierPoints(unittest.TestCase):

    def test_explicit_fuel_type_wins(self):

        points, source = score_fuel_tier(
            fuel_type="LNG", vessel_type="Heavy fuel"
        )

        self.assertEqual(points, FUEL_TYPE_POINTS["lng"])
        self.assertEqual(source, "fuel_type")

    def test_vessel_type_used_when_no_fuel_type(self):

        points, source = score_fuel_tier(
            vessel_type="Eco Container Ship"
        )

        self.assertEqual(
            points, VESSEL_TYPE_POINTS["eco container ship"]
        )
        self.assertEqual(source, "vessel_type")

    def test_unknown_values_are_unavailable(self):

        points, source = score_fuel_tier(
            fuel_type="nuclear", vessel_type="spacecraft"
        )

        self.assertIsNone(points)
        self.assertIsNone(source)


class CategoryThresholds(unittest.TestCase):

    def test_boundaries_map_to_expected_letters(self):

        cases = (
            (100.0, "A"),
            (85.0, "A"),
            (84.9, "B"),
            (70.0, "B"),
            (69.9, "C"),
            (55.0, "C"),
            (54.9, "D"),
            (40.0, "D"),
            (39.9, "E"),
            (0.0, "E"),
        )

        for score, expected in cases:

            category, _ = CostSustainabilityAgent.classify(
                score
            )

            self.assertEqual(
                category,
                expected,
                f"score {score} should be {expected}",
            )

    def test_thresholds_are_descending(self):

        thresholds = [
            entry[0] for entry in CATEGORY_THRESHOLDS
        ]

        self.assertEqual(
            thresholds, sorted(thresholds, reverse=True)
        )


class WeightedScoring(unittest.TestCase):

    def test_documented_formula_recomputed(self):

        result = calculate_sustainability_score(
            emission_intensity=12.0,
            average_speed_knots=16.0,
            port_wait_hours=10.0,
            fuel_type="VLSFO",
        )

        self.assertEqual(result["status"], "success")

        expected = (
            score_emission_intensity(12.0) * 0.40
            + score_speed_efficiency(16.0) * 0.25
            + score_port_waiting(10.0) * 0.15
            + score_fuel_tier(fuel_type="VLSFO")[0] * 0.20
        )

        self.assertAlmostEqual(
            result["sustainability_score"],
            round(expected, 1),
            places=1,
        )

    def test_all_perfect_inputs_score_100(self):

        result = calculate_sustainability_score(
            emission_intensity=EMISSION_BEST_KG_PER_NM,
            average_speed_knots=SPEED_OPTIMAL_MIN_KNOTS,
            port_wait_hours=WAIT_BEST_HOURS,
            fuel_type="LNG",
        )

        self.assertEqual(
            result["sustainability_score"], 100.0
        )

        self.assertEqual(result["category"], "A")
        self.assertEqual(result["rating_label"], "Excellent")

    def test_renormalises_when_a_factor_is_missing(self):

        # Only emission intensity is supplied, so the overall
        # score must equal that single factor's points.
        result = calculate_sustainability_score(
            emission_intensity=11.0
        )

        self.assertEqual(result["status"], "success")

        self.assertAlmostEqual(
            result["sustainability_score"],
            round(score_emission_intensity(11.0), 1),
            places=1,
        )

        self.assertEqual(
            len(result["missing_inputs"]), 3
        )

    def test_no_inputs_is_insufficient_data(self):

        result = calculate_sustainability_score()

        self.assertEqual(
            result["status"], "insufficient_data"
        )

        self.assertIsNone(result["sustainability_score"])
        self.assertIsNone(result["category"])

    def test_invalid_numbers_do_not_score(self):

        result = calculate_sustainability_score(
            emission_intensity="not-a-number"
        )

        self.assertEqual(
            result["status"], "insufficient_data"
        )


class RouteDerivedInputs(unittest.TestCase):

    def test_known_route_derives_the_four_inputs(self):

        inputs = derive_route_inputs(KNOWN_ROUTE_ID)

        self.assertEqual(inputs["route_id"], KNOWN_ROUTE_ID)

        # Each derived value must match the dataset columns it
        # came from, so the card never shows a fabricated number.
        import pandas as pd
        import os

        csv_path = os.path.join(
            BACKEND_ROOT, "app", "routes.csv"
        )

        df = pd.read_csv(csv_path)

        row = df[df["route_id"] == KNOWN_ROUTE_ID].iloc[0]

        self.assertAlmostEqual(
            inputs["emission_intensity"],
            float(row["estimated_co2_kg"])
            / float(row["distance_nm"]),
            places=6,
        )

        self.assertAlmostEqual(
            inputs["average_speed_knots"],
            float(row["distance_nm"])
            / (float(row["transit_days"]) * 24.0),
            places=6,
        )

        self.assertEqual(
            inputs["vessel_type"],
            str(row["vessel_type"]).strip(),
        )

    def test_unknown_route_returns_empty(self):

        self.assertEqual(
            derive_route_inputs("R-NOPE"), {}
        )

    def test_blank_route_returns_empty(self):

        self.assertEqual(derive_route_inputs(""), {})


class SustainabilityEndpoint(unittest.TestCase):

    def test_route_id_path_scores_the_voyage(self):

        response = analyze_sustainability_route(
            SustainabilityAnalyzeRequest(
                route_id=KNOWN_ROUTE_ID
            )
        )

        self.assertTrue(response["success"])

        payload = response["sustainability"]

        self.assertEqual(payload["status"], "success")

        self.assertGreaterEqual(
            payload["sustainability_score"], 0
        )

        self.assertLessEqual(
            payload["sustainability_score"], 100
        )

        self.assertIn(
            payload["category"], ["A", "B", "C", "D", "E"]
        )

        # All four documented factors are present.
        self.assertEqual(
            set(payload["components"].keys()),
            set(FACTOR_WEIGHTS.keys()),
        )

    def test_explicit_inputs_path(self):

        response = analyze_sustainability_route(
            SustainabilityAnalyzeRequest(
                emission_intensity=9.5,
                average_speed_knots=15.0,
                port_wait_hours=4.0,
                fuel_type="LNG",
            )
        )

        payload = response["sustainability"]

        self.assertEqual(payload["sustainability_score"], 94.0)
        self.assertEqual(payload["category"], "A")

    def test_corridor_path_resolves_a_route(self):

        response = analyze_sustainability_route(
            SustainabilityAnalyzeRequest(
                origin="Mumbai",
                destination="Kochi",
                cargo_type="Perishable",
                cargo_subtype="Fresh Fruits",
            )
        )

        payload = response["sustainability"]

        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["route_id"])

    def test_empty_request_is_rejected(self):

        with self.assertRaises(HTTPException) as caught:

            analyze_sustainability_route(
                SustainabilityAnalyzeRequest()
            )

        self.assertEqual(caught.exception.status_code, 400)

    def test_unknown_route_reports_missing_inputs_not_error(self):

        response = analyze_sustainability_route(
            SustainabilityAnalyzeRequest(
                route_id="R-DOES-NOT-EXIST"
            )
        )

        payload = response["sustainability"]

        self.assertEqual(
            payload["status"], "insufficient_data"
        )

        self.assertEqual(
            len(payload["missing_inputs"]), 4
        )

    def test_response_never_exposes_restricted_commercial_data(self):

        response = analyze_sustainability_route(
            SustainabilityAnalyzeRequest(
                route_id=KNOWN_ROUTE_ID
            )
        )

        text = str(response).lower()

        for forbidden in (
            "margin",
            "profit",
            "selling_price",
            "selling price",
            "target_margin",
        ):

            self.assertNotIn(
                forbidden,
                text,
                f"restricted field '{forbidden}' leaked",
            )


if __name__ == "__main__":

    unittest.main()
