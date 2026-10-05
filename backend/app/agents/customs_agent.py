# =========================================================
# CUSTOMS AGENT
# =========================================================
# Responsibility:
# "Which customs documents does this shipment need on this
#  route, and is the shipment compliant right now?"
#
# The Customs Agent is an INDEPENDENT INTELLIGENCE MODULE.
# It never selects a route, never changes a route score and
# never touches pricing, margin, quotations or shipments.
#
# Flow
# ----
#   Selected route + cargo (route_id, origin, destination,
#   cargo_type, cargo_subtype)
#            |
#            v
#   Customs Dataset  (backend/app/customs.csv, built from
#                    backend/app/routes.csv)
#            |
#            v
#   Requirement Check + Deterministic Compliance Scoring
#            |
#            v
#   customs_status + compliance % + missing documents
#
# DATASET-DRIVEN, NOT HARD-CODED
# ------------------------------
# No customs requirement is written as a route specific rule
# in this file. Every requirement flag is read from
# customs.csv at request time, keyed on the existing route_id
# and on the existing cargo_type / cargo_subtype values.
#
# MATCHING IS ALWAYS FOUR KEY
# ---------------------------
# A customs record is located by
#
#     ORIGIN + DESTINATION + CARGO TYPE + CARGO SUBTYPE
#
# Origin + destination alone NEVER identifies a customs
# record. The agent first tries the exact four key match and
# only then the same corridor with the exact cargo pair, so
# two routes on the same lane carrying different cargo can
# never be confused with each other.
#
# AI IS NOT USED FOR RULES
# ------------------------
# The customs status, the compliance percentage and the list
# of missing documents are produced by the deterministic
# logic in this file. Gemini only turns this structured
# result into a readable advisory sentence and can never
# change a requirement.
#
# FAIL-SAFE BY DESIGN
# -------------------
# A missing dataset, a malformed row, an unknown route or an
# unsupported cargo pair never raises through the
# application. The agent returns a structured
# "not available" result so Route Intelligence, the
# Maritime Route Map, quotations and shipments keep working
# exactly as before.
# =========================================================

import logging
import os
import threading

import pandas as pd

from app.agents.route_agent import (
    normalize_cargo_type
)


logger = logging.getLogger("uvicorn.error")


# =========================================================
# DATASET LOCATIONS
# =========================================================

CUSTOMS_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "customs.csv"
)

ROUTES_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "routes.csv"
)


# Human readable labels. This data is reference data that
# ships with the project - it is never presented as a live
# customs authority feed.

CUSTOMS_DATA_SOURCE = (
    "customs.csv (static project reference dataset)"
)

CUSTOMS_DATA_NOTE = (
    "Reference customs requirement data derived from the "
    "project route dataset. This is not an official "
    "customs authority feed and always has to be confirmed "
    "with a licensed customs broker."
)


# =========================================================
# DATASET SCHEMA
# =========================================================

REQUIRED_COLUMNS = [
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

TEXT_COLUMNS = [
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
# TRACKED CUSTOMS CONTROLS
# =========================================================
# The five controls the platform monitors for every shipment.
# `column` is the customs.csv field that states whether the
# control is required for that route + cargo combination.
#
# `critical` marks a control whose absence blocks customs
# clearance. A critical gap therefore escalates the status to
# Action Required instead of only a Warning.
# =========================================================

TRACKED_CONTROLS = [
    {
        "key": "hs_code",
        "column": "hs_code_required",
        "label": "HS Code",
        "description": (
            "Harmonised System classification for the "
            "declared goods."
        ),
        "critical": True,
    },
    {
        "key": "commercial_invoice",
        "column": "commercial_invoice",
        "label": "Commercial Invoice",
        "description": (
            "Seller invoice stating the cargo value and "
            "the parties to the transaction."
        ),
        "critical": True,
    },
    {
        "key": "packing_list",
        "column": "packing_list",
        "label": "Packing List",
        "description": (
            "Package level detail of the consignment, "
            "required for piece and container cargo."
        ),
        "critical": False,
    },
    {
        "key": "certificate_of_origin",
        "column": "certificate_of_origin",
        "label": "Certificate of Origin",
        "description": (
            "Proves the country in which the goods were "
            "produced or exported."
        ),
        "critical": True,
    },
]

TRACKED_CONTROL_COUNT = len(TRACKED_CONTROLS) + 1

RESTRICTED_CONTROL_KEY = "restricted_cargo_permit"

RESTRICTED_CONTROL_LABEL = "Restricted Cargo Permit"


# =========================================================
# CUSTOMS STATUS
# =========================================================
# The three states the platform reports. A shipment is always
# reported as one of these, or as UNKNOWN when no customs
# record exists.
# =========================================================

STATUS_VALID = "Valid"
STATUS_WARNING = "Warning"
STATUS_ACTION_REQUIRED = "Action Required"
STATUS_UNKNOWN = "Unknown"

# Higher rank always wins when two rules disagree.

STATUS_RANK = {
    STATUS_VALID: 0,
    STATUS_WARNING: 1,
    STATUS_ACTION_REQUIRED: 2,
    STATUS_UNKNOWN: -1,
}

STATUS_SEQUENCE = [
    STATUS_VALID,
    STATUS_WARNING,
    STATUS_ACTION_REQUIRED,
]


# =========================================================
# NOT AVAILABLE MESSAGE
# =========================================================

NOT_AVAILABLE_MESSAGE = (
    "Customs information is unavailable for this "
    "shipment."
)


# =========================================================
# DATASET CACHE
# =========================================================
# The customs dataset is static project reference data, so it
# is read once and reused until the file changes on disk.
# This mirrors the existing Weather Agent cache.
# =========================================================

_cache_lock = threading.Lock()

_customs_cache = {
    "signature": None,
    "dataset": None,
}


def _dataset_signature():
    """File signature used to invalidate the cache."""

    try:

        stat = os.stat(CUSTOMS_CSV_PATH)

    except OSError:

        return None

    return (stat.st_mtime, stat.st_size)


# =========================================================
# SAFE READERS
# =========================================================

def _normalize(value):
    """Case and whitespace insensitive comparison key."""

    return str(value if value is not None else "").strip().lower()


def _safe_text(record, field, fallback=""):
    """Read a trimmed text field that is never None."""

    try:

        value = str(record.get(field, fallback))

        return value.strip() or fallback

    except (TypeError, ValueError, AttributeError):

        return fallback


def _parse_flag(value):
    """
    Read a Yes / No customs flag.

    Returns
    -------
    True   - explicitly required
    False  - explicitly not required
    None   - missing or unrecognised value

    None is never silently treated as False. An unreadable
    flag is reported as a dataset issue and handled as a
    required control, because an unknown customs requirement
    must never look like a cleared shipment.
    """

    normalized = _normalize(value)

    if normalized in ("yes", "y", "true", "1", "required"):
        return True

    if normalized in ("no", "n", "false", "0", "not required"):
        return False

    return None


def _parse_status(value):
    """Read a customs_status value into a known status."""

    normalized = _normalize(value)

    if not normalized:

        return None

    if "action" in normalized or "required" in normalized:
        return STATUS_ACTION_REQUIRED

    if "warn" in normalized:
        return STATUS_WARNING

    if "valid" in normalized or "clear" in normalized:
        return STATUS_VALID

    return None


# =========================================================
# DATASET LOADING
# =========================================================

def _clean_customs_frame(df):
    """
    Normalize the customs dataset: lowercase column names,
    trimmed text values and a dropped empty row. Malformed
    rows are reported, never fatal.
    """

    df.columns = df.columns.str.strip().str.lower()

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "customs.csv is missing required column(s): "
            + ", ".join(missing)
        )

    df = df.copy()

    for column in TEXT_COLUMNS:

        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # A row without a primary key or a foreign key is not
    # usable and is dropped here.
    df = df[
        (df["customs_id"] != "")
        & (df["route_id"] != "")
    ].copy()

    return df


def _load_route_index():
    """
    Small lookup built from the EXISTING routes.csv so the
    customs module can show origin and destination without
    ever duplicating or inventing a port.

    Returns {} when routes.csv cannot be read. The customs
    dataset itself stays fully usable in that case.
    """

    try:

        routes_df = pd.read_csv(ROUTES_CSV_PATH)

        routes_df.columns = (
            routes_df.columns.str.strip().str.lower()
        )

    except Exception as load_error:

        logger.warning(
            "Route index unavailable for customs: %s",
            load_error
        )

        return {}

    index = {}

    for _, row in routes_df.iterrows():

        route_id = _safe_text(row.to_dict(), "route_id")

        if not route_id or route_id in index:
            continue

        index[route_id] = {
            "origin": _safe_text(row.to_dict(), "origin"),
            "destination": _safe_text(
                row.to_dict(), "destination"
            ),
        }

    return index


def load_customs_dataset():
    """
    Return the indexed customs dataset.

    Never raises. A missing or unreadable dataset resolves to
    an empty index so every caller can degrade gracefully.
    """

    signature = _dataset_signature()

    with _cache_lock:

        if (
            _customs_cache["dataset"] is not None
            and _customs_cache["signature"] == signature
        ):

            return _customs_cache["dataset"]

    dataset = {
        "records": [],
        "by_customs_id": {},
        "by_route_id": {},
        "by_corridor_cargo": {},
        "route_index": {},
        "route_count": 0,
        "cargo_types": [],
        "cargo_subtypes": [],
        "statuses": [],
        "dataset_error": None,
        "invalid_records": [],
    }

    frame = None

    try:

        if signature is None:

            raise FileNotFoundError(
                f"customs.csv was not found at "
                f"{CUSTOMS_CSV_PATH}"
            )

        frame = _clean_customs_frame(
            pd.read_csv(CUSTOMS_CSV_PATH)
        )

    except Exception as load_error:

        logger.warning(
            "Customs dataset unavailable: %s", load_error
        )

        dataset["dataset_error"] = str(load_error)

        with _cache_lock:

            _customs_cache["signature"] = signature
            _customs_cache["dataset"] = dataset

        return dataset

    invalid_records = []

    # -----------------------------------------------------
    # ROUTE IDENTITY IS LOADED FIRST
    #
    # The customs dataset deliberately stores no port of its
    # own. Origin and destination are read from the EXISTING
    # routes dataset through route_id, so a port can never
    # drift away from the route it belongs to.
    # -----------------------------------------------------

    route_index = _load_route_index()

    dataset["route_index"] = route_index

    for _, row in frame.iterrows():

        record = row.to_dict()

        customs_id = _safe_text(record, "customs_id")

        route_id = _safe_text(record, "route_id")

        # -------------------------------------------------
        # PRIMARY KEY / FOREIGN KEY INTEGRITY
        # A duplicate customs_id or a missing route_id makes
        # the record unusable, so it is skipped and reported.
        # -------------------------------------------------

        if customs_id in dataset["by_customs_id"]:

            invalid_records.append({
                "customs_id": customs_id,
                "route_id": route_id,
                "issue": "Duplicate customs_id",
            })

            continue

        issues = []

        for column in REQUIRED_COLUMNS[4:9]:

            if _parse_flag(record.get(column)) is None:

                issues.append(
                    f"Invalid value in '{column}'"
                )

        if _parse_status(
            record.get("customs_status")
        ) is None:

            issues.append("Invalid customs_status")

        if issues:

            invalid_records.append({
                "customs_id": customs_id,
                "route_id": route_id,
                "issue": "; ".join(issues),
            })

        dataset["by_customs_id"][customs_id] = record

        # route_id can carry several cargo records, so the
        # index keeps the first record deterministically
        # (rows arrive in customs_id order).
        dataset["by_route_id"].setdefault(route_id, record)

        route_info = route_index.get(route_id, {})

        # -------------------------------------------------
        # FOUR KEY MATCH INDEX
        #
        # origin + destination + cargo_type + cargo_subtype
        # -------------------------------------------------

        corridor_key = (
            _normalize(route_info.get("origin")) or "",
            _normalize(route_info.get("destination")) or "",
            _normalize(
                normalize_cargo_type(
                    record.get("cargo_type", "")
                )
            ) or "",
            _normalize(record.get("cargo_subtype")) or "",
        )

        dataset["by_corridor_cargo"].setdefault(
            corridor_key, []
        ).append(record)

    dataset["records"] = list(
        dataset["by_customs_id"].values()
    )

    dataset["route_count"] = len(
        dataset["by_route_id"]
    )

    dataset["invalid_records"] = invalid_records

    dataset["cargo_types"] = sorted(
        {
            _safe_text(record, "cargo_type")
            for record in dataset["records"]
            if _safe_text(record, "cargo_type")
        }
    )

    dataset["cargo_subtypes"] = sorted(
        {
            _safe_text(record, "cargo_subtype")
            for record in dataset["records"]
            if _safe_text(record, "cargo_subtype")
        }
    )

    dataset["statuses"] = [
        status
        for status in STATUS_SEQUENCE
        if any(
            _parse_status(record.get("customs_status"))
            == status
            for record in dataset["records"]
        )
    ]

    with _cache_lock:

        _customs_cache["signature"] = signature
        _customs_cache["dataset"] = dataset

    return dataset


# =========================================================
# ROUTE IDENTITY
# =========================================================

def _corridor_key(origin, destination, cargo_type, cargo_subtype):
    """
    Build the four key customs match key.

    Origin + destination alone is never enough: cargo type and
    cargo subtype are always part of the key.
    """

    return (
        _normalize(origin) or "",
        _normalize(destination) or "",
        _normalize(
            normalize_cargo_type(cargo_type)
        ) or "",
        _normalize(cargo_subtype) or "",
    )


def _cargo_matches(record, cargo_type, cargo_subtype):
    """
    Cargo comparison used by the matching stage.

    The cargo_type is compared through the existing Route
    Agent mapping so a frontend alias and a dataset value
    resolve to the same category. Both the direct value and
    the mapped value are accepted, which keeps the customs
    module consistent with the Route Agent.
    """

    record_cargo = _normalize(record.get("cargo_type"))

    requested = _normalize(cargo_type)

    mapped = _normalize(normalize_cargo_type(cargo_type))

    if requested not in (record_cargo, mapped):

        return False

    record_subtype = _normalize(
        record.get("cargo_subtype")
    )

    requested_subtype = _normalize(cargo_subtype)

    if record_subtype != requested_subtype:

        return False

    return True


def _cargo_type_not_matched(clean_cargo_type, record_cargo_type):
    """
    Admin cargo_type filter comparison.

    Both the requested value and the requested value mapped
    through the existing Route Agent mapping are accepted, so
    the admin filter works with a dataset value and with a
    frontend alias alike.
    """

    if not clean_cargo_type:

        return False

    accepted = {
        clean_cargo_type,
        _normalize(normalize_cargo_type(clean_cargo_type)),
    }

    if _normalize(record_cargo_type) in accepted:

        return False

    return _normalize(
        normalize_cargo_type(record_cargo_type)
    ) not in accepted


def _route_identity(dataset, record):
    """
    Resolve origin / destination for a record from the EXISTING
    routes dataset. The customs dataset deliberately stores no
    port of its own, so a port can never drift away from the
    route dataset.
    """

    route_id = _safe_text(record, "route_id")

    route_info = dataset["route_index"].get(
        route_id, {}
    )

    return (
        route_info.get("origin") or None,
        route_info.get("destination") or None,
    )


# =========================================================
# RECORD MATCHING
# =========================================================

def match_customs_record(
    origin,
    destination,
    cargo_type,
    cargo_subtype,
    route_id=""
):
    """
    Locate the customs record for one shipment.

    Matching stages, in order:

      1. route_id + origin + destination + cargo_type +
         cargo_subtype     -> match_type "route_and_cargo"
      2. origin + destination + cargo_type + cargo_subtype
                          -> match_type "corridor_cargo"

    Origin + destination on its own is never a match, and a
    corridor that carries the cargo type but not the selected
    subtype is never a match either.

    Returns
    -------
    (record | None, match_type)
    """

    dataset = load_customs_dataset()

    if not dataset["records"]:

        return None, "dataset_unavailable"

    clean_route_id = _safe_text({"route_id": route_id}, "route_id")

    clean_cargo_type = str(cargo_type or "").strip()

    clean_cargo_subtype = str(cargo_subtype or "").strip()

    # -----------------------------------------------------
    # STAGE 1 - EXACT ROUTE AND CARGO
    # -----------------------------------------------------

    if clean_route_id:

        record = dataset["by_route_id"].get(clean_route_id)

        if record and _cargo_matches(
            record,
            clean_cargo_type,
            clean_cargo_subtype
        ):

            return record, "route_and_cargo"

    # -----------------------------------------------------
    # STAGE 2 - SAME CORRIDOR, SAME CARGO TYPE + SUBTYPE
    #
    # The Route Agent may recommend a neighbouring route that
    # carries a different subtype. The customs requirement is
    # then taken from the record of the exact cargo pair on
    # the same corridor. The fallback is still bounded by
    # cargo type AND cargo subtype, never by the corridor
    # alone.
    # -----------------------------------------------------

    if not (
        _normalize(origin)
        and _normalize(destination)
    ):

        return None, "insufficient_request"

    candidates = dataset["by_corridor_cargo"].get(
        _corridor_key(
            origin,
            destination,
            clean_cargo_type,
            clean_cargo_subtype
        ),
        []
    )

    for record in sorted(
        candidates,
        key=lambda item: _safe_text(item, "customs_id")
    ):

        if _cargo_matches(
            record,
            clean_cargo_type,
            clean_cargo_subtype
        ):

            return record, "corridor_cargo"

    return None, "no_match"


def _resolve_no_match_reason(
    dataset,
    origin,
    destination,
    cargo_type,
    cargo_subtype,
    route_id
):
    """
    Explain precisely why no customs record matched, so the
    user never sees an unrelated customs record.
    """

    if dataset["dataset_error"]:

        return (
            "The customs dataset could not be read. "
            "Route intelligence and quotations are "
            "unaffected."
        )

    if not (
        _normalize(origin) and _normalize(destination)
    ):

        return (
            "Origin and destination are both required "
            "before customs requirements can be retrieved."
        )

    clean_cargo_type = str(cargo_type or "").strip()

    clean_cargo_subtype = str(cargo_subtype or "").strip()

    if not clean_cargo_type or not clean_cargo_subtype:

        return (
            "Cargo type and cargo subtype are both required "
            "before customs requirements can be retrieved."
        )

    clean_route_id = str(route_id or "").strip()

    route_exists = clean_route_id in dataset["by_route_id"]

    corridor_exists = any(
        key[0] == _normalize(origin)
        and key[1] == _normalize(destination)
        for key in dataset["by_corridor_cargo"]
    )

    if route_exists and not corridor_exists:

        return (
            f"No customs record matches {origin} to "
            f"{destination}. The route exists in the route "
            "dataset but this corridor has no customs "
            "coverage."
        )

    if not route_exists and clean_route_id:

        return (
            f"Route {clean_route_id} has no customs record "
            "in the customs dataset."
        )

    cargo_on_corridor = any(
        key[0] == _normalize(origin)
        and key[1] == _normalize(destination)
        and key[2] in (
            _normalize(cargo_type),
            _normalize(normalize_cargo_type(cargo_type))
        )
        for key in dataset["by_corridor_cargo"]
    )

    if not cargo_on_corridor:

        return (
            f"{clean_cargo_type} cargo is not supported on "
            f"the {origin} to {destination} corridor, so no "
            "customs requirements can be shown."
        )

    return (
        f"No customs information is published for "
        f"{clean_cargo_subtype} {clean_cargo_type} cargo on "
        f"the {origin} to {destination} corridor."
    )


# =========================================================
# DETERMINISTIC REQUIREMENT EVALUATION
# =========================================================

def _document_confirmed(documents, key):
    """
    Read the declared availability of one document.

    documents is the map the frontend sends after the shipper
    confirms their document set. When the map is absent the
    standard document set is treated as on hand, which keeps a
    direct API call useful without any extra input.
    """

    if not isinstance(documents, dict):

        return True

    value = documents.get(key)

    if value is None:

        return True

    if isinstance(value, bool):

        return value

    return _parse_flag(value) is True


def evaluate_requirements(record, documents=None):
    """
    Turn one customs record into a deterministic checklist.

    Every requirement comes from the dataset. The document
    availability comes from the shipper. Nothing is guessed.
    """

    checklist = []

    missing = []

    data_issues = []

    required_controls = 0

    satisfied_controls = 0

    restricted_flag = _parse_flag(
        record.get("restricted_cargo")
    )

    if restricted_flag is None:

        data_issues.append(
            "Dataset value for 'restricted_cargo' is "
            "missing or invalid; treated as restricted."
        )

    for control in TRACKED_CONTROLS:

        required = _parse_flag(
            record.get(control["column"])
        )

        if required is None:

            data_issues.append(
                f"Dataset value for '{control['column']}' is "
                "missing or invalid; treated as required."
            )

            required = True

        if not required:

            checklist.append({
                "key": control["key"],
                "label": control["label"],
                "description": control["description"],
                "critical": control["critical"],
                "required": False,
                "value": "Not Required",
                "state": "not_required",
                "state_label": "Not Required",
            })

            continue

        required_controls += 1

        confirmed = _document_confirmed(
            documents, control["key"]
        )

        if confirmed:

            satisfied_controls += 1

            state = "available"
            state_label = "Available"

        else:

            state = "missing"
            state_label = "Missing"

            missing.append({
                "key": control["key"],
                "label": control["label"],
                "description": control["description"],
                "critical": control["critical"],
                "requirement": (
                    "Required for this route and cargo "
                    "combination."
                ),
            })

        checklist.append({
            "key": control["key"],
            "label": control["label"],
            "description": control["description"],
            "critical": control["critical"],
            "required": True,
            "value": "Required",
            "state": state,
            "state_label": state_label,
        })

    # -----------------------------------------------------
    # RESTRICTED CARGO CONTROL
    #
    # Not restricted -> the row reports "Not Restricted".
    # Restricted     -> a permit becomes a required control.
    # -----------------------------------------------------

    if restricted_flag:

        required_controls += 1

        confirmed = _document_confirmed(
            documents, RESTRICTED_CONTROL_KEY
        )

        if confirmed:

            satisfied_controls += 1

            state = "available"
            state_label = "Permit On Hand"

        else:

            state = "missing"
            state_label = "Permit Required"

            missing.append({
                "key": RESTRICTED_CONTROL_KEY,
                "label": RESTRICTED_CONTROL_LABEL,
                "description": (
                    "Restricted cargo under destination "
                    "country control. A permit or competent "
                    "authority approval is mandatory."
                ),
                "critical": True,
                "requirement": (
                    "Restricted cargo cannot be cleared "
                    "without this permit."
                ),
            })

        checklist.append({
            "key": RESTRICTED_CONTROL_KEY,
            "label": RESTRICTED_CONTROL_LABEL,
            "description": (
                "Permit or competent authority approval "
                "for restricted cargo."
            ),
            "critical": True,
            "required": True,
            "value": "Restricted",
            "state": state,
            "state_label": state_label,
        })

    else:

        checklist.append({
            "key": "restricted_cargo",
            "label": "Restricted Cargo",
            "description": (
                "Cargo under destination country import "
                "control."
            ),
            "critical": False,
            "required": False,
            "value": "Not Restricted",
            "state": "not_restricted",
            "state_label": "Not Restricted",
        })

    # -----------------------------------------------------
    # COMPLIANCE PERCENTAGE
    #
    # Only the controls that actually apply to this route and
    # cargo combination are counted, so a bulk commodity is
    # never penalised for a packing list that does not exist
    # for it.
    # -----------------------------------------------------

    if required_controls:

        compliance_percent = round(
            (satisfied_controls / required_controls) * 100
        )

    else:

        # A lane with no control to satisfy is treated as
        # fully compliant rather than as an error.
        compliance_percent = 100

    return {
        "checklist": checklist,
        "missing": missing,
        "missing_count": len(missing),
        "required_controls": required_controls,
        "satisfied_controls": satisfied_controls,
        "tracked_controls": TRACKED_CONTROL_COUNT,
        "compliance_percent": compliance_percent,
        "restricted_cargo": bool(restricted_flag),
        "data_issues": data_issues,
        "document_declaration": (
            "Confirmed"
            if isinstance(documents, dict)
            else "Assumed"
        ),
    }


# =========================================================
# DETERMINISTIC STATUS RESOLUTION
# =========================================================

def resolve_customs_status(evaluation, dataset_status):
    """
    Combine the lane condition stored in the dataset with the
    document gaps of this shipment.

    The highest ranked condition always wins, so a shipment
    can never be reported as clearer than the lane allows.
    """

    reasons = []

    baseline = dataset_status or STATUS_UNKNOWN

    if baseline == STATUS_UNKNOWN:

        reasons.append(
            "The customs dataset does not state a lane "
            "condition for this route and cargo combination."
        )

    status = baseline

    if evaluation["restricted_cargo"]:

        status = _worst(
            status, STATUS_ACTION_REQUIRED
        )

        reasons.append(
            "This cargo is restricted under destination "
            "country control, so clearance cannot proceed "
            "without the permit."
        )

    critical_missing = [
        item
        for item in evaluation["missing"]
        if item.get("critical")
    ]

    other_missing = [
        item
        for item in evaluation["missing"]
        if not item.get("critical")
    ]

    if critical_missing:

        status = _worst(
            status, STATUS_ACTION_REQUIRED
        )

        reasons.append(
            "A control that blocks customs clearance is "
            "missing: "
            + ", ".join(
                item["label"] for item in critical_missing
            )
            + "."
        )

    elif other_missing:

        status = _worst(status, STATUS_WARNING)

        reasons.append(
            "A supporting document is missing: "
            + ", ".join(
                item["label"] for item in other_missing
            )
            + "."
        )

    if baseline == STATUS_ACTION_REQUIRED:

        reasons.append(
            "The customs dataset flags this route and cargo "
            "combination as Action Required."
        )

    elif baseline == STATUS_WARNING:

        reasons.append(
            "The customs dataset flags this route and cargo "
            "combination as Warning."
        )

    elif baseline == STATUS_VALID and not evaluation["missing"]:

        reasons.append(
            "Every applicable customs requirement is "
            "satisfied and the dataset flags no customs "
            "restriction on this lane."
        )

    return status, reasons


def _worst(first, second):
    """Return the more severe of two statuses."""

    if STATUS_RANK.get(first, -1) >= STATUS_RANK.get(second, -1):

        return first

    return second


# =========================================================
# DETERMINISTIC ADVISORY
# =========================================================
# This text is always available, with or without Gemini. It is
# written only from the structured result, so it can never
# state a requirement the dataset does not contain.
# =========================================================

def build_deterministic_advisory(
    origin,
    destination,
    cargo_type,
    cargo_subtype,
    status,
    evaluation
):
    """Compose the baseline advisory from the actual result."""

    lane = (
        f"the {origin} to {destination} lane carrying "
        f"{cargo_subtype} {cargo_type} cargo"
    )

    missing_labels = [
        item["label"]
        for item in evaluation["missing"]
    ]

    if not missing_labels and evaluation["restricted_cargo"]:

        return (
            f"Your shipment on {lane} is restricted cargo. "
            "The required permit is on hand and every "
            "applicable customs document is available, so "
            f"customs status is {status}. Keep the permit "
            "and the commercial invoice ready for inspection."
        )

    if not missing_labels:

        return (
            f"Your shipment on {lane} meets every customs "
            "requirement that applies to this route and "
            f"cargo combination, so customs status is "
            f"{status}. No customs document is outstanding."
        )

    if len(missing_labels) == 1:

        subject = missing_labels[0]

        sentence = (
            f"Your shipment is missing the {subject}."
        )

    else:

        joined = ", ".join(missing_labels[:-1])

        subject = missing_labels[-1]

        sentence = (
            f"Your shipment is missing the {joined} and "
            f"the {subject}."
        )

    if status == STATUS_ACTION_REQUIRED:

        closing = (
            "Please provide the required documents before "
            "customs clearance."
        )

    else:

        closing = (
            "Please arrange the outstanding documents "
            "before cargo is tendered to the vessel."
        )

    return f"{sentence} {closing}"


# =========================================================
# UNAVAILABLE PAYLOAD
# =========================================================

def _unavailable(message, **extra):
    """
    Standard graceful 'no customs' payload.

    The shape is identical to a successful result so the
    frontend never has to special case a missing dataset.
    """

    payload = {
        "status": "not_found",
        "available": False,
        "match_type": "no_match",

        "customs_id": None,
        "route_id": None,
        "origin": None,
        "destination": None,
        "cargo_type": None,
        "cargo_subtype": None,

        "hs_code_required": None,
        "commercial_invoice": None,
        "packing_list": None,
        "certificate_of_origin": None,
        "restricted_cargo": None,
        "restricted": False,

        "customs_status": STATUS_UNKNOWN,
        "customs_status_rank": STATUS_RANK[STATUS_UNKNOWN],
        "compliance_percent": None,
        "compliance_basis": None,

        "checklist": [],
        "missing": [],
        "missing_count": 0,
        "required_controls": 0,
        "satisfied_controls": 0,
        "tracked_controls": TRACKED_CONTROL_COUNT,
        "document_declaration": "None",

        "status_reasons": [],
        "message": message,
        "advisory": NOT_AVAILABLE_MESSAGE,
        "advisory_source": "deterministic",
        "data_issues": [],
        "data_source": CUSTOMS_DATA_SOURCE,
        "data_note": CUSTOMS_DATA_NOTE,
    }

    payload.update(extra)

    return payload


# =========================================================
# MAIN ENTRY POINT
# =========================================================

def analyze_customs(
    origin,
    destination,
    cargo_type,
    cargo_subtype,
    route_id="",
    documents=None
):
    """
    Evaluate the customs requirements of one shipment.

    Parameters
    ----------
    origin, destination : str
        Ports selected by the user.
    cargo_type, cargo_subtype : str
        Cargo selected by the user. Both are part of the
        match key, together with origin and destination.
    route_id : str
        Recommended route from the Route Agent. Used for the
        exact four key match when it is available.
    documents : dict | None
        Declared document set, keyed by control key
        (hs_code, commercial_invoice, packing_list,
        certificate_of_origin, restricted_cargo_permit).

    Returns
    -------
    dict
        Structured customs result. Always returned, never
        raised, so an unavailable dataset can never break the
        surrounding application.
    """

    try:

        clean_origin = str(origin or "").strip()

        clean_destination = str(destination or "").strip()

        clean_cargo_type = str(cargo_type or "").strip()

        clean_cargo_subtype = str(cargo_subtype or "").strip()

        clean_route_id = str(route_id or "").strip()

        dataset = load_customs_dataset()

        record, match_type = match_customs_record(
            clean_origin,
            clean_destination,
            clean_cargo_type,
            clean_cargo_subtype,
            route_id=clean_route_id
        )

        # -------------------------------------------------
        # NO CUSTOMS RECORD
        # -------------------------------------------------

        if record is None:

            reason = _resolve_no_match_reason(
                dataset,
                clean_origin,
                clean_destination,
                clean_cargo_type,
                clean_cargo_subtype,
                clean_route_id
            )

            return _unavailable(
                reason,
                match_type=match_type,
                requested={
                    "origin": clean_origin or None,
                    "destination": clean_destination or None,
                    "cargo_type": clean_cargo_type or None,
                    "cargo_subtype": clean_cargo_subtype or None,
                    "route_id": clean_route_id or None,
                },
                dataset_error=dataset["dataset_error"],
            )

        # -------------------------------------------------
        # DETERMINISTIC EVALUATION
        # -------------------------------------------------

        evaluation = evaluate_requirements(
            record, documents=documents
        )

        dataset_status = _parse_status(
            record.get("customs_status")
        )

        status, reasons = resolve_customs_status(
            evaluation, dataset_status
        )

        resolved_origin, resolved_destination = (
            _route_identity(dataset, record)
        )

        result = {
            "status": "success",
            "available": True,
            "match_type": match_type,

            "customs_id": _safe_text(
                record, "customs_id"
            ) or None,
            "route_id": _safe_text(
                record, "route_id"
            ) or None,

            "origin": resolved_origin or clean_origin or None,
            "destination": (
                resolved_destination
                or clean_destination
                or None
            ),
            "cargo_type": _safe_text(
                record, "cargo_type"
            ) or None,
            "cargo_subtype": _safe_text(
                record, "cargo_subtype"
            ) or None,

            # -------------------------------------------
            # ORIGINAL DATASET VALUES
            # -------------------------------------------

            "hs_code_required": _safe_text(
                record, "hs_code_required"
            ) or None,
            "commercial_invoice": _safe_text(
                record, "commercial_invoice"
            ) or None,
            "packing_list": _safe_text(
                record, "packing_list"
            ) or None,
            "certificate_of_origin": _safe_text(
                record, "certificate_of_origin"
            ) or None,
            "restricted_cargo": _safe_text(
                record, "restricted_cargo"
            ) or None,

            # Boolean form of the same dataset field. Kept
            # separately so a consumer never has to treat
            # the "Yes" / "No" text as a boolean.
            "restricted": evaluation["restricted_cargo"],

            # -------------------------------------------
            # CALCULATED CUSTOMS RESULT
            # -------------------------------------------

            "customs_status": status,
            "customs_status_rank": STATUS_RANK[status],
            "compliance_percent":
                evaluation["compliance_percent"],
            "compliance_basis": (
                "Share of the applicable customs controls "
                "that are satisfied for this shipment."
            ),

            "checklist": evaluation["checklist"],
            "missing": evaluation["missing"],
            "missing_count": evaluation["missing_count"],
            "required_controls":
                evaluation["required_controls"],
            "satisfied_controls":
                evaluation["satisfied_controls"],
            "tracked_controls":
                evaluation["tracked_controls"],
            "document_declaration":
                evaluation["document_declaration"],

            "status_reasons": reasons,

            "message": (
                "Customs requirements retrieved from the "
                "customs dataset."
            ),

            # -------------------------------------------
            # DETERMINISTIC ADVISORY
            #
            # Always present. Gemini may replace this text
            # with a richer explanation of the SAME facts,
            # and its absence never changes the result.
            # -------------------------------------------

            "advisory": build_deterministic_advisory(
                resolved_origin or clean_origin,
                resolved_destination or clean_destination,
                _safe_text(record, "cargo_type")
                or clean_cargo_type,
                _safe_text(record, "cargo_subtype")
                or clean_cargo_subtype,
                status,
                evaluation
            ),
            "advisory_source": "deterministic",

            "data_issues": evaluation["data_issues"],
            "data_source": CUSTOMS_DATA_SOURCE,
            "data_note": CUSTOMS_DATA_NOTE,
        }

        return result

    except Exception as error:

        # The customs module is additional compliance
        # intelligence. It never breaks the surrounding
        # application.
        logger.warning(
            "Customs analysis error: %s", error
        )

        return _unavailable(
            "Customs information is currently unavailable "
            "for this shipment.",
            dataset_error=str(error),
        )


# =========================================================
# LANE COVERAGE
# =========================================================
# Compliance shown for a customs RECORD.
#
# A customs record holds requirements, not a shipper's
# document set, so a percentage of a ship's documents cannot
# be derived from a lane. What IS meaningful, and what an
# admin monitors here, is how much of the tracked customs
# control set actually applies to the lane.
#
#   compliance_percent =
#       required controls for this lane / 5 tracked controls
# =========================================================

COMPLIANCE_BASIS_RECORD = (
    "Share of the 5 tracked customs controls that apply "
    "to this route and cargo combination."
)


def _record_coverage(record):
    """Required control count for one record."""

    required_controls = 0

    data_issues = []

    for control in TRACKED_CONTROLS:

        flag = _parse_flag(record.get(control["column"]))

        if flag is None:

            data_issues.append(
                f"Invalid value in '{control['column']}'"
            )

            flag = True

        if flag:

            required_controls += 1

    restricted = _parse_flag(
        record.get("restricted_cargo")
    )

    if restricted is None:

        data_issues.append(
            "Invalid value in 'restricted_cargo'"
        )

        restricted = True

    if restricted:

        required_controls += 1

    compliance_percent = round(
        (required_controls / TRACKED_CONTROL_COUNT) * 100
    )

    return compliance_percent, required_controls, data_issues


# =========================================================
# ADMIN RECORD LISTING
# =========================================================

def list_customs_records(
    route_id="",
    origin="",
    destination="",
    cargo_type="",
    cargo_subtype="",
    customs_status="",
    restricted_cargo="",
    search="",
    limit=0
):
    """
    Return customs records for the admin dashboard with the
    requested filters applied.

    Every filter is optional and they combine with AND. An
    unreadable filter value simply matches nothing, so the
    admin table can never show an unrelated record.
    """

    dataset = load_customs_dataset()

    if dataset["dataset_error"]:

        return {
            "available": False,
            "dataset_error": dataset["dataset_error"],
            "customs": [],
            "total": 0,
            "returned": 0,
            "filters": _filter_options(dataset),
            "summary": _summary(dataset),
            "data_source": CUSTOMS_DATA_SOURCE,
            "data_note": CUSTOMS_DATA_NOTE,
        }

    clean_route_id = _normalize(route_id)

    clean_origin = _normalize(origin)

    clean_destination = _normalize(destination)

    clean_cargo_type = _normalize(cargo_type)

    clean_cargo_subtype = _normalize(cargo_subtype)

    clean_status = _normalize(customs_status)

    clean_restricted = _parse_flag(restricted_cargo)

    clean_search = _normalize(search)

    rows = []

    for record in dataset["records"]:

        resolved_origin, resolved_destination = (
            _route_identity(dataset, record)
        )

        record_route_id = _safe_text(record, "route_id")

        record_cargo_type = _safe_text(
            record, "cargo_type"
        )

        record_cargo_subtype = _safe_text(
            record, "cargo_subtype"
        )

        if clean_route_id and _normalize(
            record_route_id
        ) != clean_route_id:

            continue

        if clean_origin and _normalize(
            resolved_origin
        ) != clean_origin:

            continue

        if clean_destination and _normalize(
            resolved_destination
        ) != clean_destination:

            continue

        if clean_cargo_type and _cargo_type_not_matched(
            clean_cargo_type, record_cargo_type
        ):

            continue

        if clean_cargo_subtype and _normalize(
            record_cargo_subtype
        ) != clean_cargo_subtype:

            continue

        record_status = _parse_status(
            record.get("customs_status")
        ) or STATUS_UNKNOWN

        if clean_status and _normalize(
            record_status
        ) != clean_status:

            continue

        record_restricted = _parse_flag(
            record.get("restricted_cargo")
        )

        if clean_restricted is not None and bool(
            record_restricted
        ) != clean_restricted:

            continue

        if clean_search:

            haystack = " ".join([
                _safe_text(record, "customs_id"),
                record_route_id,
                resolved_origin or "",
                resolved_destination or "",
                record_cargo_type,
                record_cargo_subtype,
                record_status,
            ]).lower()

            if clean_search not in haystack:

                continue

        compliance_percent, required_controls, data_issues = (
            _record_coverage(record)
        )

        rows.append({
            "customs_id": _safe_text(
                record, "customs_id"
            ),
            "route_id": record_route_id or None,
            "origin": resolved_origin,
            "destination": resolved_destination,
            "cargo_type": record_cargo_type or None,
            "cargo_subtype": record_cargo_subtype or None,
            "hs_code_required": _safe_text(
                record, "hs_code_required"
            ) or None,
            "commercial_invoice": _safe_text(
                record, "commercial_invoice"
            ) or None,
            "packing_list": _safe_text(
                record, "packing_list"
            ) or None,
            "certificate_of_origin": _safe_text(
                record, "certificate_of_origin"
            ) or None,
            "restricted_cargo": (
                "Yes" if record_restricted else "No"
            ),

            # Boolean form of the same dataset field, so
            # the admin table never has to compare the
            # "Yes" / "No" text itself.
            "restricted": record_restricted,

            "customs_status": record_status,
            "compliance_percent": compliance_percent,
            "compliance_basis": COMPLIANCE_BASIS_RECORD,
            "required_controls": required_controls,
            "tracked_controls": TRACKED_CONTROL_COUNT,
            "data_issues": data_issues,
        })

    rows.sort(key=lambda item: item["customs_id"])

    total = len(rows)

    if limit and limit > 0:

        rows = rows[:limit]

    return {
        "available": True,
        "dataset_error": None,
        "customs": rows,
        "total": total,
        "returned": len(rows),
        "filters": _filter_options(dataset),
        "summary": _summary(dataset),
        "data_source": CUSTOMS_DATA_SOURCE,
        "data_note": CUSTOMS_DATA_NOTE,
    }


def _filter_options(dataset):
    """Dropdown options for the admin customs filters."""

    origins = set()

    destinations = set()

    for route_info in dataset["route_index"].values():

        if route_info.get("origin"):
            origins.add(route_info["origin"])

        if route_info.get("destination"):
            destinations.add(route_info["destination"])

    return {
        "cargo_types": dataset["cargo_types"],
        "cargo_subtypes": dataset["cargo_subtypes"],
        "customs_statuses": dataset["statuses"],
        "origins": sorted(origins),
        "destinations": sorted(destinations),
    }


def _summary(dataset):
    """Dataset wide counters for the admin dashboard."""

    counts = {
        STATUS_VALID: 0,
        STATUS_WARNING: 0,
        STATUS_ACTION_REQUIRED: 0,
    }

    restricted_total = 0

    for record in dataset["records"]:

        status = _parse_status(
            record.get("customs_status")
        )

        if status in counts:

            counts[status] += 1

        if _parse_flag(record.get("restricted_cargo")):

            restricted_total += 1

    return {
        "total_records": len(dataset["records"]),
        "total_routes": dataset["route_count"],
        "valid_records": counts[STATUS_VALID],
        "warning_records": counts[STATUS_WARNING],
        "action_required_records":
            counts[STATUS_ACTION_REQUIRED],
        "restricted_records": restricted_total,
        "invalid_records": len(dataset["invalid_records"]),
    }


def get_customs_summary():
    """Dataset coverage and status counters (read-only)."""

    dataset = load_customs_dataset()

    return {
        "available": not bool(dataset["dataset_error"]),
        "dataset_error": dataset["dataset_error"],
        "summary": _summary(dataset),
        "filters": _filter_options(dataset),
        "invalid_records": dataset["invalid_records"][:50],
        "controls": [
            {
                "key": control["key"],
                "label": control["label"],
                "description": control["description"],
                "critical": control["critical"],
            }
            for control in TRACKED_CONTROLS
        ],
        "statuses": STATUS_SEQUENCE,
        "data_source": CUSTOMS_DATA_SOURCE,
        "data_note": CUSTOMS_DATA_NOTE,
    }