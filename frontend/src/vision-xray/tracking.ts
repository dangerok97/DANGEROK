/** Foreground local 2D tracking. It does NOT claim world-anchored AR or hidden geometry. */
import type { Box } from './scene';
export type GrayFrame = { width: number; height: number; data: Float32Array };
const PW = 12, PH = 18;

export function grayFrame(image: ImageData): GrayFrame {
  const data = new Float32Array(image.width * image.height);
  for (let i = 0; i < data.length; i++) data[i] = image.data[i*4] * .299 + image.data[i*4+1] * .587 + image.data[i*4+2] * .114;
  return { width: image.width, height: image.height, data };
}
function patch(frame: GrayFrame, box: Box): Float32Array | null {
  const [x,y,w,h] = box;
  if (x < 0 || y < 0 || x+w > 1 || y+h > 1 || w < .025 || h < .025) return null;
  const values = new Float32Array(PW*PH); let sum = 0;
  for (let j = 0; j < PH; j++) for (let i = 0; i < PW; i++) {
    const fx = Math.max(0, Math.min(frame.width-1, (x+(i+.5)/PW*w)*frame.width));
    const fy = Math.max(0, Math.min(frame.height-1, (y+(j+.5)/PH*h)*frame.height));
    const x0=Math.floor(fx), y0=Math.floor(fy), x1=Math.min(x0+1,frame.width-1), y1=Math.min(y0+1,frame.height-1);
    const dx=fx-x0, dy=fy-y0;
    const top=frame.data[y0*frame.width+x0]*(1-dx)+frame.data[y0*frame.width+x1]*dx;
    const bottom=frame.data[y1*frame.width+x0]*(1-dx)+frame.data[y1*frame.width+x1]*dx;
    const value=top*(1-dy)+bottom*dy; values[j*PW+i] = value; sum += value;
  }
  const mean = sum/values.length; let sq = 0;
  for (let i = 0; i < values.length; i++) { values[i] -= mean; sq += values[i]**2; }
  // A uniform wall cannot serve as a meaningful object anchor.
  if (sq / values.length < 12) return null;
  const length = Math.sqrt(sq); for (let i = 0; i < values.length; i++) values[i] /= length;
  return values;
}
export class ObjectTracker {
  private template: Float32Array | null;
  public box: Box;
  public score = 0;
  public visible = false;
  private first = true;
  constructor(reference: GrayFrame, box: Box) { this.template = patch(reference, box); this.box = box; }
  update(frame: GrayFrame): { box: Box; visible: boolean; score: number } {
    if (!this.template) return { box: this.box, visible: false, score: 0 };
    const [x,y,w,h] = this.box, cx = x+w/2, cy = y+h/2;
    let best = -1, bestBox = this.box;
    const search = (radius: number, stepX: number, stepY = stepX) => {
      for (const scale of [1, .94, 1.06]) for (let ix = -radius; ix <= radius; ix++) for (let iy = -radius; iy <= radius; iy++) {
        const box: Box = [cx+ix*stepX-w*scale/2,cy+iy*stepY-h*scale/2,w*scale,h*scale];
        const current = patch(frame, box); if (!current) continue;
        let dot = 0; for (let i = 0; i < current.length; i++) dot += current[i]*this.template![i];
        if (dot > best) { best = dot; bestBox = box; }
      }
    };
    search(6, 1 / frame.width, 1 / frame.height);
    // A server answer refers to its capture, not necessarily the latest frame.
    if (this.first && best < .7) search(4, .06);
    this.first = false; this.score = best; this.visible = best >= .60;
    if (this.visible) this.box = bestBox;
    return { box: this.box, visible: this.visible, score: best };
  }
}
