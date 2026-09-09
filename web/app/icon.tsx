import { ImageResponse } from "next/og";
import { HeatFieldSVG } from "@/components/visual/HeatFieldSVG";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", background: "#0b0b0c" }}>
        <HeatFieldSVG theme="dark" width={32} height={32} bands={6} />
      </div>
    ),
    { ...size },
  );
}
