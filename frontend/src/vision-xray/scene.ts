/** Small declarative 3D wireframe renderer. No eval, external CAD or new dependency. */
export type Vec3 = [number, number, number];
export type Part = {
  key: string; name: string; function: string; how_it_works: string;
  shape: 'shell' | 'board' | 'keypad' | 'cylinder' | 'spring' | 'cone' | 'bottle' | 'ring' | 'box';
  size: Vec3; assembled: Vec3; exploded: Vec3; evidence: 'typical';
};
export type Manifest = {
  schema_version: 1; canonical_key: string; title: string;
  evidence_level: 'illustrative'; match_scope: 'family'; units: 'illustrative';
  parts: Part[]; limitations: string;
};
export type Box = [number, number, number, number];
type Point = [number, number];
type Mesh = { v: Vec3[]; e: [number, number][]; faces: number[][]; dots: Vec3[] };
type Hit = { key: string; bounds: [number, number, number, number]; depth: number };

function mesh(): Mesh { return { v: [], e: [], faces: [], dots: [] }; }
function line(m: Mesh, a: Vec3, b: Vec3) {
  const i = m.v.length; m.v.push(a, b); m.e.push([i, i + 1]);
  for (let k = 0; k < 4; k++) m.dots.push(a.map((x, j) => x + (b[j] - x) * k / 4) as Vec3);
}
function ring(m: Mesh, points: Vec3[]) {
  const start = m.v.length; m.v.push(...points);
  points.forEach((p, i) => { m.e.push([start + i, start + (i + 1) % points.length]); m.dots.push(p); });
  return points.map((_, i) => start + i);
}
function rect(w: number, h: number, z: number, cx = 0, cy = 0): Vec3[] {
  const r = Math.min(w * .21, h * .09);
  const out: Vec3[] = [];
  for (let corner = 0; corner < 4; corner++) {
    const centers = [[w / 2 - r, h / 2 - r], [-w / 2 + r, h / 2 - r], [-w / 2 + r, -h / 2 + r], [w / 2 - r, -h / 2 + r]];
    for (let k = 0; k <= 5; k++) {
      const a = corner * Math.PI / 2 + k * Math.PI / 10;
      out.push([cx + centers[corner][0] + r * Math.cos(a), cy + centers[corner][1] + r * Math.sin(a), z]);
    }
  }
  return out;
}
function plate(m: Mesh, w: number, h: number, d: number, cx = 0, cy = 0, cz = 0) {
  const a = ring(m, rect(w, h, cz - d / 2, cx, cy));
  const b = ring(m, rect(w, h, cz + d / 2, cx, cy));
  m.faces.push(b);
  for (let i = 0; i < a.length; i += 3) { m.e.push([a[i], b[i]]); }
  for (let i = 0; i < a.length; i++) m.faces.push([a[i], a[(i + 1) % a.length], b[(i + 1) % b.length], b[i]]);
}
function circleXY(m: Mesh, cx: number, cy: number, z: number, r: number) {
  ring(m, Array.from({ length: 24 }, (_, i) => [cx + Math.cos(i * Math.PI / 12) * r, cy + Math.sin(i * Math.PI / 12) * r, z] as Vec3));
}
function radial(m: Mesh, w: number, h: number, d: number, profile: [number, number][], hollow = false) {
  const loops = profile.map(([y, radius]) => ring(m, Array.from({ length: 32 }, (_, i) => [Math.cos(i * Math.PI / 16) * w / 2 * radius, y * h, Math.sin(i * Math.PI / 16) * d / 2 * radius] as Vec3)));
  for (let j = 1; j < loops.length; j++) {
    for (let i = 0; i < 32; i++) {
      if (i % 4 === 0) m.e.push([loops[j - 1][i], loops[j][i]]);
      m.faces.push([loops[j - 1][i], loops[j - 1][(i + 1) % 32], loops[j][(i + 1) % 32], loops[j][i]]);
    }
  }
  if (!hollow) m.faces.push(loops[loops.length - 1]);
}
export function geometry(part: Part): Mesh {
  const m = mesh(); const [w, h, d] = part.size;
  if (part.shape === 'spring') {
    let previous: Vec3 = [w / 2, -h / 2, 0];
    for (let i = 1; i <= 180; i++) {
      const a = i / 180 * Math.PI * 16;
      const current: Vec3 = [Math.cos(a) * w / 2, (i / 180 - .5) * h, Math.sin(a) * d / 2];
      line(m, previous, current); previous = current;
    }
  } else if (['cylinder', 'cone', 'bottle', 'ring'].includes(part.shape)) {
    if (part.shape === 'bottle') radial(m, w, h, d, [[-.5,.78],[-.43,1],[.19,1],[.36,.44],[.5,.42]], true);
    else if (part.shape === 'cone') radial(m, w, h, d, [[-.5,.15],[.5,1]], true);
    else if (part.shape === 'ring') radial(m, w, h, d, [[-.5,1],[.5,1],[.5,.72],[-.5,.72],[-.5,1]], true);
    else radial(m, w, h, d, [[-.5,.92],[-.43,1],[.43,1],[.5,.92]]);
  } else {
    plate(m, w, h, d);
    if (part.shape === 'shell') {
      ring(m, rect(w * .87, h * .95, d / 2 + .1));
      for (const y of [-.37, .34]) for (const x of [-.32, .32]) circleXY(m, x * w, y * h, d / 2 + .4, Math.min(w, h) * .035);
      for (const x of [-.25, .25]) line(m, [x * w, -h * .35, -d / 2], [x * w, h * .35, -d / 2]);
    }
    if (part.shape === 'keypad') {
      for (let row = 0; row < 8; row++) for (let col = 0; col < 3; col++) {
        const y = h * (.40 - row * .115), x = (col - 1) * w * .28;
        circleXY(m, x, y, d / 2 + 1, w * .087);
      }
      circleXY(m, 0, h * .03, d / 2 + 2, w * .28);
    }
    if (part.shape === 'board') {
      for (let k = 0; k < 18; k++) {
        const x = ((k * 7 % 17) / 17 - .5) * w * .84;
        const y = ((k * 11 % 19) / 19 - .5) * h * .85;
        const end: Vec3 = [x + (k % 2 ? -1 : 1) * w * .13, y + h * .065, d / 2 + .2];
        line(m, [x, y, d / 2 + .2], [x, end[1], end[2]]); line(m, [x, end[1], end[2]], end);
      }
      plate(m, w * .43, Math.min(h * .17, w * .48), 1.8, 0, h * .10, d / 2 + 1.3);
      for (let k = 0; k < 5; k++) plate(m, w * .12, h * .045, 1.2, (k % 2 ? 1 : -1) * w * .3, h * (.30 - k * .13), d / 2 + 1);
    }
  }
  return m;
}
function rotate(v: Vec3, yaw: number, pitch: number): Vec3 {
  const x = v[0] * Math.cos(yaw) + v[2] * Math.sin(yaw);
  const z = -v[0] * Math.sin(yaw) + v[2] * Math.cos(yaw);
  return [x, v[1] * Math.cos(pitch) - z * Math.sin(pitch), v[1] * Math.sin(pitch) + z * Math.cos(pitch)];
}
export function coverBox(box: Box, vw: number, vh: number, w: number, h: number): Box {
  const s = Math.max(w / vw, h / vh);
  return [(box[0] * vw * s + (w - vw * s) / 2) / w,
    (box[1] * vh * s + (h - vh * s) / 2) / h, box[2] * vw * s / w, box[3] * vh * s / h];
}

export class ExplodedScene {
  private meshes: Mesh[];
  private hits: Hit[] = [];
  constructor(public manifest: Manifest) { this.meshes = manifest.parts.map(geometry); }
  hit(x: number, y: number): string | null {
    const hit = [...this.hits].sort((a,b) => b.depth - a.depth).find(({ bounds: [l,t,r,b] }) => x >= l && x <= r && y >= t && y <= b);
    return hit?.key || null;
  }
  draw(ctx: CanvasRenderingContext2D, w: number, h: number, opts: {
    box: Box; progress: number; yaw: number; pitch: number; selected: string; time: number; opacity?: number;
  }) {
    const { box, progress, yaw, pitch, selected, time } = opts;
    const generated = this.meshes.map((m, i) => {
      const part = this.manifest.parts[i];
      const move = part.assembled.map((v,j) => v + (part.exploded[j] - v) * progress) as Vec3;
      const transform = (v: Vec3) => rotate(v.map((n,j) => n + move[j]) as Vec3, yaw, pitch);
      return { m, part, verts: m.v.map(transform), dots: m.dots.map(transform), center: rotate(move, yaw, pitch), index: i };
    });
    const vertices = generated.flatMap(p => p.verts);
    if (!vertices.length) return;
    const minX = Math.min(...vertices.map(v => v[0])), maxX = Math.max(...vertices.map(v => v[0]));
    const minY = Math.min(...vertices.map(v => v[1])), maxY = Math.max(...vertices.map(v => v[1]));
    const sceneW = maxX-minX || 1, sceneH = maxY-minY || 1;
    const targetH = Math.max(h * .25, Math.min(h * .68, box[3] * h));
    const s = Math.min(w * .90 / sceneW, targetH / sceneH);
    const cx = Math.max(w * .5 * progress, Math.min(w * (1 - .5 * progress), (box[0] + box[2] / 2) * w));
    const cy = Math.max(h * .24, Math.min(h * .66, (box[1] + box[3] / 2) * h));
    const project = (v: Vec3): Point => [cx + (v[0] - (minX+maxX)/2) * s, cy - (v[1] - (minY+maxY)/2) * s];
    this.hits = [];
    ctx.save(); ctx.globalAlpha = opts.opacity ?? 1;
    // Quiet technical rings; all displayed counts come from the manifest.
    ctx.strokeStyle = 'rgba(92,227,244,.12)'; ctx.lineWidth = 1;
    for (const r of [1, 1.17]) { ctx.beginPath(); ctx.ellipse(cx, cy, Math.min(w*.45,sceneW*s*.56)*r, sceneH*s*.56*r, -.06, .13 + time*.00002, Math.PI*1.92 + time*.00002); ctx.stroke(); }
    generated.sort((a,b) => a.center[2] - b.center[2]).forEach(({ m, part, verts, dots, center, index }) => {
      const projected = verts.map(project), active = part.key === selected;
      const color = active ? '#ffb16e' : '#86e7ee';
      for (const face of m.faces) {
        ctx.beginPath(); face.forEach((vi, j) => { const p = projected[vi]; if (j) ctx.lineTo(...p); else ctx.moveTo(...p); });
        ctx.closePath(); ctx.fillStyle = active ? 'rgba(60,33,12,.52)' : 'rgba(2,27,32,.61)'; ctx.fill();
      }
      ctx.strokeStyle = color; ctx.lineWidth = active ? 1.05 : .70;
      ctx.shadowColor = color; ctx.shadowBlur = active ? 6 : 2;
      ctx.beginPath(); for (const [a,b] of m.e) { ctx.moveTo(...projected[a]); ctx.lineTo(...projected[b]); } ctx.stroke();
      ctx.shadowBlur = 0; ctx.fillStyle = active ? '#ffd0a1' : '#adeff5';
      dots.forEach((v, j) => { if (j % 3) return; const [x,y] = project(v); ctx.globalAlpha = (opts.opacity ?? 1) * (.28 + .42 * ((j * 13 % 11) / 11)); ctx.fillRect(x, y, 1.25, 1.25); });
      ctx.globalAlpha = opts.opacity ?? 1;
      const left = Math.min(...projected.map(p => p[0])), right = Math.max(...projected.map(p => p[0]));
      const top = Math.min(...projected.map(p => p[1])), bottom = Math.max(...projected.map(p => p[1]));
      this.hits.push({ key: part.key, bounds: [left-7,top-7,right+7,bottom+7], depth: center[2] });
      if (progress > .6) {
        const [x,y] = project(center); const endY = Math.min(h-32, bottom + 18 + index % 2 * 15);
        ctx.strokeStyle = active ? '#ffb16e' : 'rgba(134,231,238,.45)';
        ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(x,endY); ctx.lineTo(x+12,endY); ctx.stroke();
        ctx.font = '11px monospace'; ctx.fillStyle = color;
        ctx.fillText(String(index+1).padStart(2,'0'), x+15, endY+4);
      }
    });
    ctx.restore();
  }
}
