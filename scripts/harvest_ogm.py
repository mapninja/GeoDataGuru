#!/usr/bin/env python3
"""
Harvest OpenGeoMetadata (OGM) records into data/ogm-subset.json.

What this does, in plain words:
  1. Downloads each OGM repository listed in scripts/harvest_config.json
     (a shallow git clone, so it is fast and small).
  2. Reads the Aardvark JSON files in each repo's metadata-aardvark folder.
  3. Trims every record to the few fields the portal needs.
  4. Writes one compact JSON file that the web page loads.

Usage (run from the repository root):

    python3 scripts/harvest_ogm.py                  # sample: per_repo records from each repo
    python3 scripts/harvest_ogm.py --full           # keep every record (file gets large)
    python3 scripts/harvest_ogm.py --per-repo 40    # bigger sample
    python3 scripts/harvest_ogm.py --repos edu.osu edu.purdue
    python3 scripts/harvest_ogm.py --repos-dir ~/ogm   # use clones you already have

Needs: Python 3.9+ and git. No other packages.

Size guide: the sample of 16 records x 13 repos is about 100 KB. A full harvest of
the BTAA member repos is tens of thousands of records and many megabytes. GitHub
Pages serves that fine, but the page downloads the whole file, so keep it modest.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(HERE, 'harvest_config.json')
OUT_DEFAULT = os.path.join(ROOT, 'data', 'ogm-subset.json')

# Keys inside dct_references_s that we read.
REF_URL = 'http://schema.org/url'
REF_DOWNLOAD = 'http://schema.org/downloadUrl'


# ---------------------------------------------------------------- cleaning helpers
def clean(text):
    """Normalize accents (NFC), drop spreadsheet junk like _x000d_, collapse spaces."""
    text = unicodedata.normalize('NFC', str(text or ''))
    text = re.sub(r'_x000d_', ' ', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def first(value):
    """Many Aardvark fields are lists. Return the first item, or the value itself."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def uniq(items):
    """Remove empties and repeats but keep the original order."""
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def parse_bbox(text):
    """
    Aardvark writes a box as ENVELOPE(west,east,north,south).
    We store "minLon,minLat,maxLon,maxLat" rounded to 3 decimals.
    If west is greater than east, the box crosses the antimeridian (the 180 degree line).
    """
    text = str(text or '')
    m = re.search(r'ENVELOPE\(\s*([^)]+)\)', text, flags=re.IGNORECASE)
    try:
        if m:
            west, east, north, south = [float(v) for v in m.group(1).split(',')]
            nums = [west, south, east, north]
        else:
            nums = [float(v) for v in text.split(',')]
    except ValueError:
        return ''
    if len(nums) != 4:
        return ''
    return ','.join(('%.3f' % v).rstrip('0').rstrip('.') for v in nums)


def pick_url(value):
    """References can be a string, an object with a url, or a list of those."""
    if not value:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return pick_url(value[0]) if value else ''
    if isinstance(value, dict):
        return value.get('url', '') or ''
    return ''


# ---------------------------------------------------------------- the main conversion
def normalize(raw, repo):
    """Turn one raw Aardvark record into the small record the portal uses."""
    try:
        refs = json.loads(raw.get('dct_references_s') or '{}')
    except (TypeError, ValueError):
        refs = {}

    year = first(raw.get('gbl_indexYear_im'))
    if not year:
        m = re.search(r'\d{4}', str(raw.get('dct_issued_s') or ''))
        year = m.group(0) if m else None

    # Description: keep the first 140 characters so the data file stays small.
    desc = clean(first(raw.get('dct_description_sm')) or '')
    if len(desc) > 140:
        desc = desc[:140].strip() + '...'

    keywords = uniq((raw.get('dcat_keyword_sm') or []) + (raw.get('dct_subject_sm') or []))
    places = uniq(raw.get('dct_spatial_sm') or [])

    return {
        'id': raw.get('id', ''),
        't': clean(raw.get('dct_title_s')),
        'd': desc,
        'p': clean(raw.get('schema_provider_s') or first(raw.get('dct_publisher_sm')) or ''),
        'c': ', '.join(raw.get('gbl_resourceClass_sm') or []),
        'y': int(year) if year else None,
        'a': raw.get('dct_accessRights_s') or '',
        'b': parse_bbox(raw.get('dcat_bbox')),
        'k': ';'.join(keywords[:6]),
        's': ';'.join(places[:4]),
        'r': repo,
        'u': pick_url(refs.get(REF_URL)),
        'dl': pick_url(refs.get(REF_DOWNLOAD)),
    }


# ---------------------------------------------------------------- reading repos
def clone(repo, workdir):
    """Shallow-clone one OGM repo. Returns the folder path."""
    dest = os.path.join(workdir, repo)
    url = 'https://github.com/OpenGeoMetadata/%s.git' % repo
    print('  cloning', url)
    subprocess.run(['git', 'clone', '--depth', '1', '--quiet', url, dest], check=True)
    return dest


def list_files(repo_dir):
    """All record files under metadata-aardvark, sorted so runs are repeatable."""
    base = os.path.join(repo_dir, 'metadata-aardvark')
    found = []
    for folder, _dirs, files in os.walk(base):
        for name in files:
            if name.endswith('.json') and name != 'layers.json':
                found.append(os.path.join(folder, name))
    return sorted(found)


def class_folder(path, repo_dir):
    """First folder under metadata-aardvark, such as Maps or Imagery."""
    rel = os.path.relpath(path, os.path.join(repo_dir, 'metadata-aardvark'))
    parts = rel.split(os.sep)
    return parts[0].lower() if len(parts) > 1 else '_root'


def sample(records_by_class, keep):
    """
    Pick 'keep' records. Records with a bounding box come first, and we rotate
    through the resource classes so one class does not crowd out the others.
    """
    pools = {}
    for cls, recs in sorted(records_by_class.items()):
        with_box = [r for r in recs if r['b']]
        without = [r for r in recs if not r['b']]
        pools[cls] = with_box + without
    chosen = []
    while len(chosen) < keep and any(pools.values()):
        for cls in sorted(pools):
            if pools[cls] and len(chosen) < keep:
                chosen.append(pools[cls].pop(0))
    return chosen


def harvest_repo(repo_dir, repo, keep, full, fetch_per_repo):
    files = list_files(repo_dir)
    total = len(files)
    by_class = {}
    # For a sample we read an evenly spaced subset of files, which is much faster.
    if not full and total > fetch_per_repo:
        step = total / float(fetch_per_repo)
        files = [files[int(i * step)] for i in range(fetch_per_repo)]
    for path in files:
        try:
            with open(path, encoding='utf-8') as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as err:
            print('  skipped', path, err)
            continue
        rec = normalize(raw, repo)
        by_class.setdefault(class_folder(path, repo_dir), []).append(rec)
    if full:
        records = [r for recs in by_class.values() for r in recs]
    else:
        records = sample(by_class, keep)
    return records, total


# ---------------------------------------------------------------- writing
def write_output(path, records, repo_info, args):
    meta = {
        'schema': 1,
        'generated': datetime.date.today().isoformat(),
        'source': 'OpenGeoMetadata GitHub repositories (https://github.com/OpenGeoMetadata), Aardvark records in metadata-aardvark/',
        'method': ('Full harvest of every record.' if args.full else
                   'Per repo: read %d evenly spaced files, keep %d (records with a bounding box first, rotating through resource classes). A sample for demos, not a full harvest.' % (args.fetch_per_repo, args.per_repo)),
        'fields': {
            'id': 'record id', 't': 'title', 'd': 'description (trimmed)', 'p': 'provider', 'c': 'resource class',
            'y': 'year', 'a': 'access rights',
            'b': 'bbox minLon,minLat,maxLon,maxLat (west greater than east means it crosses the antimeridian)',
            'k': 'keywords and subjects, joined by ;', 's': 'place names, joined by ;', 'r': 'source OGM repo',
            'u': 'landing page URL', 'dl': 'first download URL'},
        'repos': repo_info,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('{\n"meta": ' + json.dumps(meta, ensure_ascii=False, indent=1) + ',\n"records": [\n')
        fh.write(',\n'.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) for r in records))
        fh.write('\n]\n}\n')


def main():
    config = json.load(open(CONFIG, encoding='utf-8'))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repos', nargs='*', default=config['repos'], help='OGM repo names, such as edu.osu')
    ap.add_argument('--per-repo', type=int, default=config.get('per_repo', 16), help='records to keep per repo')
    ap.add_argument('--fetch-per-repo', type=int, default=config.get('fetch_per_repo', 36), help='files to read per repo before choosing')
    ap.add_argument('--full', action='store_true', help='keep every record')
    ap.add_argument('--repos-dir', help='folder that already holds clones named like the repos')
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args()

    records, repo_info = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for repo in args.repos:
            print(repo)
            try:
                folder = os.path.join(args.repos_dir, repo) if args.repos_dir else clone(repo, tmp)
                recs, total = harvest_repo(folder, repo, args.per_repo, args.full, args.fetch_per_repo)
            except (subprocess.CalledProcessError, OSError) as err:
                print('  failed:', err)
                continue
            print('  %d of %d records kept' % (len(recs), total))
            records.extend(recs)
            repo_info.append({'repo': repo, 'kept': len(recs), 'in_repo': total})

    # The same id can appear twice if a record is listed in two repos. Keep the first.
    seen, unique = set(), []
    for r in records:
        key = (r['id'], r['r'])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    write_output(args.out, unique, repo_info, args)
    print('Wrote %d records to %s' % (len(unique), args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
