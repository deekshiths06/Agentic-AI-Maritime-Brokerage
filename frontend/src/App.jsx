import React, { useEffect, useState } from "react";

const cargoSubtypes = {
  Bulk: [
    "Grain",
    "Coal",
    "Iron Ore",
    "Steel",
    "Timber",
    "Cement",
    "Fertilizer",
    "Sugar",
    "Rice",
    "Wheat",
  ],

  "General Cargo": [
    "Machinery",
    "Automotive Parts",
    "Furniture",
    "Construction Materials",
    "Industrial Equipment",
    "Paper Products",
    "Metal Products",
  ],

  Containerized: [
    "Electronics",
    "Textiles",
    "Consumer Goods",
    "Clothing",
    "Household Goods",
    "Plastic Products",
    "Packaged Food",
  ],

  Perishable: [
    "Fruits",
    "Vegetables",
    "Fresh Produce",
    "Frozen Food",
    "Seafood",
    "Dairy Products",
  ],

  Hazardous: [
    "Chemicals",
    "Petroleum Products",
    "Industrial Chemicals",
    "Flammable Materials",
    "Toxic Chemicals",
  ],
};

function App() {
  const [view, setView] = useState("home");
  const [activeNav, setActiveNav] = useState("Dashboard");

  const [origins, setOrigins] = useState([]);
  const [destinations, setDestinations] = useState([]);

  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [cargoType, setCargoType] = useState("");
  const [cargoSubtype, setCargoSubtype] = useState("");
  const [containers, setContainers] = useState(1);

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [user, setUser] = useState({});

  // ==========================================
  // LOGIN CHECK
  // ==========================================

  useEffect(() => {
    const loggedIn = localStorage.getItem("isLoggedIn");

    if (loggedIn !== "true") {
      window.location.href = "/login.html";
      return;
    }

    const savedUser =
      localStorage.getItem("loggedInUser") ||
      localStorage.getItem("user");

    if (savedUser) {
      try {
        setUser(JSON.parse(savedUser));
      } catch (err) {
        console.error("Unable to read user information");
      }
    }
  }, []);

  // ==========================================
  // LOAD LOCATIONS
  // ==========================================

  useEffect(() => {
    const loadLocations = async () => {
      try {
        const response = await fetch(
          "http://127.0.0.1:8000/api/routes/locations"
        );

        if (!response.ok) {
          throw new Error("Unable to load locations");
        }

        const data = await response.json();

        setOrigins(data.origins || []);
        setDestinations(data.destinations || []);
      } catch (err) {
        console.error("Location loading error:", err);
      }
    };

    loadLocations();
  }, []);

  // ==========================================
  // NAVIGATION
  // ==========================================

  const goHome = () => {
    setView("home");
    setActiveNav("Dashboard");
    setError("");
  };

  const goToSearch = () => {
    setView("search");
    setActiveNav("Routes");
    setError("");
  };

  const handleNewSearch = () => {
    setView("search");
    setActiveNav("Routes");
    setResult(null);
    setError("");
  };

  // ==========================================
  // CARGO CHANGE
  // ==========================================

  const handleCargoChange = (value) => {
    setCargoType(value);
    setCargoSubtype("");
  };

  // ==========================================
  // ANALYZE ROUTE
  // ==========================================

  const handleAnalyze = async (e) => {
    e.preventDefault();

    setError("");
    setResult(null);

    if (!origin) {
      setError("Please select an origin.");
      return;
    }

    if (!destination) {
      setError("Please select a destination.");
      return;
    }

    if (!cargoType) {
      setError("Please select a cargo type.");
      return;
    }

    if (!cargoSubtype) {
      setError("Please select a cargo subtype.");
      return;
    }

    if (!containers || Number(containers) < 1) {
      setError("Number of containers must be at least 1.");
      return;
    }

    try {
      setLoading(true);

      const response = await fetch(
        "http://127.0.0.1:8000/api/routes/analyze",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify({
            origin,
            destination,
            cargo_type: cargoType,
            cargo_subtype: cargoSubtype,
            containers: Number(containers),
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            data?.message ||
            "Unable to analyze the selected route."
        );
      }

      if (data?.status === "not_found") {
        setError(
          data?.message ||
            "No suitable routes were found for the selected shipment."
        );
        return;
      }

      if (data?.status === "error") {
        setError(
          data?.message ||
            "Something went wrong while analyzing the route."
        );
        return;
      }

      setResult(data);
      setView("results");
      setActiveNav("Routes");
    } catch (err) {
      console.error("Route analysis error:", err);

      setError(
        err.message ||
          "Unable to connect to the route analysis service."
      );
    } finally {
      setLoading(false);
    }
  };

  // ==========================================
  // LOGOUT
  // ==========================================

  const handleLogout = () => {
    localStorage.removeItem("isLoggedIn");
    localStorage.removeItem("user");
    localStorage.removeItem("token");
    localStorage.removeItem("loggedInUser");

    window.location.href = "/login.html";
  };

  // ==========================================
  // RESULT HELPERS
  // ==========================================

  const getValue = (obj, keys, fallback = "-") => {
    if (!obj) return fallback;

    for (const key of keys) {
      if (
        obj[key] !== undefined &&
        obj[key] !== null &&
        obj[key] !== ""
      ) {
        return obj[key];
      }
    }

    return fallback;
  };

  const getAllRoutes = () => {
    if (!result) return [];

    if (Array.isArray(result.routes)) {
      return result.routes;
    }

    if (Array.isArray(result.all_routes)) {
      return result.all_routes;
    }

    if (Array.isArray(result.route_options)) {
      return result.route_options;
    }

    return [];
  };

  const getRecommendedRoute = () => {
    if (!result) return null;

    return (
      result.recommended_route ||
      result.recommended ||
      result.best_route ||
      (getAllRoutes().length > 0 ? getAllRoutes()[0] : null)
    );
  };

  // ==========================================
  // ROUTE NAME
  // Displays:
  // Hong Kong → Durban via Malacca Strait
  // ==========================================

  const getRouteName = (route) => {
    const routeValue = getValue(
      route,
      ["route", "route_name", "name", "routeName"],
      "Route"
    );

    if (!routeValue || routeValue === "Route") {
      return "Route";
    }

    const parts = String(routeValue)
      .split("→")
      .map((part) => part.trim())
      .filter(Boolean);

    // Origin → Destination via Intermediate Location(s)
    if (parts.length >= 3) {
      const routeOrigin = parts[0];
      const routeDestination = parts[parts.length - 1];
      const via = parts.slice(1, -1).join(" → ");

      return `${routeOrigin} → ${routeDestination} via ${via}`;
    }

    // If only Origin → Destination exists
    return String(routeValue).trim();
  };

  // ==========================================
  // ROUTE ID
  // Uses route_id from CSV
  // Example: R00001
  // ==========================================

  const getRouteNumber = (route) => {
    const value = getValue(
      route,
      ["route_id", "routeId"],
      "-"
    );

    if (value === "-") return "-";

    return String(value).trim();
  };

  const getRawRouteNumber = (route) => {
    const value = getValue(
      route,
      ["route_id", "routeId"],
      "-"
    );

    if (value === "-") return "-";

    return String(value).trim();
  };

  const getTransit = (route) => {
    const value = getValue(
      route,
      [
        "transit_days",
        "transitDays",
        "transit_time",
        "days",
      ],
      "-"
    );

    if (value === "-") return "-";

    return `${value} days`;
  };

  const getDistance = (route) => {
    const value = getValue(
      route,
      ["distance_nm", "distance", "distanceNM"],
      "-"
    );

    if (value === "-") return "-";

    return `${value} nm`;
  };

  const getTransshipments = (route) => {
    return getValue(
      route,
      ["transshipments", "transshipment", "stops"],
      "-"
    );
  };

  const getScore = (route) => {
    const value = getValue(
      route,
      ["score", "route_score"],
      "-"
    );

    if (value === "-") return "-";

    if (typeof value === "number") {
      return value.toFixed(2);
    }

    return value;
  };

  const getStatus = () => {
    if (!result) return "";

    return (
      result.route_status ||
      result.status_message ||
      result.message ||
      ""
    );
  };

  const recommendedRoute = getRecommendedRoute();
  const allRoutes = getAllRoutes();

  // ==========================================
  // PROFILE NAME
  // ==========================================

  const profileName =
    user?.name ||
    user?.full_name ||
    user?.username ||
    "User";

  const profileContact =
    user?.email ||
    user?.mobile ||
    user?.phone ||
    "";

  // ==========================================
  // SIDEBAR NAVIGATION
  // ==========================================

  const handleNavClick = (item) => {
    if (item === "Dashboard") {
      goHome();
      return;
    }

    if (item === "Routes") {
      goToSearch();
      return;
    }

    if (item === "Quotation") {
      setActiveNav("Quotation");
      setView("home");

      window.setTimeout(() => {
        document
          .getElementById("dashboard-quotation")
          ?.scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
      }, 80);

      return;
    }

    setActiveNav(item);
    setError(`${item} module is not available yet.`);
  };

  // ==========================================
  // DASHBOARD
  // ==========================================

  const renderHome = () => {
    return (
      <section className="home-screen dashboard-animated page-view">

        <div className="welcome-block">

          <div className="welcome-text">

            <span className="welcome-label">
              MARITIME AI PLATFORM
            </span>

            <h1>
              Welcome, {profileName}
            </h1>

            <p>
              Intelligent route planning for smarter maritime
              freight decisions.
            </p>

            {profileContact && (
              <small>{profileContact}</small>
            )}

          </div>

        </div>

        {/* DASHBOARD QUOTATION + HUMAN ANIMATION */}

        <div
          className="dashboard-quote-section"
          id="dashboard-quotation"
        >

          <div
            className="human-illustration"
            aria-hidden="true"
          >
            <div className="human-shadow"></div>
            <div className="human-head"></div>
            <div className="human-body"></div>
            <div className="human-arm human-arm-left"></div>
            <div className="human-arm human-arm-right"></div>
            <div className="human-hand human-hand-left"></div>
            <div className="human-hand human-hand-right"></div>
            <div className="human-leg human-leg-left"></div>
            <div className="human-leg human-leg-right"></div>
          </div>

          <div className="dashboard-quote-card">
            <span className="quote-mark">“</span>

            <p>
              The right route is not just a choice —
              it is a smarter decision for every shipment.
            </p>

            <span className="quote-author">
              — Maritime AI
            </span>
          </div>

        </div>

        {/* MAIN ROUTE SEARCH BUTTON */}

        <button
          className="route-search-cta"
          onClick={goToSearch}
          type="button"
        >

          <div className="cta-content">

            <div className="cta-icon">
              ⇢
            </div>

            <div className="cta-text">

              <strong>
                Search & Analyze Routes
              </strong>

              <span>
                Find the most suitable maritime route
                for your shipment
              </span>

            </div>

            <div className="cta-arrow">
              →
            </div>

          </div>

        </button>

        {/* CLICKABLE HINT */}

        <button
          className="click-hint"
          onClick={goToSearch}
          type="button"
        >

          <span className="hint-arrow">
            ↓
          </span>

          Click here to start your route search

        </button>

        {/* INFORMATION CARDS */}

        <div className="info-cards">

          <div className="info-card">

            <div className="info-card-icon">
              ◈
            </div>

            <div>

              <h3>
                Intelligent Routing
              </h3>

              <p>
                Compare available maritime routes
                and identify the most suitable option.
              </p>

            </div>

          </div>

          <div className="info-card">

            <div className="info-card-icon">
              ◉
            </div>

            <div>

              <h3>
                Shipment Analysis
              </h3>

              <p>
                Analyze routes based on cargo type,
                transit time, distance and transfers.
              </p>

            </div>

          </div>

          <div className="info-card">

            <div className="info-card-icon">
              ◆
            </div>

            <div>

              <h3>
                Data-Driven Decisions
              </h3>

              <p>
                Get a recommended route using
                intelligent route scoring.
              </p>

            </div>

          </div>

        </div>

      </section>
    );
  };

  // ==========================================
  // SEARCH PAGE
  // ==========================================

  const renderSearch = () => {
    return (
      <section className="search-screen page-view">

        <div className="search-header">

          <button
            className="back-button"
            type="button"
            onClick={goHome}
          >
            ← Back to Dashboard
          </button>

          <div>

            <span className="section-label">
              ROUTE INTELLIGENCE
            </span>

            <h1>
              Analyze Your Shipment
            </h1>

            <p>
              Enter shipment details to find the
              most suitable maritime route.
            </p>

          </div>

        </div>

        <form
          className="route-form"
          onSubmit={handleAnalyze}
        >

          <div className="form-grid">

            {/* ORIGIN */}

            <div className="form-group">

              <label>
                Origin
              </label>

              <select
                value={origin}
                onChange={(e) =>
                  setOrigin(e.target.value)
                }
              >

                <option value="">
                  Select origin
                </option>

                {origins.map((item, index) => (
                  <option
                    value={item}
                    key={`${item}-${index}`}
                  >
                    {item}
                  </option>
                ))}

              </select>

            </div>

            {/* DESTINATION */}

            <div className="form-group">

              <label>
                Destination
              </label>

              <select
                value={destination}
                onChange={(e) =>
                  setDestination(e.target.value)
                }
              >

                <option value="">
                  Select destination
                </option>

                {destinations.map((item, index) => (
                  <option
                    value={item}
                    key={`${item}-${index}`}
                  >
                    {item}
                  </option>
                ))}

              </select>

            </div>

            {/* CONTAINERS */}

            <div className="form-group">

              <label>
                Number of Containers
              </label>

              <input
                type="number"
                min="1"
                value={containers}
                onChange={(e) =>
                  setContainers(e.target.value)
                }
                placeholder="Enter number of containers"
              />

            </div>

            {/* CARGO TYPE */}

            <div className="form-group">

              <label>
                Cargo Type
              </label>

              <select
                value={cargoType}
                onChange={(e) =>
                  handleCargoChange(e.target.value)
                }
              >

                <option value="">
                  Select cargo type
                </option>

                {Object.keys(cargoSubtypes).map(
                  (type) => (
                    <option
                      value={type}
                      key={type}
                    >
                      {type}
                    </option>
                  )
                )}

              </select>

            </div>

            {/* CARGO SUBTYPE */}

            <div className="form-group full-width">

              <label>
                Cargo Subtype
              </label>

              <select
                value={cargoSubtype}
                onChange={(e) =>
                  setCargoSubtype(e.target.value)
                }
                disabled={!cargoType}
              >

                <option value="">
                  {cargoType
                    ? "Select cargo subtype"
                    : "Select cargo type first"}
                </option>

                {cargoType &&
                  cargoSubtypes[cargoType]?.map(
                    (subtype) => (
                      <option
                        value={subtype}
                        key={subtype}
                      >
                        {subtype}
                      </option>
                    )
                  )}

              </select>

            </div>

          </div>

          {/* ERROR */}

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          {/* LOADING */}

          {loading && (
            <div className="loading-message">

              <span className="loading-spinner"></span>

              Analyzing available routes...

            </div>
          )}

          {/* FORM ACTIONS */}

          <div className="form-actions">

            <button
              type="button"
              className="secondary-button"
              onClick={goHome}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="primary-button"
              disabled={loading}
            >
              {loading
                ? "Analyzing..."
                : "Analyze Shipment →"}
            </button>

          </div>

        </form>

      </section>
    );
  };

  // ==========================================
  // RESULTS PAGE
  // ==========================================

  const renderResults = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={goToSearch}
            >
              ← Search Again
            </button>

            <span className="section-label">
              ROUTE ANALYSIS RESULTS
            </span>

            <h1>
              Recommended Maritime Route
            </h1>

            <p>
              Your shipment has been analyzed
              against the available routes.
            </p>

          </div>

        </div>

        {/* SHIPMENT SUMMARY */}

        <div className="shipment-summary">

          <div className="summary-item">

            <span>
              Origin
            </span>

            <strong>
              {origin || "-"}
            </strong>

          </div>

          <div className="summary-item">

            <span>
              Destination
            </span>

            <strong>
              {destination || "-"}
            </strong>

          </div>

          <div className="summary-item">

            <span>
              Cargo
            </span>

            <strong>
              {cargoType || "-"}
            </strong>

          </div>

          <div className="summary-item">

            <span>
              Subtype
            </span>

            <strong>
              {cargoSubtype || "-"}
            </strong>

          </div>

          <div className="summary-item">

            <span>
              Containers
            </span>

            <strong>
              {containers || "-"}
            </strong>

          </div>

        </div>

        {/* RECOMMENDATION */}

        {recommendedRoute && (
          <div className="recommendation-card">

            <div className="recommendation-top">

              <div>

                <span className="recommendation-label">
                  RECOMMENDED ROUTE
                </span>

                <h2>
                  {getRouteName(
                    recommendedRoute
                  )}
                </h2>

              </div>

              <div className="recommended-badge">
                Recommended
              </div>

            </div>

            <div className="recommendation-details">

              <div className="result-detail">

                <span>
                  Route ID
                </span>

                <strong>
                  {getRouteNumber(
                    recommendedRoute
                  )}
                </strong>

              </div>

              <div className="result-detail">

                <span>
                  Transit Time
                </span>

                <strong>
                  {getTransit(
                    recommendedRoute
                  )}
                </strong>

              </div>

              <div className="result-detail">

                <span>
                  Distance
                </span>

                <strong>
                  {getDistance(
                    recommendedRoute
                  )}
                </strong>

              </div>

              <div className="result-detail">

                <span>
                  Transshipments
                </span>

                <strong>
                  {getTransshipments(
                    recommendedRoute
                  )}
                </strong>

              </div>

              <div className="result-detail">

                <span>
                  Route Score
                </span>

                <strong>
                  {getScore(
                    recommendedRoute
                  )}
                </strong>

              </div>

            </div>

            {getStatus() && (
              <div className="route-status">
                {getStatus()}
              </div>
            )}

          </div>
        )}

        {/* ROUTE COMPARISON */}

        <div className="comparison-section">

          <div className="comparison-heading">

            <div>

              <span className="section-label">
                ROUTE COMPARISON
              </span>

              <h2>
                Available Routes
              </h2>

            </div>

            <span className="route-count">
              {allRoutes.length} route
              {allRoutes.length !== 1
                ? "s"
                : ""}
            </span>

          </div>

          {allRoutes.length > 0 ? (
            <div className="table-wrapper">

              <table className="route-table">

                <thead>

                  <tr>

                    <th>
                      Route
                    </th>

                    <th>
                      Route ID
                    </th>

                    <th>
                      Transit
                    </th>

                    <th>
                      Distance
                    </th>

                    <th>
                      Transshipments
                    </th>

                    <th>
                      Score
                    </th>

                    <th>
                      Status
                    </th>

                  </tr>

                </thead>

                <tbody>

                  {allRoutes.map(
                    (route, index) => {

                      const isRecommended =
                        recommendedRoute &&
                        (
                          getRawRouteNumber(route) ===
                            getRawRouteNumber(
                              recommendedRoute
                            ) ||
                          route === recommendedRoute
                        );

                      return (
                        <tr
                          key={
                            getRawRouteNumber(route) !== "-"
                              ? getRawRouteNumber(route)
                              : index
                          }
                          className={
                            isRecommended
                              ? "recommended-row"
                              : ""
                          }
                        >

                          <td>

                            <div className="route-name-cell">

                              {getRouteName(
                                route
                              )}

                            </div>

                          </td>

                          <td>
                            {getRouteNumber(
                              route
                            )}
                          </td>

                          <td>
                            {getTransit(
                              route
                            )}
                          </td>

                          <td>
                            {getDistance(
                              route
                            )}
                          </td>

                          <td>
                            {getTransshipments(
                              route
                            )}
                          </td>

                          <td>

                            <strong>
                              {getScore(
                                route
                              )}
                            </strong>

                          </td>

                          <td>

                            {isRecommended ? (
                              <span className="route-status recommended">
                                Recommended
                              </span>
                            ) : (
                              <span className="route-status">
                                Alternative
                              </span>
                            )}

                          </td>

                        </tr>
                      );
                    }
                  )}

                </tbody>

              </table>

            </div>
          ) : (
            <div className="no-routes">
              No route comparison data available.
            </div>
          )}

        </div>

        {/* BOTTOM ACTIONS */}

        <div className="results-actions">

          <button
            className="secondary-button"
            type="button"
            onClick={goHome}
          >
            Back to Dashboard
          </button>

          <button
            className="primary-button"
            type="button"
            onClick={handleNewSearch}
          >
            New Route Search →
          </button>

        </div>

      </section>
    );
  };

  // ==========================================
  // MAIN LAYOUT
  // ==========================================

  return (
    <div className="app-container">

      {/* SIDEBAR */}

      <aside className="sidebar">

        <div className="sidebar-brand">

          <div className="brand-icon">
            M
          </div>

          <div>

            <strong>
              Maritime AI
            </strong>

            <span>
              Freight Intelligence
            </span>

          </div>

        </div>

        <nav className="sidebar-nav">

          <button
            className={
              activeNav === "Dashboard"
                ? "nav-item active"
                : "nav-item"
            }
            type="button"
            onClick={() =>
              handleNavClick("Dashboard")
            }
          >

            <span className="nav-icon">
              ▦
            </span>

            Dashboard

          </button>

          <button
            className={
              activeNav === "Routes"
                ? "nav-item active"
                : "nav-item"
            }
            type="button"
            onClick={() =>
              handleNavClick("Routes")
            }
          >

            <span className="nav-icon">
              ⇢
            </span>

            Route Intelligence

          </button>

          <button
            className={
              activeNav === "Shipments"
                ? "nav-item active"
                : "nav-item"
            }
            type="button"
            onClick={() =>
              handleNavClick("Shipments")
            }
          >

            <span className="nav-icon">
              ▤
            </span>

            Shipments

          </button>

          <button
            className={
              activeNav === "Analytics"
                ? "nav-item active"
                : "nav-item"
            }
            type="button"
            onClick={() =>
              handleNavClick("Analytics")
            }
          >

            <span className="nav-icon">
              ◒
            </span>

            Analytics

          </button>

          <button
            className={
              activeNav === "Quotation"
                ? "nav-item active"
                : "nav-item"
            }
            type="button"
            onClick={() =>
              handleNavClick("Quotation")
            }
          >

            <span className="nav-icon">
              ❝
            </span>

            Quotation

          </button>

        </nav>

        <div className="sidebar-bottom">

          <button
            className="logout-button"
            type="button"
            onClick={handleLogout}
          >

            <span className="nav-icon">
              ↪
            </span>

            Logout

          </button>

        </div>

      </aside>

      {/* MAIN AREA */}

      <main className="main-area">

        {/* TOPBAR */}

        <header className="topbar">

          <div className="topbar-title">

            {activeNav === "Dashboard"
              ? "Dashboard"
              : activeNav === "Routes"
              ? "Route Intelligence"
              : activeNav}

          </div>

          <div className="topbar-profile">

            <div className="profile-avatar">

              {profileName
                .charAt(0)
                .toUpperCase()}

            </div>

            <div className="profile-info">

              <strong>
                {profileName}
              </strong>

              <span>
                Maritime User
              </span>

            </div>

          </div>

        </header>

        {/* CONTENT */}

        <div className="content-area">

          {view === "home" &&
            renderHome()}

          {view === "search" &&
            renderSearch()}

          {view === "results" &&
            renderResults()}

        </div>

      </main>

    </div>
  );
}

export default App;