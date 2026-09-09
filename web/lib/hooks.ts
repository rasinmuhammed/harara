"use client";

import { useEffect, useRef, useState } from "react";

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export function useSaveData(): boolean {
  const [save, setSave] = useState(false);
  useEffect(() => {
    const c = (navigator as any).connection;
    if (c?.saveData) setSave(true);
  }, []);
  return save;
}

export function useCountUp(target: number, durationMs = 900): number {
  const reduced = usePrefersReducedMotion();
  const [value, setValue] = useState(reduced ? target : 0);
  const raf = useRef<number>();
  useEffect(() => {
    if (reduced) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      setValue(target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf.current = requestAnimationFrame(tick);
      else setValue(target);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [target, durationMs, reduced]);
  return value;
}

export function useTheme(): ["light" | "dark", () => void] {
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  useEffect(() => {
    const read = (): "light" | "dark" => {
      const attr = document.documentElement.getAttribute("data-theme");
      if (attr === "dark" || attr === "light") return attr;
      return window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
    };
    setTheme(read());
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const on = () => {
      if (!document.documentElement.getAttribute("data-theme")) setTheme(read());
    };
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("harara-theme", next);
    } catch {}
    setTheme(next);
  };
  return [theme, toggle];
}

/** True after first paint plus one idle callback, so heavy-but-non-critical
 *  UI (the motif canvas) stays off the critical path. */
export function useDeferredMount(): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const go = () => !cancelled && setReady(true);
    const idle = (window as any).requestIdleCallback || ((f: () => void) => setTimeout(f, 200));
    const t = requestAnimationFrame(() => idle(go));
    return () => {
      cancelled = true;
      cancelAnimationFrame(t);
    };
  }, []);
  return ready;
}

export function useInView<T extends Element>(
  opts: IntersectionObserverInit = { rootMargin: "0px 0px -12% 0px" },
): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        setInView(true);
        io.disconnect();
      }
    }, opts);
    io.observe(el);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return [ref, inView];
}

import type { PlanResponse } from "./types";
import { DOHA } from "./types";

/** Use the server-provided plan, or fetch Doha-today client-side if it was
 *  unavailable at render time (e.g. the API was down at build). */
export function useDohaPlan(initial: PlanResponse | null): PlanResponse | null {
  const [plan, setPlan] = useState<PlanResponse | null>(initial);
  useEffect(() => {
    if (plan) return;
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + 1);
    fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: DOHA.lat,
        lon: DOHA.lon,
        date: d.toISOString().slice(0, 10),
        required_work_hours: 8,
        workload_class: "moderate",
        acclimatised: true,
      }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j && setPlan(j))
      .catch(() => {});
  }, [plan]);
  return plan;
}
