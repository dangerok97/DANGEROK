/** ORA Brain Presence — real WebGL 3D renderer.
 *
 * Knowledge IDs, areas, selections and focus semantics are unchanged.
 * The previous Canvas2D silhouette is gone: this scene uses a perspective
 * projection, depth buffer, 3D point volumes and neural fibres in WebGL.
 */
export function createPresenceScene(canvas, initial, palette, events={}) {
  const gl=canvas.getContext('webgl',{alpha:false,antialias:true,premultipliedAlpha:false,preserveDrawingBuffer:false})
    || canvas.getContext('experimental-webgl',{alpha:false,antialias:true,premultipliedAlpha:false,preserveDrawingBuffer:false});
  if(!gl) throw new Error('webgl_unavailable');

  let options={mode:'idle',area:null,paused:false,reduced:false,active:true,selectedIndex:null,resetKey:0,...initial};
  let mode=options.mode,width=700,height=460,pixelRatio=1;
  let visible=typeof document==='undefined'?true:!document.hidden,inViewport=true,destroyed=false;
  let t=1.7,frame=0,last=0,dragging=false,dragX=0,dragY=0,dragYaw=-.34,dragPitch=.10,inertia=0;
  let activeHub=-1,hovered=-1,selected=-1;
  let pointer=null,pointerId=null,downX=0,downY=0,moved=false;
  const openingSeconds=2.8;
  let opening=(options.reveal||options.revealKey)&&!options.reduced?0:openingSeconds;
  const ease=value=>{const v=Math.max(0,Math.min(1,value));return v*v*(3-2*v);};
  const camera={x:0,y:0,z:0,zoom:1};
  const cleanups=[];
  const modes={
    idle:{speed:.22,strength:.28,breath:.010,light:.68},
    listen:{speed:.34,strength:.48,breath:.018,light:.84},
    think:{speed:.58,strength:.82,breath:.008,light:1},
    speak:{speed:.44,strength:.70,breath:.012,light:.92},
  };
  const hubs=[
    {x:-.25,y:.10,z:.38,id:'memory',name:'MEMORIA'},
    {x:.45,y:.28,z:.22,id:'calendar',name:'IMPEGNI'},
    {x:-.48,y:.06,z:.08,id:'people',name:'PERSONE'},
    {x:.30,y:-.02,z:.45,id:'places',name:'LUOGHI'},
    {x:-.30,y:-.22,z:.34,id:'home',name:'CASA'},
    {x:.50,y:.02,z:-.18,id:'documents',name:'DOCUMENTI'},
    {x:-.40,y:.24,z:-.20,id:'finances',name:'FINANZE'},
    {x:.06,y:.48,z:-.06,id:'calls',name:'CHIAMATE'},
  ];

  let seed=932761;
  function random(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;}
  function hashSeed(text){let h=2166136261;for(const c of String(text||''))h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;return h||1;}
  function on(target,event,fn){if(!target?.addEventListener)return;target.addEventListener(event,fn);cleanups.push(()=>target.removeEventListener(event,fn));}

  function parseColor(value,fallback=[.72,.93,.97]){
    if(typeof value!=='string')return fallback;
    const s=value.trim();
    if(/^#([0-9a-f]{6})$/i.test(s)){
      return [parseInt(s.slice(1,3),16)/255,parseInt(s.slice(3,5),16)/255,parseInt(s.slice(5,7),16)/255];
    }
    const m=s.match(/(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)/);
    return m?[+m[1]/255,+m[2]/255,+m[3]/255]:fallback;
  }
  const colors={
    cyan:parseColor(palette.glow,[.55,.92,1]),
    line:parseColor(palette.edge,[.45,.82,.95]),
    white:parseColor(palette.point,[.92,1,1]),
    warm:parseColor(palette.warmNode,[1,.86,.60]),
    red:parseColor(palette.temporaryNode,[1,.30,.34]),
    dim:parseColor(palette.dust,[.35,.55,.62]),
  };

  function shader(type,source){
    const out=gl.createShader(type);gl.shaderSource(out,source);gl.compileShader(out);
    if(!gl.getShaderParameter(out,gl.COMPILE_STATUS))throw new Error('webgl_shader:'+gl.getShaderInfoLog(out));
    return out;
  }
  function program(vs,fs){
    const out=gl.createProgram();gl.attachShader(out,shader(gl.VERTEX_SHADER,vs));gl.attachShader(out,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(out);
    if(!gl.getProgramParameter(out,gl.LINK_STATUS))throw new Error('webgl_program:'+gl.getProgramInfoLog(out));
    return out;
  }

  const pointProgram=program(
`attribute vec3 aPosition;
attribute float aSize;
attribute float aPhase;
uniform mat4 uMvp;
uniform float uTime;
uniform float uPulse;
uniform float uReveal;
varying float vAlpha;
varying float vTwinkle;
void main(){
  vec4 clip=uMvp*vec4(aPosition,1.0);
  gl_Position=clip;
  float perspective=clamp(2.5/max(.35,clip.w),.42,2.4);
  float twinkle=.76+.24*sin(uTime*1.7+aPhase*6.28318);
  gl_PointSize=max(1.0,aSize*perspective*(1.0+uPulse*.28)*twinkle);
  vAlpha=uReveal;
  vTwinkle=twinkle;
}`,
`precision mediump float;
uniform vec4 uColor;
varying float vAlpha;
varying float vTwinkle;
void main(){
  vec2 d=gl_PointCoord-vec2(.5);
  float r=length(d);
  if(r>.5)discard;
  float core=smoothstep(.5,.02,r);
  float halo=smoothstep(.5,.18,r);
  float a=(core*.78+halo*.22)*uColor.a*vAlpha;
  gl_FragColor=vec4(uColor.rgb*(.82+.35*vTwinkle),a);
}`);
  const lineProgram=program(
`attribute vec3 aPosition;
uniform mat4 uMvp;
void main(){gl_Position=uMvp*vec4(aPosition,1.0);}`,
`precision mediump float;
uniform vec4 uColor;
void main(){gl_FragColor=uColor;}`);

  function locations(p){
    return {
      pos:gl.getAttribLocation(p,'aPosition'),
      size:gl.getAttribLocation(p,'aSize'),
      phase:gl.getAttribLocation(p,'aPhase'),
      mvp:gl.getUniformLocation(p,'uMvp'),
      time:gl.getUniformLocation(p,'uTime'),
      pulse:gl.getUniformLocation(p,'uPulse'),
      reveal:gl.getUniformLocation(p,'uReveal'),
      color:gl.getUniformLocation(p,'uColor'),
    };
  }
  const pointLoc=locations(pointProgram), lineLoc=locations(lineProgram);
  const buffers=new Set();
  function buffer(data,usage=gl.STATIC_DRAW){
    const b=gl.createBuffer();buffers.add(b);gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),usage);return b;
  }
  function replaceBuffer(old,data,usage=gl.DYNAMIC_DRAW){
    if(old){gl.deleteBuffer(old);buffers.delete(old);}
    return buffer(data,usage);
  }

  function identity(){return [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];}
  function multiply(a,b){
    const o=new Array(16).fill(0);
    for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];
    return o;
  }
  function perspective(fov,aspect,near,far){
    const f=1/Math.tan(fov/2),nf=1/(near-far);
    return [f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0];
  }
  function translate(x,y,z){const m=identity();m[12]=x;m[13]=y;m[14]=z;return m;}
  function scale(x,y,z){const m=identity();m[0]=x;m[5]=y;m[10]=z;return m;}
  function rotX(a){const c=Math.cos(a),s=Math.sin(a);return [1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1];}
  function rotY(a){const c=Math.cos(a),s=Math.sin(a);return [c,0,-s,0,0,1,0,0,s,0,c,0,0,0,0,1];}
  function transform(m,p){
    const x=p.x,y=p.y,z=p.z,w=m[3]*x+m[7]*y+m[11]*z+m[15]||1;
    return {x:(m[0]*x+m[4]*y+m[8]*z+m[12])/w,y:(m[1]*x+m[5]*y+m[9]*z+m[13])/w,z:(m[2]*x+m[6]*y+m[10]*z+m[14])/w,w};
  }
  function currentMvp(reveal=1){
    const aspect=Math.max(.1,width/Math.max(1,height));
    const proj=perspective(Math.PI/3.25,aspect,.1,20);
    const centerShift=(.5-(options.centerY??.515))*1.25;
    const distance=4.25/Math.max(.70,camera.zoom);
    let model=identity();
    model=multiply(translate(-camera.x,-camera.y+centerShift,-distance-camera.z),model);
    model=multiply(rotX(dragPitch),model);
    model=multiply(rotY(dragYaw),model);
    const introScale=options.intro?(.25+.75*reveal):(.72+.28*reveal);
    model=multiply(scale(introScale,introScale,introScale),model);
    return multiply(proj,model);
  }

  function foldNoise(theta,phi,hemi){
    return 1
      +.048*Math.sin(theta*9+phi*3.2+hemi*.7)
      +.030*Math.sin(phi*13-theta*2.2)
      +.018*Math.sin(theta*17+phi*5);
  }
  function cerebrumPoint(hemi,theta,phi){
    const cphi=Math.cos(phi),sphi=Math.sin(phi);
    const fold=foldNoise(theta,phi,hemi);
    const center=hemi*.20;
    const x=center+.82*cphi*Math.cos(theta)*fold;
    const y=.08+.72*sphi*(1-.08*Math.cos(theta))*fold;
    const z=.70*cphi*Math.sin(theta)*fold;
    const lower=Math.max(0,-y-.25);
    return {x:x*(1-lower*.08),y,z:z*(1-lower*.10)};
  }
  function ellipsoidPoint(cx,cy,cz,rx,ry,rz,theta,phi,rough=.0){
    const n=1+rough*(.55*Math.sin(theta*10+phi*4)+.45*Math.sin(phi*15-theta*3));
    return {x:cx+rx*Math.cos(phi)*Math.cos(theta)*n,y:cy+ry*Math.sin(phi)*n,z:cz+rz*Math.cos(phi)*Math.sin(theta)*n};
  }
  function buildBrain(){
    const surface=[],surfaceSize=[],surfacePhase=[],wire=[];
    for(const hemi of [-1,1]){
      const lat=32,lon=48;
      for(let i=0;i<lat;i++){
        const phi=-Math.PI/2+(i/(lat-1))*Math.PI;
        for(let j=0;j<lon;j++){
          const theta=(j/lon)*Math.PI*2;
          const p=cerebrumPoint(hemi,theta,phi);
          surface.push(p.x,p.y,p.z);surfaceSize.push(2.2+(i+j)%4*.30);surfacePhase.push(((i*37+j*19)%97)/97);
        }
      }
      for(let band=3;band<lat-3;band+=3){
        const phi=-Math.PI/2+(band/(lat-1))*Math.PI;
        let prev=null;
        for(let j=0;j<=lon;j++){
          const theta=(j/lon)*Math.PI*2,p=cerebrumPoint(hemi,theta,phi);
          if(prev)wire.push(prev.x,prev.y,prev.z,p.x,p.y,p.z);
          prev=p;
        }
      }
      for(let mer=0;mer<lon;mer+=5){
        const theta=(mer/lon)*Math.PI*2;
        let prev=null;
        for(let i=2;i<lat-2;i++){
          const phi=-Math.PI/2+(i/(lat-1))*Math.PI,p=cerebrumPoint(hemi,theta,phi);
          if(prev)wire.push(prev.x,prev.y,prev.z,p.x,p.y,p.z);
          prev=p;
        }
      }
    }
    // Cerebellum: a separately volumetric, ridged object behind/below cerebrum.
    const cLat=20,cLon=34;
    for(let i=0;i<cLat;i++){
      const phi=-Math.PI/2+(i/(cLat-1))*Math.PI;
      for(let j=0;j<cLon;j++){
        const theta=(j/cLon)*Math.PI*2;
        const p=ellipsoidPoint(-.28,-.66,-.18,.45,.27,.38,theta,phi,.035);
        surface.push(p.x,p.y,p.z);surfaceSize.push(2.0+(j%3)*.28);surfacePhase.push(((i*29+j*11)%89)/89);
      }
    }
    for(let band=3;band<cLat-2;band+=2){
      const phi=-Math.PI/2+(band/(cLat-1))*Math.PI;let prev=null;
      for(let j=0;j<=cLon;j++){
        const p=ellipsoidPoint(-.28,-.66,-.18,.45,.27,.38,(j/cLon)*Math.PI*2,phi,.035);
        if(prev)wire.push(prev.x,prev.y,prev.z,p.x,p.y,p.z);prev=p;
      }
    }
    // Brain stem as a tapered cylindrical volume.
    for(let iy=0;iy<14;iy++)for(let j=0;j<18;j++){
      const u=iy/13,a=j/18*Math.PI*2,r=.13*(1-u*.46);
      const p={x:-.02+r*Math.cos(a),y:-.72-u*.46,z:-.02+r*.82*Math.sin(a)};
      surface.push(p.x,p.y,p.z);surfaceSize.push(1.9);surfacePhase.push(((iy*17+j*7)%61)/61);
      if(j<17){const b={x:-.02+r*Math.cos(a+Math.PI*2/18),y:p.y,z:-.02+r*.82*Math.sin(a+Math.PI*2/18)};wire.push(p.x,p.y,p.z,b.x,b.y,b.z);}
    }
    // Internal neural fibres make the volume read as holographic tissue.
    const fibres=[];
    seed=712391;
    for(let i=0;i<260;i++){
      const a=hubs[Math.floor(random()*hubs.length)],b=hubs[Math.floor(random()*hubs.length)];
      if(a===b)continue;
      const bend={x:(a.x+b.x)*.5+(random()-.5)*.24,y:(a.y+b.y)*.5+(random()-.5)*.22,z:(a.z+b.z)*.5+(random()-.5)*.30};
      let prev=a;
      const steps=7;
      for(let s=1;s<=steps;s++){
        const u=s/steps,iv=1-u;
        const p={x:iv*iv*a.x+2*iv*u*bend.x+u*u*b.x,y:iv*iv*a.y+2*iv*u*bend.y+u*u*b.y,z:iv*iv*a.z+2*iv*u*bend.z+u*u*b.z};
        fibres.push(prev.x,prev.y,prev.z,p.x,p.y,p.z);prev=p;
      }
    }
    return {
      surface,wire,fibres,surfaceSize,surfacePhase,
      surfaceBuffer:buffer(surface),wireBuffer:buffer(wire),fibreBuffer:buffer(fibres),
      sizeBuffer:buffer(surfaceSize),phaseBuffer:buffer(surfacePhase),
      surfaceCount:surface.length/3,wireCount:wire.length/3,fibreCount:fibres.length/3,
    };
  }
  const brain=buildBrain();

  let points=[],edges=[],projected=[],geometryKey='',edgeBuffer=null;
  let knowledgeGroups={normal:[],tentative:[],temporary:[],hubs:[]};
  let knowledgeBuffers={normal:null,tentative:null,temporary:null,hubs:null};
  let focusBuffers=null;
  const births=new Map();
  let furthest=1;

  function rebuild(nodes,first=false){
    const key=JSON.stringify([!!options.intro,nodes||[]]);if(key===geometryKey)return;geometryKey=key;
    const oldIds=new Set(points.map(p=>p.id));
    points=hubs.map((h,i)=>({...h,group:i,areaGroup:i,hub:true,kind:'area',radius:9,phase:i*.83,distance:0}));
    const groups=hubs.map(()=>[]);
    for(const node of nodes||[]){
      const g=hubs.findIndex(h=>h.id===node.area);if(g<0||!node.id)continue;
      seed=hashSeed(node.id);
      const h=hubs[g],a=random()*Math.PI*2,u=random()*2-1,r=.07+Math.cbrt(random())*.20,v=Math.sqrt(1-u*u);
      const introPosition=node.id==='intro_step_one'?[-.52,-.30,.08]:node.id==='draft_first_name'?[.28,-.65,.18]:node.id==='draft_last_name'?[.68,.30,-.12]:node.id.startsWith('intro_example_')?[-.48,.60,-.08]:null;
      const p={
        x:introPosition?.[0]??h.x+Math.cos(a)*r*v,
        y:introPosition?.[1]??h.y+u*r*.76,
        z:introPosition?.[2]??h.z+Math.sin(a)*r*v,
        id:node.id,kind:node.kind==='branch'?'branch':'node',tentative:!!node.tentative,temporary:!!node.temporary,complete:!!node.complete,
        group:g,areaGroup:g,hub:false,radius:node.kind==='branch'?8.5:6.5+random()*2.5,phase:random()*6.28,
      };
      if(!births.has(p.id)||!oldIds.has(p.id))births.set(p.id,first?t-4:t);
      points.push(p);groups[g].push(points.length-1);
    }
    const liveIds=new Set(points.map(p=>p.id));for(const id of births.keys())if(!liveIds.has(id))births.delete(id);
    points.forEach(p=>p.distance=Math.hypot(p.x,p.y,p.z));furthest=Math.max(1,...points.map(p=>p.distance));

    edges=[];const keys=new Set();
    const add=(a,b,trunk=false)=>{const k=Math.min(a,b)+':'+Math.max(a,b);if(a===b||keys.has(k))return;keys.add(k);edges.push({a,b,trunk});};
    if(options.intro){
      for(let i=8;i<points.length;i++){add(0,i,true);if(i>8)add(i-1,i);}
    } else {
      [[0,1],[0,2],[0,3],[0,4],[0,6],[0,7],[1,3],[1,5],[1,7],[2,4],[2,6],[2,7],[3,4],[3,5],[3,7],[4,5],[4,6],[5,7],[6,7]].forEach(x=>add(x[0],x[1],true));
      groups.forEach((group,g)=>group.forEach((index,j)=>{add(index,g);for(let k=1;k<=2&&k<=j;k++)add(index,group[j-k]);}));
    }

    const edgePos=[];
    knowledgeGroups={normal:[],tentative:[],temporary:[],hubs:[]};
    points.forEach((p,i)=>{
      if(p.hub)knowledgeGroups.hubs.push(i);
      else if(p.temporary)knowledgeGroups.temporary.push(i);
      else if(p.tentative)knowledgeGroups.tentative.push(i);
      else knowledgeGroups.normal.push(i);
    });
    edges.forEach(e=>{const a=points[e.a],b=points[e.b];edgePos.push(a.x,a.y,a.z,b.x,b.y,b.z);});
    edgeBuffer=replaceBuffer(edgeBuffer,edgePos);
    const disposeGroup=value=>{
      if(!value)return;
      for(const key of ['pos','size','phase'])if(value[key]){gl.deleteBuffer(value[key]);buffers.delete(value[key]);}
    };
    Object.values(knowledgeBuffers).forEach(disposeGroup);
    const buildGroup=indices=>{
      const pos=[],sz=[],ph=[];
      for(const i of indices){const p=points[i];pos.push(p.x,p.y,p.z);sz.push(p.radius);ph.push(p.phase/6.28);}
      return {pos:buffer(pos),size:buffer(sz),phase:buffer(ph),count:indices.length};
    };
    knowledgeBuffers={
      normal:buildGroup(knowledgeGroups.normal),
      tentative:buildGroup(knowledgeGroups.tentative),
      temporary:buildGroup(knowledgeGroups.temporary),
      hubs:buildGroup(knowledgeGroups.hubs),
    };
    projected=points.map(()=>({x:0,y:0,z:0,depth:0,appear:1}));
    selected=-1;hovered=-1;pointer=null;
  }
  rebuild(options.stars,true);

  function bindPointAttributes(position,size,phase){
    gl.bindBuffer(gl.ARRAY_BUFFER,position);gl.enableVertexAttribArray(pointLoc.pos);gl.vertexAttribPointer(pointLoc.pos,3,gl.FLOAT,false,0,0);
    gl.bindBuffer(gl.ARRAY_BUFFER,size);gl.enableVertexAttribArray(pointLoc.size);gl.vertexAttribPointer(pointLoc.size,1,gl.FLOAT,false,0,0);
    gl.bindBuffer(gl.ARRAY_BUFFER,phase);gl.enableVertexAttribArray(pointLoc.phase);gl.vertexAttribPointer(pointLoc.phase,1,gl.FLOAT,false,0,0);
  }
  function drawPoints(position,size,phase,count,mvp,color,alpha,pulse,reveal){
    if(!count)return;
    gl.useProgram(pointProgram);bindPointAttributes(position,size,phase);
    gl.uniformMatrix4fv(pointLoc.mvp,false,new Float32Array(mvp));
    gl.uniform1f(pointLoc.time,t);gl.uniform1f(pointLoc.pulse,pulse);gl.uniform1f(pointLoc.reveal,reveal);
    gl.uniform4f(pointLoc.color,color[0],color[1],color[2],alpha);
    gl.drawArrays(gl.POINTS,0,count);
  }
  function drawLines(b,count,mvp,color,alpha,widthPx=1){
    if(!count)return;
    gl.useProgram(lineProgram);gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.enableVertexAttribArray(lineLoc.pos);gl.vertexAttribPointer(lineLoc.pos,3,gl.FLOAT,false,0,0);
    gl.uniformMatrix4fv(lineLoc.mvp,false,new Float32Array(mvp));gl.uniform4f(lineLoc.color,color[0],color[1],color[2],alpha);
    gl.lineWidth(widthPx);gl.drawArrays(gl.LINES,0,count);
  }
  function drawKnowledgeBuffer(group,color,alpha,mvp,pulse,reveal){
    if(!group?.count)return;
    drawPoints(group.pos,group.size,group.phase,group.count,mvp,color,alpha,pulse,reveal);
  }
  function drawFocusedPoint(index,color,mvp,reveal){
    const p=points[index];if(!p)return;
    if(!focusBuffers){
      focusBuffers={pos:buffer([0,0,0],gl.DYNAMIC_DRAW),size:buffer([1],gl.DYNAMIC_DRAW),phase:buffer([0],gl.DYNAMIC_DRAW)};
    }
    gl.bindBuffer(gl.ARRAY_BUFFER,focusBuffers.pos);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([p.x,p.y,p.z]),gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER,focusBuffers.size);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([p.radius+7]),gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER,focusBuffers.phase);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([p.phase/6.28]),gl.DYNAMIC_DRAW);
    drawPoints(focusBuffers.pos,focusBuffers.size,focusBuffers.phase,1,mvp,color,1,.9,reveal);
  }

  let overlay=null,labelEls=[];
  function ensureLabels(){
    if(typeof document==='undefined'||!canvas.parentElement||typeof document.createElement!=='function')return;
    if(overlay)return;
    const parent=canvas.parentElement;
    if(parent.style&&(!parent.style.position||parent.style.position==='static'))parent.style.position='relative';
    overlay=document.createElement('div');
    overlay.setAttribute('aria-hidden','true');
    Object.assign(overlay.style,{position:'absolute',inset:'0',pointerEvents:'none',overflow:'hidden'});
    labelEls=hubs.map(h=>{
      const el=document.createElement('div');el.textContent=h.name;
      Object.assign(el.style,{position:'absolute',transform:'translate(-50%,-50%)',padding:'3px 6px',font:'600 10px ui-monospace, SFMono-Regular, Consolas, monospace',letterSpacing:'1px',color:palette.label||'#9fced9',background:'rgba(5,12,18,.66)',border:'1px solid rgba(159,206,217,.16)',borderRadius:'3px',whiteSpace:'nowrap',opacity:'0',transition:'opacity .2s'});
      overlay.appendChild(el);return el;
    });
    parent.appendChild(overlay);cleanups.push(()=>overlay?.remove());
  }
  ensureLabels();

  function projectKnowledge(mvp,reveal){
    for(let i=0;i<points.length;i++){
      const p=points[i],clip=transform(mvp,p);
      const x=(clip.x*.5+.5)*width,y=(1-(clip.y*.5+.5))*height;
      const age=t-(births.get(p.id)??-100);
      const born=p.hub||options.reduced||options.paused?1:ease(age/1.05);
      const appear=(options.intro&&p.hub&&i!==0?0:(i===0?1:ease((reveal-p.distance/furthest*.50-.02)/.24)))*born;
      projected[i]={x,y,z:clip.z,depth:1-Math.min(1,Math.max(0,(clip.z+1)*.5)),appear};
    }
    if(labelEls.length){
      const show=height>=150&&opening/openingSeconds>.62;
      hubs.forEach((_,i)=>{
        const q=projected[i],el=labelEls[i];if(!el)return;
        if(!show||q.appear<.85||q.x<15||q.x>width-15||q.y<12||q.y>height-12){el.style.opacity='0';return;}
        el.style.left=q.x+'px';el.style.top=q.y+'px';el.style.opacity=activeHub===i?'1':'.82';
        el.style.color=activeHub===i?(palette.warmLabel||'#e3c492'):(palette.label||'#9fced9');
      });
    }
  }
  function hitTest(x,y,touch=false){
    let best=-1,score=Infinity;
    projected.forEach((q,i)=>{
      if(q.appear<.78||q.x<0||q.x>width||q.y<0||q.y>height)return;
      const d=Math.hypot(x-q.x,y-q.y),radius=touch?25:(points[i].hub?16:13);
      const candidate=d-q.depth*2;
      if(d<=radius&&candidate<score){best=i;score=candidate;}
    });
    return best;
  }
  function nodeInfo(index){
    const p=points[index];return p?{index,area:hubs[p.areaGroup].id,kind:p.hub?'area':p.kind,...(p.hub?{}:{id:p.id})}:null;
  }
  function localPointer(e){const box=canvas.getBoundingClientRect();return {x:e.clientX-(box.left||0),y:e.clientY-(box.top||0),touch:e.pointerType==='touch'};}

  function moveCamera(dt,instant=false){
    activeHub=options.intro?-1:hubs.findIndex(h=>h.id===options.area);
    const focused=points.find(p=>p.id===options.spotlightId);
    const selectedPoint=selected>=0?points[selected]:null;
    const target=selectedPoint||focused||(activeHub>=0?hubs[activeHub]:{x:0,y:0,z:0});
    const mix=instant?1:1-Math.exp(-dt*3.0);
    camera.x+=(target.x*.72-camera.x)*mix;camera.y+=(target.y*.72-camera.y)*mix;camera.z+=(target.z*.46-camera.z)*mix;
    const requested=Number.isFinite(options.zoomOverride)?Math.max(.72,Math.min(1.55,options.zoomOverride)):1;
    const desired=(selectedPoint?1.58:focused?1.46:activeHub>=0?1.62:1)*requested;
    camera.zoom+=(desired-camera.zoom)*mix;
  }

  function draw(){
    const state=modes[mode]||modes.idle;
    const reveal=options.reduced||options.paused?1:ease(opening/openingSeconds);
    const active=mode==='think'||mode==='speak';
    const beatPhase=(t%1.65)/1.65;
    const beat=active&&!options.reduced&&!options.paused?(Math.exp(-Math.pow((beatPhase-.16)/.085,2))+.38*Math.exp(-Math.pow((beatPhase-.37)/.105,2))):0;
    const mvp=currentMvp(reveal);

    gl.viewport(0,0,canvas.width,canvas.height);
    const bg=parseColor(palette.background,[.02,.035,.055]);
    gl.clearColor(bg[0],bg[1],bg[2],1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);gl.depthMask(true);
    gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);

    // True 3D holographic anatomy, depth-tested in model space.
    drawPoints(brain.surfaceBuffer,brain.sizeBuffer,brain.phaseBuffer,brain.surfaceCount,mvp,colors.cyan,.31+.10*state.light,beat,reveal);
    gl.depthMask(false);
    drawLines(brain.wireBuffer,brain.wireCount,mvp,colors.white,.16+.09*state.light,1);
    drawLines(brain.fibreBuffer,brain.fibreCount,mvp,colors.line,.055+.055*state.light,1);
    gl.depthMask(true);

    if(edgeBuffer){
      drawLines(edgeBuffer,edges.length*2,mvp,colors.line,.16+.12*state.light,1);
      drawKnowledgeBuffer(knowledgeBuffers.normal,colors.white,.92,mvp,beat,reveal);
      drawKnowledgeBuffer(knowledgeBuffers.tentative,colors.warm,.96,mvp,beat,reveal);
      drawKnowledgeBuffer(knowledgeBuffers.temporary,colors.red,1,mvp,beat,reveal);
      drawKnowledgeBuffer(knowledgeBuffers.hubs,activeHub>=0?colors.cyan:colors.white,.95,mvp,beat,reveal);
      const spotlight=points.findIndex(p=>p.id===options.spotlightId);
      const inspected=hovered>=0?hovered:selected>=0?selected:spotlight;
      if(inspected>=0){
        const p=points[inspected],color=p.temporary?colors.red:colors.white;
        drawFocusedPoint(inspected,color,mvp,reveal);
      }
    }
    gl.depthMask(true);
    projectKnowledge(mvp,reveal);
    if(pointer&&!dragging)hovered=hitTest(pointer.x,pointer.y,pointer.touch);
    if(canvas.style)canvas.style.cursor=dragging?'grabbing':hovered>=0?'pointer':'grab';
  }

  function schedule(){if(!frame&&!destroyed&&!options.paused&&!options.reduced&&options.active&&visible&&inViewport)frame=requestAnimationFrame(tick);}
  function stop(){if(frame)cancelAnimationFrame(frame);frame=0;last=0;}
  function tick(now){
    frame=0;const dt=last?Math.min(.05,(now-last)/1000):.016;last=now;
    opening=Math.min(openingSeconds,opening+dt);
    if(!dragging&&hovered<0&&selected<0){t+=dt;dragYaw+=inertia;inertia*=.93;if(opening===openingSeconds)moveCamera(dt);}
    draw();schedule();
  }
  function size(){
    const box=canvas.getBoundingClientRect();width=Math.max(1,box.width);height=Math.max(1,box.height);pixelRatio=Math.min((typeof window!=='undefined'?window.devicePixelRatio:1)||1,1.75);
    canvas.width=Math.max(1,Math.round(width*pixelRatio));canvas.height=Math.max(1,Math.round(height*pixelRatio));draw();
  }
  function update(next){
    const revealKey=next.revealKey&&next.revealKey!==options.revealKey;
    const reset=next.resetKey!==undefined&&next.resetKey!==options.resetKey;
    options={...options,...next};mode=modes[options.mode]?options.mode:'idle';rebuild(options.stars);
    if(Object.prototype.hasOwnProperty.call(next,'selectedIndex'))selected=Number.isInteger(options.selectedIndex)&&points[options.selectedIndex]?options.selectedIndex:-1;
    if(revealKey){opening=0;camera.x=0;camera.y=0;camera.z=0;camera.zoom=1;hovered=-1;pointer=null;}
    if(options.reduced||options.paused)opening=openingSeconds;
    if(reset){dragYaw=-.34;dragPitch=.10;inertia=0;hovered=-1;selected=-1;pointer=null;camera.x=0;camera.y=0;camera.z=0;camera.zoom=1;}
    if(options.reduced||options.paused)moveCamera(0,true);
    stop();draw();schedule();
  }

  on(canvas,'pointerdown',e=>{
    if(e.button!==undefined&&e.button!==0||pointerId!==null)return;
    opening=openingSeconds;pointerId=e.pointerId;pointer=localPointer(e);downX=dragX=e.clientX;downY=dragY=e.clientY;moved=false;dragging=false;inertia=0;hovered=hitTest(pointer.x,pointer.y,pointer.touch);
    canvas.setPointerCapture?.(e.pointerId);draw();
  });
  on(canvas,'pointermove',e=>{
    if(pointerId!==null&&e.pointerId!==pointerId)return;
    pointer=localPointer(e);
    if(pointerId!==null){
      const dx=e.clientX-dragX,dy=e.clientY-dragY;if(Math.hypot(e.clientX-downX,e.clientY-downY)>6)moved=true;
      if(moved){dragging=true;hovered=-1;dragYaw+=dx*.008;dragPitch=Math.max(-1.15,Math.min(1.15,dragPitch+dy*.006));inertia=dx*.00018;}
      dragX=e.clientX;dragY=e.clientY;
    }
    draw();
  });
  function release(e,cancelled=false){
    if(pointerId===null||e.pointerId!==pointerId)return;const id=pointerId;pointerId=null;
    if(!cancelled&&!moved){const p=localPointer(e);selected=hitTest(p.x,p.y,p.touch);options.selectedIndex=selected;events.onSelect?.(nodeInfo(selected));}
    dragging=false;if(cancelled||e.pointerType==='touch'){pointer=null;hovered=-1;}
    if(canvas.hasPointerCapture?.(id))canvas.releasePointerCapture(id);draw();schedule();
  }
  on(canvas,'pointerup',e=>release(e));on(canvas,'pointercancel',e=>release(e,true));on(canvas,'lostpointercapture',e=>release(e,true));
  on(canvas,'pointerleave',()=>{if(pointerId===null){pointer=null;hovered=-1;draw();}});
  if(typeof document!=='undefined')on(document,'visibilitychange',()=>{visible=!document.hidden;stop();schedule();});
  if(typeof window!=='undefined'&&'IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{inViewport=entries[0].isIntersecting;stop();schedule();},{threshold:.05});observer.observe(canvas);cleanups.push(()=>observer.disconnect());}
  if(typeof window!=='undefined'&&'ResizeObserver' in window){const observer=new ResizeObserver(size);observer.observe(canvas);cleanups.push(()=>observer.disconnect());}
  else if(typeof window!=='undefined')on(window,'resize',size);

  size();update(initial);
  return {
    update,
    destroy(){destroyed=true;stop();cleanups.forEach(fn=>fn());for(const b of buffers)try{gl.deleteBuffer(b);}catch{};buffers.clear();},
    snapshot(){
      return {
        surface:'brain3d',renderer:'webgl',brainVertices:brain.surfaceCount,brainLines:(brain.wireCount+brain.fibreCount)/2,
        camera:{...camera},rotation:{yaw:dragYaw,pitch:dragPitch},hovered,selected,activeHub,
        points:points.length,knowledgeStars:points.filter(p=>p.kind==='node').length,edges:edges.length,frame,mode,
        opening:opening/openingSeconds,visiblePoints:projected.filter(p=>p.appear>.01).length,
        projected:projected.map((p,i)=>({x:p.x,y:p.y,appear:p.appear,...nodeInfo(i)})),
      };
    },
  };
}
