const $ = (selector) => document.querySelector(selector);
const assetVersion = new URL(import.meta.url).searchParams.get('v') || 'dev';
const versioned = (url) => `${url}?v=${assetVersion}`;
const {computeReach, pathTo} = await import(versioned('./reach.mjs'));
const {directoryChildren, parentDirectory} = await import(versioned('./tree.mjs'));
const fmt = (value) => new Intl.NumberFormat('en-US').format(value);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const size = (value) => value == null ? '—' : value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1048576).toFixed(1)} MB`;
const filesystemMode = (mode) => mode === 'files' || mode === 'restore';
const state = { manifest:null, build:null, tab:'device', query:'', volume:'all', limit:80, selected:null, browsePath:'/', swiftImage:null, methodImage:null, driverkitFunctionQuery:'', driverkitFunctionLimit:80, iosSymbolQuery:'', iosSymbolLimit:80, iosSymbolData:null, machoMethodQuery:'', machoMethodLimit:80, machoMethodData:null, machoSymbolQuery:'', machoSymbolLimit:80, machoSymbolData:null, machoSwiftQuery:'', machoSwiftTypeLimit:40, machoSwiftMemberLimit:80, machoSwiftData:null, liveMethodPath:null, liveMethodQuery:'', liveMethodLimit:80, liveSymbolQuery:'', liveSymbolLimit:80, liveSymbolData:null, reachSource:null, reachWeak:false, reachPaths:null, datasets:new Map() };
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
  const result = kind === 'files' ? await compressedJSON(info.files_url) : kind === 'restore' ? await compressedJSON(info.restore_url) : kind === 'device' ? await compressedJSON(info.device_url) : kind === 'device_macho' ? await compressedJSON(info.device_macho_url) : kind === 'device_macho_objc' ? await compressedJSON(info.device_macho_objc_url) : kind === 'device_macho_dependencies' ? await compressedJSON(info.device_macho_dependency_url) : kind === 'device_macho_symbols' ? await compressedJSON(info.device_macho_symbol_index_url) : kind === 'objc' ? await compressedJSON(info.objc_url) : kind === 'methods_index' ? await compressedJSON(info.objc_method_index_url) : kind === 'ios_symbol_index' ? await compressedJSON(info.ios_symbol_index_url) : kind === 'driverkit_functions' ? await compressedJSON(info.driverkit_function_url) : kind === 'macho' ? await compressedJSON(info.standalone_macho_url) : kind === 'macho_identity' ? await compressedJSON(info.live_standalone_identity_url) : kind === 'macho_methods_index' ? await compressedJSON(info.standalone_objc_index_url) : kind === 'macho_symbol_index' ? await compressedJSON(info.standalone_symbol_index_url) : kind === 'macho_swift_index' ? await compressedJSON(info.standalone_swift_index_url) : kind === 'protocols' ? await compressedJSON(info.objc_protocol_url) : kind === 'dependencies' ? await compressedJSON(info.dyld_dependency_url) : kind === 'driverkit_dependencies' ? await compressedJSON(info.driverkit_dependency_url) : await json(kind === 'swift' ? info.swift_url : kind === 'driverkit' ? info.driverkit_url : kind === 'archive' ? info.archive_url : kind === 'kernel' ? info.kernel_url : kind === 'services' ? info.service_url : info.dyld_url);
  if (kind === 'device_macho') result.byPath = new Map(result.records.map((item) => [item.path, item]));
  if (kind === 'device_macho_objc' || kind === 'device_macho_dependencies') result.byPath = new Map(result.files.map((item) => [item.path, item]));
  if (kind === 'device_macho_symbols') result.byPath = new Map(result.files.map((item) => [item.path, item]));
  if (kind === 'macho_identity') {
    result.byKey = new Map(result.records.map((item) => [`${item.volume}\0${item.path}`, item]));
    result.byDevicePath = new Map(result.records.filter((item) => item.status === 'matched').map((item) => [item.device_path, item]));
  }
  if (kind === 'services') result.binaryByKey = new Map(result.binaries.map((item) => [`${item.volume}:${item.path}`, item]));
  if (kind === 'macho_methods_index') result.byKey = new Map(result.files.map((item) => [`${item.volume}\0${item.path}`, item]));
  if (kind === 'macho_symbol_index') result.byKey = new Map(result.files.map((item) => [`${item.volume}\0${item.path}`, item]));
  if (kind === 'macho_swift_index') result.byKey = new Map(result.files.map((item) => [`${item.volume}\0${item.path}`, item]));
  if (kind === 'ios_symbol_index') {
    if (result.build !== build || result.cache_uuid !== info.cache_uuid) throw new Error('iOS symbol index identity differs');
    result.byName = new Map(result.images.map((item) => [item.install_name, item]));
  }
  if (kind === 'dependencies' || kind === 'driverkit_dependencies') {
    result.byName = new Map(result.images.map((item) => [item.install_name, item]));
    result.importers = new Map();
    for (const image of result.images) for (const imp of image.imports) {
      if (!result.byName.has(imp.install_name)) continue;
      if (!result.importers.has(imp.install_name)) result.importers.set(imp.install_name, []);
      result.importers.get(imp.install_name).push({source:image.install_name, load_command:imp.load_command});
    }
  }
  state.datasets.set(key, result);
  return result;
}

function setTab(tab, query = '') {
  state.tab = tab;
  state.reachSource = tab === 'reach' && query.startsWith('source:') ? query.slice(7) : null;
  state.reachPaths = null;
  state.reachWeak = false;
  state.query = state.reachSource ? '' : query;
  state.volume = 'all';
  state.limit = 80;
  state.selected = null;
  state.browsePath = '/';
  state.swiftImage = null;
  state.methodImage = null;
  state.driverkitFunctionQuery = '';
  state.driverkitFunctionLimit = 80;
  state.iosSymbolQuery = '';
  state.iosSymbolLimit = 80;
  state.iosSymbolData = null;
  state.machoMethodQuery = '';
  state.machoMethodLimit = 80;
  state.machoMethodData = null;
  state.machoSymbolQuery = '';
  state.machoSymbolLimit = 80;
  state.machoSymbolData = null;
  state.machoSwiftQuery = '';
  state.machoSwiftTypeLimit = 40;
  state.machoSwiftMemberLimit = 80;
  state.machoSwiftData = null;
  state.liveMethodQuery = '';
  state.liveMethodLimit = 80;
  state.liveMethodPath = null;
  state.liveSymbolQuery = '';
  state.liveSymbolLimit = 80;
  state.liveSymbolData = null;
  for (const button of document.querySelectorAll('[role="tab"]')) button.setAttribute('aria-selected', button.dataset.tab === tab);
  history.replaceState(null, '', (tab === 'research' || tab === 'methods') && query ? `#${tab}/${encodeURIComponent(query)}` : state.reachSource ? `#reach/${encodeURIComponent(state.reachSource)}` : `#${tab}`);
  render().catch(showError);
  document.querySelector('.workspace').scrollIntoView({behavior:'smooth', block:'start'});
}

function updateSource() {
  const files = state.tab === 'files';
  const device = state.tab === 'device';
  const deviceMacho = state.tab === 'device_macho';
  const images = state.tab === 'images';
  const driverkit = state.tab === 'driverkit';
  const macho = state.tab === 'macho';
  const archive = state.tab === 'archive';
  const restore = state.tab === 'restore';
  const kernel = state.tab === 'kernel';
  const services = state.tab === 'services';
  const objc = state.tab === 'objc';
  const methods = state.tab === 'methods';
  const protocols = state.tab === 'protocols';
  const swift = state.tab === 'swift';
  const research = state.tab === 'research';
  const reach = state.tab === 'reach';
  $('#source-method').href = device || deviceMacho ? 'https://github.com/everettjf/ios-atlas/blob/main/docs/live-device-collection.md' : methods && state.methodImage?.endsWith('/SpringBoard.framework/SpringBoard') ? 'https://github.com/everettjf/ios-atlas/blob/main/research/23A355/SpringBoard-Method-Surface.md' : methods && state.methodImage?.endsWith('/Foundation.framework/Foundation') ? 'https://github.com/everettjf/ios-atlas/blob/main/research/23A355/Foundation-Method-Surface.md' : methods ? 'https://github.com/everettjf/ios-atlas/blob/main/research/23A355/Method-Catalog-Coverage.md' : images ? 'https://github.com/everettjf/ios-atlas/blob/main/research/23A355/iOS-Cache-Named-Symbol-Coverage.md' : driverkit ? 'https://github.com/everettjf/ios-atlas/blob/main/research/23A355/DriverKit-Function-Surface.md' : macho ? 'https://github.com/everettjf/ios-atlas/blob/main/research/23A355/Standalone-ObjC-Method-Coverage.md' : 'https://github.com/everettjf/ios-atlas/blob/main/docs/acquisition-23A355.md';
  $('#source-title').textContent = device ? 'Source: live iPhone 11 file paths' : deviceMacho ? 'Source: verified jailbreak Mach-O files' : driverkit ? 'Source: official DriverKit cache' : macho ? 'Source: mounted official IPSW Mach-O files' : methods ? 'Source: exact iOS cache image class dumps' : objc || protocols ? 'Source: official iOS dyld cache Objective-C table' : swift ? 'Source: official iOS dyld cache Swift metadata' : reach ? 'Source: official iOS cache Mach-O load commands' : research ? 'Source: build-specific research notes' : archive ? 'Source: complete restore IPSW archive' : restore ? 'Source: official restore RAM disks' : kernel ? 'Source: official kernelcache Mach-O filesets' : services ? 'Source: official FileSystem launchd plists' : 'Source: official iPhone 11 firmware';
  $('#source-description').textContent = device
    ? activeBuild().device_scope === 'reviewed_live'
      ? `Privacy-reviewed live snapshot: ${fmt(activeBuild().device_count)} published paths from ${fmt(activeBuild().device_complete_root_count)} of ${fmt(activeBuild().device_snapshot_root_count)} scanned roots. User and app data paths are withheld.`
      : 'Read-only /rootfs observation of seven Apple system roots. The jailbreak namespace, preboot, and user data are not yet in the public catalog.'
    : deviceMacho ? `${fmt(activeBuild().device_macho_count)} privacy-reviewed Mach-O files from the live jailbreak installation tree matched device-side SHA-256 hashes. ${fmt(activeBuild().device_macho_objc_method_count || 0)} Objective-C method entries, ${fmt(activeBuild().device_macho_named_symbol_count || 0)} named __text symbol records, and ${fmt(activeBuild().device_macho_direct_load_count || 0)} direct library loads are indexed; static metadata does not establish runtime loading.`
    : driverkit ? 'A separate DriverKit platform cache: 51 images in 3 physical files. Named __text symbols are searchable per image; they are not a complete function inventory.'
    : macho ? `Regular Mach-O files in three official firmware images, with hashes, UUIDs, Objective-C methods, named __text symbols, and Swift dump declarations. ${fmt(activeBuild().live_standalone_matched_count || 0)} files also matched this iPhone by SHA-256; metadata is not a complete function list.`
    : objc ? 'Class entries come from the intact iOS cache optimization table. Image labels are resolved to exact install names with Mach-O segment addresses where needed.'
    : methods ? 'Method entries and IMP addresses cover all classes and categories in each indexed cache image. Select an image to search its methods; some selectors are unavailable in the class dump. These are static metadata, not observed calls.'
    : protocols ? 'Protocol entries come from the intact iOS cache optimization table. Repeated image basenames are kept as ambiguous associations.'
    : swift ? 'Static type-to-protocol conformance records from the intact cache. Addresses resolve to exact Mach-O images; names are raw symbols when available.'
    : reach ? 'Shortest paths follow exact in-cache install-name matches from static Mach-O load commands. No path proves runtime loading.'
    : research ? 'Author-written analyses connect exact firmware artifacts and explain the boundary between observed bytes, interpretation and unknowns.'
    : archive ? 'All 127 ZIP entries are indexed by path and role. Artifact presence is distinct from mounted filesystem content.'
    : kernel ? 'Release and research kernelcaches have distinct UUIDs. Kext metadata and fileset entry counts are separate measurements.'
    : services ? 'Launchd job declarations, executable paths, Mach service names, and events from the stock firmware. A declaration is not proof that a job ran.'
    : files ? 'Browse observed paths within each IPSW filesystem image. Logical dyld images appear separately in the same directory and never count as physical files.'
    : restore ? 'Browse paths in the Erase and Upgrade restore RAM disks. These are recovery environments, separate from installed iOS.'
    : images ? 'Exact iOS cache images with linked framework introductions, Objective-C methods, named code symbols, and direct library loads. Static names and declarations do not establish runtime behavior.'
    : 'All 80 cache files matched the connected device by SHA-256. An in-cache image is not counted as an on-disk executable.';
}

function toolbar({placeholder, volumes = [], filterLabel = 'All volumes'}) {
  const filterName = filterLabel === 'All variants' ? 'Filter variant' : filterLabel === 'All resolutions' ? 'Filter executable resolution' : 'Filter volume';
  return `<div class="toolbar"><label class="searchbox"><span class="sr-only">Search catalog</span><input id="catalog-search" type="search" autocomplete="off" placeholder="${escapeHTML(placeholder)}" value="${escapeHTML(state.query)}"></label>${volumes.length ? `<select id="volume-filter" aria-label="${filterName}"><option value="all">${filterLabel}</option>${volumes.map((name) => `<option value="${escapeHTML(name)}" ${state.volume === name ? 'selected' : ''}>${escapeHTML(name)}</option>`).join('')}</select>` : ''}<span class="result-count" id="result-count"></span></div>`;
}

function bindToolbar() {
  const input = $('#catalog-search');
  if (input) input.addEventListener('input', () => { state.query = input.value; state.limit = 80; clearTimeout(searchTimer); searchTimer = setTimeout(renderResults, 180); });
  const filter = $('#volume-filter');
  if (filter) filter.addEventListener('change', () => { state.volume = filter.value; state.limit = 80; state.selected = null; if (filesystemMode(state.tab)) state.browsePath = '/'; renderResults(); });
}

function browseTo(path) {
  state.browsePath = path;
  state.selected = null;
  state.limit = 80;
  history.replaceState(null, '', `#${state.tab}/${encodeURIComponent(path)}`);
  renderResults();
}

function renderDirectoryResults(mode, data) {
  const stock = filesystemMode(mode);
  const selectedVolume = stock && state.volume !== 'all' ? data.volumes.findIndex((item) => item.name === state.volume) : null;
  const children = directoryChildren(data.entries, state.browsePath, stock ? 1 : 0, stock ? 2 : 1, stock ? 0 : null, selectedVolume);
  const segments = state.browsePath.split('/').filter(Boolean);
  let cumulative = '';
  const crumbs = [{label:'/', path:'/'}].concat(segments.map((part) => ({label:part, path:cumulative += `/${part}`})));
  const breadcrumbs = `<nav class="folder-breadcrumbs" aria-label="Current directory">${crumbs.map((part, index) => `<button data-browse-path="${escapeHTML(part.path)}" ${index === crumbs.length - 1 ? 'aria-current="location"' : ''}>${escapeHTML(part.label)}</button>`).join('<span aria-hidden="true">/</span>')}</nav>`;
  const visible = children.slice(0, state.limit);
  const rows = visible.map((child, index) => {
    const folder = child.type === 'directory' || child.type === 'virtual directory';
    const icon = folder ? '▤' : child.type === 'symlink' ? '↗' : '·';
    const label = child.path.split('/').pop();
    const source = child.type === 'virtual directory' ? 'PARENT' : stock ? data.volumes[child.volume].name : child.type.toUpperCase();
    return `<button class="result-row folder-row" data-index="${index}" title="${escapeHTML(child.path)}"><span class="row-main"><span class="row-icon">${icon}</span><span class="row-text">${escapeHTML(label)}${folder ? '/' : ''}</span></span><span class="row-sub">${escapeHTML(source)}</span></button>`;
  }).join('');
  const cache = (mode === 'files' || mode === 'device') && state.volume === 'all' ? state.datasets.get(`dyld:${state.build}`) : null;
  const logicalPath = mode === 'device' && (state.browsePath === '/rootfs' || state.browsePath.startsWith('/rootfs/')) ? state.browsePath.slice(7) || '/' : state.browsePath;
  const images = cache ? cache.images.filter((item) => parentDirectory(item.install_name) === logicalPath) : [];
  const cacheRows = images.length ? `<div class="folder-cache"><div class="folder-cache-heading"><strong>${fmt(images.length)} logical image${images.length === 1 ? '' : 's'} in dyld cache</strong><span>${mode === 'device' ? 'Cache bytes matched this device at the recorded observation; these images are not separate filesystem entries.' : 'These are cache images, not filesystem entries.'}</span></div>${images.slice(0, 20).map((image) => `<button class="folder-cache-row" data-linked-tab="images" data-linked-query="${escapeHTML(image.install_name)}"><span>◇ ${escapeHTML(image.install_name.split('/').pop())}</span><small>IN CACHE ↗</small></button>`).join('')}${images.length > 20 ? `<button class="more-button" data-linked-tab="images" data-linked-query="${escapeHTML(logicalPath + '/')}">Explore all matching images ↗</button>` : ''}</div>` : '';
  $('#result-count').textContent = `${fmt(children.length)} direct path${children.length === 1 ? '' : 's'}`;
  $('#results').innerHTML = breadcrumbs + `<div class="result-head"><span>DIRECT CHILD</span><span>${stock ? 'VOLUME' : 'TYPE'}</span></div>${rows || '<p class="empty-state">No direct entries in this scanned source.</p>'}${children.length > state.limit ? '<button id="show-more" class="more-button">Show more ↓</button>' : ''}` + cacheRows;
  $('#detail').innerHTML = `<div class="empty-detail">Browse a folder or select a file. Symlinks are not followed. PARENT labels identify unobserved ancestors needed to reach a scanned path.</div>`;
  for (const button of $('#results').querySelectorAll('[data-browse-path]')) button.addEventListener('click', () => browseTo(button.dataset.browsePath));
  for (const button of $('#results').querySelectorAll('.folder-row')) button.addEventListener('click', () => {
    const child = visible[Number(button.dataset.index)];
    if (child.type === 'directory' || child.type === 'virtual directory') { browseTo(child.path); return; }
    state.selected = child.row;
    $('#detail').innerHTML = detailHTML(child.row, mode, data);
    $('#results').querySelectorAll('.folder-row').forEach((row) => row.classList.toggle('selected', row === button));
  });
  $('#results').querySelector('#show-more')?.addEventListener('click', () => { state.limit += 80; renderDirectoryResults(mode, data); });
  for (const button of $('#results').querySelectorAll('[data-linked-tab]')) button.addEventListener('click', () => setTab(button.dataset.linkedTab, button.dataset.linkedQuery));
}

function serviceBinary(item, data) {
  const source = item.executable;
  return source.matches.length ? data.binaryByKey.get(`${source.matches[0].volume}:${source.source_path}`) : null;
}

function driverkitFunctionResults(item) {
  const data = state.datasets.get(`driverkit_functions:${state.build}`);
  const image = data?.images.find((entry) => entry.install_name === item.install_name);
  if (!image) return '<p class="empty-state">No function-symbol catalog is available for this image.</p>';
  const query = state.driverkitFunctionQuery.trim().toLocaleLowerCase();
  const matches = query ? image.functions.filter((row) => `${row[0]} ${row[1]} ${row[2]}`.toLocaleLowerCase().includes(query)) : image.functions;
  const visible = matches.slice(0, state.driverkitFunctionLimit);
  return `<p class="explain">${fmt(matches.length)} matching named functions · ${fmt(image.named_function_count)} in this image. Symbol-table coverage is not a complete function inventory.</p><ul>${visible.map((row) => `<li><code>${escapeHTML(row[0])}</code> ${escapeHTML(row[1])}<small>${escapeHTML(row[2])}</small></li>`).join('') || '<li>No matching named functions</li>'}</ul>${matches.length > visible.length ? '<button id="driverkit-function-more" class="more-button">Show more ↓</button>' : ''}`;
}

function machoMethodResults(item, data) {
  const query = state.machoMethodQuery.trim().toLocaleLowerCase();
  const matches = data.records.filter((row) => {
    const group = data.groups[row[0]];
    return !query || `${group.display_name} ${row[1]} ${row[2] ?? ''} ${row[3]}`.toLocaleLowerCase().includes(query);
  });
  const visible = matches.slice(0, state.machoMethodLimit);
  return `<p class="explain">${fmt(matches.length)} matching Objective-C method entries in this physical file. These are static declarations, not observed calls or a complete function inventory.</p><ul>${visible.map((row) => `<li><code>${escapeHTML(`${row[1]}[${data.groups[row[0]].display_name} ${row[2] ?? 'selector unavailable'}]`)}</code><small>IMP ${escapeHTML(row[3])}</small></li>`).join('') || '<li>No matching methods</li>'}</ul>${matches.length > visible.length ? '<button id="macho-method-more" class="more-button">Show more ↓</button>' : ''}`;
}

async function openMachoMethods() {
  const item = state.selected;
  const summary = state.datasets.get(`macho_methods_index:${state.build}`)?.byKey.get(`${item.volume}\0${item.path}`);
  if (!summary?.bucket_url) return;
  const key = `macho_bucket:${state.build}:${summary.bucket_url}`;
  let bucket = state.datasets.get(key);
  if (!bucket) {
    bucket = await compressedJSON(summary.bucket_url);
    if (bucket.build !== state.build) throw new Error('Standalone method bucket build differs');
    state.datasets.set(key, bucket);
  }
  if (state.tab !== 'macho' || state.selected !== item) return;
  const data = bucket.files.find((entry) => entry.volume === item.volume && entry.path === item.path);
  if (!data || data.sha256 !== item.sha256 || data.records.length !== summary.method_count) {
    throw new Error('Standalone method bucket identity or count differs');
  }
  const target = $('#macho-methods');
  target.innerHTML = `<h4>Objective-C methods (${fmt(summary.method_count)})</h4><label class="searchbox"><span class="sr-only">Search Objective-C methods</span><input id="macho-method-search" type="search" placeholder="Search class, category, selector, or IMP…" value="${escapeHTML(state.machoMethodQuery)}"></label><div id="macho-method-results">${machoMethodResults(item, data)}</div>`;
  state.machoMethodData = data;
}

function machoSymbolResults(data) {
  const query = state.machoSymbolQuery.trim().toLocaleLowerCase();
  const matches = data.symbols.filter((row) => !query ||
    `${row[0]} ${row[1]} ${row[2]} ${row[3]}`.toLocaleLowerCase().includes(query));
  const visible = matches.slice(0, state.machoSymbolLimit);
  return `<p class="explain">${fmt(matches.length)} matching named __text symbol records. A symbol name can be private, an alias, or compiler generated; this is not an exhaustive function list.</p><ul>${visible.map((row) => `<li><code>${escapeHTML(row[1])}</code><small>${escapeHTML(row[0])} · ${escapeHTML(row[3])} · ${escapeHTML(row[2])}</small></li>`).join('') || '<li>No matching named symbols</li>'}</ul>${matches.length > visible.length ? '<button id="macho-symbol-more" class="more-button">Show more ↓</button>' : ''}`;
}

function liveSymbolResults(data) {
  const query = state.liveSymbolQuery.trim().toLocaleLowerCase();
  const matches = data.symbols.filter((row) => !query || row.join(' ').toLocaleLowerCase().includes(query));
  const visible = matches.slice(0, state.liveSymbolLimit);
  return `<p class="explain">${fmt(matches.length)} matching named __text records across verified Mach-O slices. Names and aliases do not enumerate every callable function.</p><ul>${visible.map((row) => `<li><code>${escapeHTML(row[1])}</code><small>${escapeHTML(row[4])} · ${escapeHTML(row[0])} · ${escapeHTML(row[3])} · ${escapeHTML(row[2])}</small></li>`).join('') || '<li>No matching named symbols</li>'}</ul>${matches.length > visible.length ? '<button id="live-symbol-more" class="more-button">Show more ↓</button>' : ''}`;
}

async function openLiveSymbols() {
  const item = state.selected;
  if (state.liveSymbolData?.path !== item.path) {
    state.liveSymbolQuery = '';
    state.liveSymbolLimit = 80;
  }
  const summary = state.datasets.get(`device_macho_symbols:${state.build}`)?.byPath.get(item.path);
  if (!summary?.bucket_url) return;
  const key = `live_symbols:${state.build}:${summary.bucket_url}`;
  let bucket = state.datasets.get(key);
  if (!bucket) {
    bucket = await compressedJSON(summary.bucket_url);
    if (bucket.build !== state.build) throw new Error('Live symbol bucket build differs');
    state.datasets.set(key, bucket);
  }
  if (state.tab !== 'device_macho' || state.selected !== item) return;
  const data = bucket.files.find((entry) => entry.path === item.path);
  if (!data || data.sha256 !== item.sha256 || data.symbols.length !== summary.named_symbol_count) {
    throw new Error('Live symbol bucket identity or count differs');
  }
  state.liveSymbolData = data;
  $('#live-symbols').innerHTML = `<h4>Named __text symbols (${fmt(summary.named_symbol_count)})</h4><label class="searchbox"><span class="sr-only">Search live named symbols</span><input id="live-symbol-search" type="search" placeholder="Search name, architecture, address…" value="${escapeHTML(state.liveSymbolQuery)}"></label><div id="live-symbol-results">${liveSymbolResults(data)}</div>`;
}

function iosSymbolResults(data) {
  const query = state.iosSymbolQuery.trim().toLocaleLowerCase();
  const matches = data.symbols.filter((row) => !query ||
    `${row[0]} ${row[1]} ${row[2]} ${row[3]}`.toLocaleLowerCase().includes(query));
  const visible = matches.slice(0, state.iosSymbolLimit);
  return `<p class="explain">${fmt(matches.length)} matching named __text records. Names include Objective-C methods, aliases, private names, and generated labels; a stripped name is not evidence that code is absent.</p><ul>${visible.map((row) => `<li><code>${escapeHTML(row[1])}</code><small>${escapeHTML(row[0])} · ${escapeHTML(row[3])} · ${escapeHTML(row[2])}</small></li>`).join('') || '<li>No matching named symbols</li>'}</ul>${matches.length > visible.length ? '<button id="ios-symbol-more" class="more-button">Show more ↓</button>' : ''}`;
}

async function openIosSymbols() {
  const item = state.selected;
  const summary = state.datasets.get(`ios_symbol_index:${state.build}`)?.byName.get(item.install_name);
  if (!summary?.bucket_url) return;
  const key = `ios_symbols:${state.build}:${summary.bucket_url}`;
  let bucket = state.datasets.get(key);
  if (!bucket) {
    bucket = await compressedJSON(summary.bucket_url);
    if (bucket.build !== state.build || bucket.cache_uuid !== activeBuild().cache_uuid) throw new Error('iOS symbol bucket identity differs');
    state.datasets.set(key, bucket);
  }
  if (state.tab !== 'images' || state.selected !== item) return;
  const data = bucket.images.find((entry) => entry.install_name === item.install_name);
  if (!data || data.uuid !== item.uuid || data.symbols.length !== summary.named_symbol_count) {
    throw new Error('iOS symbol bucket identity or count differs');
  }
  state.iosSymbolData = data;
  $('#ios-symbols').innerHTML = `<h4>Named __text symbols (${fmt(summary.named_symbol_count)})</h4><label class="searchbox"><span class="sr-only">Search named symbols</span><input id="ios-symbol-search" type="search" placeholder="Search symbol name, address, or visibility…" value="${escapeHTML(state.iosSymbolQuery)}"></label><div id="ios-symbol-results">${iosSymbolResults(data)}</div>`;
}

async function openMachoSymbols() {
  const item = state.selected;
  const summary = state.datasets.get(`macho_symbol_index:${state.build}`)?.byKey.get(`${item.volume}\0${item.path}`);
  if (!summary?.bucket_url) return;
  const key = `macho_symbols:${state.build}:${summary.bucket_url}`;
  let bucket = state.datasets.get(key);
  if (!bucket) {
    bucket = await compressedJSON(summary.bucket_url);
    if (bucket.build !== state.build) throw new Error('Standalone symbol bucket build differs');
    state.datasets.set(key, bucket);
  }
  if (state.tab !== 'macho' || state.selected !== item) return;
  const data = bucket.files.find((entry) => entry.volume === item.volume && entry.path === item.path);
  if (!data || data.sha256 !== item.sha256 || data.symbols.length !== summary.named_symbol_count) {
    throw new Error('Standalone symbol bucket identity or count differs');
  }
  const target = $('#macho-symbols');
  target.innerHTML = `<h4>Named __text symbols (${fmt(summary.named_symbol_count)})</h4><label class="searchbox"><span class="sr-only">Search named symbols</span><input id="macho-symbol-search" type="search" placeholder="Search symbol name, address, or visibility…" value="${escapeHTML(state.machoSymbolQuery)}"></label><div id="macho-symbol-results">${machoSymbolResults(data)}</div>`;
  state.machoSymbolData = data;
}

function machoSwiftResults(data) {
  const query = state.machoSwiftQuery.trim().toLocaleLowerCase();
  const types = [];
  const members = [];
  for (const declaration of data.declarations) {
    const label = `${declaration.kind} ${declaration.name}`;
    if (!query || label.toLocaleLowerCase().includes(query)) types.push(declaration);
    for (const [section, line] of declaration.members) {
      if (!query || `${label} ${section} ${line}`.toLocaleLowerCase().includes(query)) members.push([declaration.name, section, line]);
    }
  }
  const visibleTypes = types.slice(0, state.machoSwiftTypeLimit);
  const visibleMembers = members.slice(0, state.machoSwiftMemberLimit);
  return `<h4>Types and extensions (${fmt(types.length)})</h4><ul>${visibleTypes.map((row) => `<li><code>${escapeHTML(row.name)}</code><small>${escapeHTML(row.kind)} · ${fmt(row.members.length)} member / requirement lines</small></li>`).join('') || '<li>No matching declarations</li>'}</ul>${types.length > visibleTypes.length ? '<button id="macho-swift-type-more" class="more-button">Show more types ↓</button>' : ''}<h4>Methods and requirements (${fmt(members.length)})</h4><ul>${visibleMembers.map(([name, section, line]) => `<li><code>${escapeHTML(line)}</code><small>${escapeHTML(name)} · ${escapeHTML(section)}</small></li>`).join('') || '<li>No matching member lines</li>'}</ul>${members.length > visibleMembers.length ? '<button id="macho-swift-member-more" class="more-button">Show more members ↓</button>' : ''}`;
}

async function openMachoSwift() {
  const item = state.selected;
  const summary = state.datasets.get(`macho_swift_index:${state.build}`)?.byKey.get(`${item.volume}\0${item.path}`);
  if (!summary?.bucket_url) return;
  const key = `macho_swift:${state.build}:${summary.bucket_url}`;
  let bucket = state.datasets.get(key);
  if (!bucket) {
    bucket = await compressedJSON(summary.bucket_url);
    if (bucket.build !== state.build) throw new Error('Standalone Swift bucket build differs');
    state.datasets.set(key, bucket);
  }
  if (state.tab !== 'macho' || state.selected !== item) return;
  const data = bucket.files.find((entry) => entry.volume === item.volume && entry.path === item.path);
  if (!data || data.sha256 !== item.sha256 || data.declarations.length !== summary.declaration_count ||
      data.declarations.reduce((count, row) => count + row.members.length, 0) !== summary.member_count) {
    throw new Error('Standalone Swift bucket identity or count differs');
  }
  const target = $('#macho-swift');
  target.innerHTML = `<h4>Swift dump</h4><p class="explain">These are static tool-reported declaration and member lines, including stripped or generated labels. They do not prove ownership, public API, or runtime use.${summary.status === 'partially_parsed' ? ` ${fmt(summary.unparsed_line_count)} malformed output lines were omitted.` : ''}</p><label class="searchbox"><span class="sr-only">Search Swift metadata</span><input id="macho-swift-search" type="search" placeholder="Search types, methods, or requirements…" value="${escapeHTML(state.machoSwiftQuery)}"></label><div id="macho-swift-results">${machoSwiftResults(data)}</div>`;
  state.machoSwiftData = data;
}

function liveMethodList(objc) {
  const query = state.liveMethodQuery.trim().toLocaleLowerCase();
  const matches = objc.records.filter((row) => !query ||
    `${objc.groups[row[0]].display_name} ${row[2] || ''}`.toLocaleLowerCase().includes(query));
  const visible = matches.slice(0, state.liveMethodLimit);
  return `<p class="explain">${fmt(matches.length)} matching static Objective-C methods. This is a class-dump result, not a runtime call trace.</p><ul>${visible.map((row) => `<li><code>${escapeHTML(`${row[1]}[${objc.groups[row[0]].display_name} ${row[2] ?? 'selector unavailable'}]`)}</code><small>IMP ${escapeHTML(row[3])}</small></li>`).join('') || '<li>No matching methods</li>'}</ul>${matches.length > visible.length ? '<button id="live-method-more" class="more-button">Show more ↓</button>' : ''}`;
}

function liveMethodSection(item, objc) {
  if (state.liveMethodPath !== item.path) {
    state.liveMethodPath = item.path;
    state.liveMethodQuery = '';
    state.liveMethodLimit = 80;
  }
  if (!objc) return '<div class="direct-imports"><h4>Objective-C methods</h4><p class="explain">This file has not been indexed for Objective-C methods.</p></div>';
  if (objc.status === 'no_objc_info') return '<div class="direct-imports"><h4>Objective-C methods</h4><p class="explain">The exact-file class dump reported no Objective-C information. Other callable code may still be present.</p></div>';
  return `<div class="direct-imports"><h4>Objective-C methods (${fmt(objc.method_count)})</h4><label class="searchbox"><span class="sr-only">Search live methods</span><input id="live-method-search" type="search" placeholder="Search classes or selectors…" value="${escapeHTML(state.liveMethodQuery)}"></label><div id="live-method-results">${liveMethodList(objc)}</div></div>`;
}

function liveDependencySection(dependencies) {
  if (!dependencies) return '';
  const rows = dependencies.slices.flatMap((part) => part.dependencies.map((load) =>
    `<li><span>${escapeHTML(load.install_name)}</span><small>${escapeHTML(part.architecture)} · ${escapeHTML(load.load_command.replace('LC_', '').replace('_DYLIB', ''))}</small></li>`)).join('');
  const rpaths = dependencies.slices.flatMap((part) => part.rpaths.map((path) =>
    `<li><span>${escapeHTML(path)}</span><small>${escapeHTML(part.architecture)}</small></li>`)).join('');
  const count = dependencies.slices.reduce((total, part) => total + part.dependencies.length, 0);
  const redacted = dependencies.slices.reduce((total, part) => total + part.redacted_rpath_count, 0);
  return `<div class="direct-imports"><h4>Direct library loads (${fmt(count)})</h4><p class="explain">Declared by Mach-O load commands across all file slices; repeated names may occur across architectures. This does not establish which path dyld resolved at runtime.</p><ul>${rows || '<li>No direct library loads declared</li>'}</ul>${rpaths || redacted ? `<h4>Runpath declarations</h4><ul>${rpaths || '<li>No public runpaths</li>'}</ul>${redacted ? `<p class="explain">${fmt(redacted)} embedded build-machine path${redacted === 1 ? '' : 's'} withheld.</p>` : ''}` : ''}</div>`;
}

function detailHTML(item, mode, data) {
  if (!item) return `<div class="empty-detail">Select a row to inspect its source and metadata.</div>`;
  if (mode === 'objc') {
    const [name, address, label, installName, resolution] = item;
    const imageLink = installName ? `<button class="inline-link" data-linked-tab="images" data-linked-query="${escapeHTML(installName)}">${escapeHTML(installName)} ↗</button>` : 'Unresolved';
    const methods = state.datasets.get(`methods_index:${state.build}`)?.images.find((image) => image.install_name === installName)?.groups.find((group) => group[0] === name);
    return `<span class="detail-label">OBJECTIVE-C CLASS ENTRY</span><h3>${escapeHTML(name)}</h3><dl><dt>CLASS METADATA ADDRESS</dt><dd>${escapeHTML(address)}</dd><dt>CACHE IMAGE LABEL</dt><dd>${escapeHTML(label)}</dd><dt>DEFINING CACHE IMAGE</dt><dd>${imageLink}</dd><dt>IMAGE RESOLUTION</dt><dd>${resolution === 'segment_address' ? 'Class address within a Mach-O segment of one matching image' : resolution === 'unique_label' ? 'Unique image basename in this cache' : 'No unique image established'}</dd>${methods ? `<dt>INDEXED METHODS</dt><dd><button class="inline-link" data-linked-tab="methods" data-linked-query="class:${escapeHTML(name)}">${fmt(methods[1])} entries ↗</button></dd>` : ''}</dl><p class="explain">This is an entry in the dyld cache Objective-C optimization table. Names and addresses describe static metadata in the official firmware, not live objects or method calls. Multiple entries may share a class name.</p>`;
  }
  if (mode === 'methods') {
    const [className, installName, kind, selector, address] = item;
    const source = data.classes.find((entry) => entry.display_name === className && entry.install_name === installName);
    return `<span class="detail-label">OBJECTIVE-C METHOD METADATA</span><h3>${escapeHTML(`${kind}[${className} ${selector ?? 'selector unavailable'}]`)}</h3><dl><dt>IMP ADDRESS</dt><dd>${escapeHTML(address)}</dd><dt>SELECTOR</dt><dd>${escapeHTML(selector ?? 'Not decoded in class dump')}</dd><dt>DECLARATION</dt><dd>${source.category_name ? 'CATEGORY' : 'CLASS'} · ${escapeHTML(className)}</dd><dt>DEFINING IMAGE</dt><dd><button class="inline-link" data-linked-tab="images" data-linked-query="${escapeHTML(installName)}">${escapeHTML(installName)} ↗</button></dd><dt>MACH-O UUID</dt><dd>${escapeHTML(source.image_uuid)}</dd><dt>EXTRACTED IMAGE SHA-256</dt><dd>${escapeHTML(source.extracted_image_sha256 || 'Not extracted for this catalog')}</dd>${source.cache_main_sha256 ? `<dt>MAIN CACHE SHA-256</dt><dd>${escapeHTML(source.cache_main_sha256)}</dd>` : ''}<dt>CLASS DUMP SHA-256</dt><dd>${escapeHTML(source.class_dump_sha256)}</dd></dl><p class="explain">Method metadata and implementation address from this exact cache image. A missing selector stays unknown. Multiple entries for one known selector can have different addresses; this page does not resolve which implementation runs. It does not show a runtime call, verify behavior, or establish a safe tweak hook. The full class dump remains local; a standalone analysis image is created only for selected studies.</p>`;
  }
  if (mode === 'protocols') {
    const [name, address, label, installName, resolution] = item;
    const candidates = data.ambiguous_labels[label] || [];
    const imageInfo = installName ? `<button class="inline-link" data-linked-tab="images" data-linked-query="${escapeHTML(installName)}">${escapeHTML(installName)} ↗</button>` : `${fmt(candidates.length)} candidate images: ${escapeHTML(candidates.join(', '))}`;
    return `<span class="detail-label">OBJECTIVE-C PROTOCOL TABLE ENTRY</span><h3>${escapeHTML(name)}</h3><dl><dt>TABLE ADDRESS</dt><dd>${escapeHTML(address)}</dd><dt>REPORTED IMAGE LABEL</dt><dd>${escapeHTML(label)}</dd><dt>MATCHING CACHE IMAGE</dt><dd>${imageInfo}</dd><dt>LABEL RESOLUTION</dt><dd>${resolution === 'unique_label' ? 'One image has this basename' : 'Multiple images have this basename; no exact image assigned'}</dd></dl><p class="explain">This is a protocol entry associated with a reported image label in the cache optimization table. The address can refer to shared metadata; an image-label match does not prove that the image defines the protocol or uses it at runtime.</p>`;
  }
  if (mode === 'images' || mode === 'driverkit') {
    const present = item.physical_volumes.length > 0;
    const consumers = item.service_consumer_count;
    const graph = state.datasets.get(`${mode === 'driverkit' ? 'driverkit_dependencies' : 'dependencies'}:${state.build}`);
    const imports = graph?.byName.get(item.install_name)?.imports || [];
    const importers = graph?.importers.get(item.install_name) || [];
    const loadRows = imports.map((imp) => `<li>${graph.byName.has(imp.install_name) ? `<button class="inline-link" data-linked-tab="${mode}" data-linked-query="${escapeHTML(imp.install_name)}">${escapeHTML(imp.install_name)} ↗</button>` : escapeHTML(imp.install_name)}<small>${escapeHTML(imp.load_command.replace(/^LC_/, ''))} · ${graph.byName.has(imp.install_name) ? 'IN CACHE' : 'NO EXACT CACHE MATCH'}</small></li>`).join('');
    const importerRows = importers.slice(0, 30).map((entry) => `<li><button class="inline-link" data-linked-tab="${mode}" data-linked-query="${escapeHTML(entry.source)}">${escapeHTML(entry.source)} ↗</button><small>${escapeHTML(entry.load_command.replace(/^LC_/, ''))}</small></li>`).join('');
    const methodImage = mode === 'images' ? state.datasets.get(`methods_index:${state.build}`)?.images.find((entry) => entry.install_name === item.install_name) : null;
    const iosSymbols = mode === 'images' ? state.datasets.get(`ios_symbol_index:${state.build}`)?.byName.get(item.install_name) : null;
    const driverkitImage = mode === 'driverkit' ? state.datasets.get(`driverkit_functions:${state.build}`)?.images.find((entry) => entry.install_name === item.install_name) : null;
    const kind = item.install_name.includes('/PrivateFrameworks/') ? 'private framework' : item.install_name.includes('/Frameworks/') ? 'system framework' : item.install_name.includes('/usr/lib/') ? 'system library' : 'system component';
    const prominent = methodImage?.groups.filter((group) => group[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 3).map((group) => group[0]) || [];
    const overview = mode === 'images' ? `<p class="explain">This ${kind} is part of the iOS cache. Its class dump lists ${fmt(methodImage?.method_count || 0)} Objective-C methods in ${fmt(methodImage?.class_count || 0)} classes and ${fmt(methodImage?.category_count || 0)} categories.${prominent.length ? ` Prominent method groups: ${prominent.map(escapeHTML).join(', ')}.` : ''} This is a metadata overview; implementation and runtime behavior need separate study.</p>` : mode === 'driverkit' ? `<p class="explain">This ${kind} is in the separate DriverKit cache. Its symbol table names ${fmt(driverkitImage?.named_function_count || 0)} functions in <code>__text</code>; the Objective-C class dump lists no classes or methods. Names may include C++ methods. Implementation and runtime behavior need separate study.</p>` : '';
    const methodRow = methodImage ? `<dt>OBJECTIVE-C METHODS</dt><dd><button class="inline-link" data-linked-tab="methods" data-linked-query="image:${escapeHTML(item.install_name)}">${fmt(methodImage.method_count)} entries ↗</button></dd>` : '';
    const iosSymbolRow = iosSymbols ? `<dt>NAMED __TEXT SYMBOLS</dt><dd>${fmt(iosSymbols.named_symbol_count)} in code sections${iosSymbols.named_symbol_count ? '' : ' · no names found'}</dd>` : '';
    const iosSymbolSection = iosSymbols?.bucket_url ? `<div class="direct-imports" id="ios-symbols"><button class="inline-link" id="ios-symbol-open">Browse named __text symbols ↗</button></div>` : '';
    const functionalIntro = item.functional_intro ? `<p class="explain"><strong>${item.functional_intro.verbatim ? 'Apple overview:' : 'Documented role:'}</strong> ${item.functional_intro.verbatim ? `<q>${escapeHTML(item.functional_intro.summary)}</q>` : escapeHTML(item.functional_intro.summary)} <a href="${escapeHTML(item.functional_intro.source_url)}" target="_blank" rel="noopener">${escapeHTML(item.functional_intro.source_label)} ↗</a></p>` : '';
    const driverkitRow = driverkitImage ? `<dt>NAMED __TEXT FUNCTIONS</dt><dd>${fmt(driverkitImage.named_function_count)} symbols below</dd>` : '';
    const driverkitSection = driverkitImage ? `<div class="direct-imports"><h4>Named functions</h4><label class="searchbox"><span class="sr-only">Search named functions</span><input id="driverkit-function-search" type="search" placeholder="Search function names or addresses…" value="${escapeHTML(state.driverkitFunctionQuery)}"></label><div id="driverkit-function-results">${driverkitFunctionResults(item)}</div></div>` : '';
    const graphHTML = graph ? `<div class="direct-imports"><h4>Direct library loads (${fmt(imports.length)})</h4><ul>${loadRows || '<li>None recorded</li>'}</ul></div><div class="direct-imports"><h4>Loaded by cached images (${fmt(importers.length)})</h4><ul>${importerRows || '<li>None recorded</li>'}</ul>${importers.length > 30 ? `<button class="more-button" data-linked-tab="${mode}" data-linked-query="imports:${escapeHTML(item.install_name)}">View all ${fmt(importers.length)} importers ↗</button>` : ''}</div>` : '';
    return `<span class="detail-label">${mode === 'driverkit' ? 'DRIVERKIT CACHE IMAGE' : 'IN-CACHE IMAGE'}</span><h3>${escapeHTML(item.install_name.split('/').pop())}</h3>${functionalIntro}${overview}<dl><dt>LOGICAL INSTALL NAME</dt><dd>${escapeHTML(item.install_name)}</dd>${methodRow}${iosSymbolRow}${driverkitRow}<dt>IMAGE UUID</dt><dd>${escapeHTML(item.uuid)}</dd><dt>SOURCE VERSION</dt><dd>${escapeHTML(item.version || 'Not recorded')}</dd><dt>CACHE UUID</dt><dd>${escapeHTML(data.cache_uuid)}</dd><dt>STANDALONE FILE IN SCANNED IMAGES</dt><dd>${present ? escapeHTML(item.physical_volumes.join(', ')) : 'None observed'}</dd>${consumers == null ? '' : `<dt>DIRECT IMPORTS BY INDEXED SERVICE EXECUTABLES</dt><dd>${fmt(consumers)}${consumers ? ` <button class="inline-link" data-linked-tab="services" data-linked-query="${escapeHTML(item.install_name)}">View services ↗</button>` : ''}</dd>`}${item.objc_class_count == null ? '' : `<dt>OBJECTIVE-C CLASS ENTRIES</dt><dd>${fmt(item.objc_class_count)}${item.objc_class_count ? ` <button class="inline-link" data-linked-tab="objc" data-linked-query="image:${escapeHTML(item.install_name)}">View classes ↗</button>` : ''}</dd>`}${item.objc_protocol_entry_count == null ? '' : `<dt>PROTOCOL TABLE ENTRIES WITH UNIQUE IMAGE LABEL</dt><dd>${fmt(item.objc_protocol_entry_count)}${item.objc_protocol_entry_count ? ` <button class="inline-link" data-linked-tab="protocols" data-linked-query="image:${escapeHTML(item.install_name)}">View entries ↗</button>` : ''}</dd>`}${item.swift_conformance_count == null ? '' : `<dt>SWIFT TYPE CONFORMANCES</dt><dd>${fmt(item.swift_conformance_count)}${item.swift_conformance_count ? ` <button class="inline-link" data-linked-tab="swift" data-linked-query="image:${escapeHTML(item.install_name)}">View conformances ↗</button>` : ''}</dd>`}${mode !== 'images' || !graph ? '' : `<dt>TRANSITIVE LOAD PATHS</dt><dd><button class="inline-link" data-linked-tab="reach" data-linked-query="source:${escapeHTML(item.install_name)}">Trace dependency reach ↗</button></dd>`}</dl>${iosSymbolSection}${driverkitSection}${graphHTML}<p class="explain">${present ? 'A separate physical file was also found at this logical path. The cache image and file remain distinct records.' : 'No regular file exists at this path in the three processed IPSW images. Its executable image is listed in the dyld shared cache.'} Library edges are direct static Mach-O load commands, not runtime calls; weak loads may never resolve.</p>`;
  }
  if (mode === 'macho') {
    const slices = item.slices.map((part) => `<li>${escapeHTML(part.architecture)} · ${escapeHTML(part.file_type)} · UUID ${escapeHTML(part.uuid || 'Not present')}</li>`).join('');
    const identity = state.datasets.get(`macho_identity:${state.build}`)?.byKey.get(`${item.volume}\0${item.path}`);
    const methods = state.datasets.get(`macho_methods_index:${state.build}`)?.byKey.get(`${item.volume}\0${item.path}`);
    const symbols = state.datasets.get(`macho_symbol_index:${state.build}`)?.byKey.get(`${item.volume}\0${item.path}`);
    const swift = state.datasets.get(`macho_swift_index:${state.build}`)?.byKey.get(`${item.volume}\0${item.path}`);
    const methodRow = methods ? `<dt>OBJECTIVE-C METHODS</dt><dd>${fmt(methods.method_count)} indexed entries${methods.status === 'no_objc_info' ? ' · no ObjC metadata reported' : ''}</dd><dt>OBJECTIVE-C CLASSES</dt><dd>${fmt(methods.class_count)} classes · ${fmt(methods.category_count)} categories</dd>` : '';
    const methodSection = methods?.bucket_url ? `<div class="direct-imports" id="macho-methods"><button class="inline-link" id="macho-method-open">Browse Objective-C methods ↗</button></div>` : '';
    const symbolRow = symbols ? `<dt>NAMED __TEXT SYMBOLS</dt><dd>${fmt(symbols.named_symbol_count)} in code sections${symbols.named_symbol_count ? '' : ' · no names found'}</dd>` : '';
    const symbolSection = symbols?.bucket_url ? `<div class="direct-imports" id="macho-symbols"><button class="inline-link" id="macho-symbol-open">Browse named __text symbols ↗</button></div>` : '';
    const swiftRow = swift ? `<dt>SWIFT DUMP</dt><dd>${fmt(swift.declaration_count)} declarations · ${fmt(swift.member_count)} member / requirement lines${swift.status === 'partially_parsed' ? ` · ${fmt(swift.unparsed_line_count)} malformed lines` : swift.status === 'no_swift_info' ? ' · no Swift metadata reported' : ''}</dd>` : '';
    const swiftSection = swift?.bucket_url ? `<div class="direct-imports" id="macho-swift"><button class="inline-link" id="macho-swift-open">Browse Swift metadata ↗</button></div>` : '';
    const identityRow = identity ? `<dt>LIVE DEVICE IDENTITY</dt><dd>${identity.status === 'matched' ? 'SHA-256 matches this iPhone' : 'No byte match established · ' + escapeHTML(identity.status.replaceAll('_', ' '))}</dd><dt>MAPPED DEVICE PATH</dt><dd>${escapeHTML(identity.device_path)}${identity.status === 'matched' && item.volume === 'FileSystem' ? ` · <button class="inline-link" data-linked-tab="device" data-linked-query="${escapeHTML(identity.device_path)}">Inspect live path ↗</button>` : ''}</dd>` : '';
    const identityExplanation = identity?.status === 'matched' ? 'These exact bytes matched a read-only SHA-256 pass on the connected iPhone at the recorded observation time.' : identity?.status === 'unobserved_at_mapped_path' ? 'The snapshot had no file at this firmware staging path. This does not establish that the app or code is absent elsewhere on the phone.' : 'This firmware file has no verified byte match to the device in the current catalog.';
    return `<span class="detail-label">STANDALONE MACH-O FILE</span><h3>${escapeHTML(item.path.split('/').pop())}</h3><dl><dt>PATH</dt><dd>${escapeHTML(item.path)}</dd><dt>IPSW VOLUME</dt><dd>${escapeHTML(item.volume)}</dd><dt>FILE SIZE</dt><dd>${size(item.size)}</dd><dt>FILE SHA-256</dt><dd>${escapeHTML(item.sha256)}</dd><dt>ARCHITECTURES AND FILE TYPES</dt><dd><ul>${slices}</ul></dd>${identityRow}${methodRow}${symbolRow}${swiftRow}<dt>FILESYSTEM RECORD</dt><dd><button class="inline-link" data-linked-tab="files" data-linked-query="${escapeHTML(item.path)}">Inspect path ↗</button></dd></dl>${methodSection}${symbolSection}${swiftSection}<p class="explain">${identityExplanation} A zero ObjC, symbol, or Swift result does not mean there are no callable functions, and static metadata does not prove execution.</p>`;
  }
  if (filesystemMode(mode)) {
    const [volumeIndex, path, type, bytes, target] = item;
    const volume = data.volumes[volumeIndex];
    return `<span class="detail-label">${mode === 'restore' ? 'RESTORE RAMDISK ENTRY' : 'FILESYSTEM ENTRY'}</span><h3>${escapeHTML(path.split('/').pop())}</h3><dl><dt>PATH</dt><dd>${escapeHTML(path)}</dd><dt>VOLUME</dt><dd>${escapeHTML(volume.name)}</dd><dt>SOURCE IMAGE</dt><dd>${escapeHTML(volume.image_name)}</dd><dt>TYPE</dt><dd>${escapeHTML(type)}</dd><dt>SIZE</dt><dd>${escapeHTML(size(bytes))}</dd>${target ? `<dt>LINK TARGET</dt><dd>${escapeHTML(target)}</dd>` : ''}</dl><p class="explain">${mode === 'restore' ? 'Observed in a mounted IPSW restore environment. This is not the normal running iOS root filesystem.' : 'Observed in the mounted official firmware image. A file path here does not establish that the same bytes are present on a running device.'}</p>`;
  }
  if (mode === 'device_macho') {
    const slices = item.slices.map((part) => `<li>${escapeHTML(part.architecture)} · ${escapeHTML(part.file_type)} · UUID ${escapeHTML(part.uuid || 'Not present')}</li>`).join('');
    const objc = state.datasets.get(`device_macho_objc:${state.build}`)?.byPath.get(item.path);
    const dependencies = state.datasets.get(`device_macho_dependencies:${state.build}`)?.byPath.get(item.path);
    const symbols = state.datasets.get(`device_macho_symbols:${state.build}`)?.byPath.get(item.path);
    const symbolRow = symbols ? `<dt>NAMED __TEXT SYMBOLS</dt><dd>${fmt(symbols.named_symbol_count)} across ${fmt(symbols.slice_count)} slice(s)${symbols.named_symbol_count ? '' : ' · no names found'}</dd>` : '';
    const symbolSection = symbols?.bucket_url ? `<div class="direct-imports" id="live-symbols"><button class="inline-link" id="live-symbol-open">Browse named __text symbols ↗</button></div>` : '';
    return `<span class="detail-label">LIVE JAILBREAK MACH-O</span><h3>${escapeHTML(item.path.split('/').pop())}</h3><dl><dt>DEVICE PATH</dt><dd>${escapeHTML(item.path)}</dd><dt>FILE SIZE</dt><dd>${size(item.size)}</dd><dt>DEVICE SHA-256</dt><dd>${escapeHTML(item.sha256)}</dd><dt>ARCHITECTURES AND FILE TYPES</dt><dd><ul>${slices}</ul></dd>${objc ? `<dt>OBJECTIVE-C METHODS</dt><dd>${fmt(objc.method_count)} · ${fmt(objc.class_count)} classes · ${fmt(objc.category_count)} categories</dd>` : ''}${symbolRow}<dt>DEVICE FILE RECORD</dt><dd><button class="inline-link" data-linked-tab="device" data-linked-query="${escapeHTML(item.path)}">Inspect path ↗</button></dd></dl>${liveMethodSection(item, objc)}${symbolSection}${liveDependencySection(dependencies)}<p class="explain">The bytes were acquired from this iPhone and matched a device-side SHA-256 pass. Method and symbol names are static metadata; they do not prove a process loaded the file or that a hook is safe.</p>`;
  }
  if (mode === 'device') {
    const [path, type, bytes] = item;
    const broad = data.kind === 'live_device_public_paths';
    const liveMacho = state.datasets.get(`device_macho:${state.build}`)?.byPath.get(path);
    const stockIdentity = state.datasets.get(`macho_identity:${state.build}`)?.byDevicePath.get(path);
    return `<span class="detail-label">OBSERVED DEVICE PATH</span><h3>${escapeHTML(path.split('/').pop())}</h3><dl><dt>LIVE PATH</dt><dd>${escapeHTML(path)}</dd><dt>TYPE</dt><dd>${escapeHTML(type)}</dd>${bytes == null ? '' : `<dt>SIZE AT SCAN</dt><dd>${escapeHTML(size(bytes))}</dd>`}${liveMacho ? `<dt>MACH-O</dt><dd>${escapeHTML(liveMacho.slices.map((part) => `${part.architecture} ${part.file_type}`).join(', '))} · <button class="inline-link" data-linked-tab="device_macho" data-linked-query="${escapeHTML(path)}">Verified file details ↗</button></dd>` : ''}${stockIdentity ? `<dt>VERIFIED IPSW MACH-O</dt><dd>SHA-256 matched · <button class="inline-link" data-linked-tab="macho" data-linked-query="${escapeHTML(stockIdentity.path)}">Inspect binary analysis ↗</button></dd>` : ''}<dt>SOURCE</dt><dd>${broad ? 'Privacy-reviewed live device snapshot' : 'Read-only scan of seven /rootfs system roots'}</dd></dl><p class="explain">${broad ? 'This path was observed in a reviewed live scan. Other paths, including user and app data, are withheld from the public catalog.' : 'This path was observed in the RootHide /rootfs view. The public scan does not yet cover the jailbreak namespace, preboot, or user data.'} ${stockIdentity ? 'The exact file bytes also matched the official build by device-side SHA-256.' : 'A path record alone does not prove file contents.'} Static metadata does not prove runtime use.</p>`;
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
  if (mode === 'services') {
    const source = item.executable;
    const location = source.matches.length ? source.matches.map((match) => `${match.volume} (${match.type})`).join(', ') : 'Not matched in the three scanned images';
    const args = item.program_arguments.length ? item.program_arguments.join(' ') : 'Not declared';
    const services = item.mach_services.length ? item.mach_services.join(', ') : 'None declared';
    const events = item.launch_events.length ? item.launch_events.join(', ') : 'None declared';
    const keepAlive = item.keep_alive == null ? 'Not declared' : JSON.stringify(item.keep_alive);
    const binary = serviceBinary(item, data);
    const imports = binary?.imports || [];
    const importRows = imports.map((imp) => {
      const cache = imp.cache_matches[0];
      const target = cache ? cache.platform === 'DriverKit' ? 'driverkit' : 'images' : imp.file_matches.length ? 'files' : null;
      const status = cache ? `${cache.platform} CACHE` : imp.file_matches.length ? `${imp.file_matches.join(', ')} FILE` : 'NO CATALOG MATCH';
      const name = target ? `<button class="inline-link" data-linked-tab="${target}" data-linked-query="${escapeHTML(imp.install_name)}">${escapeHTML(imp.install_name)} ↗</button>` : escapeHTML(imp.install_name);
      return `<li><span>${name}</span><small>${imp.load_command === 'LC_LOAD_WEAK_DYLIB' ? 'WEAK · ' : ''}${escapeHTML(status)}</small></li>`;
    }).join('');
    return `<span class="detail-label">LAUNCHD ${item.kind.toUpperCase()}</span><h3>${escapeHTML(item.label || item.plist_path.split('/').pop())}</h3><dl><dt>PLIST PATH</dt><dd>${escapeHTML(item.plist_path)}</dd><dt>PLIST SHA-256</dt><dd>${escapeHTML(item.plist_sha256)}</dd><dt>PROGRAM</dt><dd>${escapeHTML(item.program || 'Not declared')}</dd><dt>PROGRAM ARGUMENTS</dt><dd>${escapeHTML(args)}</dd><dt>EXECUTABLE RESOLUTION</dt><dd>${escapeHTML(source.status)} · ${escapeHTML(location)}</dd>${source.source_path && source.source_path !== item.program ? `<dt>PATH INSIDE CRYPTEX IMAGE</dt><dd>${escapeHTML(source.source_path)}</dd>` : ''}${binary ? `<dt>EXECUTABLE SHA-256</dt><dd>${escapeHTML(binary.sha256)}</dd><dt>MACH-O UUID</dt><dd>${escapeHTML(binary.macho_uuid)}</dd>` : ''}<dt>MACH SERVICES (${fmt(item.mach_services.length)})</dt><dd>${escapeHTML(services)}</dd><dt>LAUNCH EVENTS (${fmt(item.launch_events.length)})</dt><dd>${escapeHTML(events)}</dd><dt>USER</dt><dd>${escapeHTML(item.user || 'Not declared')}</dd><dt>RUN AT LOAD</dt><dd>${escapeHTML(item.run_at_load == null ? 'Not declared' : String(item.run_at_load))}</dd><dt>KEEP ALIVE</dt><dd>${escapeHTML(keepAlive)}</dd></dl>${binary ? `<div class="direct-imports"><h4>Direct Mach-O loads (${fmt(imports.length)})</h4><ul>${importRows}</ul></div>` : ''}<p class="explain">Parsed from official firmware. Launchd and Mach-O declarations do not prove that a job ran or that dyld loaded every library. “No catalog match” is limited to the scanned IPSW images and cache families.</p>`;
  }
  return `<span class="detail-label">CACHE FILE</span><h3>${escapeHTML(item.name)}</h3><dl><dt>FILE SIZE</dt><dd>${escapeHTML(size(item.size))}</dd><dt>SHA-256</dt><dd>${escapeHTML(item.sha256)}</dd><dt>CACHE FAMILY UUID</dt><dd>${escapeHTML(data.cache_uuid)}</dd></dl><p class="explain">A physical member of the extracted SystemOS dyld cache family. Its contents are not hosted by this site.</p>`;
}

function renderRows(items, mode, data) {
  const visible = items.slice(0, state.limit);
  const rows = visible.map((item, index) => {
    const path = mode === 'images' || mode === 'driverkit' ? item.install_name : mode === 'methods' ? `${item[2]}[${item[0]} ${item[3] ?? 'selector unavailable'}]` : mode === 'objc' || mode === 'protocols' ? item[0] : filesystemMode(mode) ? item[1] : mode === 'device' ? item[0] : mode === 'archive' || mode === 'macho' || mode === 'device_macho' ? item.path : mode === 'kernel' ? item.id : mode === 'services' ? item.label || item.plist_path : item.name;
    const secondary = mode === 'images' || mode === 'driverkit' ? (item.physical_volumes.length ? 'DISK + CACHE' : 'IN CACHE') : mode === 'methods' ? item[4] : mode === 'objc' || mode === 'protocols' ? item[2] : mode === 'restore' ? data.volumes[item[0]].name.replace(/^RestoreRamDisk/, '') : mode === 'files' ? data.volumes[item[0]].name : mode === 'device' ? item[1].toUpperCase() : mode === 'archive' ? item.kind.toUpperCase() : mode === 'macho' ? `${item.volume} · ${item.slices[0].file_type}` : mode === 'device_macho' ? item.slices.map((part) => part.file_type).join(', ') : mode === 'kernel' ? item.variant.toUpperCase() : mode === 'services' ? item.executable.status.toUpperCase() : size(item.size);
    const icon = mode === 'images' || mode === 'driverkit' ? '◇' : mode === 'objc' || mode === 'protocols' || mode === 'methods' ? '◌' : filesystemMode(mode) ? item[2] === 'directory' ? '▤' : item[2] === 'symlink' ? '↗' : '·' : mode === 'device' ? item[1] === 'directory' ? '▤' : item[1] === 'symlink' ? '↗' : '·' : mode === 'archive' || mode === 'macho' || mode === 'device_macho' ? '▧' : mode === 'kernel' ? '✳' : mode === 'services' ? '◉' : '◈';
    return `<button class="result-row ${state.selected === item ? 'selected' : ''}" data-index="${index}" title="${escapeHTML(path)}"><span class="row-main"><span class="row-icon">${icon}</span><span class="row-text">${escapeHTML(path)}</span></span><span class="row-sub">${escapeHTML(secondary)}</span></button>`;
  }).join('');
  $('#result-count').textContent = `${fmt(items.length)} result${items.length === 1 ? '' : 's'}`;
  const heading = mode === 'kernel' ? 'BUNDLE IDENTIFIER' : mode === 'archive' ? 'ARCHIVE MEMBER' : mode === 'macho' || mode === 'device_macho' ? 'FILE PATH' : mode === 'services' ? 'SERVICE LABEL' : mode === 'methods' ? 'METHOD' : mode === 'objc' ? 'CLASS NAME' : mode === 'protocols' ? 'PROTOCOL NAME' : 'PATH / INSTALL NAME';
  const sourceHeading = mode === 'kernel' ? 'VARIANT' : mode === 'archive' ? 'KIND' : mode === 'device_macho' ? 'FILE TYPE' : mode === 'services' ? 'EXECUTABLE' : mode === 'methods' ? 'IMP ADDRESS' : mode === 'objc' || mode === 'protocols' ? 'IMAGE LABEL' : 'SOURCE';
  $('#results').innerHTML = `<div class="result-head"><span>${heading}</span><span>${sourceHeading}</span></div>${rows || '<p class="empty-state">No matching entries in the selected source.</p>'}${items.length > state.limit ? '<button id="show-more" class="more-button">Show more ↓</button>' : ''}`;
  $('#detail').innerHTML = detailHTML(state.selected, mode, data);
  for (const row of document.querySelectorAll('.result-row')) row.addEventListener('click', () => { state.selected = visible[Number(row.dataset.index)]; state.driverkitFunctionQuery = ''; state.driverkitFunctionLimit = 80; state.iosSymbolQuery = ''; state.iosSymbolLimit = 80; state.iosSymbolData = null; state.machoMethodQuery = ''; state.machoMethodLimit = 80; state.machoMethodData = null; state.machoSymbolQuery = ''; state.machoSymbolLimit = 80; state.machoSymbolData = null; state.machoSwiftQuery = ''; state.machoSwiftTypeLimit = 40; state.machoSwiftMemberLimit = 80; state.machoSwiftData = null; $('#detail').innerHTML = detailHTML(state.selected, mode, data); document.querySelectorAll('.result-row').forEach((other) => other.classList.toggle('selected', other === row)); });
  $('#show-more')?.addEventListener('click', () => { state.limit += 80; renderRows(items, mode, data); });
}

function renderResults() {
  const mode = state.tab;
  if (mode === 'swift') { renderSwiftResults(); return; }
  if (mode === 'reach') { renderReachResults(); return; }
  if (mode === 'methods' && !state.methodImage) { renderMethodsIndexResults(); return; }
  const data = state.datasets.get(`${filesystemMode(mode) ? mode : mode === 'device' ? 'device' : mode === 'device_macho' ? 'device_macho' : mode === 'objc' ? 'objc' : mode === 'methods' ? 'methods' : mode === 'protocols' ? 'protocols' : mode === 'driverkit' ? 'driverkit' : mode === 'macho' ? 'macho' : mode === 'archive' ? 'archive' : mode === 'kernel' ? 'kernel' : mode === 'services' ? 'services' : 'dyld'}:${state.build}`);
  if (!data || !['images','driverkit','macho','device_macho','objc','methods','protocols','files','restore','device','caches','archive','kernel','services'].includes(mode)) return;
  if ((filesystemMode(mode) || mode === 'device') && !state.query.trim()) { renderDirectoryResults(mode, data); return; }
  const query = state.query.trim().toLocaleLowerCase();
  let items;
  if (filesystemMode(mode)) items = data.entries.filter((item) => (state.volume === 'all' || data.volumes[item[0]].name === state.volume) && (!query || item[1].toLocaleLowerCase().includes(query)));
  else if (mode === 'device') items = data.entries.filter((item) => !query || item[0].toLocaleLowerCase().includes(query));
  else if (mode === 'objc' && query.startsWith('image:')) items = data.records.filter((item) => item[3] === state.query.trim().slice(6));
  else if (mode === 'objc' && query.startsWith('class:')) items = data.records.filter((item) => item[0] === state.query.trim().slice(6));
  else if (mode === 'objc') items = data.records.filter((item) => !query || `${item[0]} ${item[1]} ${item[2]} ${item[3] || ''}`.toLocaleLowerCase().includes(query));
  else if (mode === 'methods' && query.startsWith('class:')) items = data.records.filter((item) => item[0] === state.query.trim().slice(6));
  else if (mode === 'methods' && query.startsWith('image:')) items = data.records.filter((item) => item[1] === state.query.trim().slice(6));
  else if (mode === 'methods') items = data.records.filter((item) => !query || `${item[0]} ${item[1]} ${item[3] ?? ''} ${item[4]}`.toLocaleLowerCase().includes(query));
  else if (mode === 'protocols' && query.startsWith('image:')) items = data.records.filter((item) => item[3] === state.query.trim().slice(6));
  else if (mode === 'protocols') items = data.records.filter((item) => !query || `${item[0]} ${item[1]} ${item[2]} ${item[3] || ''}`.toLocaleLowerCase().includes(query));
  else if ((mode === 'images' || mode === 'driverkit') && query.startsWith('imports:')) {
    const graph = state.datasets.get(`${mode === 'driverkit' ? 'driverkit_dependencies' : 'dependencies'}:${state.build}`);
    const sources = new Set((graph?.importers.get(state.query.trim().slice(8)) || []).map((entry) => entry.source));
    items = data.images.filter((item) => sources.has(item.install_name));
  }
  else if ((mode === 'images' || mode === 'driverkit') && query.startsWith('intro:')) {
    const term = query.slice(6).trim();
    items = data.images.filter((item) => item.functional_intro &&
      (!term || `${item.install_name} ${item.functional_intro.summary}`.toLocaleLowerCase().includes(term)));
  }
  else if (mode === 'images' || mode === 'driverkit') items = data.images.filter((item) => !query || item.install_name.toLocaleLowerCase().includes(query));
  else if (mode === 'macho') items = data.records.filter((item) => (state.volume === 'all' || item.volume === state.volume) && (!query || `${item.path} ${item.volume} ${item.sha256} ${item.slices.map((part) => `${part.architecture} ${part.file_type} ${part.uuid || ''}`).join(' ')}`.toLocaleLowerCase().includes(query)));
  else if (mode === 'device_macho') items = data.records.filter((item) => !query || `${item.path} ${item.sha256} ${item.slices.map((part) => `${part.architecture} ${part.file_type} ${part.uuid || ''}`).join(' ')}`.toLocaleLowerCase().includes(query));
  else if (mode === 'archive') items = data.entries.filter((item) => !query || item.path.toLocaleLowerCase().includes(query));
  else if (mode === 'kernel') items = data.kexts.filter((item) => (state.volume === 'all' || item.variant === state.volume) && (!query || `${item.id} ${item.name} ${item.bundle_path}`.toLocaleLowerCase().includes(query)));
  else if (mode === 'services') items = data.records.filter((item) => (state.volume === 'all' || item.executable.status === state.volume) && (!query || `${item.label} ${item.plist_path} ${item.program} ${item.mach_services.join(' ')} ${item.launch_events.join(' ')} ${serviceBinary(item, data)?.imports.map((imp) => imp.install_name).join(' ') || ''}`.toLocaleLowerCase().includes(query)));
  else items = data.files.filter((item) => !query || item.name.toLocaleLowerCase().includes(query));
  state.selected = items.includes(state.selected) ? state.selected : items.length === 1 ? items[0] : null;
  renderRows(items, mode, data);
}

function renderMethodsIndexResults() {
  const index = state.datasets.get(`methods_index:${state.build}`);
  if (!index || state.tab !== 'methods' || state.methodImage || !$('#results')) return;
  const query = state.query.trim().toLocaleLowerCase();
  const className = query.startsWith('class:') ? state.query.trim().slice(6) : null;
  const images = index.images.filter((image) => className
    ? image.groups.some((group) => group[0] === className)
    : !query || image.install_name.toLocaleLowerCase().includes(query) ||
      image.groups.some((group) => group[0].toLocaleLowerCase().includes(query)));
  const visible = images.slice(0, state.limit);
  $('#result-count').textContent = `${fmt(images.length)} indexed image${images.length === 1 ? '' : 's'}`;
  $('#results').innerHTML = `<div class="result-head"><span>CACHE IMAGE</span><span>METHODS</span></div>${visible.map((image, number) => `<button class="result-row" data-index="${number}" title="${escapeHTML(image.install_name)}"><span class="row-main"><span class="row-icon">◇</span><span class="row-text">${escapeHTML(image.install_name)}</span></span><span class="row-sub">${fmt(image.method_count)}</span></button>`).join('') || '<p class="empty-state">No indexed image matches this search.</p>'}${images.length > state.limit ? '<button id="show-more" class="more-button">Show more ↓</button>' : ''}`;
  $('#detail').innerHTML = '<div class="empty-detail">Select an indexed cache image to search its class and category methods. Images without an indexed method catalog are outside this view.</div>';
  for (const button of $('#results').querySelectorAll('.result-row')) button.addEventListener('click', () => {
    const image = visible[Number(button.dataset.index)];
    state.methodImage = image.install_name;
    if (!state.query.startsWith('class:')) state.query = '';
    state.limit = 80;
    state.selected = null;
    history.replaceState(null, '', `#methods/${encodeURIComponent(`image:${image.install_name}`)}`);
    renderMethodsExplorer().catch(showError);
  });
  $('#show-more')?.addEventListener('click', () => { state.limit += 80; renderMethodsIndexResults(); });
}

async function renderMethodsExplorer() {
  const explorer = $('#explorer');
  if (!activeBuild().objc_method_index_url) {
    explorer.innerHTML = '<p class="empty-state">No cache image method catalogs are published for this build.</p>';
    return;
  }
  explorer.innerHTML = '<p class="loading">Opening method index…</p>';
  const index = await dataset('methods_index');
  if (state.tab !== 'methods') return;
  if (!state.methodImage && state.query.startsWith('image:')) {
    state.methodImage = state.query.slice(6);
    state.query = '';
  }
  if (!state.methodImage && state.query.startsWith('class:')) {
    const name = state.query.slice(6);
    const matches = index.images.filter((image) => image.groups.some((group) => group[0] === name));
    if (matches.length === 1) state.methodImage = matches[0].install_name;
  }
  const image = state.methodImage ? index.images.find((item) => item.install_name === state.methodImage) : null;
  if (state.methodImage && !image) throw new Error('Selected image is absent from this build method index');
  updateSource();
  const unknownSelectors = image?.unknown_selector_count ?? activeBuild().objc_method_unknown_selector_count;
  const extraSwiftClasses = image?.unlisted_swift_class_count ?? activeBuild().objc_method_unlisted_swift_class_count;
  const summary = `<div class="kernel-summary"><div><strong>${fmt(image?.method_count ?? activeBuild().objc_method_count)} METHODS</strong><span>${image ? 'Class and category entries in this image' : 'Entries across indexed cache images'}${unknownSelectors ? ` · ${fmt(unknownSelectors)} selector labels unavailable` : ''}</span></div><div><strong>${fmt(image?.class_count ?? activeBuild().objc_method_class_count)} CLASSES</strong><span>${fmt(image?.category_count ?? activeBuild().objc_method_category_count)} categories · ${fmt(activeBuild().objc_method_image_count)} indexed image${activeBuild().objc_method_image_count === 1 ? '' : 's'}${extraSwiftClasses ? ` · ${fmt(extraSwiftClasses)} extra Swift-marked classes` : ''}</span></div></div>`;
  if (!image) {
    state.datasets.delete(`methods:${state.build}`);
    explorer.innerHTML = summary + toolbar({placeholder:'Search indexed cache images or class names…'}) + '<div class="explorer-grid"><div id="results" class="result-list"></div><aside id="detail" class="detail"></aside></div>';
    bindToolbar();
    renderMethodsIndexResults();
    return;
  }
  const key = `methods:${state.build}:${image.uuid}`;
  let data = state.datasets.get(key);
  if (!data) {
    data = await compressedJSON(image.url);
    if (data.build !== state.build || data.install_name !== image.install_name ||
        data.records.length !== image.method_count || data.classes.length !== image.groups.length) {
      throw new Error('Method bucket identity or count differs from its index');
    }
    state.datasets.set(key, data);
  }
  if (state.tab !== 'methods' || state.methodImage !== image.install_name) return;
  state.datasets.set(`methods:${state.build}`, data);
  explorer.innerHTML = summary + `<div class="reach-context"><button id="methods-back" class="inline-link">← All indexed images</button><strong>${escapeHTML(image.install_name)}</strong></div>` + toolbar({placeholder:'Search class, category, selector, or IMP address…'}) + '<div class="explorer-grid"><div id="results" class="result-list"></div><aside id="detail" class="detail"></aside></div>';
  $('#methods-back').addEventListener('click', () => {
    state.methodImage = null;
    state.query = '';
    state.limit = 80;
    state.selected = null;
    history.replaceState(null, '', '#methods');
    renderMethodsExplorer().catch(showError);
  });
  bindToolbar();
  $('#detail').addEventListener('click', (event) => {
    const link = event.target.closest('[data-linked-tab]');
    if (link) setTab(link.dataset.linkedTab, link.dataset.linkedQuery);
  });
  renderResults();
}

function reachDetail(graph, paths, target) {
  if (!target) return '<div class="empty-detail">Select a reachable image to inspect its shortest static load path.</div>';
  const chain = pathTo(paths.parent, target);
  const steps = chain.map((step, number) => `<li><span class="reach-step">${number ? escapeHTML(step.incoming.load_command.replace(/^LC_/, '')) : 'SOURCE IMAGE'}</span><button class="inline-link" data-linked-tab="images" data-linked-query="${escapeHTML(step.name)}">${escapeHTML(step.name)} ↗</button></li>`).join('');
  return `<span class="detail-label">STATIC LOAD PATH</span><h3>${escapeHTML(target.split('/').pop())}</h3><dl><dt>SHORTEST CHAIN</dt><dd>${fmt(chain.length - 1)} direct declaration${chain.length === 2 ? '' : 's'}</dd><dt>TARGET UUID</dt><dd>${escapeHTML(graph.byName.get(target).uuid)}</dd></dl><ol class="reach-path">${steps}</ol><p class="explain">Each step is an exact install-name match within this iOS cache family. The path shows static Mach-O load declarations, not a measured process load or call sequence. Other paths may also exist.</p>`;
}

function renderReachResults() {
  const graph = state.datasets.get(`dependencies:${state.build}`);
  if (!graph || state.tab !== 'reach' || !$('#results')) return;
  const query = state.query.trim().toLocaleLowerCase();
  const paths = state.reachPaths && (state.reachWeak ? state.reachPaths.all : state.reachPaths.withoutWeak);
  const items = state.reachSource
    ? [...paths.depth.entries()].filter(([name]) => name !== state.reachSource && (!query || name.toLocaleLowerCase().includes(query)))
      .sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]))
    : graph.images.filter((image) => !query || image.install_name.toLocaleLowerCase().includes(query))
      .sort((a, b) => a.install_name.localeCompare(b.install_name));
  const names = items.map((item) => state.reachSource ? item[0] : item.install_name);
  state.selected = names.includes(state.selected) ? state.selected : names.length === 1 ? names[0] : null;
  const visible = items.slice(0, state.limit);
  $('#result-count').textContent = `${fmt(items.length)} result${items.length === 1 ? '' : 's'}`;
  $('#results').innerHTML = `<div class="result-head"><span>${state.reachSource ? 'REACHABLE IMAGE' : 'SOURCE IMAGE'}</span><span>${state.reachSource ? 'STEPS' : 'DIRECT LOADS'}</span></div>${visible.map((item, number) => {
    const name = state.reachSource ? item[0] : item.install_name;
    const secondary = state.reachSource ? String(item[1]) : fmt(item.imports.length);
    return `<button class="result-row ${state.selected === name ? 'selected' : ''}" data-index="${number}" title="${escapeHTML(name)}"><span class="row-main"><span class="row-icon">◇</span><span class="row-text">${escapeHTML(name)}</span></span><span class="row-sub">${secondary}</span></button>`;
  }).join('') || '<p class="empty-state">No matching images in this static graph.</p>'}${items.length > state.limit ? '<button id="show-more" class="more-button">Show more ↓</button>' : ''}`;
  $('#detail').innerHTML = state.reachSource ? reachDetail(graph, paths, state.selected) : `<span class="detail-label">SELECT A STARTING IMAGE</span><h3>Trace the cache graph</h3><p class="explain">Choose an image to see every in-cache image reachable through exact Mach-O load declarations. Paths can be viewed with or without weak loads.</p>`;
  for (const row of document.querySelectorAll('.result-row')) row.addEventListener('click', () => {
    const item = visible[Number(row.dataset.index)];
    const name = state.reachSource ? item[0] : item.install_name;
    if (!state.reachSource) { openReachSource(name).catch(showError); return; }
    state.selected = name;
    $('#detail').innerHTML = reachDetail(graph, paths, name);
    document.querySelectorAll('.result-row').forEach((other) => other.classList.toggle('selected', other === row));
  });
  $('#show-more')?.addEventListener('click', () => { state.limit += 80; renderReachResults(); });
}

async function openReachSource(name) {
  state.reachSource = name;
  state.reachPaths = null;
  state.reachWeak = false;
  state.query = '';
  state.limit = 80;
  state.selected = null;
  history.replaceState(null, '', `#reach/${encodeURIComponent(name)}`);
  await renderReachExplorer();
}

async function renderReachExplorer() {
  const explorer = $('#explorer');
  explorer.classList.add('reach-mode');
  if (!activeBuild().dyld_dependency_url) { explorer.innerHTML = '<p class="empty-state">No iOS cache load graph is available for this build.</p>'; return; }
  const graph = await dataset('dependencies');
  if (state.tab !== 'reach') return;
  if (state.reachSource && !graph.byName.has(state.reachSource)) throw new Error('Starting image is absent from this exact cache build');
  if (state.reachSource && !state.reachPaths) state.reachPaths = {
    withoutWeak:computeReach(graph.images, state.reachSource, false),
    all:computeReach(graph.images, state.reachSource, true)
  };
  const summary = state.reachSource
    ? `<div class="kernel-summary"><div><strong>${fmt(state.reachPaths.withoutWeak.parent.size - 1)} WITHOUT WEAK LOADS</strong><span>Exact in-cache matches reachable through ordinary, re-export and upward load declarations</span></div><div><strong>${fmt(state.reachPaths.all.parent.size - 1)} INCLUDING WEAK LOADS</strong><span>Static reachability when weak declarations are also followed</span></div></div><div class="reach-context"><button id="reach-back" class="inline-link">← Choose another image</button><strong>${escapeHTML(state.reachSource)}</strong></div><div class="reach-modes"><button data-reach-mode="without" aria-pressed="${!state.reachWeak}">Without weak loads</button><button data-reach-mode="all" aria-pressed="${state.reachWeak}">Include weak loads</button></div>`
    : `<div class="kernel-summary"><div><strong>${fmt(graph.images.length)} CACHE IMAGES</strong><span>Pick a source image to follow its exact static Mach-O library loads</span></div><div><strong>${fmt(activeBuild().dyld_direct_import_count)} DIRECT LOADS</strong><span>Only exact matches within this cache family become graph edges</span></div></div>`;
  explorer.innerHTML = summary + toolbar({placeholder:state.reachSource ? 'Find a reachable library by install name…' : 'Choose a source library by install name…'}) + '<div class="explorer-grid"><div id="results" class="result-list"></div><aside id="detail" class="detail"></aside></div>';
  $('#reach-back')?.addEventListener('click', () => { state.reachSource = null; state.reachPaths = null; state.query = ''; state.selected = null; state.limit = 80; history.replaceState(null, '', '#reach'); renderReachExplorer().catch(showError); });
  for (const button of explorer.querySelectorAll('[data-reach-mode]')) button.addEventListener('click', () => {
    state.reachWeak = button.dataset.reachMode === 'all';
    explorer.querySelectorAll('[data-reach-mode]').forEach((item) => item.setAttribute('aria-pressed', item === button ? 'true' : 'false'));
    state.selected = null;
    state.limit = 80;
    renderReachResults();
  });
  bindToolbar();
  $('#detail').addEventListener('click', (event) => {
    const link = event.target.closest('[data-linked-tab]');
    if (link) setTab(link.dataset.linkedTab, link.dataset.linkedQuery);
  });
  renderReachResults();
}

async function swiftBucket(index, imageIndex) {
  const number = imageIndex % index.bucket_count;
  const key = `swiftbucket:${state.build}:${number}`;
  if (!state.datasets.has(key)) {
    const filename = index.buckets[number].file;
    state.datasets.set(key, await compressedJSON(activeBuild().swift_bucket_base + filename));
  }
  return state.datasets.get(key).records;
}

function swiftDetail(row, index) {
  if (!row) return '<div class="empty-detail">Select a conformance to inspect its metadata.</div>';
  const role = (label, address, symbol, imageIndex) => `<dt>${label}</dt><dd><strong>${escapeHTML(symbol || 'Name unavailable')}</strong><br><code>0x${address.toString(16)}</code><br><button class="inline-link" data-linked-tab="images" data-linked-query="${escapeHTML(index.images[imageIndex].install_name)}">${escapeHTML(index.images[imageIndex].install_name)} ↗</button></dd>`;
  return `<span class="detail-label">SWIFT TYPE CONFORMANCE</span><h3>${escapeHTML(row[3] || `0x${row[2].toString(16)}`)}</h3><dl>${role('TYPE', row[2], row[3], row[4])}${role('PROTOCOL', row[5], row[6], row[7])}${role('CONFORMANCE DESCRIPTOR', row[8], row[9], row[10])}<dt>CACHE RECORD OFFSET</dt><dd><code>0x${row[0].toString(16)}</code></dd><dt>DYLIB OBJC INDEX</dt><dd>${row[1]}</dd><dt>NEXT IS DUPLICATE MARKER</dt><dd>${row[11] ? 'Yes' : 'No'}</dd></dl><p class="explain">This is a static dyld cache Swift metadata record. Names are raw symbols from the inspection tool; missing names remain unnamed. A conformance record does not prove runtime use.</p>`;
}

function renderSwiftResults() {
  const index = state.datasets.get(`swift:${state.build}`);
  if (!index || state.tab !== 'swift' || !$('#results')) return;
  const query = state.query.trim().toLocaleLowerCase();
  let items;
  if (state.swiftImage == null) {
    items = index.images.map((image, number) => ({...image, number, count:index.image_counts[number]}))
      .filter((image) => image.count && (!query || image.install_name.toLocaleLowerCase().includes(query)))
      .sort((a, b) => b.count - a.count || a.install_name.localeCompare(b.install_name));
  } else {
    const records = state.datasets.get(`swiftrows:${state.build}:${state.swiftImage}`) || [];
    items = records.filter((row) => !query || [row[3], row[6], row[9],
      `0x${row[2].toString(16)}`, `0x${row[5].toString(16)}`, `0x${row[8].toString(16)}`]
      .some((value) => value?.toLocaleLowerCase().includes(query)));
  }
  state.selected = items.includes(state.selected) ? state.selected : items.length === 1 ? items[0] : null;
  const visible = items.slice(0, state.limit);
  const rows = visible.map((item, number) => {
    const image = state.swiftImage == null;
    const main = image ? item.install_name : item[3] || `0x${item[2].toString(16)}`;
    const secondary = image ? `${fmt(item.count)} RECORDS` : item[6] || `0x${item[5].toString(16)}`;
    return `<button class="result-row ${state.selected === item ? 'selected' : ''}" data-index="${number}" title="${escapeHTML(main)}"><span class="row-main"><span class="row-icon">${image ? '◇' : '◌'}</span><span class="row-text">${escapeHTML(main)}</span></span><span class="row-sub">${escapeHTML(secondary)}</span></button>`;
  }).join('');
  $('#result-count').textContent = `${fmt(items.length)} result${items.length === 1 ? '' : 's'}`;
  $('#results').innerHTML = `<div class="result-head"><span>${state.swiftImage == null ? 'CACHE IMAGE' : 'TYPE SYMBOL / ADDRESS'}</span><span>${state.swiftImage == null ? 'CONFORMANCES' : 'PROTOCOL SYMBOL / ADDRESS'}</span></div>${rows || '<p class="empty-state">No matching entries in this source.</p>'}${items.length > state.limit ? '<button id="show-more" class="more-button">Show more ↓</button>' : ''}`;
  $('#detail').innerHTML = state.swiftImage == null
    ? state.selected ? `<span class="detail-label">CACHE IMAGE</span><h3>${escapeHTML(state.selected.install_name.split('/').pop())}</h3><dl><dt>INSTALL NAME</dt><dd>${escapeHTML(state.selected.install_name)}</dd><dt>IMAGE UUID</dt><dd>${escapeHTML(state.selected.uuid)}</dd><dt>SWIFT CONFORMANCES</dt><dd>${fmt(state.selected.count)}</dd></dl><button id="open-swift-image" class="more-button">Open conformances →</button>` : '<div class="empty-detail">Select an image to browse its Swift conformances.</div>'
    : swiftDetail(state.selected, index);
  $('#open-swift-image')?.addEventListener('click', () => openSwiftImage(state.selected.number, index).catch(showError));
  for (const row of document.querySelectorAll('.result-row')) row.addEventListener('click', () => {
    const chosen = visible[Number(row.dataset.index)];
    if (state.swiftImage == null) { openSwiftImage(chosen.number, index).catch(showError); return; }
    state.selected = chosen;
    $('#detail').innerHTML = swiftDetail(chosen, index);
    document.querySelectorAll('.result-row').forEach((other) => other.classList.toggle('selected', other === row));
  });
  $('#show-more')?.addEventListener('click', () => { state.limit += 80; renderSwiftResults(); });
}

async function openSwiftImage(imageIndex, index) {
  state.swiftImage = imageIndex;
  state.query = '';
  state.limit = 80;
  state.selected = null;
  $('#explorer').innerHTML = '<p class="loading">Opening this image’s conformance records…</p>';
  const rows = (await swiftBucket(index, imageIndex)).filter((row) => row[10] === imageIndex);
  if (state.tab !== 'swift' || state.swiftImage !== imageIndex) return;
  state.datasets.set(`swiftrows:${state.build}:${imageIndex}`, rows);
  await renderSwiftExplorer();
}

async function renderSwiftExplorer() {
  const explorer = $('#explorer');
  explorer.classList.add('swift-mode');
  if (!activeBuild().swift_url) { explorer.innerHTML = '<p class="empty-state">No Swift conformance catalog is available for this build.</p>'; return; }
  const index = await dataset('swift');
  if (state.tab !== 'swift') return;
  if (state.query.startsWith('image:')) {
    const name = state.query.slice(6);
    const imageIndex = index.images.findIndex((image) => image.install_name === name);
    if (imageIndex >= 0) { await openSwiftImage(imageIndex, index); return; }
  }
  const image = state.swiftImage == null ? null : index.images[state.swiftImage];
  const summary = `<div class="kernel-summary"><div><strong>${fmt(index.record_count)} CONFORMANCES</strong><span>Static type-to-protocol metadata in the intact iOS cache</span></div><div><strong>${fmt(index.image_count_with_conformances)} CACHE IMAGES</strong><span>Each type, protocol and descriptor address matched an exact Mach-O image</span></div></div>`;
  explorer.innerHTML = summary + (image ? `<div class="swift-context"><button id="swift-back" class="inline-link">← All images</button><strong>${escapeHTML(image.install_name)}</strong><span>${fmt(index.image_counts[state.swiftImage])} records</span></div>` : '') + toolbar({placeholder:image ? 'Search type, protocol, descriptor symbol or address…' : 'Search images with Swift conformances…'}) + '<div class="explorer-grid"><div id="results" class="result-list"></div><aside id="detail" class="detail"></aside></div>';
  $('#swift-back')?.addEventListener('click', () => { state.swiftImage = null; state.query = ''; state.selected = null; state.limit = 80; renderSwiftExplorer().catch(showError); });
  bindToolbar();
  $('#detail').addEventListener('click', (event) => {
    const link = event.target.closest('[data-linked-tab]');
    if (link) setTab(link.dataset.linkedTab, link.dataset.linkedQuery);
  });
  renderSwiftResults();
}

async function renderExplorer() {
  const mode = state.tab;
  const explorer = $('#explorer');
  explorer.onclick = null;
  explorer.classList.toggle('swift-mode', mode === 'swift');
  explorer.classList.toggle('reach-mode', mode === 'reach');
  updateSource();
  if (mode === 'research') {
    const entries = state.manifest.research.filter((note) => note.build === state.build);
    const selected = entries.find((note) => note.id === state.query);
    explorer.innerHTML = selected
      ? `<article class="research-detail"><div class="research-detail-top"><button id="research-back" class="inline-link">← All research</button><span>iPhone 11 · iOS 26.0.1 · ${escapeHTML(selected.build)}</span></div><div class="research-prose">${selected.rendered_html}</div><div class="research-detail-links">${selected.install_name ? `<button class="inline-link" data-linked-tab="images" data-linked-query="${escapeHTML(selected.install_name)}">Inspect cached image ↗</button>` : ''}<a href="https://github.com/everettjf/ios-atlas/blob/main/${encodeURI(selected.note)}" target="_blank" rel="noopener">View source Markdown ↗</a></div></article>`
      : `<div class="research-list">${entries.map((note) => `<article class="research-card"><span class="tag">BUILD ${escapeHTML(note.build)} / COMPONENT NOTE</span><h3>${escapeHTML(note.title)}</h3><p>${escapeHTML(note.summary)}</p><button class="inline-link" data-research-id="${escapeHTML(note.id)}">Read analysis →</button></article>`).join('') || '<p class="empty-state">No published research notes for this build yet.</p>'}</div>`;
    $('#research-back')?.addEventListener('click', () => setTab('research'));
    for (const button of explorer.querySelectorAll('[data-research-id]')) button.addEventListener('click', () => setTab('research', button.dataset.researchId));
    explorer.onclick = (event) => {
      const link = event.target.closest('[data-linked-tab]');
      if (link) setTab(link.dataset.linkedTab, link.dataset.linkedQuery);
    };
    return;
  }
  if (mode === 'swift') { await renderSwiftExplorer(); return; }
  if (mode === 'reach') { await renderReachExplorer(); return; }
  if (mode === 'methods') { await renderMethodsExplorer(); return; }
  if (mode === 'device' && !activeBuild().device_url) { explorer.innerHTML = '<p class="empty-state">No privacy-reviewed device system inventory is published for this build.</p>'; return; }
  if (mode === 'device_macho' && !activeBuild().device_macho_url) { explorer.innerHTML = '<p class="empty-state">No verified jailbreak Mach-O inventory is published for this build.</p>'; return; }
  if (mode === 'driverkit' && !activeBuild().driverkit_url) { explorer.innerHTML = '<p class="empty-state">No DriverKit cache is cataloged for this build.</p>'; return; }
  if (mode === 'macho' && !activeBuild().standalone_macho_url) { explorer.innerHTML = '<p class="empty-state">No standalone Mach-O inventory is cataloged for this build.</p>'; return; }
  if (mode === 'objc' && !activeBuild().objc_url) { explorer.innerHTML = '<p class="empty-state">No Objective-C class table is cataloged for this build.</p>'; return; }
  if (mode === 'protocols' && !activeBuild().objc_protocol_url) { explorer.innerHTML = '<p class="empty-state">No Objective-C protocol table is cataloged for this build.</p>'; return; }
  if (mode === 'archive' && !activeBuild().archive_url) { explorer.innerHTML = '<p class="empty-state">No restore archive is cataloged for this build.</p>'; return; }
  if (mode === 'restore' && !activeBuild().restore_url) { explorer.innerHTML = '<p class="empty-state">No restore RAM disks are cataloged for this build.</p>'; return; }
  if (mode === 'kernel' && !activeBuild().kernel_url) { explorer.innerHTML = '<p class="empty-state">No kernelcache metadata is cataloged for this build.</p>'; return; }
  if (mode === 'services' && !activeBuild().service_url) { explorer.innerHTML = '<p class="empty-state">No official launchd service catalog is available for this build.</p>'; return; }
  explorer.innerHTML = '<p class="loading">Opening source-bound catalog…</p>';
  const [data] = await Promise.all([
    dataset(filesystemMode(mode) ? mode : mode === 'device' ? 'device' : mode === 'device_macho' ? 'device_macho' : mode === 'objc' ? 'objc' : mode === 'protocols' ? 'protocols' : mode === 'driverkit' ? 'driverkit' : mode === 'macho' ? 'macho' : mode === 'archive' ? 'archive' : mode === 'kernel' ? 'kernel' : mode === 'services' ? 'services' : 'dyld'),
    ...(mode === 'images' && activeBuild().dyld_dependency_url ? [dataset('dependencies')] : []),
    ...(mode === 'images' && activeBuild().objc_method_index_url ? [dataset('methods_index')] : []),
    ...(mode === 'images' && activeBuild().ios_symbol_index_url ? [dataset('ios_symbol_index')] : []),
    ...(mode === 'objc' && activeBuild().objc_method_index_url ? [dataset('methods_index')] : []),
    ...(mode === 'files' || mode === 'device' ? [dataset('dyld')] : []),
    ...(mode === 'device' && activeBuild().device_macho_url ? [dataset('device_macho')] : []),
    ...(mode === 'device' && activeBuild().live_standalone_identity_url ? [dataset('macho_identity')] : []),
    ...(mode === 'device_macho' && activeBuild().device_macho_objc_url ? [dataset('device_macho_objc')] : []),
    ...(mode === 'device_macho' && activeBuild().device_macho_dependency_url ? [dataset('device_macho_dependencies')] : []),
    ...(mode === 'device_macho' && activeBuild().device_macho_symbol_index_url ? [dataset('device_macho_symbols')] : []),
    ...(mode === 'driverkit' && activeBuild().driverkit_dependency_url ? [dataset('driverkit_dependencies')] : []),
    ...(mode === 'driverkit' && activeBuild().driverkit_function_url ? [dataset('driverkit_functions')] : []),
    ...(mode === 'macho' && activeBuild().standalone_objc_index_url ? [dataset('macho_methods_index')] : []),
    ...(mode === 'macho' && activeBuild().live_standalone_identity_url ? [dataset('macho_identity')] : []),
    ...(mode === 'macho' && activeBuild().standalone_symbol_index_url ? [dataset('macho_symbol_index')] : []),
    ...(mode === 'macho' && activeBuild().standalone_swift_index_url ? [dataset('macho_swift_index')] : [])
  ]);
  if (state.tab !== mode) return;
  const deviceSummary = mode === 'device' ? data.kind === 'live_device_public_paths'
    ? `<div class="kernel-summary"><div><strong>${fmt(data.entry_count)} PUBLISHED PATHS</strong><span>Reviewed system and jailbreak paths only</span></div><div><strong>${fmt(data.complete_root_count)} / ${fmt(data.snapshot_root_count)} ROOTS COMPLETE</strong><span>Private snapshot coverage; user and app path names withheld</span></div><div><strong>${fmt(data.unpublished_entry_count)} WITHHELD OBSERVATIONS</strong><span>May overlap across mounts; no names or contents published</span></div></div>`
    : `<div class="kernel-summary"><div><strong>${fmt(data.entry_count)} OBSERVED PATHS</strong><span>Seven selected /rootfs system roots</span></div><div><strong>PARTIAL DEVICE COVERAGE</strong><span>Jailbreak, preboot and data-volume paths are not yet published</span></div></div>` : '';
  const kernelSummary = mode === 'kernel' ? `<div class="kernel-summary">${data.images.map((image) => `<div><strong>${escapeHTML(image.variant.toUpperCase())}</strong><span>UUID ${escapeHTML(image.macho_uuid)}</span><span>Darwin ${escapeHTML(image.darwin)} · XNU ${escapeHTML(image.xnu)} · ${fmt(image.fileset_entry_count)} fileset entries · ${fmt(image.kext_count)} kext records</span></div>`).join('')}</div>` : '';
  const serviceSummary = mode === 'services' ? `<div class="kernel-summary"><div><strong>${fmt(data.records.length)} PLISTS</strong><span>Launchd job and configuration declarations</span></div><div><strong>${fmt(activeBuild().mach_service_name_count)} MACH SERVICE NAMES</strong><span>Declared names; duplicates across plists are possible</span></div>${activeBuild().service_direct_import_count == null ? '' : `<div><strong>${fmt(activeBuild().service_direct_import_count)} DIRECT LOADS</strong><span>From ${fmt(activeBuild().service_executable_count)} service executables; ${fmt(activeBuild().service_cache_matched_import_count)} match cache images</span></div>`}</div>` : '';
  const objcSummary = mode === 'objc' ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().objc_class_count)} CLASS ENTRIES</strong><span>From the iOS cache Objective-C optimization table</span></div><div><strong>${fmt(activeBuild().objc_image_count)} CACHE IMAGES</strong><span>${fmt(activeBuild().objc_unresolved_count)} class entries without an exact image</span></div></div>` : '';
  const protocolSummary = mode === 'protocols' ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().objc_protocol_entry_count)} PROTOCOL ENTRIES</strong><span>From the iOS cache Objective-C optimization table</span></div><div><strong>${fmt(activeBuild().objc_protocol_ambiguous_label_count)} AMBIGUOUS ENTRIES</strong><span>${fmt(activeBuild().objc_protocol_unique_label_count)} entries have a unique image-label match</span></div></div>` : '';
  const prefix = mode === 'driverkit' ? 'driverkit' : 'dyld';
  const dependencySummary = (mode === 'images' || mode === 'driverkit') && activeBuild()[`${prefix}_dependency_url`] ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild()[`${prefix}_direct_import_count`])} DIRECT LIBRARY LOADS</strong><span>From ${fmt(activeBuild()[`${prefix}_dependency_image_count`])} cached images</span></div><div><strong>${fmt(activeBuild()[`${prefix}_exact_cache_match_count`])} EXACT CACHE MATCHES</strong><span>Static install-name matches within this cache family</span></div></div>` : '';
  const introCount = mode === 'images' ? activeBuild().ios_functional_intro_count : mode === 'driverkit' ? activeBuild().driverkit_functional_intro_count : null;
  const introSummary = introCount != null ? `<div class="kernel-summary"><div><strong>${fmt(introCount)} SOURCED INTRODUCTIONS</strong><span>Framework documentation describes an API family, not every behavior of this exact binary. <button class="inline-link" id="intro-filter">Browse introductions ↗</button></span></div></div>` : '';
  const driverkitSummary = mode === 'driverkit' && activeBuild().driverkit_named_function_count != null ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().driverkit_named_function_count)} NAMED FUNCTIONS</strong><span>Symbols in __text across all ${fmt(activeBuild().driverkit_image_count)} DriverKit cache images</span></div></div>` : '';
  const iosSymbolSummary = mode === 'images' && activeBuild().ios_symbol_index_url ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().ios_named_symbol_count)} NAMED __TEXT SYMBOLS</strong><span>From ${fmt(activeBuild().ios_symbol_image_count)} exact iOS cache images</span></div><div><strong>${fmt(activeBuild().ios_symbol_empty_image_count)} IMAGES WITHOUT NAMES</strong><span>Names complement Objective-C methods and do not enumerate every function</span></div></div>` : '';
  const machoSummary = mode === 'macho' ? `<div class="kernel-summary"><div><strong>${fmt(data.macho_file_count)} PHYSICAL MACH-O FILES</strong><span>Across FileSystem, SystemOS, and AppOS in the official IPSW</span></div><div><strong>${fmt(data.excluded_candidates.length)} MIXED CONTAINERS</strong><span>Metal libraries with non-Mach-O slices are listed in the coverage note</span></div></div>${activeBuild().standalone_objc_index_url ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().standalone_objc_method_count)} OBJECTIVE-C METHODS</strong><span>Static entries from inspected standalone files</span></div><div><strong>${fmt(activeBuild().standalone_objc_no_info_count)} FILES WITHOUT OBJC INFO</strong><span>A zero ObjC result is not a complete function inventory</span></div></div>` : ''}${activeBuild().standalone_symbol_index_url ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().standalone_named_symbol_count)} NAMED __TEXT SYMBOLS</strong><span>Records within code sections of standalone files</span></div><div><strong>${fmt(activeBuild().standalone_symbol_empty_file_count)} FILES WITHOUT NAMES</strong><span>Stripped symbol tables do not imply missing functions</span></div></div>` : ''}${activeBuild().standalone_swift_index_url ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().standalone_swift_declaration_count)} SWIFT DUMP DECLARATIONS</strong><span>Static type and extension lines across standalone files</span></div><div><strong>${fmt(activeBuild().standalone_swift_partial_count)} PARTIAL OUTPUTS</strong><span>Malformed lines are counted, not silently accepted</span></div></div>` : ''}` : '';
  const liveIdentitySummary = mode === 'macho' && activeBuild().live_standalone_identity_url ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().live_standalone_matched_count)} DEVICE BYTE MATCHES</strong><span>Read-only SHA-256 pass on this iPhone</span></div><div><strong>${fmt(activeBuild().live_standalone_unobserved_count)} UNOBSERVED STAGING PATHS</strong><span>No same mapped path in the device snapshot; other locations remain possible</span></div></div>` : '';
  const deviceMachoSummary = mode === 'device_macho' ? `<div class="kernel-summary"><div><strong>${fmt(data.macho_file_count)} VERIFIED DEVICE FILES</strong><span>From the jailbreak installation namespace</span></div><div><strong>${fmt(data.records.reduce((count, item) => count + item.slices.length, 0))} MACH-O SLICES</strong><span>Architectures, file types, and UUIDs from acquired bytes</span></div>${activeBuild().device_macho_objc_url ? `<div><strong>${fmt(activeBuild().device_macho_objc_method_count)} OBJECTIVE-C METHODS</strong><span>${fmt(activeBuild().device_macho_objc_parsed_count)} files parsed · ${fmt(activeBuild().device_macho_objc_no_info_count)} without ObjC information</span></div>` : ''}${activeBuild().device_macho_symbol_index_url ? `<div><strong>${fmt(activeBuild().device_macho_named_symbol_count)} NAMED __TEXT SYMBOLS</strong><span>Records across verified slices · ${fmt(activeBuild().device_macho_symbol_empty_file_count)} files without names</span></div>` : ''}</div>` : '';
  explorer.innerHTML = deviceSummary + deviceMachoSummary + kernelSummary + serviceSummary + objcSummary + protocolSummary + dependencySummary + introSummary + iosSymbolSummary + driverkitSummary + machoSummary + liveIdentitySummary + toolbar({placeholder:mode === 'files' ? 'Search all filesystem paths…' : mode === 'restore' ? 'Search all restore environment paths…' : mode === 'device' ? 'Search published live paths…' : mode === 'device_macho' ? 'Search live paths, file types, UUIDs, hashes…' : mode === 'objc' ? 'Search Objective-C class names or images…' : mode === 'protocols' ? 'Search Objective-C protocol names or images…' : mode === 'images' || mode === 'driverkit' ? 'Search library install names or use intro:…' : mode === 'macho' ? 'Search paths, file types, architectures, UUIDs, hashes…' : mode === 'archive' ? 'Search IPSW archive members…' : mode === 'kernel' ? 'Search kext identifiers…' : mode === 'services' ? 'Search labels, programs, Mach services, events…' : 'Search cache file names…', volumes:filesystemMode(mode) ? data.volumes.map((volume) => volume.name) : mode === 'macho' ? Object.keys(data.volume_images) : mode === 'kernel' ? data.images.map((image) => image.variant) : mode === 'services' ? ['direct','cryptex','unresolved','undeclared'] : [], filterLabel:mode === 'kernel' ? 'All variants' : mode === 'services' ? 'All resolutions' : 'All volumes'}) + '<div class="explorer-grid"><div id="results" class="result-list"></div><aside id="detail" class="detail"></aside></div>';
  bindToolbar();
  $('#intro-filter')?.addEventListener('click', () => { state.query = 'intro:'; state.limit = 80; $('#catalog-search').value = state.query; renderResults(); });
  $('#detail').addEventListener('click', (event) => {
    const link = event.target.closest('[data-linked-tab]');
    if (link) setTab(link.dataset.linkedTab, link.dataset.linkedQuery);
    if (event.target.id === 'driverkit-function-more' && state.selected) {
      state.driverkitFunctionLimit += 80;
      $('#driverkit-function-results').innerHTML = driverkitFunctionResults(state.selected);
    }
    if (event.target.id === 'ios-symbol-open' && state.selected) openIosSymbols().catch(showError);
    if (event.target.id === 'ios-symbol-more' && state.selected && state.iosSymbolData) {
      state.iosSymbolLimit += 80;
      $('#ios-symbol-results').innerHTML = iosSymbolResults(state.iosSymbolData);
    }
    if (event.target.id === 'macho-method-open' && state.selected) openMachoMethods().catch(showError);
    if (event.target.id === 'macho-method-more' && state.selected && state.machoMethodData) {
      state.machoMethodLimit += 80;
      $('#macho-method-results').innerHTML = machoMethodResults(state.selected, state.machoMethodData);
    }
    if (event.target.id === 'live-method-more' && state.selected) {
      const objc = state.datasets.get(`device_macho_objc:${state.build}`)?.byPath.get(state.selected.path);
      if (objc) {
        state.liveMethodLimit += 80;
        $('#live-method-results').innerHTML = liveMethodList(objc);
      }
    }
    if (event.target.id === 'live-symbol-open' && state.selected) openLiveSymbols().catch(showError);
    if (event.target.id === 'live-symbol-more' && state.selected && state.liveSymbolData) {
      state.liveSymbolLimit += 80;
      $('#live-symbol-results').innerHTML = liveSymbolResults(state.liveSymbolData);
    }
    if (event.target.id === 'macho-symbol-open' && state.selected) openMachoSymbols().catch(showError);
    if (event.target.id === 'macho-symbol-more' && state.selected && state.machoSymbolData) {
      state.machoSymbolLimit += 80;
      $('#macho-symbol-results').innerHTML = machoSymbolResults(state.machoSymbolData);
    }
    if (event.target.id === 'macho-swift-open' && state.selected) openMachoSwift().catch(showError);
    if (event.target.id === 'macho-swift-type-more' && state.selected && state.machoSwiftData) {
      state.machoSwiftTypeLimit += 40;
      $('#macho-swift-results').innerHTML = machoSwiftResults(state.machoSwiftData);
    }
    if (event.target.id === 'macho-swift-member-more' && state.selected && state.machoSwiftData) {
      state.machoSwiftMemberLimit += 80;
      $('#macho-swift-results').innerHTML = machoSwiftResults(state.machoSwiftData);
    }
  });
  $('#detail').addEventListener('input', (event) => {
    if (event.target.id === 'driverkit-function-search' && state.selected) {
      state.driverkitFunctionQuery = event.target.value;
      state.driverkitFunctionLimit = 80;
      $('#driverkit-function-results').innerHTML = driverkitFunctionResults(state.selected);
    }
    if (event.target.id === 'ios-symbol-search' && state.selected && state.iosSymbolData) {
      state.iosSymbolQuery = event.target.value;
      state.iosSymbolLimit = 80;
      $('#ios-symbol-results').innerHTML = iosSymbolResults(state.iosSymbolData);
    }
    if (event.target.id === 'macho-method-search' && state.selected && state.machoMethodData) {
      state.machoMethodQuery = event.target.value;
      state.machoMethodLimit = 80;
      $('#macho-method-results').innerHTML = machoMethodResults(state.selected, state.machoMethodData);
    }
    if (event.target.id === 'live-method-search' && state.selected) {
      const objc = state.datasets.get(`device_macho_objc:${state.build}`)?.byPath.get(state.selected.path);
      if (objc) {
        state.liveMethodQuery = event.target.value;
        state.liveMethodLimit = 80;
        $('#live-method-results').innerHTML = liveMethodList(objc);
      }
    }
    if (event.target.id === 'live-symbol-search' && state.selected && state.liveSymbolData) {
      state.liveSymbolQuery = event.target.value;
      state.liveSymbolLimit = 80;
      $('#live-symbol-results').innerHTML = liveSymbolResults(state.liveSymbolData);
    }
    if (event.target.id === 'macho-symbol-search' && state.selected && state.machoSymbolData) {
      state.machoSymbolQuery = event.target.value;
      state.machoSymbolLimit = 80;
      $('#macho-symbol-results').innerHTML = machoSymbolResults(state.machoSymbolData);
    }
    if (event.target.id === 'macho-swift-search' && state.selected && state.machoSwiftData) {
      state.machoSwiftQuery = event.target.value;
      state.machoSwiftTypeLimit = 40;
      state.machoSwiftMemberLimit = 80;
      $('#macho-swift-results').innerHTML = machoSwiftResults(state.machoSwiftData);
    }
  });
  renderResults();
}

async function render() { await renderExplorer(); }
function showError(error) { $('#explorer').innerHTML = `<p class="empty-state">Unable to open this catalog: ${escapeHTML(error.message)}</p>`; }

async function start() {
  state.manifest = await json('data/manifest.json');
  const first = state.manifest.builds[0];
  state.build = first.build;
  $('#metric-files').textContent = first.device_count == null ? '—' : fmt(first.device_count);
  $('#metric-files-note').textContent = first.device_scope === 'reviewed_live' ? 'Privacy-reviewed live snapshot' : 'Seven selected /rootfs roots';
  $('#metric-images').textContent = fmt(first.image_count);
  $('#metric-caches').textContent = fmt(first.cache_file_count);
  $('#metric-build').textContent = first.build;
  $('#build-select').innerHTML = state.manifest.builds.map((item) => `<option value="${escapeHTML(item.build)}">${escapeHTML(item.version)} · ${escapeHTML(item.build)}</option>`).join('');
  $('#build-select').addEventListener('change', () => { state.build = $('#build-select').value; state.selected = null; state.browsePath = '/'; state.swiftImage = null; state.methodImage = null; state.reachSource = null; state.reachPaths = null; state.limit = 80; const build = activeBuild(); $('#metric-files').textContent = build.device_count == null ? '—' : fmt(build.device_count); $('#metric-files-note').textContent = build.device_scope === 'reviewed_live' ? 'Privacy-reviewed live snapshot' : 'Seven selected /rootfs roots'; $('#metric-images').textContent = fmt(build.image_count); $('#metric-caches').textContent = fmt(build.cache_file_count); $('#metric-build').textContent = build.build; render().catch(showError); });
  for (const button of document.querySelectorAll('[data-tab]')) button.addEventListener('click', () => setTab(button.dataset.tab));
  const [initial, noteId] = location.hash.slice(1).split('/', 2);
  if (['files','restore','device','device_macho','images','objc','methods','protocols','swift','reach','driverkit','macho','caches','archive','kernel','services','research'].includes(initial)) state.tab = initial;
  if (initial === 'research' && noteId) state.query = decodeURIComponent(noteId);
  if (initial === 'methods' && noteId) state.query = decodeURIComponent(noteId);
  if (initial === 'reach' && noteId) state.reachSource = decodeURIComponent(noteId);
  if (['files','restore','device'].includes(initial) && noteId) state.browsePath = decodeURIComponent(noteId);
  for (const button of document.querySelectorAll('[role="tab"]')) button.setAttribute('aria-selected', button.dataset.tab === state.tab);
  await render();
}

start().catch(showError);
