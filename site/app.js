const $ = (selector) => document.querySelector(selector);
const assetVersion = new URL(import.meta.url).searchParams.get('v') || 'dev';
const versioned = (url) => `${url}?v=${assetVersion}`;
const fmt = (value) => new Intl.NumberFormat('en-US').format(value);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const size = (value) => value == null ? '—' : value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1048576).toFixed(1)} MB`;
const filesystemMode = (mode) => mode === 'files' || mode === 'restore';
const state = { manifest:null, build:null, tab:'images', query:'', volume:'all', limit:80, selected:null, datasets:new Map(), compareOld:null, compareNew:null };
let searchTimer;

async function json(url) {
  const response = await fetch(versioned(url));
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

async function compressedJSON(url) {
  if (!('DecompressionStream' in window)) throw new Error('This browser cannot open compressed catalog data. Use a current Safari, Chrome, or Firefox.');
  const response = await fetch(versioned(url));
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json();
}

function activeBuild() { return state.manifest.builds.find((item) => item.build === state.build); }

async function dataset(kind, build = state.build) {
  const key = `${kind}:${build}`;
  if (state.datasets.has(key)) return state.datasets.get(key);
  const info = state.manifest.builds.find((item) => item.build === build);
  const result = kind === 'files' ? await compressedJSON(info.files_url) : kind === 'restore' ? await compressedJSON(info.restore_url) : kind === 'device' ? await compressedJSON(info.device_url) : await json(kind === 'driverkit' ? info.driverkit_url : kind === 'archive' ? info.archive_url : kind === 'kernel' ? info.kernel_url : info.dyld_url);
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

function updateSource() {
  const device = state.tab === 'device';
  const driverkit = state.tab === 'driverkit';
  const archive = state.tab === 'archive';
  const restore = state.tab === 'restore';
  const kernel = state.tab === 'kernel';
  $('#source-title').textContent = device ? 'Source: live iPhone 11 system view' : driverkit ? 'Source: official DriverKit cache' : archive ? 'Source: complete restore IPSW archive' : restore ? 'Source: official restore RAM disks' : kernel ? 'Source: official kernelcache Mach-O filesets' : 'Source: official iPhone 11 firmware';
  $('#source-description').textContent = device
    ? 'Read-only /rootfs observation of selected Apple system roots. User data and jailbreak namespace are excluded; differences do not establish jailbreak causation.'
    : driverkit ? 'A separate DriverKit platform cache: 51 images in 3 physical files. All 3 files matched the connected device by SHA-256.'
    : archive ? 'All 127 ZIP entries are indexed by path and role. Artifact presence is distinct from mounted filesystem content.'
    : restore ? 'Erase and Upgrade recovery environments are cataloged separately from the installed iOS filesystem.'
    : kernel ? 'Release and research kernelcaches have distinct UUIDs. Kext metadata and fileset entry counts are separate measurements.'
    : 'All 80 cache files matched the connected device by SHA-256. An in-cache image is not counted as an on-disk executable.';
}

function toolbar({placeholder, volumes = [], filterLabel = 'All volumes'}) {
  return `<div class="toolbar"><label class="searchbox"><span class="sr-only">Search paths</span><input id="catalog-search" type="search" autocomplete="off" placeholder="${escapeHTML(placeholder)}" value="${escapeHTML(state.query)}"></label>${volumes.length ? `<select id="volume-filter" aria-label="${filterLabel === 'All variants' ? 'Filter variant' : 'Filter volume'}"><option value="all">${filterLabel}</option>${volumes.map((name) => `<option value="${escapeHTML(name)}" ${state.volume === name ? 'selected' : ''}>${escapeHTML(name)}</option>`).join('')}</select>` : ''}<span class="result-count" id="result-count"></span></div>`;
}

function bindToolbar() {
  const input = $('#catalog-search');
  if (input) input.addEventListener('input', () => { state.query = input.value; state.limit = 80; clearTimeout(searchTimer); searchTimer = setTimeout(renderResults, 180); });
  const filter = $('#volume-filter');
  if (filter) filter.addEventListener('change', () => { state.volume = filter.value; state.limit = 80; renderResults(); });
}

function detailHTML(item, mode, data) {
  if (!item) return `<div class="empty-detail">Select a row to inspect its source and metadata.</div>`;
  if (mode === 'images' || mode === 'driverkit') {
    const present = item.physical_volumes.length > 0;
    return `<span class="detail-label">${mode === 'driverkit' ? 'DRIVERKIT CACHE IMAGE' : 'IN-CACHE IMAGE'}</span><h3>${escapeHTML(item.install_name.split('/').pop())}</h3><dl><dt>LOGICAL INSTALL NAME</dt><dd>${escapeHTML(item.install_name)}</dd><dt>IMAGE UUID</dt><dd>${escapeHTML(item.uuid)}</dd><dt>SOURCE VERSION</dt><dd>${escapeHTML(item.version || 'Not recorded')}</dd><dt>CACHE UUID</dt><dd>${escapeHTML(data.cache_uuid)}</dd><dt>STANDALONE FILE IN SCANNED IMAGES</dt><dd>${present ? escapeHTML(item.physical_volumes.join(', ')) : 'None observed'}</dd></dl><p class="explain">${present ? 'A separate physical file was also found at this logical path. The cache image and file remain distinct records.' : 'No regular file exists at this path in the three processed IPSW images. Its executable image is listed in the dyld shared cache.'}</p>`;
  }
  if (filesystemMode(mode)) {
    const [volumeIndex, path, type, bytes, target] = item;
    const volume = data.volumes[volumeIndex];
    return `<span class="detail-label">${mode === 'restore' ? 'RESTORE RAMDISK ENTRY' : 'FILESYSTEM ENTRY'}</span><h3>${escapeHTML(path.split('/').pop())}</h3><dl><dt>PATH</dt><dd>${escapeHTML(path)}</dd><dt>VOLUME</dt><dd>${escapeHTML(volume.name)}</dd><dt>SOURCE IMAGE</dt><dd>${escapeHTML(volume.image_name)}</dd><dt>TYPE</dt><dd>${escapeHTML(type)}</dd><dt>SIZE</dt><dd>${escapeHTML(size(bytes))}</dd>${target ? `<dt>LINK TARGET</dt><dd>${escapeHTML(target)}</dd>` : ''}</dl><p class="explain">${mode === 'restore' ? 'Observed in a mounted IPSW restore environment. This is not the normal running iOS root filesystem.' : 'Observed in the mounted official firmware image. A file path here does not establish that the same bytes are present on a running device.'}</p>`;
  }
  if (mode === 'device') {
    const [path, type] = item;
    return `<span class="detail-label">DEVICE SYSTEM PATH</span><h3>${escapeHTML(path.split('/').pop())}</h3><dl><dt>PATH IN /ROOTFS</dt><dd>${escapeHTML(path)}</dd><dt>TYPE</dt><dd>${escapeHTML(type)}</dd><dt>SOURCE</dt><dd>Read-only device observation, selected Apple system roots</dd></dl><p class="explain">This path was seen in the live RootHide /rootfs view. It is not evidence that the jailbreak created or changed it. User data and the jailbreak namespace are outside this catalog.</p>`;
  }
  if (mode === 'archive') {
    const roles = [...new Set(item.manifest_roles.map((pair) => pair[1]))].join(', ') || 'No BuildManifest role';
    return `<span class="detail-label">IPSW ARCHIVE MEMBER</span><h3>${escapeHTML(item.path.split('/').filter(Boolean).pop())}</h3><dl><dt>ARCHIVE PATH</dt><dd>${escapeHTML(item.path)}</dd><dt>KIND</dt><dd>${escapeHTML(item.kind)}</dd><dt>UNCOMPRESSED SIZE</dt><dd>${escapeHTML(size(item.size))}</dd><dt>SHA-256</dt><dd>${escapeHTML(item.sha256 || 'Directory')}</dd><dt>BUILD MANIFEST ROLES</dt><dd>${escapeHTML(roles)}</dd><dt>CONTENTS INDEXED</dt><dd>${escapeHTML(item.indexed_view || 'Artifact metadata only')}</dd></dl><p class="explain">An archive member is a restore artifact. It is not necessarily a file on the running iPhone. The roles above are from this IPSW's BuildManifest.</p>`;
  }
  if (mode === 'kernel') {
    const image = data.images.find((entry) => entry.variant === item.variant);
    const dependencies = Object.keys(item.dependencies).join(', ') || 'None recorded';
    return `<span class="detail-label">KERNEL EXTENSION METADATA</span><h3>${escapeHTML(item.name || item.id)}</h3><dl><dt>BUNDLE ID</dt><dd>${escapeHTML(item.id)}</dd><dt>VERSION</dt><dd>${escapeHTML(item.version || 'Not recorded')}</dd><dt>BUNDLE PATH</dt><dd>${escapeHTML(item.bundle_path || 'Not recorded')}</dd><dt>DEPENDENCIES</dt><dd>${escapeHTML(dependencies)}</dd><dt>KERNEL VARIANT</dt><dd>${escapeHTML(item.variant)}</dd><dt>KERNEL UUID</dt><dd>${escapeHTML(item.kernel_uuid)}</dd><dt>XNU</dt><dd>${escapeHTML(image.xnu)}</dd></dl><p class="explain">Parsed from the decompressed IPSW kernelcache fileset. This is extension metadata, not a separate on-disk kext file observation or proof of runtime loading.</p>`;
  }
  return `<span class="detail-label">CACHE FILE</span><h3>${escapeHTML(item.name)}</h3><dl><dt>FILE SIZE</dt><dd>${escapeHTML(size(item.size))}</dd><dt>SHA-256</dt><dd>${escapeHTML(item.sha256)}</dd><dt>CACHE FAMILY UUID</dt><dd>${escapeHTML(data.cache_uuid)}</dd></dl><p class="explain">A physical member of the extracted SystemOS dyld cache family. Its contents are not hosted by this site.</p>`;
}

function renderRows(items, mode, data) {
  const visible = items.slice(0, state.limit);
  const rows = visible.map((item, index) => {
    const path = mode === 'images' || mode === 'driverkit' ? item.install_name : filesystemMode(mode) ? item[1] : mode === 'device' ? item[0] : mode === 'archive' ? item.path : mode === 'kernel' ? item.id : item.name;
    const secondary = mode === 'images' || mode === 'driverkit' ? (item.physical_volumes.length ? 'DISK + CACHE' : 'IN CACHE') : filesystemMode(mode) ? data.volumes[item[0]].name : mode === 'device' ? item[1].toUpperCase() : mode === 'archive' ? item.kind.toUpperCase() : mode === 'kernel' ? item.variant.toUpperCase() : size(item.size);
    const icon = mode === 'images' || mode === 'driverkit' ? '◇' : filesystemMode(mode) ? item[2] === 'directory' ? '▤' : item[2] === 'symlink' ? '↗' : '·' : mode === 'device' ? item[1] === 'directory' ? '▤' : item[1] === 'symlink' ? '↗' : '·' : mode === 'archive' ? '▧' : mode === 'kernel' ? '✳' : '◈';
    return `<button class="result-row ${state.selected === item ? 'selected' : ''}" data-index="${index}" title="${escapeHTML(path)}"><span class="row-main"><span class="row-icon">${icon}</span><span class="row-text">${escapeHTML(path)}</span></span><span class="row-sub">${escapeHTML(secondary)}</span></button>`;
  }).join('');
  $('#result-count').textContent = `${fmt(items.length)} result${items.length === 1 ? '' : 's'}`;
  const heading = mode === 'kernel' ? 'BUNDLE IDENTIFIER' : mode === 'archive' ? 'ARCHIVE MEMBER' : 'PATH / INSTALL NAME';
  const sourceHeading = mode === 'kernel' ? 'VARIANT' : mode === 'archive' ? 'KIND' : 'SOURCE';
  $('#results').innerHTML = `<div class="result-head"><span>${heading}</span><span>${sourceHeading}</span></div>${rows || '<p class="empty-state">No matching entries in the selected source.</p>'}${items.length > state.limit ? '<button id="show-more" class="more-button">Show more ↓</button>' : ''}`;
  $('#detail').innerHTML = detailHTML(state.selected, mode, data);
  for (const row of document.querySelectorAll('.result-row')) row.addEventListener('click', () => { state.selected = visible[Number(row.dataset.index)]; $('#detail').innerHTML = detailHTML(state.selected, mode, data); document.querySelectorAll('.result-row').forEach((other) => other.classList.toggle('selected', other === row)); });
  $('#show-more')?.addEventListener('click', () => { state.limit += 80; renderRows(items, mode, data); });
}

function renderResults() {
  const mode = state.tab;
  const data = state.datasets.get(`${filesystemMode(mode) ? mode : mode === 'device' ? 'device' : mode === 'driverkit' ? 'driverkit' : mode === 'archive' ? 'archive' : mode === 'kernel' ? 'kernel' : 'dyld'}:${state.build}`);
  if (!data || !['images','driverkit','files','restore','device','caches','archive','kernel'].includes(mode)) return;
  const query = state.query.trim().toLocaleLowerCase();
  let items;
  if (filesystemMode(mode)) items = data.entries.filter((item) => (state.volume === 'all' || data.volumes[item[0]].name === state.volume) && (!query || item[1].toLocaleLowerCase().includes(query)));
  else if (mode === 'device') items = data.entries.filter((item) => !query || item[0].toLocaleLowerCase().includes(query));
  else if (mode === 'images' || mode === 'driverkit') items = data.images.filter((item) => !query || item.install_name.toLocaleLowerCase().includes(query));
  else if (mode === 'archive') items = data.entries.filter((item) => !query || item.path.toLocaleLowerCase().includes(query));
  else if (mode === 'kernel') items = data.kexts.filter((item) => (state.volume === 'all' || item.variant === state.volume) && (!query || `${item.id} ${item.name} ${item.bundle_path}`.toLocaleLowerCase().includes(query)));
  else items = data.files.filter((item) => !query || item.name.toLocaleLowerCase().includes(query));
  state.selected = items.includes(state.selected) ? state.selected : null;
  renderRows(items, mode, data);
}

async function renderExplorer() {
  const mode = state.tab;
  const explorer = $('#explorer');
  updateSource();
  if (mode === 'research') {
    const entries = state.manifest.research.filter((note) => note.build === state.build);
    explorer.innerHTML = `<div class="research-list">${entries.map((note) => `<article class="research-card"><span class="tag">BUILD ${escapeHTML(note.build)} / COMPONENT NOTE</span><h3>${escapeHTML(note.title)}</h3><p>${escapeHTML(note.summary)}</p><a href="https://github.com/everettjf/ios-atlas/blob/main/${encodeURI(note.note)}" target="_blank" rel="noopener">Read evidence note ↗</a></article>`).join('') || '<p class="empty-state">No published research notes for this build yet.</p>'}</div>`;
    return;
  }
  if (mode === 'compare') { await renderCompare(); return; }
  if (mode === 'device' && !activeBuild().device_url) { explorer.innerHTML = '<p class="empty-state">No privacy-reviewed device system inventory is published for this build.</p>'; return; }
  if (mode === 'driverkit' && !activeBuild().driverkit_url) { explorer.innerHTML = '<p class="empty-state">No DriverKit cache is cataloged for this build.</p>'; return; }
  if (mode === 'archive' && !activeBuild().archive_url) { explorer.innerHTML = '<p class="empty-state">No restore archive is cataloged for this build.</p>'; return; }
  if (mode === 'restore' && !activeBuild().restore_url) { explorer.innerHTML = '<p class="empty-state">No restore RAM disks are cataloged for this build.</p>'; return; }
  if (mode === 'kernel' && !activeBuild().kernel_url) { explorer.innerHTML = '<p class="empty-state">No kernelcache metadata is cataloged for this build.</p>'; return; }
  explorer.innerHTML = '<p class="loading">Opening source-bound catalog…</p>';
  const data = await dataset(filesystemMode(mode) ? mode : mode === 'device' ? 'device' : mode === 'driverkit' ? 'driverkit' : mode === 'archive' ? 'archive' : mode === 'kernel' ? 'kernel' : 'dyld');
  if (state.tab !== mode) return;
  const kernelSummary = mode === 'kernel' ? `<div class="kernel-summary">${data.images.map((image) => `<div><strong>${escapeHTML(image.variant.toUpperCase())}</strong><span>UUID ${escapeHTML(image.macho_uuid)}</span><span>Darwin ${escapeHTML(image.darwin)} · XNU ${escapeHTML(image.xnu)} · ${fmt(image.fileset_entry_count)} fileset entries · ${fmt(image.kext_count)} kext records</span></div>`).join('')}</div>` : '';
  explorer.innerHTML = kernelSummary + toolbar({placeholder:mode === 'files' ? 'Search filesystem paths…' : mode === 'restore' ? 'Search restore environment paths…' : mode === 'device' ? 'Search live system paths…' : mode === 'images' || mode === 'driverkit' ? 'Search library install names…' : mode === 'archive' ? 'Search IPSW archive members…' : mode === 'kernel' ? 'Search kext identifiers…' : 'Search cache file names…', volumes:filesystemMode(mode) ? data.volumes.map((volume) => volume.name) : mode === 'kernel' ? data.images.map((image) => image.variant) : [], filterLabel:mode === 'kernel' ? 'All variants' : 'All volumes'}) + '<div class="explorer-grid"><div id="results" class="result-list"></div><aside id="detail" class="detail"></aside></div>';
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
  if (['files','restore','device','images','driverkit','caches','archive','kernel','research','compare'].includes(initial)) state.tab = initial;
  for (const button of document.querySelectorAll('[role="tab"]')) button.setAttribute('aria-selected', button.dataset.tab === state.tab);
  await render();
}

start().catch(showError);
