import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import MaritimeRouteMap from "./components/MaritimeRouteMap.jsx";
import MapErrorBoundary from "./components/MapErrorBoundary.jsx";
import { alternativeColorFor } from "./utils/maritimeGeometry";

// ==========================================
// ONE UNIFIED "HOW TO USE" WORKFLOW
// Consolidates the former step cards and the
// logic diagram into a single end-to-end flow
// covering user actions AND the internal AI
// agents (Route, Pricing, Margin) inline.
// ==========================================

const howToFlow = [
  {
    icon: "◉",
    title: "Login to Maritime AI",
    description:
      "Login using your registered email or mobile number and password to access the dashboard.",
    system: "",
  },
  {
    icon: "⇢",
    title: "Enter Shipment Requirements",
    description:
      "In Route Intelligence, choose the origin port, destination port, cargo type, cargo subtype and the number of containers.",
    system: "",
  },
  {
    icon: "⌖",
    title: "Analyze Route",
    description:
      "The Route Agent evaluates every available route on the corridor and returns the recommended route with transit time, distance and transshipments.",
    system: "Route Agent",
  },
  {
    icon: "▣",
    title: "Review the Recommended Route",
    description:
      "Inspect the recommended route on the Maritime Route Map and compare the alternatives, then select the option that fits your schedule.",
    system: "",
  },
  {
    icon: "$",
    title: "Generate Quotation",
    description:
      "The Pricing Agent computes the operating and demand-adjusted cost, while the Margin Agent sets the selling price, expected profit and achieved margin.",
    system: "Pricing Agent · Margin Agent",
  },
  {
    icon: "%",
    title: "Accept Quotation & Submit for Approval",
    description:
      "Accept the quotation to submit it for admin approval. Once an admin approves it, a shipment record is created automatically and appears in My Shipments.",
    system: "",
  },
  {
    icon: "◇",
    title: "Track Shipment Status",
    description:
      "The shipment advances through the controlled status flow — from Booking Confirmed to Delivered. This is a workflow simulation, not live vessel tracking.",
    system: "",
  },
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

// ==========================================
// QUOTATION APPROVAL STATUS LABELS
// Maps the backend approval_status value to
// the customer-facing labels. Internal fields
// (margin targets, expected profit, pricing
// formulas) are never exposed here.
// ==========================================

const approvalStatusClass = (status) => {
  if (status === "rejected") return "approval-status-rejected";
  if (status === "approved") return "approval-status-approved";
  return "approval-status-pending";
};

const approvalStatusLabel = (status) => {
  if (status === "approved") return "Approved by Admin";
  if (status === "rejected") return "Rejected by Admin";
  return "Pending Admin Approval";
};

function ApprovalStatusBadge({ item }) {
  const status = item?.approval_status || "";

  if (!status) return null;

  const rejectionReason = item?.rejection_reason || "";

  return (
    <div className="approval-status-cell">
      <span
        className={`approval-status-pill ${approvalStatusClass(
          status
        )}`}
      >
        {approvalStatusLabel(status)}
      </span>
      {status === "rejected" && rejectionReason && (
        <span className="approval-status-reason">
          Reason: {rejectionReason}
        </span>
      )}
    </div>
  );
}

// ==========================================
// DATE/TIME FORMATTER (IST)
// ==========================================
// Formats any backend timestamp (stored in UTC)
// into Indian Standard Time for display.
//
//   formatDateTime("2026-09-18T12:00:00Z")
//   -> "18 Sep 2026, 05:30 PM"
//
// The conversion is done ONLY at display time via
// the Intl timeZone "Asia/Kolkata". No manual
// +5:30 offset is ever applied, and no IST value
// is stored anywhere.
// ==========================================

const formatDateTime = (timestamp) => {
  if (timestamp == null || timestamp === "") return "-";

  const date =
    timestamp instanceof Date
      ? timestamp
      : typeof timestamp === "string"
      ? new Date(timestamp)
      : new Date(Number(timestamp));

  if (isNaN(date.getTime())) return String(timestamp);

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).formatToParts(date);

  const value = {};
  parts.forEach((part) => {
    if (part.type !== "literal") value[part.type] = part.value;
  });

  if (!value.day || !value.month || !value.year) {
    return String(timestamp);
  }

  return `${value.day} ${value.month} ${value.year}, ${value.hour}:${value.minute} ${value.dayPeriod}`;
};

// ==========================================
// ROUTE HISTORY STATUS
// ==========================================
// Human-readable status for a Route History
// record, derived ONLY from data the backend
// already stores (quotation presence + the
// existing approval_status field). No new
// workflow is introduced.
//
// Priority: Rejected -> Approved -> Pending
// Admin Approval -> Quotation Pending
// Acceptance -> "-".
// ==========================================

const routeHistoryStatus = (item) => {
  const approval = item?.approval_status || "";

  if (approval === "rejected") return "rejected";
  if (approval === "approved") return "approved";
  if (approval === "pending_admin_approval") {
    return "pending_admin_approval";
  }
  if (item && (item.pricing || item.margin)) {
    return "quotation_pending_acceptance";
  }
  return null;
};

const routeHistoryStatusLabel = (status) => {
  if (status === "rejected") return "Rejected";
  if (status === "approved") return "Approved";
  if (status === "pending_admin_approval") {
    return "Pending Admin Approval";
  }
  if (status === "quotation_pending_acceptance") {
    return "Quotation Pending Acceptance";
  }
  return "-";
};

const routeHistoryStatusClass = (status) => {
  if (status === "rejected") return "approval-status-rejected";
  if (status === "approved") return "approval-status-approved";
  return "approval-status-pending";
};

function RouteHistoryStatus({ item }) {
  const status = routeHistoryStatus(item);

  if (!status) {
    return <span className="approval-no-action">-</span>;
  }

  return (
    <div className="approval-status-cell">
      <span
        className={`approval-status-pill ${routeHistoryStatusClass(
          status
        )}`}
      >
        {routeHistoryStatusLabel(status)}
      </span>
      {status === "rejected" && item?.rejection_reason && (
        <span className="approval-status-reason">
          Reason: {item.rejection_reason}
        </span>
      )}
    </div>
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

  // Full-screen Maritime Map state. The fixed network is loaded
  // from the backend once; `mapBackTarget` decides where the map
  // back button returns (route results or the admin dashboard).
  const [mapRetryKey, setMapRetryKey] = useState(0);
  const [mapBackTarget, setMapBackTarget] = useState("results");
  const [selectedRouteId, setSelectedRouteId] = useState("");
  const [mapExpanded, setMapExpanded] = useState(false);
  const [selectedShipmentId, setSelectedShipmentId] =
    useState("");

  // Complete fixed maritime network loaded once from the
  // backend (GET /api/routes/network, built from routes.csv).
  // The map renders this base network and highlights the
  // recommended route on top of it; a new search only changes
  // the highlight, never this set of ports and edges.
  const [networkPorts, setNetworkPorts] = useState({});
  const [networkEdges, setNetworkEdges] = useState([]);
  const [networkLoading, setNetworkLoading] = useState(false);
  const [networkError, setNetworkError] = useState("");

  // Real AIS vessels (GET /api/vessels -> AISHub through the
  // FastAPI backend). The provider API key never reaches the
  // browser. Data is refreshed on a fixed interval, never on
  // every render, and the backend caches provider responses.
  const [vesselsData, setVesselsData] = useState(null);
  const [vesselsLoading, setVesselsLoading] = useState(false);

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
  const [quotationSuccess, setQuotationSuccess] =
    useState("");

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
  const [adminQuotationActionId, setAdminQuotationActionId] =
    useState(null);
  const [adminQuotationActionError, setAdminQuotationActionError] =
    useState("");
  const [adminQuotationActionMessage, setAdminQuotationActionMessage] =
    useState("");
  const [rejectQuotation, setRejectQuotation] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectingQuotation, setRejectingQuotation] =
    useState(false);
  const [rejectError, setRejectError] = useState("");
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
          "/api/routes/locations"
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
          "/api/routes/cargo-subtypes"
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

  const goToResultMap = () => {
    setView("result-map");
    setActiveNav("Maritime Route Map");
    setError("");
    setMapBackTarget("results");
  };

  const goBackToResults = () => {
    setView("results");
    setActiveNav("Routes");
    setError("");
  };

  const goBackToAdminDashboard = () => {
    setView("admin-home");
    setActiveNav("Admin Dashboard");
    setError("");
    loadAdminStats();
  };

  // ==========================================
  // COMPLETE MARITIME NETWORK
  // Loads the full fixed network (every unique port and every
  // port-to-port connection from routes.csv) from the backend
  // exactly once, the first time the map view is opened. It is
  // kept in state afterwards so every later route search reuses
  // the same complete network and only changes the highlight.
  // ==========================================

  useEffect(() => {
    if (view !== "result-map") return;
    if (Object.keys(networkPorts).length > 0) return;

    let cancelled = false;

    const loadRouteNetwork = async () => {
      setNetworkLoading(true);
      setNetworkError("");

      try {
        const response = await fetch("/api/routes/network");

        if (!response.ok) {
          throw new Error("Unable to load the maritime network.");
        }

        const data = await response.json();

        if (cancelled) return;

        setNetworkPorts(data?.ports || {});
        setNetworkEdges(data?.edges || []);
      } catch (err) {
        if (cancelled) return;
        console.error("Route network loading error:", err);
        setNetworkError(
          err.message ||
            "Unable to load the maritime network."
        );
      } finally {
        if (!cancelled) setNetworkLoading(false);
      }
    };

    loadRouteNetwork();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, mapRetryKey]);

  // ==========================================
  // SHIPMENT CONTEXT ON MAP
  // When the Maritime Route Map opens, the logged-in user's
  // own shipments are loaded (never fabricated) so the map can
  // visually associate a shipment with its route and status.
  // The list is reused from My Shipments; nothing hard-coded.
  // ==========================================

  const shipmentsFetchedRef = useRef(false);

  useEffect(() => {
    if (view !== "result-map") return;
    if (shipmentsFetchedRef.current) return;

    shipmentsFetchedRef.current = true;
    loadShipments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

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
        `/api/routes/history?${params}`,
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
        `/api/routes/history/${recordId}?${params}`,
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
        `/api/routes/history?${params}`,
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
        `/api/routes/cargo-subtypes?${params}`
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
    setQuotation(null);
    setQuotationError("");
    setQuotationSuccess("");
    setAcceptError("");
    setAcceptResult(null);

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
        "/api/routes/analyze",
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
  // ANALYZE ON MARITIME MAP
  // Same Route Agent call as handleAnalyze, but stays on
  // the Maritime Route Map view so the result is drawn
  // directly on the map with the route panel below it.
  // ==========================================

  const handleMapAnalyze = async (e) => {
    e.preventDefault();

    setError("");
    setResult(null);
    setQuotation(null);
    setQuotationError("");
    setQuotationSuccess("");
    setAcceptError("");
    setAcceptResult(null);
    setSelectedRouteId("");
    setSelectedShipmentId("");

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
      if (cargoType && routeCargoSubtypes.length === 0) {
        setError("No cargo subtypes available for this route.");
      } else {
        setError("Please select a cargo subtype.");
      }
      return;
    }

    if (!containers || Number(containers) < 1) {
      setError("Number of containers must be at least 1.");
      return;
    }

    try {
      setLoading(true);

      const response = await fetch("/api/routes/analyze", {
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
      });

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

      const rec =
        data?.recommended_route ||
        data?.recommended ||
        data?.best_route ||
        (Array.isArray(data?.route_options) &&
        data.route_options.length > 0
          ? data.route_options[0]
          : null);

      const recId = rec
        ? String(
            getValue(rec, ["route_id", "routeId"], "")
          ).trim()
        : "";

      setSelectedRouteId(recId);
    } catch (err) {
      console.error("Route map analysis error:", err);

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
    setQuotationSuccess("");
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
        "/api/quotations/generate",
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
      setQuotationSuccess(
        "Quotation generated successfully."
      );
      setActiveNav("Quotation");
      setView("quotation");
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
        `/api/shipments?${params}`,
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
  // LIVE AIS VESSELS
  // Fetches real vessel positions (GET /api/vessels) from the
  // FastAPI backend, which talks to the AIS provider (AISHub)
  // with the API key that only exists server-side. The map
  // keeps working regardless of the response: a provider that
  // is not configured, or temporarily down, yields a friendly
  // non-blocking status instead of an error. Nothing here is
  // ever fabricated; when the provider has no data we simply
  // say so.
  // ==========================================

  const loadVessels = useCallback(async (silent = false) => {
    if (!silent) {
      setVesselsLoading(true);
    }

    try {
      const response = await fetch("/api/vessels", {
        headers: { ...getAuthHeaders() },
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        setVesselsData({
          status: "unavailable",
          vessels: [],
          message:
            data?.detail ||
            "Live vessel data temporarily unavailable.",
          updatedAt: new Date().toISOString(),
          source: "AIS",
        });
        return;
      }

      setVesselsData({
        status:
          data?.status === "ok"
            ? "ok"
            : data?.status || "unavailable",
        vessels:
          Array.isArray(data?.vessels) ? data.vessels : [],
        message:
          typeof data?.message === "string"
            ? data.message
            : "",
        updatedAt:
          typeof data?.updated_at === "string"
            ? data.updated_at
            : "",
        source:
          typeof data?.source === "string" ? data.source : "AIS",
      });
    } catch (err) {
      console.error("Vessels loading error:", err);
      setVesselsData({
        status: "unavailable",
        vessels: [],
        message:
          "Live vessel data temporarily unavailable.",
        updatedAt: new Date().toISOString(),
        source: "AIS",
      });
    } finally {
      if (!silent) {
        setVesselsLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshVessels = useCallback(() => {
    loadVessels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load AIS data once when the Maritime Route Map opens, then
  // keep it fresh on a fixed interval. The backend caches the
  // provider response so the browser refresh rate is harmless.
  const vesselsFetchedRef = useRef(false);

  useEffect(() => {
    if (view !== "result-map") return;
    if (vesselsFetchedRef.current) {
      refreshVessels();
      return;
    }

    vesselsFetchedRef.current = true;
    loadVessels();

    const timer = window.setInterval(() => {
      refreshVessels();
    }, 300000);

    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, mapRetryKey]);

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
        `/api/shipments/${encodeURIComponent(
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
        `/api/quotations/${encodeURIComponent(
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
        "/api/admin/stats"
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
        `/api/admin/users${query ? `?${query}` : ""}`
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
        "/api/admin/route-activity"
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
        "/api/admin/quotations"
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
  // ADMIN APPROVE / REJECT QUOTATION
  // ==========================================

  const handleApproveQuotation = (item) => {
    const confirmed = window.confirm(
      "Approve this quotation? Approving creates the customer's shipment."
    );

    if (!confirmed) return;

    setAdminQuotationActionId(item.record_id);
    setAdminQuotationActionError("");
    setAdminQuotationActionMessage("");

    adminFetch(
      `/api/admin/quotations/${encodeURIComponent(
        item.record_id
      )}/approve`,
      { method: "POST" }
    )
      .then(async (response) => {
        const data = await response
          .json()
          .catch(() => ({}));

        if (!response.ok) {
          throw new Error(
            data?.detail ||
              "Unable to approve this quotation."
          );
        }

        setAdminQuotationActionMessage(
          data?.message ||
            (data?.already_approved
              ? "This quotation was already approved."
              : "Quotation approved.")
        );
        loadAdminQuotations();
      })
      .catch((err) => {
        console.error(
          "Admin quotation approval error:",
          err
        );
        setAdminQuotationActionError(
          err.message ||
            "Unable to approve this quotation."
        );
      })
      .finally(() => {
        setAdminQuotationActionId(null);
      });
  };

  const openRejectQuotationModal = (item) => {
    setRejectQuotation(item);
    setRejectReason("");
    setRejectError("");
  };

  const closeRejectQuotationModal = () => {
    if (rejectingQuotation) return;
    setRejectQuotation(null);
    setRejectReason("");
    setRejectError("");
  };

  const handleRejectQuotation = async () => {
    const reason = rejectReason.trim();

    if (!reason) {
      setRejectError(
        "Please provide a reason for rejecting this quotation."
      );
      return;
    }

    if (!rejectQuotation) return;

    setRejectingQuotation(true);
    setRejectError("");

    try {
      const response = await adminFetch(
        `/api/admin/quotations/${encodeURIComponent(
          rejectQuotation.record_id
        )}/reject`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ reason }),
        }
      );

      const data = await response
        .json()
        .catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to reject this quotation."
        );
      }

      setRejectQuotation(null);
      setRejectReason("");
      setAdminQuotationActionMessage(
        data?.message ||
          "Quotation rejected."
      );
      loadAdminQuotations();
    } catch (err) {
      console.error(
        "Admin quotation rejection error:",
        err
      );
      setRejectError(
        err.message ||
          "Unable to reject this quotation."
      );
    } finally {
      setRejectingQuotation(false);
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
        `/api/admin/shipments${query ? `?${query}` : ""}`
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
        `/api/admin/shipments/${encodeURIComponent(
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
        "/api/admin/pricing"
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
        "/api/feedback",
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
        "/api/feedback",
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
        "/api/admin/feedback"
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
        "/api/admin/invitations"
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
        "/api/admin/invitations",
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

  const buildInviteLink = (token) => {
    if (!token) return "";

    const host = window.location.hostname;
    const isLoopback =
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "::1";

    const origin =
      isLoopback && inviteResult?.frontend_origin
        ? inviteResult.frontend_origin
        : window.location.origin;

    return `${origin}/accept-invitation.html?token=${encodeURIComponent(
      token
    )}`;
  };

  const copyInviteLink = () => {
    const token = inviteResult?.token;

    if (!token) return;

    const link = buildInviteLink(token);

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
    const routeOrigin = getValue(route, ["origin"], "");
    const routeDestination = getValue(route, ["destination"], "");

    const raw = getValue(
      route,
      ["route", "route_name", "name", "routeName"],
      ""
    );

    const parseText = (value) => {
      const parts = String(value || "")
        .split("|")[0]
        .split("→")
        .map((part) => part.trim())
        .filter(Boolean);

      if (parts.length >= 2) {
        return {
          origin: parts[0].toLowerCase(),
          destination: parts[parts.length - 1].toLowerCase(),
          display:
            parts.length >= 3
              ? `${parts[0]} → ${parts[parts.length - 1]} via ${parts
                  .slice(1, -1)
                  .join(" → ")}`
              : `${parts[0]} → ${parts[parts.length - 1]}`,
        };
      }
      return null;
    };

    const parsed = parseText(raw);
    const lowerOrigin = String(routeOrigin).toLowerCase();
    const lowerDestination = String(routeDestination).toLowerCase();

    if (
      lowerOrigin &&
      lowerDestination &&
      parsed &&
      parsed.origin === lowerOrigin &&
      parsed.destination === lowerDestination
    ) {
      return parsed.display;
    }

    if (lowerOrigin && lowerDestination) {
      return `${routeOrigin} → ${routeDestination}`;
    }

    if (parsed) return parsed.display;

    return String(raw).trim() || "Route";
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

    if (item === "Maritime Route Map") {
      setView("result-map");
      setActiveNav("Maritime Route Map");
      setError("");
      setMapBackTarget(isAdmin ? "admin" : "results");
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

        {/* GO TO MAPS */}

        {recommendedRoute && (
          <div className="go-to-maps-section result-animate result-animate-2">
            <button
              className="go-to-maps-button"
              type="button"
              onClick={goToResultMap}
            >
              <div className="go-to-maps-icon">
                🗺️
              </div>
              <div className="go-to-maps-text">
                <strong>
                  GO TO MAPS
                </strong>
                <span>
                  View this recommended route for {origin} → {destination} on the interactive map
                </span>
              </div>
              <div className="go-to-maps-arrow">
                →
              </div>
            </button>
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

        {quotation && (
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
                {(quotation.alternative_routes || []).length}{" "}
                alternatives
              </span>
            </div>

            {quotation.alternative_routes &&
            quotation.alternative_routes.length > 0 ? (
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
            ) : (
              <div className="no-routes">
                No alternative routes available for this
                selection.
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

          {allRoutes.length === 1 && (
            <div className="no-routes single-route-note">
              Only one available route found for this
              selection.
            </div>
          )}

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
  // FULL-SCREEN MARITIME MAP
  // ==========================================
  // A SEPARATE full-screen map view opened ONLY when the user
  // clicks GO TO MAPS (or an admin opens it from the admin
  // interface). It shows the COMPLETE fixed maritime network
  // from routes.csv. The map page contains NO route summary,
  // NO recommended-route card, NO Route Agent reasoning and NO
  // shipment details - those belong to the Route Intelligence
  // page and are intentionally not repeated here.
  // ==========================================

  const renderResultMap = () => {
    const recRoute = recommendedRoute;
    const routes = allRoutes.length > 0 ? allRoutes : [];

    const recommendedRouteId = recRoute
      ? String(
          getValue(recRoute, ["route_id", "routeId"], "")
        ).trim()
      : "";

    // Cargo subtype dependent state (same rules as the
    // Route Intelligence search form).
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

    const totalPorts = Object.keys(networkPorts).length;
    const totalConnections = networkEdges.length;

    // Active shipment context (only real backend shipments).
    const activeShipment = selectedShipmentId
      ? shipments.find(
          (item) => item.shipment_id === selectedShipmentId
        ) || null
      : null;

    // Zoom target. A selected shipment focuses its own route;
    // otherwise the analyzed route (origin -> destination); when
    // nothing is active the map fits all dataset ports.
    const fitPoints = [];
    if (activeShipment) {
      const so = activeShipment.origin
        ? networkPorts[activeShipment.origin]
        : null;
      const sd = activeShipment.destination
        ? networkPorts[activeShipment.destination]
        : null;
      if (so) {
        fitPoints.push([
          Number(so.latitude),
          Number(so.longitude),
        ]);
      }
      if (sd) {
        fitPoints.push([
          Number(sd.latitude),
          Number(sd.longitude),
        ]);
      }
    }
    if (
      fitPoints.length < 2 &&
      origin &&
      networkPorts[origin]
    ) {
      fitPoints.push([
        Number(networkPorts[origin].latitude),
        Number(networkPorts[origin].longitude),
      ]);
    }
    if (
      fitPoints.length < 2 &&
      destination &&
      networkPorts[destination]
    ) {
      fitPoints.push([
        Number(networkPorts[destination].latitude),
        Number(networkPorts[destination].longitude),
      ]);
    }
    const mapFitPoints = fitPoints.length === 2 ? fitPoints : null;
    const mapFitKey = `${origin}->${destination}->${selectedRouteId}->${selectedShipmentId}`;

    const mapTitle =
      activeShipment
        ? `${activeShipment.origin} → ${activeShipment.destination}`
        : origin && destination
          ? `${origin} → ${destination}`
          : "Complete Maritime Network";

    const backLabel =
      mapBackTarget === "admin"
        ? "← Back to Admin Dashboard"
        : "← Back to Route Intelligence";

    const handleBack = () => {
      if (mapBackTarget === "admin") {
        goBackToAdminDashboard();
        return;
      }
      if (!result) {
        goToSearch();
        return;
      }
      goBackToResults();
    };

    // The route the summary reflects: the card the user clicked,
    // otherwise the Route Agent's recommended route.
    const activeRoute =
      routes.find((route) => {
        const rid = String(
          getValue(route, ["route_id", "routeId"], "")
        ).trim();
        return Boolean(selectedRouteId) && rid === selectedRouteId;
      }) || recRoute ||
      null;

    const activeIsRecommended = Boolean(
      activeRoute &&
        recommendedRouteId &&
        String(
          getValue(activeRoute, ["route_id", "routeId"], "")
        ).trim() === recommendedRouteId
    );

    const handleSelectShipment = (value) => {
      setSelectedShipmentId(value || "");
      if (value) {
        setSelectedRouteId("");
      }
    };

    const handleSelectRoute = (route) => {
      const routeId = String(
        getValue(route, ["route_id", "routeId"], "")
      ).trim();
      setSelectedRouteId(routeId);
      if (routeId || route) {
        setSelectedShipmentId("");
      }
    };

    return (
      <section
        className="maritime-map-view page-view"
        data-testid="fullscreen-maritime-map"
      >
        {/* ---------- PAGE HEADER ---------- */}

        <header className="maritime-map-header">
          <button
            className="maritime-map-back"
            type="button"
            onClick={handleBack}
          >
            {backLabel}
          </button>

          <div className="maritime-map-title">
            <span className="maritime-map-title-label">
              MARITIME ROUTE MAP
            </span>
            <strong>{mapTitle}</strong>
            <div className="maritime-map-stats">
              <span>
                <b>{totalPorts}</b> dataset ports
              </span>
              <span>
                <b>{totalConnections}</b> connections
              </span>
              {routes.length > 0 && (
                <span>
                  <b>{routes.length}</b> routes shown
                </span>
              )}
            </div>
          </div>

          <div className="maritime-map-actions">
            <button
              className="maritime-map-expand"
              type="button"
              onClick={() =>
                setMapExpanded((value) => !value)
              }
            >
              {mapExpanded ? "⤢  Hide expanded map" : "⤢  Expand map"}
            </button>
          </div>
        </header>

        {/* ---------- CONTROLS BAR ---------- */}

        <form
          className="maritime-map-controls"
          onSubmit={handleMapAnalyze}
        >
          <div className="maritime-map-control">
            <label htmlFor="map-origin">Origin</label>
            <select
              id="map-origin"
              value={origin}
              onChange={(e) =>
                handleOriginChange(e.target.value)
              }
            >
              <option value="">Select origin</option>
              {origins.map((item, index) => (
                <option value={item} key={`${item}-${index}`}>
                  {item}
                </option>
              ))}
            </select>
          </div>

          <div className="maritime-map-control">
            <label htmlFor="map-destination">Destination</label>
            <select
              id="map-destination"
              value={destination}
              onChange={(e) =>
                handleDestinationChange(e.target.value)
              }
            >
              <option value="">Select destination</option>
              {destinations.map((item, index) => (
                <option value={item} key={`${item}-${index}`}>
                  {item}
                </option>
              ))}
            </select>
          </div>

          <div className="maritime-map-control">
            <label htmlFor="map-cargo">Cargo Type</label>
            <select
              id="map-cargo"
              value={cargoType}
              onChange={(e) =>
                handleCargoChange(e.target.value)
              }
            >
              <option value="">Select cargo type</option>
              {Object.keys(cargoSubtypesByType).map((type) => (
                <option value={type} key={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>

          <div className="maritime-map-control">
            <label htmlFor="map-subtype">Cargo Subtype</label>
            <select
              id="map-subtype"
              value={cargoSubtype}
              onChange={(e) =>
                setCargoSubtype(e.target.value)
              }
              disabled={subtypeDisabled}
            >
              <option value="">{subtypePlaceholder}</option>
              {routeCargoSubtypes.map((subtype) => (
                <option value={subtype} key={subtype}>
                  {subtype}
                </option>
              ))}
            </select>
            {noSubtypes && (
              <span className="maritime-map-control-note">
                No cargo subtypes available for this route.
              </span>
            )}
          </div>

          <div className="maritime-map-control">
            <label htmlFor="map-containers">Containers</label>
            <input
              id="map-containers"
              type="number"
              min="1"
              value={containers}
              onChange={(e) =>
                setContainers(e.target.value)
              }
              placeholder="TEU"
            />
          </div>

          <button
            className="maritime-map-analyze"
            type="submit"
            disabled={loading || subtypeDisabled}
          >
            {loading ? "Analyzing..." : "Analyze Route"}
          </button>
        </form>

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        {/* ---------- SHIPMENT CONTEXT BAR ---------- */}

        <div className="maritime-shipment-bar">
          <span className="maritime-shipment-bar-label">
            Shipment Context
          </span>
          <select
            className="maritime-shipment-select"
            value={selectedShipmentId}
            onChange={(e) =>
              handleSelectShipment(e.target.value)
            }
            disabled={shipmentsLoading}
          >
            <option value="">
              {shipmentsLoading
                ? "Loading your shipments…"
                : shipments.length > 0
                  ? "Associate a shipment with this map (optional)"
                  : "No shipments yet — accept a quotation to create one"}
            </option>
            {shipments.map((shipment) => (
              <option
                value={shipment.shipment_id}
                key={shipment.shipment_id}
              >
                {shipment.shipment_id} · {shipment.origin} →{" "}
                {shipment.destination}
              </option>
            ))}
          </select>
          {shipmentsError && !shipmentsLoading && (
            <span className="maritime-shipment-bar-note">
              {shipmentsError}
            </span>
          )}
          {activeShipment && (
            <span
              className={`maritime-shipment-status ${shipmentStatusClass(
                activeShipment.status
              )}`}
            >
              {activeShipment.status || "Booking Confirmed"}
            </span>
          )}
        </div>

        {/* ---------- LARGE MAP STAGE ---------- */}

        <div
          className={`maritime-map-stage${
            mapExpanded ? " map-expanded" : ""
          }`}
        >
          {Object.keys(networkPorts).length === 0 &&
          networkLoading ? (
            <div className="maritime-map-loading">
              <span className="ai-agent-core" />
              Loading the complete maritime network…
            </div>
          ) : networkError &&
            Object.keys(networkPorts).length === 0 ? (
            <div className="maritime-map-empty">
              <strong>
                Unable to load the maritime network
              </strong>
              <span>
                The map could not connect to the route data
                service. Please try again.
              </span>
              <button
                className="secondary-button"
                type="button"
                onClick={() =>
                  setMapRetryKey((key) => key + 1)
                }
              >
                Try Again
              </button>
            </div>
          ) : (
            <MapErrorBoundary
              onRetry={() =>
                setMapRetryKey((key) => key + 1)
              }
            >
              <MaritimeRouteMap
                ports={networkPorts}
                edges={networkEdges}
                routes={routes}
                recommendedRouteId={recommendedRouteId}
                selectedRouteId={selectedRouteId}
                onSelectRoute={handleSelectRoute}
                origin={origin}
                destination={destination}
                fitPoints={mapFitPoints}
                fitKey={mapFitKey}
                shipment={activeShipment}
                vessels={vesselsData?.vessels || []}
                vesselsStatus={vesselsData?.status || ""}
                vesselsMessage={vesselsData?.message || ""}
                vesselsUpdatedAt={vesselsData?.updatedAt || ""}
                vesselsSource={vesselsData?.source || ""}
                onRefreshVessels={refreshVessels}
              />
            </MapErrorBoundary>
          )}

          {loading && (
            <div className="maritime-map-loading">
              <span className="ai-agent-core" />
              AI Route Agent analyzing the route…
            </div>
          )}
        </div>

        {/* ---------- ROUTE INFORMATION PANEL ---------- */}

        <div className="maritime-route-panel">
          <div className="maritime-route-panel-head">
            <span className="maritime-route-panel-title">
              Route Information
            </span>
            <span className="maritime-route-panel-hint">
              {routes.length > 0
                ? "Click a route to highlight it on the map"
                : "Analyze a route above to list options"}
            </span>
          </div>

          {activeRoute && (
            <div className="maritime-route-summary">
              <div className="maritime-route-summary-head">
                <span className="maritime-route-summary-title">
                  Route Summary
                </span>
                <span
                  className={`maritime-summary-status ${
                    activeIsRecommended
                      ? "recommended"
                      : "available"
                  }`}
                >
                  {activeIsRecommended
                    ? "★ Recommended"
                    : "◈ Available"}
                </span>
              </div>

              <div className="maritime-summary-main">
                <strong>
                  {getValue(
                    activeRoute,
                    ["origin"],
                    origin
                  )}{" "}
                  →{" "}
                  {getValue(
                    activeRoute,
                    ["destination"],
                    destination
                  )}
                </strong>
                <span>
                  {getRouteNumber(activeRoute)}
                  {getRouteName(activeRoute) !== "Route"
                    ? ` · ${getRouteName(activeRoute)}`
                    : ""}
                </span>
              </div>

              <div className="maritime-summary-metrics">
                <div>
                  <span>Transit</span>
                  <b>{getTransit(activeRoute)}</b>
                </div>
                <div>
                  <span>Distance</span>
                  <b>{getDistance(activeRoute)}</b>
                </div>
                <div>
                  <span>Transshipments</span>
                  <b>{getTransshipments(activeRoute)}</b>
                </div>
                <div>
                  <span>Status</span>
                  <b>
                    {activeIsRecommended
                      ? "Recommended"
                      : "Available"}
                  </b>
                </div>
              </div>
            </div>
          )}

          {activeShipment && (
            <div className="maritime-shipment-panel">
              <div className="maritime-shipment-panel-head">
                <span className="maritime-shipment-panel-title">
                  Associated Shipment
                </span>
                <span
                  className={`maritime-shipment-id ${
                    shipmentStatusClass(activeShipment.status)
                  }`}
                >
                  {activeShipment.shipment_id}
                </span>
              </div>

              <div className="maritime-shipment-panel-body">
                <div className="maritime-shipment-overview">
                  <div className="maritime-shipment-route">
                    <strong>{activeShipment.origin}</strong>
                    <span>→</span>
                    <strong>
                      {activeShipment.destination}
                    </strong>
                  </div>
                  <span className="maritime-shipment-route-name">
                    {activeShipment.route_name || "Route"}
                    {activeShipment.route_id
                      ? ` · ${activeShipment.route_id}`
                      : ""}
                  </span>
                  <div className="maritime-shipment-metrics">
                    <span>
                      Containers{" "}
                      <b>
                        {activeShipment.containers ?? "-"}
                      </b>
                    </span>
                    <span>
                      Transit{" "}
                      <b>
                        {activeShipment.transit_days
                          ? `${activeShipment.transit_days} days`
                          : "-"}
                      </b>
                    </span>
                    <span>
                      Distance{" "}
                      <b>
                        {activeShipment.distance_nm
                          ? `${activeShipment.distance_nm} nm`
                          : "-"}
                      </b>
                    </span>
                    <span>
                      Transshipments{" "}
                      <b>
                        {activeShipment.transshipments ??
                          "-"}
                      </b>
                    </span>
                  </div>
                  <p className="maritime-shipment-note">
                    Shipment route visualization — progress is
                    a platform workflow simulation, not live
                    GPS / AIS vessel tracking.
                  </p>
                </div>

                <div className="maritime-journey">
                  <span className="maritime-journey-title">
                    Shipment Journey
                  </span>
                  <div className="maritime-journey-steps">
                    {shipmentStatusFlow.map((stage) => {
                      const stageIndex =
                        shipmentStatusFlow.indexOf(stage);
                      const currentIndex =
                        shipmentStatusFlow.indexOf(
                          activeShipment.status
                        );
                      const reached =
                        currentIndex >= 0 &&
                        stageIndex <= currentIndex;
                      return (
                        <div
                          className={`maritime-journey-step ${
                            reached ? "reached" : "pending"
                          } ${
                            stageIndex === currentIndex
                              ? "current"
                              : ""
                          }`}
                          key={stage}
                        >
                          <span className="maritime-journey-dot" />
                          <span className="maritime-journey-label">
                            {stage}
                          </span>
                          {stageIndex === currentIndex && (
                            <span className="maritime-journey-current">
                              Current
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}

          {routes.length > 0 ? (
            <div className="maritime-route-cards">
              {routes.map((route, index) => {
                const routeId = String(
                  getValue(route, ["route_id", "routeId"], "")
                ).trim();

                const isRecommended =
                  Boolean(recommendedRouteId) &&
                  routeId === recommendedRouteId;

                const isSelected =
                  !isRecommended &&
                  Boolean(selectedRouteId) &&
                  routeId === selectedRouteId;

                const cardColor = isRecommended
                  ? "#0d8a5e"
                  : alternativeColorFor(routeId, routes, recommendedRouteId);

                return (
                  <div
                    className={`maritime-route-card${
                      isRecommended
                        ? " recommended"
                        : ""
                    }${isSelected ? " selected" : ""}`}
                    key={routeId || `${index}-route`}
                    style={{ borderLeft: `4px solid ${cardColor}` }}
                    onClick={() =>
                      handleSelectRoute(route)
                    }
                    role="button"
                    tabIndex="0"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleSelectRoute(route);
                      }
                    }}
                  >
                    <div className="maritime-route-card-head">
                      <span
                        className="maritime-route-card-color"
                        style={{ background: cardColor }}
                        aria-hidden="true"
                      />
                      <span className="maritime-route-badge">
                        {isRecommended
                          ? "★ Recommended"
                          : `Alternative ${index}`}
                      </span>
                      <span className="maritime-route-rank">
                        {getRouteNumber(route)}
                      </span>
                    </div>

                    <div className="maritime-route-card-route">
                      {getRouteName(route)}
                    </div>

                    <div className="maritime-route-card-metrics">
                      <span>
                        Transit <b>{getTransit(route)}</b>
                      </span>
                      <span>
                        Distance <b>{getDistance(route)}</b>
                      </span>
                      <span>
                        Transshipments{" "}
                        <b>{getTransshipments(route)}</b>
                      </span>
                      <span>
                        Score <b>{getScore(route)}</b>
                      </span>
                      <span
                        className={`maritime-route-card-status ${
                          isRecommended
                            ? "recommended"
                            : isSelected
                              ? "selected"
                              : "available"
                        }`}
                      >
                        {isRecommended
                          ? "Recommended"
                          : isSelected
                            ? "Selected"
                            : "Available"}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="maritime-route-empty">
              {result
                ? "No routes were returned for this combination. Try different cargo or route details."
                : "Select an origin, destination, cargo type and containers above, then click Analyze Route. The recommended route and its alternatives will be highlighted on the map with a summary below."}
            </div>
          )}
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
                        Status
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
                          <RouteHistoryStatus item={item} />
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

        {quotationSuccess && (
          <div className="success-message">
            ✓ {quotationSuccess}
          </div>
        )}

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
                    ACCEPT & GET APPROVAL
                  </span>

                  <h2>
                    Accept This Quotation
                  </h2>

                  <p>
                    Accepting the quotation submits it for
                    admin approval. Once approved, a shipment
                    is created automatically with the status
                    "Booking Confirmed".
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

                  {acceptResult.pending ||
                  acceptResult.already_accepted ? (
                    <>
                      <div className="accept-success-icon accept-success-icon-pending">
                        ⏳
                      </div>

                      <h3>
                        Quotation Pending Admin Approval
                      </h3>

                      <div className="accept-success-status">
                        <span>
                          Approval Status:
                        </span>
                        <strong>
                          Pending Admin Approval
                        </strong>
                      </div>

                      <p className="accept-success-message">
                        {acceptResult.message ||
                          "Your quotation has been submitted for admin approval. Your shipment will be created once an admin approves it."}
                      </p>

                      <button
                        className="primary-button accept-view-shipments"
                        type="button"
                        onClick={goToShipments}
                      >
                        View My Shipments →
                      </button>
                    </>
                  ) : (
                    <>
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
                    </>
                  )}

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
              One end-to-end workflow: enter your shipment
              requirements, let the AI agents design and price
              the best route, then track your shipment.
            </p>

          </div>

        </div>

        {/* ONE UNIFIED WORKFLOW */}
        {/* Combines the user steps with the internal AI agents
            (Route Agent, Pricing Agent, Margin Agent) inline,
            so the process is a single flow — not two separate
            explanations. */}

        <div className="howto-flow">

          {howToFlow.map((step, index) => (
            <React.Fragment key={step.title}>

              {index > 0 && (
                <div
                  className="howto-flow-arrow"
                  aria-hidden="true"
                >
                  →
                </div>
              )}

              <article className="howto-card">

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

                {step.system && (
                  <span className="howto-agent-chip">
                    {step.system}
                  </span>
                )}

              </article>

            </React.Fragment>
          ))}

        </div>

        {/* CLOSING NOTE */}

        <p className="howto-flow-note">
          The Route Agent, Pricing Agent and Margin Agent work at
          exactly the steps shown above, so you always know what
          happens behind the screens. Once the quotation is
          accepted, the shipment follows the controlled status
          flow — Booking Confirmed to Delivered — which you can
          follow in My Shipments and on the Maritime Route Map.
        </p>

      </section>
    );
  };

  // ==========================================
  // ADMIN VIEW HELPERS
  // ==========================================

  const formatAdminDate = (value) => {
    if (!value) return "-";

    const date =
      value instanceof Date
        ? value
        : typeof value === "string"
        ? new Date(value)
        : null;

    if (!date || isNaN(date.getTime())) return String(value);

    const day = date.getDate();
    const month = date.toLocaleString("en", {
      month: "short",
    });
    const year = date.getFullYear();
    let hours = date.getHours();
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const meridiem = hours >= 12 ? "PM" : "AM";
    hours = hours % 12;
    if (hours === 0) hours = 12;

    return `${day} ${month} ${year}, ${hours}:${minutes} ${meridiem}`;
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
              accepted. After admin approval, each accepted
              quotation becomes a shipment.
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
                    {formatDateTime(shipment.created_at)}
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
                    {formatDateTime(shipment.created_at)}
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

          <div
            className="info-card admin-action-card"
            onClick={() =>
              handleNavClick("Maritime Route Map")
            }
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" ||
                e.key === " "
              ) {
                handleNavClick("Maritime Route Map");
              }
            }}
          >

            <div className="info-card-icon">
              🗺️
            </div>

            <div>

              <h3>
                Maritime Route Map
              </h3>

              <p>
                Explore the full fixed maritime
                network of ports and connections.
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
              Approve or reject accepted quotations. Shipments
              are created only after a quotation is approved.
            </p>

          </div>

        </div>

        {/* ERROR */}

        {adminQuotationsError && (
          <div className="error-message">
            {adminQuotationsError}
          </div>
        )}

        {/* ACTION MESSAGE / ERROR */}

        {adminQuotationActionMessage && (
          <div className="success-message">
            {adminQuotationActionMessage}
          </div>
        )}

        {adminQuotationActionError && (
          <div className="error-message">
            {adminQuotationActionError}
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
                      <th>Quotation ID</th>
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
                      <th>Accepted / Date</th>
                      <th>Status</th>
                      <th>Actions</th>

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
                          <span className="history-route-id">
                            {item.record_id || "-"}
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
                            {formatDateTime(
                              item.accepted_at ||
                                item.created_at
                            )}
                          </span>

                        </td>

                        <td>
                          <ApprovalStatusBadge item={item} />
                        </td>

                        <td>
                          <div className="approval-actions">
                            {item.approval_status ===
                            "pending_admin_approval" ? (
                              <>
                                <button
                                  className="approval-approve-btn"
                                  type="button"
                                  disabled={
                                    adminQuotationActionId ===
                                    item.record_id
                                  }
                                  onClick={() =>
                                    handleApproveQuotation(
                                      item
                                    )
                                  }
                                >
                                  {adminQuotationActionId ===
                                  item.record_id
                                    ? "Approving..."
                                    : "Approve"}
                                </button>
                                <button
                                  className="approval-reject-btn"
                                  type="button"
                                  disabled={
                                    adminQuotationActionId ===
                                    item.record_id
                                  }
                                  onClick={() =>
                                    openRejectQuotationModal(
                                      item
                                    )
                                  }
                                >
                                  Reject
                                </button>
                              </>
                            ) : (
                              <span className="approval-no-action">
                                —
                              </span>
                            )}
                          </div>
                        </td>

                      </tr>
                    ))}

                  </tbody>

                </table>

              </div>

            </div>
          )}

        {/* REJECT QUOTATION MODAL */}

        {rejectQuotation && (
          <div
            className="reject-modal-overlay"
            onClick={closeRejectQuotationModal}
          >
            <div
              className="reject-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="reject-modal-title"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="reject-modal-header">
                <span className="section-label">REVIEW QUOTATION</span>
                <h2 id="reject-modal-title">
                  Reject Quotation
                </h2>
                <p>
                  The customer will see this quotation as
                  "Rejected by Admin" with your reason.
                  No shipment will be created.
                </p>
              </div>

              <div className="reject-modal-summary">
                <span>
                  {rejectQuotation.origin || "-"} →{" "}
                  {rejectQuotation.destination || "-"}
                </span>
                <span>
                  {rejectQuotation.cargo_type || "-"}
                  {rejectQuotation.cargo_subtype
                    ? ` / ${rejectQuotation.cargo_subtype}`
                    : ""}
                  {rejectQuotation.containers
                    ? ` · ${rejectQuotation.containers} containers`
                    : ""}
                </span>
              </div>

              <label
                className="reject-modal-label"
                htmlFor="reject-reason-input"
              >
                Rejection reason
              </label>

              <textarea
                id="reject-reason-input"
                className="reject-modal-textarea"
                value={rejectReason}
                onChange={(e) => {
                  setRejectReason(e.target.value);
                  setRejectError("");
                }}
                placeholder="Please provide a reason for rejecting this quotation."
                rows="4"
              />

              {rejectError && (
                <div className="error-message reject-modal-error">
                  {rejectError}
                </div>
              )}

              <div className="reject-modal-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={rejectingQuotation}
                  onClick={closeRejectQuotationModal}
                >
                  Cancel
                </button>
                <button
                  className="approval-reject-btn reject-modal-submit"
                  type="button"
                  disabled={
                    rejectingQuotation ||
                    !rejectReason.trim()
                  }
                  onClick={handleRejectQuotation}
                >
                  {rejectingQuotation
                    ? "Rejecting..."
                    : "Confirm Reject"}
                </button>
              </div>
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
                            {formatDateTime(
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
                  Invitation generated. Copy this link
                  and send it to the invited person.
                  The invitation expires in 24 hours.
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
                  {buildInviteLink(inviteResult?.token)}
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
                  activeNav === "Maritime Route Map"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Maritime Route Map")
                }
              >

                <span className="nav-icon">
                  🗺️
                </span>

                Maritime Route Map

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
                  activeNav === "Maritime Route Map"
                    ? "nav-item active"
                    : "nav-item"
                }
                type="button"
                onClick={() =>
                  handleNavClick("Maritime Route Map")
                }
              >

                <span className="nav-icon">
                  🗺️
                </span>

                Maritime Route Map

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

          {view === "result-map" &&
            renderResultMap()}

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
