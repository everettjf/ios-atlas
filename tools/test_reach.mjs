import assert from 'node:assert/strict';
import {computeReach, pathTo} from '../site/reach.mjs';

const image = (name, imports = []) => ({install_name:name, imports});
const load = (name, command = 'LC_LOAD_DYLIB') => ({install_name:name, load_command:command});
const images = [
  image('A', [load('B'), load('C', 'LC_LOAD_WEAK_DYLIB'), load('outside')]),
  image('B', [load('D'), load('A')]),
  image('C', [load('D')]),
  image('D', [])
];

const strict = computeReach(images, 'A', false);
assert.deepEqual([...strict.depth.entries()], [['A',0], ['B',1], ['D',2]]);
assert.equal(pathTo(strict.parent, 'C'), null);
assert.deepEqual(pathTo(strict.parent, 'D').map((item) => item.name), ['A','B','D']);

const all = computeReach(images, 'A', true);
assert.equal(all.depth.get('C'), 1);
assert.equal(all.depth.get('D'), 2);
assert.equal(pathTo(all.parent, 'C')[1].incoming.load_command, 'LC_LOAD_WEAK_DYLIB');
assert.throws(() => computeReach(images, 'missing'), /Unknown cache image/);
console.log('reach graph cycle, weak-load, unmatched-target and shortest-path checks passed');
