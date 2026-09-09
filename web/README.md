# Harara web

Single-screen Next.js app for the forecast-driven work/rest scheduler. It talks
only to the FastAPI service in `../api` (through same-origin route handlers that
proxy server-side); there are no keys or secrets in the browser.

- Next.js 14 (App Router, TypeScript, RSC shell + one client island)
- Tailwind over a CSS-variable token layer (`app/globals.css`, both themes)
- Radix primitives for the accessible controls; the hero chart is hand-built
  with `d3-scale` + `d3-shape` and SVG
- CSS-only motion (no animation library), all gated by `prefers-reduced-motion`

See `DESIGN.md` for the token system, the WBGT colour ramp and its
colour-vision-deficiency rationale, and the four non-happy UI states.

## Run locally

```bash
# 1. start the API (from the repo root)
pip install -r api/requirements.txt
HARARA_FORECAST_SOURCE=mock uvicorn api.main:app --port 8000

# 2. start the web app
cd web
pnpm install
echo "API_BASE=http://127.0.0.1:8000" > .env.local
pnpm dev            # http://localhost:3000
```

`HARARA_FORECAST_SOURCE=mock` serves a deterministic synthetic day so you can
work offline; drop it for real Open-Meteo forecasts. Add `?demo=1` to the URL
to auto-run a Doha plan on load.

## Environment

| var | meaning |
|---|---|
| `API_BASE` | base URL of the Harara API. Server-side only. Falls back to `NEXT_PUBLIC_API_BASE`, then `http://127.0.0.1:8000`. |

## Build & deploy (Vercel)

```bash
pnpm build && pnpm start        # local production check
```

Import the repo into Vercel with **root directory `web`**. Set `API_BASE` to
the deployed API origin (e.g. the Render URL). `vercel.json` pins the framework
and pnpm. After the first deploy, set the API's `ALLOWED_ORIGINS` to the Vercel
URL so CORS admits it.

## Scripts

| script | |
|---|---|
| `pnpm dev` | dev server |
| `pnpm build` / `pnpm start` | production build / serve |
| `pnpm typecheck` | `tsc --noEmit` |
