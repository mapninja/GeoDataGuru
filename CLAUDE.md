# GeoDataGuru

Static spatial data portal in a GeoCities style, published on GitHub Pages from `main` (root folder). No build step and no package manager. Plain HTML, CSS and JS in the browser, plus Python 3.9+ scripts that use only the standard library. See `README.md` for setup and deployment, and `REPORT.md` for feasibility findings.

## Commands

```
python3 -m http.server 4173                  # run locally. Opening index.html as a file does not work.
python3 scripts/validate_data.py             # checks the catalog, the OGM snapshot and the Aardvark records
python3 scripts/aardvark_catalog.py build    # rebuilds data/weird-catalog.json from metadata-aardvark/
python3 scripts/test_aardvark_catalog.py     # converter tests. Also runs aardvark.js under node if installed.
python3 scripts/test_harvest.py              # harvester tests
python3 scripts/harvest_ogm.py               # refreshes data/ogm-subset.json (needs git and network)
```

CI (`.github/workflows/check.yml`) runs the validator and both test scripts on every push. It cannot block a Pages publish.

## Data flow

- **Weird shelf.** Source of truth is `metadata-aardvark/<Resource class>/<id>.json`, one Aardvark record per dataset. `data/weird-catalog.json` is generated from them. Never edit it by hand: run `build` after changing a record. The allowed values for theme, spatial, fit and checked are in `data/weird-vocab.json`.
- **Custom fields.** Fields with no Aardvark equivalent are `gdg_*` extra fields (`gdg_fit_s`, `gdg_layers_sm`, `gdg_order_i` and so on). The mapping is in `scripts/aardvark_catalog.py` and is documented in `README.md`.
- **Two copies of the mapping.** `to_aardvark()` in `scripts/aardvark_catalog.py` and `toAardvark()` in `aardvark.js` must agree. `test_aardvark_catalog.py` compares them, so change both together.
- **OGM snapshot.** `data/ogm-subset.json` is written by `scripts/harvest_ogm.py` from the OpenGeoMetadata repos, in a compact short-key format. Do not hand edit it.
- **Page.** `app.js` loads both data files in `loadLocalData()` and searches them in the browser. The live BTAA API is limited to 10 requests per minute, and `app.js` stays at 8.

## Conventions

- Keep the code readable for beginners. `app.js` and the scripts are heavily commented, so match that.
- `app.js` uses `const` and arrow functions. Python scripts have no third-party packages.
- Record file names must equal the record `id`, and the folder must match the first resource class (the same layout OGM Metadata Studio exports).
- JSON files use a one-space indent and keep real accents, not `\u` escapes. `aardvark_catalog.py` already writes them that way.
- GitHub Actions versions in the workflows were not checked against current releases. Bump them if a run fails.

## Workflows

`.github/workflows/`: `check.yml` (validate and test), `harvest.yml` (monthly OGM refresh), `build-catalog.yml` (rebuilds the catalog after a record changes). The two that commit need Settings > Actions > General > Workflow permissions set to Read and write.
