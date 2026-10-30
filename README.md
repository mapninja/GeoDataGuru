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
| `aardvark.js` | Turns a weird shelf entry into an Aardvark record. Used by the "Add a dataset" form. |
| `data/ogm-subset.json` | OGM records. Written by the harvester. |
| `metadata-aardvark/` | The weird shelf as OpenGeoMetadata Aardvark records, one JSON file each. **Edit these.** Layout matches what OGM Metadata Studio reads and writes. |
| `data/weird-catalog.json` | The weird shelf as the page loads it. **Built from `metadata-aardvark/`. Do not edit by hand.** |
| `data/weird-vocab.json` | The allowed values for theme, spatial, fit and checked. Edited by hand. |
| `assets/` | Animated GIFs and still PNGs (globe, satellite orbit, radar, divider strip). |
| `scripts/harvest_ogm.py` | Rebuilds `ogm-subset.json` from GitHub. |
| `scripts/harvest_config.json` | Which OGM repos to harvest and how many records to keep. |
| `scripts/aardvark_catalog.py` | Builds `weird-catalog.json` from the Aardvark records. |
| `scripts/validate_data.py` | Checks the catalog, the OGM snapshot and the Aardvark records. |
| `scripts/test_harvest.py` | Tests for the harvester. |
| `scripts/test_aardvark_catalog.py` | Tests for the record converter and `aardvark.js`. |
| `scripts/make_gifs.py` | Redraws the GIFs. |
| `.github/workflows/` | `check.yml` validates the data on every push. `harvest.yml` refreshes the snapshot monthly. `build-catalog.yml` rebuilds `weird-catalog.json` when a record changes. |
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

8. **Optional: GitHub Actions.** Open the **Actions** tab. `check.yml` runs on every push and should show a green mark. `harvest.yml` runs on the 1st of each month and commits a refreshed `data/ogm-subset.json`. `build-catalog.yml` commits a rebuilt `data/weird-catalog.json` after a record changes. To let them commit, go to Settings > Actions > General > Workflow permissions and choose **Read and write permissions**. You can start either one by hand from the Actions tab with **Run workflow**.

### After the first deploy

Every push to `main` republishes the site in a minute or two. The loop for any change is:

```
git add -A
git commit -m "Describe the change"
git push origin main
```

You can also edit a record in the GitHub web editor and commit there. See the next sections.

### Good to know

- `check.yml` validates the data on every push, but Pages publishes on its own, so a failed check does not block the publish. It shows a red mark in the Actions tab. To check first, commit to a branch and merge through a pull request.
- The whole repository is public on the site, including `scripts/` and `REPORT.md`.
- If the site shows an old version, hard refresh (Cmd+Shift+R) and check the Actions tab for a failed build.
- If the page is a 404, confirm Source is **Deploy from a branch**, the branch is `main`, and the folder is `/ (root)`. A private repository needs a paid GitHub plan for Pages.
- The action versions in the workflows (checkout v4, setup-python v5) were not checked against current releases. If a run fails on a version, bump it.

## Weird shelf records (Aardvark)

Each weird dataset is one [OpenGeoMetadata Aardvark](https://opengeometadata.org/) record in `metadata-aardvark/<Resource class>/<id>.json`. Most are in `Datasets/`. Live services are in `Web services/`. The page does not read those files. `scripts/aardvark_catalog.py build` gathers them into `data/weird-catalog.json`, and the `build-catalog.yml` workflow runs that for you after a push.

How the old fields map:

| Shelf field | Aardvark field |
| --- | --- |
| `id`, `title` | `id`, `dct_title_s` |
| `note` | `dct_description_sm` |
| `url` | `dct_references_s` (JSON text, key `http://schema.org/url`) |
| `license` | `dct_rights_sm` (free text, so not `dct_license_sm`, which expects a link) |
| `theme` | `gdg_theme_s`. A copy goes in `dcat_keyword_sm`, but the page reads `gdg_theme_s`. |
| `spatial`, `fit`, `checked`, `size`, `via` | `gdg_spatial_s`, `gdg_fit_s`, `gdg_checked_s`, `gdg_size_s`, `gdg_via_s` |
| `layers` | `gdg_layers_sm`. One text row per layer: `name \| count \| source \| license`. |
| list position | `gdg_order_i`. Lower numbers show first. Records without one go last. |

Fields that start with `gdg_` have no Aardvark equivalent. They are ordinary extra fields, and Studio keeps them when it imports and exports. `theme`, `spatial`, `fit` and `checked` must be a value listed in `data/weird-vocab.json`. To add a new theme, add it there.

### Add a dataset

Option A, with the page:

1. Open the page and expand **Add a dataset to the shelf**.
2. Fill in the form and click **Make JSON**.
3. Click **Copy**. Save the text as the file named under the record, for example `metadata-aardvark/Datasets/my-dataset.json`. In the GitHub web editor, use **Add file > Create new file**.

Option B, by hand. Copy an existing record in `metadata-aardvark/` and edit it. The file name must be the `id` plus `.json`, and the folder must be the record's first resource class.

Then publish:

```
python3 scripts/aardvark_catalog.py build   # writes data/weird-catalog.json
python3 scripts/validate_data.py
git add metadata-aardvark data/weird-catalog.json
git commit -m "Add dataset"
git push
```

If you skip the `build` line and push only the record, `build-catalog.yml` rebuilds the catalog and commits it. That takes a minute or so. If a record has a problem, the run fails and the Actions log says which file and what is wrong.

### Edit a record

- On the page, each shelf card has an **Edit this record** link to the GitHub web editor for its file. Commit there and the catalog rebuilds.
- Or edit the JSON file locally and run the commands above.

### Edit records in OGM Metadata Studio

[OGM Metadata Studio](https://github.com/ewlarson/ogm-metadata-studio) is a separate browser app for editing Aardvark records. It is not part of this site, so you run it yourself. Its README says to clone it, then run `npm install` and `npm run dev` inside its `web/` folder, which serves it at http://localhost:5173. Editing needs a Google sign-in, and reading a repository needs a GitHub token.

1. In Studio, use the GitHub import and point it at `mapninja/GeoDataGuru`, branch `main`. The importer looks for a `metadata-aardvark` folder, which is where these records are.
2. Edit records. The `gdg_` fields are extra fields, so they may not appear as named form fields. If you cannot find them, edit those records in the JSON file instead.
3. Export the records as a ZIP. Studio names each file after the record's `id` and its folder after the first resource class, which matches this repository.
4. Unzip it over the repository so the files land in `metadata-aardvark/`. Studio may add empty fields. That is harmless.
5. Commit and push. The catalog rebuilds. Check the build log if a record is rejected.

Notes:

- Studio's README lists writing edits straight back to GitHub as "In Progress", so the ZIP step is the way to get edits into the repository.
- If you change a record's first resource class in Studio, the export puts it in a different folder. Delete the old file, or the build reports a duplicate id.
- Records for the OGM snapshot (`data/ogm-subset.json`) are not edited here. They are harvested from the OpenGeoMetadata repositories, and fixes belong upstream.

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
