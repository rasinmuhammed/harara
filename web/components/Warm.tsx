"use client";

import { useEffect } from "react";
import { warmBackend } from "@/lib/warm";

// Renders nothing. Kicks the free-tier backend awake on first paint so it is
// ready by the time a visitor opens the planner or scrolls to a live example.
export function Warm() {
  useEffect(() => {
    warmBackend();
  }, []);
  return null;
}
