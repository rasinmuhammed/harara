// A compact, token-driven MapLibre style over OpenFreeMap's open vector tiles
// (no key). Near-monochrome, one cool accent for water, thin roads, sparse
// labels: an instrument, not a tourist map. Colours are passed in from the
// resolved design tokens so the map matches the current theme exactly.

type Hex = string;

export interface MapTokens {
  land: Hex;
  landAlt: Hex;
  water: Hex;
  road: Hex;
  roadMajor: Hex;
  building: Hex;
  boundary: Hex;
  label: Hex;
  labelHalo: Hex;
  accent: Hex;
}

const SRC = "https://tiles.openfreemap.org/planet";
const GLYPHS = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf";

export function buildMapStyle(t: MapTokens) {
  return {
    version: 8 as const,
    glyphs: GLYPHS,
    sources: {
      ofm: { type: "vector" as const, url: SRC },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": t.land } },
      {
        id: "landuse",
        type: "fill",
        source: "ofm",
        "source-layer": "landuse",
        filter: ["in", "class", "residential", "industrial", "commercial"],
        paint: { "fill-color": t.landAlt, "fill-opacity": 0.5 },
      },
      {
        id: "park",
        type: "fill",
        source: "ofm",
        "source-layer": "landcover",
        paint: { "fill-color": t.landAlt, "fill-opacity": 0.35 },
      },
      {
        id: "water",
        type: "fill",
        source: "ofm",
        "source-layer": "water",
        paint: { "fill-color": t.water },
      },
      {
        id: "building",
        type: "fill",
        source: "ofm",
        "source-layer": "building",
        minzoom: 12,
        paint: {
          "fill-color": t.building,
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 12, 0, 14, 0.5],
        },
      },
      {
        id: "road-minor",
        type: "line",
        source: "ofm",
        "source-layer": "transportation",
        filter: ["in", "class", "minor", "service", "street"],
        minzoom: 12,
        paint: {
          "line-color": t.road,
          "line-width": ["interpolate", ["linear"], ["zoom"], 12, 0.4, 18, 3],
        },
      },
      {
        id: "road-major",
        type: "line",
        source: "ofm",
        "source-layer": "transportation",
        filter: ["in", "class", "primary", "secondary", "trunk", "motorway"],
        paint: {
          "line-color": t.roadMajor,
          "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 16, 4],
        },
      },
      {
        id: "boundary",
        type: "line",
        source: "ofm",
        "source-layer": "boundary",
        filter: ["<=", "admin_level", 2],
        paint: { "line-color": t.boundary, "line-width": 0.8, "line-dasharray": [2, 2] },
      },
      {
        id: "place-major",
        type: "symbol",
        source: "ofm",
        "source-layer": "place",
        filter: ["in", "class", "city", "town"],
        layout: {
          "text-field": ["get", "name"],
          "text-font": ["Noto Sans Regular"],
          "text-size": ["interpolate", ["linear"], ["zoom"], 6, 11, 12, 14],
          "text-transform": "uppercase",
          "text-letter-spacing": 0.08,
          "text-max-width": 7,
        },
        paint: {
          "text-color": t.label,
          "text-halo-color": t.labelHalo,
          "text-halo-width": 1.2,
        },
      },
    ],
  };
}

export function tokensFromCSS(el: HTMLElement, theme: "light" | "dark"): MapTokens {
  const c = getComputedStyle(el);
  const g = (n: string) => c.getPropertyValue(n).trim();
  return {
    land: g("--bg"),
    landAlt: g("--surface-2"),
    water: theme === "dark" ? "#132a38" : "#dfe8ec",
    road: g("--border"),
    roadMajor: g("--border-strong"),
    building: g("--surface-2"),
    boundary: g("--border-strong"),
    label: g("--text-secondary"),
    labelHalo: g("--bg"),
    accent: g("--accent") || "#e0a343",
  };
}

/** Great-circle distance in km (small-angle safe enough for a city). */
export function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const la1 = (a.lat * Math.PI) / 180;
  const la2 = (b.lat * Math.PI) / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export const FORECAST_CELL_DEG = 0.25;

export function forecastCell(lat: number, lon: number) {
  const la = Math.floor(lat / FORECAST_CELL_DEG) * FORECAST_CELL_DEG;
  const lo = Math.floor(lon / FORECAST_CELL_DEG) * FORECAST_CELL_DEG;
  const d = FORECAST_CELL_DEG;
  return {
    type: "Feature" as const,
    geometry: {
      type: "Polygon" as const,
      coordinates: [[
        [lo, la], [lo + d, la], [lo + d, la + d], [lo, la + d], [lo, la],
      ]],
    },
    properties: {},
  };
}
