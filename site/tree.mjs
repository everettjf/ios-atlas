// Browse direct children without treating symlinks or cache install names as files.
export function directoryChildren(entries, directory, pathIndex, typeIndex, volumeIndex = null, selectedVolume = null) {
  if (!directory.startsWith('/') || (directory.length > 1 && directory.endsWith('/'))) throw new Error('invalid directory');
  const prefix = directory === '/' ? '/' : `${directory}/`;
  const children = new Map();
  for (const row of entries) {
    const volume = volumeIndex == null ? 0 : row[volumeIndex];
    if (selectedVolume != null && volume !== selectedVolume) continue;
    const path = row[pathIndex];
    if (!path.startsWith(prefix)) continue;
    const rest = path.slice(prefix.length);
    if (!rest) continue;
    const childPath = prefix + rest.split('/', 1)[0];
    const key = `${volume}\0${childPath}`;
    let child = children.get(key);
    if (!child) {
      child = {volume, path:childPath, row:null, descendantCount:0};
      children.set(key, child);
    }
    child.descendantCount++;
    if (path === childPath) child.row = row;
  }
  return [...children.values()].map((child) => ({...child, type:child.row?.[typeIndex] || 'virtual directory'}))
    .sort((a, b) => {
      const ad = a.type === 'directory' || a.type === 'virtual directory';
      const bd = b.type === 'directory' || b.type === 'virtual directory';
      return Number(bd) - Number(ad) || a.path.localeCompare(b.path) || a.volume - b.volume;
    });
}

export function parentDirectory(path) {
  if (path === '/') return null;
  return path.slice(0, path.lastIndexOf('/')) || '/';
}
