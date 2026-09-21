// =====================================================================
// OCEAN-AWARE ROUTE GEOMETRY (visualization-only maritime routing)
// ---------------------------------------------------------------------
// Self-contained, deterministic maritime routing for the operations
// map: fully client-side, no external API and no API keys.
//
//  * Origin -> ocean lane -> destination instead of great-circles
//    that cut through continents.
//  * The path is a *geographic visualization* between real dataset
//    ports, never a claim of exact lanes or live vessel tracks.
//
// Strategy:
//  1. A real coastline model (decimated Natural Earth polygons)
//     decides whether a sampled point is on land or at sea.
//  2. Region-based ocean lanes connect every pair of port regions.
//     Each lane is stored "origin side -> destination side";
//     laneRails() reverses the chain when the pair is queried from
//     the other side.
//  3. Per-port APPROACH chains get a ship safely out of its coastal
//     box (or into the port) before/after the region lane.
//  4. A bounded "sentinel" pass inspects every waypoint leg and
//     inserts a detour waypoint when a leg still crosses a long land
//     run.
// =====================================================================

import COAST from "./coastData.js";

const LANE_DEG_SAMPLE = 0.7; // ~0.7 degrees between samples on a leg

// ---------------------------------------------------------------
// REAL LAND MODEL - decimated world coastline polygons
// ---------------------------------------------------------------

function base64ToUint8(b64) {
  const chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const clean = String(b64).replace(/[^A-Za-z0-9+/]/g, "");
  const len = clean.length;
  const bytes = new Uint8Array((len * 3) / 4);
  let p = 0;
  for (let i = 0; i < len; i += 4) {
    const c0 = chars.indexOf(clean[i]);
    const c1 = chars.indexOf(clean[i + 1]);
    const c2 = chars.indexOf(clean[i + 2]);
    const c3 = chars.indexOf(clean[i + 3]);
    bytes[p++] = (c0 << 2) | (c1 >> 4);
    if (i + 2 < len) bytes[p++] = ((c1 & 15) << 4) | (c2 >> 2);
    if (i + 3 < len) bytes[p++] = ((c2 & 3) << 6) | c3;
  }
  return bytes;
}

const COAST_RINGS = (() => {
  const n = COAST.n;
  const coordBuf = base64ToUint8(COAST.r);
  const boxBuf = base64ToUint8(COAST.b);
  const offBuf = base64ToUint8(COAST.o);
  const rings = [];
  for (let i = 0; i < n; i += 1) {
    const start = offBuf[i * 4] | (offBuf[i * 4 + 1] << 8) | (offBuf[i * 4 + 2] << 16) | (offBuf[i * 4 + 3] << 24);
    const end = offBuf[(i + 1) * 4] | (offBuf[(i + 1) * 4 + 1] << 8) | (offBuf[(i + 1) * 4 + 2] << 16) | (offBuf[(i + 1) * 4 + 3] << 24);
    const count = end - start;
    const lons = new Float32Array(count);
    const lats = new Float32Array(count);
    for (let k = 0; k < count; k += 1) {
      const o = (start + k) * 4;
      let v16 = offBuf[o] | (offBuf[o + 1] << 8);
      if (v16 & 0x8000) v16 -= 0x10000;
      lons[k] = v16 / 100;
      v16 = offBuf[o + 2] | (offBuf[o + 3] << 8);
      if (v16 & 0x8000) v16 -= 0x10000;
      lats[k] = v16 / 100;
    }
    rings.push({
      lons,
      lats,
      minLon: readF32(boxBuf, i * 16),
      minLat: readF32(boxBuf, i * 16 + 4),
      maxLon: readF32(boxBuf, i * 16 + 8),
      maxLat: readF32(boxBuf, i * 16 + 12),
    });
  }
  return rings;
})();

function readF32(buf, o) {
  const u = buf[o] | (buf[o + 1] << 8) | (buf[o + 2] << 16) | (buf[o + 3] << 24);
  const pow = Math.pow;
  const sign = (u & 0x80000000) ? -1 : 1;
  const exp = (u >> 23) & 0xff;
  const mant = u & 0x7fffff;
  if (exp === 0xff) return mant ? NaN : sign * Infinity;
  if (exp === 0) return sign * mant * pow(2, -149);
  return sign * (1 + mant / 0x800000) * pow(2, exp - 127);
}

function pointInRing(lat, lon, ring) {
  const { lons, lats } = ring;
  let inside = false;
  for (let i = 0, j = lons.length - 1; i < lons.length; j = i += 1) {
    const xi = lons[i];
    const yi = lats[i];
    const xj = lons[j];
    const yj = lats[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

// ---------------------------------------------------------------
// NAVIGABLE PASSES - narrow straits/canals that are land in the
// coastline data but are genuinely passable by a ship. A sampled
// point inside one of these boxes counts as sea.
// ---------------------------------------------------------------

const OVERRIDE_SEA_BOXES = [
  { name: "suez", lat: [29.6, 31.4], lon: [32.1, 33.5] },
  { name: "panama", lat: [8.4, 10.2], lon: [-80.8, -78.9] },
  { name: "gibraltar", lat: [35.7, 36.3], lon: [-6.4, -4.8] },
  { name: "bosphorus", lat: [40.8, 41.4], lon: [28.5, 29.7] },
  { name: "malacca", lat: [0, 6.2], lon: [95.8, 104.6] },
  { name: "babElMandeb", lat: [11.9, 13.4], lon: [42.2, 44.3] },
  { name: "hormuz", lat: [25, 26.9], lon: [55.5, 57.5] },
];

const CELL = 10; // grid cell size in degrees
const COAST_CELLS = (() => {
  const map = new Map(); // key -> array of ring indices
  for (let i = 0; i < COAST_RINGS.length; i += 1) {
    const ring = COAST_RINGS[i];
    const x0 = Math.floor((ring.minLon + 180) / CELL);
    const x1 = Math.floor((ring.maxLon + 180) / CELL);
    const y0 = Math.floor((ring.minLat + 90) / CELL);
    const y1 = Math.floor((ring.maxLat + 90) / CELL);
    for (let cx = x0; cx <= x1; cx += 1) {
      for (let cy = y0; cy <= y1; cy += 1) {
        const key = `${cx},${cy}`;
        let arr = map.get(key);
        if (!arr) {
          arr = [];
          map.set(key, arr);
        }
        arr.push(i);
      }
    }
  }
  return map;
})();

function ringsNear(lat, lon) {
  const cx = Math.floor((lon + 180) / CELL);
  const cy = Math.floor((lat + 90) / CELL);
  const out = [];
  for (let dx = -1; dx <= 1; dx += 1) {
    for (let dy = -1; dy <= 1; dy += 1) {
      const arr = COAST_CELLS.get(`${cx + dx},${cy + dy}`);
      if (arr) out.push(...arr);
    }
  }
  return out;
}

function isOceanPoint(lat, lon) {
  for (let i = 0; i < OVERRIDE_SEA_BOXES.length; i += 1) {
    if (inBox(lat, lon, OVERRIDE_SEA_BOXES[i])) return true;
  }
  const near = ringsNear(lat, lon);
  for (let i = 0; i < near.length; i += 1) {
    const ring = COAST_RINGS[near[i]];
    if (
      lon < ring.minLon - 0.01 ||
      lon > ring.maxLon + 0.01 ||
      lat < ring.minLat - 0.01 ||
      lat > ring.maxLat + 0.01
    ) {
      continue;
    }
    if (pointInRing(lat, lon, ring)) return false;
  }
  return true;
}

// ---------------------------------------------------------------
// GEOMETRY HELPERS
// ---------------------------------------------------------------

function toRad(v) {
  return (Number(v) * Math.PI) / 180;
}

function fromRad(v) {
  return (v * 180) / Math.PI;
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

function dot3(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function scale3(v, f) {
  return [v[0] * f, v[1] * f, v[2] * f];
}

function norm3(v) {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return scale3(v, 1 / l);
}

function add3(a, b) {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function slerp(a, b, t) {
  const aN = norm3(a);
  const bN = norm3(b);
  const dot = Math.max(-1, Math.min(1, dot3(aN, bN)));
  const omega = Math.acos(dot);
  if (omega < 1e-6) {
    return [
      aN[0] + (bN[0] - aN[0]) * t,
      aN[1] + (bN[1] - aN[1]) * t,
      aN[2] + (bN[2] - aN[2]) * t,
    ];
  }
  const sin = Math.sin(omega);
  const fa = Math.sin((1 - t) * omega) / sin;
  const fb = Math.sin(t * omega) / sin;
  return add3(scale3(aN, fa), scale3(bN, fb));
}

function greatCirclePoints(a, b, segments = 48) {
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
  const va = latLonToVec3(latA, lonA);
  const vb = latLonToVec3(latB, lonB);
  const pts = [];
  for (let i = 0; i <= segments; i += 1) {
    pts.push(vec3ToLatLon(slerp(va, vb, i / segments)));
  }
  return pts;
}

function sampleLeg(a, b, segments = 0) {
  const ptA = [Number(a[0]), Number(a[1])];
  const ptB = [Number(b[0]), Number(b[1])];
  const va = latLonToVec3(ptA[0], ptA[1]);
  const vb = latLonToVec3(ptB[0], ptB[1]);
  const dot = Math.max(-1, Math.min(1, dot3(va, vb)));
  const omegaDeg = fromRad(Math.acos(dot));
  const count =
    segments ||
    Math.round(Math.max(12, Math.min(96, omegaDeg / LANE_DEG_SAMPLE)));
  return greatCirclePoints(ptA, ptB, count);
}

function inBox(lat, lon, box) {
  return (
    lat >= box.lat[0] &&
    lat <= box.lat[1] &&
    lon >= box.lon[0] &&
    lon <= box.lon[1]
  );
}

// ---------------------------------------------------------------
// LAND RUN DETECTION
// ---------------------------------------------------------------

const RUN_THRESHOLD = 3;

function longestLandRun(a, b, segments = 0) {
  const pts = sampleLeg(a, b, segments);
  if (pts.length < 3) return 0;
  let longest = 0;
  let current = 0;
  let skip = 2;
  for (let i = 0; i < pts.length; i += 1) {
    const nearEnd = i < skip || i > pts.length - 1 - skip;
    const isLand = nearEnd ? false : !isOceanPoint(pts[i][0], pts[i][1]);
    if (isLand) {
      current += 1;
      if (current > longest) longest = current;
    } else {
      current = 0;
    }
  }
  return longest;
}

function landCentroidAt(a, b, segments = 28) {
  const pts = sampleLeg(a, b, segments);
  const runs = [];
  let start = -1;
  const skip = 2;
  for (let i = 0; i < pts.length; i += 1) {
    const nearEnd = i < skip || i >= pts.length - skip;
    const isLand = nearEnd ? false : !isOceanPoint(pts[i][0], pts[i][1]);
    if (isLand && start === -1) start = i;
    if (!isLand && start !== -1) {
      runs.push([start, i - 1]);
      start = -1;
    }
  }
  if (start !== -1) runs.push([start, pts.length - 1 - skip]);
  runs.sort((r1, r2) => r2[1] - r2[0] - (r1[1] - r1[0]));
  if (runs.length === 0) return null;
  const [s, e] = runs[0];
  const mid = pts[Math.floor((s + e) / 2)];
  return { lat: mid[0], lon: mid[1], run: Math.max(0, e - s) };
}

// ---------------------------------------------------------------
// OCEAN WAYPOINT POOL
// Names are internal only - never rendered as ports.
// ---------------------------------------------------------------

const OCEAN_POOL = {
  arabianSea: [14, 66],
  gulfAden: [11.8, 48.5],
  somaliCoast: [-2, 45],
  eAfricaE: [-4, 43],
  cSouth: [4.8, 76.6],
  redSea: [19, 38.5],
  suezGate: [30.5, 32.5],
  eastMed: [34.2, 25],
  centMed: [36.5, 14],
  gibraltar: [35.4, -6.3],
  iberiaW: [38.5, -13],
  biscay: [46, -8.5],
  channelW: [49.5, -5],
  channelE: [51.2, -1.5],
  nSea: [53.2, 3.2],
  equatorInd: [-2, 82],
  southernBay: [2.4, 78],
  cenEastCoast: [13.2, 82],
  mannar: [8.2, 79.3],
  malacca: [2.5, 101.7],
  southChina: [12, 112.5],
  philSea: [24.5, 133],
  eastChinaSea: [27, 125],
  taiwanStrait: [23, 120],
  javaSea: [-7, 111],
  sIndOcean: [-33, 102],
  mozambique: [-18.5, 41.5],
  durbanOff: [-31, 34],
  cape: [-37.5, 20.5],
  southAtl: [-24, -21],
  eqAtl: [-2, -21],
  northAtl: [35, -37],
  panamaPac: [6.8, -81.8],
  panamaCanal: [9.1, -79.8],
  caribbean: [15, -72],
  seaboard: [34, -71],
  midPacificW: [27, 168],
  midPacificC: [29.5, -157],
  midPacificE: [35, -142],
  auEast: [-35, 155],
  auSouth: [-40, 140],
  bassStrait: [-40.1, 145],
  nzNE: [-33, 176],
  swAtlS: [-38, -44],
  gulfOman: [25, 59.5],
  japanExit: [31, 141],
};

// ---------------------------------------------------------------
// PORT REGIONS + PORT APPROACHES
// ---------------------------------------------------------------

const PORT_REGIONS = {
  mumbai: "india",
  chennai: "india",
  kochi: "india",
  colombo: "india",
  dubai: "gulf",
  "jebel ali": "gulf",
  mombasa: "eafricaN",
  "dar es salaam": "eafricaN",
  durban: "eafricaS",
  "cape town": "eafricaS",
  "hong kong": "easia",
  shanghai: "easia",
  busan: "easia",
  tokyo: "easia",
  singapore: "easia",
  piraeus: "emed",
  istanbul: "emed",
  valencia: "emed",
  rotterdam: "eneu",
  hamburg: "eneu",
  felixstowe: "eneu",
  london: "eneu",
  "new york": "aeast",
  santos: "samerica",
  "buenos aires": "samerica",
  vancouver: "awest",
  "los angeles": "awest",
  sydney: "oceania",
  melbourne: "oceania",
  auckland: "oceania",
};

// Generic sea exit / entry chain applied right after the origin port
// and right before the destination port (order: closest first).
const PORT_APPROACH = {
  mumbai: ["arabianSea"],
  chennai: ["southernBay"],
  kochi: ["cSouth"],
  colombo: ["southernBay"],
  dubai: ["gulfOman"],
  "jebel ali": ["gulfOman"],
  mombasa: ["eAfricaE"],
  "dar es salaam": ["eAfricaE"],
  durban: ["cape"],
  "cape town": ["cape"],
  "hong kong": ["southChina"],
  shanghai: ["eastChinaSea"],
  busan: ["eastChinaSea"],
  tokyo: ["eastChinaSea"],
  singapore: ["malacca"],
  piraeus: ["eastMed"],
  istanbul: ["eastMed"],
  valencia: ["centMed"],
  rotterdam: ["nSea"],
  hamburg: ["nSea"],
  felixstowe: ["nSea"],
  london: ["nSea"],
  "new york": ["seaboard"],
  santos: ["southAtl"],
  "buenos aires": ["swAtlS"],
  vancouver: ["midPacificE"],
  "los angeles": ["midPacificE"],
  sydney: ["auEast"],
  melbourne: ["auSouth"],
  auckland: ["nzNE"],
};

function normalizeName(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

// ---------------------------------------------------------------
// OCEAN LANES
// Each lane is stored "origin side -> destination side"; laneRails()
// reverses the chain when the pair was queried from the opposite side.
// ---------------------------------------------------------------

const SUEZ_MED = ["somaliCoast", "redSea", "suezGate", "eastMed"];
const SUEZ_MED_ATL = [
  "somaliCoast",
  "redSea",
  "suezGate",
  "eastMed",
  "centMed",
  "gibraltar",
  "biscay",
  "nSea",
];
const SUEZ_ATL = [
  "somaliCoast",
  "redSea",
  "suezGate",
  "eastMed",
  "centMed",
  "gibraltar",
  "northAtl",
];
const IN_O = ["cSouth", "malacca", "southChina", "philSea"];

const LANES = {
  "india|india": ["cSouth"],

  "india|gulf": ["cSouth", "arabianSea", "gulfOman"],
  "india|eafricaN": ["cSouth", "somaliCoast"],
  "india|eafricaS": ["cSouth", "mozambique", "cape"],
  "india|easia": ["cSouth", "malacca", "southChina", "eastChinaSea"],
  "india|emed": ["cSouth"].concat(SUEZ_MED),
  "india|eneu": ["cSouth"].concat(SUEZ_MED_ATL),
  "india|aeast": ["cSouth"].concat(SUEZ_ATL).concat(["seaboard"]),
  "india|samerica": ["cSouth", "somaliCoast", "mozambique", "cape", "southAtl"],
  "india|awest": IN_O.concat(["midPacificW", "midPacificC"]),
  "india|oceania": ["cSouth", "sIndOcean", "auSouth"],

  "gulf|eafricaN": ["somaliCoast"],
  "gulf|eafricaS": ["cSouth", "mozambique", "cape"],
  "gulf|easia": ["cSouth", "malacca", "southChina", "eastChinaSea"],
  "gulf|emed": ["gulfAden", "redSea", "suezGate", "eastMed"],
  "gulf|eneu": ["gulfAden", "redSea", "suezGate", "eastMed", "centMed", "gibraltar", "biscay", "nSea"],
  "gulf|aeast": ["gulfAden", "redSea", "suezGate", "eastMed", "centMed", "gibraltar", "northAtl", "seaboard"],
  "gulf|samerica": ["somaliCoast", "mozambique", "cape", "southAtl"],
  "gulf|awest": ["cSouth", "malacca", "southChina", "philSea", "midPacificW", "midPacificC"],
  "gulf|oceania": ["cSouth", "sIndOcean", "auSouth"],

  "eafricaN|eafricaS": [],
  "eafricaN|easia": ["cSouth", "malacca", "southChina", "eastChinaSea"],
  "eafricaN|emed": ["somaliCoast", "gulfAden", "redSea", "suezGate", "eastMed"],
  "eafricaN|eneu": ["somaliCoast", "gulfAden", "redSea", "suezGate", "eastMed", "centMed", "gibraltar", "biscay", "nSea"],
  "eafricaN|aeast": ["somaliCoast", "gulfAden", "redSea", "suezGate", "eastMed", "centMed", "gibraltar", "northAtl", "seaboard"],
  "eafricaN|samerica": ["somaliCoast", "mozambique", "cape", "southAtl"],
  "eafricaN|awest": ["cSouth", "malacca", "southChina", "philSea", "midPacificW", "midPacificC"],
  "eafricaN|oceania": ["sIndOcean", "auSouth"],

  "eafricaS|easia": ["mozambique", "cSouth", "malacca", "southChina", "eastChinaSea"],
  "eafricaS|emed": ["southAtl", "eqAtl", "northAtl", "gibraltar", "centMed", "eastMed"],
  "eafricaS|eneu": ["southAtl", "eqAtl", "northAtl", "biscay", "nSea"],
  "eafricaS|aeast": ["southAtl", "eqAtl", "northAtl", "seaboard"],
  "eafricaS|samerica": ["southAtl"],
  "eafricaS|awest": ["southAtl", "eqAtl", "caribbean", "panamaCanal", "panamaPac"],
  "eafricaS|oceania": ["sIndOcean", "auSouth"],

  "easia|emed": ["southChina", "malacca", "cSouth"].concat(SUEZ_MED),
  "easia|eneu": ["southChina", "malacca", "cSouth"].concat(SUEZ_MED_ATL),
  "easia|aeast": ["southChina", "malacca", "cSouth"].concat(SUEZ_ATL).concat(["seaboard"]),
  "easia|samerica": ["southChina", "malacca", "cSouth", "somaliCoast", "mozambique", "cape", "southAtl"],
  "easia|awest": ["philSea", "midPacificW", "midPacificC"],
  "easia|oceania": ["philSea", "auEast"],

  "emed|eneu": ["centMed", "gibraltar", "biscay", "nSea"],
  "emed|aeast": ["centMed", "gibraltar", "northAtl", "seaboard"],
  "emed|samerica": ["centMed", "gibraltar", "northAtl", "eqAtl", "southAtl"],
  "emed|awest": ["centMed", "gibraltar", "northAtl", "caribbean", "panamaCanal", "panamaPac"],
  "emed|oceania": ["centMed", "gibraltar", "northAtl", "eqAtl", "southAtl", "cape", "sIndOcean", "auSouth"],

  "eneu|aeast": ["northAtl", "seaboard"],
  "eneu|samerica": ["northAtl", "eqAtl", "southAtl"],
  "eneu|awest": ["biscay", "gibraltar", "northAtl", "caribbean", "panamaCanal", "panamaPac"],
  "eneu|oceania": ["biscay", "gibraltar", "northAtl", "eqAtl", "southAtl", "cape", "sIndOcean", "auSouth"],

  "aeast|samerica": ["northAtl", "eqAtl", "southAtl"],
  "aeast|awest": ["seaboard", "caribbean", "panamaCanal", "panamaPac"],
  "aeast|oceania": ["northAtl", "eqAtl", "southAtl", "cape", "sIndOcean", "auSouth"],

  "samerica|samerica": ["southAtl", "swAtlS"],
  "samerica|awest": ["eqAtl", "caribbean", "panamaCanal", "panamaPac"],
  "samerica|oceania": ["southAtl", "cape", "sIndOcean", "auSouth"],

  "awest|oceania": [],
};

function laneRails(regionA, regionB) {
  if (regionA === regionB) {
    return LANES[`${regionA}|${regionA}`] || [];
  }
  const key = `${regionA}|${regionB}`;
  if (LANES[key]) return LANES[key];
  const rev = `${regionB}|${regionA}`;
  if (LANES[rev]) return [...LANES[rev]].reverse();
  return [];
}

// ---------------------------------------------------------------
// GENERIC DETOUR (sentinel)
// ---------------------------------------------------------------

function genericDetourPoint(centroid) {
  const candidates = [];
  Object.keys(OCEAN_POOL).forEach((poolKey) => {
    const p = OCEAN_POOL[poolKey];
    candidates.push({ lat: p[0], lon: p[1] });
  });
  candidates.push(
    { lat: centroid.lat - 16, lon: centroid.lon },
    { lat: centroid.lat + 16, lon: centroid.lon },
    { lat: centroid.lat, lon: centroid.lon - 30 },
    { lat: centroid.lat, lon: centroid.lon + 30 }
  );

  const a = centroid.pointA || [centroid.lat, centroid.lon];
  const b = centroid.pointB || [centroid.lat, centroid.lon];
  const base = longestLandRun(a, b);

  let best = null;
  let bestTotal = Infinity;
  let bestSpan = Infinity;
  for (let i = 0; i < candidates.length; i += 1) {
    const c = candidates[i];
    const score1 = longestLandRun(a, [c.lat, c.lon]);
    const score2 = longestLandRun([c.lat, c.lon], b);
    const total = score1 + score2;
    const span = Math.abs(c.lat - centroid.lat) + Math.abs(c.lon - centroid.lon);
    if (total < bestTotal || (total === bestTotal && span < bestSpan)) {
      bestTotal = total;
      bestSpan = span;
      best = c;
    }
  }
  if (!best || bestTotal >= base) return null;
  return [best.lat, best.lon];
}

// ---------------------------------------------------------------
// MAIN API
// ---------------------------------------------------------------

function portRegion(portName) {
  const key = normalizeName(portName);
  if (Object.prototype.hasOwnProperty.call(PORT_REGIONS, key)) {
    return PORT_REGIONS[key];
  }
  return null;
}

function buildOceanWaypoints(originPos, destPos, originName, destName) {
  const regO = portRegion(originName);
  const regD = portRegion(destName);

  let chain = [];
  if (regO && regD) {
    chain = laneRails(regO, regD)
      .map((name) => OCEAN_POOL[name])
      .filter(Boolean);
  }

  const outA = (PORT_APPROACH[normalizeName(originName)] || [])
    .map((name) => OCEAN_POOL[name])
    .filter(Boolean);
  const inA = (PORT_APPROACH[normalizeName(destName)] || [])
    .map((name) => OCEAN_POOL[name])
    .filter(Boolean);

  const waypoints = [originPos].concat(outA, chain, inA, [destPos]);

  const cleaned = [];
  for (let i = 0; i < waypoints.length; i += 1) {
    const prev = cleaned[cleaned.length - 1];
    if (
      prev &&
      Math.abs(prev[0] - waypoints[i][0]) < 0.4 &&
      Math.abs(prev[1] - waypoints[i][1]) < 0.4
    ) {
      continue;
    }
    cleaned.push(waypoints[i]);
  }
  return cleaned;
}

function applyDetourPass(waypoints, maxInsert = 4) {
  const fixed = [waypoints[0]];
  let inserted = 0;
  for (let i = 0; i < waypoints.length - 1; i += 1) {
    const a = fixed[fixed.length - 1];
    const b = waypoints[i + 1];
    const run = longestLandRun(a, b);
    if (run >= RUN_THRESHOLD && inserted < maxInsert) {
      const centroid = landCentroidAt(a, b);
      if (centroid) {
        centroid.pointA = a;
        centroid.pointB = b;
        const detour = genericDetourPoint(centroid);
        if (detour) {
          fixed.push(detour);
          inserted += 1;
        }
      }
    }
    fixed.push(b);
  }
  return fixed;
}

function computeRoute(originPos, destPos, originName, destName) {
  if (!originPos || !destPos) return { points: [], waypoints: [] };
  let waypoints = buildOceanWaypoints(originPos, destPos, originName, destName);
  if (waypoints.length < 2) waypoints = [originPos, destPos];

  let passes = [applyDetourPass(waypoints, 4)];
  for (let p = 0; p < 5; p += 1) {
    const next = applyDetourPass(passes[passes.length - 1], 4);
    passes.push(next);
  }
  waypoints = passes[passes.length - 1];

  const points = [];
  for (let i = 0; i < waypoints.length - 1; i += 1) {
    const leg = greatCirclePoints(waypoints[i], waypoints[i + 1], 40);
    if (i > 0 && leg.length > 1) leg.shift();
    points.push(...leg);
  }
  if (points.length < 2) points.push(originPos, destPos);
  return { points, waypoints };
}

export function oceanRoutePoints(originPos, destPos, originName, destName) {
  const { points } = computeRoute(originPos, destPos, originName, destName);
  return points;
}

export function oceanRouteEnabled(originName, destName) {
  return Boolean(portRegion(originName)) && Boolean(portRegion(destName));
}

export function oceanDetectorReport(originPos, destPos, originName, destName) {
  const { waypoints } = computeRoute(originPos, destPos, originName, destName);
  if (waypoints.length < 2) return null;
  let longest = 0;
  let worst = null;
  for (let i = 0; i < waypoints.length - 1; i += 1) {
    const run = longestLandRun(waypoints[i], waypoints[i + 1]);
    if (run > longest) {
      longest = run;
      worst = { a: waypoints[i], b: waypoints[i + 1], run };
    }
  }
  return { longest, worst, waypointCount: waypoints.length };
}

export function isOceanPosition(lat, lon) {
  return isOceanPoint(Number(lat), Number(lon));
}