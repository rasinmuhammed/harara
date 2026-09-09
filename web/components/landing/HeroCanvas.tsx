"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { PlanResponse } from "@/lib/types";

const FRAG = `
precision highp float;
varying vec2 vUv;
uniform float uTime;
uniform float uWbgt[16];
uniform vec3 uCool;
uniform vec3 uWarm;
uniform vec3 uHot;
uniform vec3 uBg;

float wbgtAt(float x) {
  float f = x * 15.0;
  int i = int(floor(f));
  float t = fract(f);
  float a = uWbgt[i];
  float b = uWbgt[i + 1 >= 16 ? 15 : i + 1];
  return mix(a, b, smoothstep(0.0, 1.0, t));
}

void main() {
  vec2 uv = vUv;
  float w = wbgtAt(uv.x);                 // 0..1 normalised WBGT for this hour
  float drift = 0.06 * sin(uTime * 0.15 + uv.x * 6.2831);
  float field = uv.y + drift - (0.15 + w * 0.7);

  // isotherm bands
  float bands = abs(fract(field * 7.0 + uTime * 0.02) - 0.5);
  float line = smoothstep(0.05, 0.0, bands) * (0.18 + w * 0.28);

  // hot ridge where WBGT crosses the stop-work level (~0.62 normalised)
  float ridge = smoothstep(0.02, 0.0, abs(w - 0.62)) * smoothstep(0.35, 0.0, abs(field)) * 0.4;

  vec3 base = mix(uCool, uWarm, smoothstep(0.25, 0.62, w));
  base = mix(base, uHot, smoothstep(0.62, 1.0, w));
  vec3 col = mix(uBg, base, 0.06 + line * 0.7);
  col += ridge * uHot * 0.45;

  // vignette
  float v = smoothstep(1.15, 0.2, length(uv - 0.5));
  gl_FragColor = vec4(mix(uBg, col, v), 1.0);
}
`;

const VERT = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

function Field({ wbgt, theme }: { wbgt: number[]; theme: "light" | "dark" }) {
  const mat = useRef<THREE.ShaderMaterial>(null);
  const uniforms = useMemo(() => {
    const cool = new THREE.Color(theme === "dark" ? "#2a4f68" : "#3a6d8c");
    const warm = new THREE.Color(theme === "dark" ? "#b9853f" : "#c98a3a");
    const hot = new THREE.Color(theme === "dark" ? "#9e4535" : "#b24a3c");
    const bg = new THREE.Color(theme === "dark" ? "#0b0b0c" : "#fbfaf8");
    const arr = new Array(16).fill(0).map((_, i) => wbgt[i] ?? wbgt[wbgt.length - 1] ?? 0.4);
    return {
      uTime: { value: 0 },
      uWbgt: { value: arr },
      uCool: { value: cool },
      uWarm: { value: warm },
      uHot: { value: hot },
      uBg: { value: bg },
    };
  }, [wbgt, theme]);

  useFrame((_, dt) => {
    if (mat.current) mat.current.uniforms.uTime.value += dt;
  });

  return (
    <mesh>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial ref={mat} vertexShader={VERT} fragmentShader={FRAG} uniforms={uniforms} />
    </mesh>
  );
}

export default function HeroCanvas({
  plan,
  theme,
  active,
}: {
  plan: PlanResponse | null;
  theme: "light" | "dark";
  active: boolean;
}) {
  const wbgt = useMemo(() => {
    const src = plan?.hours ?? [];
    if (!src.length) return new Array(16).fill(0.45);
    const vals = src.map((h) => h.wbgt_c);
    const lo = 24;
    const hi = 40;
    const norm = vals.map((v) => Math.max(0, Math.min(1, (v - lo) / (hi - lo))));
    // resample to 16 points
    const out: number[] = [];
    for (let i = 0; i < 16; i++) {
      const f = (i / 15) * (norm.length - 1);
      const a = Math.floor(f);
      out.push(norm[a] + (norm[Math.min(a + 1, norm.length - 1)] - norm[a]) * (f - a));
    }
    return out;
  }, [plan]);

  return (
    <Canvas
      className="h-full w-full"
      dpr={[1, 1.5]}
      frameloop={active ? "always" : "never"}
      gl={{ antialias: false, powerPreference: "low-power" }}
      style={{ pointerEvents: "none" }}
    >
      <Field wbgt={wbgt} theme={theme} />
    </Canvas>
  );
}
