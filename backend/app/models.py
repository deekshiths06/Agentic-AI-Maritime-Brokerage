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