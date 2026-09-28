# =========================================================
# WEATHER DATASET GENERATOR
# =========================================================
# Generates a COMPLETE weather.csv so that every route_id
# that exists in routes.csv has exactly one weather record.
#
# RULES
# ------
# - Fully deterministic. No random values. Re-running this
#   script always produces an identical weather.csv.
# - routes.csv is READ ONLY. It is never modified here.
# - One record per route_id. The route-level relationship is
#   preserved: origin/destination are copied from routes.csv,
#   so the Route Agent recommendation and the Weather Agent
#   always speak about the same route.
# - Additional routes can be appended to weather.csv later
#   without touching the Weather Agent.
#
# WHAT THE DATASET IS
# -------------------
# weather.csv is STATIC PROJECT REFERENCE DATA for the Weather
# Intelligence module. It is NOT live weather and no external
# weather API or API key is used anywhere in this project.
#
# WHERE THE VALUES COME FROM
# --------------------------
# The maritime route dataset (routes.csv) already carries one
# weather-related field per route: `weather_risk`
# (Low / Moderate / Elevated). That field is used as the
# storm-exposure BAND for the generated record:
#
#   routes.csv weather_risk   ->   weather.csv storm_risk
#   ------------------------------------------------------
#   Low                       ->   Low
#   Moderate                  ->   Moderate
#   Elevated                  ->   High
#
# wind_speed_knots / wave_height_m / rainfall_mm /
# visibility_km are then generated inside the range that
# belongs to that band, so the Weather Agent's documented
# risk thresholds classify the record exactly as the band
# describes.
#
# DETERMINISTIC VALUE RULES
# -------------------------
# Every route gets a stable pseudo-random position (a hash of
# its route_id, never a random number) blended with an
# "ocean exposure" factor derived from the real coordinates
# and distance already stored in routes.csv:
#
#   exposure = 0.55 * mean(|origin_lat|, |destination_lat|)/90
#            + 0.45 * min(distance_nm / 12000, 1)
#
#   value = band_low + (band_high - band_low)
#                   * (0.5 * route_hash + 0.5 * exposure)
#
# Because the blended position always stays inside
# [band_low, band_high], exposed long-distance/high-latitude
# corridors sit near the severe end of their band while calm
# short-haul corridors sit near the calm end, and the record
# always matches its storm_risk band.
#
# BAND RANGES
# -----------
#   Low      wind  8 - 22 kn | wave 0.4 - 1.6 m
#            rain  0 -  8 mm | vis 12.0 - 20.0 km
#   Moderate wind 22 - 34 kn | wave 1.6 - 3.2 m
#            rain  8 - 35 mm | vis  7.0 - 12.0 km
#   High     wind 34 - 58 kn | wave 3.2 - 6.5 m
#            rain 35 -120 mm | vis  2.0 -  7.0 km
#
# WEATHER CONDITION
# -----------------
# Derived from the generated values, first matching rule wins:
#   Storm    : visibility < 4 km OR wind >= 45 kn OR wave >= 5.0 m
#   Squall   : wind >= 33 kn OR wave >= 3.0 m
#   Rain     : rainfall >= 15 mm
#   Overcast : rainfall >= 3 mm OR visibility < 10 km
#   Fair     : everything else
# =========================================================

import hashlib
import os

import pandas as pd


# =========================================================
# PATHS
# =========================================================

ROUTES_CSV = os.path.join(
    os.path.dirname(__file__), "..", "routes.csv"
)

WEATHER_CSV = os.path.join(
    os.path.dirname(__file__), "..", "weather.csv"
)


# =========================================================
# STORM EXPOSURE BANDS
# =========================================================

# routes.csv weather_risk -> weather.csv storm_risk
STORM_BAND = {
    "low": "Low",
    "moderate": "Moderate",
    "elevated": "High",
}

# Fallback band when routes.csv carries no weather_risk value.
DEFAULT_STORM_BAND = "Moderate"

# value ranges per storm_risk band:
#   wind   : knots
#   wave   : metres
#   rain   : millimetres
#   vis    : kilometres
BAND_RANGES = {
    "Low": {
        "wind": (8.0, 22.0),
        "wave": (0.4, 1.6),
        "rain": (0.0, 8.0),
        "vis": (12.0, 20.0),
    },
    "Moderate": {
        "wind": (22.0, 34.0),
        "wave": (1.6, 3.2),
        "rain": (8.0, 35.0),
        "vis": (7.0, 12.0),
    },
    "High": {
        "wind": (34.0, 58.0),
        "wave": (3.2, 6.5),
        "rain": (35.0, 120.0),
        "vis": (2.0, 7.0),
    },
}

# Reference distance (nautical miles) at which a corridor is
# treated as a fully exposed open-ocean passage.
EXPOSURE_DISTANCE_NM = 12000.0


# =========================================================
# HELPERS
# =========================================================

def _clamp(value, low, high):
    return max(low, min(high, value))


def _stable_unit(route_id: str, salt: str) -> float:
    """
    Return a stable pseudo-random value in [0, 1) for a
    route_id. md5 is used purely as a reproducible hash, not
    for security, so the result is identical on every run and
    on every machine.
    """

    digest = hashlib.md5(
        f"{salt}|{route_id}".encode("utf-8")
    ).hexdigest()

    return int(digest[:8], 16) / 0x100000000


def _to_float(value, fallback=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback

    if number != number:  # NaN
        return fallback

    return number


def _exposure(origin_lat, destination_lat, distance_nm):
    """
    Open-ocean exposure in [0, 1]. Higher latitudes and
    longer passages expose a corridor to rougher conditions.
    """

    mean_lat = (
        abs(_to_float(origin_lat)) +
        abs(_to_float(destination_lat))
    ) / 2.0

    latitude_factor = _clamp(mean_lat / 90.0, 0.0, 1.0)

    distance_factor = _clamp(
        _to_float(distance_nm) / EXPOSURE_DISTANCE_NM,
        0.0,
        1.0
    )

    return _clamp(
        0.55 * latitude_factor + 0.45 * distance_factor,
        0.0,
        1.0
    )


def _band_value(route_id, salt, band_range, exposure):
    """Blend the route hash with exposure inside the band."""

    low, high = band_range

    position = (
        0.5 * _stable_unit(route_id, salt) +
        0.5 * exposure
    )

    return low + (high - low) * position


# =========================================================
# LOAD routes.csv (READ ONLY)
# =========================================================

def _load_routes():
    if not os.path.exists(ROUTES_CSV):
        raise FileNotFoundError(
            f"routes.csv not found at {ROUTES_CSV}"
        )

    df = pd.read_csv(ROUTES_CSV)

    for column in ("route_id", "origin", "destination",
                   "weather_risk"):
        if column in df.columns:
            df[column] = (
                df[column].fillna("").astype(str).str.strip()
            )

    return df


# =========================================================
# WEATHER CONDITION
# =========================================================

def _weather_condition(wind, wave, rain, visibility):
    """First matching rule wins (see header documentation)."""

    if visibility < 4.0 or wind >= 45.0 or wave >= 5.0:
        return "Storm"

    if wind >= 33.0 or wave >= 3.0:
        return "Squall"

    if rain >= 15.0:
        return "Rain"

    if rain >= 3.0 or visibility < 10.0:
        return "Overcast"

    return "Fair"


# =========================================================
# MAIN GENERATOR
# =========================================================

def generate_weather_csv():
    """
    Build the complete weather dataset (one record per
    route_id) and write it to backend/app/weather.csv.
    """

    routes = _load_routes()

    routes = routes.sort_values("route_id").reset_index(
        drop=True
    )

    records = []

    used_route_ids = set()

    for _, route in routes.iterrows():

        route_id = str(route.get("route_id", "")).strip()

        if not route_id or route_id in used_route_ids:
            continue

        used_route_ids.add(route_id)

        storm_risk = STORM_BAND.get(
            str(route.get("weather_risk", "")).strip().lower(),
            DEFAULT_STORM_BAND
        )

        band = BAND_RANGES[storm_risk]

        exposure = _exposure(
            route.get("origin_latitude"),
            route.get("destination_latitude"),
            route.get("distance_nm")
        )

        wind = _band_value(
            route_id, "wind", band["wind"], exposure
        )

        wave = _band_value(
            route_id, "wave", band["wave"], exposure
        )

        rain = _band_value(
            route_id, "rain", band["rain"], exposure
        )

        visibility = _band_value(
            route_id, "vis", band["vis"], 1.0 - exposure
        )

        records.append({
            "route_id": route_id,
            "origin": str(
                route.get("origin", "")
            ).strip(),
            "destination": str(
                route.get("destination", "")
            ).strip(),
            "storm_risk": storm_risk,
            "wind_speed_knots": int(round(wind)),
            "wave_height_m": round(wave, 1),
            "rainfall_mm": int(round(rain)),
            "visibility_km": round(visibility, 1),
            "weather_condition": _weather_condition(
                wind, wave, rain, visibility
            ),
        })

    columns = [
        "route_id",
        "origin",
        "destination",
        "storm_risk",
        "wind_speed_knots",
        "wave_height_m",
        "rainfall_mm",
        "visibility_km",
        "weather_condition",
    ]

    out = pd.DataFrame(records, columns=columns)

    out = out.drop_duplicates(subset=["route_id"], keep="first")

    out = out.sort_values("route_id").reset_index(drop=True)

    out.to_csv(WEATHER_CSV, index=False)

    return out


if __name__ == "__main__":
    result = generate_weather_csv()

    print(f"weather.csv written: {len(result)} records")

    print(
        "route_id range: "
        f"{result['route_id'].iloc[0]} .. "
        f"{result['route_id'].iloc[-1]}"
    )

    print(
        "unique corridors: "
        f"{result.groupby(['origin', 'destination']).ngroups}"
    )

    print(result["storm_risk"].value_counts().to_string())
