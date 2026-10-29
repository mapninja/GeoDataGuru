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
| `.github/workflows/` | `check.yml` validates the data on every push. `harvest.yml` refreshes the snapshot monthly. |
| `.nojekyll` | Empty file. Tells GitHub Pages to serve the files as they are. |

## Run it on your computer

The page loads JSON files, so it needs a web server. Opening `index.html` as a file will not work.

```
python3 -m http.server 4173
```

Run the command from the repository root. Open http://localhost:4173.

## Deploy to GitHub Pages

The site files live at the top level of the repository, so Pages publishes straight from `main`. There is no build step. This repository is `mapninja/GeoDataGuru`, so the live address will be:

**https://mapninja.github.io/GeoDataGuru/**

### Step by step (first time)

1. **Test locally.** From the repository root, run:

   ```
   python3 scripts/validate_data.py
   python3 -m http.server 4173
   ```

   The first command should print `OK`. Open http://localhost:4173 and confirm the page loads, shows results and the globes animate. Stop the server with Ctrl+C.

2. **Commit everything.** The site files moved from the `geocities-geoportal/` folder to the top level, so Git will show the old paths as deleted and the new paths as added. That is expected.

   ```
   git add -A
   git status
   git commit -m "Move portal to repo root for GitHub Pages"
   ```

   `git status` should list `index.html`, `app.js`, `style.css`, `data/`, `assets/`, `scripts/`, `.nojekyll` and `.github/workflows/`.

3. **Push to GitHub.**

   ```
   git push origin main
   ```

4. **Turn on Pages.** In your browser:
   1. Open https://github.com/mapninja/GeoDataGuru.
   2. Click **Settings** (top row of tabs).
   3. In the left sidebar, click **Pages**.
   4. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
   5. Under **Branch**, choose `main` and the folder `/ (root)`. Click **Save**.

5. **Wait for the first publish.** Open the **Actions** tab. A run named "pages build and deployment" appears. It usually finishes in one to two minutes. The first publish can take a few minutes longer.

6. **Open the site.** Go to https://mapninja.github.io/GeoDataGuru/. Settings > Pages also shows the address once the site is live.

7. **Check it works.**
   - The status line says it searched local records, and results appear.
   - Search `bigfoot`. Two weird shelf entries should appear.
   - Click **Search near center**. The count drops.
   - The weird data shelf at the bottom lists 36 datasets.
   - If you see "Could not load the data files", the page was opened from the wrong address. Use the `github.io` address above, not a file.

8. **Optional: GitHub Actions.** Open the **Actions** tab. `check.yml` runs on every push and should show a green mark. `harvest.yml` runs on the 1st of each month and commits a refreshed `data/ogm-subset.json`. To let it commit, go to Settings > Actions > General > Workflow permissions and choose **Read and write permissions**. You can start `harvest.yml` by hand from the Actions tab with **Run workflow**.

### After the first deploy

Every push to `main` republishes the site in a minute or two. The loop for any change is:

```
git add -A
git commit -m "Describe the change"
git push origin main
```

You can also edit `data/weird-catalog.json` in the GitHub web editor and commit there.

### Good to know

- `check.yml` validates the data on every push, but Pages publishes on its own, so a failed check does not block the publish. It shows a red mark in the Actions tab. To check first, commit to a branch and merge through a pull request.
- The whole repository is public on the site, including `scripts/` and `REPORT.md`.
- If the site shows an old version, hard refresh (Cmd+Shift+R) and check the Actions tab for a failed build.
- If the page is a 404, confirm Source is **Deploy from a branch**, the branch is `main`, and the folder is `/ (root)`. A private repository needs a paid GitHub plan for Pages.
- The action versions in the workflows (checkout v4, setup-python v5) were not checked against current releases. If a run fails on a version, bump it.

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
