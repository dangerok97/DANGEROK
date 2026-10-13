/** Reproject the detector's box from its frozen source crop to the camera
 * rectangle that is CURRENTLY visible. This is 2D anchoring, not pose tracking. */
import type {Box} from './scene';
import type {Crop} from './cameraControls';
export type AnatomyCaptureAnchor={box:Box;sourceWidth:number;sourceHeight:number;
 capturedCrop:Crop;photo:boolean;zoom:number};
export function projectAnatomyAnchor(source:AnatomyCaptureAnchor,viewCrop:Crop):Box|null{
 const {box,capturedCrop}=source;
 if(box.length!==4||box.some(n=>!Number.isFinite(n))||
  [capturedCrop.x,capturedCrop.y,capturedCrop.width,capturedCrop.height,
   viewCrop.x,viewCrop.y,viewCrop.width,viewCrop.height].some(n=>!Number.isFinite(n))||
  capturedCrop.width<=0||capturedCrop.height<=0||viewCrop.width<=0||viewCrop.height<=0)return null;
 const x=(capturedCrop.x+box[0]*capturedCrop.width-viewCrop.x)/viewCrop.width;
 const y=(capturedCrop.y+box[1]*capturedCrop.height-viewCrop.y)/viewCrop.height;
 const width=box[2]*capturedCrop.width/viewCrop.width;
 const height=box[3]*capturedCrop.height/viewCrop.height;
 const left=Math.max(0,x),top=Math.max(0,y);
 const right=Math.min(1,x+width),bottom=Math.min(1,y+height);
 return right-left>.04&&bottom-top>.04?[left,top,right-left,bottom-top]:null;
}
export function sameAnatomyAnchor(a:Box|null,b:Box|null,tolerance=.001):boolean{
 return a===b||(a!==null&&b!==null&&a.length===4&&b.length===4&&
  a.every((n,i)=>Math.abs(n-b[i])<=tolerance));
}
