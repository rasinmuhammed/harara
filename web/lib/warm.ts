// The demo backend runs on Render's free tier and spins down after about
// 15 minutes of no traffic. The next request then pays a cold start of roughly
// 30 to 60 seconds. warmBackend() fires a health ping so the service starts
// waking while the visitor is still reading, before they ask for a plan.

let fired = false;

export function warmBackend(): void {
  if (fired || typeof window === "undefined") return;
  fired = true;
  // fire and forget; the route handler swallows timeouts
  fetch("/api/health", { cache: "no-store" }).catch(() => {});
}
