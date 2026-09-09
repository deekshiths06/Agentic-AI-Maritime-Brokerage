from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
import bcrypt
import re
from datetime import datetime

from dotenv import load_dotenv

from app.models import RouteRequest
from app.agents.route_agent import analyze_route


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
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# MONGODB
# ============================================================

client = MongoClient(
    "mongodb://127.0.0.1:27017/"
)

db = client["maritime_brokerage"]

users_collection = db["users"]


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
# ROUTE ANALYSIS
# ============================================================

@app.post("/api/routes/analyze")
def analyze_shipment(
    request: RouteRequest
):

    return analyze_route(
        request.origin,
        request.destination,
        request.cargo_type,
        request.containers
    )