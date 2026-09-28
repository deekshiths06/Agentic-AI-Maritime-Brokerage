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
    # OPTIONAL USER IDENTITY
    # Sent by the frontend when a user is logged in.
    # Used to associate route history with the user.
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