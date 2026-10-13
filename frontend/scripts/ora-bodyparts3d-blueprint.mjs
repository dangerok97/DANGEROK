/**
 * ORA Blueprint adaptation for a pinned BodyParts3D viewer.
 * The original meshes, labels, source indexes, hit-testing and FMA IDs remain
 * unchanged. Only the shading and bounded edge outlines are altered.
 */
function replaceOne(source,from,to){
 if(!source.includes(from))throw new Error('BodyParts3D renderer drift: '+from.slice(0,90));
 return source.replace(from,to);
}
export function applyOraBlueprint(source){
 let scene=source;
 scene=replaceOne(scene,
  'scene.add(new T.HemisphereLight(0xffffff,0xa7acb2,1.05));',
  'scene.add(new T.HemisphereLight(0xe4faff,0x234c62,1.10));');
 scene=replaceOne(scene,
  'const key=new T.DirectionalLight(0xfffaf4,2.3);',
  'const key=new T.DirectionalLight(0xb6edff,2.05);');
 scene=replaceOne(scene,
  'const rim=new T.DirectionalLight(0xe9f0ff,1.8);',
  'const rim=new T.DirectionalLight(0x73dcff,2.15);');
 scene=replaceOne(scene,
  'const markerMaterial=new T.PointsMaterial({color:0x64748b,size:5,sizeAttenuation:false,transparent:true,opacity:.72,depthTest:false});',
  'const markerMaterial=new T.PointsMaterial({color:0x55cdef,size:3,sizeAttenuation:false,transparent:true,opacity:.38,depthTest:false});');
 const systemColor=[
  "  // Low-chroma satin surfaces match the cyan wireframe of ORA object explosions.",
  "  const technicalColor=(system:string):string=>({",
  "   skeletal:'#bfd6df',muscular:'#95b3c0',arterial:'#a3c4d0',",
  "   venous:'#87b0c1',nervous:'#aed0dc',digestive:'#a8bfca',",
  "   respiratory:'#a1c6d2',urinary:'#a0bac7',cardiac:'#a9c3cf',",
  "   sensory:'#b6d1dc',endocrine:'#a4bec9',lymphatic:'#95bdc9',",
  "   connective:'#aabfcc',reproductive:'#a3c0cc',integumentary:'#acc8d3'",
  "  } as Record<string,string>)[system]??'#a7c5d1';",
  "  const materialFor=(system:string)=>{"
 ].join('\n');
 scene=replaceOne(scene,'const materialFor=(system:string)=>{',systemColor);
 scene=replaceOne(scene,
  "const m=new T.MeshStandardMaterial({color:SYSTEMS.find(s=>s.id===system)?.color??'#aebbb8',metalness:.08,roughness:.53,side:T.DoubleSide,transparent:system==='integumentary',opacity:system==='integumentary'?.1:1,depthWrite:system!=='integumentary'});",
  "const m=new T.MeshStandardMaterial({color:technicalColor(system),metalness:.18,roughness:.45,side:T.DoubleSide,transparent:system==='integumentary'||oraInline,opacity:system==='integumentary'?.10:oraInline?.88:1,depthWrite:system!=='integumentary'});");
 scene=replaceOne(scene,
  "vec3(0.42, 0.85, 0.78), partSelected * 0.75",
  "vec3(0.47, 0.88, 1.00), partSelected * 0.72");
 const rimShader=[
  "float oraRim = pow(1.0 - abs(dot(normalize(normal), normalize(vViewPosition))), 2.1);",
  "float oraEdgeStrength = 0.56 + 0.32 * partSelected;",
  "gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.25, 0.76, 0.99), clamp(oraRim * oraEdgeStrength, 0.0, 0.94));",
  "#include <dithering_fragment>"
 ].join('\n');
 const shaderInjection="shader.fragmentShader=shader.fragmentShader.replace('#include <dithering_fragment>',"+
  JSON.stringify(rimShader)+");";
 scene=replaceOne(scene,'   };materials.push(m);return m;',
   '    '+shaderInjection+'\n   };materials.push(m);return m;');
 const outlines=[
  '  // Build true outline geometry only for meshes on the current exploded page.',
  '  // Full body contains 2,234 parts: never outline all of them in WebGL.',
  '  const blueprintEdges=new Map<number,T.LineSegments>();',
  '  const activeBlueprintEdges=new Set<number>();',
  '  const EDGE_LIMIT=20,EDGE_CACHE_LIMIT=42;',
  '  const syncBlueprintEdges=(s:SceneState,amount:number)=>{',
  '   const relevant:number[]=[],selectedIds=new Set(s.selected);',
  '   for(let i=0;i<atlas.parts.length;i++){',
  '    if(data[i*4+3]<.5||!pickers[i])continue;',
  '    if(amount>.45||selectedIds.has(atlas.parts[i].id))relevant.push(i);',
  '   }',
  '   relevant.sort((a,b)=>Number(selectedIds.has(atlas.parts[b].id))-Number(selectedIds.has(atlas.parts[a].id)));',
  '   const displayed=new Set(relevant.slice(0,EDGE_LIMIT));',
  '   for(const [i,line] of blueprintEdges){',
  '    line.visible=displayed.has(i);',
  '    if(!line.visible)continue;',
  '    line.position.copy(pickers[i]!.position);',
  '    const selected=selectedIds.has(atlas.parts[i].id);',
  '    const material=line.material as T.LineBasicMaterial;',
  '    material.color.set(selected?0xc5f7ff:0x55d1ff);',
  '    material.opacity=selected?.98:.80;',
  '   }',
  '   activeBlueprintEdges.clear();',
  '   for(const i of displayed){',
  '    activeBlueprintEdges.add(i);',
  '    if(blueprintEdges.has(i))continue;',
  '    const mesh=pickers[i];if(!mesh)continue;',
  '    const geometry=new T.EdgesGeometry(mesh.geometry,32);',
  '    const selected=selectedIds.has(atlas.parts[i].id);',
  '    const material=new T.LineBasicMaterial({color:selected?0xc5f7ff:0x55d1ff,',
  '     transparent:true,opacity:selected?.98:.80,depthWrite:false,depthTest:true,toneMapped:false});',
  '    const line=new T.LineSegments(geometry,material);',
  '    line.position.copy(mesh.position);line.frustumCulled=false;line.renderOrder=3;',
  '    scene.add(line);blueprintEdges.set(i,line);',
  '   }',
  '   if(blueprintEdges.size>EDGE_CACHE_LIMIT){',
  '    for(const [i,line] of blueprintEdges){',
  '     if(displayed.has(i))continue;',
  '     scene.remove(line);line.geometry.dispose();(line.material as T.Material).dispose();',
  '     blueprintEdges.delete(i);',
  '     if(blueprintEdges.size<=EDGE_LIMIT)break;',
  '    }',
  '   }',
  '  };',
  '  let loaded=0;'
 ].join('\n');
 scene=replaceOne(scene,'let loaded=0;',outlines);
 scene=replaceOne(scene,
  'partTexture.needsUpdate=true;selectionTexture.needsUpdate=true;markerGeometry.attributes.position.needsUpdate=true;lastState=s;',
  'partTexture.needsUpdate=true;selectionTexture.needsUpdate=true;markerGeometry.attributes.position.needsUpdate=true;syncBlueprintEdges(s,amount);lastState=s;');
 scene=replaceOne(scene,
  'env.dispose();partTexture.dispose();selectionTexture.dispose();markerGeometry.dispose();markerMaterial.dispose();hover.remove();',
  'blueprintEdges.forEach(line=>{scene.remove(line);line.geometry.dispose();(line.material as T.Material).dispose();});blueprintEdges.clear();env.dispose();partTexture.dispose();selectionTexture.dispose();markerGeometry.dispose();markerMaterial.dispose();hover.remove();');
 return scene;
}
