# =========================================================
# CUSTOMS DATASET GENERATOR
# =========================================================
# Builds backend/app/customs.csv from backend/app/routes.csv.
#
# WHY A GENERATOR
# ---------------
# The customs dataset must never drift away from the routes
# dataset. Every customs record is therefore derived from an
# existing row of routes.csv, so:
#
#   * route_id      is a REAL route id (R00001, R00231, ...)
#   * cargo_type    is a REAL cargo_type already used by the
#                   Route Agent ("Bulk", "Containerized",
#                   "General Cargo", "Perishable", "Hazardous")
#   * cargo_subtype is a REAL cargo_subtype already used by
#                   the Route Agent (34 existing values)
#
# No route, port or cargo value is invented here.
#
# RUN
# ---
#   cd backend
#   python app/data/generate_customs.py
#
# The output is deterministic: the same routes.csv always
# produces the exact same customs.csv.
# =========================================================

import csv
import hashlib
import os


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

ROUTES_CSV_PATH = os.path.join(BASE_DIR, "routes.csv")

CUSTOMS_CSV_PATH = os.path.join(BASE_DIR, "customs.csv")


# =========================================================
# OUTPUT COLUMNS
# =========================================================
# Exactly the agreed customs dataset structure.
# customs_id is the PRIMARY KEY, route_id is the FOREIGN KEY
# back into routes.csv.
# =========================================================

CUSTOMS_COLUMNS = [
    "customs_id",
    "route_id",
    "cargo_type",
    "cargo_subtype",
    "hs_code_required",
    "commercial_invoice",
    "packing_list",
    "certificate_of_origin",
    "restricted_cargo",
    "customs_status",
]


# =========================================================
# CARGO REQUIREMENT PROFILE
# =========================================================
# Realistic customs / documentation behaviour per cargo
# subtype that ALREADY exists in routes.csv.
#
#   hs_code_required        Harmonised System classification
#                          needed for the declaration.
#   commercial_invoice      Commercial Invoice always needed.
#   packing_list            Needed for piece / container
#                          cargo. Not applicable to bulk
#                          commodities shipped loose.
#   certificate_of_origin   Needed for an international
#                          movement (see COUNTRY RULE below).
#   restricted_cargo        Cargo under import / export
#                          control by the destination.
#
# Values are written as "Yes" / "No" so the dataset stays
# readable exactly like the agreed example rows.
# =========================================================

CARGO_REQUIREMENT_PROFILE = {

    # -------------------------------------------------
    # HAZARDOUS - every movement is regulated.
    # A dangerous goods declaration, a competent authority
    # approval and an HS classification are all mandatory.
    # -------------------------------------------------

    "Compressed Gases": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "Yes",
    },
    "Corrosive Chemicals": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "Yes",
    },
    "Dangerous Goods": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "Yes",
    },
    "Explosives": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "Yes",
    },
    "Flammable Liquids": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "Yes",
    },
    "Toxic Materials": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "Yes",
    },

    # -------------------------------------------------
    # BULK - liquid bulk. No piece packing list because
    # the cargo moves in tanks, not in packages. Regulated
    # bulk (Liquefied Gas, Petroleum, Chemicals) is
    # restricted cargo.
    # -------------------------------------------------

    "Liquefied Gas": {
        "hs_code_required": "Yes",
        "packing_list": "No",
        "restricted_cargo": "Yes",
    },
    "Petroleum": {
        "hs_code_required": "Yes",
        "packing_list": "No",
        "restricted_cargo": "Yes",
    },
    "Chemicals": {
        "hs_code_required": "Yes",
        "packing_list": "No",
        "restricted_cargo": "Yes",
    },
    "Edible Oils": {
        "hs_code_required": "Yes",
        "packing_list": "No",
        "restricted_cargo": "No",
    },

    # -------------------------------------------------
    # DRY BULK - declared as a bulk commodity under the
    # commodity heading, so an item level HS breakdown is
    # not required for every shipment. Steel still needs
    # an HS classification because it is a specified
    # import in several markets.
    # -------------------------------------------------

    "Coal": {
        "hs_code_required": "No",
        "packing_list": "No",
        "restricted_cargo": "No",
    },
    "Cement": {
        "hs_code_required": "No",
        "packing_list": "No",
        "restricted_cargo": "No",
    },
    "Fertilizer": {
        "hs_code_required": "No",
        "packing_list": "No",
        "restricted_cargo": "No",
    },
    "Grain": {
        "hs_code_required": "No",
        "packing_list": "No",
        "restricted_cargo": "No",
    },
    "Iron Ore": {
        "hs_code_required": "No",
        "packing_list": "No",
        "restricted_cargo": "No",
    },
    "Steel": {
        "hs_code_required": "Yes",
        "packing_list": "No",
        "restricted_cargo": "No",
    },

    # -------------------------------------------------
    # CONTAINERIZED - piece cargo inside containers.
    # Full standard document set.
    # -------------------------------------------------

    "Automotive Parts": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Consumer Goods": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Electronics": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Industrial Equipment": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Machinery": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Textiles": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },

    # -------------------------------------------------
    # GENERAL CARGO - break bulk / project cargo.
    # Full standard document set.
    # -------------------------------------------------

    "Furniture": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Household Goods": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Industrial Goods": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Paper Products": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Retail Products": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },

    # -------------------------------------------------
    # PERISHABLE - phyto / sanitary control and a cold
    # chain certificate. Not import controlled, but
    # heavily inspected.
    # -------------------------------------------------

    "Dairy Products": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Flowers": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Fresh Fruits": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Fresh Vegetables": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Frozen Food": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Meat": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
    "Seafood": {
        "hs_code_required": "Yes",
        "packing_list": "Yes",
        "restricted_cargo": "No",
    },
}

# A Commercial Invoice is required on every commercial
# shipment regardless of cargo. Kept here (and not inside
# the profile above) so the rule is stated once.
COMMERCIAL_INVOICE_REQUIRED = "Yes"


# =========================================================
# CUSTOMS STATUS BASELINE
# =========================================================

STATUS_VALID = "Valid"
STATUS_WARNING = "Warning"
STATUS_ACTION_REQUIRED = "Action Required"


# =========================================================
# COUNTRY RULE
# =========================================================
# A Certificate of Origin proves the origin of the goods and
# is only issued for an international movement. On a purely
# domestic movement (same origin and destination country)
# no certificate of origin exists, so the requirement is No.
# =========================================================


# =========================================================
# STRICTER IMPORT MARKETS
# =========================================================
# Destination markets that apply a higher share of import
# inspections and licence checks to non restricted cargo.
# They raise the share of WARNING lanes, which is what the
# admin dashboard monitors.
# =========================================================

STRICT_IMPORT_MARKETS = {
    "USA",
    "Germany",
    "Netherlands",
    "Spain",
    "Japan",
}

# Share of the remaining lanes that are flagged.
# These are dataset weights, not customs facts about a
# specific consignment - the Customs Agent reports them as
# a lane level baseline that a broker must confirm.
STRICT_MARKET_WARNING_SHARE = 40
STANDARD_WARNING_SHARE = 18


# =========================================================
# DETERMINISTIC PSEUDO RANDOM
# =========================================================
# Python's built-in hash() is randomised per process, so a
# stable SHA-256 of the route_id is used instead. The same
# route always receives the same lane condition on every
# regeneration.
# =========================================================

def stable_percent(route_id):
    """Stable 0-99 value for a route_id."""

    digest = hashlib.sha256(
        str(route_id).encode("utf-8")
    ).hexdigest()

    return int(digest[:8], 16) % 100


# =========================================================
# STATUS DETERMINATION
# =========================================================

def resolve_customs_status(
    route_id,
    restricted_cargo,
    destination_country
):

    """
    Lane level customs condition stored in the dataset.

    * Restricted cargo can never be below Action Required -
      an import / dangerous goods permit must be obtained
      before clearance.
    * Otherwise a stable share of lanes is flagged Warning,
      and the share is higher for the stricter import
      markets listed above.
    """

    if restricted_cargo == "Yes":

        return STATUS_ACTION_REQUIRED

    threshold = STANDARD_WARNING_SHARE

    if destination_country in STRICT_IMPORT_MARKETS:

        threshold = STRICT_MARKET_WARNING_SHARE

    if stable_percent(route_id) < threshold:

        return STATUS_WARNING

    return STATUS_VALID


# =========================================================
# RECORD BUILDER
# =========================================================

def build_record(sequence, route):

    """
    Build one customs row for one routes.csv row.
    """

    route_id = str(route.get("route_id", "")).strip()

    cargo_type = str(route.get("cargo_type", "")).strip()

    cargo_subtype = str(
        route.get("cargo_subtype", "")
    ).strip()

    origin_country = str(
        route.get("origin_country", "")
    ).strip()

    destination_country = str(
        route.get("destination_country", "")
    ).strip()

    profile = CARGO_REQUIREMENT_PROFILE.get(
        cargo_subtype,
        # -------------------------------------------------
        # A subtype that is not in the profile falls back
        # to the safest standard document set. This keeps a
        # newly added routes.csv subtype usable without
        # regenerating the whole rule table.
        # -------------------------------------------------
        {
            "hs_code_required": "Yes",
            "packing_list": "Yes",
            "restricted_cargo": "No",
        }
    )

    restricted_cargo = profile["restricted_cargo"]

    is_international = (
        origin_country
        and
        destination_country
        and
        origin_country != destination_country
    )

    record = {
        "customs_id": f"C{sequence:05d}",
        "route_id": route_id,
        "cargo_type": cargo_type,
        "cargo_subtype": cargo_subtype,

        "hs_code_required": profile["hs_code_required"],

        "commercial_invoice":
            COMMERCIAL_INVOICE_REQUIRED,

        "packing_list": profile["packing_list"],

        # -------------------------------------------
        # CERTIFICATE OF ORIGIN
        # International movement  -> Required
        # Domestic movement      -> Not applicable
        # -------------------------------------------

        "certificate_of_origin": (
            "Yes" if is_international else "No"
        ),

        "restricted_cargo": restricted_cargo,

        "customs_status": resolve_customs_status(
            route_id,
            restricted_cargo,
            destination_country
        ),
    }

    return record


# =========================================================
# MAIN
# =========================================================

def main():

    if not os.path.exists(ROUTES_CSV_PATH):

        raise SystemExit(
            f"routes.csv was not found at {ROUTES_CSV_PATH}"
        )

    with open(
        ROUTES_CSV_PATH,
        "r",
        encoding="utf-8",
        newline="",
        errors="replace"
    ) as handle:

        reader = csv.DictReader(handle)

        routes = [
            row
            for row in reader
            if str(row.get("route_id", "")).strip()
        ]

    records = []

    seen_route_ids = set()

    for index, route in enumerate(routes, start=1):

        route_id = str(route["route_id"]).strip()

        if route_id in seen_route_ids:

            continue

        seen_route_ids.add(route_id)

        records.append(build_record(index, route))

    # ------------------------------------------------------------
    # customs_id must stay aligned with the route order so a
    # reviewer can read C001 -> R00001 immediately.
    # ------------------------------------------------------------

    for index, record in enumerate(records, start=1):

        record["customs_id"] = f"C{index:05d}"

    with open(
        CUSTOMS_CSV_PATH,
        "w",
        encoding="utf-8",
        newline=""
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=CUSTOMS_COLUMNS,
            lineterminator="\n"
        )

        writer.writeheader()

        writer.writerows(records)

    status_counts = {}

    for record in records:

        status = record["customs_status"]

        status_counts[status] = (
            status_counts.get(status, 0) + 1
        )

    print(
        f"customs.csv written: "
        f"{len(records)} records -> {CUSTOMS_CSV_PATH}"
    )

    print(
        "  statuses: "
        + ", ".join(
            f"{status}={count}"
            for status, count in sorted(
                status_counts.items()
            )
        )
    )

    print(f"  first row: {records[0]}")
    print(f"  last row : {records[-1]}")


if __name__ == "__main__":
    main()