# =========================================================
# EXECUTIVE DASHBOARD
# =========================================================
# Pure aggregation layer for the admin Executive Dashboard.
#
# The endpoint in main.py is a thin transport: it reads the
# real counts and recent records from MongoDB and passes them
# into ::build_executive_report, which computes every KPI,
# funnel step, status distribution, weekly trend and top-lane
# figure here. Keeping the arithmetic in a pure function makes
# the dashboard fully testable with fixture records (matching
# the existing deterministic test style) and guarantees the
# displayed numbers always come from the same code path.
#
# Everything is computed from real stored data. No figure is
# invented or mocked.
# =========================================================

from datetime import datetime, timedelta, timezone


def _percent(part, whole):

    if not whole:

        return 0.0

    return round((part / whole) * 100, 1)


def _week_key(created_at):

    """
    Return an ISO year-week key ("2026-W14") for a record
    timestamp so records bucket consistently by calendar week.
    """

    if isinstance(created_at, str):

        try:

            parsed = datetime.fromisoformat(created_at)

        except (TypeError, ValueError):

            return None

        if parsed.tzinfo is None:

            parsed = parsed.replace(tzinfo=timezone.utc)

        created_at = parsed

    if not isinstance(created_at, datetime):

        return None

    if created_at.tzinfo is None:

        created_at = created_at.replace(tzinfo=timezone.utc)

    iso_year, iso_week, _ = created_at.isocalendar()

    return f"{iso_year}-W{iso_week:02d}"


def _last_week_keys(weeks=8, now=None):

    if now is None:

        now = datetime.now(timezone.utc)

    keys = []

    for offset in range(weeks - 1, -1, -1):

        date = now - timedelta(days=7 * offset)

        iso_year, iso_week, _ = date.isocalendar()

        keys.append(f"{iso_year}-W{iso_week:02d}")

    return keys


def _record_lane(record):

    return (
        str(record.get("origin", "") or "").strip(),
        str(record.get("destination", "") or "").strip(),
    )


def _top_list(items, limit=8):

    counted = {}

    for item in items:

        if not item:
            continue

        counted[item] = counted.get(item, 0) + 1

    return [
        {"label": label, "count": count}
        for label, count in sorted(
            counted.items(),
            key=lambda pair: (-pair[1], str(pair[0]))
        )[:limit]
    ]


def build_executive_report(
    total_users,
    total_route_analyses,
    total_quotations,
    total_shipments,
    shipments,
    history_records,
    status_flow=None,
):
    """
    Compute the complete Executive Dashboard payload from real
    Mongo counts and recent stored records.

    Parameters
    ----------
    total_users, total_route_analyses, total_quotations,
    total_shipments : int
        Exact document counts from MongoDB.
    shipments : list
        Recent shipment documents (created_at desc).
    history_records : list
        Recent route history / quotation documents.
    status_flow : list | None
        Shipment status workflow used for the status
        distribution ordering.
    """

    if not status_flow:

        status_flow = _default_status_flow()

    # ---------------------------------------------
    # APPROVAL FUNNEL
    # ---------------------------------------------

    quotations_with_acceptance = sum(
        1
        for record in history_records
        if record.get("accepted_at")
        or record.get("approval_status")
        in ("pending_admin_approval", "approved")
    )

    approved_quotations = sum(
        1
        for record in history_records
        if record.get("approval_status") == "approved"
    )

    pending_quotations = sum(
        1
        for record in history_records
        if record.get("approval_status")
        == "pending_admin_approval"
    )

    # Newest recorded activity for the "last activity" card.

    created_values = [
        record.get("created_at")
        for record in history_records
        if record.get("created_at")
    ]

    last_activity = max(
        created_values,
        default=None,
    )

    # ---------------------------------------------
    # SHIPMENT STATUS DISTRIBUTION
    # ---------------------------------------------

    status_counts = {}

    for shipment in shipments:

        status = shipment.get(
            "status", status_flow[0]
        )

        status_counts[status] = status_counts.get(
            status, 0
        ) + 1

    for status in status_flow:

        status_counts.setdefault(status, 0)

    status_distribution = [
        {
            "status": status,
            "count": status_counts.get(status, 0),
        }
        for status in status_flow
    ]

    # ---------------------------------------------
    # WEEKLY ROUTE ACTIVITY
    # ---------------------------------------------

    weekly = {}

    for record in history_records:

        key = _week_key(record.get("created_at"))

        if key:
            weekly[key] = weekly.get(key, 0) + 1

    trend = [
        {
            "week": key,
            "count": weekly.get(key, 0),
        }
        for key in _last_week_keys(weeks=8)
    ]

    # ---------------------------------------------
    # TOP LANES + CARGO
    # ---------------------------------------------

    lanes = _top_list(
        [
            f"{origin} -> {destination}"
            if origin and destination
            else ""
            for origin, destination in (
                _record_lane(record)
                for record in history_records
            )
        ],
        limit=8,
    )

    cargo = _top_list(
        [
            str(record.get("cargo_type", "") or "").strip()
            for record in history_records
        ],
        limit=8,
    )

    # ---------------------------------------------
    # COMPOSE THE REPORT
    # ---------------------------------------------

    return {
        "success": True,

        # -----------------------------------------
        # HEADLINE KPIs
        # -----------------------------------------

        "kpis": {
            "total_users": int(total_users or 0),
            "total_route_analyses": int(
                total_route_analyses or 0
            ),
            "total_quotations": int(total_quotations or 0),
            "total_shipments": int(total_shipments or 0),
            "active_shipments": sum(
                1
                for shipment in shipments
                if shipment.get("status", "")
                != (status_flow[-1] if status_flow else "Delivered")
            ),
            "delivered_shipments": sum(
                1
                for shipment in shipments
                if shipment.get("status", "")
                == (status_flow[-1] if status_flow else "Delivered")
            ),
            "pending_approvals": pending_quotations,
            "approved_quotations": approved_quotations,
        },

        # -----------------------------------------
        # QUOTATION APPROVAL FUNNEL
        # Real counts from the stored workflow.
        # -----------------------------------------

        "funnel": {
            "analyses": int(total_route_analyses or 0),
            "quotations": int(total_quotations or 0),
            "accepted": quotations_with_acceptance,
            "approved": approved_quotations,
            "shipments": int(total_shipments or 0),
            "conversion_rates": {
                "analyses_to_quotations": _percent(
                    total_quotations,
                    total_route_analyses,
                ),
                "quotations_to_accepted": _percent(
                    quotations_with_acceptance,
                    total_quotations,
                ),
                "accepted_to_approved": _percent(
                    approved_quotations,
                    quotations_with_acceptance,
                ),
                "approved_to_shipments": _percent(
                    total_shipments,
                    approved_quotations,
                ),
            },
        },

        # -----------------------------------------
        # SHIPMENT STATUS DISTRIBUTION
        # -----------------------------------------

        "shipment_status": status_distribution,

        # -----------------------------------------
        # WEEKLY ROUTE ACTIVITY TREND
        # -----------------------------------------

        "weekly_activity": trend,

        # -----------------------------------------
        # TOP LANES + CARGO
        # -----------------------------------------

        "top_lanes": lanes,
        "top_cargo": cargo,

        # -----------------------------------------
        # TIMESTAMPS
        # -----------------------------------------

        "generated_at": datetime.now(timezone.utc).isoformat(),

        "last_activity": last_activity,

        "snapshot": {
            "recent_shipments_checked": len(shipments),
            "recent_history_checked": len(history_records),
        },
    }


def _default_status_flow():

    """
    Fallback shipment workflow used only when a caller does
    not supply one, so the distribution still has a stable
    order.
    """

    return [
        "Booking Confirmed",
        "Cargo Ready",
        "At Origin Port",
        "Vessel Departed",
        "In Transit",
        "At Destination Port",
        "Delivered",
    ]


__all__ = [
    "build_executive_report",
    "_percent",
    "_week_key",
    "_top_list",
]