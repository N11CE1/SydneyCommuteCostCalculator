# Sydney Commute Cost Calculator

A personal, **map-first rental workspace** for Sydney. The first milestone lets you shortlist places, not calculate journeys: add a work destination and rentals, edit their rent/details, and keep a local workspace.

Built with Svelte 5, TypeScript, Vite and MapLibre, served by a small Go HTTP server. See [DesignDoc.md](DesignDoc.md) for the agreed architecture and roadmap.

## Run locally

Requirements: Node.js 24 LTS (22.12+ and 26+ are also supported), npm, and Go 1.24+ for the backend.

```sh
npm --prefix web ci
cp web/.env.example web/.env.local
```

Set `VITE_MAPTILER_KEY` in the **ignored** `web/.env.local` to your own origin-restricted browser key. Do not put keys in commits, Jira or PRs. The app remains usable through coordinate entry without a key, but the basemap requires one. [Full provider setup, pricing/attribution and privacy notes](docs/frontend.md#maptiler-setup).

Start the frontend:

```sh
npm --prefix web run dev -- --host 127.0.0.1
```

Open the local URL Vite prints (normally `http://127.0.0.1:5173`). For backend development, run this in another terminal from the repository root:

```sh
go run ./cmd/server -addr 127.0.0.1:8080
```

Vite proxies `/api` to Go; `GET /api/health` is currently the only API endpoint. This milestone does not require the API for rental editing.

### One-process production-shaped preview

```sh
npm --prefix web run build
go run ./cmd/server -addr 127.0.0.1:8080
```

Open `http://127.0.0.1:8080`. Go serves `web/dist` by default. Vite embeds the browser key at **build time**; changing it requires a rebuild, not just restarting Go. Keep `web/dist`, dependencies and local configuration out of Git. This is a local preview, not production hosting/security configuration.

## What to try

1. **Set work destination**, click the map, then save a label. Coordinate entry is an alternative.
2. **Add a rental**, pick a point, and enter its label, weekly AUD rent and optional listing link.
3. Select rentals using the map markers or sidebar. Edit a rental or remove it after confirmation.
4. Reload to restore the local workspace. **Export JSON** for a backup; **Import JSON** validates first and asks before replacing your workspace.

No TfNSW connection, fare estimate, commute time or automatic address search is present. The UI labels those later milestones explicitly; it does not draw fictional journey lines. Workspaces and exports contain locations—keep backups private.

## Checks

```sh
npm --prefix web run format:check
npm --prefix web run check
npm --prefix web test
npm --prefix web run build
npm --prefix web exec -- playwright install chromium
npm --prefix web run test:e2e
go test ./...
```

Browser checks start/stop their own local servers, run real MapLibre with local style fixtures, and do not use your MapTiler credentials or quota. See [frontend architecture and test details](docs/frontend.md). Go and browser build caches use their normal user/OS locations, not a repository `.cache/` folder.

Work is tracked in [Jira SCCC](https://tomhickman.atlassian.net/jira/software/projects/SCCC/boards). Delivery conventions live in [AGENTS.md](AGENTS.md); PR/Jira automation is documented in [docs/jira-automation.md](docs/jira-automation.md).
