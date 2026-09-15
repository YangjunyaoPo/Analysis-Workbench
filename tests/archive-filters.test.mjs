import test from 'node:test';
import assert from 'node:assert/strict';
import {filterRecords} from '../prototype/archive-filters.mjs';

const records = [
  {id: 'a', title: 'Oil FTIR', category: 'FTIR', notes: 'Reference run', tags: ['olive'], date: '2026-09-10', savedAt: '2026-09-11', materials: [{name: 'trace.png', kind: 'image'}]},
  {id: 'b', title: 'Blank', category: 'Raman', notes: '', tags: [], date: '', savedAt: '2026-09-12', materials: [{name: 'result.csv', kind: 'table'}]},
  {id: 'c', title: 'Later', category: 'FTIR', notes: '', tags: [], date: '2026-09-11', savedAt: '2026-09-10', materials: []},
];
const ids = filters => filterRecords(records, filters).map(r => r.id);

test('query tokens search across metadata and filenames, then intersect filters', () => {
  assert.deepEqual(ids({query: 'OLIVE trace reference', kind: 'image', category: 'ftir'}), ['a']);
  assert.deepEqual(ids({query: 'olive result'}), []);
  assert.deepEqual(ids({kind: 'table'}), ['b']);
  assert.deepEqual(ids({category: 'FTIR'}), ['a', 'c']);
});

test('date ranges include boundaries and never invent an unknown experiment date', () => {
  assert.deepEqual(ids({from: '2026-09-10', to: '2026-09-11'}), ['a', 'c']);
  assert.deepEqual(ids({from: '2026-09-11', to: '2026-09-11'}), ['c']);
  assert.deepEqual(ids({unknown: true}), ['b']);
  assert.throws(() => ids({from: '2026-09-12', to: '2026-09-10'}), /start date/);
});

test('sorting distinguishes saved and experiment dates, leaving unknown dates last', () => {
  assert.deepEqual(ids({}), ['b', 'a', 'c']);
  assert.deepEqual(ids({sort: 'date-newest'}), ['c', 'a', 'b']);
  assert.deepEqual(ids({sort: 'date-oldest'}), ['a', 'c', 'b']);
  assert.deepEqual(ids({sort: 'title'}), ['b', 'c', 'a']);
  assert.deepEqual(records.map(r => r.id), ['a', 'b', 'c']);
});
