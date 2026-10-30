#!/usr/bin/env python3
"""
Keeps the weird shelf as OpenGeoMetadata Aardvark records.

The records in metadata-aardvark/ are the source of truth. One JSON file per
dataset, in the layout that OGM Metadata Studio reads and writes:

    metadata-aardvark/<Resource class>/<id>.json

The page does not read those files one by one. This script gathers them into
data/weird-catalog.json, which is the file app.js loads. Do not edit that file
by hand: the next build overwrites it.

    python3 scripts/aardvark_catalog.py build   # records -> data/weird-catalog.json
    python3 scripts/aardvark_catalog.py check   # is the built file up to date?
    python3 scripts/aardvark_catalog.py split   # one-time move: catalog -> records

Fields with no Aardvark equivalent (fit, checked, size, via, layers, order) are
stored as extra fields that start with gdg_. Studio keeps unknown fields when it
imports and exports, so they survive an edit there.

Needs only Python 3.9+. No packages.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS_DIR = os.path.join(ROOT, 'metadata-aardvark')
VOCAB = os.path.join(ROOT, 'data', 'weird-vocab.json')
CATALOG = os.path.join(ROOT, 'data', 'weird-catalog.json')

# Most entries are datasets. A live service is an Aardvark "Web services" record.
RESOURCE_CLASS = {'service': 'Web services'}
DEFAULT_CLASS = 'Datasets'
# Only where Aardvark has a matching word. Other shapes get no resource type.
RESOURCE_TYPE = {'points': 'Point data', 'tracks': 'Line data'}
PROVIDER = 'Weird shelf'
URL_KEY = 'http://schema.org/url'
LAYER_SEP = ' | '
NO_ORDER = 10 ** 9   # records without gdg_order_i go after the numbered ones


def folder_name(resource_class):
    """Studio names the folder after the first resource class and drops odd characters."""
    return re.sub(r'[^a-zA-Z0-9 _-]', '', resource_class or '') or 'Uncategorized'


def resource_class(entry):
    return RESOURCE_CLASS.get(entry.get('spatial'), DEFAULT_CLASS)


def record_path(entry):
    """Repo-relative path where this entry's record belongs."""
    return 'metadata-aardvark/%s/%s.json' % (folder_name(resource_class(entry)), entry['id'])


# ---------------------------------------------------------------- catalog entry -> Aardvark
def to_aardvark(entry, order=None, modified=None):
    """One weird shelf entry (the shape app.js uses) becomes one Aardvark record."""
    rec = {
        'id': entry['id'],
        'dct_title_s': entry['title'],
        'gbl_resourceClass_sm': [resource_class(entry)],
        'dct_accessRights_s': 'Public',
        'gbl_mdVersion_s': 'Aardvark',
        'schema_provider_s': PROVIDER,
        'dct_references_s': json.dumps({URL_KEY: entry['url']}, separators=(',', ':'), ensure_ascii=False),
    }
    if entry.get('note'):
        rec['dct_description_sm'] = [entry['note']]
    if RESOURCE_TYPE.get(entry.get('spatial')):
        rec['gbl_resourceType_sm'] = [RESOURCE_TYPE[entry['spatial']]]
    if entry.get('theme'):
        rec['dcat_keyword_sm'] = [entry['theme']]   # a copy for other Aardvark tools. gdg_theme_s is what the page reads.
    if entry.get('license'):
        rec['dct_rights_sm'] = [entry['license']]
    if modified:
        rec['gbl_mdModified_dt'] = modified
    for key, field in (('theme', 'gdg_theme_s'), ('spatial', 'gdg_spatial_s'), ('fit', 'gdg_fit_s'),
                       ('checked', 'gdg_checked_s'), ('size', 'gdg_size_s'), ('via', 'gdg_via_s')):
        if entry.get(key):
            rec[field] = entry[key]
    if entry.get('layers'):
        rows = []
        for name, count, source, lic in entry['layers']:
            if LAYER_SEP in str(name) or LAYER_SEP in str(source):
                raise ValueError('%s: layer name and source cannot contain "%s"' % (entry['id'], LAYER_SEP))
            rows.append(LAYER_SEP.join([str(name), str(count), str(source), str(lic)]))
        rec['gdg_layers_sm'] = rows
    if order is not None:
        rec['gdg_order_i'] = order
    return rec


# ---------------------------------------------------------------- Aardvark -> catalog entry
def _one(rec, key):
    value = rec.get(key)
    return value.strip() if isinstance(value, str) else ''


def _many(rec, key):
    value = rec.get(key)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _url_from_references(rec):
    """The page address lives in dct_references_s, a JSON string. The value may be text or a list."""
    raw = rec.get('dct_references_s')
    try:
        refs = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return ''
    value = refs.get(URL_KEY) if isinstance(refs, dict) else None
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get('url')
    return value.strip() if isinstance(value, str) else ''


def from_aardvark(rec):
    """Returns (entry, problems). problems lists what is wrong with this one record."""
    problems = []
    entry = {
        'id': _one(rec, 'id'),
        'title': _one(rec, 'dct_title_s'),
        'theme': _one(rec, 'gdg_theme_s'),
        'spatial': _one(rec, 'gdg_spatial_s'),
        'size': _one(rec, 'gdg_size_s'),
        'license': '; '.join(_many(rec, 'dct_rights_sm')),
        'checked': _one(rec, 'gdg_checked_s'),
        'fit': _one(rec, 'gdg_fit_s'),
        'url': _url_from_references(rec),
        'via': _one(rec, 'gdg_via_s'),
        'note': ' '.join(_many(rec, 'dct_description_sm')),
    }
    for key, label in (('id', 'id'), ('title', 'dct_title_s'), ('theme', 'gdg_theme_s'),
                       ('spatial', 'gdg_spatial_s'), ('fit', 'gdg_fit_s'), ('checked', 'gdg_checked_s'),
                       ('url', 'dct_references_s (needs a %s address)' % URL_KEY)):
        if not entry[key]:
            problems.append('missing %s' % label)
    layers = []
    for row in _many(rec, 'gdg_layers_sm'):
        parts = row.split(LAYER_SEP, 3)
        if len(parts) == 4 and parts[1].strip().isdigit():
            layers.append([parts[0].strip(), int(parts[1]), parts[2].strip(), parts[3].strip()])
        else:
            problems.append('gdg_layers_sm row "%s" must be: name | count | source | license' % row)
    if layers:
        entry['layers'] = layers
    return entry, problems


def check_record(rec, path):
    """Structural checks on one Aardvark record, plus the same id/filename rule Studio's export follows."""
    problems = []
    if not isinstance(rec, dict):
        return ['must be a JSON object']
    classes = _many(rec, 'gbl_resourceClass_sm')
    if not classes:
        problems.append('missing gbl_resourceClass_sm')
    if not _one(rec, 'dct_accessRights_s'):
        problems.append('missing dct_accessRights_s')
    if _one(rec, 'gbl_mdVersion_s') != 'Aardvark':
        problems.append('gbl_mdVersion_s must be "Aardvark"')
    stem = os.path.splitext(os.path.basename(path))[0]
    if _one(rec, 'id') and _one(rec, 'id') != stem:
        problems.append('id "%s" does not match the file name "%s.json"' % (rec['id'], stem))
    if classes and os.path.basename(os.path.dirname(path)) != folder_name(classes[0]):
        problems.append('file is in folder "%s" but its first resource class is "%s"'
                        % (os.path.basename(os.path.dirname(path)), classes[0]))
    order = rec.get('gdg_order_i')
    if order is not None and (not isinstance(order, int) or isinstance(order, bool)):
        problems.append('gdg_order_i must be a whole number')
    return problems


# ---------------------------------------------------------------- build
def load_records(records_dir=RECORDS_DIR):
    """Every .json file under metadata-aardvark/, as (relative path, record or None, read problem)."""
    found = []
    for folder, dirs, files in os.walk(records_dir):
        dirs.sort()
        for name in sorted(files):
            if not name.endswith('.json'):
                continue
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, os.path.dirname(records_dir))
            try:
                with open(full, encoding='utf-8') as fh:
                    found.append((rel, json.load(fh), None))
            except ValueError as err:
                found.append((rel, None, 'not valid JSON (%s)' % err))
    return found


def build_catalog(records_dir=RECORDS_DIR, vocab_path=VOCAB):
    """Returns (catalog dict, problems). The catalog has the same shape app.js has always loaded."""
    problems = []
    try:
        with open(vocab_path, encoding='utf-8') as fh:
            meta = json.load(fh)
    except (OSError, ValueError) as err:
        return None, ['%s: cannot read (%s)' % (os.path.basename(vocab_path), err)]

    rows = []
    seen = {}
    for rel, rec, read_problem in load_records(records_dir):
        if read_problem:
            problems.append('%s: %s' % (rel, read_problem))
            continue
        for p in check_record(rec, rel):
            problems.append('%s: %s' % (rel, p))
        entry, entry_problems = from_aardvark(rec)
        entry['record'] = rel.replace(os.sep, '/')   # lets the page link to the file that holds this entry
        for p in entry_problems:
            problems.append('%s: %s' % (rel, p))
        if entry['id'] in seen:
            problems.append('%s: duplicate id, also in %s' % (rel, seen[entry['id']]))
        seen[entry['id']] = rel
        order = rec.get('gdg_order_i')
        rows.append((order if isinstance(order, int) else NO_ORDER, entry['id'], entry))
    rows.sort(key=lambda r: (r[0], r[1]))
    return {'meta': meta, 'datasets': [r[2] for r in rows]}, problems


def dump(data):
    """Same layout the catalog has always had: one-space indent, real accents."""
    return json.dumps(data, indent=1, ensure_ascii=False) + '\n'


def write_if_changed(path, text):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            if fh.read() == text:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return True


def catalog_is_current():
    """True when data/weird-catalog.json matches what the records would build."""
    built, _ = build_catalog()
    try:
        with open(CATALOG, encoding='utf-8') as fh:
            return built is not None and json.load(fh) == built
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------- commands
def cmd_build(_args):
    catalog, problems = build_catalog()
    if problems:
        print('%d problem(s) found. Nothing was written:' % len(problems))
        for p in problems:
            print('  -', p)
        return 1
    changed = write_if_changed(CATALOG, dump(catalog))
    print('%s %s (%d datasets)' % ('Wrote' if changed else 'Already up to date:',
                                   os.path.relpath(CATALOG, ROOT), len(catalog['datasets'])))
    return 0


def cmd_check(_args):
    if catalog_is_current():
        print('OK: data/weird-catalog.json matches metadata-aardvark/')
        return 0
    print('data/weird-catalog.json is out of date. Run: python3 scripts/aardvark_catalog.py build')
    return 1


def cmd_split(args):
    """One-time move from the hand-edited catalog to Aardvark records."""
    if os.path.isdir(RECORDS_DIR) and load_records() and not args.force:
        print('metadata-aardvark/ already has records. Use --force to overwrite them.')
        return 1
    with open(CATALOG, encoding='utf-8') as fh:
        data = json.load(fh)
    modified = args.modified or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for i, entry in enumerate(data['datasets'], start=1):
        rec = to_aardvark(entry, order=i, modified=modified)
        write_if_changed(os.path.join(ROOT, record_path(entry)), json.dumps(rec, indent=2, ensure_ascii=False) + '\n')
    meta = dict(data['meta'])
    meta['note'] = ('Generated into weird-catalog.json together with the records in metadata-aardvark/. '
                    'Lists the allowed values for theme, spatial, fit and checked. '
                    'Run python3 scripts/aardvark_catalog.py build after any change.')
    write_if_changed(VOCAB, dump(meta))
    print('Wrote %d records to metadata-aardvark/ and data/weird-vocab.json' % len(data['datasets']))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('build', help='write data/weird-catalog.json from metadata-aardvark/').set_defaults(run=cmd_build)
    sub.add_parser('check', help='exit 1 if data/weird-catalog.json is out of date').set_defaults(run=cmd_check)
    split = sub.add_parser('split', help='one-time: write records from the current catalog')
    split.add_argument('--force', action='store_true', help='overwrite existing records')
    split.add_argument('--modified', help='gbl_mdModified_dt value, e.g. 2026-10-30T00:00:00Z (default: now)')
    split.set_defaults(run=cmd_split)
    args = parser.parse_args()
    return args.run(args)


if __name__ == '__main__':
    sys.exit(main())
