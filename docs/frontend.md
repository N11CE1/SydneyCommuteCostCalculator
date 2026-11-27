# Map-first rental prototype (SCCC-6)

Tracking: [SCCC-6](https://tomhickman.atlassian.net/browse/SCCC-6). This delivers milestone 1 from `DesignDoc.md`, not the complete commute calculator. Run/build commands are in the [README](../README.md).

## Boundaries and learning guide

- `web/src/App.svelte`: application state, sidebar/editor, selection and explicit save/import actions. Svelte 5 `$state` owns the workspace; `$derived` resolves the current selection. Changes are committed only after validation, not persisted via an effect that might overwrite a corrupt save on startup.
- `web/src/lib/MapView.svelte`: all MapLibre map, marker, camera and lifecycle objects. It accepts plain locations/selected IDs and emits coordinate/selection events. Markers use DOM `textContent`, not HTML from user inputs. Map objects never enter saved scenarios.
- `web/src/lib/scenario.ts`: provider-independent model, validation, money input parsing and JSON serialization. Rent is stored as integer AUD cents; it is not a complete financial-calculation module.
- `web/src/lib/persistence.ts`: browser-storage boundary with explicit failures and recovery. No new backend database or API is needed for this milestone.
- `web/src/style.css`: responsive map-first layout using system fonts; no external font service or CSS framework.

The scenario uses collections of people, destinations and candidates so later UI expansion does not require replacing the whole model. Version 1 deliberately accepts exactly one traveller and at most one destination; changing those supported limits or the schema requires reviewing validation and version migration. Future TfNSW requests and financial calculations belong behind the boundaries in `DesignDoc.md`, not in the map component.

MapLibre's ESM worker is imported with Vite's `?worker&url` and registered with `setWorkerUrl`; this keeps its URL valid in both development and the Go-served build. The browser fixture includes GeoJSON so readiness checks exercise actual worker parsing, not just a background layer.

MapLibre is the renderer; MapTiler supplies styles/tiles. Switching tile supplier is a map-integration/configuration change with fresh terms/attribution checks. Switching SDKs is not a string replacement, but the scenario and editor do not depend on the current SDK.

## MapTiler setup

Published provider guidance was rechecked during implementation on 2026-11-27. This is not verification of the owner's actual account configuration, quota or restricted-key behavior.

1. Create/use a [MapTiler Cloud Free account](https://www.maptiler.com/cloud/pricing/). The published plan is suitable for personal, non-commercial, testing and prototype use and does not need a credit card. Do not silently upgrade to a paid plan.
2. Copy `web/.env.example` to `web/.env.local`, then set `VITE_MAPTILER_KEY`. The key is visible in the browser by design; never use a server/admin credential here. The file is ignored. Never paste a real key into source, screenshots, PRs or tickets.
3. In the key's **Allowed HTTP origins**, allow the development host you use: `127.0.0.1` and/or `localhost`, **without protocol or port**, per MapTiler's current guidance. They are distinct hosts. Do not add `?` (unknown origins) or a global wildcard.
4. Restart Vite after changing the local environment. For the Go-served build, rebuild the frontend. A missing key shows setup instructions instead of attempting provider calls. Incorrect/restricted keys, unavailable network/tiles and quota failures show a generic actionable warning without displaying the key.
5. Before any public deployment, remove localhost rules and restrict the key to the actual domain. Localhost restrictions are not strong protection: anyone can run a local server. Free currently includes one API key; do not assume separate development/production keys are available on that plan. Recheck available options and account limits before hosting.

### Usage and attribution

The published Free plan currently includes **100,000 API requests/month**, **5,000 map sessions/month**, and **1,000 search sessions/month**. These are different allowances. This app uses **MapLibre directly**, not MapTiler SDK, so map usage is counted **per request**, not per map session. A vector tile counts as one request; panning and zooming can load more. Do not estimate quota using the session allowance for this implementation.

The published Free service pauses on quota exhaustion until the next period/upgrade; paid Flex service can incur overage charges. No billing configuration is changed by this app. Monitor the account Analytics page and recheck provider terms before commercial use or a public launch. No geocoder or autocomplete is connected, and no public OSM tile/Nominatim server is used as a fallback.

MapLibre's attribution control is visible (not collapsed) with MapTiler and OpenStreetMap copyright links; source-supplied credits remain enabled. The free-plan MapTiler logo is shown as a linked official image at the map's lower-left edge. Do not hide the logo/credits, including on mobile.

Sources:

- [MapTiler pricing and quota behavior](https://www.maptiler.com/cloud/pricing/)
- [Sessions versus requests](https://docs.maptiler.com/guides/account/sessions-vs-requests/)
- [API key and allowed-origin setup](https://docs.maptiler.com/guides/developer/credentials/api-key/)
- [Required attribution and logo](https://docs.maptiler.com/guides/map-design/attribution/add-attribution/)

## Storage, imports and privacy

- Save key: `sccc.scenario.v1` in browser `localStorage`. Schema fields are `schemaVersion`, `people`, `destinations`, and `candidates`; locations are ordinary latitude/longitude pairs. Selection and unfinished editor inputs are session UI state, not part of the export.
- Saves apply after successful edits/removals/imports. Reload restores saved data. Browser origins are separate: Vite and the Go-served preview do not share storage. Transfer between them using JSON.
- Imports are limited to 1 MiB and 100 rentals, with strict version/field/ID uniqueness, finite coordinate ranges, integer rent cents, label limits and safe HTTP(S) listing links. Unknown/provider fields and unsupported versions are rejected, not silently dropped. HTML labels are rendered as text. A valid import still requires confirmation before replacement; an invalid/cancelled import leaves the workspace and save untouched.
- Unreadable saves are **not overwritten automatically**. The UI offers the original raw save for download and requires explicit confirmation before replacing it. A blocked/full storage implementation leaves the in-memory editor and export available, with a warning instead of claiming a successful save.
- This is local persistence, not a backup or encryption service. Exports contain home/work locations and listing links. Keep them private; use exports before clearing browser storage. There is no cross-tab merge/synchronization or account sync; avoid editing the same origin in multiple tabs.
- The Go server does not receive scenario data in this milestone. With a key configured, the browser contacts MapTiler for style/tile/logo resources: IP, origin/referrer and the visible map viewport are exposed to that provider. Camera movements can reveal the areas being considered even though candidate labels/rents are not sent. Opening a listing sends an ordinary browser request to its website.

## Validation and remaining manual checks

Unit tests exercise JSON round-trips, invalid/unsupported data, limits, IDs, URLs, rent precision, geographic bounds and unavailable/corrupt storage. Playwright runs real MapLibre in Chromium with **local intercepted style/logo fixtures and no real provider calls**. It covers map clicks, keyboard marker selection and sidebar synchronization, editing/removal, persistence, import/export, unsafe labels, missing-key mode, storage recovery, map errors and mobile overflow. Two fixture dev servers exercise key-present/key-missing behavior; only the second uses Vite's `--bypass-lock` for this intentional same-project test setup. Test servers are stopped by Playwright and browser artifacts go to the OS temporary directory.

`Frontend checks` CI is read-only, has no Jira/MapTiler credentials, and runs formatting/type checks, unit tests, build and browser tests on Node 24. No branch-protection requirements are changed. Vite may report a large-chunk advisory because this MVP includes MapLibre; it is not a build failure. Monitor size before public deployment rather than hiding the advisory.

Local implementation validation also exercised a key-present production bundle through the Go server: health endpoint, bundled worker startup, map readiness, rental creation and persistence after reload. Provider requests were intercepted with local fixtures in that smoke check too; it is not a live MapTiler test.

Before claiming a live-provider acceptance check, the owner should:

- Configure their own restricted key and verify an actual Sydney basemap, attribution/logo, zoom/pan and marker placement in their browser; check the account Analytics usage.
- Try one real destination and a couple of rentals, keyboard selection, reload, edit/removal and JSON restore on desktop/mobile.
- Check bad-key/quota behavior without exposing credentials. Real quota exhaustion is not simulated against the account, and automated fixtures are not proof of real provider entitlement or tile quality.

No journey durations, fares, route geometry, schedule editor, costing or sample routes are fabricated. Those remain SCCC-7 and SCCC-8. Keep SCCC-6 open until the live-provider/manual acceptance checks and merge requirements are satisfied.
