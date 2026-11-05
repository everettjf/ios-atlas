const $ = (selector) => document.querySelector(selector);
const assetVersion = new URL(import.meta.url).searchParams.get('v') || 'dev';
const versioned = (url) => `${url}?v=${assetVersion}`;
const {computeReach, pathTo} = await import(versioned('./reach.mjs'));
const {directoryChildren, parentDirectory} = await import(versioned('./tree.mjs'));
const fmt = (value) => new Intl.NumberFormat('en-US').format(value);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const size = (value) => value == null ? '—' : value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1048576).toFixed(1)} MB`;
const filesystemMode = (mode) => mode === 'files' || mode === 'restore';
const state = { manifest:null, build:null, tab:'images', query:'', volume:'all', limit:80, selected:null, browsePath:'/', swiftImage:null, reachSource:null, reachWeak:false, reachPaths:null, datasets:new Map(), compareOld:null, compareNew:null };
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
  const result = kind === 'files' ? await compressedJSON(info.files_url) : kind === 'restore' ? await compressedJSON(info.restore_url) : kind === 'device' ? await compressedJSON(info.device_url) : kind === 'observation' ? await compressedJSON(info.stock_device_url) : kind === 'objc' ? await compressedJSON(info.objc_url) : kind === 'protocols' ? await compressedJSON(info.objc_protocol_url) : kind === 'dependencies' ? await compressedJSON(info.dyld_dependency_url) : kind === 'driverkit_dependencies' ? await compressedJSON(info.driverkit_dependency_url) : await json(kind === 'swift' ? info.swift_url : kind === 'driverkit' ? info.driverkit_url : kind === 'archive' ? info.archive_url : kind === 'kernel' ? info.kernel_url : kind === 'services' ? info.service_url : info.dyld_url);
  if (kind === 'services') result.binaryByKey = new Map(result.binaries.map((item) => [`${item.volume}:${item.path}`, item]));
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
  for (const button of document.querySelectorAll('[role="tab"]')) button.setAttribute('aria-selected', button.dataset.tab === tab);
  history.replaceState(null, '', tab === 'research' && query ? `#research/${encodeURIComponent(query)}` : state.reachSource ? `#reach/${encodeURIComponent(state.reachSource)}` : `#${tab}`);
  render().catch(showError);
  document.querySelector('.workspace').scrollIntoView({behavior:'smooth', block:'start'});
}

function updateSource() {
  const files = state.tab === 'files';
  const device = state.tab === 'device';
  const driverkit = state.tab === 'driverkit';
  const archive = state.tab === 'archive';
  const restore = state.tab === 'restore';
  const kernel = state.tab === 'kernel';
  const services = state.tab === 'services';
  const objc = state.tab === 'objc';
  const protocols = state.tab === 'protocols';
  const swift = state.tab === 'swift';
  const research = state.tab === 'research';
  const observation = state.tab === 'observation';
  const reach = state.tab === 'reach';
  $('#source-title').textContent = observation ? 'Sources: official IPSW and filtered live /rootfs' : device ? 'Source: live iPhone 11 system view' : driverkit ? 'Source: official DriverKit cache' : objc || protocols ? 'Source: official iOS dyld cache Objective-C table' : swift ? 'Source: official iOS dyld cache Swift metadata' : reach ? 'Source: official iOS cache Mach-O load commands' : research ? 'Source: build-specific research notes' : archive ? 'Source: complete restore IPSW archive' : restore ? 'Source: official restore RAM disks' : kernel ? 'Source: official kernelcache Mach-O filesets' : services ? 'Source: official FileSystem launchd plists' : 'Source: official iPhone 11 firmware';
  $('#source-description').textContent = device
    ? 'Read-only /rootfs observation of selected Apple system roots. User data and jailbreak namespace are excluded; differences do not establish jailbreak causation.'
    : observation ? 'Exact path/type pairs within seven scanned roots only. IPSW image paths and the live RootHide namespace can differ; this is not a jailbreak before/after comparison.'
    : driverkit ? 'A separate DriverKit platform cache: 51 images in 3 physical files. All 3 files matched the connected device by SHA-256.'
    : objc ? 'Class entries come from the intact iOS cache optimization table. Image labels are resolved to exact install names with Mach-O segment addresses where needed.'
    : protocols ? 'Protocol entries come from the intact iOS cache optimization table. Repeated image basenames are kept as ambiguous associations.'
    : swift ? 'Static type-to-protocol conformance records from the intact cache. Addresses resolve to exact Mach-O images; names are raw symbols when available.'
    : reach ? 'Shortest paths follow exact in-cache install-name matches from static Mach-O load commands. No path proves runtime loading.'
    : research ? 'Author-written analyses connect exact firmware artifacts and explain the boundary between observed bytes, interpretation and unknowns.'
    : archive ? 'All 127 ZIP entries are indexed by path and role. Artifact presence is distinct from mounted filesystem content.'
    : kernel ? 'Release and research kernelcaches have distinct UUIDs. Kext metadata and fileset entry counts are separate measurements.'
    : services ? 'Launchd job declarations, executable paths, Mach service names, and events from the stock firmware. A declaration is not proof that a job ran.'
    : files ? 'Browse observed paths within each IPSW filesystem image. Logical dyld images appear separately in the same directory and never count as physical files.'
    : restore ? 'Browse paths in the Erase and Upgrade restore RAM disks. These are recovery environments, separate from installed iOS.'
    : 'All 80 cache files matched the connected device by SHA-256. An in-cache image is not counted as an on-disk executable.';
}

function toolbar({placeholder, volumes = [], filterLabel = 'All volumes'}) {
  const filterName = filterLabel === 'All variants' ? 'Filter variant' : filterLabel === 'All resolutions' ? 'Filter executable resolution' : 'Filter volume';
  return `<div class="toolbar"><label class="searchbox"><span class="sr-only">Search paths</span><input id="catalog-search" type="search" autocomplete="off" placeholder="${escapeHTML(placeholder)}" value="${escapeHTML(state.query)}"></label>${volumes.length ? `<select id="volume-filter" aria-label="${filterName}"><option value="all">${filterLabel}</option>${volumes.map((name) => `<option value="${escapeHTML(name)}" ${state.volume === name ? 'selected' : ''}>${escapeHTML(name)}</option>`).join('')}</select>` : ''}<span class="result-count" id="result-count"></span></div>`;
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
  const cache = mode === 'files' && state.volume === 'all' ? state.datasets.get(`dyld:${state.build}`) : null;
  const images = cache ? cache.images.filter((item) => parentDirectory(item.install_name) === state.browsePath) : [];
  const cacheRows = images.length ? `<div class="folder-cache"><div class="folder-cache-heading"><strong>${fmt(images.length)} logical image${images.length === 1 ? '' : 's'} in dyld cache</strong><span>These are cache images, not filesystem entries.</span></div>${images.slice(0, 20).map((image) => `<button class="folder-cache-row" data-linked-tab="images" data-linked-query="${escapeHTML(image.install_name)}"><span>◇ ${escapeHTML(image.install_name.split('/').pop())}</span><small>IN CACHE ↗</small></button>`).join('')}${images.length > 20 ? `<button class="more-button" data-linked-tab="images" data-linked-query="${escapeHTML(state.browsePath + '/')}">Explore all matching images ↗</button>` : ''}</div>` : '';
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

function detailHTML(item, mode, data) {
  if (!item) return `<div class="empty-detail">Select a row to inspect its source and metadata.</div>`;
  if (mode === 'objc') {
    const [name, address, label, installName, resolution] = item;
    const imageLink = installName ? `<button class="inline-link" data-linked-tab="images" data-linked-query="${escapeHTML(installName)}">${escapeHTML(installName)} ↗</button>` : 'Unresolved';
    return `<span class="detail-label">OBJECTIVE-C CLASS ENTRY</span><h3>${escapeHTML(name)}</h3><dl><dt>CLASS METADATA ADDRESS</dt><dd>${escapeHTML(address)}</dd><dt>CACHE IMAGE LABEL</dt><dd>${escapeHTML(label)}</dd><dt>DEFINING CACHE IMAGE</dt><dd>${imageLink}</dd><dt>IMAGE RESOLUTION</dt><dd>${resolution === 'segment_address' ? 'Class address within a Mach-O segment of one matching image' : resolution === 'unique_label' ? 'Unique image basename in this cache' : 'No unique image established'}</dd></dl><p class="explain">This is an entry in the dyld cache Objective-C optimization table. Names and addresses describe static metadata in the official firmware, not live objects or method calls. Multiple entries may share a class name.</p>`;
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
    const graphHTML = graph ? `<div class="direct-imports"><h4>Direct library loads (${fmt(imports.length)})</h4><ul>${loadRows || '<li>None recorded</li>'}</ul></div><div class="direct-imports"><h4>Loaded by cached images (${fmt(importers.length)})</h4><ul>${importerRows || '<li>None recorded</li>'}</ul>${importers.length > 30 ? `<button class="more-button" data-linked-tab="${mode}" data-linked-query="imports:${escapeHTML(item.install_name)}">View all ${fmt(importers.length)} importers ↗</button>` : ''}</div>` : '';
    return `<span class="detail-label">${mode === 'driverkit' ? 'DRIVERKIT CACHE IMAGE' : 'IN-CACHE IMAGE'}</span><h3>${escapeHTML(item.install_name.split('/').pop())}</h3><dl><dt>LOGICAL INSTALL NAME</dt><dd>${escapeHTML(item.install_name)}</dd><dt>IMAGE UUID</dt><dd>${escapeHTML(item.uuid)}</dd><dt>SOURCE VERSION</dt><dd>${escapeHTML(item.version || 'Not recorded')}</dd><dt>CACHE UUID</dt><dd>${escapeHTML(data.cache_uuid)}</dd><dt>STANDALONE FILE IN SCANNED IMAGES</dt><dd>${present ? escapeHTML(item.physical_volumes.join(', ')) : 'None observed'}</dd>${consumers == null ? '' : `<dt>DIRECT IMPORTS BY INDEXED SERVICE EXECUTABLES</dt><dd>${fmt(consumers)}${consumers ? ` <button class="inline-link" data-linked-tab="services" data-linked-query="${escapeHTML(item.install_name)}">View services ↗</button>` : ''}</dd>`}${item.objc_class_count == null ? '' : `<dt>OBJECTIVE-C CLASS ENTRIES</dt><dd>${fmt(item.objc_class_count)}${item.objc_class_count ? ` <button class="inline-link" data-linked-tab="objc" data-linked-query="image:${escapeHTML(item.install_name)}">View classes ↗</button>` : ''}</dd>`}${item.objc_protocol_entry_count == null ? '' : `<dt>PROTOCOL TABLE ENTRIES WITH UNIQUE IMAGE LABEL</dt><dd>${fmt(item.objc_protocol_entry_count)}${item.objc_protocol_entry_count ? ` <button class="inline-link" data-linked-tab="protocols" data-linked-query="image:${escapeHTML(item.install_name)}">View entries ↗</button>` : ''}</dd>`}${item.swift_conformance_count == null ? '' : `<dt>SWIFT TYPE CONFORMANCES</dt><dd>${fmt(item.swift_conformance_count)}${item.swift_conformance_count ? ` <button class="inline-link" data-linked-tab="swift" data-linked-query="image:${escapeHTML(item.install_name)}">View conformances ↗</button>` : ''}</dd>`}${mode !== 'images' || !graph ? '' : `<dt>TRANSITIVE LOAD PATHS</dt><dd><button class="inline-link" data-linked-tab="reach" data-linked-query="source:${escapeHTML(item.install_name)}">Trace dependency reach ↗</button></dd>`}</dl>${graphHTML}<p class="explain">${present ? 'A separate physical file was also found at this logical path. The cache image and file remain distinct records.' : 'No regular file exists at this path in the three processed IPSW images. Its executable image is listed in the dyld shared cache.'} Library edges are direct static Mach-O load commands, not runtime calls; weak loads may never resolve.</p>`;
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
    const path = mode === 'images' || mode === 'driverkit' ? item.install_name : mode === 'objc' || mode === 'protocols' ? item[0] : filesystemMode(mode) ? item[1] : mode === 'device' ? item[0] : mode === 'archive' ? item.path : mode === 'kernel' ? item.id : mode === 'services' ? item.label || item.plist_path : item.name;
    const secondary = mode === 'images' || mode === 'driverkit' ? (item.physical_volumes.length ? 'DISK + CACHE' : 'IN CACHE') : mode === 'objc' || mode === 'protocols' ? item[2] : mode === 'restore' ? data.volumes[item[0]].name.replace(/^RestoreRamDisk/, '') : mode === 'files' ? data.volumes[item[0]].name : mode === 'device' ? item[1].toUpperCase() : mode === 'archive' ? item.kind.toUpperCase() : mode === 'kernel' ? item.variant.toUpperCase() : mode === 'services' ? item.executable.status.toUpperCase() : size(item.size);
    const icon = mode === 'images' || mode === 'driverkit' ? '◇' : mode === 'objc' || mode === 'protocols' ? '◌' : filesystemMode(mode) ? item[2] === 'directory' ? '▤' : item[2] === 'symlink' ? '↗' : '·' : mode === 'device' ? item[1] === 'directory' ? '▤' : item[1] === 'symlink' ? '↗' : '·' : mode === 'archive' ? '▧' : mode === 'kernel' ? '✳' : mode === 'services' ? '◉' : '◈';
    return `<button class="result-row ${state.selected === item ? 'selected' : ''}" data-index="${index}" title="${escapeHTML(path)}"><span class="row-main"><span class="row-icon">${icon}</span><span class="row-text">${escapeHTML(path)}</span></span><span class="row-sub">${escapeHTML(secondary)}</span></button>`;
  }).join('');
  $('#result-count').textContent = `${fmt(items.length)} result${items.length === 1 ? '' : 's'}`;
  const heading = mode === 'kernel' ? 'BUNDLE IDENTIFIER' : mode === 'archive' ? 'ARCHIVE MEMBER' : mode === 'services' ? 'SERVICE LABEL' : mode === 'objc' ? 'CLASS NAME' : mode === 'protocols' ? 'PROTOCOL NAME' : 'PATH / INSTALL NAME';
  const sourceHeading = mode === 'kernel' ? 'VARIANT' : mode === 'archive' ? 'KIND' : mode === 'services' ? 'EXECUTABLE' : mode === 'objc' || mode === 'protocols' ? 'IMAGE LABEL' : 'SOURCE';
  $('#results').innerHTML = `<div class="result-head"><span>${heading}</span><span>${sourceHeading}</span></div>${rows || '<p class="empty-state">No matching entries in the selected source.</p>'}${items.length > state.limit ? '<button id="show-more" class="more-button">Show more ↓</button>' : ''}`;
  $('#detail').innerHTML = detailHTML(state.selected, mode, data);
  for (const row of document.querySelectorAll('.result-row')) row.addEventListener('click', () => { state.selected = visible[Number(row.dataset.index)]; $('#detail').innerHTML = detailHTML(state.selected, mode, data); document.querySelectorAll('.result-row').forEach((other) => other.classList.toggle('selected', other === row)); });
  $('#show-more')?.addEventListener('click', () => { state.limit += 80; renderRows(items, mode, data); });
}

function renderResults() {
  const mode = state.tab;
  if (mode === 'swift') { renderSwiftResults(); return; }
  if (mode === 'reach') { renderReachResults(); return; }
  const data = state.datasets.get(`${filesystemMode(mode) ? mode : mode === 'device' ? 'device' : mode === 'objc' ? 'objc' : mode === 'protocols' ? 'protocols' : mode === 'driverkit' ? 'driverkit' : mode === 'archive' ? 'archive' : mode === 'kernel' ? 'kernel' : mode === 'services' ? 'services' : 'dyld'}:${state.build}`);
  if (!data || !['images','driverkit','objc','protocols','files','restore','device','caches','archive','kernel','services'].includes(mode)) return;
  if ((filesystemMode(mode) || mode === 'device') && !state.query.trim()) { renderDirectoryResults(mode, data); return; }
  const query = state.query.trim().toLocaleLowerCase();
  let items;
  if (filesystemMode(mode)) items = data.entries.filter((item) => (state.volume === 'all' || data.volumes[item[0]].name === state.volume) && (!query || item[1].toLocaleLowerCase().includes(query)));
  else if (mode === 'device') items = data.entries.filter((item) => !query || item[0].toLocaleLowerCase().includes(query));
  else if (mode === 'objc' && query.startsWith('image:')) items = data.records.filter((item) => item[3] === state.query.trim().slice(6));
  else if (mode === 'objc') items = data.records.filter((item) => !query || `${item[0]} ${item[1]} ${item[2]} ${item[3] || ''}`.toLocaleLowerCase().includes(query));
  else if (mode === 'protocols' && query.startsWith('image:')) items = data.records.filter((item) => item[3] === state.query.trim().slice(6));
  else if (mode === 'protocols') items = data.records.filter((item) => !query || `${item[0]} ${item[1]} ${item[2]} ${item[3] || ''}`.toLocaleLowerCase().includes(query));
  else if ((mode === 'images' || mode === 'driverkit') && query.startsWith('imports:')) {
    const graph = state.datasets.get(`${mode === 'driverkit' ? 'driverkit_dependencies' : 'dependencies'}:${state.build}`);
    const sources = new Set((graph?.importers.get(state.query.trim().slice(8)) || []).map((entry) => entry.source));
    items = data.images.filter((item) => sources.has(item.install_name));
  }
  else if (mode === 'images' || mode === 'driverkit') items = data.images.filter((item) => !query || item.install_name.toLocaleLowerCase().includes(query));
  else if (mode === 'archive') items = data.entries.filter((item) => !query || item.path.toLocaleLowerCase().includes(query));
  else if (mode === 'kernel') items = data.kexts.filter((item) => (state.volume === 'all' || item.variant === state.volume) && (!query || `${item.id} ${item.name} ${item.bundle_path}`.toLocaleLowerCase().includes(query)));
  else if (mode === 'services') items = data.records.filter((item) => (state.volume === 'all' || item.executable.status === state.volume) && (!query || `${item.label} ${item.plist_path} ${item.program} ${item.mach_services.join(' ')} ${item.launch_events.join(' ')} ${serviceBinary(item, data)?.imports.map((imp) => imp.install_name).join(' ') || ''}`.toLocaleLowerCase().includes(query)));
  else items = data.files.filter((item) => !query || item.name.toLocaleLowerCase().includes(query));
  state.selected = items.includes(state.selected) ? state.selected : items.length === 1 ? items[0] : null;
  renderRows(items, mode, data);
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
  if (mode === 'compare') { await renderCompare(); return; }
  if (mode === 'observation') { await renderObservation(); return; }
  if (mode === 'swift') { await renderSwiftExplorer(); return; }
  if (mode === 'reach') { await renderReachExplorer(); return; }
  if (mode === 'device' && !activeBuild().device_url) { explorer.innerHTML = '<p class="empty-state">No privacy-reviewed device system inventory is published for this build.</p>'; return; }
  if (mode === 'driverkit' && !activeBuild().driverkit_url) { explorer.innerHTML = '<p class="empty-state">No DriverKit cache is cataloged for this build.</p>'; return; }
  if (mode === 'objc' && !activeBuild().objc_url) { explorer.innerHTML = '<p class="empty-state">No Objective-C class table is cataloged for this build.</p>'; return; }
  if (mode === 'protocols' && !activeBuild().objc_protocol_url) { explorer.innerHTML = '<p class="empty-state">No Objective-C protocol table is cataloged for this build.</p>'; return; }
  if (mode === 'archive' && !activeBuild().archive_url) { explorer.innerHTML = '<p class="empty-state">No restore archive is cataloged for this build.</p>'; return; }
  if (mode === 'restore' && !activeBuild().restore_url) { explorer.innerHTML = '<p class="empty-state">No restore RAM disks are cataloged for this build.</p>'; return; }
  if (mode === 'kernel' && !activeBuild().kernel_url) { explorer.innerHTML = '<p class="empty-state">No kernelcache metadata is cataloged for this build.</p>'; return; }
  if (mode === 'services' && !activeBuild().service_url) { explorer.innerHTML = '<p class="empty-state">No official launchd service catalog is available for this build.</p>'; return; }
  explorer.innerHTML = '<p class="loading">Opening source-bound catalog…</p>';
  const [data] = await Promise.all([
    dataset(filesystemMode(mode) ? mode : mode === 'device' ? 'device' : mode === 'objc' ? 'objc' : mode === 'protocols' ? 'protocols' : mode === 'driverkit' ? 'driverkit' : mode === 'archive' ? 'archive' : mode === 'kernel' ? 'kernel' : mode === 'services' ? 'services' : 'dyld'),
    ...(mode === 'images' && activeBuild().dyld_dependency_url ? [dataset('dependencies')] : []),
    ...(mode === 'files' ? [dataset('dyld')] : []),
    ...(mode === 'driverkit' && activeBuild().driverkit_dependency_url ? [dataset('driverkit_dependencies')] : [])
  ]);
  if (state.tab !== mode) return;
  const kernelSummary = mode === 'kernel' ? `<div class="kernel-summary">${data.images.map((image) => `<div><strong>${escapeHTML(image.variant.toUpperCase())}</strong><span>UUID ${escapeHTML(image.macho_uuid)}</span><span>Darwin ${escapeHTML(image.darwin)} · XNU ${escapeHTML(image.xnu)} · ${fmt(image.fileset_entry_count)} fileset entries · ${fmt(image.kext_count)} kext records</span></div>`).join('')}</div>` : '';
  const serviceSummary = mode === 'services' ? `<div class="kernel-summary"><div><strong>${fmt(data.records.length)} PLISTS</strong><span>Launchd job and configuration declarations</span></div><div><strong>${fmt(activeBuild().mach_service_name_count)} MACH SERVICE NAMES</strong><span>Declared names; duplicates across plists are possible</span></div>${activeBuild().service_direct_import_count == null ? '' : `<div><strong>${fmt(activeBuild().service_direct_import_count)} DIRECT LOADS</strong><span>From ${fmt(activeBuild().service_executable_count)} service executables; ${fmt(activeBuild().service_cache_matched_import_count)} match cache images</span></div>`}</div>` : '';
  const objcSummary = mode === 'objc' ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().objc_class_count)} CLASS ENTRIES</strong><span>From the iOS cache Objective-C optimization table</span></div><div><strong>${fmt(activeBuild().objc_image_count)} CACHE IMAGES</strong><span>${fmt(activeBuild().objc_unresolved_count)} class entries without an exact image</span></div></div>` : '';
  const protocolSummary = mode === 'protocols' ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild().objc_protocol_entry_count)} PROTOCOL ENTRIES</strong><span>From the iOS cache Objective-C optimization table</span></div><div><strong>${fmt(activeBuild().objc_protocol_ambiguous_label_count)} AMBIGUOUS ENTRIES</strong><span>${fmt(activeBuild().objc_protocol_unique_label_count)} entries have a unique image-label match</span></div></div>` : '';
  const prefix = mode === 'driverkit' ? 'driverkit' : 'dyld';
  const dependencySummary = (mode === 'images' || mode === 'driverkit') && activeBuild()[`${prefix}_dependency_url`] ? `<div class="kernel-summary"><div><strong>${fmt(activeBuild()[`${prefix}_direct_import_count`])} DIRECT LIBRARY LOADS</strong><span>From ${fmt(activeBuild()[`${prefix}_dependency_image_count`])} cached images</span></div><div><strong>${fmt(activeBuild()[`${prefix}_exact_cache_match_count`])} EXACT CACHE MATCHES</strong><span>Static install-name matches within this cache family</span></div></div>` : '';
  explorer.innerHTML = kernelSummary + serviceSummary + objcSummary + protocolSummary + dependencySummary + toolbar({placeholder:mode === 'files' ? 'Search all filesystem paths…' : mode === 'restore' ? 'Search all restore environment paths…' : mode === 'device' ? 'Search all live system paths…' : mode === 'objc' ? 'Search Objective-C class names or images…' : mode === 'protocols' ? 'Search Objective-C protocol names or images…' : mode === 'images' || mode === 'driverkit' ? 'Search library install names…' : mode === 'archive' ? 'Search IPSW archive members…' : mode === 'kernel' ? 'Search kext identifiers…' : mode === 'services' ? 'Search labels, programs, Mach services, events…' : 'Search cache file names…', volumes:filesystemMode(mode) ? data.volumes.map((volume) => volume.name) : mode === 'kernel' ? data.images.map((image) => image.variant) : mode === 'services' ? ['direct','cryptex','unresolved','undeclared'] : [], filterLabel:mode === 'kernel' ? 'All variants' : mode === 'services' ? 'All resolutions' : 'All volumes'}) + '<div class="explorer-grid"><div id="results" class="result-list"></div><aside id="detail" class="detail"></aside></div>';
  bindToolbar();
  $('#detail').addEventListener('click', (event) => {
    const link = event.target.closest('[data-linked-tab]');
    if (link) setTab(link.dataset.linkedTab, link.dataset.linkedQuery);
  });
  renderResults();
}

async function renderObservation() {
  const explorer = $('#explorer');
  if (!activeBuild().stock_device_url) {
    explorer.innerHTML = '<p class="empty-state">No reviewed device comparison is available for this build.</p>';
    return;
  }
  explorer.innerHTML = '<p class="loading">Comparing source-bound path indexes…</p>';
  const data = await dataset('observation');
  if (state.tab !== 'observation') return;
  const cards = [
    [data.unique_stock_pair_count, 'UNIQUE STOCK PATH / TYPE PAIRS'],
    [data.observed_pair_count, 'FILTERED DEVICE PAIRS'],
    [data.stock_only_pair_count, 'STOCK PAIRS NOT SEEN AT SAME PATH'],
    [data.device_only_pair_count, 'PUBLISHED DEVICE-ONLY PAIRS'],
  ];
  const fileSystem = data.volumes.find((row) => row.name === 'FileSystem');
  const fileSystemSentence = fileSystem?.same_path_type_count === data.observed_pair_count
    ? 'Every published device pair matches the official FileSystem image. '
    : '';
  const matrix = (heading, rows, label) => `<section class="observation-matrix"><h3>${heading}</h3><div class="observation-table"><div class="observation-table-head"><span>${label}</span><span>STOCK</span><span>SAME PATH</span><span>STOCK ONLY</span></div>${rows.map((row) => `<div class="observation-table-row"><strong>${escapeHTML(row.name || row.path)}</strong><span>${fmt(row.stock_pair_count)}</span><span>${fmt(row.same_path_type_count ?? row.observed_pair_count)}</span><span>${fmt(row.stock_only_pair_count)}</span></div>`).join('')}</div></section>`;
  explorer.innerHTML = `<div class="observation-summary">${cards.map(([value, label]) => `<div><strong>${fmt(value)}</strong><span>${label}</span></div>`).join('')}</div><div class="observation-intro"><p>Compared exact path and file type within the seven selected system roots. ${fileSystemSentence}${fmt(data.stock_only_pair_count)} stock pairs were not observed at those same paths in the filtered <code>/rootfs</code> view; the image breakdown below shows their source. This does not show that the files are absent from the phone or that a jailbreak changed them. A zero device-only count is enforced by the public catalog review gate.</p><button class="inline-link" id="observation-note">Read the source-bound interpretation ↗</button></div>${matrix('By IPSW image', data.volumes, 'IMAGE')}${matrix('By scanned root', data.roots, 'ROOT')}<section class="observation-list"><h3>Stock paths without a same-path device record</h3><div class="toolbar"><label class="searchbox"><span class="sr-only">Search stock-only paths</span><input id="observation-search" type="search" autocomplete="off" placeholder="Search stock-only paths…" value="${escapeHTML(state.query)}"></label><select id="observation-volume" aria-label="Filter IPSW image"><option value="all">All images</option>${data.volumes.map((row) => `<option value="${escapeHTML(row.name)}" ${state.volume === row.name ? 'selected' : ''}>${escapeHTML(row.name)}</option>`).join('')}</select><span class="result-count" id="observation-count"></span></div><div class="explorer-grid"><div id="observation-results" class="result-list"></div><aside id="observation-detail" class="detail"></aside></div></section>`;
  $('#observation-note').addEventListener('click', () => setTab('research', 'stock-device-boundary'));
  $('#observation-search').addEventListener('input', (event) => { state.query = event.target.value; state.limit = 80; clearTimeout(searchTimer); searchTimer = setTimeout(() => renderObservationResults(data), 180); });
  $('#observation-volume').addEventListener('change', (event) => { state.volume = event.target.value; state.limit = 80; state.selected = null; renderObservationResults(data); });
  renderObservationResults(data);
}

function renderObservationResults(data) {
  const query = state.query.trim().toLocaleLowerCase();
  const entries = data.stock_only.filter((row) =>
    (state.volume === 'all' || row[2].includes(state.volume)) &&
    (!query || `${row[0]} ${row[1]} ${row[2].join(' ')}`.toLocaleLowerCase().includes(query)));
  if (!entries.includes(state.selected)) state.selected = null;
  const visible = entries.slice(0, state.limit);
  $('#observation-count').textContent = `${fmt(entries.length)} paths`;
  $('#observation-results').innerHTML = `<div class="result-head"><span>STOCK PATH</span><span>IMAGE</span></div>${visible.map((row, index) => `<button class="result-row ${state.selected === row ? 'selected' : ''}" data-index="${index}" title="${escapeHTML(row[0])}"><span class="row-main"><span class="row-icon">${row[1] === 'directory' ? '▤' : row[1] === 'symlink' ? '↗' : '·'}</span><span class="row-text">${escapeHTML(row[0])}</span></span><span class="row-sub">${escapeHTML(row[2].join(', '))}</span></button>`).join('') || '<p class="empty-state">No paths match this filter.</p>'}${entries.length > state.limit ? '<button id="observation-more" class="more-button">Show more ↓</button>' : ''}`;
  const detail = (row) => row ? `<span class="detail-label">OFFICIAL IPSW PATH</span><h3>${escapeHTML(row[0].split('/').pop())}</h3><dl><dt>PATH</dt><dd>${escapeHTML(row[0])}</dd><dt>TYPE</dt><dd>${escapeHTML(row[1])}</dd><dt>STOCK IMAGE</dt><dd>${escapeHTML(row[2].join(', '))}</dd><dt>FILTERED /ROOTFS OBSERVATION</dt><dd>No record at the same path and type</dd></dl><p class="explain">The stock record comes from a separate mounted IPSW image. The device scan covered selected paths in the RootHide /rootfs namespace. This comparison cannot establish whether the file exists elsewhere on the device or whether a jailbreak changed it.</p><button class="inline-link" id="observation-stock-link">Find in stock filesystem ↗</button>` : '<div class="empty-detail">Select an official path to inspect its source boundary.</div>';
  $('#observation-detail').innerHTML = detail(state.selected);
  for (const button of $('#observation-results').querySelectorAll('.result-row')) button.addEventListener('click', () => { state.selected = visible[Number(button.dataset.index)]; renderObservationResults(data); });
  $('#observation-results').querySelector('#observation-more')?.addEventListener('click', () => { state.limit += 80; renderObservationResults(data); });
  $('#observation-stock-link')?.addEventListener('click', () => setTab('files', state.selected[0]));
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
  $('#build-select').addEventListener('change', () => { state.build = $('#build-select').value; state.selected = null; state.browsePath = '/'; state.swiftImage = null; state.reachSource = null; state.reachPaths = null; state.limit = 80; const build = activeBuild(); $('#metric-files').textContent = fmt(build.file_count); $('#metric-images').textContent = fmt(build.image_count); $('#metric-caches').textContent = fmt(build.cache_file_count); $('#metric-build').textContent = build.build; render().catch(showError); });
  for (const button of document.querySelectorAll('[data-tab]')) button.addEventListener('click', () => setTab(button.dataset.tab));
  const [initial, noteId] = location.hash.slice(1).split('/', 2);
  if (['files','restore','device','images','objc','protocols','swift','reach','driverkit','caches','archive','kernel','services','research','observation','compare'].includes(initial)) state.tab = initial;
  if (initial === 'research' && noteId) state.query = decodeURIComponent(noteId);
  if (initial === 'reach' && noteId) state.reachSource = decodeURIComponent(noteId);
  if (['files','restore','device'].includes(initial) && noteId) state.browsePath = decodeURIComponent(noteId);
  for (const button of document.querySelectorAll('[role="tab"]')) button.setAttribute('aria-selected', button.dataset.tab === state.tab);
  await render();
}

start().catch(showError);
