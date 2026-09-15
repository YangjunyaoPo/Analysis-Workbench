// Uses the same pure extraction module as the UI; Python only decodes source PNGs.
// Usage: node scripts/evaluate_extraction.mjs /absolute/path/to/python
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {parseCSV,tablePoints,extractCurve,comparePixels,curvePoints,analyze,toData} from '../prototype/core.mjs';

const root=fileURLToPath(new URL('..',import.meta.url));
const python=process.argv[2]||'python';
const data=resolve(root,'data/initial-samples');
const reference=JSON.parse(readFileSync(resolve(data,'controlled-fixtures/ftir-reference.json')));
const arcadia=JSON.parse(readFileSync(resolve(data,'arcadia/inspection.json')));
const c={px1:150,px2:1340,py1:750,py2:140,x1:1600,x2:1800,y1:0,y2:.1};
const candidates=[{name:'ftir-controlled',image:resolve(data,'controlled-fixtures/ftir-reference.png'),points:reference.points.map(([x,y])=>({x,y})),c,rgb:[18,97,160],interval:[1600,1800],calibrationSource:'Known rendering coordinates; no manual calibration error.'}];
const manual=[
  {px1:126,px2:618,py1:366,py2:66,x1:500,x2:3500,y1:.8,y2:1.5},
  {px1:126,px2:618,py1:345,py2:90,x1:500,x2:3500,y1:752,y2:753.5},
  {px1:126,px2:618,py1:355,py2:109,x1:500,x2:3500,y1:.78,y2:.86},
];
for(const [i,s] of arcadia.samples.entries()){
  const stem=s.archive_stem.split('/').at(-1),folder=resolve(data,'arcadia/selected');
  const table=parseCSV(readFileSync(resolve(folder,stem+'.csv'),'utf8'));
  // Extend the tick-derived mapping to the visible plot frame to retain the baseline.
  const low=toData(90,385,manual[i]),high=toData(648,52,manual[i]);
  const full={px1:90,px2:648,py1:385,py2:52,x1:low.x,x2:high.x,y1:low.y,y2:high.y};
  candidates.push({name:stem,image:resolve(folder,stem+'.png'),points:tablePoints(table,4,1),c:full,rgb:[0,0,255],interval:[2800,3100],calibrationSource:'Manual tick mapping extended to visible plot frame. Error includes calibration and image/table disagreement.'});
}
const reports=[];
for(const item of candidates){
  const decoded=spawnSync(python,['-c','from PIL import Image; import sys; im=Image.open(sys.argv[1]).convert("RGBA"); sys.stdout.buffer.write(im.width.to_bytes(4,"little")+im.height.to_bytes(4,"little")+im.tobytes())',item.image],{maxBuffer:80*1024*1024});
  if(decoded.status!==0)throw Error(decoded.stderr.toString());
  const width=decoded.stdout.readUInt32LE(0),height=decoded.stdout.readUInt32LE(4),pixels=decoded.stdout.subarray(8);
  const extraction=extractCurve({data:pixels,width,height},item.c,item.rgb);
  const comparison=comparePixels(extraction,item.points,item.c);
  let imageAnalysis;
  try{imageAnalysis=analyze(curvePoints(extraction,item.c),...item.interval);}catch(error){imageAnalysis={error:error.message};}
  const report={sample:item.name,calibration:item.c,calibrationSource:item.calibrationSource,method:extraction.method,
    fullRegionCoverage:extraction.coverage,broadColumns:extraction.broadColumns,ambiguousColumns:extraction.ambiguousColumns,
    comparison,tableAnalysis:analyze(item.points,...item.interval),imageAnalysis};
  reports.push(report);
  console.log(JSON.stringify(report,null,2));
}
mkdirSync(resolve(root,'data/evaluation'),{recursive:true});
writeFileSync(resolve(root,'data/evaluation/extraction.json'),JSON.stringify(reports,null,2));
if(reports[0].comparison.p95>2||reports[0].comparison.coverage<.95)throw Error('Controlled curve fails the provisional acceptance threshold.');
if(Math.abs(reports[0].tableAnalysis.area-2.368734462460104)>1e-10)throw Error('FTIR numerical reference mismatch.');
