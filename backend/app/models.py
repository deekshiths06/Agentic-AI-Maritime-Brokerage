from typing import Optional

from pydantic import BaseModel, Field


# =========================================================
# ROUTE REQUEST
# =========================================================

class RouteRequest(BaseModel):

    origin: str = Field(
        ...,
        min_length=1
    )

    destination: str = Field(
        ...,
        min_length=1
    )

    cargo_type: str = Field(
        ...,
        min_length=1
    )

    # -----------------------------------------------------
    # CARGO SUBTYPE
    # Optional since the Maritime Route Map analyses a route
    # by cargo type alone, without a subtype. When empty,
    # the Route Agent evaluates every route that carries the
    # selected cargo type between the two ports. Route
    # Intelligence and Quotation flows still send a subtype.
    # -----------------------------------------------------

    cargo_subtype: str = ""

    containers: int = Field(
        ...,
        ge=1
    )

    # -----------------------------------------------------
    # LEGACY CLIENT IDENTITY FIELDS
    # `user_id` / `user_contact` are still accepted so the
    # existing frontend request shape does not change, but
    # the backend NEVER uses them for authentication or
    # ownership. Record ownership is taken only from the
    # verified bearer token. A value sent here cannot grant
    # access to another user's history or shipments.
    # -----------------------------------------------------

    user_id: str = ""

    user_contact: str = ""


# =========================================================
# WEATHER ANALYSIS REQUEST
# =========================================================
# Used by the Weather Agent. The route is identified by the
# route_id produced by the Route Agent (preferred) or by an
# origin/destination pair. `route_ids` analyses several routes
# at once and is used to show the weather of the recommended
# route together with its alternative routes.
# =========================================================

class WeatherAnalyzeRequest(BaseModel):

    route_id: str = ""

    origin: str = ""

    destination: str = ""

    route_ids: list[str] = []

    def requested_route_ids(self):

        """All route ids to analyze, primary route first."""

        route_ids = []

        primary = self.route_id.strip()

        if primary:
            route_ids.append(primary)

        for route_id in self.route_ids or []:

            cleaned = str(route_id or "").strip()

            if cleaned and cleaned not in route_ids:
                route_ids.append(cleaned)

        return route_ids

    def has_route(self):

        """True when the request identifies a route."""

        if self.requested_route_ids():
            return True

        return bool(
            self.origin.strip()
            and self.destination.strip()
        )


# =========================================================
# CUSTOMS CHECK REQUEST
# =========================================================
# Used by the Customs Agent. The shipment is identified the
# same way the Route Agent result is: origin, destination,
# cargo type and cargo subtype, plus the recommended
# route_id when the Route Agent already produced one.
#
# `documents` is the shipper's confirmed document set,
# keyed by customs control key. It is optional so a direct
# API call works without it, and it never carries customs
# RULES: a user can only declare which documents they hold,
# never what is required.
# =========================================================

class CustomsCheckRequest(BaseModel):

    route_id: str = ""

    origin: str = ""

    destination: str = ""

    cargo_type: str = ""

    cargo_subtype: str = ""

    # -----------------------------------------------------
    # DOCUMENT DECLARATION
    # Keys used by the Customs Agent:
    #   hs_code
    #   commercial_invoice
    #   packing_list
    #   certificate_of_origin
    #   restricted_cargo_permit
    # Values are booleans. A missing key is treated as "on
    # hand", so the checklist never blanks out by accident.
    # -----------------------------------------------------

    documents: dict = Field(default_factory=dict)

    def has_shipment(self):

        """True when the shipment can be matched."""

        return bool(
            self.origin.strip()
            and self.destination.strip()
            and self.cargo_type.strip()
            and self.cargo_subtype.strip()
        )


# =========================================================
# SUSTAINABILITY ANALYSIS REQUEST
# =========================================================
# Used by the Cost & Sustainability Agent. A voyage can be
# identified by a route_id (preferred, straight from the
# Route Agent) or by an origin/destination pair. The four
# operational inputs are OPTIONAL overrides: when they are
# omitted the agent derives what it can from routes.csv and
# reports anything it still cannot score.
#
# Explicit inputs:
#   emission_intensity   kg CO2 per nautical mile
#   average_speed_knots  average sailing speed
#   port_wait_hours      total port waiting / idle hours
#   fuel_type            e.g. LNG, VLSFO, MGO, HFO
#   vessel_type          overrides the routes.csv vessel type
#
# Values are validated by the agent; a missing or unsupported
# value never invents a score.

class SustainabilityAnalyzeRequest(BaseModel):

    route_id: str = ""

    origin: str = ""

    destination: str = ""

    cargo_type: str = ""

    cargo_subtype: str = ""

    containers: int = Field(default=1, ge=1)

    emission_intensity: Optional[float] = None

    average_speed_knots: Optional[float] = None

    port_wait_hours: Optional[float] = None

    fuel_type: str = ""

    vessel_type: str = ""

    def clean_route_id(self):

        return self.route_id.strip()

    def has_route(self):

        """True when the request identifies a voyage to score."""

        if self.clean_route_id():
            return True

        return bool(
            self.origin.strip()
            and self.destination.strip()
        )

    def has_explicit_input(self):

        """True when at least one factor value was supplied."""

        return any(
            value is not None
            for value in (
                self.emission_intensity,
                self.average_speed_knots,
                self.port_wait_hours,
            )
        ) or bool(
            self.fuel_type.strip()
            or self.vessel_type.strip()
        )

    def is_scorable(self):

        """True when a score can be attempted at all."""

        return self.has_route() or self.has_explicit_input()


# =========================================================
# MARITIME ASSISTANT REQUEST
# =========================================================
# Used by the Maritime AI Assistant (user) and the Admin AI
# Assistant (admin).
#
# `shipment_id` and `route_id` are OPTIONAL references. They
# only tell the assistant which of the caller's OWN existing
# records the question is about. They are never used to reach
# a record the caller does not own: the backend scopes every
# lookup to the authenticated principal first.
#
# The request carries no data values at all, so the assistant
# can never be asked to accept a number, status or document
# from the client.
# =========================================================

class AssistantRequest(BaseModel):

    message: str = Field(
        ...,
        min_length=1,
        max_length=1000
    )

    shipment_id: str = ""

    route_id: str = ""

    def clean_message(self):

        """Trimmed question text."""

        return self.message.strip()

    def clean_shipment_id(self):

        """Trimmed shipment reference."""

        return self.shipment_id.strip()

    def clean_route_id(self):

        """Trimmed route reference."""

        return self.route_id.strip()