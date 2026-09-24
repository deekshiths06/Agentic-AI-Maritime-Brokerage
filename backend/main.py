from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import MongoClient
from bson import ObjectId
import bcrypt
import jwt
import pymongo
import re
import os
import logging
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from app.models import RouteRequest
from app.agents.route_agent import analyze_route
from app.agents.quotation_service import (
    generate_quotation
)
from app.services.ais_service import (
    fetch_ais_vessels,
)


logger = logging.getLogger("uvicorn.error")


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Agentic Maritime Brokerage Platform",
    description="AI-powered maritime freight quotation platform",
    version="1.0.0"
)


# ============================================================
# STARTUP - SEED ADMIN ACCOUNT + INDEXES
# ============================================================

@app.on_event("startup")
def on_startup():

    seed_admin_account()

    ensure_database_indexes()


# ============================================================
# DATABASE INDEXES
# ============================================================
# Lightweight, safe indexes used by the shipment and route
# history collections. Failures never block startup.
# ============================================================

def ensure_database_indexes():

    try:

        shipments_collection.create_index("user_id")

        shipments_collection.create_index(
            "shipment_id", unique=True
        )

        shipments_collection.create_index("user_contact")

        shipments_collection.create_index(
            "quotation_record_id"
        )

        feedbacks_collection.create_index("user_id")

        # -------------------------------------------------
        # LEGACY INDEX CLEANUP
        # Older versions created a unique, non-sparse index
        # on "feedback_id", but no document ever sets that
        # field. MongoDB then treats every missing value as
        # the same null key, so the second insert hits a
        # duplicate-key error (HTTP 500). Drop it here so
        # feedback submission works on existing databases.
        # -------------------------------------------------

        try:
            feedbacks_collection.drop_index(
                "feedback_id_1"
            )
        except Exception:
            pass

    except Exception as error:

        logger.warning(
            "Could not create database indexes: %s",
            error
        )


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_origin_regex=r"^http://.*:5173$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# MONGODB
# ============================================================
# Database configuration comes from environment variables.
# MONGO_URI      full MongoDB connection string
# MONGO_DATABASE database name
#
# Local development falls back to a default local MongoDB.
# Create a backend/.env file to override these values.
# ============================================================

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://127.0.0.1:27017/"
)

MONGO_DATABASE = os.getenv(
    "MONGO_DATABASE",
    "maritime_brokerage"
)

client = MongoClient(MONGO_URI)

db = client[MONGO_DATABASE]

users_collection = db["users"]

route_history_collection = db["route_history"]

shipments_collection = db["shipments"]

counters_collection = db["counters"]

feedbacks_collection = db["feedbacks"]


# ============================================================
# SHIPMENT STATUS WORKFLOW
# ============================================================
# Shipment tracking in this project is a platform workflow
# simulation. Statuses advance in a controlled sequence.
# No real vessel tracking is claimed.
# ============================================================

SHIPMENT_STATUS_FLOW = [
    "Booking Confirmed",
    "Cargo Ready",
    "At Origin Port",
    "Vessel Departed",
    "In Transit",
    "At Destination Port",
    "Delivered"
]


# ============================================================
# AUTHENTICATION & ADMIN CONFIGURATION
# ============================================================
# The admin account is seeded by the backend on startup and
# is never created through the public registration form.
#
# Safe defaults are provided for development. Override them
# in backend/.env for production or a real deployment.
# ============================================================

JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "maritime-ai-dev-secret-key-2024"
)

JWT_ALGORITHM = "HS256"

JWT_EXPIRY_HOURS = 24

ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    "admin@maritime.ai"
)

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    "Admin@123"
)

ADMIN_NAME = os.getenv(
    "ADMIN_NAME",
    "Administrator"
)


# ============================================================
# ROLE HELPERS
# ============================================================
# Users created before the role system existed may not have a
# role field. Missing role is always treated as "user".
# ============================================================

def get_user_role(user: dict) -> str:

    role = user.get("role", "user")

    if role not in ("admin", "user"):
        return "user"

    return role


# ============================================================
# AUTH HELPER - ISSUE TOKEN
# ============================================================

def create_access_token(user: dict) -> str:

    payload = {
        "user_id": str(user["_id"]),
        "role": get_user_role(user),
        "name": user.get("name", ""),
        "contact": user.get("contact", ""),
        "exp": (
            datetime.utcnow()
            + timedelta(hours=JWT_EXPIRY_HOURS)
        )
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )


# ============================================================
# AUTH DEPENDENCY - GET CURRENT USER
# ============================================================
# Reads the Bearer token from the Authorization header and
# returns a safe user descriptor. The role always comes from
# the backend-issued token, never from the frontend.
# ============================================================

def get_current_user(
    authorization: str = Header(None)
):

    if not authorization:

        raise HTTPException(
            status_code=401,
            detail="Authentication is required."
        )

    parts = authorization.split()

    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
    ):

        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid authentication token format."
            )
        )

    try:

        payload = jwt.decode(
            parts[1],
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

    except jwt.ExpiredSignatureError:

        raise HTTPException(
            status_code=401,
            detail="Authentication token has expired."
        )

    except jwt.InvalidTokenError:

        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token."
        )

    user_id = payload.get("user_id")

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token."
        )

    return {
        "user_id": user_id,
        "role": payload.get("role", "user"),
        "name": payload.get("name", ""),
        "contact": payload.get("contact", "")
    }


# ============================================================
# AUTH DEPENDENCY - REQUIRE ADMIN
# ============================================================
# Blocks every non-admin principal before an admin-only
# endpoint runs. A normal user cannot bypass this check by
# editing frontend localStorage.
# ============================================================

def require_admin(
    current_user: dict = Depends(get_current_user)
):

    if current_user.get("role") != "admin":

        raise HTTPException(
            status_code=403,
            detail=(
                "Administrator access is required "
                "for this action."
            )
        )

    return current_user


# ============================================================
# SEED ADMIN ACCOUNT
# ============================================================
# Called once on startup. Creates the initial admin account
# if it does not exist. Never duplicates an existing admin.
# ============================================================

def seed_admin_account():

    try:

        admin_contact = (
            ADMIN_EMAIL.strip().lower()
        )

        existing = users_collection.find_one({
            "contact": admin_contact
        })

        if existing:

            # -----------------------------
            # Ensure the existing account
            # holds the admin role in DB.
            # -----------------------------

            if existing.get("role") != "admin":

                users_collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"role": "admin"}}
                )

            return

        hashed_password = bcrypt.hashpw(
            ADMIN_PASSWORD.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        users_collection.insert_one({
            "name": ADMIN_NAME,
            "contact": admin_contact,
            "password": hashed_password,
            "role": "admin",
            "created_at": datetime.utcnow(),
            "verified": True,
            "mfa_enabled": False
        })

        logger.info(
            "Admin account seeded successfully."
        )

    except Exception as error:

        logger.warning(
            "Could not seed admin account: %s",
            error
        )


# ============================================================
# REQUEST MODELS
# ============================================================

class RegisterRequest(BaseModel):
    name: str
    contact: str
    password: str


class LoginRequest(BaseModel):
    contact: str
    password: str


class ShipmentStatusUpdate(BaseModel):
    status: str


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback_type: str
    message: str


class QuotationRejectRequest(BaseModel):
    reason: str


# ============================================================
# HELPER - NORMALIZE CONTACT
# ============================================================

def normalize_contact(contact: str) -> str:

    contact = contact.strip()

    # If email, convert to lowercase
    if "@" in contact:
        contact = contact.lower()

    return contact


# ============================================================
# HELPER - VALIDATE CONTACT
# ============================================================

def validate_contact(contact: str) -> str:

    contact = normalize_contact(contact)

    # Email validation
    is_email = re.match(
       r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        contact
    )

    # Mobile validation
    is_mobile = re.match(
        r"^[0-9]{10}$",
        contact
    )

    if not is_email and not is_mobile:

        raise HTTPException(
            status_code=400,
            detail="Enter a valid email or 10-digit mobile number."
        )

    return contact


# ============================================================
# HELPER - VALIDATE PASSWORD
# ============================================================

def validate_password(password: str):

    if not password:

        raise HTTPException(
            status_code=400,
            detail="Password is required."
        )

    if len(password) < 6:

        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 6 characters."
        )

    if len(password) > 72:

        raise HTTPException(
            status_code=400,
            detail="Password must not exceed 72 characters."
        )


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():

    return {
        "message": "Agentic Maritime Brokerage API is running",
        "project": "Maritime Freight Quotation Platform",
        "milestone": "Milestone 2 - Pricing Intelligence "
                     "& Margin Optimization"
    }


# ============================================================
# REGISTER
# ============================================================

@app.post("/api/auth/register")
def register_user(request: RegisterRequest):

    # --------------------------------------------------------
    # CLEAN INPUT
    # --------------------------------------------------------

    name = request.name.strip()
    contact = validate_contact(request.contact)
    password = request.password


    # --------------------------------------------------------
    # NAME VALIDATION
    # --------------------------------------------------------

    if len(name) < 3:

        raise HTTPException(
            status_code=400,
            detail="Please enter a valid full name."
        )


    # --------------------------------------------------------
    # PASSWORD VALIDATION
    # --------------------------------------------------------

    validate_password(password)


    # --------------------------------------------------------
    # CHECK EXISTING USER
    # --------------------------------------------------------

    existing_user = users_collection.find_one({
        "contact": contact
    })

    if existing_user:

        raise HTTPException(
            status_code=400,
            detail=(
                "An account with this email or mobile number "
                "already exists. Please login."
            )
        )


    # --------------------------------------------------------
    # HASH PASSWORD
    # --------------------------------------------------------

    hashed_password = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


    # --------------------------------------------------------
    # CREATE USER
    # --------------------------------------------------------
    # Public registration ALWAYS creates a "user" account.
    # The backend decides the role; the frontend never sends
    # a role value. Admin accounts are seeded separately.
    # --------------------------------------------------------

    user = {
        "name": name,
        "contact": contact,
        "password": hashed_password,
        "role": "user",
        "created_at": datetime.utcnow(),
        "verified": True,
        "mfa_enabled": False
    }


    # --------------------------------------------------------
    # SAVE USER
    # --------------------------------------------------------

    result = users_collection.insert_one(user)


    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {
        "success": True,
        "message": "Account created successfully.",
        "user": {
            "id": str(result.inserted_id),
            "name": name,
            "contact": contact,
            "role": "user"
        }
    }


# ============================================================
# LOGIN
# ============================================================

@app.post("/api/auth/login")
def login_user(request: LoginRequest):

    # --------------------------------------------------------
    # CLEAN INPUT
    # --------------------------------------------------------

    contact = validate_contact(request.contact)
    password = request.password


    # --------------------------------------------------------
    # PASSWORD VALIDATION
    # --------------------------------------------------------

    validate_password(password)


    # --------------------------------------------------------
    # FIND USER
    # --------------------------------------------------------

    try:

        user = users_collection.find_one({
            "contact": contact
        })

    except Exception:

        raise HTTPException(
            status_code=503,
            detail="Login service is temporarily unavailable. Please try again later."
        )


    # --------------------------------------------------------
    # INVALID USER
    # --------------------------------------------------------

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid email/mobile number or password."
        )


    # --------------------------------------------------------
    # GET STORED PASSWORD
    # --------------------------------------------------------

    stored_password = user.get("password")


    if not stored_password:

        raise HTTPException(
            status_code=500,
            detail="User account does not contain a valid password."
        )


    # --------------------------------------------------------
    # VERIFY PASSWORD
    # --------------------------------------------------------

    try:

        password_correct = bcrypt.checkpw(
            password.encode("utf-8"),
            stored_password.encode("utf-8")
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail="Unable to verify password."
        )


    # --------------------------------------------------------
    # WRONG PASSWORD
    # --------------------------------------------------------

    if not password_correct:

        raise HTTPException(
            status_code=401,
            detail="Invalid email/mobile number or password."
        )


    # --------------------------------------------------------
    # LOGIN SUCCESS
    # --------------------------------------------------------
    # The returned role always comes from the MongoDB user
    # record. Missing role fields safely default to "user".
    # The token is signed by the backend and used later to
    # protect admin-only endpoints.
    # --------------------------------------------------------

    role = get_user_role(user)

    token = create_access_token(user)

    return {
        "success": True,
        "message": "Login successful.",
        "user": {
            "id": str(user["_id"]),
            "name": user.get("name", ""),
            "contact": user.get("contact", ""),
            "role": role,
            "mfa_enabled": user.get("mfa_enabled", False)
        },
        "token": token
    }


# ============================================================
# ROUTE HISTORY HELPERS
# ============================================================

def _history_document(result, request, quotation=None):

    recommended = (
        result.get("recommended_route") or {}
    )

    doc = {
        "user_id": request.user_id,
        "user_contact": request.user_contact,
        "origin": result.get(
            "origin", request.origin
        ),
        "destination": result.get(
            "destination", request.destination
        ),
        "cargo_type": result.get(
            "cargo_type", request.cargo_type
        ),
        "cargo_subtype": result.get(
            "cargo_subtype", request.cargo_subtype
        ),
        "containers": result.get(
            "containers", request.containers
        ),
        "route_id": str(
            recommended.get("route_id", "")
        ).strip(),
        "route_name": recommended.get(
            "route", ""
        ),
        "transit_days": recommended.get(
            "transit_days"
        ),
        "distance_nm": recommended.get(
            "distance_nm"
        ),
        "transshipments": recommended.get(
            "transshipments"
        ),
        "route_score": recommended.get(
            "score"
        ),
        "total_available_routes": result.get(
            "total_available_routes", 0
        ),
        "created_at": datetime.now(timezone.utc)
    }

    if quotation:
        pricing = quotation.get("pricing", {})
        margin = quotation.get("margin", {})
        doc["pricing"] = {
            "base_freight_usd": pricing.get(
                "base_freight_usd"
            ),
            "operating_cost_usd": pricing.get(
                "operating_cost_usd"
            ),
            "demand_adjusted_cost_usd": pricing.get(
                "demand_adjusted_cost_usd"
            ),
            "demand_factor": pricing.get(
                "demand_factor"
            ),
        }
        doc["margin"] = {
            "target_margin_percent": margin.get(
                "target_margin_percent"
            ),
            "recommended_selling_price_usd": margin.get(
                "recommended_selling_price_usd"
            ),
            "expected_profit_usd": margin.get(
                "expected_profit_usd"
            ),
        }

    return doc


def _save_route_history(
    result, request, quotation=None, authorization=None
):

    document = _history_document(
        result, request, quotation
    )

    # When a valid token is provided, the record is
    # attributed to the authenticated user instead of
    # trusting the user_id sent in the request body.
    if authorization:

        try:

            current = get_current_user(authorization)

            document["user_id"] = current.get(
                "user_id", document["user_id"]
            )

            document["user_contact"] = current.get(
                "contact", document["user_contact"]
            )

        except HTTPException:

            pass

    # Only save history when it can be associated
    # with a logged-in user.
    if not document["user_id"]:

        return None

    result = route_history_collection.insert_one(document)

    return result.inserted_id


def _serialize_utc_datetime(value):

    # Datetimes are stored in UTC. Older records may be naive
    # UTC datetimes; attach timezone info so the serialized
    # value always carries an explicit UTC offset and the
    # frontend can convert it to local time correctly.
    if value is not None and isinstance(value, datetime):

        if value.tzinfo is None:

            value = value.replace(tzinfo=timezone.utc)

        return value.isoformat()

    if value is not None and isinstance(value, str):

        return value

    return None


def _serialize_history_record(record):

    created_at = record.get("created_at")

    # Datetimes are stored in UTC. Older records may be naive
    # UTC datetimes; attach timezone info so the serialized
    # value always carries an explicit UTC offset and the
    # frontend can convert it to local time correctly.
    if created_at is not None and created_at.tzinfo is None:

        created_at = created_at.replace(
            tzinfo=timezone.utc
        )

    return {
        "record_id": str(record["_id"]),
        "user_id": record.get("user_id", ""),
        "user_contact": record.get(
            "user_contact", ""
        ),
        "origin": record.get("origin", ""),
        "destination": record.get(
            "destination", ""
        ),
        "cargo_type": record.get(
            "cargo_type", ""
        ),
        "cargo_subtype": record.get(
            "cargo_subtype", ""
        ),
        "containers": record.get("containers"),
        "route_id": record.get("route_id", ""),
        "route_name": record.get(
            "route_name", ""
        ),
        "transit_days": record.get("transit_days"),
        "distance_nm": record.get("distance_nm"),
        "transshipments": record.get(
            "transshipments"
        ),
        "route_score": record.get("route_score"),
        "total_available_routes": record.get(
            "total_available_routes", 0
        ),
        "pricing": record.get("pricing"),
        "margin": record.get("margin"),
        "approval_status": record.get(
            "approval_status", ""
        ),
        "accepted_at": _serialize_utc_datetime(
            record.get("accepted_at")
        ),
        "accepted_by": record.get("accepted_by", ""),
        "approved_by": record.get("approved_by", ""),
        "approved_at": _serialize_utc_datetime(
            record.get("approved_at")
        ),
        "rejected_by": record.get("rejected_by", ""),
        "rejection_reason": record.get(
            "rejection_reason", ""
        ),
        "rejected_at": _serialize_utc_datetime(
            record.get("rejected_at")
        ),
        "created_at": (
            created_at.isoformat()
            if created_at
            else None
        )
    }


def _require_user_id(user_id):

    owner_id = (user_id or "").strip()

    if not owner_id:

        raise HTTPException(
            status_code=400,
            detail="User identification is required."
        )

    return owner_id


# ============================================================
# ROUTE LOCATIONS
# ============================================================

@app.get("/api/routes/locations")
def get_locations():

    import pandas as pd

    df = pd.read_csv(
        "app/routes.csv"
    )

    origins = sorted(
        df["origin"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    destinations = sorted(
        df["destination"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    # -----------------------------------------------------
    # PORT COORDINATES
    # Additive map of every port name to its real
    # coordinates/country from routes.csv. Used by the
    # Maritime Route Map to plot ports before an analysis.
    # Existing clients only read origins/destinations, so
    # this extra field is fully backward compatible.
    # -----------------------------------------------------

    port_fields = (
        (
            "origin",
            "origin_latitude",
            "origin_longitude",
            "origin_country"
        ),
        (
            "destination",
            "destination_latitude",
            "destination_longitude",
            "destination_country"
        )
    )

    ports = {}

    for _, row in df.iterrows():

        for (
            port_field,
            latitude_field,
            longitude_field,
            country_field
        ) in port_fields:

            port_name = str(
                row.get(port_field, "")
            ).strip()

            if not port_name:
                continue

            if port_name in ports:
                continue

            try:

                latitude = float(
                    row.get(latitude_field, 0)
                )

                longitude = float(
                    row.get(longitude_field, 0)
                )

            except (TypeError, ValueError):

                continue

            ports[port_name] = {
                "latitude": latitude,
                "longitude": longitude,
                "country": str(
                    row.get(country_field, "")
                ).strip()
            }

    return {
        "origins": origins,
        "destinations": destinations,
        "ports": ports
    }


# ============================================================
# ROUTE NETWORK
# ============================================================
# Exposes the COMPLETE fixed maritime network built from
# routes.csv: every unique port represented by the dataset and
# every port-to-port connection (edge) with its route count.
# The map loads this once and never rebuilds it per search.
# This is reference data only - no user or private information.
# ============================================================

@app.get("/api/routes/network")
def get_route_network():

    import pandas as pd

    df = pd.read_csv(
        "app/routes.csv"
    )

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
    )

    # -----------------------------------------------------
    # COLLECT ALL UNIQUE PORTS WITH COORDINATES
    # Origin and destination ports together form the fixed
    # set of nodes in the maritime network.
    # -----------------------------------------------------

    port_fields = (
        (
            "origin",
            "origin_latitude",
            "origin_longitude",
            "origin_country"
        ),
        (
            "destination",
            "destination_latitude",
            "destination_longitude",
            "destination_country"
        )
    )

    ports = {}

    for _, row in df.iterrows():

        for (
            port_field,
            latitude_field,
            longitude_field,
            country_field
        ) in port_fields:

            port_name = str(
                row.get(port_field, "")
            ).strip()

            if not port_name:
                continue

            if port_name in ports:
                continue

            try:

                latitude = float(
                    row.get(latitude_field, 0)
                )

                longitude = float(
                    row.get(longitude_field, 0)
                )

            except (TypeError, ValueError):

                continue

            # Skip rows without a usable coordinate pair.
            if latitude == 0 and longitude == 0:
                continue

            ports[port_name] = {
                "latitude": latitude,
                "longitude": longitude,
                "country": str(
                    row.get(country_field, "")
                ).strip()
            }

    # -----------------------------------------------------
    # COLLECT ALL UNIQUE ORIGIN -> DESTINATION EDGES
    # Each edge aggregates how many route records connect
    # that origin-destination pair in routes.csv.
    # -----------------------------------------------------

    edge_cache = {}

    for _, row in df.iterrows():

        origin = str(row.get("origin", "")).strip()

        destination = str(
            row.get("destination", "")
        ).strip()

        if not origin or not destination:
            continue

        key = (origin, destination)

        if key not in edge_cache:

            edge_cache[key] = {
                "origin": origin,
                "destination": destination,
                "route_count": 0,
                "min_transit_days": None,
                "min_distance_nm": None
            }

        edge = edge_cache[key]

        edge["route_count"] += 1

        try:

            transit_days = float(
                row.get("transit_days", 0)
            )

            distance_nm = float(
                row.get("distance_nm", 0)
            )

        except (TypeError, ValueError):

            continue

        if (
            edge["min_transit_days"] is None
            or transit_days < edge["min_transit_days"]
        ):
            edge["min_transit_days"] = transit_days

        if (
            edge["min_distance_nm"] is None
            or distance_nm < edge["min_distance_nm"]
        ):
            edge["min_distance_nm"] = distance_nm

    edges = sorted(
        [
            {
                "origin": edge["origin"],
                "destination": edge["destination"],
                "route_count": edge["route_count"],
                "min_transit_days": edge["min_transit_days"],
                "min_distance_nm": edge["min_distance_nm"]
            }
            for edge in edge_cache.values()
        ],
        key=lambda edge: (
            edge["origin"],
            edge["destination"]
        )
    )

    # -----------------------------------------------------
    # ROUTE RECORD COUNT
    # The complete number of route records in routes.csv is
    # exposed as a summary metric. Individual route rows are
    # intentionally NOT attached here: the fixed network only
    # needs the ports and edges above, and a full 7800+ row
    # JSON payload would massively bloat every map load.
    # The Route Agent (/api/routes/analyze) already returns
    # the searched route records with their own coordinates.
    # -----------------------------------------------------

    return {
        "success": True,
        "total_ports": len(ports),
        "total_routes": int(len(df)),
        "total_edges": len(edges),
        "ports": ports,
        "edges": edges
    }


# ============================================================
# LIVE AIS VESSELS
# ============================================================
# Real AIS vessel positions from the AIS provider (AISHub).
# The provider API key lives ONLY in the backend environment
# and is never returned to the browser. The response ships a
# small, normalized vessel list that the Maritime Route Map
# renders as real vessel markers.
#
# When AIS_API_KEY is missing the endpoint still answers with
# a friendly "not configured" payload so the route map never
# crashes. Provider failures answer with an "unavailable"
# payload - the dataset routes keep working either way.
# ============================================================

@app.get("/api/vessels")
def get_ais_vessels(
    min_lat: float = None,
    min_lon: float = None,
    max_lat: float = None,
    max_lon: float = None
):

    return fetch_ais_vessels(
        latmin=min_lat,
        lonmin=min_lon,
        latmax=max_lat,
        lonmax=max_lon
    )


# ============================================================
# CARGO SUBTYPES
# ============================================================

@app.get("/api/routes/cargo-subtypes")
def get_cargo_subtypes(
    origin: str = "",
    destination: str = "",
    cargo_type: str = ""
):

    import pandas as pd

    df = pd.read_csv(
        "app/routes.csv"
    )

    filters_provided = bool(
        origin or destination or cargo_type
    )

    # -----------------------------------------------------
    # PARTIAL FILTERS ARE NOT ALLOWED
    # -----------------------------------------------------

    if filters_provided and not (
        origin and destination and cargo_type
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "origin, destination and cargo_type "
                "are all required."
            )
        )

    # -----------------------------------------------------
    # FILTERED CARGO SUBTYPES
    # Origin + Destination + Cargo Type
    # -----------------------------------------------------

    if filters_provided:

        mask = (
            df["origin"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            ==
            origin.strip().lower()
        ) & (
            df["destination"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            ==
            destination.strip().lower()
        ) & (
            df["cargo_type"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            ==
            cargo_type.strip().lower()
        )

        subtypes = sorted(
            set(
                df.loc[mask, "cargo_subtype"]
                .fillna("")
                .astype(str)
                .str.strip()
                .tolist()
            )
        )

        subtypes = [
            subtype
            for subtype in subtypes
            if subtype
        ]

        return {
            "origin": origin.strip(),
            "destination": destination.strip(),
            "cargo_type": cargo_type.strip(),
            "cargo_subtypes": subtypes
        }

    # -----------------------------------------------------
    # GLOBAL CARGO SUBTYPES
    # Grouped by cargo type for the Cargo Type dropdown
    # -----------------------------------------------------

    cargo_subtypes = {}

    for cargo_type_value, group in df.groupby(
        "cargo_type"
    ):

        subtypes = sorted(
            group["cargo_subtype"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        cargo_subtypes[
            str(cargo_type_value).strip()
        ] = subtypes

    return cargo_subtypes


# ============================================================
# ROUTE ANALYSIS
# ============================================================

@app.post("/api/routes/analyze")
def analyze_shipment(
    request: RouteRequest,
    authorization: str = Header(None)
):

    try:

        result = analyze_route(
            request.origin,
            request.destination,
            request.cargo_type,
            request.cargo_subtype,
            request.containers
        )

        # -------------------------------------------------
        # SAVE ROUTE HISTORY
        # Only successful analyses reach this point.
        # A history failure never affects the response.
        # -------------------------------------------------

        try:

            _save_route_history(
                result, request, authorization=authorization
            )

        except Exception as history_error:

            logger.warning(
                "Could not save route history: %s",
                history_error
            )

        return result

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


# ============================================================
# QUOTATION GENERATION
# ============================================================

@app.post("/api/quotations/generate")
def api_generate_quotation(
    request: RouteRequest,
    authorization: str = Header(None)
):

    try:

        quotation = generate_quotation(
            request.origin,
            request.destination,
            request.cargo_type,
            request.cargo_subtype,
            request.containers
        )

        # Save quotation history with pricing data

        quotation_record_id = None

        try:

            route_result = {
                "recommended_route": {
                    "route_id": quotation.get(
                        "route", {}
                    ).get("route_id", ""),
                    "route": quotation.get(
                        "route", {}
                    ).get("route_name", ""),
                    "transit_days": quotation.get(
                        "route", {}
                    ).get("transit_days"),
                    "distance_nm": quotation.get(
                        "route", {}
                    ).get("distance_nm"),
                    "transshipments": quotation.get(
                        "route", {}
                    ).get("transshipments"),
                    "score": quotation.get(
                        "route", {}
                    ).get("route_score"),
                },
                "origin": request.origin,
                "destination": request.destination,
                "cargo_type": request.cargo_type,
                "cargo_subtype": request.cargo_subtype,
                "containers": request.containers,
            }

            quotation_record_id = (
                _save_route_history(
                    route_result, request, quotation,
                    authorization=authorization
                )
            )

        except Exception as history_error:

            logger.warning(
                "Could not save quotation history: %s",
                history_error
            )

        # The printed quotation is extended with the saved
        # history record id so the frontend can later submit
        # "Accept Quotation" to create a shipment.
        return {
            **quotation,
            "quotation_id": (
                str(quotation_record_id)
                if quotation_record_id
                else None
            )
        }

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:

        logger.error(
            "Quotation generation error: %s", error
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to generate quotation. "
                   "Please try again later."
        )


# ============================================================
# ROUTE HISTORY
# ============================================================
# When a valid backend token is provided, the request is scoped
# to the authenticated user's own history. A normal user cannot
# view another user's records by altering query parameters.
# For backward compatibility, requests without a token still
# fall back to the previous user_id-based behaviour used by
# existing clients.
# ============================================================

def _resolve_identity(
    user_id: str,
    authorization: str = None
):

    if authorization:

        try:

            current = get_current_user(authorization)

            return current.get("user_id")

        except HTTPException:

            # Invalid or expired token is treated as
            # unauthenticated below.
            pass

    return _require_user_id(user_id)


@app.get("/api/routes/history")
def get_route_history(
    user_id: str = "",
    contact: str = "",
    authorization: str = Header(None)
):

    owner_id = _resolve_identity(user_id, authorization)

    records = (
        route_history_collection
        .find(
            {"user_id": owner_id}
        )
        .sort(
            "created_at",
            -1
        )
        .limit(200)
    )

    return {
        "success": True,
        "history": [
            _serialize_history_record(record)
            for record in records
        ]
    }


@app.delete("/api/routes/history/{record_id}")
def delete_route_history(
    record_id: str,
    user_id: str = "",
    authorization: str = Header(None)
):

    owner_id = _resolve_identity(user_id, authorization)

    try:

        record_object_id = ObjectId(record_id)

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="The route history record is invalid."
        )

    # Only the record that belongs to the current user
    # can be deleted. routes.csv is never touched.
    result = route_history_collection.delete_one({
        "_id": record_object_id,
        "user_id": owner_id
    })

    if result.deleted_count == 0:

        raise HTTPException(
            status_code=404,
            detail="Route history record not found."
        )

    return {
        "success": True,
        "message": "Route history record deleted."
    }


@app.delete("/api/routes/history")
def clear_route_history(
    user_id: str = "",
    authorization: str = Header(None)
):

    owner_id = _resolve_identity(user_id, authorization)

    # Only the current user's history is removed.
    result = route_history_collection.delete_many({
        "user_id": owner_id
    })

    return {
        "success": True,
        "message": "Route history cleared.",
        "deleted_count": result.deleted_count
    }


# ============================================================
# SHIPMENT HELPERS
# ============================================================
# A shipment is created ONLY when a user accepts a generated
# quotation. The business flow remains:
# Shipment Request -> Route Agent -> Pricing Agent ->
# Margin Agent -> Quotation -> User Accepts -> Shipment.
# ============================================================

def _generate_shipment_id() -> str:
    """
    Generate the next shipment identifier (SHP-1001,
    SHP-1002, ...) using an atomic MongoDB counter so
    concurrent requests never receive the same number.
    """

    counter = counters_collection.find_one_and_update(
        {"_id": "shipment_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER
    )

    sequence = counter.get("seq", 1)

    return f"SHP-{1000 + int(sequence)}"


def _serialize_shipment(shipment: dict) -> dict:
    """
    Convert a shipment document into a safe JSON-
    friendly response. No passwords or secrets here.
    """

    created_at = shipment.get("created_at")

    # Datetimes are stored in UTC. Older records may be
    # naive UTC datetimes; attach timezone info so the
    # serialized value always carries an explicit UTC
    # offset and the frontend can convert it to India
    # Standard Time (Asia/Kolkata) correctly.
    if created_at is not None and created_at.tzinfo is None:

        created_at = created_at.replace(
            tzinfo=timezone.utc
        )

    return {
        "shipment_id": shipment.get(
            "shipment_id", ""
        ),
        "user_id": shipment.get("user_id", ""),
        "user_contact": shipment.get(
            "user_contact", ""
        ),
        "user_name": shipment.get("user_name", ""),
        "origin": shipment.get("origin", ""),
        "destination": shipment.get(
            "destination", ""
        ),
        "cargo_type": shipment.get("cargo_type", ""),
        "cargo_subtype": shipment.get(
            "cargo_subtype", ""
        ),
        "containers": shipment.get("containers"),
        "route_id": shipment.get("route_id", ""),
        "route_name": shipment.get("route_name", ""),
        "transit_days": shipment.get("transit_days"),
        "distance_nm": shipment.get("distance_nm"),
        "transshipments": shipment.get(
            "transshipments"
        ),
        "quotation_id": shipment.get(
            "quotation_record_id", ""
        ),
        "pricing": shipment.get("pricing"),
        "margin": shipment.get("margin"),
        "status": shipment.get(
            "status", SHIPMENT_STATUS_FLOW[0]
        ),
        "status_history": [
            {
                "status": entry.get("status", ""),
                "at": _serialize_utc_datetime(
                    entry.get("at")
                )
            }
            for entry in (
                shipment.get("status_history") or []
            )
            if isinstance(entry, dict)
        ],
        "created_at": (
            created_at.isoformat()
            if created_at
            else None
        )
    }


# ============================================================
# MY SHIPMENTS
# ============================================================
# Returns only the logged-in user's shipment records.
# The token identity is authoritative when provided.
# ============================================================

@app.get("/api/shipments")
def get_my_shipments(
    user_id: str = "",
    authorization: str = Header(None)
):

    owner_id = _resolve_identity(user_id, authorization)

    records = (
        shipments_collection
        .find({"user_id": owner_id})
        .sort("created_at", -1)
        .limit(200)
    )

    return {
        "success": True,
        "shipments": [
            _serialize_shipment(record)
            for record in records
        ]
    }


# ============================================================
# SHIPMENT DETAILS
# ============================================================
# A normal user may only open their own shipment. A missing
# or foreign shipment returns a generic 404.
# ============================================================

@app.get("/api/shipments/{shipment_id}")
def get_shipment_details(
    shipment_id: str,
    user_id: str = "",
    authorization: str = Header(None)
):

    owner_id = _resolve_identity(user_id, authorization)

    shipment = shipments_collection.find_one({
        "shipment_id": shipment_id.strip()
    })

    if not shipment:

        raise HTTPException(
            status_code=404,
            detail="Shipment not found."
        )

    if str(shipment.get("user_id", "")) != owner_id:

        raise HTTPException(
            status_code=404,
            detail="Shipment not found."
        )

    return {
        "success": True,
        "shipment": _serialize_shipment(shipment)
    }


# ============================================================
# QUOTATION APPROVAL WORKFLOW
# ============================================================
# After a user accepts a quotation, the quotation is queued for
# admin approval (approval_status = "pending_admin_approval").
# A shipment is created ONLY after an admin approves it. If the
# admin rejects it, no shipment is ever created and the rejection
# reason is preserved for audit.
#
# Flow: Quotation -> User Accepts -> Pending Admin Approval ->
#        Approved (shipment created) OR Rejected (reason stored).
# ============================================================

def _get_quotation_record_or_400(quotation_id):
    """
    Resolve a route_history record that is a generated
    quotation. Raises HTTP errors for invalid references,
    missing records and non-quotation records.
    """

    try:

        quotation_object_id = ObjectId(quotation_id)

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="The quotation reference is invalid."
        )

    quotation_record = route_history_collection.find_one({
        "_id": quotation_object_id
    })

    if not quotation_record:

        raise HTTPException(
            status_code=404,
            detail="Quotation not found."
        )

    if not (
        quotation_record.get("pricing")
        and quotation_record.get("margin")
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "This record is not a generated quotation. "
                "Generate a quotation first."
            )
        )

    return quotation_record


def _resolve_user_name(user_id: str) -> str:
    """
    Look up a user's display name. Missing or invalid
    references safely return an empty string.
    """

    if not user_id:

        return ""

    try:

        user = users_collection.find_one({
            "_id": ObjectId(user_id)
        })

    except Exception:

        return ""

    return user.get("name", "") if user else ""


def _create_shipment_document(quotation_record):
    """
    Build and insert the shipment for an approved quotation.

    Idempotent: if a shipment already exists for this quotation
    the existing document is returned and nothing new is inserted,
    so the approval endpoint can never create duplicate shipments.
    The original quotation pricing/margin is copied unchanged.
    """

    quotation_record_id_str = str(quotation_record["_id"])

    existing_shipment = shipments_collection.find_one({
        "quotation_record_id": quotation_record_id_str
    })

    if existing_shipment:

        return existing_shipment

    shipment_id = _generate_shipment_id()

    shipment = {
        "shipment_id": shipment_id,
        "user_id": quotation_record.get("user_id", ""),
        "user_contact": quotation_record.get(
            "user_contact", ""
        ),
        "user_name": _resolve_user_name(
            quotation_record.get("user_id", "")
        ),
        "origin": quotation_record.get("origin", ""),
        "destination": quotation_record.get(
            "destination", ""
        ),
        "cargo_type": quotation_record.get(
            "cargo_type", ""
        ),
        "cargo_subtype": quotation_record.get(
            "cargo_subtype", ""
        ),
        "containers": quotation_record.get("containers"),
        "route_id": quotation_record.get("route_id", ""),
        "route_name": quotation_record.get(
            "route_name", ""
        ),
        "transit_days": quotation_record.get(
            "transit_days"
        ),
        "distance_nm": quotation_record.get(
            "distance_nm"
        ),
        "transshipments": quotation_record.get(
            "transshipments"
        ),
        "quotation_record_id": quotation_record_id_str,
        "pricing": quotation_record.get("pricing"),
        "margin": quotation_record.get("margin"),
        "status": SHIPMENT_STATUS_FLOW[0],
        "status_history": [{
            "status": SHIPMENT_STATUS_FLOW[0],
            "at": datetime.now(timezone.utc)
        }],
        "created_at": datetime.now(timezone.utc)
    }

    shipments_collection.insert_one(shipment)

    return shipment


# ============================================================
# ACCEPT QUOTATION -> PENDING ADMIN APPROVAL
# ============================================================
# The user submits a generated quotation for acceptance.
# The backend validates that the quotation exists, belongs
# to the current user, marks it pending_admin_approval and
# does NOT create a shipment. Shipment creation happens
# only after an admin approves it.
# ============================================================

@app.post("/api/quotations/{quotation_id}/accept")
def accept_quotation(
    quotation_id: str,
    current_user: dict = Depends(get_current_user)
):

    quotation_record = _get_quotation_record_or_400(
        quotation_id
    )

    # -------------------------------------------------
    # OWNERSHIP CHECK
    # -------------------------------------------------

    record_owner = str(
        quotation_record.get("user_id", "") or ""
    )

    if record_owner and record_owner != current_user.get(
        "user_id", ""
    ):

        raise HTTPException(
            status_code=403,
            detail=(
                "This quotation does not belong "
                "to your account."
            )
        )

    quotation_record_id_str = str(quotation_record["_id"])

    # -------------------------------------------------
    # LEGACY / APPROVED QUOTATIONS
    # A shipment already exists for this quotation
    # (approved quotations, or quotations accepted
    # before the admin approval gate). Idempotent.
    # -------------------------------------------------

    existing_shipment = shipments_collection.find_one({
        "quotation_record_id": quotation_record_id_str
    })

    if existing_shipment:

        return {
            "success": True,
            "already_exists": True,
            "message": (
                "A shipment was already created "
                "for this quotation."
            ),
            "shipment": _serialize_shipment(
                existing_shipment
            )
        }

    # -------------------------------------------------
    # REJECTED QUOTATION
    # A rejected quotation cannot be re-accepted.
    # -------------------------------------------------

    existing_approval_status = quotation_record.get(
        "approval_status", ""
    )

    if existing_approval_status == "rejected":

        raise HTTPException(
            status_code=400,
            detail=(
                "This quotation was rejected by admin "
                "and cannot be accepted."
            )
        )

    # -------------------------------------------------
    # ALREADY PENDING
    # Re-accepting a pending quotation is a no-op.
    # -------------------------------------------------

    if existing_approval_status == "pending_admin_approval":

        return {
            "success": True,
            "already_accepted": True,
            "approval_status": "pending_admin_approval",
            "message": (
                "This quotation is already pending "
                "admin approval."
            )
        }

    if existing_approval_status == "approved":

        # Very rare edge case: marked approved but the
        # shipment document is missing. Queue it for the
        # admin to (re)approve rather than silently
        # creating a shipment on accept.
        return {
            "success": True,
            "already_accepted": True,
            "approval_status": "pending_admin_approval",
            "message": (
                "This quotation is being processed "
                "for shipment creation."
            )
        }

    # -------------------------------------------------
    # MARK PENDING ADMIN APPROVAL
    # The quotation data, pricing and margin are left
    # untouched. An audit trail is recorded.
    # -------------------------------------------------

    accepted_at = datetime.now(timezone.utc)

    route_history_collection.update_one(
        {"_id": quotation_record["_id"]},
        {"$set": {
            "approval_status": "pending_admin_approval",
            "accepted_at": accepted_at,
            "accepted_by": (
                current_user.get("name", "")
                or current_user.get("contact", "")
            )
        }}
    )

    return {
        "success": True,
        "pending": True,
        "approval_status": "pending_admin_approval",
        "message": (
            "Quotation accepted successfully. Your "
            "quotation is now pending admin approval. "
            "Your shipment will be created once an "
            "admin approves it."
        )
    }


# ============================================================
# ADMIN - APPROVE QUOTATION
# ============================================================
# Marks the quotation approved and creates the shipment using
# the existing shipment workflow. Idempotent: calling this
# endpoint twice never creates a second shipment.
# ============================================================

@app.post("/api/admin/quotations/{quotation_id}/approve")
def approve_quotation(
    quotation_id: str,
    current_user: dict = Depends(require_admin)
):

    quotation_record = _get_quotation_record_or_400(
        quotation_id
    )

    quotation_record_id_str = str(quotation_record["_id"])

    existing_approval_status = quotation_record.get(
        "approval_status", ""
    )

    if existing_approval_status == "rejected":

        raise HTTPException(
            status_code=400,
            detail=(
                "This quotation was already rejected "
                "and cannot be approved."
            )
        )

    # -------------------------------------------------
    # IDEMPOTENT RE-APPROVAL
    # An already-approved quotation is returned with its
    # existing shipment. No duplicate is ever created.
    # -------------------------------------------------

    if existing_approval_status == "approved":

        existing_shipment = shipments_collection.find_one({
            "quotation_record_id": quotation_record_id_str
        })

        if existing_shipment:

            return {
                "success": True,
                "already_approved": True,
                "approval_status": "approved",
                "message": (
                    "This quotation was already approved."
                ),
                "shipment": _serialize_shipment(
                    existing_shipment
                )
            }

    # -------------------------------------------------
    # MARK APPROVED
    # Original pricing/margin is never recalculated here.
    # -------------------------------------------------

    approved_at = datetime.now(timezone.utc)

    route_history_collection.update_one(
        {"_id": quotation_record["_id"]},
        {"$set": {
            "approval_status": "approved",
            "approved_by": (
                current_user.get("name", "")
                or current_user.get("contact", "")
            ),
            "approved_at": approved_at
        }}
    )

    # -------------------------------------------------
    # CREATE SHIPMENT
    # Reuses the existing shipment creation logic and
    # starts at the first status ("Booking Confirmed").
    # -------------------------------------------------

    shipment = _create_shipment_document(quotation_record)

    return {
        "success": True,
        "approval_status": "approved",
        "message": (
            "Quotation approved. Shipment "
            f"{shipment['shipment_id']} has been created."
        ),
        "shipment": _serialize_shipment(shipment)
    }


# ============================================================
# ADMIN - REJECT QUOTATION
# ============================================================
# Requires a non-empty rejection reason. The quotation is
# preserved (never deleted), no shipment is created, and the
# rejection details are stored for audit. Idempotent.
# ============================================================

@app.post("/api/admin/quotations/{quotation_id}/reject")
def reject_quotation(
    quotation_id: str,
    request: QuotationRejectRequest,
    current_user: dict = Depends(require_admin)
):

    reason = request.reason.strip()

    if not reason:

        raise HTTPException(
            status_code=400,
            detail=(
                "Please provide a reason for rejecting "
                "this quotation."
            )
        )

    quotation_record = _get_quotation_record_or_400(
        quotation_id
    )

    quotation_record_id_str = str(quotation_record["_id"])

    existing_approval_status = quotation_record.get(
        "approval_status", ""
    )

    # -------------------------------------------------
    # A quotation that already produced a shipment can
    # never be rejected afterwards.
    # -------------------------------------------------

    existing_shipment = shipments_collection.find_one({
        "quotation_record_id": quotation_record_id_str
    })

    if existing_shipment:

        raise HTTPException(
            status_code=400,
            detail=(
                "This quotation already has a shipment "
                "and cannot be rejected."
            )
        )

    if existing_approval_status == "approved":

        raise HTTPException(
            status_code=400,
            detail=(
                "This quotation has already been "
                "approved."
            )
        )

    # -------------------------------------------------
    # IDEMPOTENT RE-REJECTION
    # -------------------------------------------------

    if existing_approval_status == "rejected":

        return {
            "success": True,
            "already_rejected": True,
            "approval_status": "rejected",
            "message": (
                "This quotation was already rejected."
            ),
            "reason": quotation_record.get(
                "rejection_reason", ""
            )
        }

    # -------------------------------------------------
    # MARK REJECTED
    # The quotation and its pricing are preserved and
    # no shipment is created.
    # -------------------------------------------------

    rejected_at = datetime.now(timezone.utc)

    route_history_collection.update_one(
        {"_id": quotation_record["_id"]},
        {"$set": {
            "approval_status": "rejected",
            "rejection_reason": reason,
            "rejected_by": (
                current_user.get("name", "")
                or current_user.get("contact", "")
            ),
            "rejected_at": rejected_at
        }}
    )

    return {
        "success": True,
        "approval_status": "rejected",
        "message": (
            "Quotation rejected. The customer has been "
            "notified of the decision."
        ),
        "reason": reason
    }


# ============================================================
# ADMIN HELPER - SAFE USER DOCUMENT
# ============================================================
# Never returns passwords or password hashes.
# ============================================================

def _serialize_safe_user(user):

    created_at = user.get("created_at")

    return {
        "id": str(user["_id"]),
        "name": user.get("name", ""),
        "contact": user.get("contact", ""),
        "role": get_user_role(user),
        "verified": user.get("verified", False),
        "mfa_enabled": user.get("mfa_enabled", False),
        "created_at": (
            created_at.isoformat()
            if created_at
            else None
        )
    }


# ============================================================
# ADMIN - STATISTICS
# ============================================================
# Real counts calculated from MongoDB collections.
# ============================================================

@app.get("/api/admin/stats")
def get_admin_stats(
    current_user: dict = Depends(require_admin)
):

    total_users = users_collection.count_documents({})

    total_route_analyses = (
        route_history_collection.count_documents({})
    )

    total_quotations = (
        route_history_collection.count_documents({
            "pricing": {"$exists": True}
        })
    )

    total_shipments = (
        shipments_collection.count_documents({})
    )

    active_shipments = (
        shipments_collection.count_documents({
            "status": {"$ne": "Delivered"}
        })
    )

    delivered_shipments = (
        shipments_collection.count_documents({
            "status": "Delivered"
        })
    )

    return {
        "success": True,
        "total_users": total_users,
        "total_route_analyses": total_route_analyses,
        "total_quotations": total_quotations,
        "total_shipments": total_shipments,
        "active_shipments": active_shipments,
        "delivered_shipments": delivered_shipments
    }


# ============================================================
# ADMIN - USERS
# ============================================================
# Returns only safe user information. No passwords or hashes.
# ============================================================

@app.get("/api/admin/users")
def get_admin_users(
    search: str = "",
    current_user: dict = Depends(require_admin)
):

    query = {}

    search_term = search.strip()

    if search_term:

        search_regex = re.compile(
            re.escape(search_term),
            re.IGNORECASE
        )

        query = {
            "$or": [
                {"name": search_regex},
                {"contact": search_regex}
            ]
        }

    users_cursor = (
        users_collection
        .find(query)
        .sort("created_at", -1)
        .limit(500)
    )

    return {
        "success": True,
        "users": [
            _serialize_safe_user(user)
            for user in users_cursor
        ]
    }


# ============================================================
# ADMIN - ROUTE ACTIVITY
# ============================================================
# Aggregated route analyses across all users.
# ============================================================

@app.get("/api/admin/route-activity")
def get_admin_route_activity(
    current_user: dict = Depends(require_admin)
):

    records = (
        route_history_collection
        .find({})
        .sort("created_at", -1)
        .limit(200)
    )

    return {
        "success": True,
        "activity": [
            _serialize_history_record(record)
            for record in records
        ]
    }


# ============================================================
# ADMIN - QUOTATIONS
# ============================================================
# Quotations are stored inside route_history records that
# carry embedded pricing/margin data. No extra collection
# is needed or created.
# ============================================================

@app.get("/api/admin/quotations")
def get_admin_quotations(
    current_user: dict = Depends(require_admin)
):

    records = (
        route_history_collection
        .find({"pricing": {"$exists": True}})
        .sort("created_at", -1)
        .limit(200)
    )

    return {
        "success": True,
        "quotations": [
            _serialize_history_record(record)
            for record in records
        ]
    }


# ============================================================
# ADMIN - SHIPMENTS
# ============================================================
# All shipments across every user, optionally filtered by
# status. Monitoring only; never exposes sensitive data.
# ============================================================

@app.get("/api/admin/shipments")
def get_admin_shipments(
    status: str = "",
    current_user: dict = Depends(require_admin)
):

    query = {}

    status_filter = status.strip()

    if status_filter:

        query["status"] = status_filter

    records = (
        shipments_collection
        .find(query)
        .sort("created_at", -1)
        .limit(500)
    )

    return {
        "success": True,
        "shipments": [
            _serialize_shipment(record)
            for record in records
        ],
        "statuses": SHIPMENT_STATUS_FLOW
    }


# ============================================================
# ADMIN - UPDATE SHIPMENT STATUS
# ============================================================
# Allows safe, validated forward-status transitions only.
# This is a simulated platform workflow, not real-time
# vessel tracking.
# ============================================================

@app.patch("/api/admin/shipments/{shipment_id}/status")
def update_shipment_status(
    shipment_id: str,
    request: ShipmentStatusUpdate,
    current_user: dict = Depends(require_admin)
):

    shipment = shipments_collection.find_one({
        "shipment_id": shipment_id.strip()
    })

    if not shipment:

        raise HTTPException(
            status_code=404,
            detail="Shipment not found."
        )

    new_status = request.status.strip()

    if new_status not in SHIPMENT_STATUS_FLOW:

        raise HTTPException(
            status_code=400,
            detail="Invalid shipment status."
        )

    current_status = shipment.get(
        "status", SHIPMENT_STATUS_FLOW[0]
    )

    if new_status == current_status:

        return {
            "success": True,
            "message": "Shipment status is unchanged.",
            "shipment": _serialize_shipment(shipment)
        }

    current_index = SHIPMENT_STATUS_FLOW.index(
        current_status
    )

    new_index = SHIPMENT_STATUS_FLOW.index(new_status)

    if new_index < current_index:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid status transition. A shipment "
                "cannot move backwards in the workflow."
            )
        )

    updated_at = datetime.now(timezone.utc)

    shipments_collection.update_one(
        {"_id": shipment["_id"]},
        {
            "$set": {"status": new_status},
            "$push": {
                "status_history": {
                    "status": new_status,
                    "at": updated_at
                }
            }
        }
    )

    updated = shipments_collection.find_one({
        "_id": shipment["_id"]
    })

    return {
        "success": True,
        "message": (
            f"Shipment {shipment_id} status updated "
            f"to '{new_status}'."
        ),
        "shipment": _serialize_shipment(updated)
    }


# ============================================================
# ADMIN - PRICING & MARGIN
# ============================================================
# FEEDBACK - HELPERS
# ============================================================

def _normalize_feedback_rating(value):

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _serialize_feedback(record):
    created_at = record.get("created_at")

    if isinstance(created_at, datetime):
        created_at_text = created_at.isoformat()
    elif isinstance(created_at, str):
        created_at_text = created_at
    else:
        created_at_text = None

    return {
        "feedback_id": str(record["_id"]),
        "user_id": record.get("user_id", ""),
        "user_name": record.get("user_name", ""),
        "user_contact": record.get("user_contact", ""),
        "rating": _normalize_feedback_rating(
            record.get("rating", 0)
        ),
        "feedback_type": record.get("feedback_type", ""),
        "message": record.get("message", ""),
        "created_at": created_at_text
    }


# ============================================================
# FEEDBACK - SUBMIT
# ============================================================
# Any authenticated user can submit feedback.
# ============================================================

@app.post("/api/feedback")
def submit_feedback(
    request: FeedbackCreate,
    current_user: dict = Depends(get_current_user)
):

    rating = request.rating
    feedback_type = request.feedback_type.strip()
    message = request.message.strip()

    if rating < 1 or rating > 5:

        raise HTTPException(
            status_code=400,
            detail="Rating must be between 1 and 5."
        )

    if not feedback_type:

        raise HTTPException(
            status_code=400,
            detail="Feedback type is required."
        )

    if not message:

        raise HTTPException(
            status_code=400,
            detail="Feedback message is required."
        )

    feedback_doc = {
        "user_id": current_user.get("user_id", ""),
        "user_name": current_user.get("name", ""),
        "user_contact": current_user.get("contact", ""),
        "rating": rating,
        "feedback_type": feedback_type,
        "message": message,
        "created_at": datetime.utcnow()
    }

    result = feedbacks_collection.insert_one(feedback_doc)

    return {
        "success": True,
        "message": "Feedback submitted successfully.",
        "feedback_id": str(result.inserted_id)
    }


# ============================================================
# FEEDBACK - MY FEEDBACK
# ============================================================
# Returns only the current user's feedback.
# ============================================================

@app.get("/api/feedback")
def get_my_feedback(
    current_user: dict = Depends(get_current_user)
):

    records = (
        feedbacks_collection
        .find({"user_id": current_user.get("user_id", "")})
        .sort("created_at", -1)
        .limit(100)
    )

    return {
        "success": True,
        "feedback": [
            _serialize_feedback(record)
            for record in records
        ]
    }


# ============================================================
# ADMIN - FEEDBACK
# ============================================================
# Returns all feedback across the platform.
# Protected by the admin role requirement.
# ============================================================

@app.get("/api/admin/feedback")
def get_admin_feedback(
    current_user: dict = Depends(require_admin)
):

    records = (
        feedbacks_collection
        .find({})
        .sort("created_at", -1)
        .limit(500)
    )

    return {
        "success": True,
        "feedback": [
            _serialize_feedback(record)
            for record in records
        ]
    }


# ============================================================
# ADMIN - PRICING & MARGIN
# ============================================================
# The Pricing Agent and Margin Agent formulas are never
# changed and the CSV files are never modified here.
# ============================================================

@app.get("/api/admin/pricing")
def get_admin_pricing(
    current_user: dict = Depends(require_admin)
):

    import pandas as pd

    try:

        pricing_df = pd.read_csv(
            "app/data/pricing.csv"
        )

        routes_df = pd.read_csv(
            "app/routes.csv"
        )

    except Exception as error:

        logger.error(
            "Unable to load pricing data: %s", error
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load pricing data."
        )

    # Normalize column names like the agents do.
    pricing_df.columns = (
        pricing_df.columns.str.strip().str.lower()
    )

    routes_df.columns = (
        routes_df.columns.str.strip().str.lower()
    )

    pricing_rows = []

    for _, pricing_row in pricing_df.iterrows():

        route_id = str(
            pricing_row.get("route_id", "")
        ).strip()

        route_match = routes_df[
            routes_df["route_id"].astype(str).str.strip()
            == route_id
        ]

        route_info = {}

        if not route_match.empty:

            route_row = route_match.iloc[0]

            route_info = {
                "origin": route_row.get("origin", ""),
                "destination": route_row.get(
                    "destination", ""
                ),
                "route_name": route_row.get(
                    "route", ""
                ),
                "base_freight_usd": (
                    float(route_row["freight_cost_usd"])
                    if pd.notna(
                        route_row.get(
                            "freight_cost_usd", None
                        )
                    )
                    else None
                ),
            }

        pricing_rows.append({
            "pricing_id": str(
                pricing_row.get("pricing_id", "")
            ).strip(),
            "route_id": route_id,
            "origin": route_info.get("origin", None),
            "destination": route_info.get(
                "destination", None
            ),
            "route_name": route_info.get(
                "route_name", None
            ),
            "base_freight_usd": route_info.get(
                "base_freight_usd", None
            ),
            "fuel_surcharge_usd": (
                float(pricing_row["fuel_surcharge_usd"])
                if pd.notna(
                    pricing_row.get(
                        "fuel_surcharge_usd", None
                    )
                )
                else None
            ),
            "port_charge_usd": (
                float(pricing_row["port_charge_usd"])
                if pd.notna(
                    pricing_row.get(
                        "port_charge_usd", None
                    )
                )
                else None
            ),
            "risk_surcharge_usd": (
                float(pricing_row["risk_surcharge_usd"])
                if pd.notna(
                    pricing_row.get(
                        "risk_surcharge_usd", None
                    )
                )
                else None
            ),
            "demand_factor": (
                float(pricing_row["demand_factor"])
                if pd.notna(
                    pricing_row.get(
                        "demand_factor", None
                    )
                )
                else None
            ),
            "target_margin_percent": (
                float(pricing_row["target_margin_percent"])
                if pd.notna(
                    pricing_row.get(
                        "target_margin_percent", None
                    )
                )
                else None
            ),
        })

    return {
        "success": True,
        "pricing": pricing_rows,
        "count": len(pricing_rows)
    }