import { ImageResponse } from "next/og";
import { HeatFieldSVG } from "@/components/visual/HeatFieldSVG";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Harara. The rule sets the limit. The forecast sets the plan.";

export default function OG() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#0b0b0c",
          color: "#ececee",
          padding: 76,
          fontFamily: "sans-serif",
          position: "relative",
        }}
      >
        <div style={{ position: "absolute", inset: 0, display: "flex" }}>
          <HeatFieldSVG theme="dark" width={1200} height={630} bands={16} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18, position: "relative" }}>
          <div style={{ fontSize: 28, color: "#e9963e", letterSpacing: 3, fontWeight: 600 }}>
            HARARA
          </div>
          <div style={{ fontSize: 62, lineHeight: 1.04, maxWidth: 900, fontWeight: 600 }}>
            The rule sets the limit. The forecast sets the plan.
          </div>
        </div>
        <div style={{ fontSize: 26, color: "#d6d6db", maxWidth: 860, position: "relative" }}>
          Plans the working day inside Qatar&apos;s heat regulation, from the daily
          forecast, so the crew spends less time in the worst of the heat at the
          same output.
        </div>
      </div>
    ),
    { ...size },
  );
}
