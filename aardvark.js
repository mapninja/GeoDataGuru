// Turns a weird shelf entry into an OpenGeoMetadata Aardvark record.
// This is the browser copy of to_aardvark() in scripts/aardvark_catalog.py.
// Keep the two in step. scripts/test_aardvark_catalog.py runs both and compares them.
(function (root) {
  'use strict';

  const RESOURCE_CLASS = { service: 'Web services' };
  const RESOURCE_TYPE = { points: 'Point data', tracks: 'Line data' };
  const URL_KEY = 'http://schema.org/url';
  const LAYER_SEP = ' | ';

  const resourceClass = (entry) => RESOURCE_CLASS[entry.spatial] || 'Datasets';

  // Where the record belongs in the repository.
  const pathFor = (entry) =>
    'metadata-aardvark/' + resourceClass(entry).replace(/[^a-zA-Z0-9 _-]/g, '') + '/' + entry.id + '.json';

  // modified is an ISO date like 2026-10-30T00:00:00Z. Leave it out to skip gbl_mdModified_dt.
  function toAardvark(entry, modified) {
    const rec = {
      id: entry.id,
      dct_title_s: entry.title,
      gbl_resourceClass_sm: [resourceClass(entry)],
      dct_accessRights_s: 'Public',
      gbl_mdVersion_s: 'Aardvark',
      schema_provider_s: 'Weird shelf',
      dct_references_s: JSON.stringify({ [URL_KEY]: entry.url })
    };
    if (entry.note) rec.dct_description_sm = [entry.note];
    if (RESOURCE_TYPE[entry.spatial]) rec.gbl_resourceType_sm = [RESOURCE_TYPE[entry.spatial]];
    if (entry.theme) rec.dcat_keyword_sm = [entry.theme];
    if (entry.license) rec.dct_rights_sm = [entry.license];
    if (modified) rec.gbl_mdModified_dt = modified;
    const extras = [['theme', 'gdg_theme_s'], ['spatial', 'gdg_spatial_s'], ['fit', 'gdg_fit_s'],
      ['checked', 'gdg_checked_s'], ['size', 'gdg_size_s'], ['via', 'gdg_via_s']];
    for (const [key, field] of extras) {
      if (entry[key]) rec[field] = entry[key];
    }
    if (entry.layers && entry.layers.length) {
      rec.gdg_layers_sm = entry.layers.map(([name, count, source, license]) => {
        if (String(name).includes(LAYER_SEP) || String(source).includes(LAYER_SEP)) {
          throw new Error(entry.id + ': layer name and source cannot contain "' + LAYER_SEP + '"');
        }
        return [name, count, source, license].join(LAYER_SEP);
      });
    }
    return rec;
  }

  const api = { toAardvark, pathFor };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.GDGAardvark = api;
})(typeof window !== 'undefined' ? window : globalThis);
