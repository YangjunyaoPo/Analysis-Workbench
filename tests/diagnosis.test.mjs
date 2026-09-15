import test from 'node:test';
import assert from 'node:assert/strict';
import {columnEnvelope} from '../scripts/diagnose_extraction.mjs';

const bounds = {py1:20,py2:0};

test('a linear ramp has no column-aggregation bias at its midpoint', () => {
  const ramp = [{px:0,py:0},{px:1,py:10}];
  assert.equal(columnEnvelope(ramp,.5,bounds),5);
});

test('a subpixel triangular peak is suppressed even with perfect coordinates', () => {
  const spike = [{px:0,py:0},{px:.5,py:10},{px:1,py:0}];
  // The reference at the column center is 10; its occupied-range midpoint is 5.
  assert.equal(columnEnvelope(spike,.5,bounds),5);
  assert.equal(columnEnvelope(spike,3,bounds),null);
});
