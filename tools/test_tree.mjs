import assert from 'node:assert/strict';
import {directoryChildren, parentDirectory} from '../site/tree.mjs';

const entries = [
  [0, '/System', 'directory'],
  [0, '/System/Library', 'directory'],
  [0, '/System/Library/Foo.framework', 'directory'],
  [0, '/System/Library/Foo.framework/Info.plist', 'file'],
  [0, '/System/Alias', 'symlink'],
  [1, '/System', 'directory'],
  [1, '/System/DriverKit/Library', 'directory'],
];
const root = directoryChildren(entries, '/', 1, 2, 0);
assert.equal(root.length, 2);
assert.equal(root[0].path, '/System');
assert.equal(root[0].volume, 0);
assert.equal(root[0].descendantCount, 5);
assert.equal(root[1].volume, 1);
const system = directoryChildren(entries, '/System', 1, 2, 0, 0);
assert.deepEqual(system.map((item) => [item.path, item.type, item.descendantCount]), [
  ['/System/Library', 'directory', 3],
  ['/System/Alias', 'symlink', 1],
]);
const driver = directoryChildren(entries, '/System', 1, 2, 0, 1);
assert.equal(driver[0].type, 'virtual directory');
assert.equal(driver[0].path, '/System/DriverKit');
assert.equal(driver[0].descendantCount, 1);
assert.deepEqual(directoryChildren(entries, '/absent', 1, 2, 0), []);
assert.equal(parentDirectory('/System/Library'), '/System');
assert.equal(parentDirectory('/System'), '/');
assert.equal(parentDirectory('/'), null);
console.log('directory browse logic passed');
