# Feasibility report: GeoCities-styled spatial data portal on GitHub Pages, backed by the BTAA API

Prepared October 29, 2026 for Stace Maples. All API measurements were taken that day from a browser.

## Verdict

- **Feasible as a prototype or a demo.** The proof of concept in this folder searches the live BTAA Geospatial API from a static page, with facets, filters, paging, place search, density hexagons, map footprints, access links and citations.
- **Not ready for a classroom of 30 on one network without a change.** The API allows 10 requests per minute and counts some image requests. A shared campus IP will hit that limit fast. Three fixes are listed under "Options".
- **GeoCities styling is the easy part.** It is plain CSS and animated GIFs. It does not affect the architecture.
- **The rate limit is now avoidable for demos.** The page searches a local snapshot of 208 OpenGeoMetadata records plus the 36-entry weird shelf with no API calls. The live API is one menu choice away.
- **Updating is a file edit.** New datasets go into `data/weird-catalog.json`. The OGM snapshot is rebuilt by a script or a monthly GitHub Action. Pushing to `main` redeploys.

## What the API does (measured)

| Question | Result |
| --- | --- |
| Base URL | `https://geo.btaa.org/api/v1` (API version 0.12.1 at test time) |
| Browser access from another origin (CORS) | Works. Tested from `example.com` with search, facets and h3 calls. No custom headers are needed, so no preflight. |
| Authentication | None. No key required. |
| Response format | JSON:API style. Records are in `data[].attributes.ogm` (Aardvark fields) and `data[].meta.ui` (thumbnail, citation, downloads, links, viewer). |
| Facets | Come back in the same `/search` answer under `included`. No separate facet calls needed. |
| Filters | `include_filters[field][]=value`. Place search: `include_filters[geo][type]=distance` with center and distance (copied from the BTAA example apps, tested). |
| Density map | `/map/h3?bbox=minLon,minLat,maxLon,maxLat&resolution=N` returns `[[cell, count], ...]`. Tested live. |
| Paging | `page` and `per_page`. Total count is in `meta.totalCount`. |
| Rate limit | 10 requests per minute. Header `x-ratelimit-*` shows it. The window appeared to reset on the clock minute. Not confirmed whether it is per IP. |
| What counts toward the limit | `/search`, `/map/h3`, `/resources/{id}/thumbnail`, `/static-maps/{id}/geometry` and `/thumbnails/placeholder`. |
| What does not count | `/static-map-assets/{hash}`. These are PNGs cached for a year. In a 24-record sample, 18 used this path and 6 used the counted `/static-maps/` path. |
| Blocked requests | The 429 response has no CORS headers, so the browser reports only "Failed to fetch". The page cannot read the status or a retry time. |
| Other endpoints worth knowing | `/suggest`, `/resources/{id}`, citation formats (RIS, BibTeX, JSON-LD), `/ogc/collections/btaa-records/items` (OGC API Features), `/ogm/repos`, `/mcp`. Not tested except `/suggest` and `/resources/{id}`. |

## Risks

- **Rate limit (high).** Ten requests per minute covers one person browsing slowly. A classroom or a workshop will exceed it. If limits are per IP, a campus NAT shares one budget.
- **Counted images (high, handled in the prototype).** Loading 12 thumbnails would use the whole budget. The prototype shows only uncounted images automatically and loads others on click.
- **Opaque errors (medium, handled).** The prototype tracks its own call count, stays at 8 per minute, and on a failed call waits for the next clock minute and retries once. Verified in test: a blocked place search recovered on its own.
- **API stability (medium).** Version 0.12.x is pre-1.0. Field names and limits can change. Sample apps by the same author used `geodev.btaa.org` as the base URL, which suggests a development host exists. Production is `geo.btaa.org`.
- **Pages limits (low).** Static files only, so no secret keys and no server code. Published sites are limited to 1 GB, and repository files over 100 MB are blocked. These matter only for the weird-data layers and a full OGM harvest.
- **Snapshot staleness and bias (medium).** The local file is a demo-size, non-random sample. It goes stale between harvests. See "Local snapshot".
- **Map tiles (low).** The prototype uses the public OpenStreetMap tile server. Its usage policy discourages heavy use. Switch to a hosted tile provider for classes.
- **Mixed links (low).** API self links use `http://`. The prototype builds `https://` URLs itself.

## Options for the rate limit

1. **Ask BTAA.** Request a key, an allowlist for `*.github.io` and your campus range, or an exemption for image paths. Cheapest, and the owner may already have a plan. No code change needed.
2. **Caching proxy.** A free Cloudflare Worker (or similar) in front of the API with caching. Adds one small non-Pages component. Breaks the "pure GitHub Pages" goal.
3. **Snapshot.** Harvest OpenGeoMetadata records into static JSON on a schedule and query it in the browser. **Built in this version** at demo size (see "Local snapshot"). No rate limit, but the data goes stale between harvests, and the whole file downloads to every visitor. `ogm-metadata-studio` takes the larger-scale route with DuckDB-WASM. Not tested at full scale.

For a live demo or a class, use the local snapshot and keep the live API for spot checks.

## The prototype

Files in the `geocities-geoportal` folder (the README has the full map):

- `index.html`, `style.css`, `app.js`: the portal. About 900 lines of JavaScript, commented for beginners.
- `data/ogm-subset.json`: the OpenGeoMetadata snapshot.
- `data/weird-catalog.json`: the curated list of 36 odd datasets (see below).
- `assets/`: four animated GIFs and their still PNGs.
- `scripts/`: harvester, validator, tests and the GIF generator.
- `../.github/workflows/`: `pages.yml` (deploy) and `harvest.yml` (monthly refresh).
- `README.md`: how to run, deploy and update. `REPORT.md`: this file.

How it behaves:

- A menu chooses the source: local snapshot with the weird shelf, or the live API. The "Search live API too" button runs the same words against the API.
- Local search is AND matching on every word, ignores accents, and ranks title hits above keyword and place hits above description hits. It supports facets (resource class, provider, place, weird theme), five sorts, paging and the place search from the map center.
- Live search: one call returns results and facets together.
- State is stored in the URL hash, so searches are linkable.
- Responses are cached for 10 minutes in memory and `sessionStorage`, so a reload costs no calls.
- Record text is inserted with `textContent` only. Tested with a hostile title and a `javascript:` download link. Both were neutralized.
- A CSV tool loads any file with latitude and longitude columns, in the browser. It handles the Bigfoot and haunted places files by column name. Not tested with real Kaggle files (see "Not verified").
- Styling: starfield background, rainbow title, hazard-stripe banner, beveled buttons, visitor counter, web ring footer. Text colors were chosen for contrast: black on pale yellow for content, light text on dark for the page.
- Animated GIFs, all drawn by `scripts/make_gifs.py` (original art, not clip art): a spinning globe on each side of the title and in the footer, a satellite orbiting a globe in the construction banner and the shelf heading, a radar sweep on the place search panel, and a starry strip with satellites crossing it used as the section divider. The globe uses invented continents, not real geography. Visitors whose system asks for reduced motion get still PNGs instead. The four GIFs total about 230 KB.

## Local snapshot (OpenGeoMetadata)

What is in `data/ogm-subset.json`:

- 208 records, 16 each from 13 BTAA-area repositories: illinois, indiana, msu, northwestern, osu, psu, rutgers, uchicago, uiowa, umd, umich, umn, unl. 196 have a map footprint. Classes: Maps 159, Websites 16, Imagery 13, Datasets plus Web services 7, Other 5, Datasets 4, Web services 4.
- Each record keeps 13 short fields: id, title, 140 characters of description, provider, class, year, access, bounding box, keywords, places, source repo, landing page URL and first download URL. The `meta` block in the file documents them.
- The file is about 100 KB.

Method and bias:

- Records were read from the OGM GitHub repositories with the same normalization rules as `scripts/harvest_ogm.py`: accent normalization, spreadsheet artifacts removed, `ENVELOPE(W,E,N,S)` converted to `minLon,minLat,maxLon,maxLat`, first download link kept.
- Within each repo the sample favors records that have a bounding box and rotates through resource classes. That makes the demo map look good. It also means the sample is not representative. Do not use it to count or compare collections. The `meta` block lists, per repo, how many records the live API held on 2026-02-25 and how many were sampled.
- Four records cross the antimeridian (the UMN global records, for example `179,-75,-179,85`). The page draws each as two rectangles and the place search measures distance across the 180 degree line. Tested with a headless DOM.
- Records link to their source page and to the BTAA record page. Check access terms there.

How to refresh it: run `python3 scripts/harvest_ogm.py`, or let the monthly workflow do it. Options for sample size, repo list and full harvests are in the README. At full scale (tens of thousands of records) the single JSON file is too large to send to every visitor. Split it by repo, or use DuckDB-WASM as `ogm-metadata-studio` does.

## Your reference repos

- `geobtaa/api`: the backend. Frontend docs describe the production site (React, MUI, Leaflet, H3, Allmaps). Allmaps georeferencing links could be added to results next.
- `ewlarson/api-example-apps`: static Pages demos against this API. It confirms the pattern works and supplied the query syntax. Its examples use `geodev.btaa.org`.
- `ewlarson/rui`: a React UI for the API with a `gh-pages` deploy script. Its to-do list includes "make the application themeable." A GeoCities theme could be submitted as one.
- `ewlarson/ogm-metadata-studio`: browser-only metadata workspace on DuckDB-WASM. Source of the snapshot option above.
- `divshot/geo-bootstrap`: a 2013 Bootstrap theme (MIT). Despite the name, it is not GeoCities-styled, so it was not used.

## Weird data shelf

You asked for a curated set of unusual datasets from the sites you sent. The shelf has 36 entries across five themes: Paranormal (7), Earth events (8), Lost and historic (6), Transport and risk (11), Nature and sky (4). Each entry shows theme, location type, size, license, source and how it could be used here. Eleven were read on their pages. Twenty-five are listed only, and the shelf marks them.

What matters for the portal:

- **Strange Places v5.2** is the most useful single source: 354,770 points in 14 categories with consistent fields. The category counts add up to the total. It is too large to load at once. Split it by category.
- **Licenses conflict.** The dataset card says "other," the JSON-LD says CC BY 4.0, and the README lists Fair Use for BFRO, NUFORC and Shadowlands records. OpenStreetMap-derived layers (caves, ghost towns) are ODbL, which needs attribution and share-alike.
- **BFRO** is copyrighted (BFRO.net) with no open license, download or API found. The Kaggle Bigfoot file has an "Unknown license." Ask BFRO before committing report text to a public repository. Linking out is safe.
- **Haunted Places (Kaggle)** has a license of "Other (specified in description)." It comes from the Shadowlands index via data.world.
- **UFO file (Kaggle, CC0)** has no coordinates, only city, state and country. Geocode it first, for example against GeoNames. It is 28 KB of famous events, not a sighting database.
- **Kaggle downloads need a sign-in.** Nothing was downloaded.
- **Overlap with BTAA.** The David Rumsey collection and Pleiades fit alongside the BTAA scanned maps.
- **Live candidates** (USGS earthquakes, GBIF, GDELT, ArcGIS Hub) could become live layers. Browser access was not tested for any of them.
- **Sensitive entry.** The Flock Locations map lists surveillance cameras from community reports. It is marked link-only. Review it before reuse.

Sources that gave little: the Medium article lists 20 datasets, but only two are readable as text (80,000+ UFO reports, militarized interstate disputes). The rest are images. The rs.io list is from 2014, so links may be stale. The Kaggle discussion thread (general/250218) lists XSS attacks, Cassini images and a job survey. None are spatial, so it added nothing.

## Not verified

- Whether the rate limit is per IP, and its exact reset rule.
- The CSV loader with real files. Code paths were checked, but the Kaggle files were not downloaded.
- Browser access (CORS) for USGS, GBIF, GDELT and other live sources on the shelf.
- Rendering on the real `github.io` domain, and the new JSON loading there. Tests ran against a headless DOM with a stubbed map and stubbed `fetch`.
- The Python harvester against live GitHub. It passes tests on synthetic Aardvark fixtures and against the committed file's key set. The committed 208 records came from the same rules applied in a browser, not from this script, so the first real run may produce slightly different records. Run it once and diff the output.
- The two GitHub Actions workflows. They were never run. The action versions (checkout v4, setup-python v5, configure-pages v5, upload-pages-artifact v3, deploy-pages v4) were not checked against current releases because web fetch was unavailable. The `harvest.yml` step that starts the deploy needs the `actions: write` permission it declares.
- Layout of the new page. A static copy (no map, no scripts) was viewed at phone width: header, globes, banner, divider strip and the radar heading render correctly. The map, the results grid and the wide desktop layout were not viewed.
- Leaflet drawing of the two-piece antimeridian boxes. The code that builds the pieces was tested, not the drawn map.
- Link status of the 2014 and 2016 article links.

## Deploy and update

Full steps are in `README.md`. In short:

1. Push the repository to GitHub. In Settings > Pages, set Source to **GitHub Actions**.
2. Push to `main`. `.github/workflows/pages.yml` runs `validate_data.py` and `test_harvest.py`, then publishes only the `geocities-geoportal` folder. A bad data file stops the deploy.
3. To add a weird dataset: use the "Add a dataset" form on the page to print a JSON entry, paste it into `data/weird-catalog.json`, run `python3 scripts/validate_data.py`, commit and push. The GitHub web editor works too.
4. To refresh OGM records: `python3 scripts/harvest_ogm.py`, or wait for the monthly `harvest.yml` run (or start it from the Actions tab).

Run locally with `python3 -m http.server 4173` inside the folder. Opening `index.html` as a file does not work, because the page loads JSON. The page detects this and falls back to the live API with a message.

## Next steps

1. Run the harvester once against GitHub, diff against the committed file, and decide the sample size.
2. Push, enable Pages, and check the live site, including the map.
3. Email BTAA about a key or allowlist (option 1) if classes will use live search.
4. Decide on the weird layers: pick categories from Strange Places, confirm licenses, convert to compressed JSON or PMTiles.
5. Add Allmaps overlay links for georeferenced maps.
6. Decide whether to offer the theme to `rui`.

## Sources

- [BTAA Geospatial API root](https://geo.btaa.org/api/v1/)
- [geobtaa/api](https://github.com/geobtaa/api) and its [frontend docs](https://github.com/geobtaa/api/blob/develop/docs/frontend/README.md)
- [ewlarson/api-example-apps](https://github.com/ewlarson/api-example-apps)
- [ewlarson/rui](https://github.com/ewlarson/rui)
- [ewlarson/ogm-metadata-studio](https://github.com/ewlarson/ogm-metadata-studio)
- [divshot/geo-bootstrap](https://github.com/divshot/geo-bootstrap)
- [BFRO database](https://www.bfro.net/gdb/)
- [Kaggle: Haunted Places](https://www.kaggle.com/datasets/sujaykapadnis/haunted-places), [Bigfoot Sightings](https://www.kaggle.com/datasets/thedevastator/unlocking-mysteries-of-bigfoot-through-sightings), [UFO Sightings](https://www.kaggle.com/datasets/ahemateja19bec1025/ufosightingsdataset)
- [Strange Places dataset](https://github.com/data-poems/strange-places-dataset)
- [Weird Data Collections](https://wierddatacollections.com/)
- [awesome-public-datasets](https://github.com/awesomedata/awesome-public-datasets)
- [rs.io: 100+ Interesting Data Sets](https://rs.io/100-interesting-data-sets-for-statistics/)
- [Medium: 20 Weird & Wonderful Datasets](https://medium.com/@olivercameron/20-weird-wonderful-datasets-for-machine-learning-c70fc89b73d5)
