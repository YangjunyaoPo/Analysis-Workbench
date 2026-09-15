import test from 'node:test';
import assert from 'node:assert/strict';
import {analyze,parseCSV,tablePoints,extractCurve,toData,toPixel,comparePixels,curvePoints} from '../prototype/core.mjs';

test('CSV preserves quoted commas, multiline fields, duplicates, and missing signals',()=>{
  const t=parseCSV('\uFEFFid,x,y\r\n"a,b",0,-1\r\n"a\nb",1,NaN\r\n"a,b",2,\r\n');
  assert.equal(t.rows.length,3);assert.equal(t.rows[0][0],'a,b');assert.equal(t.rows[1][0],'a\nb');
  const p=tablePoints(t,1,2);assert.equal(p[0].y,-1);assert.ok(Number.isNaN(p[1].y));assert.ok(Number.isNaN(p[2].y));
  assert.throws(()=>parseCSV('x,y\n1,"open'),/Unclosed/);
});
test('triangle with known analytic area works in either coordinate direction',()=>{
  const points=[{x:0,y:0},{x:1,y:2},{x:2,y:0}];
  assert.equal(analyze(points,0,2).area,2);
  assert.equal(analyze([...points].reverse(),0,2).area,2);
  assert.deepEqual(analyze(points,0,2).maximum,{x:1,y:2});
});
test('interval boundaries select existing samples; gaps and duplicate X are rejected',()=>{
  const p=[{x:0,y:0},{x:1,y:2},{x:2,y:4},{x:3,y:6}];
  const r=analyze(p,.2,2.8);assert.deepEqual(r.bounds,[1,2]);assert.equal(r.area,3);
  assert.throws(()=>analyze([{x:0,y:1},{x:1,y:NaN},{x:2,y:3}],0,2),/missing/);
  assert.throws(()=>analyze([{x:0,y:1},{x:0,y:2}],0,2),/monotonic/);
});
test('linear calibration supports descending physical axes',()=>{
  const c={px1:0,px2:20,py1:20,py2:0,x1:4000,x2:500,y1:0,y2:10};
  assert.deepEqual(toData(10,10,c),{x:2250,y:5});
  assert.deepEqual(toPixel(2250,5,c),{px:10,py:10});
});
test('known raster diagonal extracts correctly and preserves a missing column',()=>{
  const width=21,height=21,data=new Uint8ClampedArray(width*height*4).fill(255);
  for(let x=0;x<21;x++){if(x===10)continue;const i=((20-x)*width+x)*4;data[i]=0;data[i+1]=0;data[i+2]=255;}
  const c={px1:.5,px2:20.5,py1:20.5,py2:.5,x1:0,x2:20,y1:0,y2:20};
  const e=extractCurve({data,width,height},c,[0,0,255],10);
  assert.equal(e.pixels[10].py,null);assert.equal(e.pixels[4].py,16.5);assert.equal(e.coverage,20/21);
  const comparison=comparePixels(e,[{x:0,y:0},{x:20,y:20}],c);
  assert.equal(comparison.p95,0);assert.equal(comparison.coverage,20/21);
  assert.throws(()=>extractCurve({data,width,height},c,[30,30,30]),/colored/);
  const extracted=curvePoints(e,c);assert.equal(extracted.length,21);
  assert.throws(()=>analyze(extracted,0,20),/missing/);
});
