import { ImageResponse } from "next/og";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Harara. Decide when to work by the forecast.";
export default function OG() {
  const pts = [[0,80],[12,72],[24,58],[36,42],[48,34],[60,32],[72,36],[84,48],[100,66]];
  const d = pts.map((p,i) => `${i?"L":"M"}${p[0]*10},${p[1]*3.6}`).join(" ");
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", background: "#0b0b0c", color: "#ececee", padding: 72, fontFamily: "sans-serif" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ fontSize: 30, color: "#e9963e", letterSpacing: 2 }}>HARARA</div>
          <div style={{ fontSize: 58, lineHeight: 1.05, maxWidth: 880, fontWeight: 600 }}>
            Decide when to work by the forecast, not the clock.
          </div>
          <div style={{ fontSize: 26, color: "#a1a1a8", maxWidth: 820 }}>
            Same work-hours, lower peak and tail heat load than the fixed 10:00 to 15:30 calendar ban.
          </div>
        </div>
        <div style={{ display: "flex", position: "relative" }}>
          <svg width="1056" height="330" viewBox="0 0 1000 330">
            <defs>
              <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#9e4535" />
                <stop offset="0.45" stopColor="#c98a3a" />
                <stop offset="0.6" stopColor="#87b9ba" />
                <stop offset="1" stopColor="#3c6e8e" />
              </linearGradient>
            </defs>
            <path d={`${d} L1000,330 L0,330 Z`} fill="url(#g)" opacity="0.5" />
            <path d={d} fill="none" stroke="#ececee" strokeWidth="4" />
            <line x1="0" y1="150" x2="1000" y2="150" stroke="#ececee" strokeWidth="2" strokeDasharray="4 6" />
          </svg>
          <div style={{ position: "absolute", right: 2, top: 118, fontSize: 20, color: "#ececee" }}>32.1 C stop-work</div>
        </div>
      </div>
    ),
    { ...size },
  );
}
