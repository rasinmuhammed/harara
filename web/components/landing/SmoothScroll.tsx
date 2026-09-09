"use client";
import { useEffect } from "react";
import { usePrefersReducedMotion, useSaveData } from "@/lib/hooks";

export function SmoothScroll() {
  const reduced = usePrefersReducedMotion();
  const save = useSaveData();
  useEffect(() => {
    if (reduced || save) return;
    let lenis: any;
    let raf = 0;
    let cancelled = false;
    import("lenis").then(({ default: Lenis }) => {
      if (cancelled) return;
      lenis = new Lenis({ duration: 1.1, smoothWheel: true });
      const loop = (t: number) => {
        lenis.raf(t);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      lenis?.destroy();
    };
  }, [reduced, save]);
  return null;
}
