// Pure data operations shared by the browser and the numerical evaluation runner.
export function parseCSV(text) {
  const rows = []; let row = [], value = '', quoted = false, closed = false;
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { value += '"'; i++; }
      else if (ch === '"') { quoted = false; closed = true; }
      else value += ch;
    } else if (ch === '"') {
      if (value || closed) throw Error('Unexpected quote in CSV.');
      quoted = true;
    } else if (ch === ',' || ch === '\n' || ch === '\r') {
      row.push(value); value = ''; closed = false;
      if (ch !== ',') {
        if (ch === '\r' && text[i + 1] === '\n') i++;
        rows.push(row); row = [];
      }
    } else {
      if (closed) throw Error('Unexpected text after a quoted CSV field.');
      value += ch;
    }
  }
  if (quoted) throw Error('Unclosed CSV quote.');
  if (row.length || value || closed) rows.push([...row, value]);
  if (rows.length < 2 || rows[0].length < 2) throw Error('A header and at least two columns are required.');
  if (rows.some(r => r.length !== rows[0].length)) throw Error('CSV rows have inconsistent column counts.');
  return {headers: rows[0], rows: rows.slice(1)};
}

export function tablePoints(table, xi, yi) {
  const number = v => v.trim() === '' ? NaN : Number(v);
  return table.rows.map((row, i) => ({x: number(row[xi]), y: number(row[yi]), row: i + 2}));
}

export function validateCalibration(c, width, height) {
  const keys = ['px1','px2','py1','py2','x1','x2','y1','y2'];
  if (!c || keys.some(k => !Number.isFinite(c[k]))) throw Error('Set all four axis marks and values.');
  if (Math.abs(c.px2 - c.px1) < 10 || Math.abs(c.py2 - c.py1) < 10) throw Error('Axis marks must be at least 10 pixels apart.');
  if (c.x1 === c.x2 || c.y1 === c.y2) throw Error('Axis values must differ.');
  if ([c.px1,c.px2].some(v => v < 0 || v >= width) || [c.py1,c.py2].some(v => v < 0 || v >= height)) throw Error('Axis marks must lie inside the image.');
  return c;
}

export function toData(px, py, c) {
  return {x: c.x1 + (px - c.px1) * (c.x2 - c.x1) / (c.px2 - c.px1),
    y: c.y1 + (py - c.py1) * (c.y2 - c.y1) / (c.py2 - c.py1)};
}

export function toPixel(x, y, c) {
  return {px: c.px1 + (x - c.x1) * (c.px2 - c.px1) / (c.x2 - c.x1),
    py: c.py1 + (y - c.y1) * (c.py2 - c.py1) / (c.y2 - c.y1)};
}

export function extractCurve({data, width, height}, calibration, rgb, tolerance = 80) {
  const c = validateCalibration(calibration, width, height);
  if (rgb.length !== 3 || rgb.some(v => !Number.isFinite(v) || v < 0 || v > 255)) throw Error('Select a valid trace color.');
  if (Math.max(...rgb) - Math.min(...rgb) < 40) throw Error('This prototype extracts colored traces. Keep grayscale images as attachments.');
  if (!(tolerance >= 1 && tolerance <= 200)) throw Error('Color tolerance must be between 1 and 200.');
  // Raster indices locate pixel boxes; calibration and output use their centers.
  const left = Math.max(0,Math.ceil(Math.min(c.px1,c.px2)-.5)), right = Math.min(width-1,Math.floor(Math.max(c.px1,c.px2)-.5));
  const top = Math.max(0,Math.ceil(Math.min(c.py1,c.py2)-.5)), bottom = Math.min(height-1,Math.floor(Math.max(c.py1,c.py2)-.5));
  const pixels = []; let ambiguous = 0, broad = 0;
  for (let px = left; px <= right; px++) {
    const ys = [];
    for (let py = top; py <= bottom; py++) {
      const i = (py * width + px) * 4;
      if (data[i + 3] < 128) continue;
      const d = Math.hypot(data[i]-rgb[0], data[i+1]-rgb[1], data[i+2]-rgb[2]);
      if (d <= tolerance) ys.push(py);
    }
    if (!ys.length) { pixels.push({px:px+.5, py: null}); continue; }
    if (ys.some((v,i) => i && v - ys[i-1] > 2)) ambiguous++;
    if (ys.at(-1) - ys[0] > 8) broad++;
    const mid = (ys.length - 1) / 2;
    pixels.push({px:px+.5, py: (ys[Math.floor(mid)] + ys[Math.ceil(mid)]) / 2 + .5});
  }
  const matched = pixels.filter(p => p.py !== null).length;
  if (!matched) throw Error('No trace found. Check axis bounds, trace color, and tolerance.');
  return {pixels, coverage: matched / pixels.length, ambiguousColumns: ambiguous, broadColumns: broad,
    method: 'rgb-distance-column-median-v1', tolerance, rgb};
}

export function curvePoints(extraction, calibration) {
  // No extrapolation beyond the detected trace. Internal gaps remain explicit.
  const first = extraction.pixels.findIndex(p => p.py !== null);
  const last = extraction.pixels.findLastIndex(p => p.py !== null);
  return extraction.pixels.slice(first,last+1).map(p => p.py === null
    ? {x: toData(p.px, 0, calibration).x, y: NaN}
    : toData(p.px, p.py, calibration));
}

export function analyze(points, lo, hi) {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo >= hi) throw Error('Enter an increasing, finite analysis interval.');
  if (points.some(p => !Number.isFinite(p.x))) throw Error('A nonfinite X value prevents interval selection. Review the table.');
  const direction = Math.sign(points.at(-1)?.x - points[0]?.x);
  if (!direction || points.some((p,i) => i && Math.sign(p.x - points[i-1].x) !== direction)) throw Error('X must be strictly monotonic; duplicate or unordered coordinates need review.');
  const band = points.filter(p => p.x >= lo && p.x <= hi);
  if (band.length < 2) throw Error('The interval must contain at least two samples.');
  if (band.some(p => !Number.isFinite(p.y))) throw Error('The interval contains missing values or extraction gaps. Correct them or choose a complete interval.');
  if (direction < 0) band.reverse();
  let area = 0, compensation = 0, peak = band[0];
  for (let i = 1; i < band.length; i++) {
    const term = (band[i].x - band[i-1].x) * (band[i].y + band[i-1].y) / 2;
    const adjusted = term - compensation, next = area + adjusted;
    compensation = (next - area) - adjusted; area = next;
    if (band[i].y > peak.y) peak = band[i];
  }
  if (!Number.isFinite(area)) throw Error('The integral exceeds the numeric range.');
  return {count: band.length, bounds: [band[0].x,band.at(-1).x], maximum: {x:peak.x,y:peak.y},
    area, method:'sampled-trapezoid-v1', baseline:'none'};
}

export function comparePixels(extraction, reference, c) {
  if (reference.some(p => !Number.isFinite(p.x) || !Number.isFinite(p.y))) throw Error('Reference contains missing values.');
  const points = reference.map(p => toPixel(p.x,p.y,c)).sort((a,b)=>a.px-b.px);
  if (points.some((p,i)=>i && p.px<=points[i-1].px)) throw Error('Reference coordinates must be unique.');
  const errors = []; let eligible = 0, j = 0;
  for (const p of extraction.pixels) {
    if (p.px < points[0].px || p.px > points.at(-1).px) continue;
    while (j < points.length-2 && points[j+1].px < p.px) j++;
    const a=points[j], b=points[j+1], py=a.py+(p.px-a.px)*(b.py-a.py)/(b.px-a.px);
    if (py < Math.min(c.py1,c.py2) || py > Math.max(c.py1,c.py2)) continue;
    eligible++;
    if (p.py !== null) errors.push(Math.abs(p.py-py));
  }
  if (!eligible || !errors.length) throw Error('No overlapping reference points inside calibrated bounds.');
  errors.sort((a,b)=>a-b);
  return {eligible, matched:errors.length, coverage:errors.length/eligible,
    p95:errors[Math.ceil(errors.length*.95)-1], median:errors[Math.floor(errors.length/2)],
    definition:'Vertical pixel error against linearly interpolated CSV reference; calibration error included.'};
}
