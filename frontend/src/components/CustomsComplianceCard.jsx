import React from "react";

// ==========================================
// CUSTOMS COMPLIANCE DISPLAY (CUSTOMS AGENT)
// ==========================================
// Presentation only. Every value is read from the
// Customs Agent response (backend/app/customs.csv
// via /api/customs/analyze, and the read-only
// /api/admin/customs listing). No customs status,
// control requirement, compliance percentage or
// document is calculated in this file - the Customs
// Agent owns all of that, this only renders it.
//
// The component is deliberately props-driven and
// stateless so it can be mounted from the user Route
// Intelligence results page without any data
// fetching of its own.
// ==========================================

// Shown whenever the Customs Agent has no record for
// the requested corridor + cargo combination, so a
// missing dataset or an unknown combination degrades
// to a safe, readable state instead of an empty card
// or a broken page.
const CUSTOMS_UNAVAILABLE_LABEL = "Customs Data Unavailable";

const CUSTOMS_STATUS_UNKNOWN_LABEL = "Unknown";

// "Auckland → Hamburg (R02216)" for the user card.
const customsCorridorLabel = (payload, fallbackRoute) => {
  const origin = String(payload?.origin || "").trim();
  const destination = String(
    payload?.destination || ""
  ).trim();
  const routeId = String(payload?.route_id || "").trim();

  if (origin && destination) {
    const corridor = `${origin} → ${destination}`;

    return routeId ? `${corridor} (${routeId})` : corridor;
  }

  if (!fallbackRoute) return routeId || "-";

  const fallbackOrigin = String(
    fallbackRoute.origin || ""
  ).trim();
  const fallbackDestination = String(
    fallbackRoute.destination || ""
  ).trim();
  const fallbackId = String(
    fallbackRoute.route_id || ""
  ).trim();

  if (fallbackOrigin && fallbackDestination) {
    const corridor = `${fallbackOrigin} → ${fallbackDestination}`;

    return fallbackId ? `${corridor} (${fallbackId})` : corridor;
  }

  return fallbackId || routeId || "-";
};

// Dataset text is already title-cased by the Customs
// Agent; this only normalises unexpected casing.
const customsText = (value, fallback = "-") => {
  const text = String(value ?? "").trim();

  if (!text) return fallback;

  return text.charAt(0).toUpperCase() + text.slice(1);
};

// Maps the Customs Agent status onto the existing
// badge color convention used by the Weather risk
// badge, so Valid / Warning / Action Required read
// consistently with the rest of the platform.
const customsStatusClass = (status) => {
  const value = String(status || "").trim().toUpperCase();

  if (value === "VALID") return "customs-status-valid";
  if (value === "WARNING") return "customs-status-warning";
  if (value === "ACTION REQUIRED") {
    return "customs-status-action";
  }

  return "customs-status-unknown";
};

// Accepts the Customs API payload (`available`) and
// normalises it into one truthy/falsy check.
const hasCustoms = (payload) => {
  if (!payload) return false;
  if (payload.available === false) return false;

  return Boolean(payload.customs_id || payload.checklist?.length);
};

const customsPercent = (value) => {
  if (value == null || value === "") return "-";

  const number = Number(value);

  if (isNaN(number)) return String(value);

  return `${Math.round(number)}%`;
};

// "4 of 5 controls satisfied" for the user card.
const customsControlSummary = (payload) => {
  const satisfied = Number(payload?.satisfied_controls);
  const required = Number(payload?.required_controls);
  const tracked = Number(payload?.tracked_controls);

  if (!isFinite(required) || !isFinite(satisfied)) {
    return "-";
  }

  if (!required) {
    return isFinite(tracked) && tracked
      ? `0 of ${tracked} tracked controls required`
      : "No controls required";
  }

  const label = isFinite(tracked)
    ? `${satisfied} of ${required} required controls satisfied`
    : `${satisfied} of ${required} controls satisfied`;

  return `${label} (${tracked} tracked)`;
};

// Compact status badge reused by the user card and
// the admin Customs Management table.
export function CustomsStatusBadge({ status, small }) {
  return (
    <span
      className={`customs-status-badge ${customsStatusClass(
        status
      )} ${small ? "customs-status-badge-sm" : ""}`}
    >
      {customsText(status, CUSTOMS_STATUS_UNKNOWN_LABEL)}
    </span>
  );
}

// Full Customs Compliance card for the user Route
// Intelligence results view. Reads every field from
// the Customs API response and falls back to the
// safe "Customs Data Unavailable" state.
export default function CustomsComplianceCard({
  customs,
  loading,
  route,
}) {
  const hasData = hasCustoms(customs);

  const missingLabels = (customs?.missing || [])
    .map((item) => customsText(item?.label, ""))
    .filter(Boolean);

  return (
    <div className="customs-card result-animate result-animate-2">

      <div className="customs-card-header">

        <div className="customs-card-icon">
          ⚖
        </div>

        <div>
          <span className="section-label">
            CUSTOMS COMPLIANCE
          </span>
          <h2>
            Customs Requirements for this Shipment
          </h2>
          <p>
            Matched by the Customs Agent on the
            project customs dataset using origin,
            destination, cargo type and cargo
            subtype
          </p>
        </div>

        {loading && (
          <span className="customs-card-loading">
            <span className="loading-spinner"></span>
            Checking customs...
          </span>
        )}

      </div>

      {/* FAIL-SAFE: no customs record for this corridor + cargo */}

      {!loading && !hasData && (
        <div className="customs-unavailable">
          <strong>
            {CUSTOMS_UNAVAILABLE_LABEL}
          </strong>
          <span>
            {customs?.message ||
              customs?.fallback_reason ||
              "No customs requirements are published for this origin, destination, cargo type and cargo subtype combination. Route intelligence, pricing and quotations are unaffected."}
          </span>
        </div>
      )}

      {!loading && hasData && (
        <>
          {/* ---------- Status banner ---------- */}

          <div className="customs-status-banner">
            <div>
              <span className="customs-status-label">
                Customs Status
              </span>
              <CustomsStatusBadge
                status={customs.customs_status}
              />
            </div>

            <div className="customs-status-route">
              <span className="customs-status-label">
                Corridor
              </span>
              <strong>
                {customsCorridorLabel(customs, route)}
              </strong>
            </div>

            <div className="customs-status-route">
              <span className="customs-status-label">
                Cargo
              </span>
              <strong>
                {[
                  customsText(customs.cargo_type, ""),
                  customsText(customs.cargo_subtype, ""),
                ]
                  .filter(Boolean)
                  .join(" / ") || "-"}
              </strong>
            </div>

            <div className="customs-status-route">
              <span className="customs-status-label">
                Document Compliance
              </span>
              <strong>
                {customsPercent(
                  customs.compliance_percent
                )}
              </strong>
            </div>
          </div>

          {/* ---------- Controls / checklist ---------- */}

          <div className="customs-controls">
            {customs.checklist.map((item) => {
              const state = String(
                item?.state || ""
              ).toLowerCase();

              return (
                <div
                  key={item.key}
                  className={`customs-control customs-control-${state}`}
                >
                  <span className="customs-control-label">
                    {customsText(item.label, "-")}
                  </span>
                  <strong className="customs-control-value">
                    {customsText(item.value, "-")}
                  </strong>
                  <span className="customs-control-state">
                    {customsText(item.state_label, "-")}
                  </span>
                </div>
              );
            })}
          </div>

          {/* ---------- Advisory ---------- */}

          <div className="customs-advisory">
            <span className="customs-advisory-icon">
              i
            </span>
            <div>
              <strong>Advisory</strong>
              <span>
                {customs.advisory ||
                  "No outstanding customs document."}
              </span>

              {missingLabels.length > 0 && (
                <>
                  <strong>Missing Documents</strong>
                  <span>
                    {missingLabels.join(", ")}
                  </span>
                </>
              )}

              {Array.isArray(customs.status_reasons) &&
                customs.status_reasons.length > 0 && (
                  <>
                    <strong>Status Basis</strong>
                    <span>
                      {customs.status_reasons.join(" ")}
                    </span>
                  </>
                )}

              {customs.compliance_basis && (
                <>
                  <strong>
                    Compliance Basis
                  </strong>
                  <span>
                    {customs.compliance_basis} (
                    {customsControlSummary(customs)})
                  </span>
                </>
              )}

              {/* The explanation service is an implementation detail.
                  The card only reports whether a written
                  advisory was added, never which service
                  produced it. */}

              {customs.advisory_included && (
                <span className="customs-advisory-source">
                  Includes an automated advisory
                </span>
              )}
            </div>
          </div>
        </>
      )}

    </div>
  );
}