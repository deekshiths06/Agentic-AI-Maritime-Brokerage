// =====================================================================
// MARITIME ROUTE MAP
// =====================================================================
// A real-world ocean map built with Leaflet + react-leaflet +
// OpenStreetMap (keyless public tiles, no external geocoding).
//
// Responsibilities (purely presentational - no business logic):
//   * render the app's dataset ports at their real coordinates
//   * draw the Route Agent's recommended + available routes as
//     ocean-aware sea lanes between the two real ports
//   * honour real intermediate/transshipment ports from the app's
//     own port database; corridor labels (e.g. "Suez Canal") are
//     drawn as text on the line, never as invented port markers
//   * split arcs at the international date line so Pacific lanes
//     (Auckland <-> Vancouver) render correctly
//   * overlay live AIS vessels supplied by the FastAPI backend
//     (GET /api/vessels -> AISHub). Only real provider data is
//     rendered - nothing is ever fabricated; when the provider is
//     unavailable the map shows a non-blocking note instead.
//
// Automatic view: fits the active route (else origin->destination,
// else the whole port network) whenever the fit "key" changes, while
// leaving the user free to pan/zoom afterwards.
//
// All labels are English.
// =====================================================================

import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import L from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  MapContainer,
  TileLayer,
  Polyline,
  CircleMarker,
  Tooltip,
  Popup,
  Marker,
  LayerGroup,
  ZoomControl,
  useMap,
} from "react-leaflet";

import {
  alternateLaneSpread,
  alternativeColorFor,
  buildRouteGeometry,
  displayCountry,
  laneOffsetPolyline,
  normalizePortName,
  pointAlongPolyline,
  polylineMidpoint,
  sampleRouteDecorations,
  splitAtAntimeridian,
} from "../utils/maritimeGeometry";

// ---------------------------------------------------------------
// DESIGN TOKENS
// ---------------------------------------------------------------

const COLORS = {
  recommended: "#0d8a5e",
  selected: "#2563eb",
  alternative: "#9fb4c8",
  port: "#3f6d8c",
  shipment: "#0f766e",
  vessel: "#b91c1c",
  origin: "#0b6bcb",
  destination: "#c05621",
  transit: "#2dd4bf",
};

// ---------------------------------------------------------------
// SMALL HELPERS (no hooks)
// ---------------------------------------------------------------

// Reads a route field that may be snake_case or camelCase.
function routeValue(route, snakeKey, camelKey, fallback = "-") {
  const value = route?.[snakeKey] ?? route?.[camelKey];
  return value === undefined || value === null || value === ""
    ? fallback
    : value;
}

function formatAisTime(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Derives each port's dataset role ("origin" | "destination" | "both")
// purely from the fixed network edges loaded from the backend.
function buildPortRoles(edges) {
  const roles = {};

  (edges || []).forEach((edge) => {
    const origin = normalizePortName(edge.origin);
    const destination = normalizePortName(edge.destination);

    if (origin) {
      roles[origin] = roles[origin] === "destination" ? "both" : "origin";
    }
    if (destination) {
      roles[destination] = roles[destination] === "origin" ? "both" : "destination";
    }
  });

  return roles;
}

// ---------------------------------------------------------------
// MAP SENSORS
// ---------------------------------------------------------------

// Leaflet captures its container size at mount. Because the map
// renders inside the app shell while page transitions/CSS run, the
// container can briefly report a wrong size. These timers + a
// ResizeObserver keep the map correctly sized.
function MapResizeSensor({ containerRef }) {
  const map = useMap();

  useEffect(() => {
    const timers = [
      window.setTimeout(() => map.invalidateSize(), 50),
      window.setTimeout(() => map.invalidateSize(), 250),
      window.setTimeout(() => map.invalidateSize(), 600),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [map]);

  useEffect(() => {
    if (!containerRef?.current) return () => {};
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [map, containerRef]);

  return null;
}

// Fits the map over `points` whenever `fitKey` changes. Without a key
// change the user's own pans/zooms are left untouched.
function AutoFitView({ points, fitKey = "", maxZoom = 6 }) {
  const map = useMap();
  const lastFit = useRef({ key: "", points: null });

  useEffect(() => {
    if (!points || points.length === 0) return;

    const signature = points.map((point) => `${point[0]},${point[1]}`).join("|");

    if (lastFit.current.key === fitKey && lastFit.current.points === signature) {
      return;
    }

    lastFit.current = { key: fitKey, points: signature };

    map.fitBounds(L.latLngBounds(points), {
      padding: [48, 48],
      maxZoom,
      animate: false,
    });
  }, [map, points, fitKey, maxZoom]);

  return null;
}

// ---------------------------------------------------------------
// INLINE MARKERS (div icon based, no assets required)
// ---------------------------------------------------------------

// Origin / destination labelled pin.
function EndpointMarker({ position, kind, portName }) {
  const icon = useMemo(
    () =>
      L.divIcon({
        className: "route-endpoint-icon",
        html: `<div class="route-endpoint-marker endpoint-${kind.toLowerCase()}">
                 <span class="route-endpoint-label">
                   <span class="route-endpoint-kind">⚓ ${kind}</span>
                   ${portName ? `<span class="route-endpoint-name">${portName}</span>` : ""}
                 </span>
                 <span class="route-endpoint-pin"><span class="route-endpoint-core"></span></span>
               </div>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
    [kind, portName]
  );

  if (!position) return null;

  return <Marker position={position} icon={icon} interactive={false} zIndexOffset={900} />;
}

// Direction chevron rotated to the local great-circle bearing.
function DirectionArrow({ position, rotation, tone = "alt", color }) {
  const icon = useMemo(
    () =>
      L.divIcon({
        className: "route-arrow-icon",
        html: `<span class="route-arrow route-arrow-${tone}"${
          color
            ? ` style="border-top-color:${color};transform: rotate(${Number(
                rotation
              ).toFixed(0)}deg)"`
            : ` style="transform: rotate(${Number(rotation).toFixed(0)}deg)"`
        }></span>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
    [rotation, tone, color]
  );

  return (
    <Marker
      position={position}
      icon={icon}
      interactive={false}
      zIndexOffset={tone === "recommended" ? 520 : tone === "selected" || tone === "shipment" ? 420 : 320}
    />
  );
}

// Real intermediate/transshipment port marker (honoured only when the
// waypoint name resolves to a port in the app's own database).
function TransitMarker({ position, name, active = false }) {
  const icon = useMemo(
    () =>
      L.divIcon({
        className: "route-transit-icon",
        html: `<div class="route-transit-node${active ? " transit-active" : ""}">
                 <span class="route-transit-tag">[TRANSIT]</span>
                 <span class="route-transit-name">${String(name).trim()}</span>
               </div>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
    [name, active]
  );

  return (
    <>
      <CircleMarker
        center={position}
        radius={8}
        pathOptions={{
          color: active ? COLORS.transit : "#94a3b8",
          weight: 2,
          fillColor: active ? COLORS.shipment : "#64748b",
          fillOpacity: 0.9,
        }}
        interactive={false}
      />
      <Marker position={position} icon={icon} interactive={false} zIndexOffset={800} />
    </>
  );
}

// Corridor label (e.g. "◈ Suez Canal") - a text chip, never a port.
function CorridorLabel({ position, text }) {
  const icon = useMemo(
    () =>
      L.divIcon({
        className: "route-corridor-icon",
        html: `<div class="route-corridor-node">◈ ${String(text).trim()}</div>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
    [text]
  );

  if (!position) return null;

  return <Marker position={position} icon={icon} interactive={false} zIndexOffset={700} />;
}

function RecommendedBadge({ center }) {
  const icon = useMemo(
    () =>
      L.divIcon({
        className: "recommended-badge-icon",
        html: '<div class="recommended-badge-node">★ Recommended</div>',
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
    []
  );

  if (!center) return null;

  return <Marker position={center} icon={icon} interactive={false} zIndexOffset={1000} />;
}

function ShipmentBadge({ center, label }) {
  const icon = useMemo(
    () =>
      L.divIcon({
        className: "recommended-badge-icon",
        html: `<div class="shipment-route-badge-node">▤ ${String(label).trim()}</div>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
    [label]
  );

  if (!center) return null;

  return <Marker position={center} icon={icon} interactive={false} zIndexOffset={1001} />;
}

// ---------------------------------------------------------------
// AIS VESSEL LAYER
// ---------------------------------------------------------------
// Real vessels returned by the backend (GET /api/vessels -> AISHub).
// Only vessels currently inside the map viewport are rendered, so a
// global dataset never floods the map. No fake vessels are created.

function VesselPopupRow({ label, value }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="ais-popup-row">
      <span className="ais-popup-label">{label}</span>
      <strong className="ais-popup-value">{value}</strong>
    </div>
  );
}

function VesselMarker({ vessel }) {
  const heading = Number(vessel.heading);
  const rotation = Number.isFinite(heading) ? heading : 0;

  const icon = useMemo(
    () =>
      L.divIcon({
        className: "ais-vessel-icon",
        html: `<div class="ais-vessel-marker" style="transform: rotate(${Number(
          rotation
        ).toFixed(1)}deg)"><span class="ais-ship-hull"></span><span class="ais-ship-head"></span></div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      }),
    [rotation]
  );

  const position = [Number(vessel.latitude), Number(vessel.longitude)];
  const vesselName = String(vessel.name || "").trim();
  const destination = String(vessel.destination || "").trim();
  const eta = String(vessel.eta || "").trim();
  const speed = vessel.speed_knots ?? null;
  const course = vessel.course ?? null;
  const headingValue = vessel.heading ?? null;
  const timestamp = formatAisTime(vessel.timestamp);

  return (
    <Marker position={position} icon={icon} zIndexOffset={880}>
      <Popup className="ais-vessel-popup" autoPan={false}>
        <div className="ais-popup-head">
          <span className="ais-popup-title">🚢 {vesselName || "Unidentified vessel"}</span>
          <span className="ais-popup-source">Recent AIS data (AISHub)</span>
        </div>
        <div className="ais-popup-grid">
          <VesselPopupRow label="MMSI" value={vessel.mmsi} />
          <VesselPopupRow label="IMO" value={vessel.imo} />
          <VesselPopupRow label="Vessel type" value={vessel.vessel_type} />
          <VesselPopupRow label="Latitude" value={Number(vessel.latitude).toFixed(4)} />
          <VesselPopupRow label="Longitude" value={Number(vessel.longitude).toFixed(4)} />
          <VesselPopupRow
            label="Speed"
            value={speed != null ? `${Number(speed).toFixed(1)} kn` : null}
          />
          <VesselPopupRow
            label="Course"
            value={course != null ? `${Number(course).toFixed(0)}°` : null}
          />
          <VesselPopupRow
            label="Heading"
            value={headingValue != null ? `${Number(headingValue).toFixed(0)}°` : null}
          />
          <VesselPopupRow label="Destination" value={destination || null} />
          <VesselPopupRow label="ETA" value={eta || null} />
          {timestamp && <VesselPopupRow label="Last AIS update" value={timestamp} />}
        </div>
      </Popup>
    </Marker>
  );
}

function AISVesselLayer({ vessels }) {
  const map = useMap();
  const [bounds, setBounds] = useState(() => map.getBounds());

  useEffect(() => {
    const update = () => setBounds(map.getBounds());
    update();
    map.on("moveend zoomend", update);
    return () => {
      map.off("moveend zoomend", update);
    };
  }, [map]);

  const visibleVessels = useMemo(() => {
    if (!vessels || vessels.length === 0) return [];
    const box = L.latLngBounds(bounds);

    return vessels.filter((vessel) => {
      const lat = Number(vessel.latitude);
      const lon = Number(vessel.longitude);
      return (
        Number.isFinite(lat) &&
        Number.isFinite(lon) &&
        lat >= -90 &&
        lat <= 90 &&
        lon >= -180 &&
        lon <= 180 &&
        box.contains([lat, lon])
      );
    });
  }, [vessels, bounds]);

  if (visibleVessels.length === 0) return null;

  return (
    <LayerGroup>
      {visibleVessels.map((vessel) => {
        const key = String(
          vessel.mmsi || vessel.imo || `${vessel.latitude},${vessel.longitude}` || ""
        ).trim();
        return <VesselMarker key={`ais-${key}`} vessel={vessel} />;
      })}
    </LayerGroup>
  );
}

// ---------------------------------------------------------------
// ROUTE INFO OVERLAYS (tooltip + popup)
// ---------------------------------------------------------------

function RouteInfoPopup({ route, isRecommended }) {
  const routeNumber = String(
    routeValue(route, "route_id", "routeId", "Route")
  ).trim();

  const origin = String(routeValue(route, "origin", "", "-"));
  const destination = String(routeValue(route, "destination", "", "-"));
  const transit = routeValue(route, "transit_days", "transitDays", "-");
  const distance = routeValue(route, "distance_nm", "distance", "-");
  const transshipments = routeValue(route, "transshipments", "transshipment", "-");
  const score = routeValue(route, "score", "score", "-");
  const status = isRecommended ? "Recommended" : "Available";

  const row = (label, value) => (
    <div className="route-detail-row">
      <span className="route-detail-label">{label}</span>
      <strong className="route-detail-value">{value}</strong>
    </div>
  );

  return (
    <div className="route-detail-popup">
      <div className="route-detail-title">Route Information</div>
      {row("Route ID", routeNumber)}
      {row("Origin", origin)}
      {row("Destination", destination)}
      {row("Transit Days", `${transit} days`)}
      {row("Distance", `${distance} nm`)}
      {row("Transshipments", transshipments)}
      {row("Score", score)}
      {row("Status", status)}
    </div>
  );
}

// ===============================================================
// MAIN COMPONENT
// ===============================================================

export default function MaritimeRouteMap({
  ports = {},
  edges = [],
  origin = "",
  destination = "",
  routes = [],
  recommendedRouteId = "",
  selectedRouteId = "",
  onSelectRoute = () => {},
  fitPoints = null,
  fitKey = "",
  shipment = null,
  vessels = [],
  vesselsStatus = "",
  vesselsMessage = "",
  vesselsUpdatedAt = "",
  vesselsSource = "",
  onRefreshVessels = null,
}) {
  const [mapReady, setMapReady] = useState(false);
  const [showRecommended, setShowRecommended] = useState(true);
  const [showAvailable, setShowAvailable] = useState(true);
  const [showAis, setShowAis] = useState(true);
  const containerRef = useRef(null);

  // ---------------------------------------------------------------
  // PORT DATA
  // ---------------------------------------------------------------

  const portPositions = useMemo(() => {
    const map = {};
    Object.keys(ports || {}).forEach((name) => {
      const lat = Number(ports[name] && ports[name].latitude);
      const lon = Number(ports[name] && ports[name].longitude);
      if (Number.isFinite(lat) && Number.isFinite(lon) && !(lat === 0 && lon === 0)) {
        map[normalizePortName(name)] = [lat, lon];
      }
    });
    return map;
  }, [ports]);

  const portEntries = useMemo(() => {
    const seen = new Set();
    const entries = [];

    Object.keys(ports || {}).forEach((name) => {
      const key = normalizePortName(name);
      if (!key || seen.has(key)) return;

      const port = ports[name];
      const lat = Number(port && port.latitude);
      const lon = Number(port && port.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || (lat === 0 && lon === 0)) return;

      seen.add(key);
      entries.push({
        name,
        latitude: lat,
        longitude: lon,
        country: displayCountry(port && port.country),
      });
    });

    return entries;
      }, [ports]);

  const allPortPoints = useMemo(
    () => portEntries.map((port) => [port.latitude, port.longitude]),
    [portEntries]
  );

  const portRoles = useMemo(() => buildPortRoles(edges), [edges]);

  // ---------------------------------------------------------------
  // ROUTES (Route Agent results only)
  // ---------------------------------------------------------------

  const routeFeatures = useMemo(() => {
    const safeRoutes = (routes || []).filter(
      (route) => route && typeof route === "object"
    );
    if (safeRoutes.length === 0) return [];

    if (!portPositions[normalizePortName(origin)] || !portPositions[normalizePortName(destination)]) {
      return [];
    }

    const recommendedIndex = safeRoutes.findIndex(
      (route) =>
        String(routeValue(route, "route_id", "routeId", "")).trim() ===
        String(recommendedRouteId || "").trim()
    );

    const features = [];

    safeRoutes.forEach((route, index) => {
      const routeId = String(routeValue(route, "route_id", "routeId", "")).trim();
      const isRecommended = recommendedIndex === index;
      const isSelected =
        !isRecommended && routeId === String(selectedRouteId || "").trim();

      const geometry = buildRouteGeometry({
        originName: origin,
        destinationName: destination,
        intermediatePorts: route.intermediate_ports ?? route.intermediatePorts,
        portPositions,
      });
      if (!geometry) return;

      // Lateral separation only between identical origin -> destination
      // corridors without real transit ports (presentation offset only;
      // both ends always stay the two real ports).
      let points = geometry.points;
      if (geometry.transitPorts.length === 0 && recommendedIndex !== -1) {
        const spread = alternateLaneSpread(index - recommendedIndex, geometry.oceanRouted);
        if (spread !== 0) {
          points = laneOffsetPolyline(geometry.points, spread);
        }
      }

      features.push({
        route,
        routeId,
        isRecommended,
        isSelected,
        altColor: isRecommended
          ? null
          : alternativeColorFor(
              routeId,
              safeRoutes,
              String(recommendedRouteId || "").trim()
            ),
        transitPorts: geometry.transitPorts,
        corridorLabel: geometry.corridorLabel,
        points,
        segments: splitAtAntimeridian(points),
        decorations: sampleRouteDecorations(points, 5),
        corridorPosition: pointAlongPolyline(points, 0.42),
      });
    });

    return features;
  }, [routes, origin, destination, recommendedRouteId, selectedRouteId, portPositions]);

  // ---------------------------------------------------------------
  // SHIPMENT CONTEXT
  // ---------------------------------------------------------------

  const shipmentName = String(shipment?.shipment_id || "").trim();
  const shipmentRouteId = String(shipment?.route_id || shipment?.routeId || "").trim();
  const shipmentOriginName = String(shipment?.origin || "").trim();
  const shipmentDestinationName = String(shipment?.destination || "").trim();

  const shipmentMatch = useMemo(() => {
    if (!shipmentName || !shipmentRouteId) return null;
    return routeFeatures.find((item) => item.routeId === shipmentRouteId) || null;
  }, [shipmentName, shipmentRouteId, routeFeatures]);

  const shipmentArc = useMemo(() => {
    if (!shipmentName) return null;

    const geometry = buildRouteGeometry({
      originName: shipmentOriginName,
      destinationName: shipmentDestinationName,
      intermediatePorts: shipment?.intermediate_ports ?? shipment?.intermediatePorts,
      portPositions,
    });
    if (!geometry) return null;

    const points =
      geometry.transitPorts.length === 0 ? geometry.points : geometry.points;

    return {
      ...geometry,
      points,
      segments: splitAtAntimeridian(points),
      decorations: sampleRouteDecorations(points, 4),
      corridorPosition: pointAlongPolyline(points, 0.42),
    };
  }, [shipmentName, shipmentOriginName, shipmentDestinationName, shipment, portPositions]);

  const activeRouteItem = useMemo(() => {
    if (shipmentMatch) return shipmentMatch;
    if (shipmentName && shipmentArc) return shipmentArc;
    const selected = routeFeatures.find((item) => item.isSelected);
    if (selected) return selected;
    return routeFeatures.find((item) => item.isRecommended) || null;
  }, [shipmentMatch, shipmentName, shipmentArc, routeFeatures]);

  const endpointNames = useMemo(
    () =>
      shipmentName
        ? [shipmentOriginName, shipmentDestinationName]
        : [origin, destination],
    [shipmentName, shipmentOriginName, shipmentDestinationName, origin, destination]
  );

  const activeStart = portPositions[normalizePortName(endpointNames[0])] || null;
  const activeEnd = portPositions[normalizePortName(endpointNames[1])] || null;

  const recommendedFeature = routeFeatures.find((item) => item.isRecommended) || null;

  const anchorLine = shipmentMatch || shipmentArc || recommendedFeature || null;
  const anchorMid = polylineMidpoint(anchorLine ? anchorLine.points : null);

  // Fit target: active route, else explicit fit points, else ports.
  const fitTarget = useMemo(() => {
    if (activeRouteItem && activeRouteItem.points && activeRouteItem.points.length >= 2) {
      return activeRouteItem.points;
    }
    if (fitPoints && fitPoints.length >= 2) return fitPoints;
    return allPortPoints;
  }, [activeRouteItem, fitPoints, allPortPoints]);

  const fitKeyCombined = `${shipmentName ? "shipment" : "route"}-${fitKey}`;
  const fitMaxZoom = activeRouteItem ? 7 : 2;

  // ---------------------------------------------------------------
  // AIS STATUS
  // ---------------------------------------------------------------

  const safeVessels = useMemo(
    () =>
      (vessels || []).filter((vessel) => {
        const lat = Number(vessel && vessel.latitude);
        const lon = Number(vessel && vessel.longitude);
        return (
          Number.isFinite(lat) &&
          Number.isFinite(lon) &&
          lat >= -90 &&
          lat <= 90 &&
          lon >= -180 &&
          lon <= 180
        );
      }),
    [vessels]
  );

  const aisVesselsPresent = safeVessels.length > 0;
  const aisSnapshotLabel = formatAisTime(vesselsUpdatedAt);

  const aisNotice = useMemo(() => {
    if (vesselsStatus === "not_configured") {
      return {
        kind: "warn",
        text:
          "Live AIS vessel tracking is not configured. Add AIS_API_KEY to the backend environment to enable live vessel data.",
      };
    }

    if (vesselsStatus === "unavailable") {
      return {
        kind: "warn",
        text: vesselsMessage || "Live vessel data temporarily unavailable.",
      };
    }

    if (vesselsStatus === "ok") {
      if (safeVessels.length === 0) {
        return { kind: "warn", text: "Live AIS vessel data unavailable." };
      }
      const source = vesselsSource || "AIS";
      const suffix = aisSnapshotLabel ? ` - snapshot ${aisSnapshotLabel}` : "";
      return {
        kind: "ok",
        text: `🚢 ${safeVessels.length} real AIS vessel${
          safeVessels.length === 1 ? "" : "s"
        } (recent ${source} data${suffix})`,
      };
    }

    return null;
  }, [vesselsStatus, safeVessels, vesselsSource, aisSnapshotLabel, vesselsMessage]);

  // ---------------------------------------------------------------
  // ROUTE RENDERING HELPERS
  // ---------------------------------------------------------------

  const modeForItem = (item) => {
    if (shipmentMatch && item.routeId === shipmentMatch.routeId) return "shipment";
    if (item.isRecommended) return "recommended";
    if (item.isSelected) return "selected";
    return "alt";
  };

  const renderRouteDecorations = (item, mode) => {
    const tone =
      mode === "recommended"
        ? "recommended"
        : mode === "selected"
          ? "selected"
          : mode === "shipment"
            ? "shipment"
            : "alt";

    const arrowCount = mode === "alt" ? 2 : 5;
    const arrows = item.decorations || [];
    const usedArrows =
      arrowCount < arrows.length
        ? arrows.filter(
            (_, index) =>
              index % Math.ceil(arrows.length / arrowCount) === 0
          )
        : arrows;

    return (
      <>
        {usedArrows.map((arrow, index) => (
          <DirectionArrow
            key={`${mode}-arrow-${item.routeId}-${index}`}
            position={arrow.position}
            rotation={arrow.rotation}
            tone={tone}
            color={mode === "alt" ? item.altColor : undefined}
          />
        ))}

        {mode !== "alt" &&
          (item.transitPorts || []).map((waypoint, index) => (
            <TransitMarker
              key={`${mode}-transit-${item.routeId}-${index}`}
              position={waypoint.position}
              name={waypoint.name}
              active
            />
          ))}

        {mode !== "alt" && item.corridorLabel && (
          <CorridorLabel
            position={item.corridorPosition}
            text={item.corridorLabel}
          />
        )}
      </>
    );
  };

  const renderRouteLine = (item, mode) => {
    const style =
      mode === "shipment"
        ? { casing: "#ffffff", core: COLORS.shipment, weight: 5.5 }
        : mode === "recommended"
          ? { casing: "#ffffff", core: COLORS.recommended, weight: 7 }
          : mode === "selected"
            ? {
                casing: "#ffffff",
                core: item.altColor || COLORS.selected,
                weight: 5.5,
              }
            : {
                casing: "transparent",
                core: item.altColor || COLORS.alternative,
                weight: 2.5,
              };

    const isRecommended = mode === "recommended";
    const route = item.route;

    const pathSegments = [
      String(routeValue(route, "origin", "", origin)),
      ...(item.transitPorts || []).map((waypoint) => waypoint.name),
      String(routeValue(route, "destination", "", destination)),
    ];

    const transit = routeValue(route, "transit_days", "transitDays", "-");
    const distance = routeValue(route, "distance_nm", "distance", "-");
    const transshipments = routeValue(route, "transshipments", "transshipment", "-");

    return item.segments.map((segment, segmentIndex) => (
      <React.Fragment key={`${mode}-${item.routeId}-${segmentIndex}`}>
        <Polyline
          positions={segment}
          interactive={false}
          pathOptions={{
            color: style.casing,
            weight: style.weight + 5,
            opacity: mode === "alt" ? 0 : 0.92,
            lineCap: "round",
            lineJoin: "round",
          }}
        />
        <Polyline
          positions={segment}
          interactive
          eventHandlers={{ click: () => onSelectRoute(route) }}
          pathOptions={{
            color: style.core,
            weight: style.weight,
            opacity: mode === "alt" ? 0.72 : 0.98,
            lineCap: "round",
            lineJoin: "round",
            dashArray: mode === "alt" ? "3 9" : undefined,
            className:
              mode === "shipment"
                ? "route-shipment-line"
                : mode === "recommended"
                  ? "route-flow-line"
                  : mode === "selected"
                    ? "route-selected-line"
                    : "route-alt-line",
          }}
        >
          <Tooltip
            direction="top"
            offset={[0, -12]}
            opacity={1}
            className="route-info-tooltip"
          >
            <div className="route-tip-route">{item.routeId}</div>
            <div className="route-tip-path">{pathSegments.join(" → ")}</div>
            <div className="route-tip-metrics">
              <span>Transit {transit}d</span>
              <span>{distance} nm</span>
              <span>{transshipments} trans</span>
            </div>
          </Tooltip>

          <Popup className="route-port-popup" autoPan={false}>
            <RouteInfoPopup route={route} isRecommended={isRecommended} />
          </Popup>
        </Polyline>
      </React.Fragment>
    ));
  };

  // ---------------------------------------------------------------
  // LAYER FILTERING (simple controls)
  // ---------------------------------------------------------------

  const visibleRouteFeatures = useMemo(
    () =>
      routeFeatures.filter((item) => {
        const mode = modeForItem(item);
        if (mode === "alt") return showAvailable;
        if (mode === "recommended") return showRecommended;
        return true; // selected + shipment lines always stay visible
      }),
    [routeFeatures, showRecommended, showAvailable] // eslint-disable-line react-hooks/exhaustive-deps
  );

  // Distinct palette colours actually used by the available routes, in
  // result order. Drives one legend row per colour so every alternative
  // lane on the map is accounted for (palette cycles when needed).
  const legendAlternativeColors = useMemo(() => {
    if (!showAvailable) return [];
    const seen = new Set();
    const colors = [];
    routeFeatures.forEach((item) => {
      if (item.isRecommended || !item.altColor) return;
      if (seen.has(item.altColor)) return;
      seen.add(item.altColor);
      colors.push(item.altColor);
    });
    return colors;
  }, [routeFeatures, showAvailable]);

  // ---------------------------------------------------------------
  // RENDER
  // ---------------------------------------------------------------

  const hasAnyRoutes = routeFeatures.length > 0;
  const singleRouteOnly = hasAnyRoutes && routeFeatures.length === 1 && !shipmentName;

  return (
    <div
      className="route-map-leaflet"
      data-testid="maritime-route-map"
      ref={containerRef}
    >
      {allPortPoints.length > 0 ? (
        <>
          <MapContainer
            className="maritime-leaflet-map"
            center={[18, 20]}
            zoom={2}
            minZoom={1}
            maxZoom={18}
            zoomControl={false}
            worldCopyJump
            scrollWheelZoom
            attributionControl
            whenReady={() => setMapReady(true)}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              subdomains="abc"
              maxZoom={19}
            />

            <MapResizeSensor containerRef={containerRef} />
            <AutoFitView points={fitTarget} fitKey={fitKeyCombined} maxZoom={fitMaxZoom} />
            <ZoomControl position="topleft" />

            {/* -------- ROUTE LAYERS -------- */}
            {visibleRouteFeatures.length > 0 && (
              <LayerGroup>
                {visibleRouteFeatures.map((item) => {
                  const mode = modeForItem(item);
                  return (
                    <React.Fragment key={`${mode}-${item.routeId}`}>
                      {renderRouteLine(item, mode)}
                      {renderRouteDecorations(item, mode)}
                    </React.Fragment>
                  );
                })}
              </LayerGroup>
            )}

            {shipmentName && !shipmentMatch && shipmentArc && (
              <LayerGroup>
                {renderRouteLine(shipmentArc, "shipment")}
                {renderRouteDecorations(shipmentArc, "shipment")}
              </LayerGroup>
            )}

            {shipmentName ? (
              anchorMid && <ShipmentBadge center={anchorMid} label={shipmentName} />
            ) : (
              recommendedFeature &&
              anchorMid && <RecommendedBadge center={anchorMid} />
            )}

            {/* -------- ENDPOINT MARKERS -------- */}
            {activeStart && (
              <EndpointMarker position={activeStart} kind="ORIGIN" portName={endpointNames[0]} />
            )}
            {activeEnd && (
              <EndpointMarker position={activeEnd} kind="DESTINATION" portName={endpointNames[1]} />
            )}

            {/* -------- DATASET PORTS -------- */}
            <LayerGroup>
              {portEntries.map((port) => {
                const key = normalizePortName(port.name);
                const role = portRoles[key] || "";
                const highlighted =
                  key === normalizePortName(endpointNames[0]) ||
                  key === normalizePortName(endpointNames[1]);

                return (
                  <React.Fragment key={key}>
                    <CircleMarker
                      center={[port.latitude, port.longitude]}
                      radius={highlighted ? 12 : 9}
                      pathOptions={{
                        color: "transparent",
                        fillColor: COLORS.port,
                        fillOpacity: highlighted ? 0.22 : 0.14,
                      }}
                      interactive={false}
                    />
                    <CircleMarker
                      center={[port.latitude, port.longitude]}
                      radius={6}
                      pathOptions={{
                        color: highlighted ? "#ffffff" : "#ffffff",
                        weight: 2,
                        fillColor: highlighted ? COLORS.shipment : COLORS.port,
                        fillOpacity: 0.95,
                      }}
                      interactive
                    >
                      <Tooltip direction="top" offset={[0, -9]} opacity={0.95} className="route-port-tooltip">
                        {port.name}
                      </Tooltip>
                      <Popup className="route-port-popup" autoPan={false}>
                        <div className="port-popup-name">{port.name}</div>
                        {port.country && (
                          <div className="port-popup-country">{port.country}</div>
                        )}
                        <div className="port-popup-type-row">
                          {role && (
                            <span className={`port-popup-type ${role}`}>
                              {role === "both"
                                ? "Origin & Destination Port"
                                : role === "origin"
                                  ? "Origin Port"
                                  : "Destination Port"}
                            </span>
                          )}
                          {(role === "both" ||
                            role === "origin" ||
                            role === "destination") && (
                            <span className="port-popup-type dataset-port">
                              Dataset Port
                            </span>
                          )}
                        </div>
                      </Popup>
                    </CircleMarker>
                  </React.Fragment>
                );
              })}
            </LayerGroup>

            {/* -------- REAL AIS VESSELS -------- */}
            {aisVesselsPresent && showAis && <AISVesselLayer vessels={safeVessels} />}
          </MapContainer>

          {/* -------- LAYER CONTROLS -------- */}
          {mapReady && (
            <div className="maritime-map-tools" aria-label="Map layer controls">
              <span className="map-tools-title">Layers</span>
              <button
                type="button"
                className={`map-tool-toggle${showRecommended ? " active" : ""}`}
                onClick={() => setShowRecommended((value) => !value)}
                aria-pressed={showRecommended}
              >
                ⭐ Recommended
              </button>
              <button
                type="button"
                className={`map-tool-toggle${showAvailable ? " active" : ""}`}
                onClick={() => setShowAvailable((value) => !value)}
                aria-pressed={showAvailable}
              >
                🚢 Available
              </button>
              <button
                type="button"
                className={`map-tool-toggle${showAis ? " active" : ""}`}
                onClick={() => setShowAis((value) => !value)}
                aria-pressed={showAis}
              >
                🚢 AIS
              </button>
            </div>
          )}

          {/* -------- LEGEND -------- */}
          {mapReady && (
            <div className="maritime-map-legend" aria-label="Map legend">
              {showRecommended && hasAnyRoutes && !shipmentName && (
                <div className="maritime-legend-row">
                  <span className="legend-line legend-line-recommended" />
                  🟢 Recommended Route
                </div>
              )}
              {!shipmentName &&
                legendAlternativeColors.map((color) => (
                  <div className="maritime-legend-row" key={color}>
                    <span className="legend-line" style={{ background: color }} />
                    Available Route
                  </div>
                ))}
              <div className="maritime-legend-row">
                <span className="legend-port" />
                ⚓ Port
              </div>
              {aisVesselsPresent && showAis && (
                <div className="maritime-legend-row">
                  <span className="legend-vessel" />
                  🚢 Live AIS Vessel
                </div>
              )}
            </div>
          )}

          {/* -------- AIS STATUS BANNER -------- */}
          {mapReady && aisNotice && (
            <div
              className={`maritime-ais-banner ais-${aisNotice.kind}`}
              role="status"
              aria-live="polite"
            >
              <span className="ais-banner-text">{aisNotice.text}</span>
              {vesselsStatus === "ok" && onRefreshVessels && (
                <button
                  className="ais-banner-refresh"
                  type="button"
                  onClick={onRefreshVessels}
                >
                  Refresh
                </button>
              )}
            </div>
          )}

          {/* -------- FOOTNOTE -------- */}
          {mapReady && (
            <div className="maritime-map-note">
              {shipmentName
                ? "Shipment route visualization — progress is a workflow simulation, not GPS/AIS tracking of that shipment."
                : singleRouteOnly
                  ? "Only one available route found for this selection."
                  : "Dataset sea lanes between ports. Vessel markers are real AIS positions supplied by the AIS provider — shown independently of any shipment."}
            </div>
          )}
        </>
      ) : (
        <div className="maritime-map-empty">
          <strong>No port data available</strong>
          <span>
            The dataset could not be loaded, so no ports can be plotted.
          </span>
        </div>
      )}
    </div>
  );
}