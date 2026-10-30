/* ============================================================
   Spatial Data Portal prototype
   Two search sources, one page. No server needed.
     - "local": two JSON files in the data/ folder (an OpenGeoMetadata
       snapshot and the weird data catalog). Searched in the browser.
       No rate limit.
     - "live": the BTAA Geospatial API. Limited to 10 requests per minute.

   How this file is organized (read top to bottom):
     1. Settings
     2. Small helper functions
     3. API client (rate limit budget, cache, error handling)
     4. Map setup
     5. Search: live API request, then local search over the JSON files
     6. Drawing the page (results, filters, pager)
     7. Map tools (search near center, density hexagons)
     8. CSV layers (Bigfoot, haunted places, any lat/lon file)
     8b. Weird data shelf and the "add a dataset" helper
     9. Page state in the URL, visitor counter, start up

   Everything from the API is treated as untrusted text. We build page
   elements with textContent, never innerHTML, so a record cannot inject code.
   ============================================================ */
(function () {
  'use strict'; // Turns some silent mistakes into visible errors.

  // ---------- 1. Settings ----------
  const API_BASE = 'https://geo.btaa.org/api/v1'; // the production API
  const SITE_BASE = 'https://geo.btaa.org';       // full record pages live here
  const REPO_EDIT_BASE = 'https://github.com/mapninja/GeoDataGuru/edit/main/'; // GitHub web editor for a repo file
  const PER_PAGE = 12;                            // results per page
  const MAX_PAGE = 100;                           // stop paging far into the result set

  // The API allows 10 requests per minute per visitor (measured October 2026).
  // Image requests to some API paths count too (see readRecord).
  // We stop at 8 so a second tab or a retry does not push us over the limit.
  const BUDGET_MAX = 8;
  const BUDGET_WINDOW_MS = 60 * 1000;
  const CACHE_TTL_MS = 10 * 60 * 1000;            // reuse answers for 10 minutes

  // The two data files. data/weird-catalog.json is built from metadata-aardvark/ (see README.md).
  const DATA_OGM = 'data/ogm-subset.json';
  const DATA_WEIRD = 'data/weird-catalog.json';

  // Facets (filter lists) to show, with friendly names. Keys are API field names.
  const FACETS = {
    gbl_resourceClass_sm: 'Resource class',
    schema_provider_s: 'Provider',
    gbl_resourceType_sm: 'Resource type',
    dct_spatial_sm: 'Place',
    dct_creator_sm: 'Creator'
  };

  // Facets for the local search. Keys are short names used by facetValues() below.
  const LOCAL_FACETS = { c: 'Resource class', p: 'Provider', s: 'Place', th: 'Weird theme' };

  // ---------- 2. Small helpers ----------
  const $ = (id) => document.getElementById(id); // shortcut: $('q') finds id="q"
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // Make an element: el('p', {class:'x'}, 'text or child nodes').
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === false || value == null) continue;
      node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children) {
      if (child == null) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  // Only allow web links. Blocks "javascript:" links that a bad record might contain.
  function safeUrl(value) {
    if (!value) return null; // an empty string would otherwise resolve to the site root
    try {
      const url = new URL(value, SITE_BASE);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
    } catch (e) {
      return null;
    }
  }

  // Many record fields are lists (names end in _sm). Take the first value.
  const first = (value) => (Array.isArray(value) ? value[0] : value);

  function truncate(text, max) {
    if (!text) return '';
    return text.length > max ? text.slice(0, max).trim() + '...' : text;
  }

  function setStatus(message, isError) {
    const node = $('status');
    node.textContent = message;
    node.classList.toggle('error', Boolean(isError));
  }

  // ---------- 3. API client ----------
  const budgetLog = [];      // timestamps (ms) of our recent API calls
  let cooldownUntil = 0;     // when set, we wait until this time before calling

  function pruneBudget() {
    const cutoff = Date.now() - BUDGET_WINDOW_MS;
    while (budgetLog.length && budgetLog[0] < cutoff) budgetLog.shift();
  }

  function showBudget() {
    $('budget').hidden = state.src !== 'live'; // the budget only matters for live API searches
    pruneBudget();
    $('budget').textContent = 'API calls used this minute: ' + budgetLog.length + ' of ' + BUDGET_MAX;
  }

  // Wait until we are allowed to make another call.
  async function waitForBudget() {
    for (;;) {
      pruneBudget();
      const now = Date.now();
      if (now < cooldownUntil) {
        setStatus('Waiting ' + Math.ceil((cooldownUntil - now) / 1000) + ' s for the API rate limit to reset...');
        await sleep(500);
      } else if (budgetLog.length >= BUDGET_MAX) {
        const wait = budgetLog[0] + BUDGET_WINDOW_MS - now;
        setStatus('Rate limit reached. Waiting ' + Math.ceil(wait / 1000) + ' s...');
        await sleep(500);
      } else {
        return;
      }
      showBudget();
    }
  }

  // Cache answers in memory and in sessionStorage so a reload costs no API calls.
  const memoryCache = new Map();
  function cacheGet(key) {
    let entry = memoryCache.get(key);
    if (!entry) {
      try { entry = JSON.parse(sessionStorage.getItem('btaa:' + key)); } catch (e) { entry = null; }
    }
    return entry && Date.now() - entry.time < CACHE_TTL_MS ? entry.json : null;
  }
  function cacheSet(key, json) {
    const entry = { time: Date.now(), json: json };
    memoryCache.set(key, entry);
    try {
      const text = JSON.stringify(entry);
      if (text.length < 400000) sessionStorage.setItem('btaa:' + key, text); // skip huge answers
    } catch (e) { /* storage full or blocked: memory cache still works */ }
  }

  // Fetch one API path with query parameters. Returns parsed JSON.
  async function apiGet(path, params, attempt) {
    const url = API_BASE + path + '?' + params.toString();
    const cached = cacheGet(url);
    if (cached) return cached;

    await waitForBudget();
    budgetLog.push(Date.now()); // record the call BEFORE sending it
    showBudget();

    let response;
    try {
      response = await fetch(url); // no custom headers: avoids a CORS preflight request
    } catch (err) {
      // When the API sends HTTP 429 (too many requests), the response has no CORS
      // headers, so the browser hides it and reports only "Failed to fetch".
      // We treat that as a rate limit: wait for the next clock minute, retry once.
      if (!attempt) {
        const now = Date.now();
        cooldownUntil = (Math.floor(now / 60000) + 1) * 60000 + 2000;
        return apiGet(path, params, 1);
      }
      throw new Error('The API did not answer. It may be rate limiting this network or be offline.');
    }
    if (!response.ok) throw new Error('The API returned HTTP ' + response.status + '.');
    const json = await response.json();
    cacheSet(url, json);
    return json;
  }

  // ---------- 4. Map setup ----------
  const map = L.map('map', { preferCanvas: true }).setView([41.5, -90], 4); // central U.S.
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  const resultsLayer = L.layerGroup().addTo(map); // boxes for the current page of results
  const placeLayer = L.layerGroup().addTo(map);   // the "search near" circle
  const hexLayer = L.layerGroup().addTo(map);     // density hexagons
  const boxById = new Map();                      // record id -> its rectangle on the map

  // ---------- 5. Search ----------
  // The whole page state lives in one object. Changing it and calling runSearch() redraws everything.
  // src is 'local' (JSON files in data/) or 'live' (the BTAA API).
  const state = { src: 'local', q: '', page: 1, sort: 'relevance', filters: {}, near: null };

  // Build the query string the API expects.
  // Filters look like include_filters[field][]=value. Place search uses the same style.
  // Local filters use different field names, so they are only sent in live mode.
  function buildParams(extra) {
    const p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    for (const [field, value] of Object.entries(state.src === 'live' ? state.filters : {})) {
      p.append('include_filters[' + field + '][]', value);
    }
    if (state.near) {
      p.set('include_filters[geo][type]', 'distance');
      p.set('include_filters[geo][field]', 'dcat_centroid');
      p.set('include_filters[geo][center][lat]', String(state.near.lat));
      p.set('include_filters[geo][center][lon]', String(state.near.lon));
      p.set('include_filters[geo][distance]', state.near.km + 'km');
    }
    for (const [k, v] of Object.entries(extra || {})) p.set(k, String(v));
    return p;
  }

  let searchToken = 0; // lets us ignore an old answer if a newer search started

  async function runSearch() {
    const token = ++searchToken;
    writeHash();
    syncSourceUi();
    if (state.src === 'local') { runLocalSearch(); return; } // no API call, no waiting
    setStatus('Searching the live API...');
    $('results').replaceChildren();
    try {
      const params = buildParams({ page: state.page, per_page: PER_PAGE });
      if (state.sort !== 'relevance') params.set('sort', state.sort);
      const json = await apiGet('/search', params);
      if (token !== searchToken) return; // a newer search replaced this one
      render(json);
      setStatus('Done.');
    } catch (err) {
      if (token !== searchToken) return;
      setStatus(err.message, true);
    }
  }

  // ---------- 5b. Local search ----------
  // Searches the two JSON files in the browser. Both kinds of record are turned
  // into one common shape ("items") so the same code can draw them.
  const local = { ready: false, items: [], weird: [], weirdMeta: {}, ogmMeta: {} };

  // Lowercase and strip accents so "Montreal" finds "Montréal".
  const fold = (text) => String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  // Center point of a "minLon,minLat,maxLon,maxLat" box.
  // If west is greater than east, the box crosses the antimeridian (the 180 degree line),
  // so we add 360 to east before averaging, then wrap the answer back into -180..180.
  function bboxCenter(text) {
    const n = String(text || '').split(',').map(Number);
    if (n.length !== 4 || n.some((v) => !Number.isFinite(v))) return null;
    const west = n[0];
    const east = n[0] > n[2] ? n[2] + 360 : n[2];
    let lon = (west + east) / 2;
    if (lon > 180) lon -= 360;
    return { lat: (n[1] + n[3]) / 2, lon: lon };
  }

  // Great-circle distance in km between two {lat, lon} points (haversine formula).
  // Longitudes wrap naturally, so this works across the antimeridian.
  function distanceKm(a, b) {
    const rad = Math.PI / 180;
    const dLat = (b.lat - a.lat) * rad;
    const dLon = (b.lon - a.lon) * rad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  // Turn one compact OGM record (short keys, see data/ogm-subset.json "fields") into an item.
  function ogmItem(r) {
    const btaaUrl = SITE_BASE + '/resources/' + encodeURIComponent(r.id);
    const links = [];
    if (r.u) links.push({ label: 'Source page', url: r.u });
    links.push({ label: 'BTAA record', url: btaaUrl });
    return {
      kind: 'ogm',
      id: r.id,
      title: r.t || '(untitled)',
      description: r.d || '',
      provider: r.p || '',
      classes: r.c ? r.c.split(', ') : [],
      resourceClass: r.c || '',
      year: r.y || '',
      access: r.a || '',
      bbox: r.b || '',
      places: r.s ? r.s.split(';') : [],
      thumb: '',
      citation: '',
      downloads: r.dl ? [{ label: 'file', url: r.dl }] : [],
      sourceLinks: links,
      url: r.u || btaaUrl,
      center: bboxCenter(r.b),
      // Search text, folded once at load time. Title counts most, then keywords and places, then the rest.
      t: fold(r.t),
      k: fold((r.k || '') + ' ' + (r.s || '')),
      x: fold((r.d || '') + ' ' + (r.p || '') + ' ' + (r.c || '') + ' ' + (r.r || ''))
    };
  }

  // Turn one weird catalog entry into an item. These have no map footprint.
  function weirdItem(d) {
    return {
      kind: 'weird',
      id: 'weird:' + d.id,
      title: d.title,
      description: d.note || '',
      provider: 'Weird shelf',
      classes: ['Weird data'],
      resourceClass: 'Weird data',
      year: '',
      access: '',
      bbox: '',
      places: [],
      theme: d.theme || '',
      weird: d,
      thumb: '',
      citation: '',
      downloads: [],
      sourceLinks: [],
      url: d.url,
      center: null,
      t: fold(d.title),
      k: fold((d.theme || '') + ' ' + (SPATIAL_LABELS[d.spatial] || d.spatial || '') + ' ' + (d.fit || '')),
      x: fold((d.note || '') + ' ' + (d.license || '') + ' ' + (d.via || '') + ' ' + (d.size || '') +
        ' ' + (d.layers || []).map((l) => l[0]).join(' '))
    };
  }

  // Fetch one JSON file or throw a readable error.
  async function fetchJson(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(path + ' returned HTTP ' + response.status);
    return response.json();
  }

  async function loadLocalData() {
    const [ogm, weird] = await Promise.all([fetchJson(DATA_OGM), fetchJson(DATA_WEIRD)]);
    local.ogmMeta = ogm.meta || {};
    local.weirdMeta = weird.meta || {};
    local.weird = weird.datasets || [];
    local.items = (ogm.records || []).map(ogmItem).concat(local.weird.map(weirdItem));
    local.ready = true;
  }

  // The values an item has for one local facet field.
  function facetValues(item, field) {
    if (field === 'c') return item.classes;
    if (field === 'p') return item.provider ? [item.provider] : [];
    if (field === 's') return item.places;
    if (field === 'th') return item.theme ? [item.theme] : [];
    return [];
  }

  // Every local item that matches the words, the place filter and the facet filters.
  // Returns [{ item, score }]. Not sorted yet. The density map reuses this.
  function localRows() {
    // Split the query into words. Every word must match somewhere (AND).
    const words = fold(state.q).split(/[^a-z0-9]+/).filter(Boolean);
    let rows = [];
    for (const item of local.items) {
      let score = 0;
      let matches = true;
      for (const w of words) {
        if (item.t.includes(w)) score += 5;
        else if (item.k.includes(w)) score += 3;
        else if (item.x.includes(w)) score += 1;
        else { matches = false; break; }
      }
      if (matches) rows.push({ item: item, score: score });
    }

    // Place filter: keep records whose box center is within the radius of the map center.
    if (state.near) {
      rows = rows.filter((row) => row.item.center && distanceKm(row.item.center, state.near) <= state.near.km);
    }

    // Facet filters (resource class, provider, place, theme).
    return rows.filter((row) => Object.entries(state.filters).every(([f, v]) => facetValues(row.item, f).includes(v)));
  }

  function runLocalSearch() {
    if (!local.ready) { setStatus('The data files are not loaded yet.', true); return; }
    const rows = localRows();

    // Sort. Records without a year go last when sorting by year.
    const byTitle = (a, b) => a.item.title.localeCompare(b.item.title);
    const yr = (row, missing) => Number(row.item.year) || missing;
    const sorters = {
      year_desc: (a, b) => yr(b, 0) - yr(a, 0) || byTitle(a, b),
      year_asc: (a, b) => yr(a, 9999) - yr(b, 9999) || byTitle(a, b),
      title_asc: byTitle,
      title_desc: (a, b) => byTitle(b, a)
    };
    rows.sort(sorters[state.sort] || ((a, b) => b.score - a.score || byTitle(a, b)));

    // Facet counts come from the rows that survived.
    const lists = {};
    for (const field of Object.keys(LOCAL_FACETS)) {
      const counts = new Map();
      for (const row of rows) for (const v of facetValues(row.item, field)) counts.set(v, (counts.get(v) || 0) + 1);
      lists[field] = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 8);
    }

    // Paging.
    const pages = Math.max(1, Math.ceil(rows.length / PER_PAGE));
    state.page = Math.min(Math.max(1, state.page), pages);
    const slice = rows.slice((state.page - 1) * PER_PAGE, state.page * PER_PAGE).map((row) => row.item);

    $('countHead').textContent = rows.length.toLocaleString() + ' result' + (rows.length === 1 ? '' : 's') + ' (local snapshot and weird shelf)';
    renderResults(slice);
    renderFacetBox(lists);
    renderPager(state.page, pages);
    setStatus('Done. Searched ' + local.items.length.toLocaleString() + ' local records. No API calls used.');
  }

  // Switch between local and live search. Facet filters do not carry over (different field names).
  function setSource(src) {
    if (src === 'local' && !local.ready) { setStatus('The local data files did not load.', true); src = 'live'; }
    state.src = src;
    state.filters = {};
    state.page = 1;
    runSearch();
  }

  // Keep the source menu and buttons in step with the state.
  function syncSourceUi() {
    $('srcSel').value = state.src;
    $('liveBtn').hidden = state.src === 'live';
    showBudget();
  }

  // ---------- 6. Drawing the page ----------
  // Pull the fields we need out of one API record.
  function readRecord(item) {
    const ogm = (item.attributes && item.attributes.ogm) || {};
    const ui = (item.meta && item.meta.ui) || {};
    return {
      kind: 'live',
      url: SITE_BASE + '/resources/' + encodeURIComponent(item.id),
      id: item.id,
      title: ogm.dct_title_s || '(untitled)',
      description: first(ogm.dct_description_sm) || '',
      provider: ogm.schema_provider_s || first(ogm.dct_publisher_sm) || first(ogm.dct_creator_sm) || '',
      resourceClass: (ogm.gbl_resourceClass_sm || []).join(', '),
      year: first(ogm.gbl_indexYear_im) || ogm.dct_issued_s || '',
      access: ogm.dct_accessRights_s || '',
      bbox: ogm.dcat_bbox || '',     // "minLon,minLat,maxLon,maxLat"
      // Image choice matters because of the rate limit. Measured October 2026:
      //   /static-map-assets/{hash}  -> not counted, cached for a year (free to show)
      //   /static-maps/{id}/geometry -> counted against the 10 per minute limit
      //   /resources/{id}/thumbnail  -> counted against the limit
      // So we only auto-load the first kind. Other images load on request.
      thumb: ui.static_map || '',
      citation: ui.citation || '',
      downloads: Array.isArray(ui.downloads) ? ui.downloads : [],
      sourceLinks: (ui.links && ui.links['Visit Source']) || []
    };
  }

  function render(json) {
    const meta = json.meta || {};
    const total = meta.totalCount || 0;
    $('countHead').textContent = total.toLocaleString() + ' result' + (total === 1 ? '' : 's');

    renderResults((json.data || []).map(readRecord));
    renderFacets(json.included || []);
    renderPager(meta.currentPage || 1, Math.min(meta.totalPages || 1, MAX_PAGE));
  }

  function renderResults(records) {
    const list = $('results');
    list.replaceChildren();
    resultsLayer.clearLayers();
    boxById.clear();

    if (!records.length) {
      list.append(el('li', { class: 'panel' }, 'No records matched. Remove a filter or try other words.'));
      return;
    }

    const bounds = [];
    for (const r of records) {
      const thumb = thumbCell(r); // null when the record has no preview image
      const body = r.kind === 'weird' ? weirdBody(r.weird) : bodyCell(r);
      const card = el('li', { class: 'card' + (thumb ? '' : ' nothumb'), id: 'rec-' + r.id }, thumb, body);
      list.append(card);

      // Draw the record's bounding box on the map.
      const parts = boxParts(r.bbox);
      if (parts.length) {
        // A featureGroup holds one rectangle, or two when the box crosses the antimeridian.
        const group = L.featureGroup(parts.map((p) => L.rectangle(p, { color: '#ff00ff', weight: 2, fillOpacity: 0.1 })));
        group.bindPopup(el('a', { href: safeUrl(r.url) || '#', target: '_blank', rel: 'noopener' }, r.title));
        group.on('click', () => highlight(r.id));
        resultsLayer.addLayer(group);
        boxById.set(r.id, group);
        // Boxes that cross the antimeridian are skipped when zooming to results,
        // because they would stretch the view around the whole globe.
        if (parts.length === 1) bounds.push(parts[0][0], parts[0][1]);
      }
    }
    if (bounds.length && !state.near) map.fitBounds(L.latLngBounds(bounds), { maxZoom: 9, padding: [20, 20] });
  }

  // Leaflet needs plain boxes. Split a box that crosses the antimeridian into two.
  // Returns a list of [[south, west], [north, east]] boxes (empty when there is no box).
  function boxParts(text) {
    const box = parseBbox(text);
    if (!box) return [];
    const [[south, west], [north, east]] = box;
    if (west <= east) return [box];
    return [[[south, west], [north, 180]], [[south, -180], [north, east]]];
  }

  function thumbCell(r) {
    const src = safeUrl(r.thumb);
    if (!src) return null;

    const alt = 'Preview map for ' + r.title;
    // Free images (see readRecord) load right away.
    if (new URL(src).pathname.startsWith('/api/v1/static-map-assets/')) {
      return el('img', { src: src, alt: alt, loading: 'lazy', width: 110, height: 110 });
    }
    // Counted images wait for a click, and the click is charged to the API budget.
    const btn = el('button', { type: 'button', class: 'btn', title: 'Uses 1 of 8 API calls per minute' }, 'Load preview');
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      await waitForBudget();
      budgetLog.push(Date.now());
      showBudget();
      btn.replaceWith(el('img', { src: src, alt: alt, width: 110, height: 110 }));
    });
    return btn;
  }

  function bodyCell(r) {
    const recordUrl = safeUrl(r.url) || '#';
    const metaBits = [r.provider, r.resourceClass, r.year].filter(Boolean).join(' | ');

    // Access row: where can I get this? Each link comes straight from the record.
    const access = el('div', { class: 'access' });
    if (r.access) access.append(el('span', { class: 'badge' + (/restricted/i.test(r.access) ? ' restricted' : '') }, r.access));
    for (const link of r.sourceLinks) {
      const url = safeUrl(link.url);
      if (url) access.append(el('a', { href: url, target: '_blank', rel: 'noopener' }, link.label || 'Visit source'));
    }
    for (const dl of r.downloads) {
      const url = safeUrl(dl.url);
      if (url) access.append(el('a', { href: url, target: '_blank', rel: 'noopener' }, 'Download: ' + (dl.label || 'file')));
    }

    const body = el('div', {},
      el('h3', {}, el('a', { href: recordUrl, target: '_blank', rel: 'noopener' }, r.title)),
      el('p', { class: 'meta' }, metaBits),
      el('p', { class: 'desc' }, truncate(r.description, 240)),
      access
    );

    // Only records with a bounding box can be shown on the map.
    if (parseBbox(r.bbox)) {
      const showBtn = el('button', { type: 'button', class: 'btn' }, 'Show on map');
      showBtn.addEventListener('click', () => {
        const rect = boxById.get(r.id);
        if (rect) { map.fitBounds(rect.getBounds(), { maxZoom: 10 }); rect.openPopup(rect.getBounds().getCenter()); highlight(r.id); }
      });
      body.append(showBtn);
    }
    if (r.citation) body.append(el('details', {}, el('summary', {}, 'Cite'), el('p', {}, r.citation)));
    return body;
  }

  // bbox text "minLon,minLat,maxLon,maxLat" -> [[minLat,minLon],[maxLat,maxLon]] for Leaflet.
  function parseBbox(text) {
    const n = String(text || '').split(',').map(Number);
    if (n.length !== 4 || n.some((v) => !Number.isFinite(v))) return null;
    return [[n[1], n[0]], [n[3], n[2]]];
  }

  function highlight(id) {
    document.querySelectorAll('.card.hot').forEach((c) => c.classList.remove('hot'));
    const card = $('rec-' + id);
    if (card) { card.classList.add('hot'); card.scrollIntoView({ block: 'nearest' }); }
  }

  // Live API: pull each facet's list out of the "included" part of the answer.
  function renderFacets(included) {
    const lists = {};
    for (const field of Object.keys(FACETS)) {
      const facet = included.find((x) => x.type === 'facet' && x.id === field);
      lists[field] = ((facet && facet.attributes && facet.attributes.items) || []);
    }
    renderFacetBox(lists);
  }

  // Draw the filter lists. lists is { fieldName: [[value, count], ...] }. Used by both sources.
  function renderFacetBox(lists) {
    renderActiveFilters();
    const box = $('facets');
    box.replaceChildren();
    for (const [field, items] of Object.entries(lists)) {
      if (!items.length) continue;
      const list = el('ul');
      for (const [value, count] of items.slice(0, 8)) {
        const isOn = state.filters[field] === String(value);
        const btn = el('button', { type: 'button', class: 'linkbtn', 'aria-pressed': String(isOn) }, String(value));
        btn.addEventListener('click', () => { setFilter(field, isOn ? null : String(value)); });
        list.append(el('li', {}, btn, ' ', el('span', { class: 'num' }, '(' + Number(count).toLocaleString() + ')')));
      }
      box.append(el('div', { class: 'facet' }, el('h3', {}, facetLabel(field)), list));
    }
    if (!box.children.length) box.append(el('p', { class: 'small' }, 'No filters for this search.'));
  }

  // Friendly name for a filter field, depending on the active source.
  const facetLabel = (field) => (state.src === 'local' ? LOCAL_FACETS : FACETS)[field] || field;

  function renderActiveFilters() {
    const box = $('active');
    box.replaceChildren();
    for (const [field, value] of Object.entries(state.filters)) {
      const chip = el('button', { type: 'button', class: 'chip', title: 'Remove filter' }, facetLabel(field) + ': ' + value + ' x');
      chip.addEventListener('click', () => setFilter(field, null));
      box.append(chip);
    }
  }

  function setFilter(field, value) {
    if (value == null) delete state.filters[field]; else state.filters[field] = value; // one value per field
    state.page = 1;
    runSearch();
  }

  function renderPager(page, pages) {
    const nav = $('pager');
    nav.replaceChildren();
    if (pages <= 1) return;
    const prev = el('button', { type: 'button', class: 'btn', disabled: page <= 1 }, '< Previous');
    const next = el('button', { type: 'button', class: 'btn', disabled: page >= pages }, 'Next >');
    prev.addEventListener('click', () => { state.page = page - 1; runSearch(); });
    next.addEventListener('click', () => { state.page = page + 1; runSearch(); });
    const capNote = state.src === 'live' && pages >= MAX_PAGE ?' (paging stops at ' + MAX_PAGE + '; add filters to narrow)' : '';
    nav.append(prev, el('span', {}, 'Page ' + page + ' of ' + pages + capNote), next);
  }

  // ---------- 7. Map tools ----------
  function searchNearCenter() {
    const c = map.getCenter();
    state.near = { lat: +c.lat.toFixed(4), lon: +c.lng.toFixed(4), km: Number($('radiusSel').value) };
    state.page = 1;
    drawPlace();
    runSearch();
  }

  function drawPlace() {
    placeLayer.clearLayers();
    $('clearNear').hidden = !state.near;
    if (!state.near) return;
    const circle = L.circle([state.near.lat, state.near.lon], { radius: state.near.km * 1000, color: '#00ccff', weight: 2, fillOpacity: 0.05 });
    placeLayer.addLayer(circle);
    map.fitBounds(circle.getBounds());
  }

  // Density hexagons: count records per H3 cell in view.
  // Local mode counts the records in the JSON file (no API call).
  // Live mode asks the API.
  async function showDensity() {
    if (!window.h3) { setStatus('The h3-js library did not load, so density is unavailable.', true); return; }
    setStatus('Loading density...');
    try {
      const b = map.getBounds();
      const z = map.getZoom();
      const resolution = z <= 3 ? 2 : z <= 5 ? 3 : z <= 7 ? 4 : z <= 9 ? 5 : 6; // finer hexagons when zoomed in
      let hexes; // [[cellId, count], ...]
      if (state.src === 'local') {
        // Count each matching record once, in the cell that holds its box center.
        const counts = new Map();
        for (const row of localRows()) {
          const c = row.item.center;
          if (!c || c.lat < b.getSouth() || c.lat > b.getNorth() || c.lon < b.getWest() || c.lon > b.getEast()) continue;
          const cell = window.h3.latLngToCell(c.lat, c.lon, resolution);
          counts.set(cell, (counts.get(cell) || 0) + 1);
        }
        hexes = [...counts.entries()];
      } else {
        const params = buildParams({
          bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(3)).join(','),
          resolution: resolution
        });
        const json = await apiGet('/map/h3', params);
        hexes = json.hexes || [];
      }
      hexLayer.clearLayers();
      const max = Math.max(1, ...hexes.map((h) => h[1]));
      for (const [cell, count] of hexes) {
        const outline = window.h3.cellToBoundary(cell); // list of [lat, lng]
        const poly = L.polygon(outline, { color: '#ff6600', weight: 1, fillOpacity: 0.15 + 0.6 * (count / max) });
        poly.bindTooltip(count.toLocaleString() + ' records');
        hexLayer.addLayer(poly);
      }
      $('hexClear').hidden = false;
      setStatus('Density shows ' + hexes.length + ' cells for the current view.');
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  // ---------- 8. CSV layers ----------
  // Reads a CSV in the browser. Needs a latitude and a longitude column.
  const csvLayers = [];
  const LAT_NAMES = ['latitude', 'lat', 'y'];
  const LON_NAMES = ['longitude', 'lon', 'lng', 'long', 'x'];
  const TITLE_NAMES = ['title', 'location', 'name', 'report_number'];
  const TEXT_NAMES = ['description', 'observed', 'summary', 'location_details'];
  const MAX_ROWS = 20000; // keeps the map responsive

  // Find the first column name that matches a list of candidates, ignoring case.
  function findColumn(fields, candidates) {
    return candidates.map((c) => fields.find((f) => f.toLowerCase() === c)).find(Boolean) || null;
  }

  function loadCsv(file) {
    setStatus('Reading ' + file.name + '...');
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (result) => {
        const fields = result.meta.fields || [];
        const latCol = findColumn(fields, LAT_NAMES);
        const lonCol = findColumn(fields, LON_NAMES);
        if (!latCol || !lonCol) {
          setStatus('No latitude and longitude columns found in ' + file.name + '.', true);
          return;
        }
        const titleCol = findColumn(fields, TITLE_NAMES);
        const textCol = findColumn(fields, TEXT_NAMES);
        const layer = L.layerGroup();
        let drawn = 0;
        for (const row of result.data.slice(0, MAX_ROWS)) {
          const lat = parseFloat(row[latCol]);
          const lon = parseFloat(row[lonCol]);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue; // skip rows without coordinates
          const dot = L.circleMarker([lat, lon], { radius: 4, color: '#00ff66', weight: 1, fillOpacity: 0.7 });
          dot.bindPopup(el('div', {},
            el('strong', {}, (titleCol && row[titleCol]) || file.name),
            el('p', {}, truncate((textCol && row[textCol]) || '', 300))
          ));
          layer.addLayer(dot);
          drawn += 1;
        }
        layer.addTo(map);
        csvLayers.push(layer);
        addLayerListItem(file.name, drawn, layer);
        const capped = result.data.length > MAX_ROWS ? ' (first ' + MAX_ROWS.toLocaleString() + ' rows only)' : '';
        setStatus('Added ' + drawn.toLocaleString() + ' points from ' + file.name + capped + '.');
      },
      error: (err) => setStatus('Could not read the file: ' + err.message, true)
    });
  }

  function addLayerListItem(name, count, layer) {
    const remove = el('button', { type: 'button', class: 'btn' }, 'Remove');
    const item = el('li', {}, el('span', {}, name + ' (' + count.toLocaleString() + ')'), remove);
    remove.addEventListener('click', () => { map.removeLayer(layer); item.remove(); });
    $('layerList').append(item);
  }

  // ---------- 8b. Weird data shelf ----------
  // The catalog lives in data/weird-catalog.json. Drawing it makes no API calls.
  // The same entries also show up in local search results (see weirdItem above).
  const FIT_LABELS = {
    'csv-layer': 'Load as CSV layer',
    'live': 'Live service',
    'geocode': 'Needs geocoding',
    'link-only': 'Link only',
    'reference': 'Background reference'
  };
  const SPATIAL_LABELS = {
    points: 'Points', geocode: 'Place names only', tracks: 'Lines or tracks',
    service: 'Live service', region: 'Region level', sky: 'Sky coordinates'
  };

  // Build the card body for one catalog entry. Used by the shelf and by search results.
  function weirdBody(d) {
    const meta = [d.theme, SPATIAL_LABELS[d.spatial] || d.spatial, d.size].filter(Boolean).join(' | ');
    const body = el('div', {},
      el('h3', {}, el('a', { href: safeUrl(d.url) || '#', target: '_blank', rel: 'noopener' }, d.title)),
      el('p', { class: 'meta' }, meta),
      el('div', { class: 'access' },
        el('span', { class: 'badge' }, FIT_LABELS[d.fit] || d.fit),
        el('span', { class: 'badge' + (d.checked === 'page read' ? '' : ' restricted') }, d.checked === 'page read' ? 'Page read' : 'Listed only')
      ),
      el('p', { class: 'desc' }, 'License: ' + (d.license || 'unknown')),
      el('p', { class: 'desc' }, d.note || ''),
      d.via ? el('p', { class: 'small' }, 'Found via: ' + d.via) : null,
      d.record ? el('p', { class: 'small' },
        el('a', { href: REPO_EDIT_BASE + d.record, target: '_blank', rel: 'noopener' }, 'Edit this record')) : null
    );
    // Entries with sub-layers get a collapsible table.
    if (Array.isArray(d.layers) && d.layers.length) {
      const rows = d.layers.map(([name, count, source, lic]) =>
        el('li', {}, name + ': ' + Number(count).toLocaleString() + ' (' + source + ', ' + lic + ')'));
      body.append(el('details', {}, el('summary', {}, d.layers.length + ' categories'), el('ul', {}, ...rows)));
    }
    return body;
  }

  function renderShelf() {
    const catalog = local.weird;
    const themeSel = $('themeSel');

    // Fill the theme menu once, from the themes found in the catalog.
    if (themeSel.options.length === 1) {
      [...new Set(catalog.map((d) => d.theme))].forEach((t) => themeSel.append(el('option', { value: t }, t)));
    }

    const theme = themeSel.value;
    const fit = $('fitSel').value;
    const shown = catalog.filter((d) => (!theme || d.theme === theme) && (!fit || d.fit === fit));
    $('shelfCount').textContent = shown.length + ' of ' + catalog.length + ' datasets';

    const list = $('shelf');
    list.replaceChildren();
    for (const d of shown) list.append(el('li', { class: 'card shelfcard nothumb' }, weirdBody(d)));
  }

  // "Add a dataset" helper. Builds an Aardvark record (see aardvark.js) you save under metadata-aardvark/.
  // Nothing is saved or sent anywhere: the page only prints text for you to copy.
  const slug = (text) => fold(text).replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);

  // Fill the menus in the helper from the lists in the catalog file, so the two never drift apart.
  function setupAddForm() {
    const meta = local.weirdMeta;
    const fillMenu = (id, values, labels) => {
      const menu = $(id);
      menu.replaceChildren();
      (values || []).forEach((v) => menu.append(el('option', { value: v }, (labels && labels[v]) || v)));
    };
    fillMenu('addTheme', meta.themes);
    fillMenu('addSpatial', meta.spatial, SPATIAL_LABELS);
    fillMenu('addFit', meta.fit, FIT_LABELS);
    fillMenu('addChecked', meta.checked);
  }

  function makeCatalogEntry(form) {
    const get = (name) => String(form.elements[name].value || '').trim();
    const url = safeUrl(get('url'));
    if (!get('title') || !url) return null;
    const entry = {
      id: slug(get('title')),
      title: get('title'),
      theme: get('theme'),
      spatial: get('spatial'),
      size: get('size'),
      license: get('license') || 'Unknown. Check before reuse',
      checked: get('checked'),
      fit: get('fit'),
      url: url,
      via: get('via'),
      note: get('note')
    };
    if (local.weird.some((d) => d.id === entry.id)) entry.id += '-2'; // ids must be unique
    return entry;
  }

  // ---------- 9. State in the URL, counter, start up ----------
  // Putting the search in the URL hash makes searches linkable on a static site.
  function writeHash() {
    const p = new URLSearchParams();
    if (state.src === 'live') p.set('src', 'live'); // local is the default, so it is left out
    if (state.q) p.set('q', state.q);
    if (state.page > 1) p.set('page', state.page);
    if (state.sort !== 'relevance') p.set('sort', state.sort);
    for (const [field, value] of Object.entries(state.filters)) p.set('f.' + field, value);
    if (state.near) p.set('near', [state.near.lat, state.near.lon, state.near.km].join(','));
    history.replaceState(null, '', p.toString() ? '#' + p.toString() : location.pathname + location.search);
  }

  function readHash() {
    const p = new URLSearchParams(location.hash.replace(/^#/, ''));
    state.src = p.get('src') === 'live' ? 'live' : 'local';
    state.q = p.get('q') || '';
    state.page = Math.max(1, Math.min(state.src === 'live' ? MAX_PAGE : 9999, parseInt(p.get('page'), 10) || 1));
    state.sort = p.get('sort') || 'relevance';
    state.filters = {};
    for (const [key, value] of p.entries()) {
      if (key.startsWith('f.')) state.filters[key.slice(2)] = value;
    }
    const near = (p.get('near') || '').split(',').map(Number);
    state.near = near.length === 3 && near.every(Number.isFinite) ? { lat: near[0], lon: near[1], km: near[2] } : null;
    $('q').value = state.q;
    $('sortSel').value = state.sort;
    return Boolean(state.q || Object.keys(state.filters).length || state.near);
  }

  // Visitor counter. Counts visits in THIS browser only (localStorage).
  function bumpCounter() {
    let n = 1;
    try {
      n = (parseInt(localStorage.getItem('geocities-visits'), 10) || 0) + 1;
      localStorage.setItem('geocities-visits', String(n));
    } catch (e) { /* storage blocked: show 1 */ }
    $('counter').textContent = String(n).padStart(6, '0');
  }

  // Wire up the controls.
  $('searchForm').addEventListener('submit', (event) => {
    event.preventDefault(); // stop the browser from reloading the page
    state.q = $('q').value.trim();
    state.sort = $('sortSel').value;
    state.page = 1;
    runSearch();
  });
  $('sortSel').addEventListener('change', () => { state.sort = $('sortSel').value; state.page = 1; runSearch(); });
  $('srcSel').addEventListener('change', () => setSource($('srcSel').value));
  $('liveBtn').addEventListener('click', () => setSource('live')); // same words, live API
  $('addForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const entry = makeCatalogEntry(event.target);
    $('addOut').value = entry
      ? JSON.stringify(GDGAardvark.toAardvark(entry, new Date().toISOString().replace(/\.\d+Z$/, 'Z')), null, 2)
      : 'Enter a title and a web address that starts with http:// or https://.';
    $('addPath').textContent = entry ? 'Save as ' + GDGAardvark.pathFor(entry) : '';
    $('addCopy').hidden = !entry;
  });
  $('addCopy').addEventListener('click', () => {
    const text = $('addOut').value;
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => setStatus('Copied. Save it as the file named above.'), () => $('addOut').select());
    else $('addOut').select();
  });
  $('nearBtn').addEventListener('click', searchNearCenter);
  $('clearNear').addEventListener('click', () => { state.near = null; state.page = 1; drawPlace(); runSearch(); });
  $('hexBtn').addEventListener('click', showDensity);
  $('hexClear').addEventListener('click', () => { hexLayer.clearLayers(); $('hexClear').hidden = true; });
  $('csvInput').addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (file) loadCsv(file);
    event.target.value = ''; // lets the same file be chosen again
  });
  document.querySelectorAll('[data-q]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.q = btn.dataset.q;
      if (btn.dataset.src) state.src = btn.dataset.src; // some links only make sense locally
      if (state.src === 'local' && !local.ready) state.src = 'live';
      // The two sources name the resource class filter differently.
      const classField = state.src === 'local' ? 'c' : 'gbl_resourceClass_sm';
      state.filters = btn.dataset.class ? { [classField]: btn.dataset.class } : {};
      state.near = null;
      state.page = 1;
      $('q').value = state.q;
      drawPlace();
      runSearch();
    });
  });

  $('themeSel').addEventListener('change', renderShelf);
  $('fitSel').addEventListener('change', renderShelf);

  bumpCounter();
  setInterval(showBudget, 1000); // keeps the "calls used" counter honest as the minute rolls over
  const hashHasSearch = readHash();

  // Load the JSON files, then draw the shelf and the first results.
  loadLocalData().then(() => {
    renderShelf();
    setupAddForm();
    if (state.src === 'local' || hashHasSearch) { drawPlace(); runSearch(); }
  }, (err) => { // second argument of then(): runs only if loading the files failed
    // Most common cause: the page was opened as a file instead of through a web server.
    state.src = 'live';
    $('srcSel').options[0].disabled = true;
    syncSourceUi();
    setStatus('Could not load the data files (' + err.message + '). Local search is off. Use a web server or GitHub Pages. Live API search still works.', true);
    if (hashHasSearch) { drawPlace(); runSearch(); }
  });
})();
