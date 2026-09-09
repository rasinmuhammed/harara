# Harara site

The product site for the forecast-driven work/rest scheduler: a landing page, a
chat product app at `/app`, and animated result artifacts that render inside
the chat and expand full screen. It talks only to the FastAPI service in
`../api` (through same-origin Next route handlers that proxy server-side, and a
server component fetch for the landing hero). No keys in the browser.

- Next.js 14 App Router, TypeScript
- Tailwind over a CSS-variable token layer (`app/globals.css`, both themes)
- Geist Sans and Geist Mono via `geist/font`
- The hero is React Three Fiber with a GLSL shader, code-split and loaded after
  first paint, with a static poster and full reduced-motion / Save-Data
  fallbacks
- The artifacts (`components/artifact/`) are hand-built with `d3-scale` +
  `d3-shape` and SVG
- Lenis for smooth scroll; scroll reveals and count-ups are CSS + rAF

See `DESIGN.md` for tokens, the WBGT colour ramp with its colour-blindness
check, the motion principles, and the copy rules.

## Run locally

```bash
# 1. the API, from the repo root
pip install -r api/requirements.txt
HARARA_FORECAST_SOURCE=mock uvicorn api.main:app --port 8000
#   drop HARARA_FORECAST_SOURCE for real Open-Meteo forecasts
#   set HARARA_LLM=anthropic (with ANTHROPIC_API_KEY) for a conversational
#   assistant; the default "mock" runs offline with a deterministic summary

# 2. the web app
cd web
pnpm install
echo "API_BASE=http://127.0.0.1:8000" > .env.local
pnpm dev            # http://localhost:3000
```

## Environment

| var | meaning |
|---|---|
| `API_BASE` | base URL of the Harara API. Server-side only. Falls back to `NEXT_PUBLIC_API_BASE`, then `http://127.0.0.1:8000`. |

## Build and deploy (Vercel)

```bash
pnpm build && pnpm start        # local production check
```

Import the repo into Vercel with **root directory `web`**. Set `API_BASE` to
the deployed API origin. After the first deploy, set the API's
`ALLOWED_ORIGINS` to the Vercel URL so CORS admits it.

## Routes

| route | |
|---|---|
| `/` | landing page (server component, fetches the Doha plan for the hero and the scrub chart) |
| `/app` | chat product app |
| `/api/plan`, `/api/parse` | JSON proxies to the API |
| `/api/chat` | SSE proxy, streamed straight through |
