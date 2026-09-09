from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
import bcrypt
import re
import os
import logging
from datetime import datetime

from dotenv import load_dotenv

from app.models import RouteRequest
from app.agents.route_agent import analyze_route


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
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://agentic-ai-maritime-brokerage-git-main-a-3fe4.vercel.app"
    ],
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
        "milestone": "Milestone 1 - Route Intelligence"
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

    user = {
        "name": name,
        "contact": contact,
        "password": hashed_password,
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
            "contact": contact
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

    user = users_collection.find_one({
        "contact": contact
    })


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

    return {
        "success": True,
        "message": "Login successful.",
        "user": {
            "id": str(user["_id"]),
            "name": user.get("name", ""),
            "contact": user.get("contact", ""),
            "mfa_enabled": user.get("mfa_enabled", False)
        }
    }


# ============================================================
# ROUTE HISTORY HELPERS
# ============================================================

def _history_document(result, request):

    recommended = (
        result.get("recommended_route") or {}
    )

    return {
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
        "created_at": datetime.utcnow()
    }


def _save_route_history(result, request):

    # Only save history when it can be associated
    # with a logged-in user.
    if not request.user_id:

        return

    document = _history_document(result, request)

    route_history_collection.insert_one(document)


def _serialize_history_record(record):

    created_at = record.get("created_at")

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

    return {
        "origins": origins,
        "destinations": destinations
    }


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
    request: RouteRequest
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

            _save_route_history(result, request)

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
# ROUTE HISTORY
# ============================================================

@app.get("/api/routes/history")
def get_route_history(
    user_id: str = "",
    contact: str = ""
):

    owner_id = _require_user_id(user_id)

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
    user_id: str = ""
):

    owner_id = _require_user_id(user_id)

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
    user_id: str = ""
):

    owner_id = _require_user_id(user_id)

    # Only the current user's history is removed.
    result = route_history_collection.delete_many({
        "user_id": owner_id
    })

    return {
        "success": True,
        "message": "Route history cleared.",
        "deleted_count": result.deleted_count
    }