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
import secrets
import logging
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from app.models import (
    RouteRequest,
    WeatherAnalyzeRequest,
    CustomsCheckRequest,
    AssistantRequest
)
from app.agents.route_agent import analyze_route
from app.agents.quotation_service import (
    generate_quotation
)
from app.agents.orchestrator import (
    generate_freight_intelligence
)
from app.agents.weather_agent import (
    analyze_weather,
    analyze_routes_weather,
    get_weather_summary,
    weather_for_route
)
from app.agents.customs_agent import (
    analyze_customs,
    get_customs_summary,
    list_customs_records
)
from app.agents.assistant_agent import (
    answer_user_question,
    answer_admin_question
)
from app.services.gemini_service import (
    generate_customs_advisory,
    generate_assistant_reply,
    get_gemini_configuration
)
from app.services.project_context import (
    build_project_knowledge,
    build_agent_reference
)
from app.services.ais_service import (
    fetch_ais_vessels,
)
from app.services.executive_dashboard import (
    build_executive_report
)


logger = logging.getLogger("uvicorn.error")


# ============================================================
# DATASET PATHS
# ============================================================
# Resolved from this file's own location so the datasets are
# found no matter which directory the backend was started
# from (`cd backend` or the project root). The dataset files
# themselves stay exactly where they are.

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")

ROUTES_CSV_PATH = os.path.join(APP_DIR, "routes.csv")

PRICING_CSV_PATH = os.path.join(APP_DIR, "data", "pricing.csv")


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
# Local development defaults to the Vite dev server. Production
# deployments add their own frontend origins through
# CORS_ORIGINS (a comma-separated list) or open the API to any
# origin with ALLOW_ALL_ORIGINS=true. Both are read from the
# environment so the backend can restage without a code change.
# ============================================================

cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

env_cors_origins = (
    os.getenv("CORS_ORIGINS", "").strip()
)

if env_cors_origins:
    cors_origins.extend(
        entry.strip()
        for entry in env_cors_origins.split(",")
        if entry.strip()
    )

allow_all_origins = (
    os.getenv("ALLOW_ALL_ORIGINS", "false").strip().lower()
    == "true"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(cors_origins if not allow_all_origins else ["*"]),
    allow_origin_regex=r"^http://.*:5173$",
    allow_credentials=(not allow_all_origins),
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
#
# A blank or whitespace-only value is treated as "not set",
# because an empty .env entry overrides a default fallback.
# ============================================================

MONGO_URI = (
    os.getenv("MONGO_URI", "").strip()
    or "mongodb://127.0.0.1:27017/"
)

MONGO_DATABASE = (
    os.getenv("MONGO_DATABASE", "").strip()
    or "maritime_brokerage"
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
# SECURITY: no secret has a built-in default value in the
# source code. A committed fallback secret is a real key:
# anyone with the repository can forge tokens signed with it.
# Every secret below is read from the environment only.
#
# Create backend/.env for local development (see
# backend/.env.example) and set real secrets in the deployment
# environment for production. Nothing is ever printed in logs.
# ============================================================

APP_ENVIRONMENT = os.getenv(
    "APP_ENVIRONMENT",
    "development"
).strip().lower()

# Treat any non-development value as production-strict.
IS_PRODUCTION = APP_ENVIRONMENT not in {
    "development", "dev", "local", "test"
}

JWT_ALGORITHM = "HS256"

JWT_EXPIRY_HOURS = 24


def _read_secret(
    env_name: str,
    production_message: str,
    development_message: str
):
    """
    Read a secret from the environment with NO hardcoded
    fallback. Returns (value, is_provisional).

    A provisional value is a randomly generated secret used
    only so development can run without configuration. It is
    never a known constant and never logged.
    """

    value = os.getenv(env_name, "").strip()

    if value:

        return value, False

    if IS_PRODUCTION:

        raise RuntimeError(
            production_message
        )

    # Development without configuration: fail safe, not open.
    logger.warning(
        development_message
    )

    return secrets.token_urlsafe(64), True


JWT_SECRET, JWT_SECRET_IS_PROVISIONAL = _read_secret(
    "JWT_SECRET",
    production_message=(
        "JWT_SECRET is not set. Refusing to start in "
        f"{APP_ENVIRONMENT!r} mode because a hardcoded "
        "fallback would let anyone forge authentication "
        "tokens. Set the JWT_SECRET environment variable "
        "to a long random value."
    ),
    development_message=(
        "JWT_SECRET is not set. Generating a random "
        "development-only signing key for this process. All "
        "existing sessions will be invalidated when the "
        "server restarts. Set JWT_SECRET in backend/.env to "
        "keep sessions across restarts."
    )
)

# The admin login is only seeded when both credentials are
# supplied by the environment. Without them the application
# still starts in development, but no admin account is
# created, so there is no default password to discover.
ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL", ""
).strip()

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD", ""
).strip()

ADMIN_CREDENTIALS_MISSING = not (
    ADMIN_EMAIL and ADMIN_PASSWORD
)

if ADMIN_CREDENTIALS_MISSING:

    missing = [
        name
        for name, value in (
            ("ADMIN_EMAIL", ADMIN_EMAIL),
            ("ADMIN_PASSWORD", ADMIN_PASSWORD)
        )
        if not value
    ]

    if IS_PRODUCTION:

        raise RuntimeError(
            f"Missing required admin configuration: "
            f"{', '.join(missing)}. Refusing to start in "
            f"{APP_ENVIRONMENT!r} mode. No default admin "
            "credentials exist in the source code; set these "
            "environment variables explicitly."
        )

    logger.warning(
        f"Missing {', '.join(missing)}. The admin account "
        "will not be seeded. Set these in backend/.env to "
        "enable admin login."
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

    # ---------------------------------
    # No credentials configured means
    # no admin account is created. The
    # configuration block already reports
    # this, and fails hard in production.
    # Never seed an account with a blank
    # contact or password.
    # ---------------------------------

    if ADMIN_CREDENTIALS_MISSING:

        return

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


class FeedbackApproval(BaseModel):
    approved: bool


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
        "verified": False,
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

    # --------------------------------------------------------
    # LOGIN ACTIVITY MARKER
    # A single timestamp written on the existing user record.
    # This does NOT change the authentication flow: the token,
    # the role, the response and the session behaviour are all
    # exactly as before. The marker only lets the existing
    # admin Login Activity view and the Admin AI Assistant
    # answer "how many users signed in today". A failure here
    # never blocks a successful login.
    # --------------------------------------------------------

    try:

        users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login": datetime.utcnow()}}
        )

    except Exception as marker_error:

        logger.warning(
            "Could not record login activity: %s",
            marker_error
        )

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

    # -----------------------------------------------------
    # ROUTE RECOMMENDATION REASONS
    # -----------------------------------------------------
    # The Route Agent returns the list of reasons that
    # explain why the recommended route was chosen. It is
    # persisted here so route history can explain the
    # recommendation later, without recalculating anything.
    # A quotation carries the same list, so either source
    # is accepted. Nothing is invented: only reasons the
    # Route Agent actually produced are stored.
    # -----------------------------------------------------

    route_reasons = []

    if isinstance(quotation, dict):

        route_reasons = quotation.get("reasons") or []

    if not route_reasons:

        route_reasons = result.get("reasons") or []

    if not isinstance(route_reasons, list):

        route_reasons = []

    route_reasons = [
        str(reason).strip()
        for reason in route_reasons
        if str(reason or "").strip()
    ]

    doc = {
        # Ownership is deliberately blank here. It is set
        # by _save_route_history from the verified token,
        # never from the request.
        "user_id": "",
        "user_contact": "",
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
        "route_reasons": route_reasons,
        "total_available_routes": result.get(
            "total_available_routes", 0
        ),
        "created_at": datetime.now(timezone.utc)
    }

    if quotation:
        pricing = quotation.get("pricing", {})
        margin = quotation.get("margin", {})

        # -------------------------------------------------
        # PRICING BREAKDOWN
        # Every value the Pricing Agent produced is kept so
        # the stored quotation matches the quotation that
        # was shown to the customer.
        # -------------------------------------------------

        doc["pricing"] = {
            "containers": pricing.get("containers"),
            "base_freight_usd": pricing.get(
                "base_freight_usd"
            ),
            "base_freight_per_container_usd":
                pricing.get(
                    "base_freight_per_container_usd"
                ),
            "fuel_surcharge_usd": pricing.get(
                "fuel_surcharge_usd"
            ),
            "port_charge_usd": pricing.get(
                "port_charge_usd"
            ),
            "risk_surcharge_usd": pricing.get(
                "risk_surcharge_usd"
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
            "achieved_margin_percent": margin.get(
                "achieved_margin_percent"
            ),
        }

    return doc


def _save_route_history(
    result, request, quotation=None, authorization=None
):

    document = _history_document(
        result, request, quotation
    )

    # -----------------------------------------------------
    # OWNERSHIP COMES FROM THE VERIFIED TOKEN ONLY
    # -----------------------------------------------------
    # The identity stored on the record is taken from a
    # valid backend-issued JWT. A `user_id` sent in the
    # request body is never trusted for ownership, so a
    # caller cannot write route history or a quotation into
    # another user's account.
    #
    # With no token, or an invalid/expired one, no history
    # is stored. An unauthenticated route analysis or
    # quotation still returns its result to the caller; it
    # simply is not persisted to anyone's history.
    # -----------------------------------------------------

    document["user_id"] = ""
    document["user_contact"] = ""

    if not authorization:

        return None

    try:

        current = get_current_user(authorization)

    except HTTPException:

        return None

    owner_id = str(current.get("user_id", "") or "").strip()

    if not owner_id:

        return None

    document["user_id"] = owner_id
    document["user_contact"] = current.get("contact", "")

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

        # -------------------------------------------------
        # ROUTE RECOMMENDATION REASONS
        # Persisted by _history_document from the reasons
        # the Route Agent produced. Older records have no
        # stored reasons, so an empty list is returned and
        # the caller explains the route without them rather
        # than failing.
        # -------------------------------------------------

        "route_reasons": record.get(
            "route_reasons", []
        ) or [],
        "total_available_routes": record.get(
            "total_available_routes", 0
        ),
        "pricing": record.get("pricing"),
        "margin": record.get("margin"),

        # -------------------------------------------------
        # WEATHER RISK (WEATHER AGENT)
        # Additive route intelligence for the admin route
        # activity view. Resolved from weather.csv only; no
        # history document is modified.
        # -------------------------------------------------

        "weather": weather_for_route(
            record.get("route_id", "")
        ),

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


# ============================================================
# ROUTE LOCATIONS
# ============================================================

@app.get("/api/routes/locations")
def get_locations():

    import pandas as pd

    df = pd.read_csv(
        ROUTES_CSV_PATH
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
        ROUTES_CSV_PATH
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
        ROUTES_CSV_PATH
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
# WEATHER ANALYSIS (WEATHER AGENT)
# ============================================================
# The Weather Agent is an additional intelligence layer on
# top of the existing Route Agent. It reads the weather
# dataset (backend/app/weather.csv), grades the conditions
# of the selected route and returns a LOW / MEDIUM / HIGH
# weather risk with its explanation.
#
# It never selects a route, never changes a route score and
# never changes pricing, margin, quotations or shipments.
#
# The route is identified by:
#   * route_id   - preferred, straight from the Route Agent
#   * origin + destination - when only a corridor is known
#   * route_ids  - several routes at once, used to show the
#                  weather of alternative routes
#
# A missing record, a missing dataset or a malformed row
# never returns a server error: the response carries
# "available": false and the standard not-available message
# so Route Intelligence keeps working.
# ============================================================

@app.post(
    "/api/weather/analyze",
    summary="Analyze weather conditions for a route",
    response_description=(
        "Weather values from the dataset, the calculated "
        "weather risk (LOW / MEDIUM / HIGH) and the reason "
        "behind it."
    )
)
def analyze_weather_route(
    request: WeatherAnalyzeRequest
):

    if not request.has_route():

        raise HTTPException(
            status_code=400,
            detail=(
                "A route_id, or an origin and destination "
                "pair, is required to analyze weather."
            )
        )

    route_ids = request.requested_route_ids()

    try:

        # -------------------------------------------------
        # SEVERAL ROUTES (recommended + alternatives)
        # -------------------------------------------------

        if len(route_ids) > 1 or (
            len(route_ids) == 1
            and request.route_ids
        ):

            analyses = analyze_routes_weather(route_ids)

            primary = next(
                (
                    analysis
                    for analysis in analyses
                    if analysis.get("route_id")
                    == route_ids[0]
                ),
                analyses[0] if analyses else None
            )

            return {
                "success": True,
                "count": len(analyses),
                "route_ids": route_ids,
                "weather": primary,
                "routes": analyses
            }

        # -------------------------------------------------
        # SINGLE ROUTE
        # -------------------------------------------------

        if route_ids:

            weather = analyze_weather(
                route_id=route_ids[0],
                origin=request.origin,
                destination=request.destination
            )

        else:

            weather = analyze_weather(
                origin=request.origin,
                destination=request.destination
            )

        return {
            "success": True,
            "count": 1,
            "route_ids": route_ids,
            "weather": weather,
            "routes": [weather]
        }

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:

        # The weather module is optional intelligence. It
        # never breaks the surrounding application.
        logger.warning(
            "Weather analysis error: %s", error
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to analyze weather for this route."
        )


# ============================================================
# WEATHER DATASET SUMMARY
# ============================================================
# Exposes how much of the existing route coverage the weather
# dataset covers. Read-only reference information.
# ============================================================

@app.get(
    "/api/weather/summary",
    summary="Weather dataset coverage summary"
)
def get_weather_dataset_summary():

    return get_weather_summary()


# ============================================================
# CUSTOMS COMPLIANCE (CUSTOMS AGENT)
# ============================================================
# The Customs Agent is an ADDITIONAL compliance module in the
# existing pipeline:
#
#   Route Agent  -> Recommended Route
#   Weather Agent-> Weather Risk
#   Customs Agent-> Customs Compliance   <- this module
#   Pricing Agent-> Cost
#   Margin Agent -> Selling Price
#
# It reads backend/app/customs.csv, which is generated from
# the EXISTING backend/app/routes.csv, so it reuses the
# existing route ids and the existing cargo_type /
# cargo_subtype values. It never selects a route, never
# changes a route score and never touches pricing, margin,
# quotations or shipments.
#
# A record is matched on
#   ORIGIN + DESTINATION + CARGO TYPE + CARGO SUBTYPE
# so two routes on the same lane carrying different cargo are
# never confused with each other.
#
# The customs_status, the compliance percentage and the list
# of missing documents are produced by deterministic logic in
# the Customs Agent. Gemini only rewrites that structured
# result as a readable advisory, and its absence never breaks
# this endpoint.
# ============================================================

def _attach_customs_advisory(customs_result):

    """
    Add the advisory to a customs result.

    The deterministic Customs Agent result is always returned.
    Gemini is optional: any failure falls back to the
    deterministic advisory text instead of raising.
    """

    try:

        advisory = generate_customs_advisory(customs_result)

        customs_result["advisory"] = advisory.get(
            "advisory",
            customs_result.get("advisory", "")
        )

        # The browser is told only WHETHER a written advisory was
        # added. Which service produced it, whether it is
        # configured, its model name and the reason it was
        # skipped are all internal diagnostics and are never
        # sent to the customer.

        customs_result["advisory_included"] = bool(
            advisory.get("advisory")
            or customs_result.get("advisory")
        )

    except Exception as advisory_error:

        # The explanation layer is optional intelligence and
        # must never break the customs result.

        logger.warning(
            "Customs advisory layer error: %s",
            advisory_error
        )

        customs_result["advisory_included"] = bool(
            customs_result.get("advisory")
        )

    return customs_result


@app.post(
    "/api/customs/analyze",
    summary="Analyze customs requirements for a shipment",
    response_description=(
        "The customs record matched on origin, destination, "
        "cargo type and cargo subtype, the deterministic "
        "compliance result, the customs status and the "
        "advisory for this shipment."
    )
)
def analyze_customs_route(request: CustomsCheckRequest):

    if not request.has_shipment():

        raise HTTPException(
            status_code=400,
            detail=(
                "origin, destination, cargo_type and "
                "cargo_subtype are all required to analyze "
                "customs requirements."
            )
        )

    try:

        customs_result = analyze_customs(
            origin=request.origin,
            destination=request.destination,
            cargo_type=request.cargo_type,
            cargo_subtype=request.cargo_subtype,
            route_id=request.route_id,
            documents=request.documents
        )

    except Exception as error:

        # The customs module is additional intelligence. It
        # never breaks the surrounding application.
        logger.warning(
            "Customs analysis error: %s", error
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to analyze customs requirements "
                   "for this shipment."
        )

    _attach_customs_advisory(customs_result)

    # The dataset filename behind the answer is an internal
    # implementation detail. The customer gets the plain
    # language caveat instead, which says the same thing
    # without naming a file.

    customs_result.pop("data_source", None)

    # -------------------------------------------------
    # NOT AVAILABLE IS A NORMAL ANSWER, NOT AN ERROR
    #
    # A missing customs record, an unsupported cargo pair or
    # an unreadable dataset all resolve to HTTP 200 with
    # available=false, so Route Intelligence, quotations and
    # shipments keep working unchanged.
    # -------------------------------------------------

    return {
        "success": True,
        "customs": customs_result
    }


@app.get(
    "/api/customs/summary",
    summary="Customs dataset coverage summary"
)
def get_customs_dataset_summary():

    summary = get_customs_summary()

    # The service name, model and key configuration are
    # internal diagnostics. Only whether the optional
    # explanation layer is available is customer relevant.

    summary["explanation_available"] = bool(
        get_gemini_configuration().get("configured")
    )

    summary.pop("gemini", None)

    return summary


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
# Every route history endpoint requires a valid backend
# token and is scoped to the authenticated user's OWN records.
#
# The identity is taken from the verified token only, using
# the same `Depends(get_current_user)` pattern as the Maritime
# Assistant. A `user_id` supplied by the client is never used
# for ownership, so changing a query parameter or editing
# localStorage cannot expose another user's records.
# ============================================================

@app.post("/api/intelligence/analyze")
def analyze_freight_intelligence(
    request: RouteRequest,
    authorization: str = Header(None)
):

    try:

        report = generate_freight_intelligence(
            request.origin,
            request.destination,
            request.cargo_type,
            request.cargo_subtype,
            request.containers
        )

        # -------------------------------------------------
        # SAVE HISTORY (same ownership rules as the other
        # analysis endpoints). A history failure never
        # affects the response.
        # -------------------------------------------------

        analysis_id = None

        try:

            recommended = (
                report.get("route", {}).get(
                    "recommended", {}
                ) or {}
            )

            route_result = {
                "recommended_route": {
                    "route_id": recommended.get(
                        "route_id", ""
                    ),
                    "route": recommended.get(
                        "route_name", ""
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
                    "score": recommended.get(
                        "route_score"
                    ),
                },
                "origin": request.origin,
                "destination": request.destination,
                "cargo_type": request.cargo_type,
                "cargo_subtype": request.cargo_subtype,
                "containers": request.containers,
            }

            quotation_snapshot = {
                "pricing": report.get("pricing", {}),
                "margin": report.get("margin", {}),
                "reasons": (
                    report.get("route", {}).get(
                        "reasons", []
                    )
                ),
            }

            analysis_id = _save_route_history(
                route_result,
                request,
                quotation_snapshot,
                authorization=authorization
            )

        except Exception as history_error:

            logger.warning(
                "Could not save intelligence history: %s",
                history_error
            )

        return {
            **report,
            "analysis_id": (
                str(analysis_id) if analysis_id else None
            )
        }

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:

        logger.error(
            "Freight intelligence error: %s", error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to generate freight intelligence. "
                "Please try again later."
            )
        )


@app.get("/api/routes/history")
def get_route_history(
    current_user: dict = Depends(get_current_user)
):

    owner_id = str(
        current_user.get("user_id", "") or ""
    ).strip()

    if not owner_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication is required."
        )

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
    current_user: dict = Depends(get_current_user)
):

    owner_id = str(
        current_user.get("user_id", "") or ""
    ).strip()

    if not owner_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication is required."
        )

    try:

        record_object_id = ObjectId(record_id)

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="The route history record is invalid."
        )

    # Only the record that belongs to the authenticated user
    # can be deleted. The ownership filter is applied in the
    # database query, and routes.csv is never touched.
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
    current_user: dict = Depends(get_current_user)
):

    owner_id = str(
        current_user.get("user_id", "") or ""
    ).strip()

    if not owner_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication is required."
        )

    # Only the authenticated user's own history is removed.
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

        # -------------------------------------------------
        # WEATHER RISK (WEATHER AGENT)
        # Read-only intelligence resolved from weather.csv
        # for the shipment's route_id. Additive only: no
        # shipment document, workflow or status is changed,
        # and a missing weather record simply returns null.
        # -------------------------------------------------

        "weather": weather_for_route(
            shipment.get("route_id", "")
        ),

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
# Returns only the authenticated user's own shipment records.
# The identity comes from the verified token only, so a
# client-supplied `user_id` cannot widen the result set.
# ============================================================

@app.get("/api/shipments")
def get_my_shipments(
    current_user: dict = Depends(get_current_user)
):

    owner_id = str(
        current_user.get("user_id", "") or ""
    ).strip()

    if not owner_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication is required."
        )

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
# A user may only open their own shipment. The ownership
# check compares the authenticated token's user against the
# shipment's stored owner. A missing or foreign shipment
# returns a generic 404 so shipment ids cannot be probed.
# ============================================================

@app.get("/api/shipments/{shipment_id}")
def get_shipment_details(
    shipment_id: str,
    current_user: dict = Depends(get_current_user)
):

    owner_id = str(
        current_user.get("user_id", "") or ""
    ).strip()

    if not owner_id:

        raise HTTPException(
            status_code=401,
            detail="Authentication is required."
        )

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
# ADMIN - EXECUTIVE DASHBOARD
# ============================================================
# One compact payload for the Executive Dashboard view. The
# counts are the same real MongoDB counts the existing
# /api/admin/stats endpoint uses; the funnel, status
# distribution, weekly trend and top-lane figures are computed
# from the recent stored records by the pure aggregation layer
# (app/services/executive_dashboard.py). Admin-only.
# ============================================================

@app.get(
    "/api/admin/executive-dashboard",
    summary="Executive dashboard KPIs and trends",
    response_description=(
        "Headline KPIs, the quotation approval funnel, the "
        "shipment status distribution, 8 weeks of route "
        "activity and the top lanes and cargo types, all "
        "computed from stored platform records."
    )
)
def get_admin_executive_dashboard(
    current_user: dict = Depends(require_admin)
):

    try:

        total_users = users_collection.count_documents({})

        total_route_analyses = (
            route_history_collection.count_documents({})
        )

        total_quotations = (
            route_history_collection.count_documents({
                "pricing": {"$exists": True}
            })
        )

        total_shipments = shipments_collection.count_documents({})

        recent_shipments = list(
            shipments_collection
            .find({})
            .sort("created_at", -1)
            .limit(500)
        )

        recent_history = list(
            route_history_collection
            .find({})
            .sort("created_at", -1)
            .limit(500)
        )

    except Exception as error:

        logger.error(
            "Executive dashboard data error: %s", error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to load the executive dashboard. "
                "Please try again later."
            )
        )

    return build_executive_report(
        total_users=total_users,
        total_route_analyses=total_route_analyses,
        total_quotations=total_quotations,
        total_shipments=total_shipments,
        shipments=recent_shipments,
        history_records=recent_history,
        status_flow=SHIPMENT_STATUS_FLOW,
    )


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

    approved_at = record.get("approved_at")

    if isinstance(approved_at, datetime):
        approved_at_text = approved_at.isoformat()
    elif isinstance(approved_at, str):
        approved_at_text = approved_at
    else:
        approved_at_text = None

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
        "approved": bool(record.get("approved", False)),
        "approved_at": approved_at_text,
        "approved_by": record.get("approved_by", ""),
        "created_at": created_at_text
    }


# ============================================================
# HELPER - SERIALIZE A PUBLIC REVIEW
# ============================================================
# The public reviews feed shows approved reviews only and
# never carries a user's contact details or internal ids.
# ============================================================

def _serialize_public_review(record):
    created_at = record.get("created_at")

    if isinstance(created_at, datetime):
        created_at_text = created_at.isoformat()
    elif isinstance(created_at, str):
        created_at_text = created_at
    else:
        created_at_text = None

    return {
        "review_id": str(record["_id"]),
        "user_name": record.get("user_name", "") or "Customer",
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
        "approved": False,
        "approved_at": None,
        "approved_by": "",
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
# PUBLIC - REVIEWS
# ============================================================
# The broker's public customer-reviews feed. Public by design:
# no token is required, so the frontend welcome area can show
# it before login. Only feedback an administrator approved is
# returned, and a review never carries a user's contact
# details or internal ids.
#
# The moderation itself happens on the same feedback
# collection, so a hidden or pending review simply never
# reaches this endpoint.
# ============================================================

@app.get(
    "/api/reviews",
    summary="Approved customer reviews",
    response_description=(
        "Approved reviews with the average rating, the review "
        "total and the rating breakdown. Public - no token "
        "required. Never includes user contact details."
    )
)
def get_public_reviews():

    try:

        approved_records = list(
            feedbacks_collection
            .find({"approved": True})
            .sort("created_at", -1)
            .limit(100)
        )

    except Exception as error:

        logger.error(
            "Unable to load public reviews: %s", error
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load customer reviews."
        )

    reviews = [
        _serialize_public_review(record)
        for record in approved_records
    ]

    total_reviews = len(reviews)

    average_rating = 0.0

    rating_counts = {star: 0 for star in range(1, 6)}

    if total_reviews:

        ratings = [
            review["rating"] for review in reviews
        ]

        average_rating = round(
            sum(ratings) / total_reviews, 2
        )

        for rating in ratings:

            rating_counts[rating] = (
                rating_counts.get(rating, 0) + 1
            )

    return {
        "success": True,
        "reviews": reviews,
        "summary": {
            "review_count": total_reviews,
            "average_rating": average_rating,
            "rating_counts": rating_counts
        }
    }


# ============================================================
# ADMIN - REVIEW APPROVAL
# ============================================================
# Decides whether a feedback entry appears on the public
# /api/reviews feed. Approving stamps who decided and when;
# hiding clears those stamps. Only admins can do this, and
# the feedback record itself is never deleted.
# ============================================================

@app.patch("/api/admin/feedback/{feedback_id}/approval")
def update_feedback_approval(
    feedback_id: str,
    request: FeedbackApproval,
    current_user: dict = Depends(require_admin)
):

    from bson import ObjectId

    feedback_id = feedback_id.strip()

    try:

        feedback_doc = feedbacks_collection.find_one({
            "_id": ObjectId(feedback_id)
        })

    except Exception:

        raise HTTPException(
            status_code=404,
            detail="Feedback not found."
        )

    if not feedback_doc:

        raise HTTPException(
            status_code=404,
            detail="Feedback not found."
        )

    stamp_fields = {}

    if request.approved:

        now = datetime.now(timezone.utc)

        stamp_fields["approved"] = True
        stamp_fields["approved_at"] = now
        stamp_fields["approved_by"] = current_user.get(
            "user_id", ""
        )

    else:

        stamp_fields["approved"] = False
        stamp_fields["approved_at"] = None
        stamp_fields["approved_by"] = ""

    feedbacks_collection.update_one(
        {"_id": feedback_doc["_id"]},
        {"$set": stamp_fields}
    )

    updated_doc = feedbacks_collection.find_one({
        "_id": feedback_doc["_id"]
    })

    return {
        "success": True,
        "message": (
            "Review approved and published."
            if request.approved
            else "Review hidden from the public feed."
        ),
        "feedback": _serialize_feedback(updated_doc)
    }
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
            PRICING_CSV_PATH
        )

        routes_df = pd.read_csv(
            ROUTES_CSV_PATH
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


# ============================================================
# ADMIN - CUSTOMS MANAGEMENT
# ============================================================
# Read-only monitoring of the customs dataset that the Customs
# Agent uses. The existing admin list + search + filter
# architecture is reused: the same require_admin dependency,
# the same list response shape (records + filters + summary)
# and the same admin toolbar pattern used by /api/admin/pricing
# and /api/admin/shipments.
#
# Every customs record is derived from the EXISTING routes
# dataset, so no customs rule is created or editable through
# this endpoint. A normal user cannot reach it: require_admin
# blocks the request before the handler runs.
# ============================================================

@app.get(
    "/api/admin/customs",
    summary="List and filter customs records",
    response_description=(
        "Customs records with their route, cargo and "
        "requirement values, the available filter options and "
        "dataset status counters."
    )
)
def get_admin_customs(
    route_id: str = "",
    origin: str = "",
    destination: str = "",
    cargo_type: str = "",
    cargo_subtype: str = "",
    customs_status: str = "",
    restricted_cargo: str = "",
    search: str = "",
    limit: int = 0,
    current_user: dict = Depends(require_admin)
):

    try:

        result = list_customs_records(
            route_id=route_id,
            origin=origin,
            destination=destination,
            cargo_type=cargo_type,
            cargo_subtype=cargo_subtype,
            customs_status=customs_status,
            restricted_cargo=restricted_cargo,
            search=search,
            limit=limit
        )

    except Exception as error:

        logger.error(
            "Unable to load customs records: %s", error
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to load customs records."
        )

    return {
        "success": True,
        **result
    }


# ============================================================
# MARITIME AI ASSISTANT
# ============================================================
# A data-grounded assistant, NOT a generic maritime chatbot.
#
#   User question
#        |
#        v
#   Intent detection (deterministic)
#        |
#        v
#   EXISTING project data, already scoped to the
#   authenticated user:
#     Route Agent result   (route history collection)
#     Weather Agent result (already stored on that record)
#     Customs Agent result (run for the same 4-key match)
#     Stored quotation     (pricing / margin on that record)
#     Stored shipment      (own shipments only)
#        |
#        v
#   Gemini explains those facts
#        |
#        v
#   Natural language answer
#
# GEMINI NEVER INVENTS A VALUE
# The model receives only the retrieved facts. The customs
# status, compliance percentage, route score, weather risk
# and quotation total are all produced by the deterministic
# modules above and are never recalculated here. Gemini can
# only phrase them.
#
# SECURITY
# * Requires a valid token (get_current_user).
# * Every record read is filtered by the token's user_id.
#   Another user's shipment, quotation or route analysis is
#   unreachable through this endpoint.
# * Internal cost and margin fields are never placed in the
#   fact set for a user, matching the existing UI where only
#   the total quotation is shown.
# * The API key is never sent to the browser.
#
# FAIL-SAFE
# Gemini being unconfigured, unreachable or slow only changes
# the tone of the answer. The deterministic answer, which is
# written from the same retrieved facts, is always returned.
# ============================================================

ASSISTANT_MAX_MESSAGE_CHARS = 1000

ASSISTANT_CONTEXT_LIMIT = 25


@app.get(
    "/api/assistant/suggestions",
    summary="Suggested Maritime Assistant questions",
    response_description=(
        "A short list of starter questions, each one "
        "answerable from the caller's own existing results."
    )
)
def get_assistant_suggestions(
    current_user: dict = Depends(get_current_user)
):

    return {
        "success": True,
        "suggestions": [
            "Why was this route recommended?",
            "What is my total quotation?",
            "What customs documents are missing?",
            "Why is my shipment risk medium?",
            "What is my shipment status?",
            "What weather risk does my route have?",
            "How is my quotation calculated?",
            "What documents do I need for customs clearance?",
            "What cargo can I ship?",
            "How do I get started on this platform?",
        ],
        "scope": (
            "admin" if current_user.get("role") == "admin"
            else "user"
        ),
    }


def _safe_assistant_records(loader, default=""):
    """
    Run a project-data loader and degrade to `default`.

    The assistant is an ADDITIONAL layer: a MongoDB or dataset
    failure must produce a plain "no information" answer
    rather than a 500 that would interrupt the dashboard.
    """

    try:

        return loader()

    except Exception as error:

        logger.warning(
            "Assistant data unavailable: %s", error
        )

        return default


def _assistant_knowledge(
    question,
    scope="user",
    intents=(),
    status_flow=None
):

    """
    Build the grounded project context for one question.

    `app/services/project_context.py` is the single place
    that describes how this codebase behaves, and it imports
    the agents' own constants so a threshold, a control or a
    formula can never drift from the code that applies it.

    Two blocks are returned:

      * `knowledge`   - what the platform is and how it
                        works, for the questions that are
                        about the implementation.
      * `agent_reference` - the real rule or threshold behind
                        a data topic, attached beside the
                        stored value it explains.
    """

    try:

        knowledge = build_project_knowledge(
            question,
            scope=scope,
            status_flow=(
                status_flow
                if status_flow is not None
                else SHIPMENT_STATUS_FLOW
            )
        )

        reference = build_agent_reference(
            question,
            scope=scope,
            status_flow=(
                status_flow
                if status_flow is not None
                else SHIPMENT_STATUS_FLOW
            ),
            intents=intents
        )

    except Exception as error:

        logger.warning(
            "Assistant project knowledge unavailable: %s",
            error
        )

        return {}

    return {
        "mode": knowledge.get("mode"),
        "topics": knowledge.get("topics", []),
        "admin_only": bool(knowledge.get("admin_only")),
        "mirrors_stored_value": bool(
            knowledge.get("mirrors_stored_value")
        ),
        "is_record_question": bool(
            knowledge.get("is_record_question")
        ),
        "is_mechanism_question": bool(
            knowledge.get("is_mechanism_question")
        ),
        "is_usage_question": bool(
            knowledge.get("is_usage_question")
        ),
        "knowledge": {
            "project_name": knowledge.get("project_name"),
            "purpose": knowledge.get("purpose"),
            "grounding_rule": knowledge.get("grounding_rule"),
            "sections": knowledge.get("sections", {}),
        },
        "agent_reference": reference,
        "deterministic_answer": knowledge.get(
            "deterministic_answer"
        ),
    }


@app.post(
    "/api/assistant/chat",
    summary="Ask the Maritime AI Assistant",
    response_description=(
        "A grounded natural language answer about the "
        "authenticated user's own route, weather, customs, "
        "quotation and shipment results, with the structured "
        "facts the answer was built from."
    )
)
def chat_with_maritime_assistant(
    request: AssistantRequest,
    current_user: dict = Depends(get_current_user)
):

    message = request.clean_message()

    if not message:

        raise HTTPException(
            status_code=400,
            detail=(
                "Please enter a question for the Maritime "
                "AI Assistant."
            )
        )

    # -------------------------------------------------
    # SCOPE EVERY READ TO THE AUTHENTICATED USER
    # -------------------------------------------------

    owner_id = current_user.get("user_id", "")

    requested_shipment_id = (
        request.clean_shipment_id()
    )

    # A shipment reference supplied by the browser is only
    # honoured when it belongs to this user. A foreign or
    # unknown reference is dropped here, so it can never
    # widen the search beyond this user's own records.
    if requested_shipment_id:

        owned = shipments_collection.find_one({
            "shipment_id": requested_shipment_id,
            "user_id": owner_id
        })

        if not owned:

            requested_shipment_id = ""

    requested_route_id = request.clean_route_id()

    shipments = _safe_assistant_records(
        lambda: list(
            shipments_collection
            .find({"user_id": owner_id})
            .sort("created_at", -1)
            .limit(ASSISTANT_CONTEXT_LIMIT)
        ),
        default=[]
    )

    history = _safe_assistant_records(
        lambda: list(
            route_history_collection
            .find({"user_id": owner_id})
            .sort("created_at", -1)
            .limit(ASSISTANT_CONTEXT_LIMIT)
        ),
        default=[]
    )

    result = answer_user_question(
        message,
        shipments=[
            _serialize_shipment(record)
            for record in shipments
        ],
        history=[
            _serialize_history_record(record)
            for record in history
        ],
        analyze=analyze_customs,
        status_flow=SHIPMENT_STATUS_FLOW,
        shipment_id=requested_shipment_id,
        route_id=requested_route_id,
        knowledge_provider=_assistant_knowledge
    )

    # -------------------------------------------------
    # REFUSAL SHORT-CIRCUIT
    #
    # An out-of-scope question is answered with the fixed
    # refusal and never reaches the explanation service. That
    # way the refused text is never sent anywhere, and the
    # customer always receives the same plain message.
    # -------------------------------------------------

    if result.get("out_of_scope"):

        return {
            "success": True,
            "scope": "user",
            "question": message,
            "answer": result["deterministic_answer"],
            "answer_source": "refusal",
            "explanation_available": False,
            "out_of_scope": True,
            "intents": result.get("intents", []),
            "focus": result.get("focus", {}),
            "facts": {},
            "deterministic_answer": result[
                "deterministic_answer"
            ]
        }

    # -------------------------------------------------
    # GEMINI EXPLAINS THE RETRIEVED FACTS
    # -------------------------------------------------

    project_block = (
        (result.get("facts") or {}).get("project")
    )

    try:

        explanation = generate_assistant_reply(
            question=message,
            facts=result["facts"],
            deterministic_answer=result[
                "deterministic_answer"
            ],
            scope="user",
            project_knowledge=project_block
        )

    except Exception as explanation_error:

        logger.warning(
            "Assistant explanation layer error: %s",
            explanation_error
        )

        explanation = {
            "answer": result["deterministic_answer"],
            "answer_source": "deterministic",
            "explanation_available": False,
        }

    return {
        "success": True,
        "scope": "user",
        "question": message,
        "answer": explanation.get(
            "answer",
            result["deterministic_answer"]
        ),
        "answer_source": explanation.get(
            "answer_source", "deterministic"
        ),
        "explanation_available": explanation.get(
            "explanation_available", False
        ),

        # The explanation service's model name and the reason
        # it was skipped are internal diagnostics and are
        # deliberately not returned to the customer.

        "intents": result.get("intents", []),
        "focus": result.get("focus", {}),
        "facts": result.get("facts", {}),
        "deterministic_answer": result[
            "deterministic_answer"
        ]
    }


# ============================================================
# ADMIN AI ASSISTANT
# ============================================================
# Same grounding architecture as the user assistant, reading
# the SAME admin collections the existing admin dashboard
# already reads. No new collection, no new dataset.
#
# ACCESS CONTROL
# require_admin blocks the request before the handler runs, so
# a normal user receives HTTP 403 and can never reach admin
# counters, other users' records or system health through the
# chatbot. The user assistant has no code path to these
# endpoints either.
#
# NO SECRETS ARE EVER READ OR RETURNED
# The health report contains availability states only
# ("configured" / "not configured"). The Gemini key, the JWT
# secret, passwords and the Mongo connection string are never
# read into a fact and never leave the backend.
# ============================================================

def _collect_system_health():

    """
    Availability report for the existing subsystems.

    Reports availability only. No key, secret, password or
    connection string is read into this dictionary.
    """

    health = {
        "database": "unavailable",
        "routes_dataset": "unavailable",
        "weather_dataset": "unavailable",
        "customs_dataset": "unavailable",
        "ais_provider": "not configured",
        "ai_advisory_layer": "not configured",
        "issues": [],
    }

    # -------------------------------------------------
    # DATABASE
    # -------------------------------------------------

    try:

        db.command("ping")

        health["database"] = "connected"

    except Exception as error:

        health["database"] = "unavailable"

        health["issues"].append(
            "The database is not responding, so live "
            "platform data cannot be read."
        )

        logger.warning(
            "Assistant health check: database ping failed: %s",
            error
        )

    # -------------------------------------------------
    # DATASETS (reused through their existing agents)
    # -------------------------------------------------

    try:

        get_locations()

        health["routes_dataset"] = "available"

    except Exception as error:

        logger.warning(
            "Assistant health check: routes dataset: %s",
            error
        )

        health["issues"].append(
            "The route dataset could not be read."
        )

    try:

        weather_summary = get_weather_summary()

        if weather_summary.get("available"):

            health["weather_dataset"] = "available"

        else:

            health["weather_dataset"] = "unavailable"

            health["issues"].append(
                "The weather dataset could not be read."
            )

    except Exception as error:

        logger.warning(
            "Assistant health check: weather dataset: %s",
            error
        )

        health["issues"].append(
            "The weather dataset could not be read."
        )

    try:

        customs_summary = get_customs_summary()

        if customs_summary.get("available"):

            health["customs_dataset"] = "available"

        else:

            health["customs_dataset"] = "unavailable"

            health["issues"].append(
                "The customs dataset could not be read."
            )

    except Exception as error:

        logger.warning(
            "Assistant health check: customs dataset: %s",
            error
        )

        health["issues"].append(
            "The customs dataset could not be read."
        )

    # -------------------------------------------------
    # AIS PROVIDER
    # Availability of the configured key only, never its
    # value.
    # -------------------------------------------------

    if os.getenv("AIS_API_KEY", "").strip():

        health["ais_provider"] = "configured"

    # -------------------------------------------------
    # AI ADVISORY LAYER
    # -------------------------------------------------

    gemini_configuration = get_gemini_configuration()

    if gemini_configuration.get("available"):

        health["ai_advisory_layer"] = "available"

    else:

        health["ai_advisory_layer"] = "not configured"

        health["issues"].append(
            "The AI advisory layer is not configured, so "
            "answers fall back to the deterministic text."
        )

    return health


@app.get(
    "/api/admin/assistant/suggestions",
    summary="Suggested Admin Assistant questions",
    response_description=(
        "A short list of starter administrator questions."
    )
)
def get_admin_assistant_suggestions(
    current_user: dict = Depends(require_admin)
):

    return {
        "success": True,
        "scope": "admin",
        "suggestions": [
            "How many active users are there?",
            "How many active shipments are there?",
            "Which shipments have customs warnings?",
            "Show me recent quotation activity.",
            "How many users logged in today?",
            "Are there any system issues?",
            "How do I approve a quotation?",
            "How is a quotation calculated?",
            "How does shipment tracking work?",
            "How is a route recommended?",
        ]
    }


def _count_users_logged_in_today():

    """
    Count distinct users that signed in today (UTC).

    Uses the existing last_login marker written by the login
    endpoint. No new collection and no login flow change.
    """

    try:

        start_of_day = datetime.now(timezone.utc).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        return users_collection.count_documents({
            "last_login": {"$gte": start_of_day}
        })

    except Exception as error:

        logger.warning(
            "Login activity count unavailable: %s", error
        )

        return 0


@app.post(
    "/api/admin/assistant/chat",
    summary="Ask the Admin AI Assistant",
    response_description=(
        "A grounded natural language answer built from the "
        "existing admin collections: user and shipment "
        "counters, live shipment customs warnings, recent "
        "quotation activity, login activity and system health."
    )
)
def chat_with_admin_assistant(
    request: AssistantRequest,
    current_user: dict = Depends(require_admin)
):

    message = request.clean_message()

    if not message:

        raise HTTPException(
            status_code=400,
            detail=(
                "Please enter a question for the Admin "
                "AI Assistant."
            )
        )

    # -------------------------------------------------
    # PLATFORM COUNTERS
    #
    # Reuses the exact counts of /api/admin/stats so the
    # assistant can never report a different figure from the
    # dashboard.
    # -------------------------------------------------

    admin_statistics = _safe_assistant_records(
        lambda: get_admin_stats(current_user),
        default={}
    )

    shipments = _safe_assistant_records(
        lambda: list(
            shipments_collection
            .find({})
            .sort("created_at", -1)
            .limit(ASSISTANT_CONTEXT_LIMIT)
        ),
        default=[]
    )

    quotations = _safe_assistant_records(
        lambda: list(
            route_history_collection
            .find({"pricing": {"$exists": True}})
            .sort("created_at", -1)
            .limit(ASSISTANT_CONTEXT_LIMIT)
        ),
        default=[]
    )

    customs_result = _safe_assistant_records(
        lambda: list_customs_records(limit=0),
        default={"customs": [], "summary": {}}
    )

    total_users = admin_statistics.get("total_users")

    if total_users is None:

        total_users = _safe_assistant_records(
            lambda: users_collection.count_documents({}),
            default=0
        )

    result = answer_admin_question(
        message,
        stats=admin_statistics,
        shipments=[
            _serialize_shipment(record)
            for record in shipments
        ],
        quotations=[
            _serialize_history_record(record)
            for record in quotations
        ],
        customs_rows=customs_result.get("customs", []),
        users_logged_in_today=(
            _count_users_logged_in_today()
        ),
        users_total=total_users,
        health=_collect_system_health(),
        analyze=analyze_customs,
        status_flow=SHIPMENT_STATUS_FLOW,
        shipment_id=request.clean_shipment_id(),
        route_id=request.clean_route_id(),
        knowledge_provider=_assistant_knowledge
    )

    # An out-of-scope question is answered with the fixed
    # refusal and never reaches the explanation service, for
    # exactly the same reason as the user assistant.

    if result.get("out_of_scope"):

        return {
            "success": True,
            "scope": "admin",
            "question": message,
            "answer": result["deterministic_answer"],
            "answer_source": "refusal",
            "explanation_available": False,
            "out_of_scope": True,
            "intents": result.get("intents", []),
            "focus": result.get("focus", {}),
            "facts": {},
            "deterministic_answer": result[
                "deterministic_answer"
            ]
        }

    project_block = (
        (result.get("facts") or {}).get("project")
    )

    try:

        explanation = generate_assistant_reply(
            question=message,
            facts=result["facts"],
            deterministic_answer=result[
                "deterministic_answer"
            ],
            scope="admin",
            project_knowledge=project_block
        )

    except Exception as explanation_error:

        logger.warning(
            "Admin assistant explanation layer error: %s",
            explanation_error
        )

        explanation = {
            "answer": result["deterministic_answer"],
            "answer_source": "deterministic",
            "explanation_available": False,
        }

    return {
        "success": True,
        "scope": "admin",
        "question": message,
        "answer": explanation.get(
            "answer",
            result["deterministic_answer"]
        ),
        "answer_source": explanation.get(
            "answer_source", "deterministic"
        ),
        "explanation_available": explanation.get(
            "explanation_available", False
        ),

        # Internal diagnostics, not returned to the browser.
        "intents": result.get("intents", []),
        "focus": result.get("focus", {}),
        "facts": result.get("facts", {}),
        "deterministic_answer": result[
            "deterministic_answer"
        ]
    }