/** Simple deterministic pagination for crowded exploded object schematics.
 * It changes only which already-versioned parts are drawn; no AI, new meshes,
 * photos or cached personal data. Part IDs and catalog order are untouched. */
export const OBJECT_PARTS_PER_PAGE=6;
export type ObjectPage={page:number;pages:number;keys:string[];from:number;to:number;count:number};
export function objectPage(parts:readonly {key:string}[],requested:number,pageSize=OBJECT_PARTS_PER_PAGE):ObjectPage{
 const count=parts.length,size=Math.max(1,Math.min(12,Math.floor(pageSize)||OBJECT_PARTS_PER_PAGE));
 const pages=Math.max(1,Math.ceil(count/size));
 const page=Number.isFinite(requested)?Math.max(0,Math.min(pages-1,Math.floor(requested))):0;
 const from=page*size,to=Math.min(count,from+size);
 return {page,pages,keys:parts.slice(from,to).map(p=>p.key),from,to,count};
}
