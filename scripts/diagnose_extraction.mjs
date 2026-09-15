// Separate column aggregation from raster/calibration/pairing effects.
// This changes neither the extractor nor the acceptance metric.
// Run evaluate_extraction.mjs first, then: node scripts/diagnose_extraction.mjs python
import {readFileSync, writeFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {parseCSV, tablePoints, extractCurve, toPixel, comparePixels} from '../prototype/core.mjs';

function quantiles(values) {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) throw Error('No eligible measurements.');
  return {count: sorted.length, median: sorted[Math.floor(sorted.length / 2)],
    p95: sorted[Math.ceil(sorted.length * .95) - 1]};
}

// A continuous polyline crossing a pixel column occupies a vertical range.
// Reducing this range to one midpoint discards any excursions within that column.
export function columnEnvelope(projected, center, c) {
  let minimum = Infinity, maximum = -Infinity;
  for (let i = 1; i < projected.length; i++) {
    const a = projected[i - 1], b = projected[i];
    if (b.px < center - .5) continue;
    if (a.px > center + .5) break;
    const left = Math.max(a.px, center - .5), right = Math.min(b.px, center + .5);
    if (left > right) continue;
    const y = px => a.py + (px - a.px) * (b.py - a.py) / (b.px - a.px);
    minimum = Math.min(minimum, y(left), y(right));
    maximum = Math.max(maximum, y(left), y(right));
  }
  const top = Math.min(c.py1, c.py2), bottom = Math.max(c.py1, c.py2);
  if (minimum > bottom || maximum < top) return null;
  return (Math.max(top, minimum) + Math.min(bottom, maximum)) / 2;
}

function main() {
const root = fileURLToPath(new URL('..', import.meta.url));
const python = process.argv[2] || 'python';
const reports = JSON.parse(readFileSync(resolve(root, 'data/evaluation/extraction.json')));
const diagnoses = [];
for (const report of reports) {
  const controlled = report.sample === 'ftir-controlled';
  let points, image;
  if (controlled) {
    const fixture = resolve(root, 'data/initial-samples/controlled-fixtures/ftir-reference');
    points = JSON.parse(readFileSync(fixture + '.json')).points.map(([x,y]) => ({x,y}));
    image = fixture + '.png';
  } else {
    const fixture = resolve(root, 'data/initial-samples/arcadia/selected', report.sample);
    points = tablePoints(parseCSV(readFileSync(fixture + '.csv', 'utf8')), 4, 1);
    image = fixture + '.png';
  }
  const decoded = spawnSync(python, ['-c',
    'from PIL import Image; import sys; im=Image.open(sys.argv[1]).convert("RGBA"); sys.stdout.buffer.write(im.width.to_bytes(4,"little")+im.height.to_bytes(4,"little")+im.tobytes())', image],
  {maxBuffer: 80 * 1024 * 1024});
  if (decoded.status !== 0) throw Error(decoded.stderr.toString());
  const width = decoded.stdout.readUInt32LE(0), height = decoded.stdout.readUInt32LE(4);
  const data = decoded.stdout.subarray(8), c = report.calibration;
  const rgb = controlled ? [18,97,160] : [0,0,255];
  const extraction = extractCurve({data, width, height}, c, rgb);
  const projected = points.map(p => toPixel(p.x, p.y, c)).sort((a,b) => a.px - b.px);
  const aggregationErrors = [], residualErrors = [], originalErrors = [];
  let index = 0;
  for (const pixel of extraction.pixels) {
    if (pixel.py === null || pixel.px < projected[0].px || pixel.px > projected.at(-1).px) continue;
    while (index < projected.length - 2 && projected[index+1].px < pixel.px) index++;
    const a = projected[index], b = projected[index+1];
    const referenceY = a.py + (pixel.px-a.px) * (b.py-a.py) / (b.px-a.px);
    if (referenceY < Math.min(c.py1,c.py2) || referenceY > Math.max(c.py1,c.py2)) continue;
    const midpoint = columnEnvelope(projected, pixel.px, c);
    if (midpoint === null) continue;
    aggregationErrors.push(Math.abs(midpoint-referenceY));
    residualErrors.push(Math.abs(pixel.py-midpoint));
    originalErrors.push(Math.abs(pixel.py-referenceY));
  }
  // Supporting geometric consistency only. A dense/noisy ink band can match many
  // different numerical series, so proximity cannot certify an image/CSV pair.
  let eligible = 0, nearInk = 0;
  for (const p of projected) {
    if (p.px < c.px1 || p.px > c.px2 || p.py < c.py2 || p.py > c.py1) continue;
    eligible++;
    let distance = Infinity;
    for (let py = Math.max(0,Math.floor(p.py)-3); py <= Math.min(height-1,Math.floor(p.py)+3); py++) {
      for (let px = Math.max(0,Math.floor(p.px)-3); px <= Math.min(width-1,Math.floor(p.px)+3); px++) {
        const i = (py * width + px) * 4;
        if (data[i+3] < 128 || Math.hypot(data[i]-rgb[0],data[i+1]-rgb[1],data[i+2]-rgb[2]) > 80) continue;
        distance = Math.min(distance, Math.hypot(px+.5-p.px,py+.5-p.py));
      }
    }
    if (distance <= 2) nearInk++;
  }
  const translations = [];
  for (const dx of [-1,0,1]) {
    for (const dy of [-1,0,1]) {
      const moved = {...c, px1:c.px1+dx, px2:c.px2+dx, py1:c.py1+dy, py2:c.py2+dy};
      translations.push({dx, dy, p95:comparePixels(extraction, points, moved).p95});
    }
  }
  const result = {sample: report.sample, calibration: c,
    originalVerticalError: quantiles(originalErrors),
    idealColumnAggregationError: quantiles(aggregationErrors),
    residualAgainstColumnEnvelope: quantiles(residualErrors),
    referenceVerticesWithinTwoPixelsOfInk: {eligible, matched:nearInk, fraction:nearInk/eligible},
    onePixelCalibrationTranslationSensitivity: translations,
    limits: 'The envelope is computed from the reference and is diagnostic only, not an image extraction algorithm. Quantiles are not additive. Residuals still combine calibration, rasterization, thresholding and possible image/table mismatch.'};
  diagnoses.push(result);
  console.log(JSON.stringify(result, null, 2));
}
writeFileSync(resolve(root, 'data/evaluation/extraction-diagnosis.json'), JSON.stringify(diagnoses, null, 2));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
