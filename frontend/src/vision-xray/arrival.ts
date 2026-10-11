/** A brief acquisition-to-study transition, NOT silhouette segmentation or AR.
 * Revalidate the captured bounding box against one current frame before animating
 * at that position. A moved/unrecognisable target safely falls back to the centre.
 */
import {coverBox,type Box} from './scene';
import {ObjectTracker,type GrayFrame} from './tracking';
export const ARRIVAL_MS=1600;
export const smooth=(n:number)=>{const t=Math.min(1,Math.max(0,n));return t*t*(3-2*t);};
export function arrivalAt(ms:number,reduced=false){
  const elapsed=Number.isFinite(ms)?Math.max(0,ms):ARRIVAL_MS;
  if(reduced||elapsed>=ARRIVAL_MS)return {active:false,mix:1,progress:1};
  return {active:true,mix:smooth((elapsed-220)/1080),progress:smooth((elapsed-480)/1120)};
}
export function currentBox(reference:GrayFrame|null,current:GrayFrame|null,box?:Box):Box|null{
  if(!reference||!current||!box||box.length!==4||box.some(n=>!Number.isFinite(n)))return null;
  if(reference.width!==current.width||reference.height!==current.height)return null;
  const tracker=new ObjectTracker(reference,box),match=tracker.update(current);
  return match.visible&&match.score>=.72?match.box:null;
}
export function originInView(box:Box,sw:number,sh:number,w:number,h:number):Box|null{
  if([sw,sh,w,h].some(n=>!Number.isFinite(n)||n<=0))return null;
  const mapped=coverBox(box,sw,sh,w,h);
  const x=Math.max(0,mapped[0]),y=Math.max(0,mapped[1]);
  const right=Math.min(1,mapped[0]+mapped[2]),bottom=Math.min(1,mapped[1]+mapped[3]);
  return right-x>.04&&bottom-y>.04?[x,y,right-x,bottom-y]:null;
}
