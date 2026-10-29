#!/usr/bin/env python3
"""
Tests for harvest_ogm.py. Run from the geocities-geoportal folder:

    python3 scripts/test_harvest.py

No network needed. The test builds a tiny fake OGM repo in a temp folder,
runs the harvester against it, and checks the output.
"""
import json
import os
import subprocess
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harvest_ogm as h  # noqa: E402

failures = []


def check(name, got, want):
    """Print PASS or FAIL for one comparison."""
    if got == want:
        print('PASS', name)
    else:
        print('FAIL', name, '\n   got: ', got, '\n   want:', want)
        failures.append(name)


# ---- 1. bounding boxes
check('bbox basic', h.parse_bbox('ENVELOPE(-86.83,-86.22,42.25,41.76)'), '-86.83,41.76,-86.22,42.25')
check('bbox antimeridian', h.parse_bbox('ENVELOPE(179,-179,85,-75)'), '179,-75,-179,85')
check('bbox rounding', h.parse_bbox('ENVELOPE(-74.123456,-73.1,41.0,40.5)'), '-74.123,40.5,-73.1,41')
check('bbox junk', h.parse_bbox('not a box'), '')
check('bbox empty', h.parse_bbox(None), '')

# ---- 2. text cleaning
check('clean x000d', h.clean('Line one_x000d_ line two'), 'Line one line two')
nfd = unicodedata.normalize('NFD', 'Montréal')
check('clean NFC', h.clean(nfd), unicodedata.normalize('NFC', 'Montréal'))

# ---- 3. one full record, shaped like a real Aardvark file
raw = {
    'id': 'test-1',
    'dct_title_s': 'Map of Somewhere',
    'dct_description_sm': ['A' * 200],
    'schema_provider_s': 'Test University',
    'gbl_resourceClass_sm': ['Maps'],
    'gbl_indexYear_im': [1911],
    'dct_accessRights_s': 'Public',
    'dcat_bbox': 'ENVELOPE(-86.83,-86.22,42.25,41.76)',
    'dcat_keyword_sm': ['roads', 'rivers', 'roads'],
    'dct_subject_sm': ['Cartography'],
    'dct_spatial_sm': ['Michigan', 'Ohio'],
    'dct_references_s': json.dumps({
        'http://schema.org/url': 'https://example.edu/item/1',
        'http://schema.org/downloadUrl': [{'url': 'https://example.edu/dl/1.zip', 'label': 'zip'}],
    }),
}
rec = h.normalize(raw, 'edu.test')
check('record title', rec['t'], 'Map of Somewhere')
check('record desc trimmed', rec['d'], 'A' * 140 + '...')
check('record year', rec['y'], 1911)
check('record keywords unique', rec['k'], 'roads;rivers;Cartography')
check('record places', rec['s'], 'Michigan;Ohio')
check('record url', rec['u'], 'https://example.edu/item/1')
check('record download', rec['dl'], 'https://example.edu/dl/1.zip')
check('record repo', rec['r'], 'edu.test')

# Year falls back to dct_issued_s.
check('year fallback', h.normalize({'id': 'x', 'dct_issued_s': '1987-05-01'}, 'r')['y'], 1987)
# Missing everything must not crash.
check('empty record ok', h.normalize({}, 'r')['t'], '')
# Bad JSON in references must not crash.
check('bad refs ok', h.normalize({'dct_references_s': '{oops'}, 'r')['u'], '')

# ---- 4. full run against a fake repo
with tempfile.TemporaryDirectory() as tmp:
    for i in range(5):
        folder = os.path.join(tmp, 'edu.test', 'metadata-aardvark', 'Maps', 'abc')
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'rec%d.json' % i), 'w', encoding='utf-8') as fh:
            json.dump(dict(raw, id='test-%d' % i), fh)
    out = os.path.join(tmp, 'out.json')
    cmd = [sys.executable, os.path.join(HERE, 'harvest_ogm.py'), '--repos', 'edu.test',
           '--repos-dir', tmp, '--per-repo', '3', '--out', out]
    result = subprocess.run(cmd, capture_output=True, text=True)
    check('harvest exit code', result.returncode, 0)
    data = json.load(open(out, encoding='utf-8'))
    check('harvest kept 3', len(data['records']), 3)
    check('harvest meta repo count', data['meta']['repos'][0]['in_repo'], 5)

    out_full = os.path.join(tmp, 'full.json')
    subprocess.run(cmd[:-4] + ['--full', '--out', out_full], capture_output=True, text=True)
    check('full keeps all', len(json.load(open(out_full, encoding='utf-8'))['records']), 5)

# ---- 5. the committed data file still has the expected shape
path = os.path.join(os.path.dirname(HERE), 'data', 'ogm-subset.json')
if os.path.exists(path):
    committed = json.load(open(path, encoding='utf-8'))
    keys = set(h.normalize({}, 'r').keys())
    bad = [r['id'] for r in committed['records'] if set(r.keys()) != keys]
    check('committed records have the same keys as the harvester', bad[:3], [])

print('\n%d failure(s)' % len(failures))
sys.exit(1 if failures else 0)
