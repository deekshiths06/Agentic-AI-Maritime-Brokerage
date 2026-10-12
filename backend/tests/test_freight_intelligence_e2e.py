# =========================================================
# FREIGHT INTELLIGENCE + EXECUTIVE DASHBOARD - E2E TESTS
# =========================================================
# End-to-end tests for the two new milestone features:
#
#   1. The Freight Intelligence engine (/api/intelligence/
#      analyze) - the orchestrator that runs the existing
#      agents together for one shipment, plus its endpoint
#      handler.
#   2. The Executive Dashboard (/api/admin/executive-
#      dashboard) - the pure aggregation layer, its MongoDB
#      wiring and the admin gate that protects it.
#
# The tests follow the existing suite's convention: they call
# the real functions directly (unittest, no HTTP TestClient,
# no httpx) and assert the real behaviour against the real
# datasets. Only the MongoDB transport is stubbed, because the
# execution dashboard endpoint reads collection counts; the
# arithmetic it tests is the pure aggregation layer that runs
# in production.
#
# Run with:
#   cd backend
#   venv\Scripts\python.exe -m unittest discover -s tests -v
# =========================================================

import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from support import (  # noqa: F401  (sets sys.path)
    BACKEND_ROOT,
    no_secrets,
)

from app.agents.orchestrator import generate_freight_intelligence
from app.agents.quotation_service import generate_quotation
from app.agents.route_agent import analyze_route
from app.agents.weather_agent import analyze_weather
from app.agents.customs_agent import analyze_customs
from app.services.executive_dashboard import build_executive_report

from main import (
    app,
    analyze_freight_intelligence,
    FeedbackApproval,
    get_admin_executive_dashboard,
    get_public_reviews,
    get_current_user,
    require_admin,
    update_feedback_approval,
    _serialize_public_review,
    SHIPMENT_STATUS_FLOW,
)
from app.models import RouteRequest


# The exact cargo mix the existing regression suite uses.
# Its figures are the real Mumbai -> Kochi perishable lane.

LANE = ("Mumbai", "Kochi", "Perishable", "Fresh Fruits", 2)


class FreightIntelligenceE2ETests(unittest.TestCase):

    def setUp(self):

        self.report = generate_freight_intelligence(*LANE)

        self.route_agent_result = analyze_route(*LANE)

        self.dedicated_quotation = generate_quotation(*LANE)

    # ---------------------------------------------
    # REPORT CONTRACT
    # ---------------------------------------------

    def test_report_status_is_success(self):

        self.assertEqual(self.report["status"], "success")

    def test_all_five_agents_report_a_status(self):

        self.assertEqual(
            set(self.report["agents"].keys()),
            {"route", "pricing", "margin", "weather", "customs"},
        )

        for agent, status in self.report["agents"].items():

            self.assertIn(status, ("success", "not_available"))

    # ---------------------------------------------
    # ROUTE CONSISTENCY (never drifts from Route Agent)
    # ---------------------------------------------

    def test_recommended_route_matches_the_route_agent(self):

        recommended = self.report["route"]["recommended"]

        agent_first = (
            self.route_agent_result["routes"][0]
        )

        self.assertEqual(
            recommended["route_id"],
            agent_first["route_id"],
        )

        self.assertEqual(
            recommended["route_name"],
            agent_first["route"],
        )

        self.assertEqual(
            recommended["transit_days"],
            agent_first["transit_days"],
        )

    def test_alternative_routes_are_included(self):

        self.assertEqual(
            self.report["route"]["total_available_routes"],
            len(self.report["route"]["alternative_routes"]) + 1,
        )

        self.assertGreaterEqual(
            len(self.report["route"]["alternative_routes"]),
            1,
        )

    def test_reasons_flow_through_from_the_pipeline(self):

        self.assertEqual(
            self.report["route"]["reasons"],
            self.dedicated_quotation["reasons"],
        )

    # ---------------------------------------------
    # PRICE CONSISTENCY (never drifts from the quote)
    # ---------------------------------------------

    def test_quotation_total_matches_the_margin_selling_price(self):

        self.assertEqual(
            self.report["quotation_total_usd"],
            self.report["margin"]["recommended_selling_price_usd"],
        )

    def test_pricing_never_drifts_from_the_quotation_pipeline(self):

        self.assertEqual(
            self.report["pricing"],
            self.dedicated_quotation["pricing"],
        )

        self.assertEqual(
            self.report["margin"],
            self.dedicated_quotation["margin"],
        )

        # The total is exposed as quotation_total_usd only.
        self.assertNotIn("price", self.report)

        self.assertEqual(
            self.report["quotation_total_usd"],
            self.dedicated_quotation["margin"][
                "recommended_selling_price_usd"
            ],
        )

    # ---------------------------------------------
    # OPTIONAL LAYERS
    # ---------------------------------------------

    def test_weather_layer_matches_the_dedicated_weather_agent(self):

        layer = self.report["weather"]

        self.assertEqual(layer["agent"], "weather")

        self.assertEqual(layer["status"], "success")

        dedicated = analyze_weather(
            route_id=self.report["route"]["recommended"]["route_id"],
            origin=LANE[0],
            destination=LANE[1],
        )

        self.assertEqual(
            layer["result"]["weather_risk"],
            dedicated["weather_risk"],
        )

    def test_customs_layer_matches_the_dedicated_customs_agent(self):

        layer = self.report["customs"]

        self.assertEqual(layer["agent"], "customs")

        self.assertEqual(layer["status"], "success")

        dedicated = analyze_customs(
            origin=LANE[0],
            destination=LANE[1],
            cargo_type=LANE[2],
            cargo_subtype=LANE[3],
            route_id=self.report["route"]["recommended"]["route_id"],
        )

        self.assertEqual(
            layer["result"]["customs_status"],
            dedicated["customs_status"],
        )

    # ---------------------------------------------
    # FAILURE SEMANTICS
    # ---------------------------------------------

    def test_unknown_lane_fails_like_the_quotation_endpoint(self):

        with self.assertRaises(ValueError):

            generate_freight_intelligence(
                "Atlantis",
                "Neverland",
                "Perishable",
                "Fresh Fruits",
                2,
            )

    def test_report_exposes_no_secret(self):

        self.assertIsNone(no_secrets(repr(self.report)))


class IntelligenceEndpointE2ETests(unittest.TestCase):

    def test_handler_returns_the_full_report(self):

        request = RouteRequest(
            origin=LANE[0],
            destination=LANE[1],
            cargo_type=LANE[2],
            cargo_subtype=LANE[3],
            containers=LANE[4],
        )

        response = analyze_freight_intelligence(
            request,
            authorization=None,
        )

        self.assertEqual(response["status"], "success")

        self.assertEqual(
            response["quotation_total_usd"],
            response["margin"]["recommended_selling_price_usd"],
        )

        # Without a token the history save degrades silently:
        # the report still returns, with no analysis_id.
        self.assertIsNone(response["analysis_id"])

    def test_handler_returns_400_for_an_unknown_lane(self):

        request = RouteRequest(
            origin="Atlantis",
            destination="Neverland",
            cargo_type="Perishable",
            cargo_subtype="Fresh Fruits",
            containers=2,
        )

        with self.assertRaises(HTTPException) as raised:

            analyze_freight_intelligence(request, authorization=None)

        self.assertEqual(raised.exception.status_code, 400)


class ExecutiveDashboardE2ETests(unittest.TestCase):

    # ---------------------------------------------
    # PURE AGGREGATION LAYER (the real dashboard math)
    # ---------------------------------------------

    def setUp(self):

        now = datetime.now(timezone.utc)

        # 6 analyses: 2 approved, 2 pending approval, 2 plain.
        # 4 of the 6 carried a quotation (pricing). The most
        # recent one sits in the current week, the rest spread
        # back 3, 6, 9, 12, 15 days - so weekly buckets see
        # varying counts and the trend has zero-filled weeks to
        # prove the 8-week window is always covered.

        self.records = []

        for i in range(6):

            self.records.append({
                "origin": "Mumbai",
                "destination": "Kochi",
                "cargo_type": "Perishable",
                "approval_status": (
                    "approved" if i < 2
                    else ("pending_admin_approval" if i < 4 else "")
                ),
                "accepted_at": (now if i < 4 else None),
                "created_at": now - timedelta(days=i * 3),
                "pricing": {"base_freight_usd": 1} if i < 4 else None,
            })

        # 3 shipments: 2 In Transit, 1 Delivered.

        self.shipments = []

        for i in range(3):

            self.shipments.append({
                "status": (
                    "In Transit" if i < 2 else "Delivered"
                ),
                "created_at": now,
            })

        self.report = build_executive_report(
            total_users=10,
            total_route_analyses=6,
            total_quotations=4,
            total_shipments=3,
            shipments=self.shipments,
            history_records=self.records,
            status_flow=SHIPMENT_STATUS_FLOW,
        )

    def test_kpis_match_the_real_counts(self):

        kpis = self.report["kpis"]

        self.assertEqual(kpis["total_users"], 10)
        self.assertEqual(kpis["total_route_analyses"], 6)
        self.assertEqual(kpis["total_quotations"], 4)
        self.assertEqual(kpis["total_shipments"], 3)
        self.assertEqual(kpis["active_shipments"], 2)
        self.assertEqual(kpis["delivered_shipments"], 1)
        self.assertEqual(kpis["pending_approvals"], 2)
        self.assertEqual(kpis["approved_quotations"], 2)

    def test_funnel_matches_the_stored_records(self):

        funnel = self.report["funnel"]

        self.assertEqual(funnel["analyses"], 6)
        self.assertEqual(funnel["quotations"], 4)

        # accepted = accepted_at present OR awaiting/approved
        self.assertEqual(funnel["accepted"], 4)
        self.assertEqual(funnel["approved"], 2)
        self.assertEqual(funnel["shipments"], 3)

        rates = funnel["conversion_rates"]

        self.assertEqual(rates["analyses_to_quotations"], 66.7)
        self.assertEqual(rates["quotations_to_accepted"], 100.0)
        self.assertEqual(rates["accepted_to_approved"], 50.0)
        self.assertEqual(rates["approved_to_shipments"], 150.0)

    def test_shipment_distribution_always_covers_every_status(self):

        distribution = self.report["shipment_status"]

        self.assertEqual(
            [item["status"] for item in distribution],
            SHIPMENT_STATUS_FLOW,
        )

        counts = {
            item["status"]: item["count"]
            for item in distribution
        }

        self.assertEqual(counts["In Transit"], 2)
        self.assertEqual(counts["Delivered"], 1)
        self.assertEqual(counts["Booking Confirmed"], 0)

    def test_weekly_trend_always_covers_eight_weeks(self):

        trend = self.report["weekly_activity"]

        self.assertEqual(len(trend), 8)

        total = sum(item["count"] for item in trend)

        self.assertEqual(total, 6)

    def test_top_lanes_and_cargo_are_aggregated(self):

        self.assertEqual(
            self.report["top_lanes"],
            [{"label": "Mumbai -> Kochi", "count": 6}],
        )

        self.assertEqual(
            self.report["top_cargo"],
            [{"label": "Perishable", "count": 6}],
        )

    def test_report_snapshot_states_what_was_checked(self):

        self.assertEqual(
            self.report["snapshot"],
            {
                "recent_shipments_checked": 3,
                "recent_history_checked": 6,
            },
        )

    # ---------------------------------------------
    # ADMIN GATE
    # ---------------------------------------------

    def test_the_admin_gate_rejects_a_normal_user(self):

        with self.assertRaises(HTTPException) as raised:

            require_admin({
                "user_id": "USR-0001",
                "role": "user",
            })

        self.assertEqual(raised.exception.status_code, 403)

    def test_the_admin_gate_admits_an_administrator(self):

        principal = {
            "user_id": "USR-ADMIN",
            "role": "admin",
        }

        self.assertEqual(require_admin(principal), principal)

    def test_get_current_user_requires_a_token(self):

        with self.assertRaises(HTTPException) as raised:

            get_current_user(None)

        self.assertEqual(raised.exception.status_code, 401)

    # ---------------------------------------------
    # ENDPOINT WIRING (MongoDB transport stubbed)
    # ---------------------------------------------

    def test_endpoint_gathers_the_real_collections(self):

        now = datetime.now(timezone.utc)

        record = {
            "origin": "Mumbai",
            "destination": "Kochi",
            "cargo_type": "Perishable",
            "approval_status": "approved",
            "accepted_at": now,
            "created_at": now,
            "pricing": {"base_freight_usd": 1},
        }

        shipment = {
            "status": "In Transit",
            "created_at": now,
        }

        with mock.patch(
            "main.users_collection",
            FakeCollection([{"role": "admin"}]),
        ), mock.patch(
            "main.route_history_collection",
            FakeCollection([record, dict(record, approval_status="")]),
        ), mock.patch(
            "main.shipments_collection",
            FakeCollection([shipment]),
        ):

            report = get_admin_executive_dashboard(
                current_user={
                    "user_id": "USR-ADMIN",
                    "role": "admin",
                }
            )

        self.assertTrue(report["success"])

        self.assertEqual(report["kpis"]["total_users"], 1)
        self.assertEqual(report["kpis"]["total_route_analyses"], 2)
        self.assertEqual(report["kpis"]["total_quotations"], 2)
        self.assertEqual(report["kpis"]["total_shipments"], 1)
        self.assertEqual(report["kpis"]["approved_quotations"], 1)

        self.assertEqual(report["funnel"]["analyses"], 2)
        self.assertEqual(report["funnel"]["accepted"], 2)

        self.assertEqual(
            report["shipment_status"][4]["status"],
            "In Transit",
        )
        self.assertEqual(report["shipment_status"][4]["count"], 1)


# ---------------------------------------------------------
# ADMIN ROUTE PROTECTION
# Every /api/admin route must sit behind require_admin in its
# dependency chain. This inspects the real FastAPI routing
# table, so a dropped dependency on any admin endpoint fails
# the suite - the frontend role check is never the boundary.
# ---------------------------------------------------------

class AdminRouteProtectionTests(unittest.TestCase):

    def _route_uses_require_admin(self, route):

        stack = [route.dependant]
        seen = set()

        while stack:

            dependant = stack.pop()

            if id(dependant) in seen:
                continue

            seen.add(id(dependant))

            if dependant.call is require_admin:
                return True

            stack.extend(dependant.dependencies)

        return False

    def test_every_admin_route_is_gated_by_require_admin(self):

        admin_routes = [
            route
            for route in app.routes
            if getattr(route, "path", "").startswith("/api/admin")
        ]

        self.assertTrue(
            admin_routes,
            "No /api/admin routes were found on the app.",
        )

        for route in admin_routes:

            self.assertTrue(
                self._route_uses_require_admin(route),
                f"{route.path} is not protected by require_admin.",
            )

    def test_the_admin_surface_is_not_empty_and_known(self):

        paths = {
            route.path
            for route in app.routes
            if getattr(route, "path", "").startswith("/api/admin")
        }

        for expected in (
            "/api/admin/stats",
            "/api/admin/executive-dashboard",
            "/api/admin/users",
            "/api/admin/feedback",
            "/api/admin/quotations",
            "/api/admin/shipments",
        ):

            self.assertIn(expected, paths)


# ---------------------------------------------------------
# FAKE MONGO TRANSPORT
# The endpoint only needs count_documents and a cursor that
# supports .sort(...).limit(...) and iteration, so a tiny
# in-memory stub is enough - no database is required.
# ---------------------------------------------------------

class FakeCursor:

    def __init__(self, documents):

        self.documents = list(documents)

    def sort(self, *args, **kwargs):

        return self

    def limit(self, *args, **kwargs):

        return self

    def __iter__(self):

        return iter(self.documents)


class FakeCollection:

    def __init__(self, documents):

        self.documents = list(documents)

    def count_documents(self, filter=None):

        return len(self.documents)

    def _matches(self, document, filter):

        if not filter:
            return True

        for key, value in filter.items():

            if document.get(key) != value:
                return False

        return True

    def find_one(self, filter=None):

        for document in self.documents:

            if self._matches(document, filter or {}):
                return document

        return None

    def find(self, filter=None, **kwargs):

        return FakeCursor(
            document
            for document in self.documents
            if self._matches(document, filter or {})
        )

    def insert_one(self, document):

        self.documents.append(document)

        return _FakeInsertResult(document)

    def update_one(self, filter, update):

        for document in self.documents:

            if self._matches(document, filter):

                set_fields = update.get("$set", {})

                for key, value in set_fields.items():
                    document[key] = value

                break

        return None


class _FakeInsertResult:

    def __init__(self, document):

        self.inserted_id = document.get("_id", "id")


class ReviewsE2ETests(unittest.TestCase):

    def setUp(self):

        from bson import ObjectId

        self.pending_feedback_id = ObjectId()

        self.approved_one = {
            "_id": ObjectId(),
            "user_id": "USR-OWNER-0001",
            "user_name": "Shipper One",
            "user_contact": "owner@example.com",
            "rating": 5,
            "feedback_type": "General",
            "message": "Reliable service.",
            "approved": True,
            "approved_at": datetime.now(timezone.utc),
            "approved_by": "USR-ADMIN",
            "created_at": datetime.now(timezone.utc),
        }

        self.approved_two = dict(
            self.approved_one,
            _id=ObjectId(),
            rating=4,
            message="Straightforward pricing.",
        )

        self.pending = dict(
            self.approved_one,
            _id=self.pending_feedback_id,
            rating=1,
            message="Rough process.",
            approved=False,
            approved_at=None,
            approved_by="",
        )

    def test_public_reviews_return_only_approved_entries(self):

        with mock.patch(
            "main.feedbacks_collection",
            FakeCollection([
                self.approved_one,
                self.approved_two,
                self.pending,
            ]),
        ):

            response = get_public_reviews()

        self.assertEqual(
            len(response["reviews"]), 2
        )

        self.assertEqual(
            response["summary"]["review_count"], 2
        )

        self.assertEqual(
            response["summary"]["average_rating"], 4.5
        )

        self.assertEqual(
            response["summary"]["rating_counts"][5], 1
        )

        self.assertEqual(
            response["summary"]["rating_counts"][1], 0
        )

    def test_a_public_review_never_leaks_contact_details(self):

        review = _serialize_public_review(self.approved_one)

        self.assertNotIn("user_contact", review)
        self.assertNotIn("user_id", review)
        self.assertNotIn("approved", review)

        self.assertEqual(review["user_name"], "Shipper One")
        self.assertEqual(review["rating"], 5)

    def test_admin_approval_publishes_a_review(self):

        with mock.patch(
            "main.feedbacks_collection",
            FakeCollection([
                self.approved_one,
                self.approved_two,
                self.pending,
            ]),
        ):

            response = update_feedback_approval(
                str(self.pending_feedback_id),
                FeedbackApproval(approved=True),
                current_user={
                    "user_id": "USR-ADMIN",
                    "role": "admin",
                },
            )

        self.assertTrue(response["success"])

        self.assertTrue(response["feedback"]["approved"])

        self.assertEqual(
            response["feedback"]["approved_by"],
            "USR-ADMIN",
        )

        self.assertIsNotNone(
            response["feedback"]["approved_at"]
        )

    def test_admin_approval_hides_a_review(self):

        with mock.patch(
            "main.feedbacks_collection",
            FakeCollection([
                self.approved_one,
                self.approved_two,
                self.pending,
            ]),
        ):

            response = update_feedback_approval(
                str(self.approved_one["_id"]),
                FeedbackApproval(approved=False),
                current_user={
                    "user_id": "USR-ADMIN",
                    "role": "admin",
                },
            )

        self.assertFalse(response["feedback"]["approved"])

        self.assertIsNone(response["feedback"]["approved_at"])

    def test_admin_approval_404_when_feedback_is_missing(self):

        with mock.patch(
            "main.feedbacks_collection",
            FakeCollection([]),
        ):

            with self.assertRaises(HTTPException) as raised:

                update_feedback_approval(
                    "000000000000000000000000",
                    FeedbackApproval(approved=True),
                    current_user={
                        "user_id": "USR-ADMIN",
                        "role": "admin",
                    },
                )

        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":

    unittest.main()