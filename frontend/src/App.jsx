import React, { useEffect, useRef, useState } from "react";

const howToSteps = [
  {
    icon: "◉",
    title: "Login to Maritime AI",
    description:
      "Login using your registered email or mobile number and password to access the dashboard.",
  },
  {
    icon: "⇢",
    title: "Select Your Route",
    description:
      "Go to Route Intelligence and select the origin and destination for your shipment.",
  },
  {
    icon: "▣",
    title: "Choose Cargo Details",
    description:
      "Select the cargo type and the available cargo subtype for your shipment.",
  },
  {
    icon: "▤",
    title: "Enter Container Quantity",
    description:
      "Enter the number of containers required for the shipment.",
  },
  {
    icon: "⌖",
    title: "Analyze Route",
    description:
      "Click Analyze Route. The Route Agent evaluates available routes and recommends the most suitable route.",
  },
  {
    icon: "$",
    title: "Generate Quotation",
    description:
      "Generate the pricing and margin quotation using the Pricing Agent and Margin Agent.",
  },
  {
    icon: "%",
    title: "Review Pricing & Margin",
    description:
      "Review operating cost, demand-adjusted cost, selling price, expected profit, and achieved margin.",
  },
  {
    icon: "◇",
    title: "View Route History",
    description:
      "Open Route History to review your previous route analyses and generated quotations.",
  },
];

const howToWorkflow = [
  { icon: "◉", label: "Login" },
  { icon: "⇢", label: "Route Intelligence" },
  { icon: "⌖", label: "Analyze Route" },
  { icon: "%", label: "Pricing & Margin" },
  { icon: "$", label: "Generate Quotation" },
  { icon: "▤", label: "Accept Quotation" },
  { icon: "◇", label: "Track Shipment" },
];

// ==========================================
// SHIPMENT STATUS WORKFLOW
// Matches the backend SHIPMENT_STATUS_FLOW.
// This is a platform workflow simulation;
// no real vessel/GPS tracking is claimed.
// ==========================================

const shipmentStatusFlow = [
  "Booking Confirmed",
  "Cargo Ready",
  "At Origin Port",
  "Vessel Departed",
  "In Transit",
  "At Destination Port",
  "Delivered",
];

// ==========================================
// ANIMATED NUMBER COUNTER
// Counts from 0 to the target value when it
// scrolls into view. Used only by the normal
// User Dashboard stats grid.
// ==========================================

function AnimatedNumber({
  value,
  duration = 1100,
}) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(null);

  useEffect(() => {
    const target = Number(value) || 0;
    const el = ref.current;

    const animate = () => {
      const start = performance.now();

      const tick = (now) => {
        const progress = Math.min(
          (now - start) / duration,
          1
        );
        const eased =
          1 - Math.pow(1 - progress, 3);
        setDisplay(Math.round(target * eased));

        if (progress < 1) {
          requestAnimationFrame(tick);
        }
      };

      requestAnimationFrame(tick);
    };

    if (!("IntersectionObserver" in window) || !el) {
      animate();
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            animate();
            observer.disconnect();
          }
        });
      },
      { threshold: 0.3 }
    );

    observer.observe(el);

    return () => observer.disconnect();
  }, [value, duration]);

  return (
    <strong
      className="animated-number"
      ref={ref}
    >
      {display.toLocaleString()}
    </strong>
  );
}

function App() {
  const readSavedUser = () => {
    try {
      const saved =
        localStorage.getItem("loggedInUser") ||
        localStorage.getItem("user");

      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  };

  const [view, setView] = useState(() => {
    const saved = readSavedUser();
    return saved?.role === "admin"
      ? "admin-home"
      : "home";
  });

  const [activeNav, setActiveNav] = useState(() => {
    const saved = readSavedUser();
    return saved?.role === "admin"
      ? "Admin Dashboard"
      : "Dashboard";
  });

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

  const [user] = useState(readSavedUser);

  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [historyActionLoading, setHistoryActionLoading] =
    useState(false);

  const [quotation, setQuotation] = useState(null);
  const [quotationLoading, setQuotationLoading] =
    useState(false);
  const [quotationError, setQuotationError] = useState("");

  // ==========================================
  // SHIPMENT STATE
  // ==========================================

  const [shipments, setShipments] = useState([]);
  const [shipmentsLoading, setShipmentsLoading] =
    useState(false);
  const [shipmentsError, setShipmentsError] = useState("");

  const [shipmentDetails, setShipmentDetails] = useState(null);
  const [shipmentDetailsLoading, setShipmentDetailsLoading] =
    useState(false);
  const [shipmentDetailsError, setShipmentDetailsError] =
    useState("");

  const [acceptingQuotation, setAcceptingQuotation] =
    useState(false);
  const [acceptResult, setAcceptResult] = useState(null);
  const [acceptError, setAcceptError] = useState("");

  // ==========================================
  // ADMIN STATE
  // ==========================================

  const [adminStats, setAdminStats] = useState(null);
  const [adminStatsLoading, setAdminStatsLoading] =
    useState(false);
  const [adminStatsError, setAdminStatsError] = useState("");
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminUsersLoading, setAdminUsersLoading] =
    useState(false);
  const [adminUsersError, setAdminUsersError] = useState("");
  const [adminUserSearch, setAdminUserSearch] = useState("");
  const [adminActivity, setAdminActivity] = useState([]);
  const [adminActivityLoading, setAdminActivityLoading] =
    useState(false);
  const [adminActivityError, setAdminActivityError] =
    useState("");
  const [adminQuotations, setAdminQuotations] = useState([]);
  const [adminQuotationsLoading, setAdminQuotationsLoading] =
    useState(false);
  const [adminQuotationsError, setAdminQuotationsError] =
    useState("");
  const [adminShipments, setAdminShipments] = useState([]);
  const [adminShipmentsLoading, setAdminShipmentsLoading] =
    useState(false);
  const [adminShipmentsError, setAdminShipmentsError] =
    useState("");
  const [adminShipmentFilter, setAdminShipmentFilter] =
    useState("");
  const [adminShipmentStatuses, setAdminShipmentStatuses] =
    useState([]);
  const [updatingShipmentId, setUpdatingShipmentId] =
    useState(null);
  const [adminShipmentMessage, setAdminShipmentMessage] =
    useState("");
  const [adminShipmentMessageError, setAdminShipmentMessageError] =
    useState("");
  const [adminPricing, setAdminPricing] = useState([]);
  const [adminPricingLoading, setAdminPricingLoading] =
    useState(false);
  const [adminPricingError, setAdminPricingError] =
    useState("");

  // ==========================================
  // FEEDBACK STATE
  // ==========================================

  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackType, setFeedbackType] = useState("");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [feedbackSubmitting, setFeedbackSubmitting] =
    useState(false);
  const [feedbackSuccess, setFeedbackSuccess] =
    useState("");
  const [feedbackError, setFeedbackError] = useState("");
  const [myFeedback, setMyFeedback] = useState([]);
  const [myFeedbackLoading, setMyFeedbackLoading] =
    useState(false);
  const [myFeedbackError, setMyFeedbackError] =
    useState("");

  // ==========================================
  // ADMIN FEEDBACK STATE
  // ==========================================

  const [adminFeedback, setAdminFeedback] = useState([]);
  const [adminFeedbackLoading, setAdminFeedbackLoading] =
    useState(false);
  const [adminFeedbackError, setAdminFeedbackError] =
    useState("");

  // ==========================================
  // ADMIN INVITATION STATE
  // ==========================================

  const [inviteContact, setInviteContact] = useState("");
  const [inviteGenerating, setInviteGenerating] =
    useState(false);
  const [inviteResult, setInviteResult] = useState(null);
  const [inviteError, setInviteError] = useState("");
  const [adminInvitations, setAdminInvitations] =
    useState([]);
  const [adminInvitationsLoading, setAdminInvitationsLoading] =
    useState(false);
  const [adminInvitationsError, setAdminInvitationsError] =
    useState("");
  const [copiedInvite, setCopiedInvite] = useState(false);

  // ==========================================
  // LOGIN CHECK
  // The saved user, initial view and active nav
  // are derived once at mount from localStorage
  // via the lazy state initializers above.
  // ==========================================

  useEffect(() => {
    const loggedIn = localStorage.getItem("isLoggedIn");

    if (loggedIn !== "true") {
      window.location.href = "/login.html";
    }
  }, []);

  // ==========================================
  // USER ROLE
  // Old localStorage records may have no role.
  // They are always treated as a normal user.
  // ==========================================

  const userRole =
    user?.role === "admin" ? "admin" : "user";

  const isAdmin = userRole === "admin";

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
    setAcceptError("");
    setAcceptResult(null);
  };

  const handleNewSearch = () => {
    setView("search");
    setActiveNav("Routes");
    setResult(null);
    setError("");
    setAcceptError("");
    setAcceptResult(null);
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

  const getAuthHeaders = () => {
    const token =
      localStorage.getItem("authToken");

    if (token) {
      return {
        Authorization: `Bearer ${token}`,
      };
    }

    return {};
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
        `http://127.0.0.1:8000/api/routes/history?${params}`,
        { headers: { ...getAuthHeaders() } }
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
          headers: { ...getAuthHeaders() },
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
          headers: { ...getAuthHeaders() },
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
    setAcceptError("");
    setAcceptResult(null);
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
    setAcceptError("");
    setAcceptResult(null);
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
    setAcceptError("");
    setAcceptResult(null);

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
            ...getAuthHeaders(),
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
  // GENERATE QUOTATION
  // Calls the Pricing Agent and Margin Agent
  // pipeline to produce a dynamic quotation.
  // ==========================================

  const handleGenerateQuotation = async () => {
    setQuotationError("");
    setQuotation(null);
    setAcceptError("");
    setAcceptResult(null);

    if (!origin || !destination || !cargoType || !cargoSubtype) {
      setQuotationError(
        "Shipment details are required to generate a quotation."
      );
      return;
    }

    try {
      setQuotationLoading(true);

      const response = await fetch(
        "http://127.0.0.1:8000/api/quotations/generate",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...getAuthHeaders(),
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
            "Unable to generate quotation."
        );
      }

      if (data?.status === "error") {
        throw new Error(
          data?.message ||
            "Quotation generation failed."
        );
      }

      setQuotation(data);
    } catch (err) {
      console.error("Quotation generation error:", err);
      setQuotationError(
        err.message ||
          "Unable to connect to the quotation service."
      );
    } finally {
      setQuotationLoading(false);
    }
  };

  // ==========================================
  // MY SHIPMENTS
  // Loads only the logged-in user's shipments
  // from the backend. Never hard-coded.
  // ==========================================

  const goToShipments = () => {
    setActiveNav("My Shipments");
    setView("shipments");
    setError("");
    loadShipments();
  };

  const loadShipments = async () => {
    const identity = resolveUser();

    if (!identity.id) {
      setShipments([]);
      setShipmentsError(
        "Sign in is required to view your shipments."
      );
      setShipmentsLoading(false);
      return;
    }

    setShipmentsLoading(true);
    setShipmentsError("");

    try {
      const params = new URLSearchParams({
        user_id: identity.id,
      });

      if (identity.contact) {
        params.append("contact", identity.contact);
      }

      const response = await fetch(
        `http://127.0.0.1:8000/api/shipments?${params}`,
        { headers: { ...getAuthHeaders() } }
      );

      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({}));
        throw new Error(
          data?.detail ||
            "Unable to load your shipments."
        );
      }

      const data = await response.json();

      setShipments(data?.shipments || []);
    } catch (err) {
      console.error("Shipments loading error:", err);
      setShipments([]);
      setShipmentsError(
        err.message ||
          "Unable to load your shipments."
      );
    } finally {
      setShipmentsLoading(false);
    }
  };

  // ==========================================
  // SHIPMENT DETAILS
  // Fetches one shipment guarded by the backend
  // so a user can only open their own shipment.
  // ==========================================

  const openShipmentDetails = (shipmentId) => {
    setActiveNav("My Shipments");
    setView("shipment-details");
    setError("");
    loadShipmentDetails(shipmentId);
  };

  const loadShipmentDetails = async (shipmentId) => {
    setShipmentDetails(null);
    setShipmentDetailsError("");
    setShipmentDetailsLoading(true);

    const identity = resolveUser();

    try {
      const params = new URLSearchParams();

      if (identity.id) {
        params.append("user_id", identity.id);
      }

      if (identity.contact) {
        params.append("contact", identity.contact);
      }

      const query = params.toString();

      const response = await fetch(
        `http://127.0.0.1:8000/api/shipments/${encodeURIComponent(
          shipmentId
        )}${query ? `?${query}` : ""}`,
        { headers: { ...getAuthHeaders() } }
      );

      if (!response.ok) {
        const data = await response
          .json()
          .catch(() => ({}));
        throw new Error(
          data?.detail ||
            "Unable to load the shipment details."
        );
      }

      const data = await response.json();

      setShipmentDetails(data?.shipment || null);
    } catch (err) {
      console.error(
        "Shipment details loading error:",
        err
      );
      setShipmentDetails(null);
      setShipmentDetailsError(
        err.message ||
          "Unable to load the shipment details."
      );
    } finally {
      setShipmentDetailsLoading(false);
    }
  };

  // ==========================================
  // ACCEPT QUOTATION -> CREATE SHIPMENT
  // A shipment is created ONLY when the user
  // explicitly accepts a generated quotation.
  // Accepting the same quotation twice never
  // creates a duplicate shipment.
  // ==========================================

  const handleAcceptQuotation = async () => {
    const quotationId = quotation?.quotation_id;

    if (!quotationId) {
      setAcceptError(
        "No valid quotation reference is available. Generate a quotation first."
      );
      return;
    }

    setAcceptError("");
    setAcceptResult(null);
    setAcceptingQuotation(true);

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/api/quotations/${encodeURIComponent(
          quotationId
        )}/accept`,
        {
          method: "POST",
          headers: { ...getAuthHeaders() },
        }
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            data?.message ||
            "Unable to accept this quotation."
        );
      }

      setAcceptResult(data);
    } catch (err) {
      console.error(
        "Quotation acceptance error:",
        err
      );
      setAcceptError(
        err.message ||
          "Unable to accept this quotation."
      );
    } finally {
      setAcceptingQuotation(false);
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
    localStorage.removeItem("authToken");

    window.location.href = "/login.html";
  };

  // ==========================================
  // ADMIN API HELPER
  // Sends the backend-issued token so the
  // server can verify the admin role there.
  // ==========================================

  const adminFetch = async (url, options = {}) => {
    const token =
      localStorage.getItem("authToken");

    const headers = {
      ...(options.headers || {}),
    };

    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    return fetch(url, {
      ...options,
      headers,
    });
  };

  // ==========================================
  // LOAD ADMIN STATS
  // ==========================================

  const loadAdminStats = async () => {
    setAdminStatsLoading(true);
    setAdminStatsError("");

    try {
      const response = await adminFetch(
        "http://127.0.0.1:8000/api/admin/stats"
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load admin statistics."
        );
      }

      setAdminStats({
        total_users: data.total_users ?? 0,
        total_route_analyses:
          data.total_route_analyses ?? 0,
        total_quotations: data.total_quotations ?? 0,
        total_shipments: data.total_shipments ?? 0,
        active_shipments: data.active_shipments ?? 0,
        delivered_shipments:
          data.delivered_shipments ?? 0,
      });
    } catch (err) {
      console.error(
        "Admin stats loading error:",
        err
      );
      setAdminStats(null);
      setAdminStatsError(
        err.message ||
          "Unable to load admin statistics."
      );
    } finally {
      setAdminStatsLoading(false);
    }
  };

  // ==========================================
  // LOAD ADMIN USERS
  // ==========================================

  const loadAdminUsers = async () => {
    setAdminUsersLoading(true);
    setAdminUsersError("");

    try {
      const params = new URLSearchParams();

      if (adminUserSearch.trim()) {
        params.append("search", adminUserSearch.trim());
      }

      const query = params.toString();

      const response = await adminFetch(
        `http://127.0.0.1:8000/api/admin/users${query ? `?${query}` : ""}`
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load registered users."
        );
      }

      setAdminUsers(data?.users || []);
    } catch (err) {
      console.error(
        "Admin users loading error:",
        err
      );
      setAdminUsers([]);
      setAdminUsersError(
        err.message ||
          "Unable to load registered users."
      );
    } finally {
      setAdminUsersLoading(false);
    }
  };

  // ==========================================
  // LOAD ADMIN ROUTE ACTIVITY
  // ==========================================

  const loadAdminActivity = async () => {
    setAdminActivityLoading(true);
    setAdminActivityError("");

    try {
      const response = await adminFetch(
        "http://127.0.0.1:8000/api/admin/route-activity"
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load route activity."
        );
      }

      setAdminActivity(data?.activity || []);
    } catch (err) {
      console.error(
        "Admin route activity loading error:",
        err
      );
      setAdminActivity([]);
      setAdminActivityError(
        err.message ||
          "Unable to load route activity."
      );
    } finally {
      setAdminActivityLoading(false);
    }
  };

  // ==========================================
  // LOAD ADMIN QUOTATIONS
  // ==========================================

  const loadAdminQuotations = async () => {
    setAdminQuotationsLoading(true);
    setAdminQuotationsError("");

    try {
      const response = await adminFetch(
        "http://127.0.0.1:8000/api/admin/quotations"
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load quotations."
        );
      }

      setAdminQuotations(data?.quotations || []);
    } catch (err) {
      console.error(
        "Admin quotations loading error:",
        err
      );
      setAdminQuotations([]);
      setAdminQuotationsError(
        err.message ||
          "Unable to load quotations."
      );
    } finally {
      setAdminQuotationsLoading(false);
    }
  };

  // ==========================================
  // LOAD ADMIN SHIPMENTS
  // ==========================================

  const loadAdminShipments = async (statusFilter) => {
    const filter =
      statusFilter !== undefined
        ? statusFilter
        : adminShipmentFilter;

    setAdminShipmentsLoading(true);
    setAdminShipmentsError("");
    setAdminShipmentMessage("");
    setAdminShipmentMessageError("");

    try {
      const params = new URLSearchParams();

      if (filter.trim()) {
        params.append("status", filter.trim());
      }

      const query = params.toString();

      const response = await adminFetch(
        `http://127.0.0.1:8000/api/admin/shipments${query ? `?${query}` : ""}`
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load shipments."
        );
      }

      setAdminShipments(data?.shipments || []);
      setAdminShipmentStatuses(
        data?.statuses ||
          shipmentStatusFlow ||
          []
      );
    } catch (err) {
      console.error(
        "Admin shipments loading error:",
        err
      );
      setAdminShipments([]);
      setAdminShipmentsError(
        err.message ||
          "Unable to load shipments."
      );
    } finally {
      setAdminShipmentsLoading(false);
    }
  };

  const handleAdminShipmentFilter = (status) => {
    setAdminShipmentFilter(status);
    loadAdminShipments(status);
  };

  // ==========================================
  // UPDATE ADMIN SHIPMENT STATUS
  // Uses the backend forward-only workflow.
  // ==========================================

  const handleAdminShipmentStatusChange = async (
    shipment,
    newStatus
  ) => {
    if (
      newStatus === shipment.status ||
      !newStatus
    ) {
      return;
    }

    setUpdatingShipmentId(shipment.shipment_id);
    setAdminShipmentMessage("");
    setAdminShipmentMessageError("");

    try {
      const response = await adminFetch(
        `http://127.0.0.1:8000/api/admin/shipments/${encodeURIComponent(
          shipment.shipment_id
        )}/status`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            status: newStatus,
          }),
        }
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to update shipment status."
        );
      }

      setAdminShipmentMessage(
        data?.message ||
          `Shipment ${shipment.shipment_id} status updated.`
      );

      setAdminShipments((prev) =>
        prev.map((item) =>
          item.shipment_id === shipment.shipment_id
            ? data?.shipment || item
            : item
        )
      );
    } catch (err) {
      console.error(
        "Admin shipment status update error:",
        err
      );
      setAdminShipmentMessageError(
        err.message ||
          "Unable to update shipment status."
      );
    } finally {
      setUpdatingShipmentId(null);
    }
  };

  // ==========================================
  // LOAD ADMIN PRICING & MARGIN
  // ==========================================

  const loadAdminPricing = async () => {
    setAdminPricingLoading(true);
    setAdminPricingError("");

    try {
      const response = await adminFetch(
        "http://127.0.0.1:8000/api/admin/pricing"
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load pricing & margin data."
        );
      }

      setAdminPricing(data?.pricing || []);
    } catch (err) {
      console.error(
        "Admin pricing loading error:",
        err
      );
      setAdminPricing([]);
      setAdminPricingError(
        err.message ||
          "Unable to load pricing & margin data."
      );
    } finally {
      setAdminPricingLoading(false);
    }
  };

  // ==========================================
  // USER FEEDBACK
  // ==========================================

  const loadMyFeedback = async () => {
    setMyFeedbackLoading(true);
    setMyFeedbackError("");

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/feedback",
        { headers: { ...getAuthHeaders() } }
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load your feedback."
        );
      }

      setMyFeedback(data?.feedback || []);
    } catch (err) {
      console.error(
        "Feedback loading error:",
        err
      );
      setMyFeedback([]);
      setMyFeedbackError(
        err.message ||
          "Unable to load your feedback."
      );
    } finally {
      setMyFeedbackLoading(false);
    }
  };

  const handleSubmitFeedback = async (e) => {
    e.preventDefault();

    setFeedbackError("");
    setFeedbackSuccess("");

    if (!feedbackRating) {
      setFeedbackError(
        "Please select a rating first."
      );
      return;
    }

    if (!feedbackType) {
      setFeedbackError(
        "Please select a feedback type."
      );
      return;
    }

    if (!feedbackMessage.trim()) {
      setFeedbackError(
        "Please enter your feedback message."
      );
      return;
    }

    setFeedbackSubmitting(true);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/feedback",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...getAuthHeaders(),
          },
          body: JSON.stringify({
            rating: Number(feedbackRating),
            feedback_type: feedbackType,
            message: feedbackMessage,
          }),
        }
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            data?.message ||
            "Unable to submit feedback."
        );
      }

      setFeedbackSuccess(
        data?.message ||
          "Thank you! Your feedback has been submitted."
      );
      setFeedbackRating(0);
      setFeedbackType("");
      setFeedbackMessage("");
      loadMyFeedback();
    } catch (err) {
      console.error(
        "Feedback submission error:",
        err
      );
      setFeedbackError(
        err.message ||
          "Unable to submit feedback."
      );
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  // ==========================================
  // ADMIN FEEDBACK
  // ==========================================

  const loadAdminFeedback = async () => {
    setAdminFeedbackLoading(true);
    setAdminFeedbackError("");

    try {
      const response = await adminFetch(
        "http://127.0.0.1:8000/api/admin/feedback"
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load feedback."
        );
      }

      setAdminFeedback(data?.feedback || []);
    } catch (err) {
      console.error(
        "Admin feedback loading error:",
        err
      );
      setAdminFeedback([]);
      setAdminFeedbackError(
        err.message ||
          "Unable to load feedback."
      );
    } finally {
      setAdminFeedbackLoading(false);
    }
  };

  // ==========================================
  // ADMIN INVITATIONS
  // ==========================================

  const loadAdminInvitations = async () => {
    setAdminInvitationsLoading(true);
    setAdminInvitationsError("");

    try {
      const response = await adminFetch(
        "http://127.0.0.1:8000/api/admin/invitations"
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to load invitations."
        );
      }

      setAdminInvitations(data?.invitations || []);
    } catch (err) {
      console.error(
        "Admin invitations loading error:",
        err
      );
      setAdminInvitations([]);
      setAdminInvitationsError(
        err.message ||
          "Unable to load invitations."
      );
    } finally {
      setAdminInvitationsLoading(false);
    }
  };

  const handleGenerateInvitation = async (e) => {
    e.preventDefault();

    setInviteError("");
    setInviteResult(null);
    setCopiedInvite(false);

    if (!inviteContact.trim()) {
      setInviteError(
        "Please enter a contact email."
      );
      return;
    }

    setInviteGenerating(true);

    try {
      const response = await adminFetch(
        "http://127.0.0.1:8000/api/admin/invitations",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            invited_contact: inviteContact.trim(),
          }),
        }
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to generate invitation."
        );
      }

      setInviteResult(data?.invitation || null);
      setInviteContact("");
      loadAdminInvitations();
    } catch (err) {
      console.error(
        "Invitation generation error:",
        err
      );
      setInviteError(
        err.message ||
          "Unable to generate invitation."
      );
    } finally {
      setInviteGenerating(false);
    }
  };

  const copyInviteLink = () => {
    const token = inviteResult?.token;

    if (!token) return;

    const link =
      `${window.location.origin}/accept-invitation.html?token=${encodeURIComponent(
        token
      )}`;

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(link)
        .then(() => {
          setCopiedInvite(true);
          setTimeout(() => setCopiedInvite(false), 2500);
        })
        .catch(() => {
          prompt(
            "Copy the invitation link:",
            link
          );
        });
    } else {
      prompt("Copy the invitation link:", link);
    }
  };

  const formatFullDate = (value) => {
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

  const starLabel = (rating) => {
    if (!rating) return "Select a rating";
    if (rating === 1) return "Poor";
    if (rating === 2) return "Fair";
    if (rating === 3) return "Good";
    if (rating === 4) return "Very Good";
    return "Excellent";
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

  const profileRoleLabel = isAdmin
    ? "Administrator"
    : "User";

  const profileRoleSubLabel = isAdmin
    ? "Admin Dashboard"
    : "Maritime Analyst";

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

    if (item === "My Shipments") {
      setActiveNav("My Shipments");
      setView("shipments");
      setError("");
      loadShipments();
      return;
    }

    if (item === "Shipments") {
      if (isAdmin) {
        setActiveNav("Shipments");
        setView("admin-shipments");
        setError("");
        loadAdminShipments();
      } else {
        setActiveNav("My Shipments");
        setView("shipments");
        setError("");
        loadShipments();
      }
      return;
    }

    if (item === "Quotation") {
      setActiveNav("Quotation");
      setView("quotation");
      setError("");
      return;
    }

    if (item === "How to Use") {
      setActiveNav("How to Use");
      setView("howto");
      setError("");
      return;
    }

    if (item === "Feedback") {
      setActiveNav("Feedback");
      setView("feedback");
      setError("");
      loadMyFeedback();
      return;
    }

    // ----------------------------------------
    // ADMIN SECTIONS
    // ----------------------------------------

    if (item === "Admin Dashboard") {
      setActiveNav("Admin Dashboard");
      setView("admin-home");
      setError("");
      loadAdminStats();
      loadAdminShipments();
      loadAdminActivity();
      return;
    }

    if (item === "Users") {
      setActiveNav("Users");
      setView("admin-users");
      setError("");
      loadAdminUsers();
      return;
    }

    if (item === "Quotations") {
      setActiveNav("Quotations");
      setView("admin-quotations");
      setError("");
      loadAdminQuotations();
      return;
    }

    if (item === "Pricing & Margin") {
      setActiveNav("Pricing & Margin");
      setView("admin-pricing");
      setError("");
      loadAdminPricing();
      return;
    }

    if (item === "Route Activity") {
      setActiveNav("Route Activity");
      setView("admin-activity");
      setError("");
      loadAdminActivity();
      return;
    }

    if (item === "User Feedback") {
      setActiveNav("User Feedback");
      setView("admin-feedback");
      setError("");
      loadAdminFeedback();
      return;
    }

    if (item === "Admin Invitations") {
      setActiveNav("Admin Invitations");
      setView("admin-invitations");
      setError("");
      loadAdminInvitations();
      return;
    }

    setActiveNav(item);
    setError(`${item} module is not available yet.`);
  };

  // ==========================================
  // ADMIN SIDEBAR DATA LOADING
  // The current users list is refreshed when
  // the search changes.
  // ==========================================

  const handleAdminUserSearch = (value) => {
    setAdminUserSearch(value);
  };

  useEffect(() => {
    if (activeNav === "Users") {
      const timer = setTimeout(
        loadAdminUsers,
        350
      );
      return () => clearTimeout(timer);
    }
  // adminUserSearch is the only meaningful trigger for the debounce;
  // activeNav is a guard, loadAdminUsers is intentionally omitted
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adminUserSearch]);

  // ==========================================
  // ADMIN DASHBOARD
  // Loads the admin dashboard data when the
  // admin first lands on the main dashboard.
  // ==========================================

  useEffect(() => {
    if (isAdmin && view === "admin-home") {
      loadAdminStats();
      loadAdminShipments();
      loadAdminActivity();
    }
  // Intentionally run only when entering the admin
  // dashboard so navigation through the sidebar
  // controls the loading (handleNavClick handles it).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, view]);

  // ==========================================
  // USER DASHBOARD LIVE STATS
  // Feeds the animated stat counters on the home
  // dashboard from the user's real route history
  // and shipments. Display only.
  // ==========================================

  const activeShipmentCount = shipments.filter(
    (shipment) =>
      shipment.status &&
      shipment.status !== "Delivered"
  ).length;

  const deliveredShipmentCount = shipments.filter(
    (shipment) => shipment.status === "Delivered"
  ).length;

  useEffect(() => {
    if (!isAdmin && view === "home") {
      loadRouteHistory();
      loadShipments();
    }
  // Runs when the user lands on the dashboard so the
  // counters always show fresh live numbers.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, view]);

  // ==========================================
  // DASHBOARD
  // ==========================================

  const renderHome = () => {
    return (
      <section className="home-screen dashboard-animated page-view">

        {/* MARITIME / AI BACKGROUND MOTION */}
        {/* Decorative layer behind the dashboard content. */}
        {/* Aesthetic only. */}

        <div className="dashboard-backdrop" aria-hidden="true">
          <div className="db-aurora db-aurora-1"></div>
          <div className="db-aurora db-aurora-2"></div>
          <div className="db-aurora db-aurora-3"></div>
          <div className="db-grid"></div>
          <div className="db-particles">
            <span className="db-particle p1"></span>
            <span className="db-particle p2"></span>
            <span className="db-particle p3"></span>
            <span className="db-particle p4"></span>
            <span className="db-particle p5"></span>
            <span className="db-particle p6"></span>
          </div>
        </div>

        {/* WELCOME / HEADER */}

        <div className="welcome-block dashboard-welcome">

          <div className="welcome-text">

            <div className="ai-status-pill">
              <span className="ai-status-dot"></span>
              AI SYSTEMS ONLINE
            </div>

            <span className="welcome-label">
              MARITIME AI PLATFORM
            </span>

            <h1>
              Welcome,{" "}
              <span className="welcome-name">
                {profileName}
              </span>
            </h1>

            <p>
              Intelligent route planning for smarter maritime
              freight decisions.
            </p>

          </div>

        </div>

        {/* AI AGENT STATUS PANEL */}

        <div className="ai-agent-panel">

          <div className="ai-panel-head">

            <span className="ai-panel-title">
              <span className="ai-panel-dot"></span>
              AI Control Plane
            </span>

            <span className="ai-panel-sub">
              All systems operational
            </span>

          </div>

          <div className="ai-agent-row">

            <div className="ai-agent-chip">
              <span className="ai-chip-core"></span>
              <span className="ai-chip-meta">
                <strong>Route Agent</strong>
                <span>Navigation & routing intelligence</span>
              </span>
              <span className="ai-chip-status online">
                Online
              </span>
            </div>

            <div className="ai-agent-chip">
              <span className="ai-chip-core"></span>
              <span className="ai-chip-meta">
                <strong>Pricing Agent</strong>
                <span>Dynamic pricing engine</span>
              </span>
              <span className="ai-chip-status online">
                Online
              </span>
            </div>

            <div className="ai-agent-chip">
              <span className="ai-chip-core"></span>
              <span className="ai-chip-meta">
                <strong>Margin Agent</strong>
                <span>Profit & margin guardrails</span>
              </span>
              <span className="ai-chip-status online">
                Online
              </span>
            </div>

          </div>

        </div>

        {/* ANIMATED STATISTICS */}

        <div className="dashboard-stats">

          <div className="stat-card">
            <div className="stat-icon">⇢</div>
            <div className="stat-meta">
              <AnimatedNumber value={history.length} />
              <span>Routes Analyzed</span>
            </div>
            <div className="stat-glow"></div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">◉</div>
            <div className="stat-meta">
              <AnimatedNumber value={activeShipmentCount} />
              <span>Active Shipments</span>
            </div>
            <div className="stat-glow"></div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">◎</div>
            <div className="stat-meta">
              <AnimatedNumber value={deliveredShipmentCount} />
              <span>Delivered Shipments</span>
            </div>
            <div className="stat-glow"></div>
          </div>

          <div className="stat-card">
            <div className="stat-icon">✦</div>
            <div className="stat-meta">
              <AnimatedNumber value={3} />
              <span>AI Agents Active</span>
            </div>
            <div className="stat-glow"></div>
          </div>

        </div>

        {/* MARITIME SHIP + ROUTE ACTIVITY ANIMATION */}

        <div className="ship-scene" aria-hidden="true">

          <div className="ship-route-track">
            <span className="ship-port port-a"></span>
            <span className="ship-port port-b"></span>
            <span className="ship-cargo-dot"></span>
          </div>

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

        {/* QUICK ACTIONS */}

        <div className="dashboard-quick-actions">

          <button
            className="quick-action-btn"
            type="button"
            onClick={() =>
              handleNavClick("Route History")
            }
          >

            <span className="qa-icon">
              ◇
            </span>

            <span className="qa-text">
              <strong>Route History</strong>
              <span>Review past route analyses</span>
            </span>

            <span className="qa-arrow" aria-hidden="true">
              →
            </span>

          </button>

          <button
            className="quick-action-btn"
            type="button"
            onClick={goToShipments}
          >

            <span className="qa-icon">
              ▤
            </span>

            <span className="qa-text">
              <strong>My Shipments</strong>
              <span>Track cargo progress</span>
            </span>

            <span className="qa-arrow" aria-hidden="true">
              →
            </span>

          </button>

        </div>

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

          <div className="info-card dashboard-card">

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

          <div className="info-card dashboard-card">

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

          <div className="info-card dashboard-card">

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

        {/* GET QUOTATION BUTTON */}

        {!quotation && !quotationLoading && (
          <div className="quotation-cta-section result-animate result-animate-2">
            <button
              className="quotation-cta-button"
              type="button"
              onClick={handleGenerateQuotation}
            >
              <div className="quotation-cta-icon">
                $
              </div>
              <div className="quotation-cta-text">
                <strong>
                  {isAdmin
                    ? "Generate Pricing & Margin Quotation"
                    : "Generate Your Quotation"}
                </strong>
                <span>
                  {isAdmin
                    ? "Run Pricing Agent and Margin Agent to calculate the optimal selling price for this shipment"
                    : "Calculate a transparent, competitive total price for this shipment"}
                </span>
              </div>
              <div className="quotation-cta-arrow">
                →
              </div>
            </button>
          </div>
        )}

        {/* QUOTATION LOADING */}

        {quotationLoading && (
          <div className="quotation-loading result-animate result-animate-2">
            <div className="ai-agent" aria-hidden="true">
              <span className="ai-agent-core"></span>
              <span className="ai-agent-ring ai-ring-1"></span>
              <span className="ai-agent-ring ai-ring-2"></span>
              <span className="ai-agent-scan"></span>
            </div>
            <div className="ai-loading-text">
              <strong>
                Pricing Agent & Margin Agent calculating
              </strong>
              <span className="ai-loading-dots">
                <i></i>
                <i></i>
                <i></i>
              </span>
            </div>
          </div>
        )}

        {/* QUOTATION ERROR */}

        {quotationError && (
          <div className="error-message">
            {quotationError}
          </div>
        )}

        {/* PRICING INTELLIGENCE */}

        {quotation && quotation.pricing && (
          <div className="quotation-section result-animate result-animate-2">
            <div className="quotation-section-header">
              <div className="quotation-section-icon quotation-icon-pricing">
                $
              </div>
              <div>
                <span className="section-label">
                  {isAdmin
                    ? "PRICING INTELLIGENCE"
                    : "QUOTATION PRICING"}
                </span>
                <h2>
                  {isAdmin ? "Cost Breakdown" : "Your Freight Cost"}
                </h2>
                <p>
                  {isAdmin
                    ? "Calculated by the Pricing Agent based on route-specific pricing data"
                    : "Transparent, customer-facing charges for this shipment"}
                </p>
              </div>
            </div>

            <div className="quotation-grid">

              <div className="quotation-row">
                <span className="quotation-label">
                  Base Freight
                </span>
                <span className="quotation-value">
                  ${quotation.pricing.base_freight_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>

              <div className="quotation-row">
                <span className="quotation-label">
                  Fuel Surcharge
                </span>
                <span className="quotation-value quotation-value-secondary">
                  +${quotation.pricing.fuel_surcharge_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>

              <div className="quotation-row">
                <span className="quotation-label">
                  Port Charge
                </span>
                <span className="quotation-value quotation-value-secondary">
                  +${quotation.pricing.port_charge_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>

              <div className="quotation-row">
                <span className="quotation-label">
                  Risk Surcharge
                </span>
                <span className="quotation-value quotation-value-secondary">
                  +${quotation.pricing.risk_surcharge_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>

              <div className="quotation-row quotation-row-divider">
                <span className="quotation-label">
                  Operating Cost
                </span>
                <span className="quotation-value quotation-value-bold">
                  ${quotation.pricing.operating_cost_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>

              <div className="quotation-row">
                <span className="quotation-label">
                  Demand Factor
                </span>
                <span className="quotation-value">
                  {quotation.pricing.demand_factor?.toFixed(2) || "-"}
                </span>
              </div>

              <div className="quotation-row quotation-row-highlight">
                <span className="quotation-label">
                  Demand Adjusted Cost
                </span>
                <span className="quotation-value quotation-value-primary">
                  ${quotation.pricing.demand_adjusted_cost_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>
              {isAdmin && (
                <>
              <div className="quotation-row quotation-row-divider">
                <span className="quotation-label">
                  Operating Cost
                </span>
                <span className="quotation-value quotation-value-bold">
                  ${quotation.pricing.operating_cost_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>

              <div className="quotation-row">
                <span className="quotation-label">
                  Demand Factor
                </span>
                <span className="quotation-value">
                  {quotation.pricing.demand_factor?.toFixed(2) || "-"}
                </span>
              </div>

              <div className="quotation-row quotation-row-highlight">
                <span className="quotation-label">
                  Demand Adjusted Cost
                </span>
                <span className="quotation-value quotation-value-primary">
                  ${quotation.pricing.demand_adjusted_cost_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>
                </>
              )}

            </div>
          </div>
        )}

        {/* FINAL QUOTATION PRICE (CUSTOMER-FACING) */}

        {!isAdmin && quotation && quotation.margin && (
          <div className="quotation-section result-animate result-animate-2 quotation-total-section">
            <div className="quotation-section-header">
              <div className="quotation-section-icon quotation-icon-accept">
                $
              </div>
              <div>
                <span className="section-label">
                  FINAL QUOTATION
                </span>
                <h2>
                  Total Quotation Price
                </h2>
                <p>
                  The final price for this shipment, including
                  all freight, surcharges and port charges.
                </p>
              </div>
            </div>

            <div className="quotation-total-readout">
              <span className="quotation-total-currency">$</span>
              <span className="quotation-total-amount">
                {quotation.margin.recommended_selling_price_usd?.toLocaleString(
                  undefined,
                  { minimumFractionDigits: 2 }
                ) || "-"}
              </span>
            </div>

          </div>
        )}

        {/* MARGIN OPTIMIZATION */}

        {isAdmin && quotation && quotation.margin && (
          <div className="quotation-section result-animate result-animate-2">
            <div className="quotation-section-header">
              <div className="quotation-section-icon quotation-icon-margin">
                %
              </div>
              <div>
                <span className="section-label">
                  MARGIN OPTIMIZATION
                </span>
                <h2>
                  Profitability Analysis
                </h2>
                <p>
                  Calculated by the Margin Agent using
                  target margin requirements
                </p>
              </div>
            </div>

            <div className="quotation-grid">

              <div className="quotation-row">
                <span className="quotation-label">
                  Target Margin
                </span>
                <span className="quotation-value">
                  {quotation.margin.target_margin_percent?.toFixed(1) || "-"}%
                </span>
              </div>

              <div className="quotation-row quotation-row-highlight">
                <span className="quotation-label">
                  Recommended Selling Price
                </span>
                <span className="quotation-value quotation-value-success">
                  ${quotation.margin.recommended_selling_price_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>

              <div className="quotation-row">
                <span className="quotation-label">
                  Expected Profit
                </span>
                <span className="quotation-value quotation-value-profit">
                  ${quotation.margin.expected_profit_usd?.toLocaleString(
                    undefined,
                    { minimumFractionDigits: 2 }
                  ) || "-"}
                </span>
              </div>

              <div className="quotation-row">
                <span className="quotation-label">
                  Achieved Margin
                </span>
                <span className="quotation-value">
                  {quotation.margin.achieved_margin_percent?.toFixed(1) || "-"}%
                </span>
              </div>

            </div>

            {/* FORMULA EXPLANATION */}

            <div className="quotation-formula-note">
              <span className="quotation-formula-icon">
                i
              </span>
              <span>
                Margin = Profit / Selling Price x 100.
                Selling Price = (Cost x 100) / (100 - Margin).
                The Margin Agent ensures the target margin is
                achieved in the final quotation.
              </span>
            </div>

          </div>
        )}

        {/* ALTERNATIVE ROUTES WITH PRICING */}

        {quotation &&
          quotation.alternative_routes &&
          quotation.alternative_routes.length > 0 && (
          <div className="comparison-section result-animate result-animate-2">
            <div className="comparison-heading">
              <div>
                <span className="section-label">
                  ALTERNATIVE ROUTES
                </span>
                <h2>
                  {isAdmin
                    ? "Route Comparison with Pricing"
                    : "Alternative Route Options"}
                </h2>
              </div>
              <span className="route-count">
                {quotation.alternative_routes.length} alternatives
              </span>
            </div>

            <div className="table-wrapper">
              <table className="route-table">
                <thead>
                  <tr>
                    <th>Route</th>
                    <th>Route ID</th>
                    <th>Transit</th>
                    <th>Distance</th>
                    <th>Base Freight</th>
                    {isAdmin && <th>Operating Cost</th>}
                    {isAdmin && <th>Demand Adj. Cost</th>}
                  </tr>
                </thead>
                <tbody>
                  {quotation.alternative_routes.map(
                    (alt, index) => (
                      <tr key={alt.route_id || index}>
                        <td>
                          <div className="route-name-cell">
                            {alt.route_name || "-"}
                          </div>
                        </td>
                        <td>{alt.route_id || "-"}</td>
                        <td>
                          {alt.transit_days != null
                            ? `${alt.transit_days} days`
                            : "-"}
                        </td>
                        <td>
                          {alt.distance_nm != null
                            ? `${alt.distance_nm} nm`
                            : "-"}
                        </td>
                        <td>
                          {alt.base_freight_usd != null
                            ? `$${alt.base_freight_usd.toLocaleString(
                                undefined,
                                { minimumFractionDigits: 2 }
                              )}`
                            : "-"}
                        </td>
                        {isAdmin && (
                          <td>
                            {alt.operating_cost_usd != null
                              ? `$${alt.operating_cost_usd.toLocaleString(
                                  undefined,
                                  { minimumFractionDigits: 2 }
                                )}`
                              : "-"}
                          </td>
                        )}
                        {isAdmin && (
                          <td>
                            {alt.demand_adjusted_cost_usd != null
                              ? `$${alt.demand_adjusted_cost_usd.toLocaleString(
                                  undefined,
                                  { minimumFractionDigits: 2 }
                                )}`
                              : "-"}
                          </td>
                        )}
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
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
  // QUOTATION PAGE
  // ==========================================

  const renderQuotation = () => {
    const hasQuotation = !!(
      quotation && quotation.status === "success"
    );

    const recommended = quotation?.route || null;

    const comparisonRows = [];

    if (recommended) {
      comparisonRows.push(recommended);
    }

    (quotation?.alternative_routes || []).forEach(
      (alt) => comparisonRows.push(alt)
    );

    const fmtMoney = (value, plus) => {
      if (
        value === undefined ||
        value === null ||
        isNaN(Number(value))
      ) {
        return "-";
      }

      const formatted = Number(value).toLocaleString(
        undefined,
        { minimumFractionDigits: 2 }
      );

      return `${plus ? "+$" : "$"}${formatted}`;
    };

    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <span className="section-label">
              QUOTATION
            </span>

            <h1>
              {isAdmin
                ? "Pricing & Margin Quotation"
                : "Your Freight Quotation"}
            </h1>

            <p>
              {isAdmin
                ? "Review the pricing intelligence, margin optimization and route comparison for your generated quotation."
                : "Review the final price and route details for your generated quotation."}
            </p>

          </div>

        </div>

        {!hasQuotation ? (

          /* EMPTY STATE */

          <div className="history-empty quotation-empty">

            <div className="history-empty-icon">
              ❝
            </div>

            <h3>
              No quotation generated yet
            </h3>

            <p>
              Analyze a route and generate a quotation
              to view it here.
            </p>

            <button
              className="primary-button"
              type="button"
              onClick={goToSearch}
            >
              Go to Route Intelligence →
            </button>

          </div>

        ) : (
          <>

            {/* SHIPMENT SUMMARY */}

            <div className="shipment-summary quotation-shipment-summary">

              <div className="summary-item">

                <span>
                  Origin
                </span>

                <strong>
                  {quotation.shipment?.origin || "-"}
                </strong>

              </div>

              <div className="summary-item">

                <span>
                  Destination
                </span>

                <strong>
                  {quotation.shipment?.destination || "-"}
                </strong>

              </div>

              <div className="summary-item">

                <span>
                  Cargo
                </span>

                <strong>
                  {quotation.shipment?.cargo_type || "-"}
                </strong>

              </div>

              <div className="summary-item">

                <span>
                  Subtype
                </span>

                <strong>
                  {quotation.shipment?.cargo_subtype || "-"}
                </strong>

              </div>

              <div className="summary-item">

                <span>
                  Containers
                </span>

                <strong>
                  {quotation.shipment?.containers ?? "-"}
                </strong>

              </div>

            </div>

            {/* ROUTE SUMMARY */}

            <div className="quotation-section result-animate result-animate-2">

              <div className="quotation-section-header">

                <div className="quotation-section-icon quotation-icon-route">
                  ⇢
                </div>

                <div>

                  <span className="section-label">
                    ROUTE SUMMARY
                  </span>

                  <h2>
                    {getRouteName(recommended)}
                  </h2>

                  <p>
                    Recommended route selected for this shipment
                  </p>

                </div>

              </div>

              <div className="route-summary-grid">

                <div className="result-detail">

                  <span>
                    Route ID
                  </span>

                  <strong>
                    {getRouteNumber(recommended)}
                  </strong>

                </div>

                <div className="result-detail">

                  <span>
                    Transit Time
                  </span>

                  <strong>
                    {getTransit(recommended)}
                  </strong>

                </div>

                <div className="result-detail">

                  <span>
                    Distance
                  </span>

                  <strong>
                    {getDistance(recommended)}
                  </strong>

                </div>

                <div className="result-detail">

                  <span>
                    Transshipments
                  </span>

                  <strong>
                    {getTransshipments(recommended)}
                  </strong>

                </div>

                <div className="result-detail">

                  <span>
                    Route Score
                  </span>

                  <strong>
                    {getScore(recommended)}
                  </strong>

                </div>

              </div>

              <div className="route-status status-recommended">
                Recommended Route
              </div>

            </div>

            {/* PRICING INTELLIGENCE */}

            {quotation.pricing && (
              <div className="quotation-section result-animate result-animate-2">

                <div className="quotation-section-header">

                  <div className="quotation-section-icon quotation-icon-pricing">
                    $
                  </div>

                  <div>

                    <span className="section-label">
                      {isAdmin
                        ? "PRICING INTELLIGENCE"
                        : "QUOTATION PRICING"}
                    </span>

                    <h2>
                      {isAdmin ? "Cost Breakdown" : "Your Freight Cost"}
                    </h2>

                    <p>
                      {isAdmin
                        ? "Calculated by the Pricing Agent based on route-specific pricing data"
                        : "Transparent, customer-facing charges for this shipment"}
                    </p>

                  </div>

                </div>

                <div className="quotation-grid">

                  <div className="quotation-row">

                    <span className="quotation-label">
                      Base Freight
                    </span>

                    <span className="quotation-value">
                      {fmtMoney(
                        quotation.pricing.base_freight_usd
                      )}
                    </span>

                  </div>

                  <div className="quotation-row">

                    <span className="quotation-label">
                      Fuel Surcharge
                    </span>

                    <span className="quotation-value quotation-value-secondary">
                      {fmtMoney(
                        quotation.pricing.fuel_surcharge_usd,
                        true
                      )}
                    </span>

                  </div>

                  <div className="quotation-row">

                    <span className="quotation-label">
                      Port Charge
                    </span>

                    <span className="quotation-value quotation-value-secondary">
                      {fmtMoney(
                        quotation.pricing.port_charge_usd,
                        true
                      )}
                    </span>

                  </div>

                  <div className="quotation-row">

                    <span className="quotation-label">
                      Risk Surcharge
                    </span>

                    <span className="quotation-value quotation-value-secondary">
                      {fmtMoney(
                        quotation.pricing.risk_surcharge_usd,
                        true
                      )}
                    </span>

                  </div>

                  {isAdmin && (
                    <>
                  <div className="quotation-row quotation-row-divider">

                    <span className="quotation-label">
                      Operating Cost
                    </span>

                    <span className="quotation-value quotation-value-bold">
                      {fmtMoney(
                        quotation.pricing.operating_cost_usd
                      )}
                    </span>

                  </div>

                  <div className="quotation-row">

                    <span className="quotation-label">
                      Demand Factor
                    </span>

                    <span className="quotation-value">
                      {quotation.pricing.demand_factor != null
                        ? Number(
                            quotation.pricing.demand_factor
                          ).toFixed(2)
                        : "-"}
                    </span>

                  </div>

                  <div className="quotation-row quotation-row-highlight">

                    <span className="quotation-label">
                      Demand Adjusted Cost
                    </span>

                    <span className="quotation-value quotation-value-primary">
                      {fmtMoney(
                        quotation.pricing.demand_adjusted_cost_usd
                      )}
                    </span>

                  </div>
                    </>
                  )}

                </div>

              </div>
            )}

            {/* MARGIN OPTIMIZATION */}

            {isAdmin && quotation.margin && (
              <div className="quotation-section result-animate result-animate-2">

                <div className="quotation-section-header">

                  <div className="quotation-section-icon quotation-icon-margin">
                    %
                  </div>

                  <div>

                    <span className="section-label">
                      MARGIN OPTIMIZATION
                    </span>

                    <h2>
                      Profitability Analysis
                    </h2>

                    <p>
                      Calculated by the Margin Agent using
                      target margin requirements
                    </p>

                  </div>

                </div>

                <div className="quotation-grid">

                  <div className="quotation-row">

                    <span className="quotation-label">
                      Target Margin
                    </span>

                    <span className="quotation-value">
                      {quotation.margin.target_margin_percent != null
                        ? `${Number(
                            quotation.margin.target_margin_percent
                          ).toFixed(1)}%`
                        : "-"}
                    </span>

                  </div>

                  <div className="quotation-row quotation-row-highlight">

                    <span className="quotation-label">
                      Recommended Selling Price
                    </span>

                    <span className="quotation-value quotation-value-success">
                      {fmtMoney(
                        quotation.margin.recommended_selling_price_usd
                      )}
                    </span>

                  </div>

                  <div className="quotation-row">

                    <span className="quotation-label">
                      Expected Profit
                    </span>

                    <span className="quotation-value quotation-value-profit">
                      {fmtMoney(
                        quotation.margin.expected_profit_usd
                      )}
                    </span>

                  </div>

                  <div className="quotation-row">

                    <span className="quotation-label">
                      Achieved Margin
                    </span>

                    <span className="quotation-value">
                      {quotation.margin.achieved_margin_percent != null
                        ? `${Number(
                            quotation.margin.achieved_margin_percent
                          ).toFixed(1)}%`
                        : "-"}
                    </span>

                  </div>

                </div>

                {/* FORMULA EXPLANATION */}

                <div className="quotation-formula-note">

                  <span className="quotation-formula-icon">
                    i
                  </span>

                  <span>
                    Margin = Profit / Selling Price x 100.
                    Selling Price = (Cost x 100) / (100 - Margin).
                    The Margin Agent ensures the target margin is
                    achieved in the final quotation.
                  </span>

                </div>

              </div>
            )}

            {/* FINAL QUOTATION PRICE (CUSTOMER-FACING) */}

            {!isAdmin && quotation.margin && (
              <div className="quotation-section result-animate result-animate-2 quotation-total-section">

                <div className="quotation-section-header">

                  <div className="quotation-section-icon quotation-icon-accept">
                    $
                  </div>

                  <div>

                    <span className="section-label">
                      FINAL QUOTATION
                    </span>

                    <h2>
                      Total Quotation Price
                    </h2>

                    <p>
                      The final price for this shipment, including
                      all freight, surcharges and port charges.
                    </p>

                  </div>

                </div>

                <div className="quotation-total-readout">
                  <span className="quotation-total-currency">$</span>
                  <span className="quotation-total-amount">
                    {fmtMoney(
                      quotation.margin.recommended_selling_price_usd
                    ).replace("$", "")}
                  </span>
                </div>

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
                  {comparisonRows.length} route
                  {comparisonRows.length !== 1
                    ? "s"
                    : ""}
                </span>

              </div>

              {comparisonRows.length > 0 ? (
                <div className="table-wrapper">

                  <table className="route-table quotation-route-table">

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

                      {comparisonRows.map(
                        (route, index) => {

                          const isRecommended =
                            recommended &&
                            getRawRouteNumber(route) ===
                              getRawRouteNumber(
                                recommended
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
                                  {getRouteName(route)}
                                </div>

                              </td>

                              <td>
                                {getRouteNumber(route)}
                              </td>

                              <td>
                                {getTransit(route)}
                              </td>

                              <td>
                                {getDistance(route)}
                              </td>

                              <td>
                                {getTransshipments(route)}
                              </td>

                              <td>

                                <strong>
                                  {getScore(route)}
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

            {/* ACCEPT QUOTATION -> CREATE SHIPMENT */}

            <div className="quotation-section accept-quotation-section result-animate result-animate-2">

              <div className="quotation-section-header">

                <div className="quotation-section-icon quotation-icon-accept">
                  ▤
                </div>

                <div>

                  <span className="section-label">
                    CREATE SHIPMENT
                  </span>

                  <h2>
                    Accept This Quotation
                  </h2>

                  <p>
                    Accepting the quotation creates a shipment
                    with the status "Booking Confirmed". A quotation
                    must be accepted explicitly to create a shipment.
                  </p>

                </div>

              </div>

              {/* ACCEPT ERROR */}

              {acceptError && (
                <div className="error-message accept-error">
                  {acceptError}
                </div>
              )}

              {/* ACCEPT SUCCESS / ALREADY EXISTS */}

              {acceptResult ? (
                <div className="accept-success">

                  <div
                    className={
                      acceptResult.already_exists
                        ? "accept-success-icon accept-success-icon-existing"
                        : "accept-success-icon"
                    }
                  >
                    {acceptResult.already_exists ? "◉" : "✓"}
                  </div>

                  <h3>
                    {acceptResult.already_exists
                      ? "Shipment Already Exists"
                      : "Shipment Created Successfully"}
                  </h3>

                  <div className="accept-success-id">
                    <span>
                      Shipment ID:
                    </span>
                    <strong>
                      {acceptResult.shipment?.shipment_id ||
                        "-"}
                    </strong>
                  </div>

                  <div className="accept-success-status">
                    <span>
                      Status:
                    </span>
                    <strong>
                      {acceptResult.shipment?.status ||
                        "Booking Confirmed"}
                    </strong>
                  </div>

                  <p className="accept-success-message">
                    {acceptResult.message ||
                      (acceptResult.already_exists
                        ? "This quotation was already used to create a shipment."
                        : "Your shipment has been booked successfully.")}
                  </p>

                  <button
                    className="primary-button accept-view-shipments"
                    type="button"
                    onClick={goToShipments}
                  >
                    View My Shipments →
                  </button>

                </div>
              ) : (
                /* ACCEPT ACTION */

                <div className="accept-actions">

                  <button
                    className="accept-quotation-button"
                    type="button"
                    disabled={
                      acceptingQuotation ||
                      !quotation.quotation_id
                    }
                    onClick={handleAcceptQuotation}
                  >
                    {acceptingQuotation
                      ? "Accepting..."
                      : "Accept Quotation"}
                  </button>

                  <span className="accept-meta">
                    Your quotation reference:" "
                    {quotation.quotation_id || "not saved"}
                  </span>

                </div>
              )}

            </div>

            {/* BOTTOM ACTIONS */}

            <div className="results-actions quotation-results-actions">

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
                onClick={goToSearch}
              >
                New Route Search →
              </button>

            </div>

          </>
        )}

      </section>
    );
  };

  // ==========================================
  // HOW TO USE PAGE
  // ==========================================

  const renderHowToUse = () => {
    return (
      <section className="howto-screen page-view">

        <div className="howto-header">

          <div>

            <span className="section-label">
              HELP & SUPPORT
            </span>

            <h1>
              How to Use Maritime AI
            </h1>

            <p>
              Follow these simple steps to analyze routes and
              generate intelligent freight quotations.
            </p>

          </div>

        </div>

        {/* STEP CARDS */}

        <div className="howto-grid">

          {(() => {
            const steps = isAdmin
              ? howToSteps
              : howToSteps
                  .filter(
                    (step) =>
                      step.title !==
                      "Review Pricing & Margin"
                  )
                  .map((step) =>
                    step.title ===
                    "Generate Quotation"
                      ? {
                          ...step,
                          description:
                            "Generate a transparent, competitive quotation with a clear total price for your shipment.",
                        }
                      : step
                  );

            return steps.map((step, index) => (
            <article
              className="howto-card"
              key={step.title}
            >

              <span className="howto-step-number">
                {index + 1}
              </span>

              <div
                className="howto-card-icon"
                aria-hidden="true"
              >
                {step.icon}
              </div>

              <h3>
                {step.title}
              </h3>

              <p>
                {step.description}
              </p>

            </article>
            ));
            })()
          }

        </div>

        {/* QUICK WORKFLOW */}

        <div className="howto-workflow">

          <div className="howto-workflow-heading">

            <div>

              <span className="section-label">
                QUICK WORKFLOW
              </span>

              <h2>
                Your Journey at a Glance
              </h2>

            </div>

          </div>

          <div className="howto-flow">

            {howToWorkflow
              .filter(
                (step) =>
                  isAdmin ||
                  step.label !== "Pricing & Margin"
              )
              .map((step, index) => (
              <React.Fragment key={step.label}>

                {index > 0 && (
                  <div
                    className="howto-flow-arrow"
                    aria-hidden="true"
                  >
                    ↓
                  </div>
                )}

                <div className="howto-flow-step">

                  <span
                    className="howto-flow-icon"
                    aria-hidden="true"
                  >
                    {step.icon}
                  </span>

                  <strong>
                    {step.label}
                  </strong>

                </div>

              </React.Fragment>
            ))}

          </div>

        </div>

      </section>
    );
  };

  // ==========================================
  // ADMIN VIEW HELPERS
  // ==========================================

  const formatAdminDate = (value) => {
    if (!value) return "-";

    if (value instanceof Date) {
      return value.toLocaleString();
    }

    if (typeof value === "string") {
      const date = new Date(value);
      if (isNaN(date.getTime())) return value;
      return date.toLocaleString();
    }

    return String(value);
  };

  const formatMoney = (value) => {
    if (value === undefined || value === null || value === "") {
      return "-";
    }

    const num = Number(value);
    if (isNaN(num)) return "-";

    return `$${num.toLocaleString(undefined, {
      minimumFractionDigits: 2,
    })}`;
  };

  const formatPercent = (value) => {
    if (value === undefined || value === null || value === "") {
      return "-";
    }

    const num = Number(value);
    if (isNaN(num)) return "-";

    return `${num.toFixed(1)}%`;
  };

  const adminRoleBadge = (role) => {
    const normalized =
      role === "admin" ? "admin" : "user";
    return (
      <span
        className={`admin-role-badge ${
          normalized === "admin"
            ? "admin-role-admin"
            : "admin-role-user"
        }`}
      >
        {normalized === "admin"
          ? "Administrator"
          : "User"}
      </span>
    );
  };

  // ==========================================
  // MY SHIPMENTS PAGE
  // Lists only the signed-in user's shipments.
  // ==========================================

  const formatUsd = (value) => {
    const num = Number(value);
    if (isNaN(num)) return "-";
    return num.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const shipmentStatusClass = (status) => {
    const value = String(status || "").toLowerCase();
    if (value.includes("delivered")) return "delivered";
    if (value.includes("transit")) return "transit";
    if (value.includes("destination")) return "destination";
    if (value.includes("departed")) return "departed";
    if (value.includes("origin")) return "origin";
    if (value.includes("ready")) return "ready";
    return "confirmed";
  };

  const renderShipments = () => {
    return (
      <section className="shipments-screen">
        <div className="results-header">
          <div>
            <span className="section-label">
              <span className="section-label-icon">
                ▤
              </span>
              SHIPMENTS
            </span>
            <h1>My Shipments</h1>
            <p>
              Track the status of every quotation you
              accepted. Accepting a quotation is the
              step that creates a shipment.
            </p>
          </div>
        </div>

        {shipmentsLoading ? (
          <div className="loading-message">
            Loading your shipments...
          </div>
        ) : shipmentsError ? (
          <div className="error-message">
            {shipmentsError}
          </div>
        ) : shipments.length === 0 ? (
          <div className="history-empty">
            <span className="history-empty-icon">
              ▤
            </span>
            <h3>No Shipments Yet</h3>
            <p>
              You have not accepted any quotation yet.
              Generate a quotation, then accept it to
              create your first shipment.
            </p>
            <button
              className="primary-button"
              type="button"
              onClick={handleNavClick.bind(null, "Quotation")}
            >
              Generate a Quotation →
            </button>
          </div>
        ) : (
          <div className="shipments-grid">
            {shipments.map((shipment) => (
              <article
                className="shipment-card"
                key={shipment.shipment_id}
              >
                <div className="shipment-card-header">
                  <div>
                    <span className="shipment-id">
                      {shipment.shipment_id}
                    </span>
                    <span
                      className={`shipment-status ${
                        shipmentStatusClass(shipment.status)
                      }`}
                    >
                      {shipment.status || "Booking Confirmed"}
                    </span>
                  </div>
                  <span className="shipment-date">
                    {formatAnalysisDate(shipment.created_at)}
                  </span>
                </div>

                <div className="shipment-route">
                  <div className="shipment-route-points">
                    <strong>{shipment.origin}</strong>
                    <span className="shipment-route-arrow">
                      →
                    </span>
                    <strong>{shipment.destination}</strong>
                  </div>
                  <span className="shipment-route-name">
                    {shipment.route_name || "Route"}
                  </span>
                </div>

                <div className="shipment-card-meta">
                  <div className="shipment-meta-item">
                    <span className="shipment-meta-label">
                      Cargo
                    </span>
                    <span className="shipment-meta-value">
                      {shipment.cargo_type || "-"}
                      {shipment.cargo_subtype
                        ? ` / ${shipment.cargo_subtype}`
                        : ""}
                    </span>
                  </div>
                  <div className="shipment-meta-item">
                    <span className="shipment-meta-label">
                      Containers
                    </span>
                    <span className="shipment-meta-value">
                      {shipment.containers ?? "-"}
                    </span>
                  </div>
                  <div className="shipment-meta-item">
                    <span className="shipment-meta-label">
                      Transit
                    </span>
                    <span className="shipment-meta-value">
                      {shipment.transit_days ?? "-"} days
                    </span>
                  </div>
                  <div className="shipment-meta-item">
                    <span className="shipment-meta-label">
                      Transshipments
                    </span>
                    <span className="shipment-meta-value">
                      {shipment.transshipments ?? "-"}
                    </span>
                  </div>
                </div>

                <button
                  className="secondary-button shipment-view-details"
                  type="button"
                  onClick={() =>
                    openShipmentDetails(shipment.shipment_id)
                  }
                >
                  View Details →
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    );
  };

  // ==========================================
  // SHIPMENT DETAILS PAGE
  // Shows full shipment info plus a status
  // timeline (platform workflow simulation).
  // ==========================================

  const renderShipmentDetails = () => {
    const shipment = shipmentDetails;

    return (
      <section className="shipment-details-screen">
        <div className="shipment-details-topbar">
          <button
            className="back-button"
            type="button"
            onClick={goToShipments}
          >
            ← My Shipments
          </button>
        </div>

        {shipmentDetailsLoading ? (
          <div className="loading-message">
            Loading shipment details...
          </div>
        ) : shipmentDetailsError ? (
          <div className="error-message">
            {shipmentDetailsError}
          </div>
        ) : !shipment ? (
          <div className="history-empty">
            <span className="history-empty-icon">
              ▤
            </span>
            <h3>Shipment Not Found</h3>
            <p>
              The shipment you are looking for is not
              available.
            </p>
          </div>
        ) : (
          <div className="shipment-details">
            <div className="shipment-details-header">
              <div>
                <span className="section-label">
                  SHIPMENT DETAILS
                </span>
                <h1>{shipment.shipment_id}</h1>
              </div>
              <span
                className={`shipment-status shipment-status-large ${
                  shipmentStatusClass(shipment.status)
                }`}
              >
                {shipment.status || "Booking Confirmed"}
              </span>
            </div>

            <div className="shipment-details-section">
              <span className="section-label">
                ROUTE & CARGO
              </span>
              <div className="shipment-details-grid">
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Origin
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.origin}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Destination
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.destination}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Route
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.route_name || "-"}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Cargo
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.cargo_type || "-"}
                    {shipment.cargo_subtype
                      ? ` / ${shipment.cargo_subtype}`
                      : ""}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Containers
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.containers ?? "-"}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Transit Days
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.transit_days ?? "-"}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Distance
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.distance_nm
                      ? `${shipment.distance_nm} nm`
                      : "-"}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Transshipments
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.transshipments ?? "-"}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Quotation Ref
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.quotation_id || "-"}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Created
                  </span>
                  <span className="shipment-meta-value">
                    {formatAnalysisDate(shipment.created_at)}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    Contact
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.user_contact || "-"}
                  </span>
                </div>
                <div className="shipment-details-item">
                  <span className="shipment-meta-label">
                    User
                  </span>
                  <span className="shipment-meta-value">
                    {shipment.user_name || "-"}
                  </span>
                </div>
              </div>
            </div>

            {shipment.pricing && (
              <div className="shipment-details-section">
                <span className="section-label">
                  PRICING SUMMARY
                </span>
                <div className="shipment-details-grid">
                  <div className="shipment-details-item">
                    <span className="shipment-meta-label">
                      Base Freight
                    </span>
                    <span className="shipment-meta-value">
                      ${formatUsd(shipment.pricing.base_freight_usd)}
                    </span>
                  </div>
                  {isAdmin && (
                    <>
                  <div className="shipment-details-item">
                    <span className="shipment-meta-label">
                      Operating Cost
                    </span>
                    <span className="shipment-meta-value">
                      ${formatUsd(shipment.pricing.operating_cost_usd)}
                    </span>
                  </div>
                  <div className="shipment-details-item">
                    <span className="shipment-meta-label">
                      Demand Factor
                    </span>
                    <span className="shipment-meta-value">
                      {Number(
                        shipment.pricing.demand_factor
                      ).toFixed(2) || "-"}
                    </span>
                  </div>
                  <div className="shipment-details-item">
                    <span className="shipment-meta-label">
                      Demand Adjusted Cost
                    </span>
                    <span className="shipment-meta-value">
                      ${formatUsd(
                        shipment.pricing.demand_adjusted_cost_usd
                      )}
                    </span>
                  </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {isAdmin && shipment.margin && (
              <div className="shipment-details-section">
                <span className="section-label">
                  MARGIN SUMMARY
                </span>
                <div className="shipment-details-grid">
                  <div className="shipment-details-item">
                    <span className="shipment-meta-label">
                      Target Margin
                    </span>
                    <span className="shipment-meta-value">
                      {Number(
                        shipment.margin.target_margin_percent
                      ).toFixed(1)}%
                    </span>
                  </div>
                  <div className="shipment-details-item">
                    <span className="shipment-meta-label">
                      Recommended Price
                    </span>
                    <span className="shipment-meta-value">
                      ${formatUsd(
                        shipment.margin.recommended_selling_price_usd
                      )}
                    </span>
                  </div>
                  <div className="shipment-details-item">
                    <span className="shipment-meta-label">
                      Expected Profit
                    </span>
                    <span className="shipment-meta-value">
                      ${formatUsd(
                        shipment.margin.expected_profit_usd
                      )}
                    </span>
                  </div>
                </div>
              </div>
            )}

            <div className="shipment-details-section">
              <span className="section-label">
                PROGRESS TIMELINE
              </span>
              <p className="shipment-timeline-note">
                Workflow simulation — a status advances along
                the booking-to-delivery journey. No live GPS
                or vessel tracking is claimed.
              </p>

              <div className="shipment-timeline">
                {shipmentStatusFlow.map((stage) => {
                  const stageIndex =
                    shipmentStatusFlow.indexOf(stage);
                  const currentIndex =
                    shipmentStatusFlow.indexOf(shipment.status);

                  const reached =
                    currentIndex >= 0 &&
                    stageIndex <= currentIndex;

                  return (
                    <div
                      className={`shipment-timeline-step ${
                        reached
                          ? "reached"
                          : "pending"
                      } ${
                        stageIndex === currentIndex
                          ? "current"
                          : ""
                      }`}
                      key={stage}
                    >
                      <span className="shipment-timeline-dot" />
                      <span className="shipment-timeline-label">
                        {stage}
                      </span>
                      {stageIndex === currentIndex && (
                        <span className="shipment-timeline-current">
                          Current
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </section>
    );
  };

  // ==========================================
  // ADMIN DASHBOARD
  // ==========================================

  const renderAdminDashboard = () => {
    const cards = [
      {
        icon: "▦",
        label: "Total Users",
        value: adminStats?.total_users ?? 0,
        note: "Registered accounts",
      },
      {
        icon: "⇢",
        label: "Route Analyses",
        value: adminStats?.total_route_analyses ?? 0,
        note: "Saved route history entries",
      },
      {
        icon: "❝",
        label: "Quotations",
        value: adminStats?.total_quotations ?? 0,
        note: "Generated quotations",
      },
      {
        icon: "▤",
        label: "Total Shipments",
        value: adminStats?.total_shipments ?? 0,
        note: "All created shipments",
      },
      {
        icon: "◈",
        label: "Active Shipments",
        value: adminStats?.active_shipments ?? 0,
        note: "Awaiting delivery",
      },
      {
        icon: "✓",
        label: "Delivered",
        value: adminStats?.delivered_shipments ?? 0,
        note: "Completed shipments",
      },
    ];

    const statusCounts = {};

    if (adminShipments && adminShipments.length > 0) {
      adminShipments.forEach((s) => {
        const key = s.status || "Unknown";
        statusCounts[key] = (statusCounts[key] || 0) + 1;
      });
    }

    const recentActivity = adminActivity.slice(0, 5);

    return (
      <section className="home-screen admin-dashboard page-view">

        <div className="welcome-block admin-welcome">

          <div className="welcome-text">

            <span className="welcome-label">
              MARITIME AI
            </span>

            <h1>
              Admin Dashboard
            </h1>

            <p>
              Administrative overview of platform users,
              shipments and quotations.
            </p>

            <div className="administrator-badge">
              <span className="administrator-dot"></span>
              Administrator
            </div>

          </div>

        </div>

        {/* STATS CARDS */}

        {adminStatsLoading && (
          <div className="loading-message">
            <span className="loading-spinner"></span>
            Loading admin statistics...
          </div>
        )}

        {adminStatsError && (
          <div className="error-message">
            {adminStatsError}
          </div>
        )}

        {!adminStatsLoading &&
          !adminStatsError &&
          adminStats && (
            <div className="admin-stats-grid">

              {cards.map((card) => (
                <div
                  className="admin-stat-card"
                  key={card.label}
                >

                  <div className="admin-stat-icon">
                    {card.icon}
                  </div>

                  <div className="admin-stat-info">

                    <span className="admin-stat-label">
                      {card.label}
                    </span>

                    <strong className="admin-stat-value">
                      {card.value.toLocaleString()}
                    </strong>

                    <span className="admin-stat-note">
                      {card.note}
                    </span>

                  </div>

                </div>
              ))}

            </div>
          )}

        {/* SHIPMENT STATUS OVERVIEW */}

        {!adminStatsLoading &&
          !adminStatsError &&
          adminStats &&
          adminShipments.length > 0 && (
            <div className="comparison-section admin-section-card">

              <div className="admin-section-header">
                <span className="section-label">
                  SHIPMENT STATUS OVERVIEW
                </span>
                <button
                  className="secondary-button admin-section-link"
                  type="button"
                  onClick={() =>
                    handleNavClick("Shipments")
                  }
                >
                  Manage Shipments →
                </button>
              </div>

              <div className="admin-status-grid">

                {shipmentStatusFlow.map((status) => {
                  const count =
                    statusCounts[status] || 0;
                  return (
                    <div
                      className="admin-status-chip"
                      key={status}
                    >
                      <span className="admin-status-chip-label">
                        {status}
                      </span>
                      <strong className="admin-status-chip-value">
                        {count}
                      </strong>
                    </div>
                  );
                })}

              </div>

            </div>
          )}

        {/* RECENT ACTIVITY */}

        {!adminStatsLoading &&
          !adminStatsError &&
          adminStats &&
          recentActivity.length > 0 && (
            <div className="comparison-section admin-section-card">

              <div className="admin-section-header">
                <span className="section-label">
                  RECENT ROUTE ACTIVITY
                </span>
                <button
                  className="secondary-button admin-section-link"
                  type="button"
                  onClick={() =>
                    handleNavClick("Route Activity")
                  }
                >
                  View All →
                </button>
              </div>

              <div className="table-wrapper">

                <table className="route-table admin-table">

                  <thead>

                    <tr>

                      <th>User</th>
                      <th>Origin</th>
                      <th>Destination</th>
                      <th>Cargo</th>
                      <th>Route</th>
                      <th>Date</th>

                    </tr>

                  </thead>

                  <tbody>

                    {recentActivity.map((item) => (
                      <tr
                        key={item.record_id}
                        className="history-row"
                      >

                        <td>
                          {item.user_contact ||
                            "Unknown"}
                        </td>

                        <td>
                          {item.origin || "-"}
                        </td>

                        <td>
                          {item.destination || "-"}
                        </td>

                        <td>
                          {item.cargo_type || "-"}
                          {item.cargo_subtype
                            ? ` / ${item.cargo_subtype}`
                            : ""}
                        </td>

                        <td>
                          <div className="history-route-cell">
                            <strong className="history-route-id">
                              {item.route_id || "-"}
                            </strong>
                            <span className="history-route-name">
                              {item.route_name || "-"}
                            </span>
                          </div>
                        </td>

                        <td>
                          <span className="history-date">
                            {formatAdminDate(
                              item.created_at
                            )}
                          </span>
                        </td>

                      </tr>
                    ))}

                  </tbody>

                </table>

              </div>

            </div>
          )}

        {/* ADMIN QUICK ACTIONS */}

        <div className="info-cards admin-quick-actions">

          <div
            className="info-card admin-action-card"
            onClick={() =>
              handleNavClick("Users")
            }
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" ||
                e.key === " "
              ) {
                handleNavClick("Users");
              }
            }}
          >

            <div className="info-card-icon">
              ▽
            </div>

            <div>

              <h3>
                Manage Users
              </h3>

              <p>
                View all registered users and their
                account status.
              </p>

            </div>

          </div>

          <div
            className="info-card admin-action-card"
            onClick={() =>
              handleNavClick("Shipments")
            }
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" ||
                e.key === " "
              ) {
                handleNavClick("Shipments");
              }
            }}
          >

            <div className="info-card-icon">
              ▤
            </div>

            <div>

              <h3>
                Shipments
              </h3>

              <p>
                Manage shipment workflow statuses.
              </p>

            </div>

          </div>

          <div
            className="info-card admin-action-card"
            onClick={() =>
              handleNavClick("Quotations")
            }
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" ||
                e.key === " "
              ) {
                handleNavClick("Quotations");
              }
            }}
          >

            <div className="info-card-icon">
              ❝
            </div>

            <div>

              <h3>
                Quotations
              </h3>

              <p>
                View generated pricing & margin
                quotations.
              </p>

            </div>

          </div>

          <div
            className="info-card admin-action-card"
            onClick={() =>
              handleNavClick("Pricing & Margin")
            }
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" ||
                e.key === " "
              ) {
                handleNavClick("Pricing & Margin");
              }
            }}
          >

            <div className="info-card-icon">
              %
            </div>

            <div>

              <h3>
                Pricing & Margin
              </h3>

              <p>
                Monitor pricing and margin agent data.
              </p>

            </div>

          </div>

          <div
            className="info-card admin-action-card"
            onClick={() =>
              handleNavClick("Route Activity")
            }
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" ||
                e.key === " "
              ) {
                handleNavClick("Route Activity");
              }
            }}
          >

            <div className="info-card-icon">
              ◈
            </div>

            <div>

              <h3>
                Route Activity
              </h3>

              <p>
                Review recent route analyses across all
                users.
              </p>

            </div>

          </div>

        </div>

      </section>
    );
  };

  // ==========================================
  // ADMIN USERS
  // ==========================================

  const renderAdminUsers = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={() =>
                handleNavClick("Admin Dashboard")
              }
            >
              ← Back to Admin Dashboard
            </button>

            <span className="section-label">
              ADMIN
            </span>

            <h1>
              Registered Users
            </h1>

            <p>
              View registered platform users. Passwords
              are never displayed.
            </p>

          </div>

        </div>

        {/* SEARCH */}

        <div className="admin-users-toolbar">

          <div className="admin-search-box">

            <span className="admin-search-icon">
              ⌕
            </span>

            <input
              type="text"
              value={adminUserSearch}
              onChange={(e) =>
                handleAdminUserSearch(
                  e.target.value
                )
              }
              placeholder="Search by name or contact..."
            />

          </div>

          <span className="admin-users-count">
            {adminUsers.length} user
            {adminUsers.length !== 1 ? "s" : ""}
          </span>

        </div>

        {/* ERROR */}

        {adminUsersError && (
          <div className="error-message">
            {adminUsersError}
          </div>
        )}

        {/* LOADING */}

        {adminUsersLoading && (
          <div className="loading-message">
            <span className="loading-spinner"></span>
            Loading users...
          </div>
        )}

        {/* EMPTY */}

        {!adminUsersLoading &&
          !adminUsersError &&
          adminUsers.length === 0 && (
            <div className="history-empty">

              <div className="history-empty-icon">
                ▽
              </div>

              <h3>
                No users found.
              </h3>

              <p>
                No registered users match your search.
              </p>

            </div>
          )}

        {/* USERS TABLE */}

        {!adminUsersLoading &&
          !adminUsersError &&
          adminUsers.length > 0 && (
            <div className="comparison-section">

              <div className="table-wrapper">

                <table className="route-table admin-table">

                  <thead>

                    <tr>

                      <th>Name</th>
                      <th>Contact</th>
                      <th>Role</th>
                      <th>Created</th>
                      <th>Status</th>

                    </tr>

                  </thead>

                  <tbody>

                    {adminUsers.map((item) => (
                      <tr key={item.id}>

                        <td>
                          <div className="admin-user-cell">
                            <span className="admin-user-avatar">
                              {getProfileInitials(
                                item.name ||
                                  item.contact
                              )}
                            </span>
                            <strong>
                              {item.name || "-"}
                            </strong>
                          </div>
                        </td>

                        <td>
                          {item.contact || "-"}
                        </td>

                        <td>
                          {adminRoleBadge(item.role)}
                        </td>

                        <td>
                          <span className="history-date">
                            {formatAdminDate(
                              item.created_at
                            )}
                          </span>
                        </td>

                        <td>
                          <span
                            className={
                              item.verified
                                ? "admin-verified"
                                : "admin-unverified"
                            }
                          >
                            {item.verified
                              ? "Verified"
                              : "Unverified"}
                          </span>
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
  // ADMIN ROUTE ACTIVITY
  // ==========================================

  const renderAdminActivity = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={() =>
                handleNavClick("Admin Dashboard")
              }
            >
              ← Back to Admin Dashboard
            </button>

            <span className="section-label">
              ADMIN
            </span>

            <h1>
              Route Activity
            </h1>

            <p>
              Route analyses performed across all users.
            </p>

          </div>

        </div>

        {/* ERROR */}

        {adminActivityError && (
          <div className="error-message">
            {adminActivityError}
          </div>
        )}

        {/* LOADING */}

        {adminActivityLoading && (
          <div className="loading-message">
            <span className="loading-spinner"></span>
            Loading route activity...
          </div>
        )}

        {/* EMPTY */}

        {!adminActivityLoading &&
          !adminActivityError &&
          adminActivity.length === 0 && (
            <div className="history-empty">

              <div className="history-empty-icon">
                ◈
              </div>

              <h3>
                No route activity yet.
              </h3>

              <p>
                Route analyses will appear here as
                users use the platform.
              </p>

            </div>
          )}

        {/* ACTIVITY TABLE */}

        {!adminActivityLoading &&
          !adminActivityError &&
          adminActivity.length > 0 && (
            <div className="comparison-section">

              <div className="table-wrapper">

                <table className="route-table admin-table">

                  <thead>

                    <tr>

                      <th>User</th>
                      <th>Origin</th>
                      <th>Destination</th>
                      <th>Cargo</th>
                      <th>Route</th>
                      <th>Transit</th>
                      <th>Distance</th>
                      <th>Tranships</th>
                      <th>Score</th>
                      <th>Date</th>

                    </tr>

                  </thead>

                  <tbody>

                    {adminActivity.map((item) => (
                      <tr
                        key={item.record_id}
                        className="history-row"
                      >

                        <td>
                          {item.user_contact ||
                            "Unknown user"}
                        </td>

                        <td>
                          {item.origin || "-"}
                        </td>

                        <td>
                          {item.destination || "-"}
                        </td>

                        <td>
                          {item.cargo_type || "-"}
                          {item.cargo_subtype
                            ? ` / ${item.cargo_subtype}`
                            : ""}
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
                            ? `${item.transit_days}d`
                            : "-"}
                        </td>

                        <td>
                          {item.distance_nm != null
                            ? `${Number(item.distance_nm).toLocaleString()} nm`
                            : "-"}
                        </td>

                        <td>
                          {item.transshipments ?? "-"}
                        </td>

                        <td>
                          {item.route_score != null
                            ? Number(item.route_score).toFixed(2)
                            : "-"}
                        </td>

                        <td>

                          <span className="history-date">
                            {formatAdminDate(
                              item.created_at
                            )}
                          </span>

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
  // ADMIN QUOTATIONS
  // ==========================================

  const renderAdminQuotations = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={() =>
                handleNavClick("Admin Dashboard")
              }
            >
              ← Back to Admin Dashboard
            </button>

            <span className="section-label">
              ADMIN
            </span>

            <h1>
              Quotations
            </h1>

            <p>
              Pricing and margin quotations generated
              across the platform.
            </p>

          </div>

        </div>

        {/* ERROR */}

        {adminQuotationsError && (
          <div className="error-message">
            {adminQuotationsError}
          </div>
        )}

        {/* LOADING */}

        {adminQuotationsLoading && (
          <div className="loading-message">
            <span className="loading-spinner"></span>
            Loading quotations...
          </div>
        )}

        {/* EMPTY */}

        {!adminQuotationsLoading &&
          !adminQuotationsError &&
          adminQuotations.length === 0 && (
            <div className="history-empty">

              <div className="history-empty-icon">
                ❝
              </div>

              <h3>
                No quotations yet.
              </h3>

              <p>
                Generated quotations will appear here
                as users generate them.
              </p>

            </div>
          )}

        {/* QUOTATIONS TABLE */}

        {!adminQuotationsLoading &&
          !adminQuotationsError &&
          adminQuotations.length > 0 && (
            <div className="comparison-section">

              <div className="table-wrapper">

                <table className="route-table admin-table">

                  <thead>

                    <tr>

                      <th>User</th>
                      <th>Origin</th>
                      <th>Destination</th>
                      <th>Cargo</th>
                      <th>Containers</th>
                      <th>Route</th>
                      <th>Base Freight</th>
                      <th>Operating Cost</th>
                      <th>Cost</th>
                      <th>Selling Price</th>
                      <th>Profit</th>
                      <th>Margin</th>
                      <th>Date</th>

                    </tr>

                  </thead>

                  <tbody>

                    {adminQuotations.map((item) => (
                      <tr
                        key={item.record_id}
                        className="history-row"
                      >

                        <td>
                          {item.user_contact ||
                            "Unknown user"}
                        </td>

                        <td>
                          {item.origin || "-"}
                        </td>

                        <td>
                          {item.destination || "-"}
                        </td>

                        <td>
                          {item.cargo_type || "-"}
                          {item.cargo_subtype
                            ? ` / ${item.cargo_subtype}`
                            : ""}
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
                          {formatMoney(
                            item.pricing?.base_freight_usd
                          )}
                        </td>

                        <td>
                          {formatMoney(
                            item.pricing?.operating_cost_usd
                          )}
                        </td>

                        <td>
                          {formatMoney(
                            item.pricing?.demand_adjusted_cost_usd
                          )}
                        </td>

                        <td>
                          {formatMoney(
                            item.margin
                              ?.recommended_selling_price_usd
                          )}
                        </td>

                        <td>
                          {formatMoney(
                            item.margin
                              ?.expected_profit_usd
                          )}
                        </td>

                        <td>
                          {formatPercent(
                            item.margin
                              ?.target_margin_percent
                          )}
                        </td>

                        <td>

                          <span className="history-date">
                            {formatAdminDate(
                              item.created_at
                            )}
                          </span>

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
  // ADMIN SHIPMENTS
  // ==========================================

  const renderAdminShipments = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={() =>
                handleNavClick("Admin Dashboard")
              }
            >
              ← Back to Admin Dashboard
            </button>

            <span className="section-label">
              ADMIN
            </span>

            <h1>
              Shipments
            </h1>

            <p>
              Manage shipment workflow statuses.
              Only forward status transitions are
              permitted.
            </p>

          </div>

        </div>

        {/* STATUS FILTER */}

        <div className="admin-users-toolbar">

          <div className="admin-search-box">

            <select
              value={adminShipmentFilter}
              onChange={(e) =>
                handleAdminShipmentFilter(
                  e.target.value
                )
              }
              className="admin-filter-select"
            >
              <option value="">
                All Statuses
              </option>
              {(adminShipmentStatuses.length
                ? adminShipmentStatuses
                : shipmentStatusFlow
              ).map((s) => (
                <option value={s} key={s}>
                  {s}
                </option>
              ))}
            </select>

          </div>

          <span className="admin-users-count">
            {adminShipments.length} shipment
            {adminShipments.length !== 1
              ? "s"
              : ""}
          </span>

        </div>

        {/* SUCCESS MESSAGE */}

        {adminShipmentMessage && (
          <div className="admin-shipment-success">
            {adminShipmentMessage}
          </div>
        )}

        {/* ERROR MESSAGE */}

        {adminShipmentMessageError && (
          <div className="error-message">
            {adminShipmentMessageError}
          </div>
        )}

        {adminShipmentsError && (
          <div className="error-message">
            {adminShipmentsError}
          </div>
        )}

        {/* LOADING */}

        {adminShipmentsLoading && (
          <div className="loading-message">
            <span className="loading-spinner"></span>
            Loading shipments...
          </div>
        )}

        {/* EMPTY */}

        {!adminShipmentsLoading &&
          !adminShipmentsError &&
          !adminShipmentMessageError &&
          adminShipments.length === 0 && (
            <div className="history-empty">

              <div className="history-empty-icon">
                ▤
              </div>

              <h3>
                No shipments found.
              </h3>

              <p>
                Shipments are created when users
                accept a quotation.
              </p>

            </div>
          )}

        {/* SHIPMENTS TABLE */}

        {!adminShipmentsLoading &&
          !adminShipmentsError &&
          adminShipments.length > 0 && (
            <div className="comparison-section">

              <div className="table-wrapper">

                <table className="route-table admin-table">

                  <thead>

                    <tr>

                      <th>Shipment ID</th>
                      <th>User</th>
                      <th>Origin</th>
                      <th>Destination</th>
                      <th>Cargo</th>
                      <th>Containers</th>
                      <th>Route</th>
                      <th>Status</th>
                      <th>Created</th>

                    </tr>

                  </thead>

                  <tbody>

                    {adminShipments.map((item) => (
                      <tr
                        key={item.shipment_id}
                        className={
                          updatingShipmentId ===
                          item.shipment_id
                            ? "updating-row"
                            : ""
                        }
                      >

                        <td>
                          <strong>
                            {item.shipment_id}
                          </strong>
                        </td>

                        <td>
                          {item.user_contact ||
                            item.user_name ||
                            "-"}
                        </td>

                        <td>
                          {item.origin || "-"}
                        </td>

                        <td>
                          {item.destination || "-"}
                        </td>

                        <td>
                          {item.cargo_type || "-"}
                          {item.cargo_subtype
                            ? ` / ${item.cargo_subtype}`
                            : ""}
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
                              {item.route_name || "-"}
                            </span>
                          </div>
                        </td>

                        <td>
                          <select
                            className="admin-status-select"
                            value={item.status || ""}
                            disabled={
                              updatingShipmentId ===
                              item.shipment_id
                            }
                            onChange={(e) =>
                              handleAdminShipmentStatusChange(
                                item,
                                e.target.value
                              )
                            }
                          >
                            {(
                              adminShipmentStatuses.length
                                ? adminShipmentStatuses
                                : shipmentStatusFlow
                            ).map((s) => (
                              <option value={s} key={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                        </td>

                        <td>
                          <span className="history-date">
                            {formatAdminDate(
                              item.created_at
                            )}
                          </span>
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
  // ADMIN PRICING & MARGIN
  // ==========================================

  const renderAdminPricing = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={() =>
                handleNavClick("Admin Dashboard")
              }
            >
              ← Back to Admin Dashboard
            </button>

            <span className="section-label">
              ADMIN
            </span>

            <h1>
              Pricing & Margin
            </h1>

            <p>
              Pricing Agent and Margin Agent data
              for platform monitoring. Pricing is
              generated automatically when quotations
              are created.
            </p>

          </div>

        </div>

        {/* ERROR */}

        {adminPricingError && (
          <div className="error-message">
            {adminPricingError}
          </div>
        )}

        {/* LOADING */}

        {adminPricingLoading && (
          <div className="loading-message">
            <span className="loading-spinner"></span>
            Loading pricing & margin data...
          </div>
        )}

        {/* EMPTY */}

        {!adminPricingLoading &&
          !adminPricingError &&
          adminPricing.length === 0 && (
            <div className="history-empty">

              <div className="history-empty-icon">
                %
              </div>

              <h3>
                No pricing data available.
              </h3>

              <p>
                Pricing data will appear here once
                routes and pricing data are
                populated.
              </p>

            </div>
          )}

        {/* PRICING TABLE */}

        {!adminPricingLoading &&
          !adminPricingError &&
          adminPricing.length > 0 && (
            <div className="comparison-section">

              <div className="table-wrapper">

                <table className="route-table admin-table">

                  <thead>

                    <tr>

                      <th>Route</th>
                      <th>Base Freight</th>
                      <th>Fuel Surcharge</th>
                      <th>Port Charge</th>
                      <th>Risk Surcharge</th>
                      <th>Demand Factor</th>
                      <th>Target Margin</th>

                    </tr>

                  </thead>

                  <tbody>

                    {adminPricing.map((item) => (
                      <tr
                        key={item.pricing_id}
                        className="history-row"
                      >

                        <td>
                          <div className="history-route-cell">
                            <strong className="history-route-id">
                              {item.route_id || "-"}
                            </strong>
                            <span className="history-route-name">
                              {item.route_name ||
                                `${item.origin || ""} → ${item.destination || ""}`}
                            </span>
                          </div>
                        </td>

                        <td>
                          {formatMoney(
                            item.base_freight_usd
                          )}
                        </td>

                        <td>
                          {formatMoney(
                            item.fuel_surcharge_usd
                          )}
                        </td>

                        <td>
                          {formatMoney(
                            item.port_charge_usd
                          )}
                        </td>

                        <td>
                          {formatMoney(
                            item.risk_surcharge_usd
                          )}
                        </td>

                        <td>
                          {Number(
                            item.demand_factor
                          ).toFixed(2) || "-"}
                        </td>

                        <td>
                          {formatPercent(
                            item.target_margin_percent
                          )}
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
  // USER FEEDBACK PAGE
  // ==========================================

  const renderFeedback = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={goHome}
            >
              ← Back to Dashboard
            </button>

            <span className="section-label">
              FEEDBACK
            </span>

            <h1>
              Share Your Feedback
            </h1>

            <p>
              Your feedback helps us improve the
              Maritime AI platform.
            </p>

          </div>

        </div>

        {/* FEEDBACK FORM CARD */}

        <div className="feedback-form-card">

          {feedbackSuccess && (
            <div className="admin-shipment-success feedback-success">
              {feedbackSuccess}
            </div>
          )}

          {feedbackError && (
            <div className="error-message">
              {feedbackError}
            </div>
          )}

          <form onSubmit={handleSubmitFeedback}>

            {/* RATING */}

            <div className="feedback-field">
              <label>
                Your Rating
              </label>

              <div className="star-rating">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    className={
                      star <= feedbackRating
                        ? "star-button star-filled"
                        : "star-button"
                    }
                    onClick={() =>
                      setFeedbackRating(star)
                    }
                    aria-label={`Rate ${star} out of 5`}
                  >
                    ★
                  </button>
                ))}
                <span className="star-label">
                  {starLabel(feedbackRating)}
                </span>
              </div>
            </div>

            {/* FEEDBACK TYPE */}

            <div className="feedback-field">
              <label>
                Feedback Type
              </label>
              <select
                value={feedbackType}
                onChange={(e) =>
                  setFeedbackType(e.target.value)
                }
              >
                <option value="">
                  Select feedback type
                </option>
                <option value="Service">
                  Service
                </option>
                <option value="Quotation">
                  Quotation
                </option>
                <option value="Route">
                  Route
                </option>
                <option value="Shipment">
                  Shipment
                </option>
                <option value="Other">
                  Other
                </option>
              </select>
            </div>

            {/* MESSAGE */}

            <div className="feedback-field">
              <label>
                Your Message
              </label>
              <textarea
                value={feedbackMessage}
                onChange={(e) =>
                  setFeedbackMessage(e.target.value)
                }
                placeholder="Tell us about your experience..."
                rows="5"
              ></textarea>
            </div>

            <div className="form-actions">

              <button
                type="submit"
                className="primary-button"
                disabled={feedbackSubmitting}
              >
                {feedbackSubmitting
                  ? "Submitting..."
                  : "Submit Feedback"}
              </button>

            </div>

          </form>

        </div>

        {/* MY FEEDBACK HISTORY */}

        <div className="my-feedback-section">

          <div className="comparison-heading">

            <div>

              <span className="section-label">
                MY FEEDBACK
              </span>

              <h2>
                Your Previous Feedback
              </h2>

            </div>

            <button
              className="secondary-button"
              type="button"
              onClick={loadMyFeedback}
            >
              Refresh
            </button>

          </div>

          {myFeedbackError && (
            <div className="error-message">
              {myFeedbackError}
            </div>
          )}

          {myFeedbackLoading && (
            <div className="loading-message">
              <span className="loading-spinner"></span>
              Loading your feedback...
            </div>
          )}

          {!myFeedbackLoading &&
            !myFeedbackError &&
            myFeedback.length === 0 && (
              <div className="history-empty">
                <div className="history-empty-icon">
                  ◈
                </div>
                <h3>
                  No feedback submitted yet.
                </h3>
                <p>
                  Your submitted feedback will appear
                  here.
                </p>
              </div>
            )}

          {!myFeedbackLoading &&
            !myFeedbackError &&
            myFeedback.length > 0 && (
              <div className="feedback-grid">
                {myFeedback.map((item) => (
                  <div
                    className="feedback-record"
                    key={item.feedback_id}
                  >
                    <div className="feedback-record-head">
                      <span className="feedback-type-badge">
                        {item.feedback_type || "Feedback"}
                      </span>
                      <span className="feedback-stars">
                        {"★".repeat(item.rating || 0)}
                        <i>
                          {"★".repeat(
                            Math.max(
                              0,
                              5 - (item.rating || 0)
                            )
                          )}
                        </i>
                      </span>
                    </div>
                    <p className="feedback-message">
                      {item.message}
                    </p>
                    <div className="feedback-record-date">
                      Submitted: {formatFullDate(item.created_at)}
                    </div>
                  </div>
                ))}
              </div>
            )}

        </div>

      </section>
    );
  };

  // ==========================================
  // ADMIN USER FEEDBACK PAGE
  // ==========================================

  const renderAdminFeedback = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={() =>
                handleNavClick("Admin Dashboard")
              }
            >
              ← Back to Admin Dashboard
            </button>

            <span className="section-label">
              ADMIN
            </span>

            <h1>
              User Feedback
            </h1>

            <p>
              Feedback submitted by users across the
              platform.
            </p>

          </div>

        </div>

        {/* TOOLBAR */}

        <div className="admin-users-toolbar">

          <div className="admin-search-box">
            <span className="admin-users-count">
              {adminFeedback.length} feedback
              {adminFeedback.length !== 1 ? "s" : ""}
            </span>
          </div>

          <button
            className="secondary-button"
            type="button"
            onClick={loadAdminFeedback}
          >
            Refresh
          </button>

        </div>

        {/* ERROR */}

        {adminFeedbackError && (
          <div className="error-message">
            {adminFeedbackError}
          </div>
        )}

        {/* LOADING */}

        {adminFeedbackLoading && (
          <div className="loading-message">
            <span className="loading-spinner"></span>
            Loading feedback...
          </div>
        )}

        {/* EMPTY */}

        {!adminFeedbackLoading &&
          !adminFeedbackError &&
          adminFeedback.length === 0 && (
            <div className="history-empty">
              <div className="history-empty-icon">
                ◈
              </div>
              <h3>
                No feedback yet.
              </h3>
              <p>
                User feedback will appear here as it
                is submitted.
              </p>
            </div>
          )}

        {/* FEEDBACK LIST */}

        {!adminFeedbackLoading &&
          !adminFeedbackError &&
          adminFeedback.length > 0 && (
            <div className="feedback-grid">
              {adminFeedback.map((item) => (
                <div
                  className="feedback-record"
                  key={item.feedback_id}
                >
                  <div className="feedback-record-head">
                    <div className="feedback-user-info">
                      <strong>
                        {item.user_name || "User"}
                      </strong>
                      {item.user_contact && (
                        <span>
                          {item.user_contact}
                        </span>
                      )}
                    </div>
                    <span className="feedback-type-badge">
                      {item.feedback_type || "Feedback"}
                    </span>
                  </div>

                  <div className="feedback-stars-row">
                    <span className="feedback-stars">
                      {"★".repeat(item.rating || 0)}
                      <i>
                        {"★".repeat(
                          Math.max(
                            0,
                            5 - (item.rating || 0)
                          )
                        )}
                      </i>
                    </span>
                    <span className="feedback-rating-text">
                      {item.rating}/5
                    </span>
                  </div>

                  <p className="feedback-message">
                    "{item.message}"
                  </p>

                  <div className="feedback-record-date">
                    Submitted: {formatFullDate(item.created_at)}
                  </div>
                </div>
              ))}
            </div>
          )}

      </section>
    );
  };

  // ==========================================
  // ADMIN INVITATIONS PAGE
  // ==========================================

  const renderAdminInvitations = () => {
    return (
      <section className="results-screen page-view">

        <div className="results-header">

          <div>

            <button
              className="back-button"
              type="button"
              onClick={() => handleNavClick("Admin Dashboard")}
            >
              {"←"} Back to Admin Dashboard
            </button>

            <span className="section-label">
              ADMIN
            </span>

            <h1>
              Admin Invitations
            </h1>

            <p>
              Invite new administrators. Each invitation expires
              in 24 hours and can be used only once.
            </p>

          </div>

        </div>

        {/* INVITE FORM CARD */}

        <div className="feedback-form-card invitation-form-card">

          <div className="invitation-form-heading">

            <span className="section-label">
              NEW INVITATION
            </span>

            <h2>
              Generate an invitation
            </h2>

            <p>
              Enter the contact email of the person you want
              to invite as an administrator.
            </p>

          </div>

          {inviteError && (
            <div className="error-message">
              {inviteError}
            </div>
          )}

          <form onSubmit={handleGenerateInvitation}>

            <div className="feedback-field">
              <label>
                Contact / Email
              </label>
              <input
                type="text"
                value={inviteContact}
                onChange={(e) => setInviteContact(e.target.value)}
                placeholder="e.g. newadmin@example.com"
                required
              />
            </div>

            <div className="form-actions">
              <button
                className="primary-button"
                type="submit"
                disabled={inviteGenerating}
              >
                {inviteGenerating
                  ? "Generating..."
                  : "Generate Invitation"}
              </button>
            </div>

          </form>

        </div>

        {/* INVITE RESULT - SUCCESS CARD */}

        {inviteResult && (
          <div className="invitation-result invitation-result-success">

            <div className="invitation-result-head">

              <span className="invitation-result-icon">
                {"✓"}
              </span>

              <div>
                <h3>
                  Admin Invitation Generated
                </h3>
                <p>
                  Copy and share the link below with the new
                  admin. The invitation expires in 24 hours.
                </p>
              </div>

            </div>

            <div className="invitation-meta-grid">

              <div className="invitation-meta">
                <span>
                  INVITED CONTACT
                </span>
                <strong>
                  {inviteResult.contact || "-"}
                </strong>
              </div>

              <div className="invitation-meta">
                <span>
                  EXPIRES
                </span>
                <strong>
                  {inviteResult.expires_at
                    ? formatFullDate(inviteResult.expires_at)
                    : "In 24 hours"}
                </strong>
              </div>

            </div>

            <div className="invitation-token-box">

              <span className="invitation-token-label">
                INVITATION LINK
              </span>

              <div className="invitation-token-readout">
                <code>
                  {invitationLink}
                </code>
              </div>

            </div>

            <button
              className="primary-button invitation-copy-button"
              type="button"
              onClick={copyInviteLink}
            >
              {copiedInvite
                ? "Copied ✓"
                : "Copy Invitation Link"}
            </button>

          </div>
        )}

        {/* INVITATION HISTORY */}

        <div className="comparison-section">

          <div className="comparison-heading">

            <div>

              <span className="section-label">
                GENERATED INVITATIONS
              </span>

              <h2>
                Invitation History
              </h2>

            </div>

            <button
              className="secondary-button"
              type="button"
              onClick={loadAdminInvitations}
            >
              Refresh
            </button>

          </div>

          {adminInvitationsError && (
            <div className="error-message">
              {adminInvitationsError}
            </div>
          )}

          {adminInvitationsLoading && (
            <div className="loading-message">
              <span className="loading-spinner"></span>
              Loading invitations...
            </div>
          )}

          {!adminInvitationsLoading &&
            !adminInvitationsError &&
            adminInvitations.length === 0 && (
              <div className="history-empty">
                <div className="history-empty-icon">
                  {"⇪"}
                </div>
                <h3>
                  No invitations generated yet.
                </h3>
                <p>
                  Generated invitations will appear here.
                </p>
              </div>
            )}

          {!adminInvitationsLoading &&
            !adminInvitationsError &&
            adminInvitations.length > 0 && (
              <div className="table-wrapper">

                <table className="route-table admin-table">

                  <thead>

                    <tr>
                      <th>Contact</th>
                      <th>Created By</th>
                      <th>Status</th>
                      <th>Used</th>
                      <th>Created At</th>
                      <th>Expires At</th>
                    </tr>

                  </thead>

                  <tbody>

                    {adminInvitations.map((item) => {

                      const isUsed = item.used === true;

                      const isExpired =
                        !isUsed &&
                        item.expires_at &&
                        new Date(item.expires_at) < new Date();

                      return (
                        <tr key={item.invitation_id}>

                          <td>
                            <strong>
                              {item.contact || "-"}
                            </strong>
                          </td>

                          <td>
                            {item.created_by || "-"}
                          </td>

                          <td>
                            <span
                              className={`invitation-status-badge ${
                                isUsed
                                  ? "invitation-badge-used"
                                  : isExpired
                                  ? "invitation-badge-expired"
                                  : "invitation-badge-active"
                              }`}
                            >
                              {isUsed
                                ? "Used"
                                : isExpired
                                ? "Expired"
                                : "Active"}
                            </span>
                          </td>

                          <td>
                            {isUsed ? "Yes" : "No"}
                          </td>

                          <td>
                            <span className="history-date">
                              {formatFullDate(item.created_at)}
                            </span>
                          </td>

                          <td>
                            <span className="history-date">
                              {formatFullDate(item.expires_at)}
                            </span>
                          </td>

                        </tr>
                      );
                    })}

                  </tbody>

                </table>

              </div>
            )}

        </div>

      </section>
    );
  };
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
              {isAdmin
                ? "Admin Dashboard"
                : "Freight Intelligence"}
            </span>

          </div>

        </div>

        <nav className="sidebar-nav">

          {isAdmin ? (
            /* ----------------------------------------
               ADMIN NAVIGATION
               ---------------------------------------- */

            <>
              <button
                className={
                  activeNav === "Admin Dashboard"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Admin Dashboard")
                }
              >

                <span className="nav-icon">
                  ▦
                </span>

                Admin Dashboard

              </button>

              <button
                className={
                  activeNav === "Users"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Users")
                }
              >

                <span className="nav-icon">
                  ▽
                </span>

                Users

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
                  activeNav === "Quotations"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Quotations")
                }
              >

                <span className="nav-icon">
                  ❝
                </span>

                Quotations

              </button>

              <button
                className={
                  activeNav === "Pricing & Margin"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Pricing & Margin")
                }
              >

                <span className="nav-icon">
                  %
                </span>

                Pricing & Margin

              </button>

              <button
                className={
                  activeNav === "Route Activity"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Route Activity")
                }
              >

                <span className="nav-icon">
                  ◈
                </span>

                Route Activity

              </button>

              <button
                className={
                  activeNav === "User Feedback"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("User Feedback")
                }
              >

                <span className="nav-icon">
                  ❝
                </span>

                User Feedback

              </button>

              <button
                className={
                  activeNav === "Admin Invitations"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Admin Invitations")
                }
              >

                <span className="nav-icon">
                  ⇪
                </span>

                Admin Invitations

              </button>
            </>
          ) : (
            /* ----------------------------------------
               USER NAVIGATION
               ---------------------------------------- */

            <>
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

              <button
                className={
                  activeNav === "My Shipments"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("My Shipments")
                }
              >

                <span className="nav-icon">
                  ▤
                </span>

                Shipments

              </button>

              <button
                className={
                  activeNav === "Feedback"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Feedback")
                }
              >

                <span className="nav-icon">
                  ◈
                </span>

                Feedback

              </button>

              <button
                className={
                  activeNav === "How to Use"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("How to Use")
                }
              >

                <span className="nav-icon">
                  ⓘ
                </span>

                How to Use

              </button>
            </>
          )}

        </nav>

        <div className="sidebar-bottom">

          {isAdmin && (
            <div className="sidebar-admin-label">
              <span className="administrator-dot"></span>
              Administrator
            </div>
          )}

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
                  {profileRoleSubLabel}
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
                      {profileRoleSubLabel}
                    </span>

                  </div>

                </div>

                <div className="profile-menu-rows">

                  <div className="profile-menu-row">

                    <span>
                      Role
                    </span>

                    <strong>
                      {profileRoleLabel}
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

          {/* Keying this wrapper by "view" forces a fresh mount
              on every navigation, so the subtle page transition
              and in-page entrance animations re-run each time. */}

          <div className="view-transition" key={view}>

          {view === "home" &&
            renderHome()}

          {view === "search" &&
            renderSearch()}

          {view === "results" &&
            renderResults()}

          {view === "history" &&
            renderHistory()}

          {view === "quotation" &&
            renderQuotation()}

          {view === "shipments" &&
            renderShipments()}

          {view === "shipment-details" &&
            renderShipmentDetails()}

          {view === "howto" &&
            renderHowToUse()}

          {view === "feedback" &&
            renderFeedback()}

          {isAdmin && view === "admin-home" &&
            renderAdminDashboard()}

          {isAdmin && view === "admin-users" &&
            renderAdminUsers()}

          {isAdmin && view === "admin-shipments" &&
            renderAdminShipments()}

          {isAdmin && view === "admin-pricing" &&
            renderAdminPricing()}

          {isAdmin && view === "admin-activity" &&
            renderAdminActivity()}

          {isAdmin && view === "admin-quotations" &&
            renderAdminQuotations()}

          {isAdmin && view === "admin-feedback" &&
            renderAdminFeedback()}

          {isAdmin && view === "admin-invitations" &&
            renderAdminInvitations()}

          </div>

                </div>

      </main>

    </div>
  );

}

export default App;
