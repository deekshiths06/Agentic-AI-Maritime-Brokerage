import React, { useEffect, useRef, useState } from "react";

function App() {
  const [view, setView] = useState("home");
  const [activeNav, setActiveNav] = useState("Dashboard");

  const [origins, setOrigins] = useState([]);
  const [destinations, setDestinations] = useState([]);

  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [cargoType, setCargoType] = useState("");
  const [cargoSubtype, setCargoSubtype] = useState("");
  const [cargoSubtypesByType, setCargoSubtypesByType] = useState({});
  const [routeCargoSubtypes, setRouteCargoSubtypes] = useState([]);
  const [subtypesLoading, setSubtypesLoading] = useState(false);

  const [containers, setContainers] = useState(1);

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [user, setUser] = useState({});

  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [historyActionLoading, setHistoryActionLoading] =
    useState(false);

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

    const loadCargoSubtypes = async () => {
      try {
        const response = await fetch(
          "http://127.0.0.1:8000/api/routes/cargo-subtypes"
        );

        if (!response.ok) {
          throw new Error("Unable to load cargo subtypes");
        }

        const data = await response.json();

        setCargoSubtypesByType(data || {});
      } catch (err) {
        console.error("Cargo subtypes loading error:", err);
      }
    };

    loadLocations();
    loadCargoSubtypes();
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
  // ROUTE HISTORY
  // ==========================================

  const resolveUser = () => {
    if (user?.id || user?._id) {
      return {
        id: user.id || user._id || "",
        contact:
          user.contact || user.email || "",
      };
    }

    try {
      const saved =
        localStorage.getItem("loggedInUser") ||
        localStorage.getItem("user");

      const parsed = saved ? JSON.parse(saved) : {};

      return {
        id: parsed?.id || parsed?._id || "",
        contact:
          parsed?.contact || parsed?.email || "",
      };
} catch {
      return { id: "", contact: "" };
    }
  };

  const formatAnalysisDate = (value) => {
    if (!value) return "-";

    const date = new Date(value);
    if (isNaN(date.getTime())) return String(value);

    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const loadRouteHistory = async () => {
    const identity = resolveUser();

    if (!identity.id) {
      setHistory([]);
      setHistoryError(
        "Sign in is required to view route history."
      );
      setHistoryLoading(false);
      return;
    }

    setHistoryLoading(true);
    setHistoryError("");

    try {
      const params = new URLSearchParams({
        user_id: identity.id,
      });

      if (identity.contact) {
        params.append("contact", identity.contact);
      }

      const response = await fetch(
        `http://127.0.0.1:8000/api/routes/history?${params}`
      );

      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({}));
        throw new Error(
          data?.detail ||
            "Unable to load route history."
        );
      }

      const data = await response.json();

      setHistory(data?.history || []);
    } catch (err) {
      console.error(
        "Route history loading error:",
        err
      );
      setHistory([]);
      setHistoryError(
        err.message ||
          "Unable to load route history."
      );
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleDeleteHistory = async (recordId) => {
    const confirmed = window.confirm(
      "Are you sure you want to delete this route history?"
    );

    if (!confirmed) return;

    const identity = resolveUser();

    if (!identity.id) {
      setHistoryError(
        "Sign in is required to manage route history."
      );
      return;
    }

    setHistoryActionLoading(true);
    setHistoryError("");

    try {
      const params = new URLSearchParams({
        user_id: identity.id,
      });

      const response = await fetch(
        `http://127.0.0.1:8000/api/routes/history/${recordId}?${params}`,
        {
          method: "DELETE",
        }
      );

      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({}));
        throw new Error(
          data?.detail ||
            "Unable to delete the route history record."
        );
      }

      setHistory((prev) =>
        prev.filter(
          (item) => item.record_id !== recordId
        )
      );
    } catch (err) {
      console.error(
        "Route history delete error:",
        err
      );
      setHistoryError(
        err.message ||
          "Unable to delete the route history record."
      );
    } finally {
      setHistoryActionLoading(false);
    }
  };

  const handleClearHistory = async () => {
    const confirmed = window.confirm(
      "Are you sure you want to clear all route history?"
    );

    if (!confirmed) return;

    const identity = resolveUser();

    if (!identity.id) {
      setHistoryError(
        "Sign in is required to manage route history."
      );
      return;
    }

    setHistoryActionLoading(true);
    setHistoryError("");

    try {
      const params = new URLSearchParams({
        user_id: identity.id,
      });

      const response = await fetch(
        `http://127.0.0.1:8000/api/routes/history?${params}`,
        {
          method: "DELETE",
        }
      );

      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({}));
        throw new Error(
          data?.detail ||
            "Unable to clear route history."
        );
      }

      setHistory([]);
    } catch (err) {
      console.error(
        "Route history clear error:",
        err
      );
      setHistoryError(
        err.message ||
          "Unable to clear route history."
      );
    } finally {
      setHistoryActionLoading(false);
    }
  };

  // ==========================================
  // CARGO SUBTYPES
  // Fetch the subtypes that actually exist for
  // the selected origin + destination + cargo type.
  // ==========================================

  const fetchRouteSubtypes = async (
    selectedOrigin,
    selectedDestination,
    selectedCargoType
  ) => {
    if (
      !selectedOrigin ||
      !selectedDestination ||
      !selectedCargoType
    ) {
      setRouteCargoSubtypes([]);
      return;
    }

    setSubtypesLoading(true);
    setError("");

    try {
      const params = new URLSearchParams({
        origin: selectedOrigin,
        destination: selectedDestination,
        cargo_type: selectedCargoType,
      });

      const response = await fetch(
        `http://127.0.0.1:8000/api/routes/cargo-subtypes?${params}`
      );

      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({}));
        throw new Error(
          data?.detail ||
            "Unable to load cargo subtypes for this route."
        );
      }

      const data = await response.json();

      setRouteCargoSubtypes(
        data?.cargo_subtypes || []
      );
    } catch (err) {
      console.error(
        "Cargo subtypes loading error:",
        err
      );
      setRouteCargoSubtypes([]);
      setError(
        err.message ||
          "Unable to load cargo subtypes for this route."
      );
    } finally {
      setSubtypesLoading(false);
    }
  };

  // ==========================================
  // ORIGIN CHANGE
  // Resets destination, cargo type, cargo subtype
  // and clears the previous analysis results.
  // ==========================================

  const handleOriginChange = (value) => {
    setOrigin(value);
    setDestination("");
    setCargoType("");
    setCargoSubtype("");
    setRouteCargoSubtypes([]);
    setResult(null);
    setError("");
  };

  // ==========================================
  // DESTINATION CHANGE
  // Resets cargo type, cargo subtype and clears
  // the previous analysis results.
  // ==========================================

  const handleDestinationChange = (value) => {
    setDestination(value);
    setCargoType("");
    setCargoSubtype("");
    setRouteCargoSubtypes([]);
    setResult(null);
    setError("");
  };

  // ==========================================
  // CARGO TYPE CHANGE
  // Loads the valid cargo subtypes for the
  // selected origin + destination + cargo type.
  // ==========================================

  const handleCargoChange = (value) => {
    setCargoType(value);
    setCargoSubtype("");
    setRouteCargoSubtypes([]);
    setResult(null);
    setError("");

    if (value && origin && destination) {
      fetchRouteSubtypes(
        origin,
        destination,
        value
      );
    }
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
      if (
        cargoType &&
        routeCargoSubtypes.length === 0
      ) {
        setError(
          "No cargo subtypes available for this route."
        );
      } else {
        setError(
          "Please select a cargo subtype."
        );
      }
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
            user_id: resolveUser().id || "",
            user_contact: resolveUser().contact || "",
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
  // PROFILE MENU
  // ==========================================

  const profileRef = useRef(null);
  const [profileOpen, setProfileOpen] = useState(false);

  const getProfileInitials = (name) => {
    const cleaned = String(name || "").trim();
    if (!cleaned) return "MA";

    const parts = cleaned.split(/\s+/).filter(Boolean);

    if (parts.length >= 2) {
      return (
        parts[0].charAt(0) +
        parts[parts.length - 1].charAt(0)
      ).toUpperCase();
    }

    return cleaned.slice(0, 2).toUpperCase();
  };

  useEffect(() => {
    if (!profileOpen) return;

    const handleClickOutside = (event) => {
      if (
        profileRef.current &&
        !profileRef.current.contains(event.target)
      ) {
        setProfileOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setProfileOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [profileOpen]);

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

    if (item === "Route History") {
      setActiveNav("Route History");
      setView("history");
      setError("");
      loadRouteHistory();
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

        {/* MARITIME SHIP ANIMATION */}

        <div className="ship-scene" aria-hidden="true">
          <div className="ship-water">
            <div className="wave wave-1"></div>
            <div className="wave wave-2"></div>
            <div className="wave wave-3"></div>
          </div>
          <div className="ship-body">
            <div className="ship-hull"></div>
            <div className="ship-deck"></div>
            <div className="ship-bridge"></div>
            <div className="ship-funnel"></div>
            <div className="ship-funnel-smoke">
              <div className="smoke-puff smoke-1"></div>
              <div className="smoke-puff smoke-2"></div>
              <div className="smoke-puff smoke-3"></div>
            </div>
            <div className="ship-containers">
              <div className="container c1"></div>
              <div className="container c2"></div>
              <div className="container c3"></div>
              <div className="container c4"></div>
              <div className="container c5"></div>
            </div>
          </div>
        </div>

        {/* DASHBOARD QUOTATION + WORKSTATION ILLUSTRATION */}

        <div
          className="dashboard-quote-section"
          id="dashboard-quotation"
        >

          <div
            className="workstation-illustration"
            aria-hidden="true"
          >
            <div className="ws-backdrop"></div>
            <div className="ws-shadow"></div>

            <div className="ws-person">
              <div className="ws-head">
                <div className="ws-hair"></div>
              </div>
              <div className="ws-body"></div>
              <div className="ws-arm ws-arm-left"></div>
              <div className="ws-arm ws-arm-right"></div>
              <div className="ws-hand ws-hand-left"></div>
              <div className="ws-hand ws-hand-right"></div>
            </div>

            <div className="ws-laptop">
              <div className="ws-laptop-screen">
                <div className="ws-screen-glow"></div>
                <div className="ws-screen-route">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <div className="ws-screen-ship"></div>
              </div>
              <div className="ws-laptop-base"></div>
            </div>

            <div className="ws-legs"></div>

            <div className="ws-backpack"></div>

            <div className="ws-books">
              <div className="ws-book ws-book-1"></div>
              <div className="ws-book ws-book-2"></div>
              <div className="ws-book ws-book-3"></div>
            </div>

            <div className="ws-ai-badge">
              <span className="ws-ai-dot"></span>
              AI ACTIVE
            </div>

            <div className="ws-ship">
              <div className="ws-ship-hull"></div>
              <div className="ws-ship-deck"></div>
              <div className="ws-ship-bridge"></div>
              <span className="ws-ship-route"></span>
            </div>

            <div className="ws-route-line"></div>

            <div className="ws-node ws-node-1"></div>
            <div className="ws-node ws-node-2"></div>
            <div className="ws-node ws-node-3"></div>
            <div className="ws-node ws-node-4"></div>
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

    // ------------------------------------------------
    // CARGO SUBTYPE DEPENDENT DROPDOWN STATE
    // ------------------------------------------------

    const noSubtypes =
      origin &&
      destination &&
      cargoType &&
      !subtypesLoading &&
      routeCargoSubtypes.length === 0;

    const subtypeDisabled =
      !origin ||
      !destination ||
      !cargoType ||
      subtypesLoading ||
      noSubtypes;

    const subtypePlaceholder =
      !origin
        ? "Select origin first"
        : !destination
        ? "Select destination first"
        : !cargoType
        ? "Select cargo type first"
        : subtypesLoading
        ? "Loading cargo subtypes..."
        : noSubtypes
        ? "No cargo subtypes available"
        : "Select cargo subtype";

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

        {/* ANIMATED ROUTE NETWORK */}

        {origin && destination && (
          <div className="route-network" aria-hidden="true">
            <div className="route-node route-origin">
              <span className="route-node-dot"></span>
              <span className="route-node-label">{origin}</span>
            </div>
            <div className={`route-line-segment ${loading ? 'route-line-active' : ''}`}>
              <div className="route-line-path"></div>
              <div className="route-line-dot route-line-dot-1"></div>
              <div className="route-line-dot route-line-dot-2"></div>
            </div>
            <div className="route-node route-port">
              <span className="route-node-dot"></span>
              <span className="route-node-label">Via Port</span>
            </div>
            <div className={`route-line-segment ${loading ? 'route-line-active' : ''}`}>
              <div className="route-line-path"></div>
              <div className="route-line-dot route-line-dot-1"></div>
              <div className="route-line-dot route-line-dot-2"></div>
            </div>
            <div className="route-node route-dest">
              <span className="route-node-dot"></span>
              <span className="route-node-label">{destination}</span>
            </div>
          </div>
        )}

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
                  handleOriginChange(e.target.value)
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
                  handleDestinationChange(e.target.value)
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

                {Object.keys(cargoSubtypesByType).map(
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
                disabled={subtypeDisabled}
              >

                <option value="">
                  {subtypePlaceholder}
                </option>

                {routeCargoSubtypes.map(
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

              {noSubtypes && (
                <div className="subtype-note">
                  No cargo subtypes available for this route.
                </div>
              )}

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
            <div className="loading-message ai-loading-message">

              <div className="ai-agent" aria-hidden="true">
                <span className="ai-agent-core"></span>
                <span className="ai-agent-ring ai-ring-1"></span>
                <span className="ai-agent-ring ai-ring-2"></span>
                <span className="ai-agent-scan"></span>
              </div>

              <div className="ai-loading-text">
                <strong>AI Route Agent analyzing</strong>
                <span className="ai-loading-dots">
                  <i></i>
                  <i></i>
                  <i></i>
                </span>
              </div>

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
              disabled={loading || subtypeDisabled}
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
          <div className="recommendation-card result-animate">

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

        <div className="comparison-section result-animate result-animate-2">

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
  // ROUTE HISTORY PAGE
  // ==========================================

  const renderHistory = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header history-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={goHome}
            >
              ← Back to Dashboard
            </button>

            <span className="section-label">
              ROUTE HISTORY
            </span>

            <h1>
              Route History
            </h1>

            <p>
              All successfully analyzed maritime routes
              are saved automatically for your review.
            </p>

          </div>

        </div>

        {/* ERROR */}

        {historyError && (
          <div className="error-message">
            {historyError}
          </div>
        )}

        {/* LOADING */}

        {historyLoading && (
          <div className="loading-message">

            <span className="loading-spinner"></span>

            Loading route history...

          </div>
        )}

        {/* EMPTY HISTORY */}

        {!historyLoading &&
          !historyError &&
          history.length === 0 && (
            <div className="history-empty">

              <div className="history-empty-icon">
                ◈
              </div>

              <h3>
                No route analysis history yet.
              </h3>

              <p>
                Analyze a maritime route and it will
                be saved here automatically.
              </p>

              <button
                className="primary-button"
                type="button"
                onClick={goToSearch}
              >
                Analyze a Route →
              </button>

            </div>
          )}

        {/* HISTORY TABLE */}

        {!historyLoading &&
          !historyError &&
          history.length > 0 && (
            <div className="comparison-section history-section">

              <div className="comparison-heading history-heading">

                <div>

                  <span className="section-label">
                    SAVED ANALYSES
                  </span>

                  <h2>
                    {history.length} route
                    {history.length !== 1 ? "s" : ""}
                  </h2>

                </div>

                <button
                  className="danger-button"
                  type="button"
                  disabled={historyActionLoading}
                  onClick={handleClearHistory}
                >
                  Clear All History
                </button>

              </div>

              <div className="table-wrapper">

                <table className="route-table history-table">

                  <thead>

                    <tr>

                      <th>
                        Date & Time
                      </th>

                      <th>
                        Origin
                      </th>

                      <th>
                        Destination
                      </th>

                      <th>
                        Cargo
                      </th>

                      <th>
                        Subtype
                      </th>

                      <th>
                        Containers
                      </th>

                      <th>
                        Recommended Route
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

                      </th>

                    </tr>

                  </thead>

                  <tbody>

                    {history.map((item) => (
                      <tr
                        key={item.record_id}
                        className="history-row"
                      >

                        <td>
                          <span className="history-date">
                            {formatAnalysisDate(
                              item.created_at
                            )}
                          </span>
                        </td>

                        <td>
                          {item.origin || "-"}
                        </td>

                        <td>
                          {item.destination || "-"}
                        </td>

                        <td>
                          {item.cargo_type || "-"}
                        </td>

                        <td>
                          {item.cargo_subtype || "-"}
                        </td>

                        <td>
                          {item.containers ?? "-"}
                        </td>

                        <td>

                          <div className="history-route-cell">

                            <strong className="history-route-id">
                              {item.route_id || "-"}
                            </strong>

                            <span className="history-route-name">
                              {item.route_name ||
                                "Recommended route"}
                            </span>

                          </div>

                        </td>

                        <td>
                          {item.transit_days != null
                            ? `${item.transit_days} days`
                            : "-"}
                        </td>

                        <td>
                          {item.distance_nm != null
                            ? `${item.distance_nm} nm`
                            : "-"}
                        </td>

                        <td>
                          {item.transshipments ?? "-"}
                        </td>

                        <td>

                          <button
                            className="history-delete"
                            type="button"
                            disabled={historyActionLoading}
                            onClick={() =>
                              handleDeleteHistory(
                                item.record_id
                              )
                            }
                            aria-label="Delete route history record"
                          >
                            Delete
                          </button>

                        </td>

                      </tr>
                    ))}

                  </tbody>

                </table>

              </div>

            </div>
          )}

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
              activeNav === "Route History"
                ? "nav-item active"
                : "nav-item"
            }
            type="button"
            onClick={() =>
              handleNavClick("Route History")
            }
          >

            <span className="nav-icon">
              ◇
            </span>

            Route History

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

          <div
            className="topbar-profile"
            ref={profileRef}
          >

            <button
              className={
                profileOpen
                  ? "profile-trigger profile-trigger-open"
                  : "profile-trigger"
              }
              type="button"
              onClick={() =>
                setProfileOpen((open) => !open)
              }
              aria-haspopup="menu"
              aria-expanded={profileOpen}
              aria-label="Open user profile menu"
            >

              <span className="profile-avatar">
                {getProfileInitials(profileName)}
              </span>

              <span className="profile-info">

                <strong className="profile-name">
                  {profileName}
                </strong>

                <span className="profile-role">
                  Maritime Analyst
                </span>

              </span>

              <span
                className={
                  profileOpen
                    ? "profile-caret profile-caret-open"
                    : "profile-caret"
                }
                aria-hidden="true"
              ></span>

            </button>

            {profileOpen && (
              <div
                className="profile-menu"
                role="menu"
                aria-label="User account menu"
              >

                <div className="profile-menu-head">

                  <span className="profile-menu-avatar">
                    {getProfileInitials(profileName)}
                  </span>

                  <div className="profile-menu-id">

                    <strong>
                      {profileName}
                    </strong>

                    <span>
                      {profileContact ||
                        "Maritime Analyst"}
                    </span>

                  </div>

                </div>

                <div className="profile-menu-rows">

                  <div className="profile-menu-row">

                    <span>
                      Role
                    </span>

                    <strong>
                      Maritime Analyst
                    </strong>

                  </div>

                  <div className="profile-menu-row">

                    <span>
                      Account
                    </span>

                    <strong className="account-active">
                      Active
                    </strong>

                  </div>

                </div>

                <button
                  className="profile-menu-logout"
                  type="button"
                  onClick={handleLogout}
                  role="menuitem"
                >
                  Logout
                </button>

              </div>
            )}

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

          {view === "history" &&
            renderHistory()}

        </div>

      </main>

    </div>
  );
}

export default App;