/**
 * Cloudflare Worker entry point.
 *
 * Static files in ./public are served automatically by the ASSETS binding
 * (configured in wrangler.jsonc). This handler only runs for requests that
 * aren't matched by a static asset — use it for API routes, redirects, etc.
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Example API route — extend or replace as needed.
    if (url.pathname === "/api/health") {
      return Response.json({ status: "ok", time: new Date().toISOString() });
    }

    // Everything else falls through to the static landing page.
    return env.ASSETS.fetch(request);
  },
};
