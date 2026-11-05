const $ = (selector) => document.querySelector(selector);
const fmt = (value) => new Intl.NumberFormat('en-US').format(value);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const size = (value) => value == null ? '—' : value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1048576).toFixed(1)} MB`;
const state = { manifest:null, build:null, tab:'images', query:'', volume:'all', limit:80, selected:null, datasets:new Map(), compareOld:null, compareNew:null };
let searchTimer;

async function json(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

async function compressedJSON(url) {
  if (!('DecompressionStream' in window)) throw new Error('This browser cannot open compressed catalog data. Use a current Safari, Chrome, or Firefox.');
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json();
}

function activeBuild() { return state.manifest.builds.find((item) => item.build === state.build); }

async function dataset(kind, build = state.build) {
  const key = `${kind}:${build}`;
  if (state.datasets.has(key)) return state.datasets.get(key);
  const info = state.manifest.builds.find((item) => item.build === build);
  const result = kind === 'files' ? await compressedJSON(info.files_url) : await json(info.dyld_url);
  state.datasets.set(key, result);
  return result;
}

function setTab(tab) {
  state.tab = tab;
  state.query = '';
  state.volume = 'all';
  state.limit = 80;
  state.selected = null;
  for (const button of document.querySelectorAll('[role="tab"]')) button.setAttribute('aria-selected', button.dataset.tab === tab);
  history.replaceState(null, '', `#${tab}`);
  render().catch(showError);
  document.querySelector('.workspace').scrollIntoView({behavior:'smooth', block:'start'});
}

function toolbar({placeholder, volumes = []}) {
  return `<div class="toolbar"><label class="searchbox"><span class="sr-only">Search paths</span><input id="catalog-search" type="search" autocomplete="off" placeholder="${escapeHTML(placeholder)}" value="${escapeHTML(state.query)}"></label>${volumes.length ? `<select id="volume-filter" aria-label="Filter volume"><option value="all">All volumes</option>${volumes.map((name) => `<option value="${escapeHTML(name)}" ${state.volume === name ? 'selected' : ''}>${escapeHTML(name)}</option>`).join('')}</select>` : ''}<span class="result-count" id="result-count"></span></div>`;
}

function bindToolbar() {
  const input = $('#catalog-search');
  if (input) input.addEventListener('input', () => { state.query = input.value; state.limit = 80; clearTimeout(searchTimer); searchTimer = setTimeout(renderResults, 180); });
  const filter = $('#volume-filter');
  if (filter) filter.addEventListener('change', () => { state.volume = filter.value; state.limit = 80; renderResults(); });
}

function detailHTML(item, mode, data) {
  if (!item) return `<div class="empty-detail">Select a row to inspect its source and metadata.</div>`;
  if (mode === 'images') {
    const present = item.physical_volumes.length > 0;
    return `<span class="detail-label">IN-CACHE IMAGE</span><h3>${escapeHTML(item.install_name.split('/').pop())}</h3><dl><dt>LOGICAL INSTALL NAME</dt><dd>${escapeHTML(item.install_name)}</dd><dt>IMAGE UUID</dt><dd>${escapeHTML(item.uuid)}</dd><dt>SOURCE VERSION</dt><dd>${escapeHTML(item.version || 'Not recorded')}</dd><dt>CACHE UUID</dt><dd>${escapeHTML(data.cache_uuid)}</dd><dt>STANDALONE FILE IN SCANNED IMAGES</dt><dd>${present ? escapeHTML(item.physical_volumes.join(', ')) : 'None observed'}</dd></dl><p class="explain">${present ? 'A separate physical file was also found at this logical path. The cache image and file remain distinct records.' : 'No regular file exists at this path in the three processed IPSW images. Its executable image is listed in the dyld shared cache.'}</p>`;
  }
  if (mode === 'files') {
    const [volumeIndex, path, type, bytes, target] = item;
    const volume = data.volumes[volumeIndex];
    return `<span class="detail-label">FILESYSTEM ENTRY</span><h3>${escapeHTML(path.split('/').pop())}</h3><dl><dt>PATH</dt><dd>${escapeHTML(path)}</dd><dt>VOLUME</dt><dd>${escapeHTML(volume.name)}</dd><dt>SOURCE IMAGE</dt><dd>${escapeHTML(volume.image_name)}</dd><dt>TYPE</dt><dd>${escapeHTML(type)}</dd><dt>SIZE</dt><dd>${escapeHTML(size(bytes))}</dd>${target ? `<dt>LINK TARGET</dt><dd>${escapeHTML(target)}</dd>` : ''}</dl><p class="explain">Observed in the mounted official firmware image. A file path here does not establish that the same bytes are present on a running device.</p>`;
  }
  return `<span class="detail-label">CACHE FILE</span><h3>${escapeHTML(item.name)}</h3><dl><dt>FILE SIZE</dt><dd>${escapeHTML(size(item.size))}</dd><dt>SHA-256</dt><dd>${escapeHTML(item.sha256)}</dd><dt>CACHE FAMILY UUID</dt><dd>${escapeHTML(data.cache_uuid)}</dd></dl><p class="explain">A physical member of the extracted SystemOS dyld cache family. Its contents are not hosted by this site.</p>`;
}

function renderRows(items, mode, data) {
  const visible = items.slice(0, state.limit);
  const rows = visible.map((item, index) => {
    const path = mode === 'images' ? item.install_name : mode === 'files' ? item[1] : item.name;
    const secondary = mode === 'images' ? (item.physical_volumes.length ? 'DISK + CACHE' : 'IN CACHE') : mode === 'files' ? data.volumes[item[0]].name : size(item.size);
    const icon = mode === 'images' ? '◇' : mode === 'files' ? item[2] === 'directory' ? '▤' : item[2] === 'symlink' ? '↗' : '·' : '◈';
    return `<button class="result-row ${state.selected === item ? 'selected' : ''}" data-index="${index}" title="${escapeHTML(path)}"><span class="row-main"><span class="row-icon">${icon}</span><span class="row-text">${escapeHTML(path)}</span></span><span class="row-sub">${escapeHTML(secondary)}</span></button>`;
  }).join('');
  $('#result-count').textContent = `${fmt(items.length)} result${items.length === 1 ? '' : 's'}`;
  $('#results').innerHTML = `<div class="result-head"><span>PATH / INSTALL NAME</span><span>SOURCE</span></div>${rows || '<p class="empty-state">No matching entries in the selected source.</p>'}${items.length > state.limit ? '<button id="show-more" class="more-button">Show more ↓</button>' : ''}`;
  $('#detail').innerHTML = detailHTML(state.selected, mode, data);
  for (const row of document.querySelectorAll('.result-row')) row.addEventListener('click', () => { state.selected = visible[Number(row.dataset.index)]; $('#detail').innerHTML = detailHTML(state.selected, mode, data); document.querySelectorAll('.result-row').forEach((other) => other.classList.toggle('selected', other === row)); });
  $('#show-more')?.addEventListener('click', () => { state.limit += 80; renderRows(items, mode, data); });
}

function renderResults() {
  const mode = state.tab;
  const data = state.datasets.get(`${mode === 'files' ? 'files' : 'dyld'}:${state.build}`);
  if (!data || !['images','files','caches'].includes(mode)) return;
  const query = state.query.trim().toLocaleLowerCase();
  let items;
  if (mode === 'files') items = data.entries.filter((item) => (state.volume === 'all' || data.volumes[item[0]].name === state.volume) && (!query || item[1].toLocaleLowerCase().includes(query)));
  else if (mode === 'images') items = data.images.filter((item) => !query || item.install_name.toLocaleLowerCase().includes(query));
  else items = data.files.filter((item) => !query || item.name.toLocaleLowerCase().includes(query));
  state.selected = items.includes(state.selected) ? state.selected : null;
  renderRows(items, mode, data);
}

async function renderExplorer() {
  const mode = state.tab;
  const explorer = $('#explorer');
  if (mode === 'research') {
    const entries = state.manifest.research.filter((note) => note.build === state.build);
    explorer.innerHTML = `<div class="research-list">${entries.map((note) => `<article class="research-card"><span class="tag">BUILD ${escapeHTML(note.build)} / COMPONENT NOTE</span><h3>${escapeHTML(note.title)}</h3><p>${escapeHTML(note.summary)}</p><a href="https://github.com/everettjf/ios-atlas/blob/main/${encodeURI(note.note)}" target="_blank" rel="noopener">Read evidence note ↗</a></article>`).join('') || '<p class="empty-state">No published research notes for this build yet.</p>'}</div>`;
    return;
  }
  if (mode === 'compare') { await renderCompare(); return; }
  explorer.innerHTML = '<p class="loading">Opening source-bound catalog…</p>';
  const data = await dataset(mode === 'files' ? 'files' : 'dyld');
  if (state.tab !== mode) return;
  explorer.innerHTML = toolbar({placeholder:mode === 'files' ? 'Search filesystem paths…' : mode === 'images' ? 'Search library install names…' : 'Search cache file names…', volumes:mode === 'files' ? data.volumes.map((volume) => volume.name) : []}) + '<div class="explorer-grid"><div id="results" class="result-list"></div><aside id="detail" class="detail"></aside></div>';
  bindToolbar();
  renderResults();
}

async function renderCompare() {
  const explorer = $('#explorer');
  const builds = state.manifest.builds;
  if (builds.length < 2) {
    explorer.innerHTML = '<div class="compare-panel"><span class="detail-label">BUILD COMPARISON</span><h3>One build is cataloged.</h3><p class="empty-detail">Comparison becomes available when a second exact firmware build passes the same collection and validation steps. The interface will compare in-cache image names and UUIDs.</p></div>';
    return;
  }
  state.compareOld ??= builds[0].build;
  state.compareNew ??= builds.at(-1).build;
  const options = builds.map((item) => `<option value="${escapeHTML(item.build)}">${escapeHTML(item.build)}</option>`).join('');
  explorer.innerHTML = `<div class="compare-panel"><div class="compare-controls"><label>FROM<select id="compare-old">${options}</select></label><label>TO<select id="compare-new">${options}</select></label></div><div id="compare-results" class="compare-section"></div></div>`;
  $('#compare-old').value = state.compareOld;
  $('#compare-new').value = state.compareNew;
  for (const id of ['compare-old','compare-new']) $("#" + id).addEventListener('change', async () => { state.compareOld = $('#compare-old').value; state.compareNew = $('#compare-new').value; await compareData(); });
  await compareData();
}

async function compareData() {
  const target = $('#compare-results');
  if (state.compareOld === state.compareNew) { target.innerHTML = '<p>Select two different builds.</p>'; return; }
  target.innerHTML = '<p>Comparing indexed images…</p>';
  const [oldData, newData] = await Promise.all([dataset('dyld', state.compareOld), dataset('dyld', state.compareNew)]);
  const oldMap = new Map(oldData.images.map((item) => [item.install_name, item]));
  const newMap = new Map(newData.images.map((item) => [item.install_name, item]));
  const added = newData.images.filter((item) => !oldMap.has(item.install_name));
  const removed = oldData.images.filter((item) => !newMap.has(item.install_name));
  const changed = newData.images.filter((item) => oldMap.has(item.install_name) && oldMap.get(item.install_name).uuid !== item.uuid);
  target.innerHTML = `<h3>${fmt(added.length)} added · ${fmt(removed.length)} removed · ${fmt(changed.length)} changed UUID</h3><p>This compares image names and binary UUIDs in two complete, build-specific caches. UUID changes alone do not explain the behavior change.</p>${[['Added',added],['Removed',removed],['Changed UUID',changed]].map(([label,items]) => `<div class="compare-section"><h3>${label}</h3>${items.slice(0,100).map((item) => `<div class="compare-item">${escapeHTML(item.install_name)}</div>`).join('') || '<p>None</p>'}${items.length > 100 ? `<p>Showing 100 of ${fmt(items.length)}.</p>` : ''}</div>`).join('')}`;
}

async function render() { await renderExplorer(); }
function showError(error) { $('#explorer').innerHTML = `<p class="empty-state">Unable to open this catalog: ${escapeHTML(error.message)}</p>`; }

async function start() {
  state.manifest = await json('data/manifest.json');
  const first = state.manifest.builds[0];
  state.build = first.build;
  $('#metric-files').textContent = fmt(first.file_count);
  $('#metric-images').textContent = fmt(first.image_count);
  $('#metric-caches').textContent = fmt(first.cache_file_count);
  $('#metric-build').textContent = first.build;
  $('#build-select').innerHTML = state.manifest.builds.map((item) => `<option value="${escapeHTML(item.build)}">${escapeHTML(item.version)} · ${escapeHTML(item.build)}</option>`).join('');
  $('#build-select').addEventListener('change', () => { state.build = $('#build-select').value; state.selected = null; state.limit = 80; const build = activeBuild(); $('#metric-files').textContent = fmt(build.file_count); $('#metric-images').textContent = fmt(build.image_count); $('#metric-caches').textContent = fmt(build.cache_file_count); $('#metric-build').textContent = build.build; render().catch(showError); });
  for (const button of document.querySelectorAll('[data-tab]')) button.addEventListener('click', () => setTab(button.dataset.tab));
  const initial = location.hash.slice(1);
  if (['files','images','caches','research','compare'].includes(initial)) state.tab = initial;
  for (const button of document.querySelectorAll('[role="tab"]')) button.setAttribute('aria-selected', button.dataset.tab === state.tab);
  await render();
}

start().catch(showError);
