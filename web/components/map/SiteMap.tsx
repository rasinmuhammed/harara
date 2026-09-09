"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion, useSaveData, useTheme } from "@/lib/hooks";
import { buildMapStyle, forecastCell, haversineKm, tokensFromCSS } from "@/lib/mapStyle";
import { LOCATION_PRESETS, DOHA } from "@/lib/types";

type LngLat = { lon: number; lat: number };
type Val = LngLat & { name?: string };

const NUDGE = 0.01;
const FINE = 0.002;

function addCellLayers(map: any, tokens: ReturnType<typeof tokensFromCSS>, v: LngLat) {
  if (!map.getSource("cell")) {
    map.addSource("cell", { type: "geojson", data: forecastCell(v.lat, v.lon) as any });
  }
  if (!map.getLayer("cell-fill")) {
    map.addLayer({
      id: "cell-fill",
      type: "fill",
      source: "cell",
      paint: { "fill-color": tokens.accent, "fill-opacity": 0.07 },
    });
  }
  if (!map.getLayer("cell-line")) {
    map.addLayer({
      id: "cell-line",
      type: "line",
      source: "cell",
      paint: {
        "line-color": tokens.accent,
        "line-width": 1.25,
        "line-opacity": 0.7,
        "line-dasharray": [2, 2],
      },
    });
  }
  if (!map.getLayer("cell-label")) {
    map.addLayer({
      id: "cell-label",
      type: "symbol",
      source: "cell",
      layout: {
        "text-field": "forecast grid cell · about 25 km",
        "text-font": ["Noto Sans Regular"],
        "text-size": 11,
        "text-letter-spacing": 0.04,
        "symbol-placement": "line",
        "text-offset": [0, -0.6],
      },
      paint: {
        "text-color": tokens.label,
        "text-halo-color": tokens.labelHalo,
        "text-halo-width": 1.4,
      },
    });
  }
}

export function SiteMap({
  value,
  onChange,
}: {
  value: Val;
  onChange: (v: Val) => void;
}) {
  const [theme] = useTheme();
  const reduced = usePrefersReducedMotion();
  const save = useSaveData();
  const boxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markerRef = useRef<any>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ label: string; lat: number; lon: number }[]>([]);
  const [cursor, setCursor] = useState(-1);
  const [searching, setSearching] = useState(false);
  const [offscreen, setOffscreen] = useState(false);
  const [live, setLive] = useState("");
  const valueRef = useRef(value);
  valueRef.current = value;

  function place(lat: number, lon: number, name?: string) {
    onChange({ lat: +lat.toFixed(4), lon: +lon.toFixed(4), name });
  }

  // build once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const maplibregl = (await import("maplibre-gl")).default;
        if (cancelled || !boxRef.current) return;
        const tokens = tokensFromCSS(document.documentElement, theme);
        const map = new maplibregl.Map({
          container: boxRef.current,
          style: buildMapStyle(tokens) as any,
          center: [valueRef.current.lon, valueRef.current.lat],
          zoom: 9.5,
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
          maxZoom: 16,
          minZoom: 5,
        });
        mapRef.current = map;
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
        map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-left");
        map.addControl(
          new maplibregl.AttributionControl({
            compact: true,
            customAttribution:
              '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> · <a href="https://openmaptiles.org" target="_blank" rel="noreferrer">OpenMapTiles</a> · © OpenStreetMap',
          }),
          "bottom-right",
        );

        const el = document.createElement("div");
        el.className = "harara-pin";
        const marker = new maplibregl.Marker({ element: el, draggable: true, anchor: "bottom" })
          .setLngLat([valueRef.current.lon, valueRef.current.lat])
          .addTo(map);
        markerRef.current = marker;
        marker.on("dragstart", () => el.classList.add("is-dragging"));
        marker.on("dragend", () => {
          el.classList.remove("is-dragging");
          const p = marker.getLngLat();
          place(p.lat, p.lng);
        });

        map.on("click", (e: any) => {
          marker.setLngLat(e.lngLat);
          if (!reduced) {
            el.classList.remove("drop");
            void el.offsetWidth;
            el.classList.add("drop");
          }
          place(e.lngLat.lat, e.lngLat.lng);
        });
        map.on("mouseenter", () => {
          map.getCanvas().style.cursor = "crosshair";
        });
        const sync = () => {
          const b = map.getBounds();
          setOffscreen(!b.contains([valueRef.current.lon, valueRef.current.lat]));
        };
        map.on("moveend", sync);

        map.on("load", () => {
          map.getCanvas().style.cursor = "crosshair";
          addCellLayers(map, tokens, valueRef.current);
          setStatus("ready");
          sync();
        });
        map.on("error", () => setStatus("error"));
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // sync marker + cell + camera when value changes from outside
  useEffect(() => {
    const map = mapRef.current;
    const marker = markerRef.current;
    if (!map || !marker || status !== "ready") return;
    marker.setLngLat([value.lon, value.lat]);
    map.getSource("cell")?.setData(forecastCell(value.lat, value.lon));
    const opts = { center: [value.lon, value.lat] as [number, number] };
    if (reduced || save) map.jumpTo(opts);
    else map.easeTo({ ...opts, duration: 450, easing: (t: number) => t * (2 - t) });
    setLive(`Site set to ${value.lat.toFixed(3)}, ${value.lon.toFixed(3)}${value.name ? `, ${value.name}` : ""}.`);
  }, [value.lat, value.lon, value.name, status, reduced, save]);

  // restyle on theme change
  useEffect(() => {
    const map = mapRef.current;
    if (!map || status !== "ready") return;
    const tokens = tokensFromCSS(document.documentElement, theme);
    map.setStyle(buildMapStyle(tokens) as any);
    map.once("styledata", () => addCellLayers(map, tokens, valueRef.current));
  }, [theme, status]);

  // keyless Nominatim search, debounced, degrades to nothing
  useEffect(() => {
    if (q.trim().length < 3) {
      setResults([]);
      setCursor(-1);
      return;
    }
    const id = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await fetch(
          `https://nominatim.openstreetmap.org/search?format=json&limit=6&q=${encodeURIComponent(q)}`,
          { headers: { "Accept-Language": "en" } },
        );
        const j = (await r.json()) as any[];
        setResults(j.map((x) => ({ label: x.display_name, lat: +x.lat, lon: +x.lon })));
        setCursor(-1);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 450);
    return () => clearTimeout(id);
  }, [q]);

  function pickResult(r: { lat: number; lon: number }) {
    place(r.lat, r.lon);
    setQ("");
    setResults([]);
    setCursor(-1);
  }

  function onSearchKey(e: React.KeyboardEvent) {
    if (!results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (c + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (c <= 0 ? results.length - 1 : c - 1));
    } else if (e.key === "Enter" && cursor >= 0) {
      e.preventDefault();
      pickResult(results[cursor]);
    } else if (e.key === "Escape") {
      setResults([]);
    }
  }

  function onMapKey(e: React.KeyboardEvent) {
    const step = e.shiftKey ? FINE : NUDGE;
    const moves: Record<string, [number, number]> = {
      ArrowUp: [step, 0],
      ArrowDown: [-step, 0],
      ArrowLeft: [0, -step],
      ArrowRight: [0, step],
    };
    const d = moves[e.key];
    if (!d) return;
    e.preventDefault();
    place(value.lat + d[0], value.lon + d[1]);
  }

  const fromDoha = haversineKm(value, DOHA);
  const inland = value.lon - DOHA.lon < -0.18;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {LOCATION_PRESETS.map((p) => (
          <button
            key={p.name}
            type="button"
            onClick={() => onChange({ lat: p.lat, lon: p.lon, name: p.name })}
            className={`rounded-full border px-2.5 py-1 text-sm transition-colors ${
              value.name === p.name
                ? "border-accent bg-accent-weak text-ink"
                : "border-border text-ink-secondary hover:border-border-strong hover:text-ink"
            }`}
          >
            {p.name}
          </button>
        ))}
      </div>

      <div className="relative">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onSearchKey}
          placeholder="Search for a place, or drop a pin on the map"
          aria-label="Search for a site location"
          role="combobox"
          aria-expanded={results.length > 0}
          aria-controls="site-search-results"
          aria-activedescendant={cursor >= 0 ? `site-result-${cursor}` : undefined}
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-base text-ink outline-none transition-colors focus:border-accent"
        />
        {(results.length > 0 || searching) && (
          <ul
            id="site-search-results"
            role="listbox"
            className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-border-strong bg-bg-raised shadow-1"
          >
            {searching && <li className="px-3 py-2 text-sm text-ink-muted">Searching…</li>}
            {results.map((r, i) => (
              <li key={i} id={`site-result-${i}`} role="option" aria-selected={i === cursor}>
                <button
                  type="button"
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => pickResult(r)}
                  className={`block w-full px-3 py-2 text-left text-sm ${
                    i === cursor ? "bg-surface-2 text-ink" : "text-ink-secondary"
                  } hover:bg-surface-2 hover:text-ink`}
                >
                  {r.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div
        className="relative h-72 overflow-hidden rounded-lg border border-border sm:h-96 focus-visible:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        tabIndex={0}
        role="application"
        aria-label="Map of the site. Arrow keys move the pin, hold Shift for finer steps. Click to place it."
        onKeyDown={onMapKey}
      >
        <div ref={boxRef} className="absolute inset-0" />

        {status === "ready" && (
          <div className="pointer-events-none absolute left-2 top-2 rounded-md border border-border bg-bg-raised/90 px-2 py-1 mono text-micro text-ink-secondary shadow-1 backdrop-blur-sm">
            {value.lat.toFixed(3)}, {value.lon.toFixed(3)}
            <span className="text-ink-muted"> · {fromDoha < 1 ? "Doha centre" : `${fromDoha.toFixed(0)} km from Doha`}</span>
          </div>
        )}

        {status === "ready" && offscreen && (
          <button
            type="button"
            onClick={() => {
              const m = mapRef.current;
              if (!m) return;
              const opts = { center: [value.lon, value.lat] as [number, number] };
              reduced || save ? m.jumpTo(opts) : m.easeTo({ ...opts, duration: 450 });
            }}
            className="absolute right-2 bottom-16 rounded-md border border-border-strong bg-bg-raised px-2.5 py-1.5 text-sm text-ink shadow-1 hover:border-accent"
          >
            Back to the pin
          </button>
        )}

        {status === "loading" && (
          <div className="absolute inset-0 grid place-items-center bg-surface text-sm text-ink-muted">
            Loading the map…
          </div>
        )}
        {status === "error" && (
          <div className="absolute inset-0 grid place-items-center bg-surface p-4 text-center text-sm text-ink-secondary">
            The map could not load. Use a preset above or type coordinates below.
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
        <label className="flex items-center gap-1.5">
          <span className="mono text-micro uppercase">lat</span>
          <input
            type="number"
            step="0.001"
            value={value.lat}
            onChange={(e) => onChange({ lat: +e.target.value, lon: value.lon, name: undefined })}
            className="w-24 rounded border border-border bg-surface px-2 py-1 text-ink"
            aria-label="Latitude"
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="mono text-micro uppercase">lon</span>
          <input
            type="number"
            step="0.001"
            value={value.lon}
            onChange={(e) => onChange({ lat: value.lat, lon: +e.target.value, name: undefined })}
            className="w-24 rounded border border-border bg-surface px-2 py-1 text-ink"
            aria-label="Longitude"
          />
        </label>
        <span className="text-ink-muted">No sign-in. Nothing about the site is stored.</span>
      </div>

      <p className="text-sm text-ink-muted">
        The dashed square is the forecast grid cell your pin falls in. The forecast
        covers this area, about 25 km across. It is not specific to one street or
        one trench.
        {inland ? " Inland tends to read a little cooler on this index because the air is drier." : ""}
      </p>

      <p aria-live="polite" className="sr-only">{live}</p>
    </div>
  );
}
