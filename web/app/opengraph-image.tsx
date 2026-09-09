import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt =
  "Harara — reshape the working day around the WBGT forecast";

export default function OG() {
  const pts = [
    [0, 78], [10, 74], [20, 66], [30, 54], [40, 40], [50, 32],
    [60, 30], [70, 33], [80, 42], [90, 58], [100, 74],
  ];
  const curve = pts.map((p, i) => `${i ? "L" : "M"}${p[0] * 10},${p[1] * 4}`).join(" ");

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#15120e",
          color: "#f4eee3",
          padding: 72,
          fontFamily: "serif",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ fontSize: 34, color: "#e0a343", letterSpacing: 1 }}>
            HARARA
          </div>
          <div style={{ fontSize: 62, lineHeight: 1.05, maxWidth: 900 }}>
            Plan the day around the forecast
          </div>
          <div
            style={{
              fontSize: 28,
              color: "#b6ac99",
              maxWidth: 880,
              fontFamily: "sans-serif",
            }}
          >
            Same work-hours, materially lower peak and tail heat load than
            Qatar&apos;s fixed 10:00–15:30 calendar ban.
          </div>
        </div>

        <div style={{ display: "flex", position: "relative" }}>
          <svg width="1056" height="360" viewBox="0 0 1000 360">
            <defs>
              <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#a03e37" />
                <stop offset="0.42" stopColor="#f2c066" />
                <stop offset="0.55" stopColor="#c4cdbd" />
                <stop offset="1" stopColor="#3c6e8e" />
              </linearGradient>
            </defs>
            <path d={`${curve} L1000,360 L0,360 Z`} fill="url(#g)" opacity="0.55" />
            <path d={curve} fill="none" stroke="#f4eee3" strokeWidth="4" />
            <line
              x1="0"
              y1="150"
              x2="1000"
              y2="150"
              stroke="#f4eee3"
              strokeWidth="2"
              strokeDasharray="4 6"
            />
          </svg>
          <div
            style={{
              position: "absolute",
              right: 4,
              top: 118,
              fontSize: 22,
              color: "#f4eee3",
              fontFamily: "sans-serif",
            }}
          >
            32.1 °C stop-work
          </div>
        </div>
      </div>
    ),
    { ...size },
  );
}
