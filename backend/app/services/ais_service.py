# =========================================================
# AIS VESSEL SERVICE - REAL AIS DATA (AISHub)
# =========================================================
# Provides real AIS vessel positions to the Maritime Route
# Map through the FastAPI backend. The React frontend never
# talks to the provider directly and never sees the API key.
#
# Provider: AISHub (https://www.aishub.net/api)
#   Endpoint : https://data.aishub.net/ws.php
#   Auth     : member username (sent as the "username" query
#              parameter, treated here as the API key)
#   Output   : format=1 (human readable) output=json
#   Rate     : poll at most once per minute; the service
#              returns an EMPTY body when called more often.
#
# This module:
#   * reads AIS_API_KEY from the backend environment
#   * calls the provider securely from FastAPI
#   * caches the provider response in memory (TTL) so the
#     map never hammers the provider on every render
#   * normalizes the response to safe fields only
#   * never exposes the provider key to the frontend
# =========================================================

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger("uvicorn.error")


# =========================================================
# PROVIDER CONFIGURATION (environment variables)
# =========================================================

AIS_API_KEY = os.getenv("AIS_API_KEY", "").strip()

AIS_API_URL = os.getenv(
    "AIS_API_URL",
    "https://data.aishub.net/ws.php"
).strip()

# How long a fetched dataset is kept in memory before the
# provider is called again. Default 180s comfortably honours
# the "once per minute" provider rule while keeping data fresh.
AIS_CACHE_TTL_SECONDS = int(
    os.getenv("AIS_CACHE_TTL_SECONDS", "180")
)

# Safety floor between two provider calls. Ignores even a
# deliberately shortened cache TTL so a misconfiguration can
# never violate the provider's once-per-minute rule.
AIS_MIN_REQUEST_INTERVAL = 90

# Cap the number of vessels shipped to the frontend. Prevents
# an unconstrained global dataset from bloating every map load.
AIS_MAX_VESSELS = int(os.getenv("AIS_MAX_VESSELS", "400"))

# Provider HTTP timeout in seconds.
AIS_TIMEOUT_SECONDS = float(
    os.getenv("AIS_TIMEOUT_SECONDS", "15")
)

# Default request area: "latmin,lonmin,latmax,lonmax".
# Defaults to the whole world. A tighter area keeps payloads
# small and still shows the vessels relevant to the map.
AIS_DEFAULT_BOUNDS = os.getenv(
    "AIS_DEFAULT_BOUNDS",
    "-90,-180,90,180"
)


# =========================================================
# IN-MEMORY CACHE
# =========================================================
# Single-process cache keyed on the requested area. FastAPI
# runs one worker process, so a module-level store is safe.
# =========================================================

_cache_lock = threading.Lock()

_in_flight_lock = threading.Lock()

_last_external_request = 0.0

# { area_key: {"fetched_at": float, "payload": dict} }
_ais_cache = {}


def _parse_default_bounds():
    parts = [
        float(value.strip())
        for value in str(AIS_DEFAULT_BOUNDS).split(",")
        if value.strip() != ""
    ]

    if len(parts) != 4:
        return (-90.0, -180.0, 90.0, 180.0)

    latmin, lonmin, latmax, lonmax = parts

    return _clamp_box(latmin, lonmin, latmax, lonmax)


def _clamp_box(latmin, lonmin, latmax, lonmax):
    latmin = max(-90.0, min(90.0, float(latmin)))
    latmax = max(-90.0, min(90.0, float(latmax)))
    lonmin = max(-180.0, min(180.0, float(lonmin)))
    lonmax = max(-180.0, min(180.0, float(lonmax)))

    if latmin > latmax:
        latmin, latmax = latmax, latmin

    if lonmin > lonmax:
        lonmin, lonmax = lonmax, lonmin

    return (latmin, lonmin, latmax, lonmax)


def _area_key(latmin, lonmin, latmax, lonmax):
    # Round to half degrees so neighbouring requests share
    # one cached dataset instead of creating many duplicates.
    step = 0.5
    return "|".join(
        str(round(value / step) * step)
        for value in (latmin, lonmin, latmax, lonmax)
    )


def _safe_bounds(latmin=None, lonmin=None, latmax=None, lonmax=None):
    if latmin is None and lonmin is None and latmax is None and lonmax is None:
        return _parse_default_bounds()

    default = (-90.0, -180.0, 90.0, 180.0)

    return _clamp_box(
        latmin if latmin is not None else default[0],
        lonmin if lonmin is not None else default[1],
        latmax if latmax is not None else default[2],
        lonmax if lonmax is not None else default[3],
    )


# =========================================================
# PROVIDER REQUEST
# =========================================================

def _call_provider(latmin, lonmin, latmax, lonmax):
    global _last_external_request

    query = urllib.parse.urlencode({
        "username": AIS_API_KEY,
        "format": "1",       # human readable values
        "output": "json",    # JSON output
        "compress": "0",     # no compression
        "latmin": str(latmin),
        "latmax": str(latmax),
        "lonmin": str(lonmin),
        "lonmax": str(lonmax),
    })

    url = f"{AIS_API_URL}?{query}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Agentic-AI-Maritime-Brokerage/1.0 "
                "(Maritime Route Map - AIS vessels)"
            )
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=AIS_TIMEOUT_SECONDS
    ) as response:

        body = response.read().decode("utf-8", errors="replace")

        if not body or not body.strip():
            raise RuntimeError(
                "AIS provider returned an empty response "
                "(rate limit or no data)."
            )

        return json.loads(body)


# =========================================================
# NORMALIZATION
# =========================================================
# AISHub human-readable JSON (format=1, output=json) is:
#   [ {"ERROR":false,"USERNAME":"...","FORMAT":"HUMAN",
#      "RECORDS":5},
#     [ {"MMSI":...,"TIME":"... GMT","LONGITUDE":..,
#        "LATITUDE":..,"COG":..,"SOG":..,"HEADING":..,
#        "IMO":..,"NAME":"..","CALLSIGN":"..","TYPE":..,
#        "DRAUGHT":..,"DEST":"..","ETA":".."}, ... ] ]
# Only fields actually returned by the provider are exposed.
# =========================================================

AIS_SHIP_TYPE_TAGS = {
    30: "Fishing",
    31: "Towing",
    32: "Towing",
    33: "Dredging",
    34: "Diving",
    35: "Military",
    36: "Sailing",
    37: "Pleasure Craft",
    40: "High Speed Craft",
    52: "Tug",
    55: "Dredging",
    60: "Passenger",
    61: "Passenger",
    62: "Passenger",
    63: "Passenger",
    64: "Passenger",
    65: "Passenger",
    66: "Passenger",
    67: "Passenger",
    68: "Passenger",
    69: "Passenger",
    70: "Cargo",
    71: "Cargo",
    72: "Cargo",
    73: "Cargo",
    74: "Cargo",
    75: "Cargo",
    76: "Cargo",
    77: "Cargo",
    78: "Cargo",
    79: "Cargo",
    80: "Tanker",
    81: "Tanker",
    82: "Tanker",
    83: "Tanker",
    84: "Tanker",
    85: "Tanker",
    86: "Tanker",
    87: "Tanker",
    88: "Tanker",
    89: "Tanker",
    90: "Other",
    91: "Other",
    93: "Other",
    99: "Not Available",
}


def _parse_float(value):
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:  # NaN
        return None

    return number


def _parse_int(value):
    if value is None:
        return None

    try:
        number = int(value)
    except (TypeError, ValueError):
        return None

    return number


def _clean_text(value):
    if value is None:
        return None

    text = str(value).strip()

    return text or None


def _parse_ais_timestamp(value):
    if not value:
        return None

    text = str(value).strip()

    if not text:
        return None

    # AISHub supplies UTC timestamps such as "2021-07-09 12:08:05 GMT".
    for pattern in (
        "%Y-%m-%d %H:%M:%S GMT",
        "%Y-%m-%d %H:%M:%S UTC",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):

        try:

            return datetime.strptime(
                text, pattern
            ).replace(tzinfo=timezone.utc).isoformat()

        except ValueError:

            continue

    try:

        unix = float(text)

        return datetime.fromtimestamp(
            unix, tz=timezone.utc
        ).isoformat()

    except (TypeError, ValueError):

        return text


def _extract_vessel_rows(data):
    """Return (rows, meta) from any plausible AISHub JSON shape."""

    if isinstance(data, dict):

        if "ERROR" in data and "MMSI" not in data:
            # metadata-only envelope
            return [], data

        if "vessel" in data and isinstance(data["vessel"], list):
            return data["vessel"], data

        if "vessels" in data and isinstance(data["vessels"], list):
            return data["vessels"], data

        if "MMSI" in data or "mmsi" in data:
            return [data], {}

        return [], {}

    if isinstance(data, list):

        if (
            len(data) >= 2
            and isinstance(data[0], dict)
            and isinstance(data[1], list)
        ):
            return data[1], data[0]

        rows = [
            row
            for row in data
            if isinstance(row, dict)
            and (
                "MMSI" in row
                or "mmsi" in row
                or "LATITUDE" in row
                or "latitude" in row
            )
        ]

        return rows, {}

    return [], {}


def _normalize_vessels(rows, meta):
    vessels = []

    for row in rows[:AIS_MAX_VESSELS]:

        if not isinstance(row, dict):
            continue

        mmsi = _clean_text(
            row.get("MMSI", row.get("mmsi"))
        )

        if not mmsi:
            continue

        latitude = _parse_float(
            row.get("LATITUDE", row.get("latitude"))
        )

        longitude = _parse_float(
            row.get("LONGITUDE", row.get("longitude"))
        )

        if (
            latitude is None
            or longitude is None
            or not (-90.0 <= latitude <= 90.0)
            or not (-180.0 <= longitude <= 180.0)
        ):
            continue

        speed = _parse_float(
            row.get("SOG", row.get("speed"))
        )

        if speed is not None and speed >= 102.4:
            speed = None

        course = _parse_float(
            row.get("COG", row.get("course"))
        )

        if course is not None and course >= 360.0:
            course = None

        heading = _parse_float(
            row.get("HEADING", row.get("heading"))
        )

        if heading is not None and heading >= 511.0:
            heading = None

        imo = _parse_int(row.get("IMO", row.get("imo")))

        if imo is not None and imo <= 0:
            imo = None

        type_code = _parse_int(
            row.get("TYPE", row.get("vessel_type_code"))
        )

        destination = _clean_text(
            row.get("DEST", row.get("destination"))
        )

        eta = _clean_text(row.get("ETA", row.get("eta")))

        # AISHub uses "00-00 00:00"-style sentinels when no
        # ETA/destination is declared. Treat them as absent.
        if eta and eta.startswith("00-00"):
            eta = None

        vessel = {
            "mmsi": str(mmsi),
            "imo": str(imo) if imo else None,
            "name": _clean_text(
                row.get("NAME", row.get("name"))
            ),
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
            "speed_knots": (
                round(speed, 1) if speed is not None else None
            ),
            "course": (
                round(course, 1) if course is not None else None
            ),
            "heading": (
                round(heading, 1) if heading is not None else None
            ),
            "destination": destination,
            "eta": eta,
            "vessel_type_code": type_code,
            "vessel_type": (
                AIS_SHIP_TYPE_TAGS.get(type_code)
                if type_code is not None
                else None
            ),
            "callsign": _clean_text(
                row.get("CALLSIGN", row.get("callsign"))
            ),
            "navigational_status": _parse_int(
                row.get("NAVSTAT", row.get("navigational_status"))
            ),
            "timestamp": _parse_ais_timestamp(
                row.get("TIME", row.get("timestamp"))
            ),
        }

        vessels.append(vessel)

    return vessels


def _dedupe_vessels(vessels):
    seen = set()
    unique = []

    for vessel in vessels:
        key = str(vessel["mmsi"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(vessel)

    return unique


# =========================================================
# PUBLIC ENTRY POINT
# =========================================================

def provider_configured():
    """True when an AIS_API_KEY is present in the environment."""
    return bool(AIS_API_KEY)


def fetch_ais_vessels(
    latmin=None,
    lonmin=None,
    latmax=None,
    lonmax=None
):
    """Fetch and normalize real AIS vessels.

    Returns a dict the frontend can render directly. Never
    raises: provider failures become a safe "unavailable"
    payload so the route map keeps working.
    """

    if not provider_configured():

        return {
            "status": "not_configured",
            "source": "AISHub",
            "message": (
                "Live AIS vessel tracking is not configured. "
                "Add AIS_API_KEY to the backend environment "
                "to enable live vessel data."
            ),
            "updated_at": None,
            "count": 0,
            "area": None,
            "vessels": [],
        }

    latmin, lonmin, latmax, lonmax = _safe_bounds(
        latmin, lonmin, latmax, lonmax
    )

    area = {
        "min_lat": latmin,
        "min_lon": lonmin,
        "max_lat": latmax,
        "max_lon": lonmax,
    }

    key = _area_key(latmin, lonmin, latmax, lonmax)

    now = time.time()

    with _cache_lock:

        cached = _ais_cache.get(key)

        if cached and now - cached["fetched_at"] < AIS_CACHE_TTL_SECONDS:

            return cached["payload"]

    # -------------------------------------------------
    # SAFETY: never call the provider more than once per
    # AIS_MIN_REQUEST_INTERVAL (provider requires 1/min).
    # -------------------------------------------------

    with _in_flight_lock:

        global _last_external_request

        if (
            now - _last_external_request
            < AIS_MIN_REQUEST_INTERVAL
        ):

            with _cache_lock:

                stale = _ais_cache.get(key)

            if stale:

                return {
                    **stale["payload"],
                    "message": (
                        "Live vessel data served from the "
                        "last AIS snapshot."
                    ),
                }

            return {
                "status": "unavailable",
                "source": "AISHub",
                "message": (
                    "Live vessel data temporarily unavailable."
                ),
                "updated_at": None,
                "count": 0,
                "area": area,
                "vessels": [],
            }

        _last_external_request = now

    # -------------------------------------------------
    # CALL PROVIDER
    # -------------------------------------------------

    try:

        data = _call_provider(latmin, lonmin, latmax, lonmax)

        rows, meta = _extract_vessel_rows(data)

        vessels = _dedupe_vessels(
            _normalize_vessels(rows, meta)
        )

        # Snapshot time: the newest per-vessel AIS timestamp.
        snapshot = None

        for vessel in vessels:

            stamped = vessel.get("timestamp")

            if stamped and not snapshot:
                snapshot = stamped

        payload = {
            "status": "ok",
            "source": "AISHub",
            "message": (
                "Recent AIS vessel positions from AISHub."
            ),
            "updated_at": snapshot
            or datetime.now(timezone.utc).isoformat(),
            "count": len(vessels),
            "area": area,
            "vessels": vessels,
        }

        fetched_at = time.time()

        with _cache_lock:

            _ais_cache[key] = {
                "fetched_at": fetched_at,
                "payload": payload,
            }

            # Keep the cache bounded (max 8 areas).
            if len(_ais_cache) > 8:

                oldest_key = min(
                    _ais_cache,
                    key=lambda item: _ais_cache[item]["fetched_at"]
                )

                _ais_cache.pop(oldest_key, None)

        return payload

    except urllib.error.HTTPError as error:

        logger.warning(
            "AIS provider HTTP error: %s %s",
            error.code, error.reason
        )

        return {
            "status": "unavailable",
            "source": "AISHub",
            "message": (
                "Live vessel data temporarily unavailable."
            ),
            "updated_at": None,
            "count": 0,
            "area": area,
            "vessels": [],
        }

    except (urllib.error.URLError, TimeoutError, OSError) as error:

        logger.warning("AIS provider connection error: %s", error)

        return {
            "status": "unavailable",
            "source": "AISHub",
            "message": (
                "Live vessel data temporarily unavailable."
            ),
            "updated_at": None,
            "count": 0,
            "area": area,
            "vessels": [],
        }

    except (ValueError, json.JSONDecodeError) as error:

        logger.warning("AIS provider response error: %s", error)

        return {
            "status": "unavailable",
            "source": "AISHub",
            "message": (
                "Live vessel data temporarily unavailable."
            ),
            "updated_at": None,
            "count": 0,
            "area": area,
            "vessels": [],
        }

    except Exception as error:

        logger.warning("AIS provider error: %s", error)

        return {
            "status": "unavailable",
            "source": "AISHub",
            "message": (
                "Live vessel data temporarily unavailable."
            ),
            "updated_at": None,
            "count": 0,
            "area": area,
            "vessels": [],
        }