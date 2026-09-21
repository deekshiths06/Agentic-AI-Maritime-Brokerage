import pandas as pd


# =========================================================
# CARGO TYPE MAPPING
# =========================================================
# Frontend cargo choices -> Main cargo_type in routes.csv
#
# Your CSV uses main categories such as:
# Bulk, General Cargo, Containerized, Perishable, Hazardous
#
# The frontend can show more business-friendly cargo choices.

CARGO_TYPE_MAPPING = {

    # -----------------------------------------------------
    # GENERAL CARGO
    # -----------------------------------------------------

    "general cargo": "General Cargo",

    "electronics": "General Cargo",

    "textiles": "General Cargo",

    "machinery": "General Cargo",

    "automotive": "General Cargo",

    "steel": "General Cargo",

    "timber": "General Cargo",

    "containerized cargo": "Containerized",

    # -----------------------------------------------------
    # CONTAINERIZED
    # -----------------------------------------------------

    "containerized": "Containerized",

    # -----------------------------------------------------
    # PERISHABLE
    # -----------------------------------------------------

    "food products": "Perishable",

    "perishable goods": "Perishable",

    "pharmaceuticals": "Perishable",

    # -----------------------------------------------------
    # BULK
    # -----------------------------------------------------

    "bulk": "Bulk",

    "agricultural products": "Bulk",

    "grain": "Bulk",

    "coal": "Bulk",

    "iron ore": "Bulk",

    "bulk dry cargo": "Bulk",

    "bulk liquid cargo": "Bulk",

    # -----------------------------------------------------
    # HAZARDOUS
    # -----------------------------------------------------

    "chemicals": "Hazardous",

    "petroleum products": "Hazardous",

    "liquefied gas": "Hazardous",

    "hazardous materials": "Hazardous",
}


# =========================================================
# LOAD ROUTE DATA
# =========================================================

def load_routes():

    df = pd.read_csv("app/routes.csv")

    # -----------------------------------------------------
    # CLEAN COLUMN NAMES
    # -----------------------------------------------------

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
    )

    # -----------------------------------------------------
    # REQUIRED COLUMNS
    # -----------------------------------------------------

    required_columns = [
        "route_id",
        "origin",
        "destination",
        "cargo_type",
        "cargo_subtype",
        "route",
        "transit_days",
        "distance_nm",
        "transshipments"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            "Required column(s) missing from routes.csv: "
            + ", ".join(missing_columns)
        )

    # -----------------------------------------------------
    # CLEAN TEXT COLUMNS
    # -----------------------------------------------------

    text_columns = [
        "route_id",
        "origin",
        "destination",
        "cargo_type",
        "cargo_subtype",
        "route"
    ]

    for column in text_columns:

        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # -----------------------------------------------------
    # CLEAN NUMERIC COLUMNS
    # -----------------------------------------------------
    # route_id is NOT included here because values such as
    # R00001, R00231, R00561 are text identifiers.

    numeric_columns = [
        "transit_days",
        "distance_nm",
        "transshipments"
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # -----------------------------------------------------
    # REMOVE INVALID RECORDS
    # -----------------------------------------------------

    df = df.dropna(
        subset=[
            "route_id",
            "origin",
            "destination",
            "cargo_type",
            "cargo_subtype",
            "route",
            "transit_days",
            "distance_nm",
            "transshipments"
        ]
    )

# -----------------------------------------------------
    # REMOVE EMPTY ROUTE IDS
    # -----------------------------------------------------

    df = df[
        df["route_id"].str.strip() != ""
    ].copy()

    return df


# =========================================================
# GEOGRAPHIC / METADATA HELPERS
# =========================================================
# These helpers read columns that already exist in routes.csv
# (port coordinates, vessel, service and risk metadata) and
# expose them in the analysis response for the Maritime Route
# Map. They never change how routes are selected, scored or
# recommended - the recommendation logic is untouched.

def _safe_coord(row, column, fallback=0.0):

    try:

        value = float(row.get(column, fallback))

        # NaN check: a NaN value never equals itself.
        if value != value:
            return fallback

        return value

    except (TypeError, ValueError):

        return fallback


def _safe_text(row, column, fallback=""):

    try:

        value = str(row.get(column, fallback))

        return value.strip() or fallback

    except (TypeError, ValueError):

        return fallback


# =========================================================
# NORMALIZE CARGO TYPE
# =========================================================

def normalize_cargo_type(cargo_type):

    if not cargo_type:
        return ""

    cargo = (
        str(cargo_type)
        .strip()
        .lower()
    )

    # -----------------------------------------------------
    # FRONTEND VALUE EXISTS IN MAPPING
    # -----------------------------------------------------

    if cargo in CARGO_TYPE_MAPPING:

        return CARGO_TYPE_MAPPING[cargo]

    # -----------------------------------------------------
    # OTHERWISE CHECK DIRECT CSV VALUE
    # -----------------------------------------------------

    return str(cargo_type).strip()


# =========================================================
# ROUTE ANALYSIS
# =========================================================

def analyze_route(
    origin,
    destination,
    cargo_type,
    cargo_subtype,
    containers
):

    try:

        # =================================================
        # LOAD DATA
        # =================================================

        df = load_routes()

        # =================================================
        # VALIDATE ORIGIN
        # =================================================

        if not origin:

            raise ValueError(
                "Origin port is required."
            )

        # =================================================
        # VALIDATE DESTINATION
        # =================================================

        if not destination:

            raise ValueError(
                "Destination port is required."
            )

        # =================================================
        # VALIDATE CARGO
        # =================================================

        if not cargo_type:

            raise ValueError(
                "Cargo type is required."
            )

        # =================================================
        # VALIDATE CONTAINERS
        # =================================================

        try:

            containers = int(containers)

        except (TypeError, ValueError):

            raise ValueError(
                "Number of containers must be a valid number."
            )

        if containers < 1:

            raise ValueError(
                "Number of containers must be at least 1."
            )

        # =================================================
        # CLEAN INPUTS
        # =================================================

        requested_cargo = (
            str(cargo_type)
            .strip()
        )

        requested_subtype = (
            str(cargo_subtype)
            .strip()
        )

        # =================================================
        # CONVERT FRONTEND CARGO TO CSV CARGO
        # =================================================

        mapped_cargo = normalize_cargo_type(
            requested_cargo
        )

        # =================================================
        # NORMALIZATION HELPER
        # =================================================
        # Robust port matching: leading/trailing whitespace and
        # casing differences never hide a valid route.

        def _normalize(value):

            return str(value or "").strip().lower()

        # =================================================
        # FILTER ORIGIN + DESTINATION
        # =================================================

        filtered = df[
            (
                df["origin"]
                .astype(str)
                .str.strip()
                .str.lower()
                ==
                _normalize(origin)
            )
            &
            (
                df["destination"]
                .astype(str)
                .str.strip()
                .str.lower()
                ==
                _normalize(destination)
            )
        ].copy()

        # =================================================
        # NO ROUTE FOR ORIGIN + DESTINATION
        # =================================================

        if filtered.empty:

            raise ValueError(
                f"No maritime routes available between "
                f"{origin} and {destination}."
            )

        # =================================================
        # FILTER CARGO TYPE
        # =================================================

        used_corridor_fallback = False

        cargo_filtered = filtered[
            filtered["cargo_type"]
            .astype(str)
            .str.strip()
            .str.lower()
            ==
            mapped_cargo.lower()
        ].copy()

        # =================================================
        # CARGO TYPE FALLBACK
        # =================================================
        # If no route carries the requested cargo category for
        # these ports, every valid route on the
        # origin -> destination corridor is kept instead of
        # being eliminated. The reasons list explains this
        # fallback so the user understands the result.
        # =================================================

        if cargo_filtered.empty:

            used_corridor_fallback = True

            cargo_filtered = filtered.copy()

        filtered = cargo_filtered

        # =================================================
        # CARGO SUBTYPE
        # =================================================
        # The selected subtype narrows the user's cargo choice
        # but it never eliminates valid routes: if routes
        # carrying the exact subtype exist they are evaluated
        # together with every other valid route for the selected
        # corridor and cargo category. If the dataset does not
        # carry the exact subtype here, the valid routes are kept
        # anyway and the reasons list explains the situation.
        # =================================================

        if requested_subtype:

            subtype_matched_count = int(
                filtered["cargo_subtype"]
                .astype(str)
                .str.strip()
                .str.lower()
                .eq(
                    requested_subtype.lower()
                )
                .sum()
            )

        else:

            subtype_matched_count = 0

        # =================================================
        # AVAILABLE ROUTES COUNT
        # =================================================

        total_available_routes = len(filtered)

        if total_available_routes == 0:

            raise ValueError(
                f"No routes available for "
                f"{requested_subtype} {mapped_cargo} "
                f"from {origin} to {destination}."
            )

        # =================================================
        # MAXIMUM VALUES
        # =================================================

        max_transit = filtered[
            "transit_days"
        ].max()

        max_distance = filtered[
            "distance_nm"
        ].max()

        max_transshipments = filtered[
            "transshipments"
        ].max()

        # =================================================
        # ROUTE SCORE
        #
        # Higher score = better route
        #
        # Lower transit time
        # Lower distance
        # Fewer transshipments
        # =================================================

        filtered["score"] = (

            (
                max_transit
                -
                filtered["transit_days"]
            ) * 5

            +

            (
                max_distance
                -
                filtered["distance_nm"]
            ) / 100

            +

            (
                max_transshipments
                -
                filtered["transshipments"]
            ) * 10
        )

        # =================================================
        # SORT ROUTES
        # =================================================
        #
        # route_id is used as the final deterministic
        # tie-breaker.
        #
        # Example:
        # R00001 comes before R00002
        # R00231 comes before R00561
        #
        # Because route_id is stored in fixed-width format
        # in the CSV, normal string sorting works correctly.

        filtered = filtered.sort_values(
            by=[
                "score",
                "transit_days",
                "distance_nm",
                "transshipments",
                "route_id"
            ],
            ascending=[
                False,
                True,
                True,
                True,
                True
            ]
        ).reset_index(drop=True)

        # =================================================
        # CREATE ROUTE LIST
        # =================================================

        routes = []

        for index, row in filtered.iterrows():

            route_data = {

                # -------------------------------------------------
                # ROUTE RANK
                # -------------------------------------------------

                "rank":
                    index + 1,

                # -------------------------------------------------
                # RECOMMENDATION STATUS
                # The highest-scoring route is the recommendation;
                # every other valid route stays available.
                # -------------------------------------------------

                "recommendation":
                    "recommended"
                    if index == 0
                    else "available",

                # -------------------------------------------------
                # ROUTE ID
                # -------------------------------------------------
                # IMPORTANT:
                # Directly use route_id from routes.csv.
                #
                # Example:
                # R00001
                # R00231
                # R00561

                "route_id":
                    str(row["route_id"]).strip(),

                # -------------------------------------------------
                # ORIGIN
                # -------------------------------------------------

                "origin":
                    row["origin"],

                # -------------------------------------------------
                # DESTINATION
                # -------------------------------------------------

                "destination":
                    row["destination"],

                # -------------------------------------------------
                # CARGO TYPE
                # -------------------------------------------------

                "cargo_type":
                    row["cargo_type"],

                # -------------------------------------------------
                # CARGO SUBTYPE
                # -------------------------------------------------

                "cargo_subtype":
                    row["cargo_subtype"],

                # -------------------------------------------------
                # REQUESTED CARGO
                # -------------------------------------------------

                "requested_cargo_type":
                    requested_cargo,

                # -------------------------------------------------
                # ROUTE
                # -------------------------------------------------

                "route":
                    row["route"],

                # -------------------------------------------------
                # TRANSIT DAYS
                # -------------------------------------------------

                "transit_days":
                    int(row["transit_days"]),

                # -------------------------------------------------
                # DISTANCE
                # -------------------------------------------------

                "distance_nm":
                    int(row["distance_nm"]),

                # -------------------------------------------------
                # TRANSSHIPMENTS
                # -------------------------------------------------

                "transshipments":
                    int(row["transshipments"]),

                # -------------------------------------------------
                # SCORE
                # -------------------------------------------------

                "score":
                    round(
                        float(row["score"]),
                        2
                    ),

                # -------------------------------------------------
                # PORT COORDINATES
                # Exposes the real origin/destination coordinates
                # already stored in routes.csv so the frontend can
                # plot maritime routes on an ocean map. Map-only.
                # -------------------------------------------------

                "origin_latitude":
                    _safe_coord(row, "origin_latitude"),

                "origin_longitude":
                    _safe_coord(row, "origin_longitude"),

                "destination_latitude":
                    _safe_coord(row, "destination_latitude"),

                "destination_longitude":
                    _safe_coord(row, "destination_longitude"),

                # -------------------------------------------------
                # ROUTE METADATA
                # Existing CSV fields surfaced for the Maritime
                # Route Map detail view. Map-only, additive.
                # -------------------------------------------------

                "route_name":
                    _safe_text(row, "route_name"),

                "intermediate_ports":
                    _safe_text(row, "intermediate_ports"),

                "vessel_type":
                    _safe_text(row, "vessel_type"),

                "service_frequency":
                    _safe_text(row, "service_frequency"),

                "route_availability":
                    _safe_text(row, "route_availability"),

                "weather_risk":
                    _safe_text(row, "weather_risk"),

                "congestion_level":
                    _safe_text(row, "congestion_level")
            }

            routes.append(route_data)

        # =================================================
        # CHECK FOR COMPLETE TIE
        # =================================================

        is_tie = (

            filtered["transit_days"]
            .nunique()
            == 1

            and

            filtered["distance_nm"]
            .nunique()
            == 1

            and

            filtered["transshipments"]
            .nunique()
            == 1
        )

        # =================================================
        # RECOMMENDED ROUTE
        # =================================================

        recommended = routes[0]

        # =================================================
        # RECOMMENDATION REASONS
        # =================================================

        reasons = []

        # -------------------------------------------------
        # SHORTEST TRANSIT
        # -------------------------------------------------

        if (
            recommended["transit_days"]
            ==
            filtered["transit_days"].min()
        ):

            reasons.append(
                "Shortest transit time among "
                "the available routes."
            )

        # -------------------------------------------------
        # LOWEST DISTANCE
        # -------------------------------------------------

        if (
            recommended["distance_nm"]
            ==
            filtered["distance_nm"].min()
        ):

            reasons.append(
                "Lower sailing distance compared "
                "with alternative routes."
            )

        # -------------------------------------------------
        # FEWEST TRANSSHIPMENTS
        # -------------------------------------------------

        if (
            recommended["transshipments"]
            ==
            filtered["transshipments"].min()
        ):

            reasons.append(
                "Fewer transshipment stops reduce "
                "handling complexity."
            )

        # =================================================
        # BALANCED ROUTE
        # =================================================

        if not reasons:

            reasons.append(
                "Best overall balance of transit time, "
                "sailing distance and transshipments."
            )

        # =================================================
        # CARGO INFORMATION
        # =================================================

        if (
            mapped_cargo.lower()
            !=
            requested_cargo.lower()
        ):

            reasons.append(
                f"Cargo category '{requested_cargo}' "
                f"was evaluated under the maritime "
                f"category '{mapped_cargo}'."
            )

        if used_corridor_fallback:

            reasons.append(
                f"No route carries '{mapped_cargo}' "
                "cargo between the selected ports. "
                "All valid routes on this corridor "
                "were evaluated instead."
            )

        if requested_subtype:

            if subtype_matched_count > 0:

                reasons.append(
                    f"{subtype_matched_count} route(s) "
                    f"carrying '{requested_subtype}' "
                    f"were evaluated together with every "
                    "other valid route for this corridor."
                )

            else:

                reasons.append(
                    f"No route carries the selected "
                    f"subtype '{requested_subtype}' on "
                    "this corridor, so every valid "
                    "route was evaluated instead."
                )

        # =================================================
        # TIE BREAKER
        # =================================================

        if is_tie:

            reasons.append(
                "Primary route metrics are identical "
                "across the available routes. "
                "The route with the lowest route ID "
                "is selected as the recommendation."
            )

        # =================================================
        # ROUTE COUNT
        # =================================================

        if total_available_routes > 1:

            reasons.append(
                f"{total_available_routes} available "
                "routes were evaluated for this shipment."
            )

        elif total_available_routes == 1:

            reasons.append(
                "1 available route was evaluated for "
                "this shipment."
            )

        # =================================================
        # FINAL RESPONSE
        # =================================================

        return {

            # -------------------------------------------------
            # SHIPMENT INFORMATION
            # -------------------------------------------------

            "origin":
                origin,

            "destination":
                destination,

            "cargo_type":
                requested_cargo,

            "cargo_subtype":
                requested_subtype,

            "mapped_cargo_type":
                mapped_cargo,

            "containers":
                containers,

            # -------------------------------------------------
            # ROUTE COUNT
            # -------------------------------------------------

            "total_available_routes":
                total_available_routes,

            # -------------------------------------------------
            # RECOMMENDED ROUTE
            # -------------------------------------------------

            "recommended_route":
                recommended,

            # -------------------------------------------------
            # ALL ROUTES
            # -------------------------------------------------

            "routes":
                routes,

            # -------------------------------------------------
            # REASONS
            # -------------------------------------------------

            "reasons":
                reasons,

            # -------------------------------------------------
            # STATUS
            # -------------------------------------------------

            "status":
                "Recommended",

            # -------------------------------------------------
            # ANALYSIS SUMMARY
            # -------------------------------------------------

            "analysis_summary": {

                "routes_evaluated":
                    total_available_routes,

                "recommendation_method":
                    "Transit time, sailing distance, "
                    "number of transshipments and "
                    "route ranking",

                "cargo_category_used":
                    mapped_cargo,

                "tie_detected":
                    is_tie
            }
        }

    # =====================================================
    # ERROR HANDLING
    # =====================================================

    except FileNotFoundError:

        raise ValueError(
            "routes.csv was not found. "
            "Please make sure it is inside "
            "the backend/app folder."
        )

    except KeyError as error:

        raise ValueError(
            f"Required column missing from routes.csv: "
            f"{error}"
        )

    except ValueError:

        raise

    except Exception as error:

        raise ValueError(
            f"Route analysis failed: {str(error)}"
        )