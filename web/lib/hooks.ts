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

/**
 * Count a number up from 0 to `target` once, on mount / when `target` changes.
 * Instant under reduced-motion.
 */
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
    const from = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + (target - from) * eased);
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
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const read = (): "light" | "dark" => {
      const attr = document.documentElement.getAttribute("data-theme");
      if (attr === "dark" || attr === "light") return attr;
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    };
    setTheme(read());
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
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
