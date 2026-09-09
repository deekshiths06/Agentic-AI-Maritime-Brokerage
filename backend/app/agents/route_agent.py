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
    # REMOVE EMPTY ROUTE IDs
    # -----------------------------------------------------

    df = df[
        df["route_id"].str.strip() != ""
    ].copy()

    return df


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

        origin_clean = (
            str(origin)
            .strip()
            .lower()
        )

        destination_clean = (
            str(destination)
            .strip()
            .lower()
        )

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
        # FILTER ORIGIN + DESTINATION
        # =================================================

        filtered = df[
            (
                df["origin"]
                .str.lower()
                .str.strip()
                ==
                origin_clean
            )
            &
            (
                df["destination"]
                .str.lower()
                .str.strip()
                ==
                destination_clean
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

        cargo_filtered = filtered[
            filtered["cargo_type"]
            .str.lower()
            .str.strip()
            ==
            mapped_cargo.lower()
        ].copy()

        # =================================================
        # USE ONLY CARGO-TYPE MATCHED ROUTES
        # =================================================
        # If no route carries this cargo type for the
        # selected ports, the frame stays empty and the
        # route-count check below reports no routes.

        filtered = cargo_filtered

        # =================================================
        # FILTER CARGO SUBTYPE
        # =================================================
        # Strict filter using the selected cargo subtype.
        # The dropdown is populated with real CSV subtypes,
        # so there is no silent fallback to all cargo-type
        # routes. If no route carries the selected subtype
        # for these ports, the route-count check below
        # raises an error.
        # =================================================

        if requested_subtype:

            filtered = filtered[
                filtered["cargo_subtype"]
                .str.lower()
                .str.strip()
                ==
                requested_subtype.lower()
            ].copy()

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
                    )
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