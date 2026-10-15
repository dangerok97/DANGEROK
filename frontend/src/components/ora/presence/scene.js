/** ORA Brain Presence.
 * The same saved knowledge IDs, selections and focus semantics are rendered as a
 * living holographic human brain. Hubs are functional brain regions; edges are
 * neural fibres. This renderer stays self-contained so native and web are identical.
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
  // Functional regions arranged inside a lateral human-brain volume.
  // The IDs and index order are unchanged: selection, accessibility and saved
  // knowledge continue to address exactly the same eight ORA areas.
  const hubs=[
    // Spread across cortical lobes: the live knowledge graph fills the brain
    // instead of floating as a small cluster inside a decorative outline.
    {x:-.18,y:.02,z:.34,id:'memory',name:'MEMORIA',dx:-18,dy:22,align:'right'},
    {x:.60,y:-.48,z:.08,id:'calendar',name:'IMPEGNI',dx:17,dy:-18,align:'left'},
    {x:-.76,y:.01,z:.12,id:'people',name:'PERSONE',dx:-20,dy:-5,align:'right'},
    {x:.46,y:-.08,z:.54,id:'places',name:'LUOGHI',dx:18,dy:5,align:'left'},
    {x:-.38,y:-.34,z:.46,id:'home',name:'CASA',dx:-18,dy:-22,align:'right'},
    {x:.82,y:-.17,z:-.15,id:'documents',name:'DOCUMENTI',dx:16,dy:18,align:'left'},
    {x:-.60,y:-.47,z:-.16,id:'finances',name:'FINANZE',dx:-16,dy:-17,align:'right'},
    {x:.14,y:.61,z:-.06,id:'calls',name:'CHIAMATE',dx:16,dy:23,align:'left'}
  ];
  let points=[],edges=[],projected=[],sorted=[],furthest=1,geometryKey='';
  let growth=1;
  const births=new Map();
  function rebuild(nodes,first=false){
    const key=JSON.stringify([!!options.intro,nodes||[]]);if(key===geometryKey)return;geometryKey=key;
    const oldIds=new Set(points.map(p=>p.id));
    points=hubs.map((h,i)=>({...h,group:i,areaGroup:i,hub:true,radius:2.7,phase:i*.83,distance:0}));
    const groups=hubs.map(()=>[]);
    for(const node of nodes||[]){
      const g=hubs.findIndex(h=>h.id===node.area);if(g<0||!node.id)continue;
      let hash=2166136261;for(const c of node.id)hash=Math.imul(hash^c.charCodeAt(0),16777619)>>>0;
      seed=hash;
      const h=hubs[g],a=random()*Math.PI*2,u=random()*2-1,r=.14+Math.cbrt(random())*.43,v=Math.sqrt(1-u*u);
      const branch=node.kind==='branch';
      const introPosition=node.id==='intro_step_one'?[-.52,-.30,.08]:node.id==='draft_first_name'?[.28,-.65,.18]:node.id==='draft_last_name'?[.68,.30,-.12]:node.id.startsWith('intro_example_')?[-.48,.60,-.08]:null;
      const p={x:introPosition?.[0]??h.x+Math.cos(a)*r*v,y:introPosition?.[1]??h.y+u*r*.85,z:introPosition?.[2]??h.z+Math.sin(a)*r*v,
        id:node.id,kind:branch?'branch':'node',tentative:!!node.tentative,temporary:!!node.temporary,complete:!!node.complete,
        group:g,areaGroup:g,hub:false,radius:branch?2.5:1.3+random()*.65,phase:random()*6.28};
      if(!births.has(p.id)||!oldIds.has(p.id))births.set(p.id,first?t-4:t);
      points.push(p);groups[g].push(points.length-1);
    }
    const liveIds=new Set(points.map(p=>p.id));for(const id of births.keys())if(!liveIds.has(id))births.delete(id);
    points.forEach(p=>p.distance=Math.hypot(p.x-(options.intro?0:hubs[0].x),p.y-(options.intro?0:hubs[0].y),p.z-(options.intro?0:hubs[0].z)));
    furthest=Math.max(1,...points.map(p=>p.distance));edges=[];
    const keys=new Set();
    const add=(a,b,trunk=false)=>{const key=Math.min(a,b)+':'+Math.max(a,b);if(a===b||keys.has(key))return;keys.add(key);edges.push({a,b,trunk,phase:random(),packet:trunk||random()<.12});};
    if(options.intro){
      for(let i=8;i<points.length;i++){add(0,i,true);if(i>8)add(i-1,i);}
    }else{
      [[0,1],[0,2],[0,3],[0,4],[0,6],[0,7],[1,3],[1,5],[1,7],[2,4],[2,6],[2,7],[3,4],[3,5],[3,7],[4,5],[4,6],[5,7],[6,7]].forEach(([a,b])=>add(a,b,true));
      groups.forEach((group,g)=>group.forEach((index,j)=>{add(index,g);for(let k=1;k<=3&&k<=j;k++)add(index,group[j-k]);if(j%4===0)add(index,(g+3)%8);}));
    }
    projected=points.map(()=>({x:0,y:0,z:0,depth:0,scale:0,energy:0}));sorted=points.map((_,i)=>i);
    if(first)growth=.55+.45*(1-Math.exp(-(nodes||[]).filter(n=>n.kind!=='branch').length/35));
    hovered=-1;pointer=null;
  }
  rebuild(options.stars,true);
  const dust=Array.from({length:58},()=>({x:random(),y:random(),z:random(),phase:random()*6.28}));

  // Decorative cortical volume only: these points never represent personal
  // data and can never be selected. They exist to give the brain real depth
  // while the saved knowledge nodes remain the only interactive information.
  const cortexCloud=(()=>{
    let s=0x5f3759df;
    const rnd=()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296;};
    // Overlapping 3D lobes. This creates a brain volume rather than a generic
    // ellipsoid, while remaining deterministic and containing no personal data.
    const lobes=[
      [-.70,-.08,.02,.47,.40,.46],[-.43,-.30,.08,.48,.37,.47],
      [-.10,-.35,.08,.49,.36,.49],[.23,-.32,.06,.49,.37,.48],
      [.58,-.17,-.02,.42,.35,.42],[-.62,.18,-.05,.42,.33,.40],
      [-.29,.18,.09,.50,.39,.49],[.11,.19,.10,.51,.40,.51],
      [.44,.16,.02,.45,.37,.44],[-.12,.40,-.13,.34,.27,.34],
    ];
    const out=[];
    let attempts=0;
    while(out.length<224&&attempts++<10000){
      const l=lobes[Math.floor(rnd()*lobes.length)];
      const a=rnd()*Math.PI*2;
      const u=rnd()*2-1;
      const v=Math.sqrt(1-u*u);
      // Anatomy-first: most decorative points live near the cortical shell.
      // A smaller translucent interior remains, but it must never become a
      // bright central cloud that hides the gyri.
      const rr=.42+.58*Math.pow(rnd(),.22);
      const x=l[0]+Math.cos(a)*v*l[3]*rr;
      const y=l[1]+u*l[4]*rr;
      const z=l[2]+Math.sin(a)*v*l[5]*rr;
      const nx=x/1.28,ny=(y+.015)/.76,nz=z/.70;
      const envelope=nx*nx+ny*ny+nz*nz;
      const temporalCut=x<-.84&&y>.34?.14:0;
      if(envelope<1.04-temporalCut&&y<.66&&y>-.72){
        out.push({
          x,y,z,
          phase:rnd()*Math.PI*2,
          size:.42+rnd()*.78,
          hot:rnd()<.15,
          warm:rnd()<.035,
          shell:rr>.72,
          energy:.48+rnd()*.42,
        });
      }
    }
    return out;
  })();
  const cortexLinks=(()=>{
    const links=[];
    for(let i=0;i<cortexCloud.length;i++){
      const a=cortexCloud[i];
      const candidates=[];
      for(let j=i+1;j<cortexCloud.length;j++){
        const b=cortexCloud[j];
        const d=Math.hypot(a.x-b.x,(a.y-b.y)*1.15,(a.z-b.z)*1.04);
        if(d<.31)candidates.push([d,j]);
      }
      candidates.sort((u,v)=>u[0]-v[0]);
      const wanted=i%13===0?3:i%5===0?2:1;
      for(let k=0;k<Math.min(wanted,candidates.length);k++){
        links.push([i,candidates[k][1],(i*31+k*17)%47/47]);
      }
    }
    return links;
  })();
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
  function glow(x,y,r,power,warm=false,temporary=false){
    if(power<.01)return;
    const c=temporary?palette.temporaryGlow:(warm?palette.warmGlow:palette.glow);
    const grad=ctx.createRadialGradient(x,y,0,x,y,r);grad.addColorStop(0,'rgba('+c+','+(power*.8)+')');grad.addColorStop(.18,'rgba('+c+','+(power*.22)+')');grad.addColorStop(1,'rgba('+c+',0)');ctx.fillStyle=grad;ctx.fillRect(x-r,y-r,r*2,r*2);
  }
  let brainFrame={cx:0,cy:0,w:0,h:0};
  let cortexFrame={x:0,y:0,w:0,h:0};
  function brainOutline(cx,cy,w,h){
    // Lateral human-brain silhouette with deliberate lobe changes: at small
    // preview sizes this must still read as a brain, not as a generic oval.
    ctx.beginPath();
    ctx.moveTo(cx-w*.08,cy+h*.39);
    ctx.bezierCurveTo(cx-w*.22,cy+h*.43,cx-w*.44,cy+h*.34,cx-w*.51,cy+h*.20);
    ctx.bezierCurveTo(cx-w*.64,cy+h*.13,cx-w*.66,cy-h*.05,cx-w*.57,cy-h*.17);
    ctx.bezierCurveTo(cx-w*.63,cy-h*.31,cx-w*.49,cy-h*.43,cx-w*.34,cy-h*.42);
    ctx.bezierCurveTo(cx-w*.30,cy-h*.54,cx-w*.12,cy-h*.57,cx-w*.02,cy-h*.48);
    ctx.bezierCurveTo(cx+w*.10,cy-h*.58,cx+w*.28,cy-h*.53,cx+w*.32,cy-h*.42);
    ctx.bezierCurveTo(cx+w*.48,cy-h*.47,cx+w*.59,cy-h*.34,cx+w*.55,cy-h*.22);
    ctx.bezierCurveTo(cx+w*.69,cy-h*.14,cx+w*.71,cy+h*.03,cx+w*.60,cy+h*.13);
    ctx.bezierCurveTo(cx+w*.61,cy+h*.27,cx+w*.43,cy+h*.38,cx+w*.27,cy+h*.35);
    ctx.bezierCurveTo(cx+w*.17,cy+h*.43,cx+w*.02,cy+h*.43,cx-w*.08,cy+h*.39);
    ctx.closePath();
  }
  function brainPoint(cx,cy,w,h,u,v){
    return {x:cx+u*w,y:cy+v*h};
  }
  function drawBrainVolume(cx,cy,w,h,state,beat){
    // Multiple overlapping lobe glows create the glassy/volumetric hologram
    // seen in the reference instead of one flat translucent fill.
    const lobes=[
      [-.30,-.14,.34,.34,.30],[-.02,-.23,.36,.34,.35],[.28,-.18,.34,.32,.33],
      [-.39,.11,.28,.27,.25],[-.08,.09,.38,.31,.34],[.28,.08,.34,.29,.31],
      [.43,.20,.23,.22,.24],[-.22,.28,.24,.20,.21],
    ];
    for(let i=0;i<lobes.length;i++){
      const [lx,ly,rx,ry,power]=lobes[i];
      const x=cx+lx*w,y=cy+ly*h,r=Math.max(rx*w,ry*h);
      const g=ctx.createRadialGradient(x,y,0,x,y,r);
      const pulse=(i%3===0?beat*.04:0);
      g.addColorStop(0,'rgba('+palette.glow+','+(power+state.light*.045+pulse)+')');
      g.addColorStop(.45,'rgba('+palette.edge+','+(power*.46)+')');
      g.addColorStop(1,'rgba('+palette.edge+',0)');
      ctx.fillStyle=g;ctx.fillRect(x-r,y-r,r*2,r*2);
    }
  }
  function drawNeuralFibreField(cx,cy,w,h,state,beat){
    // The anatomy is always visible; the neural network wakes up only when
    // ORA is actually listening/thinking/speaking or focusing a real node.
    // At rest this stays faint so the brain does not collapse into spaghetti.
    const awake=activeHub>=0||mode==='listen'||mode==='think'||mode==='speak'||selected>=0||hovered>=0;
    const gain=awake?1:.18;
    ctx.save();
    brainOutline(cx,cy,w,h);ctx.clip();
    ctx.globalCompositeOperation='lighter';
    for(let i=0;i<28;i++){
      const a=i*2.3999632297;
      const ring=.12+(i%11)/15;
      const sx=cx+Math.cos(a)*w*ring*.62;
      const sy=cy+Math.sin(a*1.13)*h*ring*.46;
      const ex=cx+Math.cos(a+1.35)*w*(.22+(i%7)*.055);
      const ey=cy+Math.sin(a*.83+1.1)*h*(.17+(i%5)*.055);
      const mx=cx+Math.sin(a*.61)*w*.16;
      const my=cy+Math.cos(a*.77)*h*.12;
      const alpha=(.020+state.light*.026+(i%7===0?beat*.060:0))*gain;
      ctx.strokeStyle='rgba('+palette.trail+','+alpha+')';
      ctx.lineWidth=i%7===0?.78:.34;
      ctx.beginPath();ctx.moveTo(sx,sy);ctx.quadraticCurveTo(mx,my,ex,ey);ctx.stroke();
    }
    for(let i=0;i<14;i++){
      const a=i*.91;
      const x=cx+Math.cos(a)*w*(.08+(i%6)*.075);
      const y=cy+Math.sin(a*1.27)*h*(.06+(i%5)*.07);
      glow(x,y,5+(i%4)*1.5,(.060+state.light*.020+(i%5===0?beat*.10:0))*gain,i%11===0);
    }
    ctx.restore();
  }
  function drawCorticalSulci(cx,cy,w,h,state,beat){
    const alpha=.20+state.light*.11+beat*.055;
    ctx.strokeStyle='rgba('+palette.point+','+alpha+')';
    ctx.lineWidth=.78;
    const traces=[
      [-.47,-.18,-.37,-.33,-.21,-.31,-.13,-.20],
      [-.50,.02,-.38,-.09,-.22,-.04,-.13,.08],
      [-.45,.19,-.31,.08,-.18,.14,-.08,.25],
      [-.26,-.42,-.16,-.31,-.03,-.34,.06,-.23],
      [-.18,-.13,-.06,-.22,.08,-.16,.16,-.05],
      [-.18,.20,-.04,.09,.12,.14,.22,.24],
      [.05,-.42,.16,-.31,.28,-.34,.36,-.22],
      [.17,-.13,.29,-.23,.42,-.15,.48,-.03],
      [.20,.10,.34,.01,.48,.08,.53,.20],
      [.00,.34,.10,.24,.24,.28,.34,.34],
    ];
    for(const p of traces){
      ctx.beginPath();
      ctx.moveTo(cx+p[0]*w,cy+p[1]*h);
      ctx.bezierCurveTo(cx+p[2]*w,cy+p[3]*h,cx+p[4]*w,cy+p[5]*h,cx+p[6]*w,cy+p[7]*h);
      ctx.stroke();
    }
    // Secondary folds are the visual texture of the cortex — denser than the
    // neural network, but quieter and anatomically directional.
    ctx.strokeStyle='rgba('+palette.edge+','+(alpha*.56)+')';
    for(let i=0;i<15;i++){
      const x=-.47+i*.067;
      const y=-.31+((i*37)%8)*.077;
      ctx.beginPath();
      ctx.moveTo(cx+x*w,cy+y*h);
      ctx.quadraticCurveTo(cx+(x+.042)*w,cy+(y-.050+(i%2)*.090)*h,cx+(x+.085)*w,cy+(y+.012)*h);
      ctx.stroke();
    }
  }
  function drawBrainEnvelope(state,yaw,pitch,scale,beat){
    const reveal=ease(opening/openingSeconds);
    if(reveal<.01)return;
    const brainGrowth=.84+.16*growth;
    const compact=height<240;
    const w=scale*(compact?2.98:2.28)*brainGrowth;
    const h=scale*(compact?1.98:1.68)*brainGrowth;
    const cx=width*.5-camera.x*scale*.90+Math.sin(yaw)*w*.025;
    const cy=height*(options.centerY??.515)-camera.y*scale*.90+Math.sin(pitch)*h*.025;
    brainFrame={cx,cy,w,h};
    const strength=(.24+state.light*.20+beat*.18)*reveal;
    ctx.save();
    ctx.globalCompositeOperation='lighter';
    ctx.globalAlpha=reveal;

    // Volumetric hologram first, then fibres, then only a restrained rim.
    glow(cx,cy,w*.58,.10+state.light*.075+beat*.055,false);
    brainOutline(cx,cy,w,h);
    const fill=ctx.createRadialGradient(cx+w*.04,cy-h*.08,0,cx,cy,w*.64);
    fill.addColorStop(0,'rgba('+palette.glow+','+(.070+strength*.060)+')');
    fill.addColorStop(.48,'rgba('+palette.edge+','+(.032+strength*.035)+')');
    fill.addColorStop(1,'rgba('+palette.edge+',0)');
    ctx.fillStyle=fill;ctx.fill();
    drawBrainVolume(cx,cy,w,h,state,beat);
    drawNeuralFibreField(cx,cy,w,h,state,beat);
    ctx.shadowColor='rgba('+palette.glow+',.22)';
    ctx.shadowBlur=compact?2:3;
    ctx.strokeStyle='rgba('+palette.glow+','+(.010+strength*.020)+')';
    ctx.lineWidth=compact?.72:.86;brainOutline(cx,cy,w,h);ctx.stroke();
    ctx.shadowBlur=0;
    ctx.strokeStyle='rgba('+palette.point+','+(.050+strength*.075)+')';
    ctx.lineWidth=compact?.44:.48;brainOutline(cx,cy,w,h);ctx.stroke();
    ctx.shadowBlur=0;
    drawCorticalSulci(cx,cy,w,h,state,beat);

    // Central fissure gives the silhouette a recognisable human-brain anatomy.
    ctx.strokeStyle='rgba('+palette.point+','+(.060+strength*.080)+')';
    ctx.lineWidth=.48;
    ctx.beginPath();
    ctx.moveTo(cx-w*.02,cy-h*.47);
    ctx.bezierCurveTo(cx-w*.09,cy-h*.26,cx+w*.04,cy-h*.08,cx-w*.02,cy+h*.28);
    ctx.stroke();

    // Only a few broad anatomical paths remain permanently visible.
    const anatomyGain=(activeHub>=0||mode==='think'||mode==='speak')?1:.34;
    for(let i=0;i<5;i++){
      const u=(i+1)/6;
      const yy=cy-h*.43+u*h*.72;
      const span=Math.sin(Math.PI*u);
      const left=cx-w*(.48-.10*u)*span;
      const right=cx+w*(.49-.05*u)*span;
      const bend=Math.sin(i*1.73+yaw*.7)*h*.045;
      ctx.strokeStyle='rgba('+palette.edge+','+((.035+state.light*.035+beat*.030)*anatomyGain)+')';
      ctx.lineWidth=.45+(i%3)*.12;
      ctx.beginPath();
      ctx.moveTo(left,yy);
      ctx.bezierCurveTo(cx-w*.18,yy-h*.06+bend,cx+w*.12,yy+h*.07-bend,right,yy+bend*.20);
      ctx.stroke();
    }
    for(let i=0;i<5;i++){
      const a=-2.65+i*.49;
      const ex=cx+Math.cos(a)*w*(.33+.07*Math.sin(i*2.1));
      const ey=cy+Math.sin(a)*h*.30;
      ctx.strokeStyle='rgba('+palette.trail+','+((.022+state.light*.030)*anatomyGain)+')';
      ctx.lineWidth=.5;
      ctx.beginPath();
      ctx.moveTo(cx-w*.02,cy+h*.03);
      ctx.bezierCurveTo(cx+Math.cos(a-.8)*w*.18,cy+Math.sin(a-.8)*h*.20,cx+Math.cos(a+.5)*w*.28,cy+Math.sin(a+.5)*h*.29,ex,ey);
      ctx.stroke();
    }

    // Cerebellum and brain stem complete the human silhouette.
    ctx.strokeStyle='rgba('+palette.point+','+(.070+strength*.090)+')';
    ctx.fillStyle='rgba('+palette.glow+','+(.012+strength*.018)+')';
    ctx.lineWidth=compact?.70:.62;
    ctx.beginPath();ctx.ellipse(cx-w*.34,cy+h*.35,w*.205,h*.145,-.18,0,Math.PI*2);ctx.fill();ctx.stroke();
    for(let i=0;i<5;i++){
      const yy=cy+h*(.285+i*.026);
      ctx.beginPath();ctx.moveTo(cx-w*.45,yy);ctx.bezierCurveTo(cx-w*.36,yy-h*.018,cx-w*.24,yy+h*.014,cx-w*.17,yy);ctx.stroke();
    }
    ctx.beginPath();
    ctx.moveTo(cx-w*.075,cy+h*.35);
    ctx.bezierCurveTo(cx-w*.04,cy+h*.48,cx-w*.07,cy+h*.61,cx-w*.025,cy+h*.72);
    ctx.moveTo(cx+w*.015,cy+h*.35);
    ctx.bezierCurveTo(cx+w*.025,cy+h*.49,cx-w*.005,cy+h*.61,cx+w*.035,cy+h*.72);
    ctx.stroke();

    // Orbital data rings preserve the old sense of motion without a star field.
    ctx.strokeStyle='rgba('+palette.leader+','+(.010+state.light*.014)+')';
    for(let i=0;i<1;i++){
      ctx.lineWidth=.35+i*.10;
      ctx.beginPath();
      ctx.ellipse(cx,cy+h*.02,w*(.54+i*.03),h*(.145+i*.028),yaw*.16+i*.55,0,Math.PI*2);
      ctx.stroke();
    }
    ctx.restore();
  }
  function projectCortexPoint(p,yaw,pitch,scale,breathing){
    const compact=height<240;
    // v179 visual gate: the cortical mass must define the brain, not sit as a
    // bright knot in its centre. Compact previews need even more spread.
    const sx=compact?1.88:1.62,sy=compact?1.82:1.56,sz=compact?1.30:1.20;
    let x=p.x*sx*breathing*growth-camera.x;
    let y=p.y*sy*breathing*growth-camera.y;
    let z=p.z*sz*breathing*growth-camera.z;
    const rx=x*Math.cos(yaw)+z*Math.sin(yaw),rz=z*Math.cos(yaw)-x*Math.sin(yaw);
    const ry=y*Math.cos(pitch)-rz*Math.sin(pitch),zz=y*Math.sin(pitch)+rz*Math.cos(pitch);
    const perspective=3.8/(3.8-zz);
    return {x:width*.5+rx*scale*perspective,y:height*(options.centerY??.515)+ry*scale*perspective,z:zz,depth:Math.max(.08,Math.min(1,(zz+1.0)/2.0)),scale:perspective};
  }
  function drawCortexCloud(yaw,pitch,scale,breathe,state,beat){
    if(options.intro)return;
    const reveal=ease(opening/openingSeconds);
    if(reveal<.04)return;
    const awake=activeHub>=0||mode==='listen'||mode==='think'||mode==='speak'||selected>=0||hovered>=0;
    const linkGain=awake?.72:.08;
    const pointGain=awake?.70:.30;
    const projectedCloud=cortexCloud.map(p=>projectCortexPoint(p,yaw,pitch,scale,breathe));
    if(projectedCloud.length){
      const xs=projectedCloud.map(p=>p.x),ys=projectedCloud.map(p=>p.y);
      const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
      cortexFrame={x:minX,y:minY,w:maxX-minX,h:maxY-minY};
    }
    ctx.save();
    ctx.globalCompositeOperation='lighter';
    ctx.globalAlpha=reveal;

    for(const [ai,bi,phase] of cortexLinks){
      const a=projectedCloud[ai],b=projectedCloud[bi];
      const depth=(a.depth+b.depth)*.5;
      const wave=(Math.sin(t*.62+phase*6.28)+1)*.5;
      const alpha=(.014+depth*.040+wave*.016+beat*.020)*state.light*linkGain;
      ctx.strokeStyle='rgba('+palette.edge+','+alpha+')';
      ctx.lineWidth=.20+depth*.30;
      const bend=(phase-.5)*12;
      ctx.beginPath();ctx.moveTo(a.x,a.y);
      ctx.quadraticCurveTo((a.x+b.x)*.5+bend,(a.y+b.y)*.5-bend*.30,b.x,b.y);
      ctx.stroke();

      // Subtle impulses travel through a subset of fibres while ORA works.
      if(awake&&mode!=='idle'&&((ai+bi)%19===0)){
        const u=(t*(.12+state.speed*.12)+phase)%1;
        const px=a.x+(b.x-a.x)*u,py=a.y+(b.y-a.y)*u;
        const power=Math.sin(Math.PI*u)*(.12+beat*.12);
        glow(px,py,5+depth*6,power,false);
      }
    }

    // Longer translucent paths make the cortex feel like an energetic volume,
    // not a small graph sitting in the middle of an outline.
    for(let i=0;i<12;i++){
      const a=projectedCloud[(i*11)%projectedCloud.length];
      const b=projectedCloud[(i*23+37)%projectedCloud.length];
      const c0=projectedCloud[(i*17+83)%projectedCloud.length];
      if(!a||!b||!c0)continue;
      const depth=(a.depth+b.depth+c0.depth)/3;
      const pulse=.5+.5*Math.sin(t*.24+i*.71);
      ctx.strokeStyle='rgba('+palette.trail+','+((.008+depth*.018+pulse*.008)*state.light*linkGain)+')';
      ctx.lineWidth=.35+depth*.52;
      ctx.beginPath();ctx.moveTo(a.x,a.y);
      ctx.bezierCurveTo(c0.x,c0.y,(b.x+c0.x)*.5,(b.y+c0.y)*.5,b.x,b.y);ctx.stroke();
    }

    const order=projectedCloud.map((_,i)=>i).sort((a,b)=>projectedCloud[a].z-projectedCloud[b].z);
    for(const i of order){
      const p=cortexCloud[i],q=projectedCloud[i];
      const flicker=.82+.18*Math.sin(t*(p.hot?1.45:.42)+p.phase);
      const shellBoost=p.shell?1.12:.78;
      const alpha=(.050+q.depth*.18)*(p.hot?1.18:1)*shellBoost*flicker*state.light*p.energy*pointGain;
      const r=p.size*(.56+q.depth*.86)*q.scale;
      if(awake&&p.hot&&i%4===0){
        glow(q.x,q.y,6+q.depth*7,.045+beat*.055,p.warm);
      }
      ctx.fillStyle=p.warm
        ? 'rgba('+palette.warmPoint+','+Math.min(.64,alpha)+')'
        : 'rgba('+palette.point+','+Math.min(.58,alpha)+')';
      ctx.beginPath();ctx.arc(q.x,q.y,r,0,Math.PI*2);ctx.fill();
      if(p.hot&&q.depth>.56){
        ctx.strokeStyle='rgba('+(p.warm?palette.warmPacket:palette.packet)+','+Math.min(.28,alpha*.40)+')';
        ctx.lineWidth=.55;
        ctx.beginPath();ctx.arc(q.x,q.y,r+2.2,0,Math.PI*2);ctx.stroke();
      }
    }
    ctx.restore();
  }
  function projectPoint(p,yaw,pitch,scale,breathing){
    const drift=p.hub?.002:.009;
    const born=p.hub||options.reduced||options.paused?1:ease((t-(births.get(p.id)??t))/1.35);
    const spread=ease(opening/openingSeconds)*growth;
    const h=options.intro?{x:0,y:0,z:0}:hubs[p.group];
    const px=p.hub&&options.intro&&p.group===0?0:p.hub?p.x:h.x+(p.x-h.x)*born;
    const py=p.hub&&options.intro&&p.group===0?0:p.hub?p.y:h.y+(p.y-h.y)*born;
    const pz=p.hub&&options.intro&&p.group===0?0:p.hub?p.z:h.z+(p.z-h.z)*born;
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
    dust.forEach(s=>{const x=(s.x*width+Math.sin(t*.04+s.phase)*7+width)%width,y=s.y*height;ctx.fillStyle='rgba('+palette.dust+','+(.025+s.z*.075)+')';ctx.beginPath();ctx.arc(x,y,.28+s.z*.42,0,Math.PI*2);ctx.fill();});
    const active=mode==='think'||mode==='speak';
    activeHub=hubs.findIndex(h=>h.id===options.area);
    // A small, broad double pulse: activity should feel alive without jolting the map.
    const beatPhase=(t%1.65)/1.65;
    const beat=active&&!options.reduced&&!options.paused?(Math.exp(-Math.pow((beatPhase-.16)/.085,2))+.38*Math.exp(-Math.pow((beatPhase-.37)/.105,2))):0;
    const breathe=1+Math.sin(t*1.48)*state.breath+beat*.014;
    const compactStage=!options.intro&&height<240;const scale=Math.min(width*(options.intro?.43:(compactStage?.46:.40)),height*(options.intro?.76:(compactStage?.58:.47)))*camera.zoom;
    const spotlight=points.findIndex(p=>p.id===options.spotlightId);
    const yaw=rotation+dragYaw,pitch=.06+Math.sin(t*.10)*.09+dragPitch;
    for(let i=0;i<points.length;i++){
      const p=points[i],q=projectPoint(p,yaw,pitch,scale,breathe);
      q.appear=(options.intro&&p.hub&&i!==0?0:i===0?1:ease((opening/openingSeconds-p.distance/furthest*.65-.06)/.29))*(p.hub||options.reduced||options.paused?1:ease((t-(births.get(p.id)??t))/1.35));
      const focus=activeHub>=0?hubs[activeHub]:hubs[0];
      const distance=Math.hypot(p.x-focus.x,p.y-focus.y,p.z-focus.z);
      const phase=((t*state.speed-distance*.44)%1+1)%1;
      const wave=Math.exp(-Math.pow((phase-.10)/.095,2))*state.strength;
      q.energy=wave*.65+(p.hub?.10:0)+beat*Math.exp(-distance*2.3)*.42+(i===spotlight?.82:0);Object.assign(projected[i],q);
    }
    drawBrainEnvelope(state,yaw,pitch,scale,beat);
    drawCortexCloud(yaw,pitch,scale,breathe,state,beat);
    if(pointer&&!dragging)hovered=hitTest(pointer.x,pointer.y,pointer.touch);
    const inspected=hovered>=0?hovered:selected>=0?selected:spotlight;
    if(canvas.style)canvas.style.cursor=dragging?'grabbing':hovered>=0?'pointer':'grab';
    ctx.globalCompositeOperation='lighter';
    edges.forEach(e=>{
      const a=projected[e.a],b=projected[e.b];const depth=(a.depth+b.depth)*.5,energy=(a.energy+b.energy)*.5;
      const appear=Math.min(a.appear,b.appear);
      if(appear<.005)return;
      const related=inspected>=0&&(e.a===inspected||e.b===inspected);
      const hubToHub=!!points[e.a]?.hub&&!!points[e.b]?.hub;
      const activeRelated=related
        ||(activeHub>=0&&(points[e.a]?.areaGroup===activeHub||points[e.b]?.areaGroup===activeHub))
        ||(spotlight>=0&&(e.a===spotlight||e.b===spotlight));
      const graphAwake=activeHub>=0||inspected>=0||spotlight>=0||mode==='listen'||mode==='think'||mode==='speak';
      if(!graphAwake&&hubToHub)return;
      const graphGain=activeRelated?1:graphAwake?.18:.055;
      ctx.globalAlpha=appear*graphGain;
      const birthId=points[e.b].id,birthAge=t-(births.get(birthId)??-100);
      const arrival=!options.reduced&&!options.paused&&e.b===spotlight&&birthAge>=0&&birthAge<2.8;
      const trail=arrival?Math.sin(Math.PI*birthAge/2.8)*.55:0;
      const alpha=Math.min(.78,((.018+depth*.070+energy*.13)*(e.trunk?1.22:1)*state.light+(related?.36:0)+trail)*graphGain);
      const warm=arrival||activeHub>=0?(arrival||e.a===activeHub||e.b===activeHub):e.trunk&&e.a===0&&(e.b===4||e.b===1);
      const first=points[e.a].distance<=points[e.b].distance?a:b,second=first===a?b:a;
      ctx.strokeStyle=warm?'rgba('+palette.warmEdge+','+alpha+')':'rgba('+palette.edge+','+alpha+')';ctx.lineWidth=related?1.35:e.trunk?.72:.38+depth*.22;
      const tx=first.x+(second.x-first.x)*appear,ty=first.y+(second.y-first.y)*appear;
      const bend=(e.phase-.5)*18;
      ctx.beginPath();ctx.moveTo(first.x,first.y);ctx.quadraticCurveTo((first.x+tx)*.5-bend*.22,(first.y+ty)*.5+bend,tx,ty);ctx.stroke();
      if(arrival&&appear>.2){
        const u=ease(birthAge/1.35),px=a.x+(b.x-a.x)*u,py=a.y+(b.y-a.y)*u;
        glow(px,py,16,.55*appear,true);
      }
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
      const age=t-(births.get(p.id)??-100);
      const arriving=!p.hub&&!options.reduced&&!options.paused&&age>=0&&age<2.8;
      const bloom=arriving?Math.sin(Math.PI*age/2.8):0;
      const r=p.radius*q.scale*(.64+q.depth*.38)*(1+q.energy*.28)+(isInspected?2.8:0);
      const spotlighted=i===spotlight;
      if(isInspected){
        glow(q.x,q.y,spotlighted?34:24,spotlighted?1.25:.95,false,spotlighted&&!!p.temporary);
        ctx.strokeStyle=spotlighted&&p.temporary?'rgba('+palette.temporaryPoint+',.95)':palette.label;
        ctx.lineWidth=spotlighted?1.8:1;
        ctx.beginPath();ctx.arc(q.x,q.y,spotlighted?12:9,0,Math.PI*2);ctx.stroke();
      }
      const temporary=!p.hub&&!!p.temporary;
      const warm=!temporary&&(p.complete||p.tentative||(activeHub>=0?p.group===activeHub:i===0||i===4));
      if(p.hub){glow(q.x,q.y,14+q.energy*17,.17+q.energy*.40,warm);glow(q.x,q.y,5+q.energy*4,.48,warm);}
      else {glow(q.x,q.y,temporary?15:(p.complete?17:8),Math.max(.22+q.energy*.3,bloom*.9),warm||arriving,temporary);}
      if(arriving&&q.appear>.12){
        ctx.strokeStyle='rgba('+(temporary?palette.temporaryNode:palette.warmNode)+','+(bloom*.65*q.appear)+')';ctx.lineWidth=1.2;
        ctx.beginPath();ctx.arc(q.x,q.y,5+age*11,0,Math.PI*2);ctx.stroke();
        glow(q.x,q.y,24+age*9,bloom*.42,!temporary,temporary);
      }
      if(p.kind==='branch'){ctx.strokeStyle='rgba('+palette.warmNode+','+(p.complete?.85:.2)+')';ctx.lineWidth=p.complete?1.5:.6;ctx.beginPath();ctx.arc(q.x,q.y,6,0,Math.PI*2);ctx.stroke();}
      if(!p.hub&&p.kind==='node'&&!p.tentative){ctx.strokeStyle='rgba('+(temporary?palette.temporaryPoint:palette.point)+','+(.3+q.energy*.3)+')';ctx.lineWidth=.7;ctx.beginPath();ctx.moveTo(q.x-3.6,q.y);ctx.lineTo(q.x+3.6,q.y);ctx.moveTo(q.x,q.y-3.6);ctx.lineTo(q.x,q.y+3.6);ctx.stroke();}
      ctx.fillStyle='rgba('+(temporary?palette.temporaryNode:(warm?palette.warmNode:palette.node))+','+Math.min(.98,bright)+')';ctx.beginPath();ctx.arc(q.x,q.y,r+(spotlighted&&temporary?1.8:0),0,Math.PI*2);ctx.fill();
      if(spotlighted&&temporary&&q.appear>.72){
        const pulse=.55+.45*Math.sin(t*4.6);
        glow(q.x,q.y,42+pulse*12,.42+pulse*.35,false,true);
        ctx.strokeStyle='rgba('+palette.temporaryPoint+','+(.45+pulse*.42)+')';
        ctx.lineWidth=1.1;ctx.beginPath();ctx.arc(q.x,q.y,17+pulse*4,0,Math.PI*2);ctx.stroke();
        const label='NUOVA';
        ctx.font='700 10px ui-monospace, SFMono-Regular, Consolas, monospace';
        const tw=ctx.measureText(label).width, lx=Math.min(width-tw-12,q.x+15), ly=Math.max(14,q.y-16);
        ctx.fillStyle='rgba(25,5,10,.78)';ctx.fillRect(lx-4,ly-8,tw+8,16);
        ctx.fillStyle='rgba('+palette.temporaryPoint+',.98)';ctx.textAlign='left';ctx.fillText(label,lx,ly);
      }
      if(p.hub&&q.energy>.35){ctx.strokeStyle='rgba('+palette.cross+','+(q.energy*.33)+')';ctx.lineWidth=.6;ctx.beginPath();ctx.moveTo(q.x-7-q.energy*4,q.y);ctx.lineTo(q.x+7+q.energy*4,q.y);ctx.moveTo(q.x,q.y-6-q.energy*3);ctx.lineTo(q.x,q.y+6+q.energy*3);ctx.stroke();}
    }
    ctx.globalCompositeOperation='source-over';
    ctx.globalAlpha=ease((opening/openingSeconds-.68)/.32);
    const occupied=[],labelIndices=options.intro?[]:activeHub>=0?[activeHub]:height<180?[0,1,5]:width<430?[0,1,2,5]:[0,1,2,3,4,5,6,7];
    if(inspected>=0&&!labelIndices.includes(points[inspected].areaGroup))labelIndices.push(points[inspected].areaGroup);
    labels=[];
    ctx.font='500 11px ui-monospace, SFMono-Regular, Consolas, monospace';ctx.textBaseline='middle';
    labelIndices.forEach(i=>{
      const h=hubs[i],p=projected[i],tw=ctx.measureText(h.name).width;
      if(p.appear<.99||opening/openingSeconds<.72)return;
      if(p.x<0||p.x>width||p.y<0||p.y>height)return;
      const outside=brainFrame.w>0&&!options.intro;
      let y=outside?p.y+h.dy*.24:p.y+h.dy;
      let left;
      if(outside){
        const side=h.align==='right'?-1:1;
        const edgeX=brainFrame.cx+side*brainFrame.w*.57;
        left=side<0?edgeX-tw-8:edgeX+8;
      }else{
        const x=p.x+h.dx;
        left=h.align==='right'?x-tw:x;
      }
      left=Math.max(8,Math.min(width-tw-8,left));y=Math.max(18,Math.min(height-20,y));
      for(let tries=0;tries<6;tries++){if(!occupied.some(b=>left<b.x+b.w+7&&left+tw+7>b.x&&Math.abs(y-b.y)<19))break;y+=19;}
      y=Math.min(height-23,y);occupied.push({x:left,y,w:tw});labels.push({x:left,y,w:tw,index:i});
      ctx.strokeStyle='rgba('+palette.leader+',.20)';ctx.lineWidth=.55;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(h.align==='right'?left+tw+4:left-4,y);ctx.stroke();
      ctx.fillStyle=palette.labelBackground;ctx.fillRect(left-3,y-8,tw+6,16);ctx.fillStyle=i===0?palette.warmLabel:palette.label;ctx.textAlign='left';ctx.fillText(h.name,left,y);
    });
    if(options.intro){
      for(let i=8;i<points.length;i++){
        const id=points[i].id;
        const name=id==='intro_step_one'?'INIZIO':id==='draft_first_name'?'NOME':id==='draft_last_name'?'COGNOME':id.startsWith('intro_example_')?'ESEMPIO':null;
        const p=projected[i];if(!name||p.appear<.85)continue;
        const tw=ctx.measureText(name).width,x=Math.min(width-tw-12,Math.max(12,p.x+9)),y=Math.min(height-14,Math.max(14,p.y-11));
        ctx.globalAlpha=p.appear;ctx.fillStyle=palette.labelBackground;ctx.fillRect(x-3,y-8,tw+6,16);
        ctx.fillStyle=palette.label;ctx.textAlign='left';ctx.fillText(name,x,y);
      }
      ctx.globalAlpha=1;
    }
  }
  function moveCamera(dt,instant=false){
    const active=mode==='think'||mode==='speak';
    activeHub=options.intro?-1:hubs.findIndex(h=>h.id===options.area);
    const focused=points.find(p=>p.id===options.spotlightId);
    const target=focused||(activeHub>=0?hubs[activeHub]:{x:0,y:0,z:0});
    const mix=instant?1:1-Math.exp(-dt*3.2);
    for(const axis of ['x','y','z'])camera[axis]+=(target[axis]*.82*growth-camera[axis])*mix;
    const requestedZoom=Number.isFinite(options.zoomOverride)?Math.max(.72,Math.min(1.55,options.zoomOverride)):1;
    camera.zoom+=(((focused?1.38:activeHub>=0?1.65:active?1.12:1)*requestedZoom)-camera.zoom)*mix;
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
    if(reveal){opening=0;camera.x=0;camera.y=0;camera.z=0;camera.zoom=Number.isFinite(options.zoomOverride)?options.zoomOverride:1;hovered=-1;pointer=null;}
    if(options.reduced||options.paused)opening=openingSeconds;
    selected=Number.isInteger(options.selectedIndex)&&points[options.selectedIndex]?options.selectedIndex:-1;
    if(reset){rotation=-.06;dragYaw=0;dragPitch=0;inertia=0;hovered=-1;pointer=null;camera.x=0;camera.y=0;camera.z=0;camera.zoom=Number.isFinite(options.zoomOverride)?options.zoomOverride:1;}
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
    snapshot(){return {surface:'brain',visualProfile:'anatomy-first-v180',brain:{...brainFrame},brainCloudFrame:{...cortexFrame},brainCloudPoints:cortexCloud.length,brainCloudLinks:cortexLinks.length,camera:{...camera},rotation:{yaw:dragYaw,pitch:dragPitch},hovered,selected,activeHub,points:points.length,knowledgeStars:points.filter(p=>p.kind==='node').length,edges:edges.length,frame,mode,opening:opening/openingSeconds,visiblePoints:projected.filter(p=>p.appear>.01).length,projected:projected.map((p,i)=>({x:p.x,y:p.y,...nodeInfo(i)}))};}};
}
