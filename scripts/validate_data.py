#!/usr/bin/env python3
"""
Checks the two data files before they go live. Run from the repository root:

    python3 scripts/validate_data.py

Exit code 0 means both files are fine. Exit code 1 means at least one problem,
and every problem is printed with the record it belongs to. The GitHub Actions
workflow runs this on every push and flags a typo in the JSON.

Needs only Python 3.9+. No packages.
"""
import json
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEIRD = os.path.join(ROOT, 'data', 'weird-catalog.json')
OGM = os.path.join(ROOT, 'data', 'ogm-subset.json')

problems = []


def bad(where, message):
    """Remember one problem. We list them all at the end instead of stopping at the first."""
    problems.append('%s: %s' % (where, message))


def is_web_url(value):
    """True for http and https addresses that have a host name."""
    try:
        u = urlparse(value)
    except ValueError:
        return False
    return u.scheme in ('http', 'https') and bool(u.netloc)


def load(path):
    """Read a JSON file. A syntax error is reported with its line number."""
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except FileNotFoundError:
        bad(os.path.basename(path), 'file not found')
    except json.JSONDecodeError as err:
        bad(os.path.basename(path), 'not valid JSON (line %d, column %d: %s)' % (err.lineno, err.colno, err.msg))
    return None


# ---------------------------------------------------------------- weird catalog
def check_weird(data):
    name = 'weird-catalog.json'
    meta = data.get('meta') or {}
    for key in ('themes', 'spatial', 'fit', 'checked'):
        if not isinstance(meta.get(key), list) or not meta.get(key):
            bad(name, 'meta.%s must be a non-empty list' % key)
    datasets = data.get('datasets')
    if not isinstance(datasets, list) or not datasets:
        bad(name, '"datasets" must be a non-empty list')
        return 0

    required = ['id', 'title', 'theme', 'spatial', 'license', 'checked', 'fit', 'url', 'note']
    seen = set()
    for i, d in enumerate(datasets):
        where = '%s entry %d (%s)' % (name, i + 1, d.get('id', '?') if isinstance(d, dict) else '?')
        if not isinstance(d, dict):
            bad(where, 'must be an object')
            continue
        for key in required:
            if not str(d.get(key, '')).strip():
                bad(where, 'missing "%s"' % key)
        if d.get('id'):
            if not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', d['id']):
                bad(where, 'id must be lowercase letters, numbers and hyphens')
            if d['id'] in seen:
                bad(where, 'duplicate id')
            seen.add(d['id'])
        # Each menu value must be one the catalog's meta lists (the page builds menus from them).
        for key, meta_key in (('theme', 'themes'), ('spatial', 'spatial'), ('fit', 'fit'), ('checked', 'checked')):
            if d.get(key) and d[key] not in (meta.get(meta_key) or []):
                bad(where, '%s "%s" is not in meta.%s' % (key, d[key], meta_key))
        if d.get('url') and not is_web_url(d['url']):
            bad(where, 'url must start with http:// or https://')
        layers = d.get('layers')
        if layers is not None:
            if not isinstance(layers, list):
                bad(where, 'layers must be a list')
            else:
                for j, layer in enumerate(layers):
                    if not (isinstance(layer, list) and len(layer) == 4 and isinstance(layer[1], int)):
                        bad(where, 'layers[%d] must be [name, count (integer), source, license]' % j)
    return len(datasets)


# ---------------------------------------------------------------- OGM snapshot
BBOX_KEYS = ('id', 't', 'd', 'p', 'c', 'y', 'a', 'b', 'k', 's', 'r', 'u', 'dl')


def check_bbox(where, text):
    """bbox is "minLon,minLat,maxLon,maxLat". West may be greater than east (antimeridian)."""
    try:
        w, s, e, n = [float(v) for v in text.split(',')]
    except ValueError:
        bad(where, 'bbox "%s" is not four numbers' % text)
        return
    if not (-180 <= w <= 180 and -180 <= e <= 180):
        bad(where, 'longitude out of range in "%s"' % text)
    if not (-90 <= s <= 90 and -90 <= n <= 90):
        bad(where, 'latitude out of range in "%s"' % text)
    if s > n:
        bad(where, 'south is greater than north in "%s"' % text)


def check_ogm(data):
    name = 'ogm-subset.json'
    if not isinstance(data.get('meta'), dict):
        bad(name, 'missing "meta"')
    records = data.get('records')
    if not isinstance(records, list) or not records:
        bad(name, '"records" must be a non-empty list')
        return 0
    seen = set()
    for i, r in enumerate(records):
        where = '%s record %d (%s)' % (name, i + 1, r.get('id', '?') if isinstance(r, dict) else '?')
        if not isinstance(r, dict):
            bad(where, 'must be an object')
            continue
        if set(r.keys()) != set(BBOX_KEYS):
            bad(where, 'keys differ from the expected set (%s)' % ', '.join(BBOX_KEYS))
            continue
        if not r['id']:
            bad(where, 'missing id')
        key = (r['id'], r['r'])
        if key in seen:
            bad(where, 'duplicate id within repo')
        seen.add(key)
        if not r['t']:
            bad(where, 'missing title')
        if r['b']:
            check_bbox(where, r['b'])
        if r['y'] is not None and not isinstance(r['y'], int):
            bad(where, 'year must be an integer or null')
        for url_key in ('u', 'dl'):
            if r[url_key] and not is_web_url(r[url_key]):
                bad(where, '%s is not a web address' % url_key)
        if '_x000d_' in json.dumps(r, ensure_ascii=False).lower():
            bad(where, 'contains the spreadsheet artifact _x000d_')
    return len(records)


def main():
    weird = load(WEIRD)
    ogm = load(OGM)
    n_weird = check_weird(weird) if isinstance(weird, dict) else 0
    n_ogm = check_ogm(ogm) if isinstance(ogm, dict) else 0
    if problems:
        print('%d problem(s) found:' % len(problems))
        for p in problems:
            print('  -', p)
        return 1
    print('OK: %d weird catalog entries, %d OGM records' % (n_weird, n_ogm))
    return 0


if __name__ == '__main__':
    sys.exit(main())
