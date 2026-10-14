import React from "react";

// ==========================================
// SUSTAINABILITY INSIGHTS DISPLAY
// (COST & SUSTAINABILITY AGENT)
// ==========================================
// Presentation only. Every score, category, rating
// label, component value and explanation is read from
// the Cost & Sustainability Agent response
// (/api/sustainability/analyze). Nothing is scored,
// weighted or averaged in this file - the agent owns
// all of the formulas. This component is deliberately
// props-driven and stateless so it can be mounted from
// the existing Route Intelligence results view without
// any data fetching of its own.
// ==========================================

// Shown when the agent has no usable inputs for the
// voyage, so a missing dataset or an unsupported route
// degrades to a safe, readable state instead of a
// broken page.
const SUSTAINABILITY_UNAVAILABLE_LABEL =
  "Sustainability Score Unavailable";

// Maps the agent category letter onto a colour class
// that follows the platform's status convention
// (green = strong, amber = moderate, red = weak).
const categoryClass = (category) => {
  const value = String(category || "").trim().toUpperCase();

  if (value === "A" || value === "B") {
    return "sustainability-category-strong";
  }

  if (value === "C") {
    return "sustainability-category-moderate";
  }

  if (value === "D" || value === "E") {
    return "sustainability-category-weak";
  }

  return "sustainability-category-unknown";
};

const sustainabilityText = (value, fallback = "-") => {
  const text = String(value ?? "").trim();

  return text || fallback;
};

const formatNumber = (value, places = 1) => {
  if (value == null || value === "") return "-";

  const number = Number(value);

  if (isNaN(number)) return "-";

  return number.toFixed(places);
};

// A factor is scorable when the agent marked it
// available and produced a numeric point value.
const factorAvailable = (factor) =>
  Boolean(factor && factor.available && factor.points != null);

// The four factors are read directly from the agent
// response, always in the documented weight order.
const FACTOR_ORDER = [
  "emission_intensity",
  "speed_efficiency",
  "port_waiting",
  "fuel_tier",
];

// A single factor card: label, points out of 100, the
// raw input with its unit, and how much the factor
// actually contributed to the weighted total.
function FactorCard({ factor }) {
  const available = factorAvailable(factor);

  const points = available ? Number(factor.points) : 0;

  const weightPercent = Math.round(
    Number(factor?.weight || 0) * 100
  );

  return (
    <div
      className={`sustainability-factor ${
        available
          ? "sustainability-factor-scored"
          : "sustainability-factor-missing"
      }`}
    >
      <div className="sustainability-factor-top">
        <span className="sustainability-factor-label">
          {sustainabilityText(factor?.label, "Factor")}
        </span>
        <span className="sustainability-factor-weight">
          {weightPercent}% weight
        </span>
      </div>

      {available ? (
        <>
          <div className="sustainability-factor-points">
            <strong>{formatNumber(points, 0)}</strong>
            <span>/ 100 pts</span>
          </div>

          <div
            className="sustainability-factor-track"
            role="img"
            aria-label={`${sustainabilityText(
              factor?.label,
              "Factor"
            )} scored ${formatNumber(points, 0)} out of 100`}
          >
            <span
              className="sustainability-factor-fill"
              style={{
                width: `${Math.max(
                  0,
                  Math.min(100, points)
                )}%`,
              }}
            />
          </div>

          <span className="sustainability-factor-input">
            Measured input:{" "}
            <strong>
              {factor?.unit === "tier"
                ? sustainabilityText(factor?.input, "-")
                : factor?.input != null
                ? `${formatNumber(
                    factor.input,
                    factor.unit === "hours" ? 1 : 2
                  )} ${sustainabilityText(
                    factor.unit,
                    ""
                  )}`.trim()
                : "-"}
            </strong>
            {factor?.source
              ? ` (${sustainabilityText(factor.source, "")})`
              : ""}
          </span>
        </>
      ) : (
        <span className="sustainability-factor-missing-text">
          Not enough data for this factor, so it was
          excluded and the remaining weights were
          renormalised.
        </span>
      )}
    </div>
  );
}

// Full Sustainability Insights card for the user Route
// Intelligence results view.
export default function SustainabilityInsightsCard({
  sustainability,
  loading,
  error,
  route,
}) {
  const status = String(
    sustainability?.status || ""
  ).trim();

  const hasScore =
    status === "success" &&
    sustainability?.sustainability_score != null;

  const score = hasScore
    ? Number(sustainability.sustainability_score)
    : null;

  const routeLabel = (() => {
    const routeId = String(
      sustainability?.route_id ||
        route?.route_id ||
        ""
    ).trim();

    const origin = String(route?.origin || "").trim();
    const destination = String(
      route?.destination || ""
    ).trim();

    const corridor =
      origin && destination
        ? `${origin} → ${destination}`
        : "";

    if (corridor && routeId) {
      return `${corridor} (${routeId})`;
    }

    return corridor || routeId || "-";
  })();

  const missingInputs = Array.isArray(
    sustainability?.missing_inputs
  )
    ? sustainability.missing_inputs.filter(Boolean)
    : [];

  const components =
    sustainability?.components &&
    typeof sustainability.components === "object"
      ? sustainability.components
      : {};

  // Contribution breakdown is only rendered when a real
  // score exists, so a partial or missing result never
  // shows a fabricated chart.
  const contributions = FACTOR_ORDER.map((key) => {
    const factor = components[key];

    if (!factorAvailable(factor)) return null;

    return {
      key,
      label: sustainabilityText(
        factor?.label,
        key
      ),
      points: Number(factor.points),
      weightedPoints: Number(
        factor?.weighted_points || 0
      ),
      weight: Number(factor?.weight || 0),
    };
  }).filter(Boolean);

  const totalContribution = contributions.reduce(
    (sum, item) => sum + item.weightedPoints,
    0
  );

  return (
    <div className="sustainability-card result-animate result-animate-2">
      <div className="sustainability-card-header">
        <div className="sustainability-card-icon">♻</div>

        <div>
          <span className="section-label">
            SUSTAINABILITY INSIGHTS
          </span>
          <h2>Voyage Sustainability Assessment</h2>
          <p>
            Calculated by the Cost &amp; Sustainability
            Agent from the project route dataset using
            emission intensity, speed efficiency, port
            waiting and fuel tier
          </p>
        </div>

        {loading && (
          <span className="sustainability-card-loading">
            <span className="loading-spinner"></span>
            Scoring voyage...
          </span>
        )}
      </div>

      {/* FAIL-SAFE: request error */}
      {!loading && error && (
        <div className="sustainability-unavailable">
          <strong>{SUSTAINABILITY_UNAVAILABLE_LABEL}</strong>
          <span>
            {error ||
              "The sustainability agent could not be reached. Route intelligence is unaffected."}
          </span>
        </div>
      )}

      {/* FAIL-SAFE: not enough data to score */}
      {!loading && !error && !hasScore && (
        <div className="sustainability-unavailable">
          <strong>{SUSTAINABILITY_UNAVAILABLE_LABEL}</strong>
          <span>
            {sustainability?.explanation ||
              "Not enough voyage data is available to calculate a sustainability score for this route. Route intelligence, pricing and quotations are unaffected."}
          </span>

          {missingInputs.length > 0 && (
            <span className="sustainability-missing-list">
              Missing inputs: {missingInputs.join(", ")}
            </span>
          )}
        </div>
      )}

      {!loading && !error && hasScore && (
        <>
          {/* ---------- Overall score banner ---------- */}
          <div className="sustainability-score-banner">
            <div className="sustainability-score-main">
              <span className="sustainability-score-label">
                Overall Sustainability Score
              </span>

              <div className="sustainability-score-value">
                <strong>{formatNumber(score, 1)}</strong>
                <span>
                  / {sustainability?.max_score ?? 100}
                </span>
              </div>
            </div>

            <div className="sustainability-score-meta">
              <div className="sustainability-category-block">
                <span className="sustainability-score-label">
                  Category
                </span>
                <span
                  className={`sustainability-category-badge ${categoryClass(
                    sustainability?.category
                  )}`}
                >
                  {sustainabilityText(
                    sustainability?.category,
                    "-"
                  )}
                </span>
              </div>

              <div className="sustainability-rating-block">
                <span className="sustainability-score-label">
                  Rating
                </span>
                <strong>
                  {sustainabilityText(
                    sustainability?.rating_label,
                    "-"
                  )}
                </strong>
              </div>

              <div className="sustainability-rating-block">
                <span className="sustainability-score-label">
                  Route
                </span>
                <strong>{routeLabel}</strong>
              </div>
            </div>
          </div>

          {/* ---------- Four factor cards ---------- */}
          <div className="sustainability-factors">
            {FACTOR_ORDER.map((key) => (
              <FactorCard
                key={key}
                factor={components[key]}
              />
            ))}
          </div>

          {/* ---------- Weighted contribution breakdown ---------- */}
          {contributions.length > 0 && (
            <div className="sustainability-breakdown">
              <span className="sustainability-breakdown-title">
                How each factor contributes to the score
              </span>

              <div className="sustainability-breakdown-bar">
                {contributions.map((item) => {
                  const share =
                    totalContribution > 0
                      ? (item.weightedPoints /
                          totalContribution) *
                        100
                      : 0;

                  return (
                    <span
                      key={item.key}
                      className={`sustainability-breakdown-segment sustainability-segment-${item.key}`}
                      style={{ width: `${share}%` }}
                      title={`${item.label}: ${formatNumber(
                        item.weightedPoints,
                        1
                      )} weighted points (${formatNumber(
                        item.points,
                        0
                      )} pts × ${Math.round(
                        item.weight * 100
                      )}%)`}
                    >
                      {share >= 12
                        ? formatNumber(
                            item.weightedPoints,
                            1
                          )
                        : ""}
                    </span>
                  );
                })}
              </div>

              <ul className="sustainability-breakdown-legend">
                {contributions.map((item) => (
                  <li key={item.key}>
                    <span
                      className={`sustainability-legend-swatch sustainability-segment-${item.key}`}
                    />
                    <span className="sustainability-legend-label">
                      {item.label}
                    </span>
                    <span className="sustainability-legend-value">
                      {formatNumber(
                        item.weightedPoints,
                        1
                      )}{" "}
                      pts ({Math.round(item.weight * 100)}%)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ---------- Explanation ---------- */}
          <div className="sustainability-advisory">
            <span className="sustainability-advisory-icon">i</span>
            <div>
              <strong>Result</strong>
              <span>
                {sustainabilityText(
                  sustainability?.explanation,
                  "-"
                )}
              </span>

              {sustainability?.formula_explanation && (
                <>
                  <strong>How the score is built</strong>
                  <span>
                    {sustainability.formula_explanation}
                  </span>
                </>
              )}

              {missingInputs.length > 0 && (
                <>
                  <strong>Unavailable factors</strong>
                  <span>{missingInputs.join(", ")}</span>
                </>
              )}

              {sustainability?.data_note && (
                <span className="sustainability-data-note">
                  {sustainability.data_note}
                </span>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
