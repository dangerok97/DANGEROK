import type {CatalogEntry} from './catalogApi';
const normalize=(s:string)=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[_-]/g,' ');
export function filterCatalog(entries:CatalogEntry[],query:string,category='Tutti'):CatalogEntry[]{
  const words=normalize(query).trim().split(/\s+/).filter(Boolean);
  return entries.filter(entry=>{
    if(category!=='Tutti'&&(entry.category||'Altri oggetti')!==category)return false;
    const text=normalize([entry.title,entry.canonical_key,entry.category||'',...(entry.aliases||[])].join(' '));
    return words.every(word=>text.includes(word));
  });
}
