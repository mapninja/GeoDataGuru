#!/usr/bin/env python3
"""
Tests for aardvark_catalog.py and aardvark.js. Run from the repository root:

    python3 scripts/test_aardvark_catalog.py

No network needed. The JS comparison runs only when node is installed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aardvark_catalog as ac  # noqa: E402

failures = []


def check(name, got, want):
    """Print PASS or FAIL for one comparison."""
    if got == want:
        print('PASS', name)
    else:
        print('FAIL', name, '\n   got: ', got, '\n   want:', want)
        failures.append(name)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh)


def build_in(tmp):
    return ac.build_catalog(os.path.join(tmp, 'metadata-aardvark'), os.path.join(tmp, 'vocab.json'))


ENTRY = {
    'id': 'sample', 'title': 'Sample "quoted" dataset é', 'theme': 'Paranormal', 'spatial': 'points',
    'size': '10 records', 'license': 'CC BY 4.0', 'checked': 'page read', 'fit': 'csv-layer',
    'url': 'https://example.org/data', 'via': 'a friend', 'note': 'A note.',
    'layers': [['Caves', 12, 'OSM', 'ODbL 1.0'], ['Ghost towns', 3, 'OSM', 'ODbL 1.0']],
}
MODIFIED = '2026-10-30T00:00:00Z'

# ---- 1. entry -> record -> entry
rec = ac.to_aardvark(ENTRY, order=4, modified=MODIFIED)
check('record has the required Aardvark fields',
      [rec[k] for k in ('id', 'gbl_resourceClass_sm', 'dct_accessRights_s', 'gbl_mdVersion_s')],
      ['sample', ['Datasets'], 'Public', 'Aardvark'])
check('record url sits in dct_references_s', json.loads(rec['dct_references_s']), {ac.URL_KEY: 'https://example.org/data'})
check('record order', rec['gdg_order_i'], 4)
back, problems = ac.from_aardvark(rec)
check('round trip keeps the entry', back, ENTRY)
check('round trip has no problems', problems, [])
check('service goes to Web services', ac.record_path({'id': 'x', 'spatial': 'service'}),
      'metadata-aardvark/Web services/x.json')
check('points go to Datasets', ac.record_path(ENTRY), 'metadata-aardvark/Datasets/sample.json')

# ---- 2. records as Studio writes them: every field present, empty arrays, list-style references
studio = dict(rec)
studio.update({
    'dct_alternative_sm': [], 'dct_creator_sm': [], 'dct_spatial_sm': [], 'gbl_displayNote_sm': [],
    'dct_references_s': json.dumps({ac.URL_KEY: [{'url': 'https://example.org/data', 'label': 'home'}]}),
    'dct_description_sm': ['First part.', 'Second part.'],
})
back, problems = ac.from_aardvark(studio)
check('Studio-style url list is read', back['url'], 'https://example.org/data')
check('Studio-style descriptions are joined', back['note'], 'First part. Second part.')
check('Studio-style record has no problems', problems, [])

# ---- 3. what a bad record reports
_, problems = ac.from_aardvark({'id': 'x', 'dct_title_s': 'T'})
check('missing custom fields are named', [p for p in problems if 'gdg_' in p],
      ['missing gdg_theme_s', 'missing gdg_spatial_s', 'missing gdg_fit_s', 'missing gdg_checked_s'])
_, problems = ac.from_aardvark(dict(rec, gdg_layers_sm=['Caves | many | OSM | ODbL']))
check('bad layer row is reported', len(problems), 1)
try:
    ac.to_aardvark(dict(ENTRY, layers=[['A | B', 1, 'src', 'lic']]))
    check('layer separator in a name is refused', 'no error', 'ValueError')
except ValueError:
    check('layer separator in a name is refused', 'ValueError', 'ValueError')

# ---- 4. building from a folder
with tempfile.TemporaryDirectory() as tmp:
    json.dump({'schema': 1, 'themes': ['Paranormal']}, open(os.path.join(tmp, 'vocab.json'), 'w'))
    for entry_id, order in (('b-last', None), ('a-second', 2), ('z-first', 1)):
        e = dict(ENTRY, id=entry_id, layers=None)
        write(os.path.join(tmp, ac.record_path(e)), ac.to_aardvark(e, order=order, modified=MODIFIED))
    catalog, problems = build_in(tmp)
    check('clean folder builds without problems', problems, [])
    check('records sort by gdg_order_i, then id', [d['id'] for d in catalog['datasets']], ['z-first', 'a-second', 'b-last'])
    check('entries remember their file', catalog['datasets'][0]['record'], 'metadata-aardvark/Datasets/z-first.json')
    check('vocab becomes meta', catalog['meta'], {'schema': 1, 'themes': ['Paranormal']})

    # The same id in two folders (what happens if Studio moves a record to a new resource class).
    moved = dict(ac.to_aardvark(dict(ENTRY, id='z-first', spatial='service'), order=1), gbl_resourceClass_sm=['Maps'])
    write(os.path.join(tmp, 'metadata-aardvark', 'Maps', 'z-first.json'), moved)
    _, problems = build_in(tmp)
    check('duplicate id across folders is reported', any('duplicate id' in p for p in problems), True)
    os.remove(os.path.join(tmp, 'metadata-aardvark', 'Maps', 'z-first.json'))

    # File name must match the id, and the folder must match the first resource class.
    write(os.path.join(tmp, 'metadata-aardvark', 'Datasets', 'wrong-name.json'), ac.to_aardvark(dict(ENTRY, id='other')))
    write(os.path.join(tmp, 'metadata-aardvark', 'Maps', 'sample.json'), ac.to_aardvark(ENTRY))
    _, problems = build_in(tmp)
    check('id/file name mismatch is reported', any('does not match the file name' in p for p in problems), True)
    check('wrong folder is reported', any('first resource class' in p for p in problems), True)

    with open(os.path.join(tmp, 'metadata-aardvark', 'Datasets', 'broken.json'), 'w') as fh:
        fh.write('{oops')
    _, problems = build_in(tmp)
    check('broken JSON is reported', any('not valid JSON' in p for p in problems), True)

# ---- 5. the committed records
catalog, problems = ac.build_catalog()
check('committed records have no problems', problems, [])
check('every committed record is in its own folder', all(
    os.path.exists(os.path.join(ac.ROOT, d['record'])) for d in catalog['datasets']), True)
no_path = [{k: v for k, v in d.items() if k != 'record'} for d in catalog['datasets']]
again = [ac.from_aardvark(ac.to_aardvark(d, order=i, modified=MODIFIED))[0] for i, d in enumerate(no_path, 1)]
check('every committed entry survives entry -> record -> entry', again, no_path)

# ---- 6. the browser copy (aardvark.js) agrees with the Python version
if shutil.which('node'):
    js = ("const a = require(%s); const entries = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
          "console.log(JSON.stringify(entries.map(e => [a.toAardvark(e, %s), a.pathFor(e)])));"
          % (json.dumps(os.path.join(os.path.dirname(HERE), 'aardvark.js')), json.dumps(MODIFIED)))
    samples = no_path + [ENTRY, {k: v for k, v in ENTRY.items() if k in ('id', 'title', 'url', 'spatial')}]
    result = subprocess.run(['node', '-e', js], input=json.dumps(samples), capture_output=True, text=True)
    check('node ran aardvark.js', result.returncode, 0)
    if result.returncode == 0:
        pairs = json.loads(result.stdout)
        want = [[ac.to_aardvark(e, modified=MODIFIED), ac.record_path(e)] for e in samples]
        check('aardvark.js matches to_aardvark and record_path for %d entries' % len(samples), pairs, want)
else:
    print('SKIP aardvark.js comparison (node not installed)')

print('\n%d failure(s)' % len(failures))
sys.exit(1 if failures else 0)
