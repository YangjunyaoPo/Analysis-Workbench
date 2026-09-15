import {parseCSV,tablePoints,validateCalibration,extractCurve,curvePoints,analyze,comparePixels,toPixel} from './core.mjs';

const $ = id => document.getElementById(id);
const canvas = $('spectrum'), ctx = canvas.getContext('2d');
const sourceCanvas = document.createElement('canvas'), sourceContext = sourceCanvas.getContext('2d',{willReadFrequently:true});
const metadata = ['record-title','experiment-date','category','notes','x-unit','y-unit'];
const state = {id:null,revision:0,dirty:false,assets:{},table:null,calibration:{},extraction:null,result:null,
  comparison:null,sampleCalibration:null,mode:null,undo:[],records:[],image:null,cursor:{x:0,y:0}};
let busy = false;

function notice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
function dirty(){state.dirty=true;$('save-state').textContent='Unsaved changes';}
function clearResult(){state.result=null;state.comparison=null;renderResults();}
function invalidateExtraction(){state.extraction=null;state.undo=[];$('reviewed').checked=false;clearResult();renderExtraction();draw();}
function changedCurve(){clearResult();$('reviewed').checked=false;dirty();renderExtraction();draw();}
function number(id){const v=$(id).value;return v.trim()===''?NaN:Number(v);}
function calibration(){return {...state.calibration,...Object.fromEntries(['x1','x2','y1','y2'].map(k=>[k,number(k)]))};}
function selectedPoints(){if(!state.table)throw Error('Import a CSV first.');return tablePoints(state.table,Number($('x-column').value),Number($('y-column').value));}
function fmt(v){return Number.isFinite(v)?Number(v.toPrecision(8)).toString():'—';}
function rgb(){return $('trace-color').value.slice(1).match(/../g).map(v=>parseInt(v,16));}
async function api(url,body){const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Request':'1'},body:JSON.stringify(body)}:{});const result=await response.json();if(!response.ok)throw Error(result.error||'Request failed.');return result;}
function action(id,fn){$(id).addEventListener('click',()=>run(fn));}
async function run(fn){if(busy)return;busy=true;try{await fn();}catch(error){notice(error.message,true);}finally{busy=false;}}
function canReplace(){return !state.dirty || window.confirm('Discard the unsaved changes in this review?');}

function renderTable(){
  for(const id of ['x-column','y-column']){
    const old=$(id).value;$(id).replaceChildren();
    (state.table?.headers||[]).forEach((name,i)=>$(id).add(new Option(`${i+1}. ${name||'(unnamed)'}`,String(i))));
    if(old && Number(old)<(state.table?.headers.length||0))$(id).value=old;
  }
  renderTablePreview();
}
function renderTablePreview(){
  $('table-preview').replaceChildren();if(!state.table){$('table-summary').textContent='No CSV attached.';return;}
  const points=selectedPoints(),missing=points.filter(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)).length;
  $('table-summary').textContent=`${state.table.rows.length.toLocaleString()} rows · ${state.table.headers.length} columns · ${missing} rows with nonfinite selected values. Originals preserved.`;
  const table=document.createElement('table'),thead=table.createTHead(),header=thead.insertRow();
  const xi=Number($('x-column').value),yi=Number($('y-column').value);
  for(const value of ['Source row',state.table.headers[xi],state.table.headers[yi]]){const cell=document.createElement('th');cell.textContent=value;header.append(cell);}
  const body=table.createTBody();state.table.rows.slice(0,5).forEach((row,i)=>{const tr=body.insertRow();for(const value of [String(i+2),row[xi],row[yi]])tr.insertCell().textContent=value;});
  $('table-preview').append(table);
}
function renderAssets(){
  $('asset-status').textContent=[state.assets.csvName,state.assets.imageName].filter(Boolean).join(' + ')||'No materials attached';
  $('provenance').textContent=state.assets.provenance||'User-provided materials; units and experimental context need review.';
  $('sample-calibration').disabled=!state.sampleCalibration||!state.image;
  $('download-csv').disabled=!state.assets.csvText;$('download-image').disabled=!state.assets.imageData;
  $('extract').disabled=!state.image;
  $('image-empty').style.display=state.image?'none':'flex';
  $('image-empty').firstChild.textContent=state.assets.imageName?'Image archived; browser preview unavailable.':'Attach a spectrum image to begin.';
}
async function displayImage(){
  state.image=null;
  if(state.assets.imageData){
    const image=new Image();image.src=state.assets.imageData;
    try{
      await image.decode();
      if(image.width*image.height>16_000_000)throw Error('Image exceeds the 16-megapixel extraction limit. It remains attached.');
      state.image=image;canvas.width=sourceCanvas.width=image.width;canvas.height=sourceCanvas.height=image.height;
      sourceContext.clearRect(0,0,image.width,image.height);sourceContext.drawImage(image,0,0);
    }catch(error){notice(error.message.includes('16-megapixel')?error.message:'Image attached for archival. This browser cannot preview its format.',true);}
  }
  renderAssets();draw();
}
function setMode(mode){
  state.mode=mode;
  document.querySelectorAll('[data-mark]').forEach(b=>b.classList.toggle('active',b.dataset.mark===mode));
  $('correct').classList.toggle('active',mode==='correct');$('pick-color').classList.toggle('active',mode==='color');
  const instructions={x1:'Click the X1 tick on the image.',x2:'Click the X2 tick on the image.',y1:'Click the Y1 tick on the image.',y2:'Click the Y2 tick on the image.',color:'Click a solid-colored part of the trace.',correct:'Click the curve to replace the extracted point at that image column. Undo restores it.'};
  $('interaction-help').textContent=instructions[mode]||'Linear axes and one colored trace. Arrow keys move the crosshair; Enter selects. Shift + arrows moves 10 pixels.';
}
function draw(){
  ctx.clearRect(0,0,canvas.width,canvas.height);if(!state.image)return;
  ctx.drawImage(state.image,0,0);
  const c=calibration(),scale=canvas.width/(canvas.clientWidth||canvas.width);
  ctx.lineWidth=1.4*scale;
  try{
    validateCalibration(c,canvas.width,canvas.height);
    const left=Math.min(c.px1,c.px2),top=Math.min(c.py1,c.py2),w=Math.abs(c.px2-c.px1),h=Math.abs(c.py2-c.py1);
    ctx.strokeStyle='#68788c';ctx.setLineDash([4*scale,4*scale]);ctx.strokeRect(left,top,w,h);ctx.setLineDash([]);
    ctx.save();ctx.beginPath();ctx.rect(left,top,w,h);ctx.clip();
    if($('show-reference').checked && state.table){
      ctx.strokeStyle='#c12ea0';ctx.lineWidth=scale;ctx.beginPath();let open=false;
      for(const p of selectedPoints()){
        if(!Number.isFinite(p.x)||!Number.isFinite(p.y)){open=false;continue;}
        const v=toPixel(p.x,p.y,c);if(open)ctx.lineTo(v.px,v.py);else ctx.moveTo(v.px,v.py);open=true;
      }ctx.stroke();
    }
    if(state.extraction){ctx.strokeStyle='#d26b14';ctx.lineWidth=1.4*scale;ctx.beginPath();let open=false;
      for(const p of state.extraction.pixels){if(p.py===null){open=false;continue;}if(open)ctx.lineTo(p.px,p.py);else ctx.moveTo(p.px,p.py);open=true;}ctx.stroke();
      for(const p of state.extraction.pixels.filter(p=>p.corrected)){ctx.fillStyle='#d26b14';ctx.fillRect(p.px-2*scale,p.py-2*scale,4*scale,4*scale);}
    }ctx.restore();
  }catch{/* Calibration is intentionally incomplete while the user marks axes. */}
  ctx.strokeStyle='#b34d13';ctx.fillStyle='#b34d13';ctx.font=`${12*scale}px sans-serif`;
  for(const key of ['x1','x2','y1','y2']){
    const mark=state.calibration['mark'+key];if(!mark)continue;
    ctx.beginPath();ctx.arc(mark.x,mark.y,4*scale,0,Math.PI*2);ctx.stroke();ctx.fillText(key.toUpperCase(),mark.x+6*scale,mark.y-5*scale);
  }
  if(state.mode && document.activeElement===canvas){const p=state.cursor;ctx.strokeStyle='#394b61';ctx.beginPath();ctx.moveTo(p.x-6*scale,p.y);ctx.lineTo(p.x+6*scale,p.y);ctx.moveTo(p.x,p.y-6*scale);ctx.lineTo(p.x,p.y+6*scale);ctx.stroke();}
}
function renderExtraction(){
  const e=state.extraction;
  $('extraction-summary').textContent=e?`${e.pixels.filter(p=>p.py!==null).length} points · ${fmt(100*e.coverage)}% column coverage · ${e.broadColumns} broad columns · ${e.ambiguousColumns} separated-color columns · ${e.pixels.filter(p=>p.corrected).length} corrections. Inspect narrow peaks and noise.`:'No curve extracted. Images can still be saved.';
  $('marks-summary').textContent=['px1','px2','py1','py2'].map(k=>`${k}: ${fmt(state.calibration[k])}`).join(' · ');
  $('correct').disabled=!e;$('undo').disabled=!state.undo.length;$('export-curve').disabled=!e;
}
function renderResults(){
  $('results').replaceChildren();const r=state.result;
  if(!r){const p=document.createElement('p');p.className='muted';p.textContent='Select an interval to calculate its sampled maximum and trapezoidal area.';$('results').append(p);}
  else{
    const entries=[['Sampled maximum',fmt(r.maximum.y),`at ${fmt(r.maximum.x)} ${$('x-unit').value||'(unit unknown)'}`],['Raw interval area',fmt(r.area),`${$('y-unit').value||'unknown'} × ${$('x-unit').value||'unknown'}`],['Samples used',String(r.count),`${fmt(r.bounds[0])} to ${fmt(r.bounds[1])}`]];
    for(const [name,value,detail] of entries){const d=document.createElement('div');d.className='metric';for(const [tag,text] of [['span',name],['strong',value],['small',detail]]){const e=document.createElement(tag);e.textContent=text;d.append(e);}$('results').append(d);}
  }
  $('comparison').textContent=state.comparison?`CSV comparison: ${fmt(state.comparison.coverage*100)}% eligible coverage; median ${fmt(state.comparison.median)} px; 95th percentile ${fmt(state.comparison.p95)} px. Includes calibration and image/table mismatch; this is not a scientific accuracy certificate.`:'';
}
function reset(){
  Object.assign(state,{id:null,revision:0,dirty:false,assets:{},table:null,calibration:{},extraction:null,result:null,comparison:null,sampleCalibration:null,mode:null,undo:[],image:null});
  for(const id of metadata)$(id).value='';$('reviewed').checked=false;$('show-reference').checked=false;
  for(const [id,value] of Object.entries({'analysis-source':'table','trace-color':'#1261a0',tolerance:80,x1:0,x2:1,y1:0,y2:1,'interval-start':0,'interval-end':1}))$(id).value=value;
  $('csv-file').value='';$('image-file').value='';$('save-state').textContent='Unsaved review';
  renderTable();renderResults();renderExtraction();renderAssets();setMode(null);draw();
}
async function loadDemo(){
  if(!canReplace())return;
  const sample=await api('/api/samples/'+$('demo-choice').value);reset();
  state.assets={csvName:sample.csvName,csvText:sample.csvText,csvData:sample.csvData,imageName:sample.imageName,imageData:sample.imageData,provenance:sample.provenance,source:sample.source};
  state.table=parseCSV(sample.csvText);state.sampleCalibration=sample.calibration;
  for(const [id,value] of Object.entries({'record-title':sample.title,'experiment-date':sample.date,category:sample.category,'x-unit':sample.xUnit,'y-unit':sample.yUnit,'interval-start':sample.interval[0],'interval-end':sample.interval[1],'trace-color':sample.color}))$(id).value=value;
  renderTable();$('x-column').value=sample.xi;$('y-column').value=sample.yi;renderTablePreview();
  await displayImage();dirty();notice('Sample loaded. Set axis marks, or use the controlled sample calibration.');
}
function selectAt(x,y){
  if(!state.image||!state.mode)return;
  x=Math.max(0,Math.min(canvas.width-1,x));y=Math.max(0,Math.min(canvas.height-1,y));
  if(state.mode==='color'){
    const p=sourceContext.getImageData(Math.round(x),Math.round(y),1,1).data;
    $('trace-color').value='#'+[...p].slice(0,3).map(v=>v.toString(16).padStart(2,'0')).join('');invalidateExtraction();setMode(null);
  }else if(state.mode==='correct'){
    const c=calibration();if(!state.extraction)throw Error('Extract a curve first.');
    const point=state.extraction.pixels.find(p=>p.px===Math.floor(x)+.5);
    if(!point||y<Math.min(c.py1,c.py2)||y>Math.max(c.py1,c.py2))throw Error('Correct a point inside the calibrated region.');
    state.undo.push({...point});point.py=y;point.corrected=true;
    state.extraction.coverage=state.extraction.pixels.filter(p=>p.py!==null).length/state.extraction.pixels.length;changedCurve();return;
  }else{
    const key=state.mode;state.calibration['p'+key]=key[0]==='x'?x:y;state.calibration['mark'+key]={x,y};
    invalidateExtraction();setMode(null);
  }dirty();renderExtraction();draw();
}
canvas.addEventListener('pointerdown',event=>run(()=>{const rect=canvas.getBoundingClientRect();canvas.focus();selectAt((event.clientX-rect.left)*canvas.width/rect.width,(event.clientY-rect.top)*canvas.height/rect.height);}));
canvas.addEventListener('keydown',event=>{
  const deltas={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
  if(deltas[event.key]){event.preventDefault();const d=deltas[event.key],n=event.shiftKey?10:1;state.cursor={x:Math.max(0,Math.min(canvas.width-1,state.cursor.x+d[0]*n)),y:Math.max(0,Math.min(canvas.height-1,state.cursor.y+d[1]*n))};draw();}
  if(event.key==='Enter'){event.preventDefault();run(()=>selectAt(state.cursor.x,state.cursor.y));}
});
document.querySelectorAll('[data-mark]').forEach(button=>button.addEventListener('click',()=>{setMode(button.dataset.mark);state.cursor={x:canvas.width/2,y:canvas.height/2};}));
action('load-demo',loadDemo);
action('new-record',()=>{if(canReplace()){reset();notice('New review. Import your materials.');}});
action('sample-calibration',()=>{state.calibration={...state.sampleCalibration};for(const key of ['x1','x2','y1','y2'])$(key).value=state.calibration[key];invalidateExtraction();dirty();notice('Applied the renderer’s known axis positions. Manual calibration error is not included in this controlled case.');});
action('pick-color',()=>setMode('color'));
action('extract',()=>{
  if(!state.image)throw Error('Attach a supported image first.');
  const c=calibration();state.extraction=extractCurve(sourceContext.getImageData(0,0,canvas.width,canvas.height),c,rgb(),number('tolerance'));
  state.calibration=c;state.undo=[];setMode(null);changedCurve();
  try{state.comparison=comparePixels(state.extraction,selectedPoints(),c);}catch(error){notice(`Curve extracted. Reference comparison unavailable: ${error.message}`);renderResults();return;}
  renderResults();notice('Curve extracted. Inspect the orange overlay before using the result.');
});
action('correct',()=>setMode('correct'));
action('undo',()=>{const old=state.undo.pop();if(!old)return;const i=state.extraction.pixels.findIndex(p=>p.px===old.px);state.extraction.pixels[i]=old;state.extraction.coverage=state.extraction.pixels.filter(p=>p.py!==null).length/state.extraction.pixels.length;changedCurve();});
action('analyze',()=>{
  clearResult();const source=$('analysis-source').value;
  if(source==='image'&&!state.extraction)throw Error('Extract a curve first.');
  const points=source==='image'?curvePoints(state.extraction,calibration()):selectedPoints();
  state.result={...analyze(points,number('interval-start'),number('interval-end')),source,requestedBounds:[number('interval-start'),number('interval-end')]};
  if(state.extraction && state.table){try{state.comparison=comparePixels(state.extraction,selectedPoints(),calibration());}catch{/* Analysis can proceed without a reference comparison. */}}
  renderResults();dirty();notice('Calculated from '+(source==='image'?'the current extracted/corrected curve.':'the selected CSV columns.'));
});
for(const id of ['x1','x2','y1','y2','trace-color','tolerance'])$(id).addEventListener('input',()=>{invalidateExtraction();dirty();});
for(const id of ['x-column','y-column'])$(id).addEventListener('change',()=>{renderTablePreview();clearResult();dirty();draw();});
for(const id of ['interval-start','interval-end','analysis-source'])$(id).addEventListener('input',()=>{clearResult();dirty();});
for(const id of metadata)$(id).addEventListener('input',()=>{dirty();if(id.endsWith('unit'))renderResults();});
$('reviewed').addEventListener('change',dirty);$('show-reference').addEventListener('change',draw);
function readFile(file,asURL=false){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read file.'));asURL?reader.readAsDataURL(file):reader.readAsText(file);});}
for(const kind of ['csv','image'])$(kind+'-file').addEventListener('change',()=>run(async()=>{
  const file=$(kind+'-file').files[0];if(!file)return;if(file.size>12*1024*1024)throw Error('Each attachment must be at most 12 MiB.');
  if(kind==='csv'){
    const text=await readFile(file),table=parseCSV(text),original=await readFile(file,true);state.assets.csvText=text;state.assets.csvData=original;state.assets.csvName=file.name;state.table=table;
    renderTable();$('x-column').value='0';$('y-column').value='1';$('x-unit').value='';$('y-unit').value='';renderTablePreview();clearResult();
  }else{
    if(!/\.(png|jpg|jpeg|webp|bmp|tif|tiff)$/i.test(file.name))throw Error('Attach PNG, JPEG, WebP, BMP, or TIFF.');
    state.assets.imageData=await readFile(file,true);state.assets.imageName=file.name;state.calibration={};state.sampleCalibration=null;invalidateExtraction();
  }
  state.assets.provenance='User-provided materials. Check the pairing, units, and experiment date.';delete state.assets.source;
  if(!$('record-title').value)$('record-title').value=file.name;
  await displayImage();renderAssets();dirty();notice(kind==='image'&&!state.image?`${file.name} attached for archival; preview and extraction are unavailable.`:`${file.name} attached. Review its metadata before analysis.`);
}));
function snapshot(){return {schema:1,id:state.id,revision:state.revision,title:$('record-title').value.trim(),date:$('experiment-date').value,category:$('category').value.trim(),notes:$('notes').value,
  assets:state.assets,calibration:calibration(),sampleCalibration:state.sampleCalibration,extraction:state.extraction,result:state.result,comparison:state.comparison,
  reviewed:$('reviewed').checked,settings:{xi:$('x-column').value,yi:$('y-column').value,xUnit:$('x-unit').value,yUnit:$('y-unit').value,color:$('trace-color').value,tolerance:number('tolerance'),
    source:$('analysis-source').value,lo:$('interval-start').value,hi:$('interval-end').value}};}
async function save(){
  if(!$('record-title').value.trim())throw Error('Give the review a title.');
  if(!state.assets.csvText&&!state.assets.imageData)throw Error('Attach at least one material.');
  const saved=await api('/api/records',snapshot());Object.assign(state,saved);state.dirty=false;$('save-state').textContent='Saved locally';await listRecords();notice('Saved originals, settings, corrections, and results on this computer.');
}
action('save-record',save);
function download(url,name){const link=document.createElement('a');link.href=url;link.download=name;link.click();}
action('download-csv',()=>{if(state.assets.csvData)download(state.assets.csvData,state.assets.csvName);else if(state.assets.csvText){const url=URL.createObjectURL(new Blob([state.assets.csvText],{type:'text/csv'}));download(url,state.assets.csvName);setTimeout(()=>URL.revokeObjectURL(url),1000);}});
action('download-image',()=>{if(state.assets.imageData)download(state.assets.imageData,state.assets.imageName);});
async function listRecords(){state.records=await api('/api/records');renderRecords();}
function renderRecords(){
  const category=$('category-filter').value.toLowerCase(),date=$('date-filter').value,unknown=$('unknown-filter').checked;
  $('record-list').replaceChildren();const filtered=state.records.filter(r=>(!category||r.category.toLowerCase().includes(category))&&(!date||r.date===date)&&(!unknown||!r.date));
  for(const record of filtered){const b=document.createElement('button');b.className='record-item';b.textContent=record.title;const d=document.createElement('small');d.textContent=`${record.date||'Unknown date'} · ${record.category||'Uncategorized'}`;b.append(d);b.addEventListener('click',()=>run(()=>openRecord(record.id)));$('record-list').append(b);}
  if(!filtered.length){const p=document.createElement('p');p.className='muted';p.textContent=state.records.length?'No matching reviews.':'No saved reviews yet.';$('record-list').append(p);}
}
async function openRecord(id){
  if(!canReplace())return;const r=await api('/api/records/'+id);if(r.schema!==1)throw Error('Unsupported saved format.');reset();
  Object.assign(state,{id:r.id,revision:r.revision,assets:r.assets,calibration:r.calibration||{},sampleCalibration:r.sampleCalibration,extraction:r.extraction,result:r.result,comparison:r.comparison});
  for(const [k,v] of Object.entries({'record-title':r.title,'experiment-date':r.date,category:r.category,notes:r.notes,'x-unit':r.settings.xUnit,'y-unit':r.settings.yUnit,'trace-color':r.settings.color,tolerance:r.settings.tolerance,'analysis-source':r.settings.source,'interval-start':r.settings.lo,'interval-end':r.settings.hi}))$(k).value=v;
  for(const key of ['x1','x2','y1','y2'])$(key).value=r.calibration?.[key]??'';
  state.table=r.assets.csvText?parseCSV(r.assets.csvText):null;renderTable();$('x-column').value=r.settings.xi;$('y-column').value=r.settings.yi;renderTablePreview();
  $('reviewed').checked=!!r.reviewed;await displayImage();renderExtraction();renderResults();state.dirty=false;$('save-state').textContent='Saved locally';notice('Review reopened with its original materials and saved results.');
}
for(const id of ['category-filter','date-filter','unknown-filter'])$(id).addEventListener('input',renderRecords);
action('export-curve',()=>{
  if(!state.extraction)throw Error('Extract a curve first.');const rows=curvePoints(state.extraction,calibration());
  const text='x,y\n'+rows.map(p=>`${p.x},${Number.isFinite(p.y)?p.y:''}`).join('\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv'}));
  const a=document.createElement('a');a.href=url;a.download='extracted-curve.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
window.addEventListener('resize',draw);
reset();run(async()=>{await listRecords();const recordId=new URLSearchParams(location.search).get('record');if(recordId)await openRecord(recordId);});
// Optional, read-only access to the same summary visible in the review surface.
if(document.modelContext?.registerTool){
  Promise.resolve(document.modelContext.registerTool({name:'read_spectrum_review',title:'Read current spectrum review',description:'Read the visible review title, extraction summary, numerical result, and saved state. Does not modify or save a review.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute(input){if(!input||Object.keys(input).length)throw Error('No arguments accepted.');return {title:$('record-title').value,extraction:$('extraction-summary').textContent,result:state.result,saved:!state.dirty};}})).catch(()=>{});
}
