# Spatial Data Portal (GeoCities style)

A static site for GitHub Pages. It searches three things from one box:

- **Local snapshot:** a sample of OpenGeoMetadata (OGM) records in `data/ogm-subset.json`.
- **Weird data shelf:** a curated list in `data/weird-catalog.json`. These entries also show up in search.
- **Live API:** the BTAA Geospatial API. Limited to 10 requests per minute.

Local search runs in the browser and uses no API calls. See `REPORT.md` for the feasibility findings.

## Folder map

| Path | What it is |
| --- | --- |
| `index.html`, `style.css`, `app.js` | The page. `app.js` is commented for beginners. |
| `data/ogm-subset.json` | OGM records. Written by the harvester. |
| `data/weird-catalog.json` | Weird datasets. Edited by hand. |
| `assets/` | Animated GIFs and still PNGs (globe, satellite orbit, radar, divider strip). |
| `scripts/harvest_ogm.py` | Rebuilds `ogm-subset.json` from GitHub. |
| `scripts/harvest_config.json` | Which OGM repos to harvest and how many records to keep. |
| `scripts/validate_data.py` | Checks both JSON files. |
| `scripts/test_harvest.py` | Tests for the harvester. |
| `scripts/make_gifs.py` | Redraws the GIFs. |
| `../.github/workflows/` | `pages.yml` deploys the site. `harvest.yml` refreshes the snapshot monthly. |

## Run it on your computer

The page loads JSON files, so it needs a web server. Opening `index.html` as a file will not work.

```
cd geocities-geoportal
python3 -m http.server 4173
```

Open http://localhost:4173.

## Deploy to GitHub Pages

One time:

1. Push the repository to GitHub.
2. Go to Settings > Pages. Under Build and deployment, set Source to **GitHub Actions**.
3. Push to `main`. The `pages.yml` workflow checks the data, then publishes the `geocities-geoportal` folder.

After that, every push to `main` that touches the folder redeploys. The workflow fails before publishing if a data file is invalid.

The action versions in the workflows were not checked against current releases. If a run fails on a version, bump it.

## Add a dataset to the weird shelf

Option A, with the page:

1. Open the page and expand **Add a dataset to the shelf**.
2. Fill in the form and click **Make JSON**.
3. Click **Copy**. Paste the text into the `datasets` list in `data/weird-catalog.json`, before the final `]`.

Option B, by hand. Copy an existing entry and edit it. Fields:

| Field | Rule |
| --- | --- |
| `id` | Lowercase letters, numbers and hyphens. Must be unique. |
| `title` | Shown on the card. |
| `theme`, `spatial`, `fit`, `checked` | Must be a value listed in `meta` at the top of the file. To add a new theme, add it to `meta.themes` too. |
| `license` | Free text. Write "Unknown" if you have not checked. |
| `url` | Starts with `http://` or `https://`. |
| `via`, `size`, `note` | Free text. |
| `layers` | Optional. List of `[name, count, source, license]` for datasets with sub-layers. |

Then check and publish:

```
python3 scripts/validate_data.py
git add data/weird-catalog.json
git commit -m "Add dataset"
git push
```

The site updates in a minute or two. You can also edit the file in the GitHub web editor and commit there.

## Refresh the OpenGeoMetadata snapshot

Needs Python 3.9+ and git. No other packages.

```
python3 scripts/harvest_ogm.py                  # 16 records per repo (settings in harvest_config.json)
python3 scripts/harvest_ogm.py --per-repo 40    # bigger sample
python3 scripts/harvest_ogm.py --repos edu.osu edu.purdue
python3 scripts/harvest_ogm.py --full           # every record (large file)
python3 scripts/harvest_ogm.py --repos-dir ~/ogm   # use clones you already have
python3 scripts/validate_data.py
```

To change the default repo list, edit `scripts/harvest_config.json`. Repo names match https://github.com/OpenGeoMetadata.

Or let GitHub do it: the `harvest.yml` workflow runs on the 1st of each month. You can also run it by hand from the Actions tab.

Notes:

- The default sample reads evenly spaced files, keeps records with a bounding box first, and rotates through resource classes. It is for demos, not a representative sample. Do not use it to count holdings.
- Every record is downloaded to the visitor's browser. About 200 records is roughly 100 KB. A full harvest is tens of thousands of records and many megabytes. If you go that far, split the file by repo or move to a server-side index.
- Some OGM repos (for example purdue and wisc) use older folder layouts. The harvester reads `metadata-aardvark/` and skips repos that lack it.
- The harvester was tested on fixtures. It has not been run against live GitHub. Run it once and read the output before trusting it.

## Change the animations

`python3 scripts/make_gifs.py` redraws every GIF and still PNG into `assets/`. It needs `pip install pillow numpy`. The page shows the still PNGs to visitors whose system asks for reduced motion.

## Tests

```
python3 scripts/test_harvest.py
python3 scripts/validate_data.py
```
