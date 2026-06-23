# Cloudflare integration

This project deploys as a **Cloudflare Worker with Static Assets**: the Worker
(`src/index.js`) can run code (API routes, redirects, etc.), and the built
landing page in `public/` is served straight from Cloudflare's edge.

## One-time setup

1. **Create an API token** — Cloudflare dashboard → My Profile → API Tokens →
   Create Token. Permissions needed:
   - `Account → Workers Scripts → Edit`
   - `Account → Cloudflare Pages → Edit` (if using `pages:deploy`)
   - `Account → Workers R2 Storage → Edit` (only if you add R2)
2. **Provide credentials.** Either:
   - **Recommended (web sessions):** add `CLOUDFLARE_API_TOKEN` and
     `CLOUDFLARE_ACCOUNT_ID` as environment secrets in the Claude Code
     environment settings, then restart the session, **or**
   - **Local:** create a `.dev.vars` / shell env with the same vars
     (already gitignored).

Verify with: `npm run whoami`

## Commands

| Command | What it does |
| --- | --- |
| `npm run build` | Assembles `public/index.html` from `kartra-full-page.html` |
| `npm run dev` | Local dev server (build + `wrangler dev`) |
| `npm run deploy` | Deploy the Worker + assets (`wrangler deploy`) |
| `npm run tail` | Live-stream production logs |
| `npm run pages:deploy` | Alternative: deploy `public/` to Cloudflare Pages |

## Notes

- Source of truth for the page is `kartra-full-page.html`; the build copies it
  to `public/index.html`. `public/` is gitignored (regenerated on build).
- Add bindings (R2, KV, D1, secrets) in `wrangler.jsonc`.
- Worker secrets (not build-time): `wrangler secret put <NAME>`.
