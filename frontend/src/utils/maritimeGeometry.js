// =====================================================================
// MARITIME ROUTE GEOMETRY (visualization-only)
// =====================================================================
// Clean, self-contained geometry helpers for the Maritime Route Map.
//
// What this module does:
//   * builds ocean-aware sea lanes between two real dataset ports
//   * honours REAL intermediate/transshipment ports only when the
//     waypoint name resolves to a port in the app's own database
//   * carries non-port corridor labels (e.g. "Suez Canal") as text on
//     the line - never as invented port markers (no fake data)
//   * splits every arc at the international date line (±180°) so no
//     line is ever drawn straight across the world
//   * offsets parallel alternatives so overlapping routes stay readable
//
// The ocean-aware lane engine itself ("does this line stay at sea?")
// lives in ./oceanRoutes.js, which uses a decimated Natural Earth
// coastline model (./coastData.js). Both are deterministic, keyless,
// client-side utilities. No external geocoding or routing service is
// ever called, and no coordinates are invented: every port position
// comes from the backend's own routes.csv.
// =====================================================================

import { oceanRoutePoints } from "./oceanRoutes.js";


// ---------------------------------------------------------------
// ALTERNATIVE ROUTE COLOURS
// ---------------------------------------------------------------
// Every available/alternative route drawn on the Maritime Route Map
// gets its own colour from a shared deterministic palette. The same
// palette is reused by the route cards/list so the map line and the
// card indicator always match. The recommended route always stays the
// brand green and is never assigned a palette colour.
// ---------------------------------------------------------------

export const ALTERNATIVE_PALETTE = [
  "#2563eb", // blue
  "#f97316", // orange
  "#8b5cf6", // purple
  "#06b6d4", // cyan
  "#ec4899", // pink
];

/**
 * Deterministic palette index for an alternative route: the count of
 * non-recommended routes that come before it in the result list,
 * modulo the palette length. Extra alternatives simply cycle through
 * the palette again.
 */
export function alternativeColorIndex(routeId, routes, recommendedRouteId) {
  const target = String(routeId || "").trim();
  const recommended = String(recommendedRouteId || "").trim();
  let countBefore = 0;

  for (const item of routes || []) {
    const id = String(item && (item.route_id ?? item.routeId ?? "")).trim();
    if (id && id === target) break;
    if (id && id !== recommended) {
      countBefore += 1;
    }
  }

  return countBefore % ALTERNATIVE_PALETTE.length;
}

export function alternativeColorFor(routeId, routes, recommendedRouteId) {
  return ALTERNATIVE_PALETTE[
    alternativeColorIndex(routeId, routes, recommendedRouteId)
  ];
}


// ---------------------------------------------------------------
// PORT NAME NORMALIZATION
// ---------------------------------------------------------------
// "Santos", "Port of Santos", "Santos Port" and "Santos Harbor"
// all resolve to the same key so corridor waypoints can be matched
// against the app's own port database. Display names are never
// rewritten - normalization is for lookup only.
// ---------------------------------------------------------------

export function normalizePortName(name) {
  return String(name || "")
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\b(port|harbor|harbour|terminal)\b/g, " ")
    .replace(/\bof\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}


// ---------------------------------------------------------------
// ENGLISH DISPLAY LOCALISATION
// ---------------------------------------------------------------
// All labels rendered by the map are English. A tiny display-only
// normalizer keeps non-ASCII country names from the CSV in English
// form (e.g. "Türkiye" -> "Turkey"). The dataset is never changed.
// ---------------------------------------------------------------

export function displayCountry(country) {
  const value = String(country || "").trim();
  if (/kiye/i.test(value)) return "Turkey";
  return value;
}


// ---------------------------------------------------------------
// SPHERICAL GEOMETRY (great-circle sea arcs)
// ---------------------------------------------------------------

function toRad(value) {
  return (Number(value) * Math.PI) / 180;
}

function fromRad(value) {
  return (value * 180) / Math.PI;
}

function latLonToVec3(lat, lon) {
  const phi = toRad(90 - lat);
  const theta = toRad(lon + 180);
  return [
    Math.sin(phi) * Math.cos(theta),
    Math.sin(phi) * Math.sin(theta),
    Math.cos(phi),
  ];
}

function vec3ToLatLon(vec) {
  const phi = Math.acos(Math.max(-1, Math.min(1, vec[2])));
  const lat = 90 - fromRad(phi);
  let lon = fromRad(Math.atan2(vec[1], vec[0])) - 180;
  lon = ((lon + 540) % 360) - 180;
  return [lat, lon];
}

function norm3(vec) {
  const length = Math.hypot(vec[0], vec[1], vec[2]) || 1;
  return [vec[0] / length, vec[1] / length, vec[2] / length];
}

function slerp(a, b, t) {
  const aN = norm3(a);
  const bN = norm3(b);
  const aDotB = Math.max(
    -1,
    Math.min(1, aN[0] * bN[0] + aN[1] * bN[1] + aN[2] * bN[2])
  );
  const omega = Math.acos(aDotB);

  if (omega < 1e-6) {
    return [
      aN[0] + (bN[0] - aN[0]) * t,
      aN[1] + (bN[1] - aN[1]) * t,
      aN[2] + (bN[2] - aN[2]) * t,
    ];
  }

  const sinOmega = Math.sin(omega);
  const fa = Math.sin((1 - t) * omega) / sinOmega;
  const fb = Math.sin(t * omega) / sinOmega;
  return [
    aN[0] * fa + bN[0] * fb,
    aN[1] * fa + bN[1] * fb,
    aN[2] * fa + bN[2] * fb,
  ];
}

/**
 * Sample a great-circle arc between two positions.
 * Returns an array of [lat, lon] points (inclusive of both ends).
 */
export function greatCirclePoints(a, b, segments = 40) {
  const latA = Number(a[0]);
  const lonA = Number(a[1]);
  const latB = Number(b[0]);
  const lonB = Number(b[1]);

  if (
    !Number.isFinite(latA) ||
    !Number.isFinite(lonA) ||
    !Number.isFinite(latB) ||
    !Number.isFinite(lonB)
  ) {
    return [];
  }

  if (latA === latB && lonA === lonB) {
    return [
      [latA, lonA],
      [latB, lonB],
    ];
  }

  const vecA = latLonToVec3(latA, lonA);
  const vecB = latLonToVec3(latB, lonB);
  const points = [];

  for (let i = 0; i <= segments; i += 1) {
    points.push(vec3ToLatLon(slerp(vecA, vecB, i / segments)));
  }

  return points;
}


/**
 * Great-circle initial bearing (degrees, 0-360) between two points.
 * Used to rotate direction chevrons along a route.
 */
export function bearingBetween(first, second) {
  const lat1 = toRad(Number(first[0]));
  const lat2 = toRad(Number(second[0]));
  const lonDiff = toRad(
    ((Number(second[1]) - Number(first[1]) + 540) % 360) - 180
  );

  const y = Math.sin(lonDiff) * Math.cos(lat2);
  const x =
    Math.cos(lat1) * Math.sin(lat2) -
    Math.sin(lat1) * Math.cos(lat2) * Math.cos(lonDiff);

  return (fromRad(Math.atan2(y, x)) + 360) % 360;
}


/**
 * Pick `count` evenly spaced direction markers along a polyline.
 * Each marker carries its local bearing so chevrons follow the arc.
 */
export function sampleRouteDecorations(points, count = 5) {
  if (!points || points.length < 2) return [];

  const safeCount = Number.isInteger(count) && count > 0 ? count : 5;
  const decorations = [];

  for (let step = 1; step <= safeCount; step += 1) {
    const fraction = step / (safeCount + 1);
    const rawIndex = fraction * (points.length - 1);
    const index = Math.max(
      1,
      Math.min(points.length - 1, Math.round(rawIndex))
    );

    const before = points[Math.max(0, index - 1)];
    const after = points[Math.min(points.length - 1, index + 1)];

    decorations.push({
      position: points[index],
      rotation: bearingBetween(before, after),
    });
  }

  return decorations;
}


// ---------------------------------------------------------------
// INTERNATIONAL DATE LINE
// ---------------------------------------------------------------
// Splits a polyline wherever it crosses the ±180° meridian so the
// arc renders correctly on a flat Mercator map instead of drawing a
// straight line across the entire world.
// ---------------------------------------------------------------

export function splitAtAntimeridian(points) {
  if (!points || points.length < 2) {
    return points ? [points] : [];
  }

  const segments = [];
  let current = [points[0]];

  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const next = points[i];
    const rawDelta = next[1] - prev[1];

    if (rawDelta > 180) {
      const continuousNext = next[1] - 360;
      const progress = (-180 - prev[1]) / (continuousNext - prev[1]);
      const boundaryLat = prev[0] + (next[0] - prev[0]) * progress;
      current.push([boundaryLat, -180]);
      segments.push(current);
      current = [[boundaryLat, 180], next];
    } else if (rawDelta < -180) {
      const continuousNext = next[1] + 360;
      const progress = (180 - prev[1]) / (continuousNext - prev[1]);
      const boundaryLat = prev[0] + (next[0] - prev[0]) * progress;
      current.push([boundaryLat, 180]);
      segments.push(current);
      current = [[boundaryLat, -180], next];
    } else {
      current.push(next);
    }
  }

  segments.push(current);
  return segments;
}


// ---------------------------------------------------------------
// PARALLEL LANE OFFSETS
// ---------------------------------------------------------------
// A small lateral bow separates identical origin -> destination
// corridors so alternative routes stay readable. Purely a
// presentation offset: both ends always remain the two real ports.
// ---------------------------------------------------------------

export function laneOffsetPolyline(points, spreadDeg) {
  if (!spreadDeg || !points || points.length < 2) {
    return points;
  }

  const a = points[0];
  const b = points[points.length - 1];

  const dirLat = b[0] - a[0];
  const dirLon = b[1] - a[1];
  const length = Math.hypot(dirLat, dirLon) || 1;

  const nx = -dirLon / length;
  const ny = dirLat / length;

  const midLat = toRad((a[0] + b[0]) / 2);
  const cosMid = Math.max(0.15, Math.cos(midLat));

  return points.map((point, index) => {
    const t = index / (points.length - 1);
    const amp = Math.sin(Math.PI * t) * spreadDeg;
    return [
      point[0] + ny * amp,
      point[1] + (nx * amp) / cosMid,
    ];
  });
}


/**
 * Deterministic lateral spread for an alternative route, relative to
 * the recommended route (offset = index delta). Ocean-routed lanes use
 * a tighter bow so alternatives stay near the real sea lane.
 *
 * Alternatives fan out in a mirror-symmetric pattern (odd number -> one
 * side, even number -> the other) with a strictly growing per-level
 * offset, so every alternative gets its own clearly separated lane and
 * routes with the same origin/destination can be told apart.
 */
export function alternateLaneSpread(offsetFromRecommended, oceanRouted) {
  const level = Math.abs(offsetFromRecommended);
  if (level === 0) return 0;

  const sideByLevel = level % 2 === 1 ? 1 : -1;
  const side = offsetFromRecommended < 0 ? -1 : 1;
  const baseSpread = oceanRouted ? 1.5 + (level - 1) * 1.5 : 4 + (level - 1) * 6;
  const cap = oceanRouted ? 15 : 38;
  return side * sideByLevel * Math.min(cap, baseSpread);
}


// ---------------------------------------------------------------
// INTERMEDIATE WAYPOINT RESOLUTION
// ---------------------------------------------------------------
// The CSV `intermediate_ports` field names the corridor a route sails
// (e.g. "Mumbai → Gulf Hub → Kochi"). A waypoint is treated as a REAL
// intermediate/transshipment port ONLY when its normalized name
// matches a port in the app's own database. Anything else is kept as
// a textual corridor label rendered on the line.
// ---------------------------------------------------------------

// Corridor labels that carry no navigation meaning on a map (the
// voyage simply takes the direct ocean lane). They are suppressed so
// no empty "◈ Direct" chip is painted along the line.
const VOID_CORRIDORS = new Set([
  "direct",
  "direct ocean",
  "direct atlantic",
  "direct pacific",
  "transshipment",
  "transshipped",
]);

function splitWaypointNames(value) {
  return String(value || "")
    .split(/[→|,;]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function resolveIntermediateWaypoints({
  intermediatePorts,
  portPositions,
  originKey,
  destinationKey,
}) {
  const seen = new Set([originKey, destinationKey]);
  const transitPorts = [];
  let corridorLabel = "";

  splitWaypointNames(intermediatePorts).forEach((name) => {
    const key = normalizePortName(name);
    if (!key || seen.has(key)) return;
    seen.add(key);

    const position = portPositions[key];

    if (position) {
      transitPorts.push({ name, position });
    } else if (!corridorLabel) {
      corridorLabel = name;
    }
  });

  if (VOID_CORRIDORS.has(normalizePortName(corridorLabel))) {
    corridorLabel = "";
  }

  return { transitPorts, corridorLabel };
}


/**
 * Build the full visualization geometry for one route.
 *
 * A continuous polyline runs origin -> (real transit ports) ->
 * destination. When the route has no real intermediate ports the leg
 * uses the ocean-aware lane engine so the line stays at sea; otherwise
 * each leg is a great-circle arc through the real port coordinates.
 *
 * Returns { points, segments, transitPorts, corridorLabel, oceanRouted }
 * or null when either endpoint cannot be resolved.
 */
export function buildRouteGeometry({
  originName,
  destinationName,
  intermediatePorts,
  portPositions,
}) {
  const originKey = normalizePortName(originName);
  const destinationKey = normalizePortName(destinationName);
  const start = portPositions[originKey];
  const end = portPositions[destinationKey];

  if (!originKey || !destinationKey || !start || !end) {
    return null;
  }

  const { transitPorts, corridorLabel } = resolveIntermediateWaypoints({
    intermediatePorts,
    portPositions,
    originKey,
    destinationKey,
  });

  const waypoints = [
    { role: "origin", name: originName, position: start },
    ...transitPorts.map((waypoint) => ({
      role: "transit",
      name: waypoint.name,
      position: waypoint.position,
    })),
    { role: "destination", name: destinationName, position: end },
  ];

  let points = [];
  let oceanRouted = false;

  // No real intermediate ports: use the ocean-aware engine.
  if (transitPorts.length === 0) {
    const lap = oceanRoutePoints(start, end, originName, destinationName);
    if (lap && lap.length >= 2) {
      points = lap;
      oceanRouted = true;
    }
  }

  // Real transit ports (or an ocean lane that failed): great-circle
  // arcs through each waypoint.
  if (points.length < 2) {
    for (let index = 0; index < waypoints.length - 1; index += 1) {
      const leg = greatCirclePoints(
        waypoints[index].position,
        waypoints[index + 1].position,
        40
      );
      if (index > 0 && leg.length > 1) {
        leg.shift();
      }
      points = points.concat(leg);
    }
  }

  if (points.length < 2) {
    points = greatCirclePoints(start, end, 40);
  }

  return {
    waypoints,
    transitPorts,
    corridorLabel: transitPorts.length > 0 ? "" : corridorLabel,
    oceanRouted,
    points,
    segments: splitAtAntimeridian(points),
  };
}


/**
 * Sample a "mid-route" position used to place corridor labels and
 * badges along a polyline (roughly 42% of the way in).
 */
export function pointAlongPolyline(points, fraction = 0.42) {
  if (!points || points.length < 2) return null;
  const index = Math.max(
    0,
    Math.min(points.length - 1, Math.round(points.length * fraction))
  );
  const lon = ((points[index][1] + 540) % 360) - 180;
  return [points[index][0], lon];
}


/**
 * Geographic midpoint of a polyline (for the ⭐ Recommended badge).
 */
export function polylineMidpoint(points) {
  if (!points || points.length < 2) return null;
  const midpoint = points[Math.floor(points.length / 2)];
  const lon = ((midpoint[1] + 540) % 360) - 180;
  return [midpoint[0], lon];
}