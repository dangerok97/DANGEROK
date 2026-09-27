/** The approved 3D scene. Self-contained so native uses exactly the same renderer.
 * Dots/edges are visual geometry; only domain focus is live application telemetry.
 */
export function createPresenceScene(canvas, initial, palette) {
  const ctx=canvas.getContext('2d',{alpha:false});
  if(!ctx) throw new Error('canvas_unavailable');
  let options={mode:'idle',area:null,paused:false,reduced:false,active:true,...initial};
  let mode=options.mode,width=700,height=460,pixelRatio=1;
  let visible=!document.hidden,inViewport=true,destroyed=false;
  let t=1.7,frame=0,last=0,dragging=false,dragX=0,dragY=0,dragYaw=0,dragPitch=0,inertia=0;
  let rotation=-.06,activeHub=-1;
  const camera={x:0,y:0,z:0,zoom:1};
  const cleanups=[];
  function on(target,event,fn){target.addEventListener(event,fn);cleanups.push(()=>target.removeEventListener(event,fn));}
  let seed=932761;
  function random(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;}
  const modes={idle:{name:'Presenza',message:'Sono qui.',speed:.26,strength:.30,breath:.020,light:.68},listen:{name:'Ascolto',message:'Ti ascolto.',speed:.40,strength:.56,breath:.039,light:.86},think:{name:'Elaborazione',message:'Sto collegando le informazioni.',speed:.62,strength:1,breath:.031,light:1},speak:{name:'Voce',message:'Ecco cosa ho trovato.',speed:.48,strength:.78,breath:.046,light:.93}};
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
  const points=hubs.map((h,i)=>({...h,group:i,hub:true,radius:2.4+random(),phase:random()*6.28}));
  for(let g=0;g<hubs.length;g++){
    const h=hubs[g];
    for(let j=0;j<34;j++){
      const a=random()*Math.PI*2,u=random()*2-1,r=Math.cbrt(random())*.235,s=Math.sqrt(1-u*u);
      points.push({x:h.x+Math.cos(a)*r*s,y:h.y+u*r*.80,z:h.z+Math.sin(a)*r*s,group:g,hub:false,radius:.50+random()*1.15,phase:random()*6.28});
    }
  }
  for(let j=0;j<122;j++){
    const a=random()*Math.PI*2,u=random()*2-1,r=Math.cbrt(random())*.93,s=Math.sqrt(1-u*u);
    points.push({x:Math.cos(a)*r*s,y:u*r*.91,z:Math.sin(a)*r*s*.86,group:-1,hub:false,radius:.45+random()*.85,phase:random()*6.28});
  }
  points.forEach(p=>p.distance=Math.hypot(p.x-hubs[0].x,p.y-hubs[0].y,p.z-hubs[0].z));
  const edges=[],edgeKeys=new Set();
  function addEdge(a,b,trunk=false){if(a===b)return;const key=Math.min(a,b)+':'+Math.max(a,b);if(edgeKeys.has(key))return;edgeKeys.add(key);edges.push({a,b,trunk,phase:random(),packet:random()<.12||trunk});}
  for(let i=0;i<points.length;i++){
    const p=points[i],near=[];
    for(let j=0;j<points.length;j++){if(i===j)continue;const q=points[j];near.push({j,d:(p.x-q.x)**2+(p.y-q.y)**2+(p.z-q.z)**2});}
    near.sort((a,b)=>a.d-b.d);for(let k=0;k<(p.hub?11:4);k++)addEdge(i,near[k].j);
    if(p.group>=0&&!p.hub&&i%5===0)addEdge(i,p.group);
    if(!p.hub&&i%7===0)addEdge(i,0);
    if(p.group>=0&&!p.hub&&i%3===0)addEdge(i,(p.group+3)%hubs.length);
  }
  const trunkPairs=[[0,1],[0,2],[0,3],[0,4],[0,6],[0,7],[1,3],[1,5],[1,7],[2,4],[2,6],[2,7],[3,4],[3,5],[3,7],[4,5],[4,6],[5,7],[6,7]];
  trunkPairs.forEach(([a,b])=>addEdge(a,b,true));
  const dust=Array.from({length:150},()=>({x:random(),y:random(),z:random(),phase:random()*6.28}));
  const projected=points.map(()=>({x:0,y:0,z:0,depth:0,scale:0,energy:0}));
  const sorted=points.map((_,i)=>i);
  function glow(x,y,r,power,warm=false){
    if(power<.01)return;
    const c=warm?palette.warmGlow:palette.glow;
    const grad=ctx.createRadialGradient(x,y,0,x,y,r);grad.addColorStop(0,'rgba('+c+','+(power*.8)+')');grad.addColorStop(.18,'rgba('+c+','+(power*.22)+')');grad.addColorStop(1,'rgba('+c+',0)');ctx.fillStyle=grad;ctx.fillRect(x-r,y-r,r*2,r*2);
  }
  function projectPoint(p,yaw,pitch,scale,breathing){
    const drift=p.hub?.002:.009;
    let x=(p.x+Math.sin(t*.36+p.phase)*drift)*breathing-camera.x;
    let y=(p.y+Math.cos(t*.30+p.phase)*drift)*breathing-camera.y;
    let z=(p.z+Math.sin(t*.29+p.phase)*drift)*breathing-camera.z;
    const rx=x*Math.cos(yaw)+z*Math.sin(yaw),rz=z*Math.cos(yaw)-x*Math.sin(yaw);
    const ry=y*Math.cos(pitch)-rz*Math.sin(pitch),zz=y*Math.sin(pitch)+rz*Math.cos(pitch);
    const perspective=3.8/(3.8-zz);
    return {x:width*.5+rx*scale*perspective,y:height*.515+ry*scale*perspective,z:zz,depth:Math.max(.14,Math.min(1,(zz+1.22)/2.25)),scale:perspective};
  }
  function draw(){
    const state=modes[mode];
    ctx.setTransform(pixelRatio,0,0,pixelRatio,0,0);ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;ctx.fillStyle=palette.background;ctx.fillRect(0,0,width,height);
    const atmosphere=ctx.createRadialGradient(width*.49,height*.47,0,width*.5,height*.5,Math.max(width,height)*.55);atmosphere.addColorStop(0,palette.atmosphere);atmosphere.addColorStop(.60,palette.depth);atmosphere.addColorStop(1,palette.background);ctx.fillStyle=atmosphere;ctx.fillRect(0,0,width,height);
    dust.forEach(s=>{const x=(s.x*width+Math.sin(t*.04+s.phase)*9+width)%width,y=s.y*height;ctx.fillStyle='rgba('+palette.dust+','+(.09+s.z*.22)+')';ctx.beginPath();ctx.arc(x,y,.35+s.z*.6,0,Math.PI*2);ctx.fill();});
    const active=mode==='think'||mode==='speak';
    const beatPhase=(t%1.18)/1.18;
    const beat=active&&!options.reduced&&!options.paused?(Math.exp(-Math.pow((beatPhase-.12)/.047,2))+.62*Math.exp(-Math.pow((beatPhase-.30)/.065,2))):0;
    const breathe=1+Math.sin(t*1.48)*state.breath+beat*.055;
    const scale=Math.min(width*.39,height*.43)*camera.zoom;
    const yaw=rotation+dragYaw,pitch=.06+Math.sin(t*.10)*.09+dragPitch;
    for(let i=0;i<points.length;i++){
      const p=points[i],q=projectPoint(p,yaw,pitch,scale,breathe);
      const focus=activeHub>=0?hubs[activeHub]:hubs[0];
      const distance=Math.hypot(p.x-focus.x,p.y-focus.y,p.z-focus.z);
      const phase=((t*state.speed-distance*.44)%1+1)%1;
      const wave=Math.exp(-Math.pow((phase-.10)/.095,2))*state.strength;
      q.energy=wave*.65+(p.hub?.10:0)+beat*Math.exp(-distance*2.3)*1.4;Object.assign(projected[i],q);
    }
    ctx.globalCompositeOperation='lighter';
    edges.forEach(e=>{
      const a=projected[e.a],b=projected[e.b];const depth=(a.depth+b.depth)*.5,energy=(a.energy+b.energy)*.5;
      const alpha=(.028+depth*.12+energy*.22)*(e.trunk?1.5:1)*state.light;
      const warm=activeHub>=0?(e.a===activeHub||e.b===activeHub):e.trunk&&e.a===0&&(e.b===4||e.b===1);
      ctx.strokeStyle=warm?'rgba('+palette.warmEdge+','+alpha+')':'rgba('+palette.edge+','+alpha+')';ctx.lineWidth=e.trunk?.8:.45+depth*.25;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
      if(e.packet&&mode!=='idle'){
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
      const r=p.radius*q.scale*(.64+q.depth*.38)*(1+q.energy*.28);
      const warm=activeHub>=0?p.group===activeHub:i===0||i===4;
      if(p.hub){glow(q.x,q.y,16+q.energy*19,.25+q.energy*.53,warm);glow(q.x,q.y,5+q.energy*4,.60,warm);}
      else if(q.energy>.35&&i%3===0)glow(q.x,q.y,4+q.energy*4,q.energy*.3);
      ctx.fillStyle='rgba('+(warm?palette.warmNode:palette.node)+','+Math.min(.98,bright)+')';ctx.beginPath();ctx.arc(q.x,q.y,r,0,Math.PI*2);ctx.fill();
      if(p.hub&&q.energy>.35){ctx.strokeStyle='rgba('+palette.cross+','+(q.energy*.33)+')';ctx.lineWidth=.6;ctx.beginPath();ctx.moveTo(q.x-7-q.energy*4,q.y);ctx.lineTo(q.x+7+q.energy*4,q.y);ctx.moveTo(q.x,q.y-6-q.energy*3);ctx.lineTo(q.x,q.y+6+q.energy*3);ctx.stroke();}
    }
    ctx.globalCompositeOperation='source-over';
    const occupied=[],labelIndices=activeHub>=0?[activeHub]:height<240?[0,1,5]:width<430?[0,1,2,5]:[0,1,2,3,5,6,7];
    ctx.font='500 11px ui-monospace, SFMono-Regular, Consolas, monospace';ctx.textBaseline='middle';
    labelIndices.forEach(i=>{
      const h=hubs[i],p=projected[i],tw=ctx.measureText(h.name).width;
      let x=p.x+h.dx,y=p.y+h.dy;let left=h.align==='right'?x-tw:x;
      left=Math.max(15,Math.min(width-tw-15,left));y=Math.max(55,Math.min(height-35,y));
      for(let tries=0;tries<6;tries++){if(!occupied.some(b=>left<b.x+b.w+7&&left+tw+7>b.x&&Math.abs(y-b.y)<19))break;y+=19;}
      y=Math.min(height-23,y);occupied.push({x:left,y,w:tw});
      ctx.strokeStyle='rgba('+palette.leader+',.28)';ctx.lineWidth=.65;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(h.align==='right'?left+tw+4:left-4,y);ctx.stroke();
      ctx.fillStyle=palette.labelBackground;ctx.fillRect(left-3,y-8,tw+6,16);ctx.fillStyle=i===0?palette.warmLabel:palette.label;ctx.textAlign='left';ctx.fillText(h.name,left,y);
    });
  }
  function moveCamera(dt,instant=false){
    const active=mode==='think'||mode==='speak';
    activeHub=active?hubs.findIndex(h=>h.id===options.area):-1;
    const target=activeHub>=0?hubs[activeHub]:{x:0,y:0,z:0};
    const mix=instant?1:1-Math.exp(-dt*3.2);
    for(const axis of ['x','y','z'])camera[axis]+=(target[axis]*.82-camera[axis])*mix;
    camera.zoom+=((active?(activeHub>=0?1.65:1.12):1)-camera.zoom)*mix;
  }
  function schedule(){if(!frame&&!destroyed&&!options.paused&&!options.reduced&&options.active&&visible&&inViewport)frame=requestAnimationFrame(tick);}
  function stop(){if(frame)cancelAnimationFrame(frame);frame=0;last=0;}
  function tick(now){frame=0;const dt=last?Math.min(.05,(now-last)/1000):.016;last=now;t+=dt;rotation+=dt*(mode==='idle'?.045:.012);moveCamera(dt);if(!dragging){dragYaw+=inertia;inertia*=.93;}draw();schedule();}
  function size(){const box=canvas.getBoundingClientRect();width=Math.max(1,box.width);height=Math.max(1,box.height);pixelRatio=Math.min(window.devicePixelRatio||1,1.75);canvas.width=Math.round(width*pixelRatio);canvas.height=Math.round(height*pixelRatio);draw();}
  function update(next){options={...options,...next};mode=modes[options.mode]?options.mode:'idle';moveCamera(0,options.reduced||options.paused);stop();draw();schedule();}
  on(canvas,'pointerdown',e=>{if(options.reduced||options.paused)return;dragging=true;dragX=e.clientX;dragY=e.clientY;inertia=0;canvas.setPointerCapture?.(e.pointerId);});
  on(canvas,'pointermove',e=>{if(!dragging)return;const dx=e.clientX-dragX,dy=e.clientY-dragY;dragYaw+=dx*.007;dragPitch=Math.max(-.7,Math.min(.7,dragPitch+dy*.004));inertia=dx*.0007;dragX=e.clientX;dragY=e.clientY;draw();});
  for(const name of ['pointerup','pointercancel','lostpointercapture'])on(canvas,name,()=>{dragging=false;});
  on(document,'visibilitychange',()=>{visible=!document.hidden;stop();schedule();});
  if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{inViewport=entries[0].isIntersecting;stop();schedule();},{threshold:.05});observer.observe(canvas);cleanups.push(()=>observer.disconnect());}
  if('ResizeObserver' in window){const observer=new ResizeObserver(size);observer.observe(canvas);cleanups.push(()=>observer.disconnect());}else on(window,'resize',size);
  size();update(initial);
  return {update,destroy(){destroyed=true;stop();cleanups.forEach(fn=>fn());},
    // Deterministic geometry inspection, with no personal data.
    snapshot(){return {camera:{...camera},activeHub,points:points.length,edges:edges.length,frame,mode};}};
}
