import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "flex-end",
          background: "#15120e",
          padding: 4,
        }}
      >
        <svg width="24" height="24" viewBox="0 0 24 24">
          <path
            d="M2 18C6 17 8 8 12 8s5 6 10 2"
            fill="none"
            stroke="#e0a343"
            strokeWidth="2.4"
            strokeLinecap="round"
          />
          <line x1="2" y1="12" x2="22" y2="12" stroke="#f4eee3" strokeWidth="1.4" strokeDasharray="2 2" />
        </svg>
      </div>
    ),
    { ...size },
  );
}
