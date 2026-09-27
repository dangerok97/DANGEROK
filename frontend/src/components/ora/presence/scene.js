/** The approved 3D scene. Self-contained so native uses exactly the same renderer.
 * Each knowledge star is a saved information ID. Hubs and edges are navigation geometry.
 */
export function createPresenceScene(canvas, initial, palette, events={}) {
  const ctx=canvas.getContext('2d',{alpha:false});
  if(!ctx) throw new Error('canvas_unavailable');
  let options={mode:'idle',area:null,paused:false,reduced:false,active:true,selectedIndex:null,resetKey:0,...initial};
  let mode=options.mode,width=700,height=460,pixelRatio=1;
  let visible=!document.hidden,inViewport=true,destroyed=false;
  let t=1.7,frame=0,last=0,dragging=false,dragX=0,dragY=0,dragYaw=0,dragPitch=0,inertia=0;
  let rotation=-.06,activeHub=-1,hovered=-1,selected=-1;
  let pointer=null,pointerId=null,downX=0,downY=0,moved=false;
  let labels=[];
  const openingSeconds=2.8;
  let opening=(options.reveal||options.revealKey)&&!options.reduced?0:openingSeconds;
  const ease=value=>{const v=Math.max(0,Math.min(1,value));return v*v*(3-2*v);};
  const camera={x:0,y:0,z:0,zoom:1};
  const cleanups=[];
  function on(target,event,fn){target.addEventListener(event,fn);cleanups.push(()=>target.removeEventListener(event,fn));}
  let seed=932761;
  function random(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;}
  const modes={idle:{name:'Presenza',message:'Sono qui.',speed:.26,strength:.30,breath:.020,light:.68},listen:{name:'Ascolto',message:'Ti ascolto.',speed:.40,strength:.56,breath:.039,light:.86},think:{name:'Elaborazione',message:'Sto collegando le informazioni.',speed:.62,strength:.82,breath:.012,light:1},speak:{name:'Voce',message:'Ecco cosa ho trovato.',speed:.48,strength:.72,breath:.018,light:.93}};
  const hubs=[
    {x:-.34,y:-.79,z:.23,id:'memory',name:'MEMORIA',dx:-14,dy:-22,align:'right'},
    {x:.49,y:-.58,z:-.30,id:'calendar',name:'IMPEGNI',dx:16,dy:-14,align:'left'},
    {x:-.73,y:-.08,z:-.04,id:'people',name:'PERSONE',dx:-19,dy:-9,align:'right'},
    {x:.39,y:.08,z:.53,id:'places',name:'LUOGHI',dx:17,dy:-10,align:'left'},
    {x:-.19,y:.56,z:.47,id:'home',name:'CASA',dx:-16,dy:27,align:'right'},
    {x:.78,y:.49,z:-.19,id:'documents',name:'DOCUMENTI',dx:14,dy:22,align:'left'},
    {x:-.55,y:.55,z:-.41,id:'finances',name:'FINANZE',dx:-14,dy:24,align:'right'},
    {x:.10,y:-.07,z:-.68,id:'calls',name:'CHIAMATE',dx:16,dy:-20,align:'left'}
  ];
  let points=[],edges=[],projected=[],sorted=[],furthest=1,geometryKey='';
  let growth=1;
  const births=new Map();
  function rebuild(nodes,first=false){
    const key=JSON.stringify(nodes||[]);if(key===geometryKey)return;geometryKey=key;
    const oldIds=new Set(points.map(p=>p.id));
    points=hubs.map((h,i)=>({...h,group:i,areaGroup:i,hub:true,radius:2.7,phase:i*.83,distance:0}));
    const groups=hubs.map(()=>[]);
    for(const node of nodes||[]){
      const g=hubs.findIndex(h=>h.id===node.area);if(g<0||!node.id)continue;
      let hash=2166136261;for(const c of node.id)hash=Math.imul(hash^c.charCodeAt(0),16777619)>>>0;
      seed=hash;
      const h=hubs[g],a=random()*Math.PI*2,u=random()*2-1,r=.10+Math.cbrt(random())*.32,v=Math.sqrt(1-u*u);
      const branch=node.kind==='branch';
      const p={x:h.x+Math.cos(a)*r*v,y:h.y+u*r*.85,z:h.z+Math.sin(a)*r*v,
        id:node.id,kind:branch?'branch':'node',tentative:!!node.tentative,complete:!!node.complete,
        group:g,areaGroup:g,hub:false,radius:branch?2.5:1.3+random()*.65,phase:random()*6.28};
      if(!births.has(p.id)||!oldIds.has(p.id))births.set(p.id,first?t-2:t);
      points.push(p);groups[g].push(points.length-1);
    }
    const liveIds=new Set(points.map(p=>p.id));for(const id of births.keys())if(!liveIds.has(id))births.delete(id);
    points.forEach(p=>p.distance=Math.hypot(p.x-hubs[0].x,p.y-hubs[0].y,p.z-hubs[0].z));
    furthest=Math.max(1,...points.map(p=>p.distance));edges=[];
    const keys=new Set();
    const add=(a,b,trunk=false)=>{const key=Math.min(a,b)+':'+Math.max(a,b);if(a===b||keys.has(key))return;keys.add(key);edges.push({a,b,trunk,phase:random(),packet:trunk||random()<.12});};
    [[0,1],[0,2],[0,3],[0,4],[0,6],[0,7],[1,3],[1,5],[1,7],[2,4],[2,6],[2,7],[3,4],[3,5],[3,7],[4,5],[4,6],[5,7],[6,7]].forEach(([a,b])=>add(a,b,true));
    groups.forEach((group,g)=>group.forEach((index,j)=>{add(index,g);for(let k=1;k<=3&&k<=j;k++)add(index,group[j-k]);if(j%4===0)add(index,(g+3)%8);}));
    projected=points.map(()=>({x:0,y:0,z:0,depth:0,scale:0,energy:0}));sorted=points.map((_,i)=>i);
    if(first)growth=.55+.45*(1-Math.exp(-(nodes||[]).filter(n=>n.kind!=='branch').length/35));
    hovered=-1;pointer=null;
  }
  rebuild(options.stars,true);
  const dust=Array.from({length:90},()=>({x:random(),y:random(),z:random(),phase:random()*6.28}));
  function nodeInfo(index){const p=points[index];return p?{index,area:hubs[p.areaGroup].id,kind:p.hub?'area':p.kind,...(p.hub?{}:{id:p.id})}:null;}
  function hitTest(x,y,touch=false){
    for(let i=labels.length-1;i>=0;i--){const b=labels[i];if(x>=b.x-4&&x<=b.x+b.w+4&&Math.abs(y-b.y)<=12)return b.index;}
    let best=-1,score=Infinity;
    projected.forEach((q,i)=>{if(q.appear<.9||q.x<0||q.x>width||q.y<0||q.y>height)return;
      const d=Math.hypot(x-q.x,y-q.y),radius=touch?22:12;
      const candidate=d-(points[i].hub?2:0)-q.depth*.3;
      if(d<=radius&&candidate<score){best=i;score=candidate;}});
    return best;
  }
  function localPointer(e){const box=canvas.getBoundingClientRect();return {x:e.clientX-(box.left||0),y:e.clientY-(box.top||0),touch:e.pointerType==='touch'};}
  function glow(x,y,r,power,warm=false){
    if(power<.01)return;
    const c=warm?palette.warmGlow:palette.glow;
    const grad=ctx.createRadialGradient(x,y,0,x,y,r);grad.addColorStop(0,'rgba('+c+','+(power*.8)+')');grad.addColorStop(.18,'rgba('+c+','+(power*.22)+')');grad.addColorStop(1,'rgba('+c+',0)');ctx.fillStyle=grad;ctx.fillRect(x-r,y-r,r*2,r*2);
  }
  function projectPoint(p,yaw,pitch,scale,breathing){
    const drift=p.hub?.002:.009;
    const born=p.hub||options.reduced||options.paused?1:ease((t-(births.get(p.id)??t))/1.35);
    const spread=ease(opening/openingSeconds)*growth;
    const h=hubs[p.group];
    const px=p.hub?p.x:h.x+(p.x-h.x)*born,py=p.hub?p.y:h.y+(p.y-h.y)*born,pz=p.hub?p.z:h.z+(p.z-h.z)*born;
    let x=(px+Math.sin(t*.36+p.phase)*drift)*breathing*spread-camera.x;
    let y=(py+Math.cos(t*.30+p.phase)*drift)*breathing*spread-camera.y;
    let z=(pz+Math.sin(t*.29+p.phase)*drift)*breathing*spread-camera.z;
    const rx=x*Math.cos(yaw)+z*Math.sin(yaw),rz=z*Math.cos(yaw)-x*Math.sin(yaw);
    const ry=y*Math.cos(pitch)-rz*Math.sin(pitch),zz=y*Math.sin(pitch)+rz*Math.cos(pitch);
    const perspective=3.8/(3.8-zz);
    return {x:width*.5+rx*scale*perspective,y:height*(options.centerY??.515)+ry*scale*perspective,z:zz,depth:Math.max(.14,Math.min(1,(zz+1.22)/2.25)),scale:perspective};
  }
  function draw(){
    const state=modes[mode];
    ctx.setTransform(pixelRatio,0,0,pixelRatio,0,0);ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;ctx.fillStyle=palette.background;ctx.fillRect(0,0,width,height);
    const atmosphere=ctx.createRadialGradient(width*.49,height*.47,0,width*.5,height*.5,Math.max(width,height)*.55);atmosphere.addColorStop(0,palette.atmosphere);atmosphere.addColorStop(.60,palette.depth);atmosphere.addColorStop(1,palette.background);ctx.fillStyle=atmosphere;ctx.fillRect(0,0,width,height);
    dust.forEach(s=>{const x=(s.x*width+Math.sin(t*.04+s.phase)*9+width)%width,y=s.y*height;ctx.fillStyle='rgba('+palette.dust+','+(.09+s.z*.22)+')';ctx.beginPath();ctx.arc(x,y,.35+s.z*.6,0,Math.PI*2);ctx.fill();});
    const active=mode==='think'||mode==='speak';
    activeHub=hubs.findIndex(h=>h.id===options.area);
    // A small, broad double pulse: activity should feel alive without jolting the map.
    const beatPhase=(t%1.65)/1.65;
    const beat=active&&!options.reduced&&!options.paused?(Math.exp(-Math.pow((beatPhase-.16)/.085,2))+.38*Math.exp(-Math.pow((beatPhase-.37)/.105,2))):0;
    const breathe=1+Math.sin(t*1.48)*state.breath+beat*.014;
    const scale=Math.min(width*.39,height*.43)*camera.zoom;
    const yaw=rotation+dragYaw,pitch=.06+Math.sin(t*.10)*.09+dragPitch;
    for(let i=0;i<points.length;i++){
      const p=points[i],q=projectPoint(p,yaw,pitch,scale,breathe);
      q.appear=(i===0?1:ease((opening/openingSeconds-p.distance/furthest*.65-.06)/.29))*(p.hub||options.reduced||options.paused?1:ease((t-(births.get(p.id)??t))/1.35));
      const focus=activeHub>=0?hubs[activeHub]:hubs[0];
      const distance=Math.hypot(p.x-focus.x,p.y-focus.y,p.z-focus.z);
      const phase=((t*state.speed-distance*.44)%1+1)%1;
      const wave=Math.exp(-Math.pow((phase-.10)/.095,2))*state.strength;
      q.energy=wave*.65+(p.hub?.10:0)+beat*Math.exp(-distance*2.3)*.42;Object.assign(projected[i],q);
    }
    if(pointer&&!dragging)hovered=hitTest(pointer.x,pointer.y,pointer.touch);
    const inspected=hovered>=0?hovered:selected;
    if(canvas.style)canvas.style.cursor=dragging?'grabbing':hovered>=0?'pointer':'grab';
    ctx.globalCompositeOperation='lighter';
    edges.forEach(e=>{
      const a=projected[e.a],b=projected[e.b];const depth=(a.depth+b.depth)*.5,energy=(a.energy+b.energy)*.5;
      const appear=Math.min(a.appear,b.appear);
      if(appear<.005)return;
      ctx.globalAlpha=appear;
      const related=inspected>=0&&(e.a===inspected||e.b===inspected);
      const alpha=Math.min(.9,(.028+depth*.12+energy*.22)*(e.trunk?1.5:1)*state.light+(related?.45:0));
      const warm=activeHub>=0?(e.a===activeHub||e.b===activeHub):e.trunk&&e.a===0&&(e.b===4||e.b===1);
      const first=points[e.a].distance<=points[e.b].distance?a:b,second=first===a?b:a;
      ctx.strokeStyle=warm?'rgba('+palette.warmEdge+','+alpha+')':'rgba('+palette.edge+','+alpha+')';ctx.lineWidth=related?1.45:e.trunk?.8:.45+depth*.25;ctx.beginPath();ctx.moveTo(first.x,first.y);ctx.lineTo(first.x+(second.x-first.x)*appear,first.y+(second.y-first.y)*appear);ctx.stroke();
      if(e.packet&&mode!=='idle'&&appear===1){
        const u=(t*(e.trunk?.34:.19)*state.speed+e.phase)%1;const strength=Math.sin(u*Math.PI)*(.25+energy*.85)*state.light;
        const px=a.x+(b.x-a.x)*u,py=a.y+(b.y-a.y)*u;
        const u0=Math.max(0,u-.09);
        const grad=ctx.createLinearGradient(a.x+(b.x-a.x)*u0,a.y+(b.y-a.y)*u0,px,py);grad.addColorStop(0,'rgba('+palette.trail+',0)');grad.addColorStop(1,warm?'rgba('+palette.warmPacket+','+strength+')':'rgba('+palette.packet+','+strength+')');
        ctx.strokeStyle=grad;ctx.lineWidth=e.trunk?1.8:1;ctx.beginPath();ctx.moveTo(a.x+(b.x-a.x)*u0,a.y+(b.y-a.y)*u0);ctx.lineTo(px,py);ctx.stroke();
        if(e.trunk){glow(px,py,7,strength*.35,warm);ctx.fillStyle=warm?'rgba('+palette.warmPoint+','+strength+')':'rgba('+palette.point+','+strength+')';ctx.beginPath();ctx.arc(px,py,.85+a.depth*.3,0,Math.PI*2);ctx.fill();}
      }
    });
    sorted.sort((a,b)=>projected[a].z-projected[b].z);
    for(const i of sorted){
      const p=points[i],q=projected[i],bright=(.19+q.depth*.64+q.energy*.32)*state.light;
      if(q.appear<.005)continue;
      ctx.globalAlpha=q.appear;
      const isInspected=i===inspected;
      const r=p.radius*q.scale*(.64+q.depth*.38)*(1+q.energy*.28)+(isInspected?2.8:0);
      if(isInspected){glow(q.x,q.y,24,.95);ctx.strokeStyle=palette.label;ctx.lineWidth=1;ctx.beginPath();ctx.arc(q.x,q.y,9,0,Math.PI*2);ctx.stroke();}
      const warm=p.complete||p.tentative||(activeHub>=0?p.group===activeHub:i===0||i===4);
      if(p.hub){glow(q.x,q.y,16+q.energy*19,.25+q.energy*.53,warm);glow(q.x,q.y,5+q.energy*4,.60,warm);}
      else {glow(q.x,q.y,p.complete?17:8,.22+q.energy*.3,warm);}
      if(p.kind==='branch'){ctx.strokeStyle='rgba('+palette.warmNode+','+(p.complete?.85:.2)+')';ctx.lineWidth=p.complete?1.5:.6;ctx.beginPath();ctx.arc(q.x,q.y,6,0,Math.PI*2);ctx.stroke();}
      if(!p.hub&&p.kind==='node'&&!p.tentative){ctx.strokeStyle='rgba('+palette.point+','+(.3+q.energy*.3)+')';ctx.lineWidth=.7;ctx.beginPath();ctx.moveTo(q.x-3.6,q.y);ctx.lineTo(q.x+3.6,q.y);ctx.moveTo(q.x,q.y-3.6);ctx.lineTo(q.x,q.y+3.6);ctx.stroke();}
      ctx.fillStyle='rgba('+(warm?palette.warmNode:palette.node)+','+Math.min(.98,bright)+')';ctx.beginPath();ctx.arc(q.x,q.y,r,0,Math.PI*2);ctx.fill();
      if(p.hub&&q.energy>.35){ctx.strokeStyle='rgba('+palette.cross+','+(q.energy*.33)+')';ctx.lineWidth=.6;ctx.beginPath();ctx.moveTo(q.x-7-q.energy*4,q.y);ctx.lineTo(q.x+7+q.energy*4,q.y);ctx.moveTo(q.x,q.y-6-q.energy*3);ctx.lineTo(q.x,q.y+6+q.energy*3);ctx.stroke();}
    }
    ctx.globalCompositeOperation='source-over';
    ctx.globalAlpha=ease((opening/openingSeconds-.68)/.32);
    const occupied=[],labelIndices=activeHub>=0?[activeHub]:height<180?[0,1,5]:width<430?[0,1,2,5]:[0,1,2,3,4,5,6,7];
    if(inspected>=0&&!labelIndices.includes(points[inspected].areaGroup))labelIndices.push(points[inspected].areaGroup);
    labels=[];
    ctx.font='500 11px ui-monospace, SFMono-Regular, Consolas, monospace';ctx.textBaseline='middle';
    labelIndices.forEach(i=>{
      const h=hubs[i],p=projected[i],tw=ctx.measureText(h.name).width;
      if(p.appear<.99||opening/openingSeconds<.72)return;
      if(p.x<0||p.x>width||p.y<0||p.y>height)return;
      let x=p.x+h.dx,y=p.y+h.dy;let left=h.align==='right'?x-tw:x;
      left=Math.max(15,Math.min(width-tw-15,left));y=Math.max(18,Math.min(height-20,y));
      for(let tries=0;tries<6;tries++){if(!occupied.some(b=>left<b.x+b.w+7&&left+tw+7>b.x&&Math.abs(y-b.y)<19))break;y+=19;}
      y=Math.min(height-23,y);occupied.push({x:left,y,w:tw});labels.push({x:left,y,w:tw,index:i});
      ctx.strokeStyle='rgba('+palette.leader+',.28)';ctx.lineWidth=.65;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(h.align==='right'?left+tw+4:left-4,y);ctx.stroke();
      ctx.fillStyle=palette.labelBackground;ctx.fillRect(left-3,y-8,tw+6,16);ctx.fillStyle=i===0?palette.warmLabel:palette.label;ctx.textAlign='left';ctx.fillText(h.name,left,y);
    });
  }
  function moveCamera(dt,instant=false){
    const active=mode==='think'||mode==='speak';
    activeHub=hubs.findIndex(h=>h.id===options.area);
    const target=activeHub>=0?hubs[activeHub]:{x:0,y:0,z:0};
    const mix=instant?1:1-Math.exp(-dt*3.2);
    for(const axis of ['x','y','z'])camera[axis]+=(target[axis]*.82*growth-camera[axis])*mix;
    camera.zoom+=((activeHub>=0?1.65:active?1.12:1)-camera.zoom)*mix;
  }
  function schedule(){if(!frame&&!destroyed&&!options.paused&&!options.reduced&&options.active&&visible&&inViewport)frame=requestAnimationFrame(tick);}
  function stop(){if(frame)cancelAnimationFrame(frame);frame=0;last=0;}
  function tick(now){
    frame=0;const dt=last?Math.min(.05,(now-last)/1000):.016;last=now;
    opening=Math.min(openingSeconds,opening+dt);
    const targetGrowth=.55+.45*(1-Math.exp(-points.filter(p=>p.kind==='node').length/35));
    growth+=(targetGrowth-growth)*(1-Math.exp(-dt*2));
    // Inspecting a point holds it still so a click can reliably reach it.
    if(!dragging&&hovered<0&&selected<0){t+=dt;rotation+=dt*(mode==='idle'?.045:.012);if(opening===openingSeconds)moveCamera(dt);dragYaw+=inertia;inertia*=.93;}
    draw();schedule();
  }
  function size(){const box=canvas.getBoundingClientRect();width=Math.max(1,box.width);height=Math.max(1,box.height);pixelRatio=Math.min(window.devicePixelRatio||1,1.75);canvas.width=Math.round(width*pixelRatio);canvas.height=Math.round(height*pixelRatio);draw();}
  function update(next){
    const reveal=next.revealKey&&next.revealKey!==options.revealKey;
    const reset=next.resetKey!==undefined&&next.resetKey!==options.resetKey;
    options={...options,...next};mode=modes[options.mode]?options.mode:'idle';
    rebuild(options.stars);
    if(options.reduced||options.paused)growth=.55+.45*(1-Math.exp(-points.filter(p=>p.kind==='node').length/35));
    // The first user turn triggers the entrance without delaying the actual work.
    if(reveal){opening=0;camera.x=0;camera.y=0;camera.z=0;camera.zoom=1;hovered=-1;pointer=null;}
    if(options.reduced||options.paused)opening=openingSeconds;
    selected=Number.isInteger(options.selectedIndex)&&points[options.selectedIndex]?options.selectedIndex:-1;
    if(reset){rotation=-.06;dragYaw=0;dragPitch=0;inertia=0;hovered=-1;pointer=null;camera.x=0;camera.y=0;camera.z=0;camera.zoom=1;}
    if(!options.paused&&options.reduced)moveCamera(0,true);
    stop();draw();schedule();
  }
  on(canvas,'pointerdown',e=>{
    if(e.button!==undefined&&e.button!==0||pointerId!==null)return;
    opening=openingSeconds;draw();
    pointerId=e.pointerId;pointer=localPointer(e);downX=dragX=e.clientX;downY=dragY=e.clientY;
    moved=false;dragging=false;inertia=0;hovered=hitTest(pointer.x,pointer.y,pointer.touch);
    canvas.setPointerCapture?.(e.pointerId);draw();
  });
  on(canvas,'pointermove',e=>{
    if(pointerId!==null&&e.pointerId!==pointerId)return;
    pointer=localPointer(e);
    if(pointerId!==null){
      const dx=e.clientX-dragX,dy=e.clientY-dragY;
      if(Math.hypot(e.clientX-downX,e.clientY-downY)>6)moved=true;
      if(moved){dragging=true;hovered=-1;dragYaw+=dx*.007;dragPitch=Math.max(-1.5,Math.min(1.5,dragPitch+dy*.005));}
      dragX=e.clientX;dragY=e.clientY;
    }
    draw();
  });
  function release(e,cancelled=false){
    if(pointerId===null||e.pointerId!==pointerId)return;
    const id=pointerId;pointerId=null;
    if(!cancelled&&!moved){const p=localPointer(e);selected=hitTest(p.x,p.y,p.touch);options.selectedIndex=selected;events.onSelect?.(nodeInfo(selected));}
    dragging=false;inertia=0;if(cancelled||e.pointerType==='touch'){pointer=null;hovered=-1;}
    if(canvas.hasPointerCapture?.(id))canvas.releasePointerCapture(id);
    draw();
  }
  on(canvas,'pointerup',e=>release(e));
  on(canvas,'pointercancel',e=>release(e,true));
  on(canvas,'lostpointercapture',e=>release(e,true));
  on(canvas,'pointerleave',()=>{if(pointerId===null){pointer=null;hovered=-1;draw();}});
  on(document,'visibilitychange',()=>{visible=!document.hidden;stop();schedule();});
  if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{inViewport=entries[0].isIntersecting;stop();schedule();},{threshold:.05});observer.observe(canvas);cleanups.push(()=>observer.disconnect());}
  if('ResizeObserver' in window){const observer=new ResizeObserver(size);observer.observe(canvas);cleanups.push(()=>observer.disconnect());}else on(window,'resize',size);
  size();update(initial);
  return {update,destroy(){destroyed=true;stop();cleanups.forEach(fn=>fn());},
    // Deterministic geometry inspection, with no personal data.
    snapshot(){return {camera:{...camera},rotation:{yaw:dragYaw,pitch:dragPitch},hovered,selected,activeHub,points:points.length,knowledgeStars:points.filter(p=>p.kind==='node').length,edges:edges.length,frame,mode,opening:opening/openingSeconds,visiblePoints:projected.filter(p=>p.appear>.01).length,projected:projected.map((p,i)=>({x:p.x,y:p.y,...nodeInfo(i)}))};}};
}
