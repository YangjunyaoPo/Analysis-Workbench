import {filterRecords} from './archive-filters.mjs';

const $ = id => document.getElementById(id);
const state = {records: [], current: null, dirty: false, busy: false, previewVersion: 0};

function notice(message, error = false) {
  $('archive-notice').textContent = message;
  $('archive-notice').classList.toggle('error', error);
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
}

function timestamp(value) {
  return value ? new Date(value).toLocaleString() : 'Not recorded';
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Request failed.');
  return result;
}

function updateControls() {
  for (const control of $('metadata-form').querySelectorAll('input, textarea, button')) control.disabled = state.busy;
  $('new-record').disabled = state.busy;
  $('files').disabled = state.busy || !state.current?.id || state.dirty;
  $('upload-help').textContent = !state.current?.id ? 'Save the record to add files.' : state.dirty
    ? 'Save metadata changes before adding files.'
    : 'Files are saved immediately. Up to 25 MiB per file, 100 files and 100 MiB per record. Unsupported formats remain available for download.';
  $('record-state').textContent = state.dirty ? 'Unsaved changes' : state.current?.id ? 'Saved locally' : 'Not saved';
}

async function run(operation) {
  if (state.busy) return;
  state.busy = true;
  updateControls();
  try { await operation(); }
  catch (error) { notice(error.message, true); }
  finally { state.busy = false; updateControls(); }
}

function canReplace() {
  return !state.dirty || window.confirm('Discard the unsaved metadata changes?');
}

function filters() {
  return {query: $('search').value, category: $('filter-category').value,
    kind: $('filter-kind').value, from: $('filter-from').value, to: $('filter-to').value,
    unknown: $('filter-unknown').checked, sort: $('sort').value};
}

function renderCatalog() {
  $('catalog').replaceChildren();
  let records;
  try { records = filterRecords(state.records, filters()); }
  catch (error) { notice(error.message, true); $('record-count').textContent = 'Invalid date range'; return; }
  $('record-count').textContent = `${records.length} of ${state.records.length} records`;
  for (const record of records) {
    const card = element('button', undefined, 'catalog-card');
    card.classList.toggle('selected', record.id === state.current?.id);
    card.setAttribute('aria-pressed', String(record.id === state.current?.id));
    card.append(element('h2', record.title));
    card.append(element('p', `${record.date || 'Unknown experiment date'} · ${record.category || 'Uncategorized'}`));
    card.append(element('p', `${record.materials.length} files · ${formatBytes(record.materials.reduce((sum, m) => sum + m.size, 0))}${record.hasAnalysis ? ' · Analysis saved' : ''}`));
    const names = record.materials.slice(0, 3).map(m => m.name).join(', ');
    if (names) card.append(element('p', names + (record.materials.length > 3 ? ', …' : '')));
    const tags = element('div', undefined, 'tag-row');
    for (const tag of record.tags) tags.append(element('span', tag, 'tag'));
    card.append(tags);
    card.addEventListener('click', () => run(() => openRecord(record.id)));
    $('catalog').append(card);
  }
  if (!records.length) $('catalog').append(element('p', state.records.length ? 'No matching records. Adjust or clear the filters.' : 'No records yet. Create one to start an archive.', 'muted'));
}

function updateCategories() {
  const selected = $('filter-category').value;
  const categories = [...new Set(state.records.map(r => r.category).filter(Boolean))].sort();
  $('filter-category').replaceChildren(new Option('All categories', ''));
  $('category-suggestions').replaceChildren();
  for (const category of categories) {
    $('filter-category').add(new Option(category, category));
    const suggestion = element('option'); suggestion.value = category;
    $('category-suggestions').append(suggestion);
  }
  if (categories.includes(selected)) $('filter-category').value = selected;
}

async function refreshCatalog() {
  const catalog = await request('/api/archive');
  state.records = catalog.records;
  updateCategories(); renderCatalog();
  return catalog.errors;
}

function closePreview() {
  state.previewVersion++;
  $('preview').hidden = true;
  $('preview-content').replaceChildren();
}

function fileURL(file) {
  return `/api/archive/${state.current.id}/files/${file.id}`;
}

async function preview(file) {
  const version = ++state.previewVersion;
  $('preview').hidden = false;
  $('preview-title').textContent = file.name;
  $('preview-content').replaceChildren(element('p', 'Loading preview…', 'muted'));
  const extension = file.name.split('.').at(-1).toLowerCase();
  const url = fileURL(file) + '?preview=1';
  if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'].includes(extension)) {
    const image = element('img');
    image.alt = file.name;
    image.addEventListener('error', () => {
      if (version === state.previewVersion) $('preview-content').replaceChildren(element('p', 'This image cannot be previewed. The original is still available for download.', 'muted'));
    });
    image.src = url;
    $('preview-content').replaceChildren(image);
  } else if (['csv', 'tsv', 'txt', 'md', 'json', 'log'].includes(extension)) {
    try {
      const result = await request(url);
      if (version !== state.previewVersion) return;
      $('preview-content').replaceChildren(element('pre', result.text));
      if (result.truncated) $('preview-content').prepend(element('p', 'Showing the first 64 KiB. Download the original for the complete content.', 'muted'));
    } catch (error) {
      if (version === state.previewVersion) $('preview-content').replaceChildren(element('p', error.message, 'muted'));
    }
  } else {
    $('preview-content').replaceChildren(element('p', 'Preview is unavailable for this format. Download the original to open it in another application.', 'muted'));
  }
}

function renderMaterials() {
  $('materials').replaceChildren();
  for (const file of state.current?.materials || []) {
    const row = element('article', undefined, 'material');
    const details = element('div');
    details.append(element('h3', file.name));
    details.append(element('p', `${file.kind} · ${formatBytes(file.size)} · Added: ${timestamp(file.addedAt)}`));
    if (file.originalBytesAvailable === false) details.append(element('p', 'Earlier review retained decoded CSV text only; original encoding bytes were not recorded.'));
    const integrity = element('details');
    integrity.append(element('summary', 'SHA-256 / file identity'), element('code', file.sha256));
    details.append(integrity);
    const actions = element('div', undefined, 'material-actions');
    const view = element('button', 'Preview');
    view.setAttribute('aria-label', `Preview ${file.name}`);
    view.addEventListener('click', () => preview(file));
    const download = element('a', 'Download'); download.href = fileURL(file);
    download.setAttribute('aria-label', `Download ${file.name}`);
    actions.append(view, download); row.append(details, actions); $('materials').append(row);
  }
  if (!state.current?.materials.length) $('materials').append(element('p', 'No files attached yet.', 'muted'));
}

function showRecord(record) {
  state.current = record; state.dirty = false;
  $('detail-empty').hidden = true; $('detail-content').hidden = false;
  $('detail-heading').textContent = record.id ? 'Record details' : 'New record';
  for (const key of ['title', 'date', 'category', 'notes']) $(key).value = record[key] || '';
  $('tags').value = (record.tags || []).join(', ');
  $('timestamps').textContent = record.id ? `Created: ${timestamp(record.createdAt)} · Last saved: ${timestamp(record.savedAt)}. Experiment date is recorded separately.` : '';
  $('export-record').hidden = !record.id;
  $('export-record').href = record.id ? `/api/archive/${record.id}/export` : '#';
  $('open-review').hidden = !record.hasReviewInputs;
  $('open-review').href = record.id ? `/?record=${record.id}` : '/';
  closePreview(); renderMaterials(); updateControls(); renderCatalog();
}

async function openRecord(identity) {
  if (!canReplace()) return;
  const record = await request(`/api/archive/${identity}`);
  showRecord(record);
  history.replaceState(null, '', `/archive#${identity}`);
  notice('Record opened. Original materials and saved analysis are retained.');
  if (window.matchMedia('(max-width: 720px)').matches) $('detail-content').scrollIntoView({behavior: 'smooth', block: 'start'});
}

function draft() {
  return {title: $('title').value, date: $('date').value, category: $('category').value,
    notes: $('notes').value, tags: $('tags').value.split(',').map(t => t.trim()).filter(Boolean),
    revision: state.current?.revision};
}

async function saveMetadata() {
  const path = '/api/archive' + (state.current?.id ? '/' + state.current.id : '');
  const record = await request(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Workbench-Request': '1'}, body: JSON.stringify(draft())});
  showRecord(record);
  history.replaceState(null, '', `/archive#${record.id}`);
  const errors = await refreshCatalog();
  notice(errors.length ? `Record saved. ${errors.length} other record(s) could not be read.` : 'Record metadata saved. You can now add files.', !!errors.length);
}

$('metadata-form').addEventListener('submit', event => {event.preventDefault(); run(saveMetadata);});
$('metadata-form').addEventListener('input', () => {state.dirty = true; updateControls();});
$('new-record').addEventListener('click', () => run(() => {
  if (!canReplace()) return;
  showRecord({title: '', date: '', category: '', notes: '', tags: [], materials: []});
  history.replaceState(null, '', '/archive');
  $('title').focus();
  notice('Name the record and save it, then add original materials. An unknown experiment date can be left blank.');
}));
$('files').addEventListener('change', () => run(async () => {
  const files = [...$('files').files];
  if (!state.current?.id || state.dirty) throw Error('Save the record before adding files.');
  let added = 0, duplicates = 0;
  try {
    for (const file of files) {
      if (file.size > 25 * 1024 ** 2) throw Error(`${file.name} exceeds 25 MiB.`);
      notice(`Saving ${file.name}…`);
      const response = await request(`/api/archive/${state.current.id}/files?name=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: {'Content-Type': 'application/octet-stream', 'X-Workbench-Request': '1', 'X-Record-Revision': String(state.current.revision)}, body: file});
      state.current = response.record;
      response.duplicate ? duplicates++ : added++;
    }
  } catch (error) {
    throw Error(`${added} file(s) saved, ${duplicates} duplicate(s) skipped. ${error.message} Remaining files were not uploaded; retry them after resolving the error.`);
  } finally {
    $('files').value = '';
    showRecord(state.current);
    await refreshCatalog();
  }
  notice(`${added} file(s) added; ${duplicates} identical same-name file(s) skipped. Original bytes are preserved.`);
}));

for (const id of ['search', 'filter-category', 'filter-kind', 'filter-from', 'filter-to', 'sort']) $(id).addEventListener('input', renderCatalog);
$('filter-unknown').addEventListener('change', () => {
  const unknown = $('filter-unknown').checked;
  $('filter-from').disabled = $('filter-to').disabled = unknown;
  if (unknown) $('filter-from').value = $('filter-to').value = '';
  renderCatalog();
});
$('clear-filters').addEventListener('click', () => {
  for (const id of ['search', 'filter-category', 'filter-kind', 'filter-from', 'filter-to']) $(id).value = '';
  $('sort').value = 'updated'; $('filter-unknown').checked = false;
  $('filter-from').disabled = $('filter-to').disabled = false;
  renderCatalog(); notice('Filters cleared.');
});
$('close-preview').addEventListener('click', closePreview);
window.addEventListener('beforeunload', event => {
  if (state.dirty || state.busy) {event.preventDefault(); event.returnValue = '';}
});
run(async () => {
  const errors = await refreshCatalog();
  notice(errors.length ? `${errors.length} record(s) could not be read. Their files were left untouched.` : 'Search your records or create one to add experimental materials.', !!errors.length);
  const identity = location.hash.slice(1);
  if (/^[0-9a-f]{32}$/.test(identity)) await openRecord(identity);
});
