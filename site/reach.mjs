/** Breadth-first paths through exact in-cache Mach-O load declarations. */
export function computeReach(images, source, includeWeak = true) {
  const byName = new Map(images.map((image) => [image.install_name, image]));
  if (!byName.has(source)) throw new Error(`Unknown cache image: ${source}`);
  const parent = new Map([[source, null]]);
  const depth = new Map([[source, 0]]);
  const queue = [source];
  for (let head = 0; head < queue.length; head++) {
    const name = queue[head];
    for (const imp of byName.get(name).imports) {
      if (!includeWeak && imp.load_command === 'LC_LOAD_WEAK_DYLIB') continue;
      if (!byName.has(imp.install_name) || parent.has(imp.install_name)) continue;
      parent.set(imp.install_name, {from: name, load_command: imp.load_command});
      depth.set(imp.install_name, depth.get(name) + 1);
      queue.push(imp.install_name);
    }
  }
  return {parent, depth};
}

export function pathTo(parent, target) {
  if (!parent.has(target)) return null;
  const path = [];
  for (let name = target; name != null; ) {
    const incoming = parent.get(name);
    path.push({name, incoming});
    name = incoming?.from ?? null;
  }
  return path.reverse();
}
