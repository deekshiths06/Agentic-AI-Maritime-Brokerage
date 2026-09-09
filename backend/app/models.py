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

    cargo_subtype: str = Field(
        ...,
        min_length=1
    )

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