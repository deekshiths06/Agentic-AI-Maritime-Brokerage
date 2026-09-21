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