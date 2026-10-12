function utf8Bytes(text) {
  const out=[];
  for(const character of text){
    let cp=character.codePointAt(0);
    if(cp>=0xd800&&cp<=0xdfff)cp=0xfffd;
    if(cp<0x80)out.push(cp);
    else if(cp<0x800)out.push(0xc0|(cp>>>6),0x80|(cp&63));
    else if(cp<0x10000)out.push(0xe0|(cp>>>12),0x80|((cp>>>6)&63),0x80|(cp&63));
    else out.push(0xf0|(cp>>>18),0x80|((cp>>>12)&63),0x80|((cp>>>6)&63),0x80|(cp&63));
  }
  return out;
}
function sha256Bytes(input) {
  const bytes=input.slice(),length=bytes.length*8;
  bytes.push(0x80);while(bytes.length%64!==56)bytes.push(0);
  const hi=Math.floor(length/4294967296),lo=length>>>0;
  for(let shift=24;shift>=0;shift-=8)bytes.push((hi>>>shift)&255);
  for(let shift=24;shift>=0;shift-=8)bytes.push((lo>>>shift)&255);
  const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const rotr=(x,n)=>(x>>>n)|(x<<(32-n));
  for(let offset=0;offset<bytes.length;offset+=64){
    const w=new Array(64);
    for(let j=0;j<16;j++){const p=offset+j*4;w[j]=((bytes[p]<<24)|(bytes[p+1]<<16)|(bytes[p+2]<<8)|bytes[p+3])>>>0;}
    for(let j=16;j<64;j++){const a=w[j-15],b=w[j-2];const s0=rotr(a,7)^rotr(a,18)^(a>>>3),s1=rotr(b,17)^rotr(b,19)^(b>>>10);w[j]=(w[j-16]+s0+w[j-7]+s1)>>>0;}
    let [a,b,c,d,e,f,g,q]=h;
    for(let j=0;j<64;j++){const s1=rotr(e,6)^rotr(e,11)^rotr(e,25),ch=(e&f)^(~e&g),t1=(q+s1+ch+k[j]+w[j])>>>0,s0=rotr(a,2)^rotr(a,13)^rotr(a,22),maj=(a&b)^(a&c)^(b&c),t2=(s0+maj)>>>0;q=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;}
    const values=[a,b,c,d,e,f,g,q];for(let j=0;j<8;j++)h[j]=(h[j]+values[j])>>>0;
  }
  return h.map(x=>x.toString(16).padStart(8,"0")).join("");
}
function sha1Bytes(input) {
  const bytes=input.slice(),length=bytes.length*8;bytes.push(0x80);while(bytes.length%64!==56)bytes.push(0);
  const hi=Math.floor(length/4294967296),lo=length>>>0;
  for(let shift=24;shift>=0;shift-=8)bytes.push((hi>>>shift)&255);
  for(let shift=24;shift>=0;shift-=8)bytes.push((lo>>>shift)&255);
  const h=[0x67452301,0xefcdab89,0x98badcfe,0x10325476,0xc3d2e1f0];
  const rotl=(x,n)=>(x<<n)|(x>>>(32-n));
  for(let offset=0;offset<bytes.length;offset+=64){
    const w=new Array(80);for(let j=0;j<16;j++){const p=offset+j*4;w[j]=((bytes[p]<<24)|(bytes[p+1]<<16)|(bytes[p+2]<<8)|bytes[p+3])>>>0;}
    for(let j=16;j<80;j++)w[j]=rotl(w[j-3]^w[j-8]^w[j-14]^w[j-16],1)>>>0;
    let [a,b,c,d,e]=h;
    for(let j=0;j<80;j++){let f,k;if(j<20){f=(b&c)|(~b&d);k=0x5a827999;}else if(j<40){f=b^c^d;k=0x6ed9eba1;}else if(j<60){f=(b&c)|(b&d)|(c&d);k=0x8f1bbcdc;}else{f=b^c^d;k=0xca62c1d6;}const t=(rotl(a,5)+f+e+k+w[j])>>>0;e=d;d=c;c=rotl(b,30)>>>0;b=a;a=t;}
    const values=[a,b,c,d,e];for(let j=0;j<5;j++)h[j]=(h[j]+values[j])>>>0;
  }
  return h.map(x=>x.toString(16).padStart(8,"0")).join("");
}
function collectTargetedReports(config, previous, packet) {
 const clone = value => JSON.parse(JSON.stringify(value));
 const normalizeTime = value => {
  const match = typeof value === "string" && /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z$/.exec(value);
  if (!match || !Number.isFinite(Date.parse(value))) throw new Error("INVALID_UTC_TIMESTAMP");
  return match[1] + "." + (match[2] || "").padEnd(9, "0") + "Z";
 };
 const prefixes = {
  situation: "ORA_SITUATION_FIRST_CYCLE ",
  autonomy: "ORA_AUTONOMY_COMPLETION_SUMMARY ",
  public: "ORA_PHASE1_READ_EVAL "
 };
 const progressPrefix = "ORA_AUTONOMY_COMPLETION_CASE ";
 const isRecord = value => value !== null && typeof value === "object" && !Array.isArray(value);
 const sha40 = /^[a-f0-9]{40}$/;
 const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
 if (!isRecord(config) || !isRecord(config.publication) ||
     !Array.isArray(config.requiredKinds) || config.requiredKinds.length === 0 ||
     new Set(config.requiredKinds).size !== config.requiredKinds.length ||
     config.requiredKinds.some(kind => !Object.hasOwn(prefixes, kind))) throw new Error("COLLECTOR_CONFIG_INVALID");
 const publication = config.publication;
 if (!sha40.test(publication.code_revision || "") || !sha40.test(publication.tree || "") ||
     ["projectId","environmentId","serviceId","deploymentId"].some(key => !uuid.test(publication[key] || ""))) throw new Error("COLLECTOR_PUBLICATION_INVALID");
 const created = normalizeTime(publication.created_at);
 if (!Array.isArray(config.requiredAutonomyScenarios) ||
     config.requiredAutonomyScenarios.length === 0 ||
     new Set(config.requiredAutonomyScenarios).size !== config.requiredAutonomyScenarios.length ||
     config.requiredAutonomyScenarios.some(name => typeof name !== "string" || !name.trim())) throw new Error("COLLECTOR_SCENARIOS_INVALID");
 const canonicalConfig = {
  publication: {
   code_revision:publication.code_revision,tree:publication.tree,
   projectId:publication.projectId,environmentId:publication.environmentId,
   serviceId:publication.serviceId,deploymentId:publication.deploymentId,
   created_at:publication.created_at
  },
  requiredKinds:config.requiredKinds.slice(),
  requiredAutonomyScenarios:config.requiredAutonomyScenarios.slice()
 };
 const fingerprint = sha256Bytes(utf8Bytes(JSON.stringify(canonicalConfig)));
 if (previous && previous.config_sha256 !== fingerprint) throw new Error("COLLECTOR_CONFIG_CHANGED");
 const state = previous ? clone(previous) : {
  schema:"ora.targeted_collector.v1",config:canonicalConfig,config_sha256:fingerprint,
  snapshots:[],logs:[],next_sequence:0,blocking_errors:[],read_errors:[],coverage:[],coverage_target:created,
  statuses:[],reports:{},progress:[]
 };
 const issue = (code, detail={}) => ({code,...detail});
 if (packet !== null && packet !== undefined) {
  if (!isRecord(packet)) throw new Error("COLLECTOR_PACKET_INVALID");
  const snapshot = {
   index:state.snapshots.length,packet_sha256:sha256Bytes(utf8Bytes(JSON.stringify(packet))),
   original_packet:clone(packet),accepted:false,issues:[]
  };
  state.snapshots.push(snapshot);
  const fail = (code, field) => {
   const item = issue(code,{snapshot:snapshot.index,...(field?{field}:{})});
   snapshot.issues.push(item);state.blocking_errors.push(item);
  };
  const receipt=packet.receipt,mcp=packet.mcp,args=receipt?.arguments,structured=mcp?.structuredContent;
  let begin,end,received;
  if (!isRecord(receipt)||!isRecord(args)||!isRecord(mcp)) fail("MISSING_PACKET_BOUNDARY");
  else {
   for (const field of ["projectId","environmentId","serviceId","deploymentId"]) if (args[field]!==publication[field]) fail("REQUEST_BINDING_MISMATCH",field);
   if (args.limit!==500 || !Array.isArray(args.types) || !args.types.includes("deploy") ||
       args.types.some(type=>type!=="deploy"&&type!=="build")) fail("REQUEST_SCOPE_INVALID");
   try {
    normalizeTime(receipt.requested_at);
    received=normalizeTime(receipt.received_at);
    begin=normalizeTime(args.startDate);
    end=args.endDate?normalizeTime(args.endDate):received;
    if(end>received) end=received;
    if(begin>end || begin<created) fail("REQUEST_WINDOW_INVALID");
   } catch {fail("REQUEST_TIMESTAMP_INVALID");}
   if (mcp.isError===true) state.read_errors.push(issue("MCP_READ_ERROR",{snapshot:snapshot.index}));
   else if (!isRecord(structured)) fail("MISSING_STRUCTURED_RESPONSE");
   else {
    if(structured.scope!=="deployment") fail("RESPONSE_SCOPE_MISMATCH");
    for(const field of ["environmentId","serviceId","deploymentId"]) if(structured[field]!==publication[field]) fail("RESPONSE_BINDING_MISMATCH",field);
    if(structured.projectId!==undefined && structured.projectId!==publication.projectId) fail("RESPONSE_BINDING_MISMATCH","projectId");
    if(structured.code_revision!==undefined && structured.code_revision!==publication.code_revision) fail("RESPONSE_REVISION_MISMATCH");
    if(!Array.isArray(structured.deploy)) fail("LOG_ROWS_MISSING");
    else if(structured.deploy.length>500) fail("LOG_LIMIT_EXCEEDED");
    else {
     for(const row of structured.deploy) {
      try {
       if(!isRecord(row)||typeof row.message!=="string") throw new Error("BAD_ROW");
       const at=normalizeTime(row.timestamp);
       if(begin && end && (at<begin || at>end)) throw new Error("OUT_OF_WINDOW");
      } catch {fail("INVALID_LOG_ROW");break;}
     }
    }
    if(snapshot.issues.length===0) {
     snapshot.accepted=true;
     snapshot.log_rows=structured.deploy.length;
     snapshot.saturated=structured.deploy.length===500;
     state.coverage_target=end>state.coverage_target?end:state.coverage_target;
     if(!snapshot.saturated) state.coverage.push({start:begin,end,snapshot:snapshot.index});
     state.statuses.push({status:structured.status,received_at:received,snapshot:snapshot.index});
     const cachedCounts=new Map();
     for(const cached of state.logs) cachedCounts.set(cached.identity,(cachedCounts.get(cached.identity)||0)+1);
     const packetCounts=new Map();
     for(const row of structured.deploy) {
      const identity=JSON.stringify([row.timestamp,row.message]);
      const occurrence=(packetCounts.get(identity)||0)+1;
      packetCounts.set(identity,occurrence);
      if(occurrence>(cachedCounts.get(identity)||0)) state.logs.push({
       identity,occurrence,sequence:state.next_sequence++,row:clone(row),first_snapshot:snapshot.index
      });
     }
    }
   }
  }
 }
 const rows=state.logs.slice().sort((a,b)=>normalizeTime(a.row.timestamp).localeCompare(normalizeTime(b.row.timestamp))||a.sequence-b.sequence);
 const markerPrefixes=[...Object.values(prefixes),progressPrefix];
 const candidates={situation:[],autonomy:[],public:[]};
 for(let start=0;start<rows.length;start++) {
  const row=rows[start].row;
  const kind=Object.keys(prefixes).find(key=>row.message.startsWith(prefixes[key]));
  if(!kind) continue;
  let body=row.message.slice(prefixes[kind].length),end=start,parsed,complete=false,boundaryReason=null;
  for(;;) {
   try {parsed=JSON.parse(body);complete=true;} catch {}
   if(complete) break;
   if(end+1>=rows.length) {boundaryReason="AWAITING_CONTINUATION";break;}
   if(markerPrefixes.some(prefix=>rows[end+1].row.message.startsWith(prefix))) {boundaryReason="NEXT_MARKER_BEFORE_COMPLETE_JSON";break;}
   body+=rows[++end].row.message;
  }
  const candidate={
   kind,complete:complete&&isRecord(parsed),first_timestamp:row.timestamp,last_timestamp:rows[end].row.timestamp,
   fragments:end-start+1,first_sequence:rows[start].sequence,
   raw_body:body,representation:"message fragments concatenated without separators",
   ...(complete&&!isRecord(parsed)?{error:"REPORT_NOT_OBJECT"}:boundaryReason?{error:boundaryReason}:{})
  };
  if(candidate.complete) {
   const text=body+"\n",bytes=utf8Bytes(text);
   candidate.text=text;candidate.parsed=parsed;candidate.bytes=bytes.length;
   candidate.sha256=sha256Bytes(bytes);
   candidate.git_blob_sha1=sha1Bytes(utf8Bytes("blob "+bytes.length+"\0").concat(bytes));
  }
  candidates[kind].push(candidate);
 }
 state.reports=candidates;
 const progress=[];
 for(const cached of rows) if(cached.row.message.startsWith(progressPrefix)) {
  let parsed=null,error=null;
  try {parsed=JSON.parse(cached.row.message.slice(progressPrefix.length));} catch {error="INCOMPLETE_PROGRESS_JSON";}
  progress.push({timestamp:cached.row.timestamp,raw_message:cached.row.message,parsed,error});
 }
 state.progress=progress;
 const reportIssues=[];
 const requiredReports={};
 for(const kind of canonicalConfig.requiredKinds) {
  const found=candidates[kind];
  if(found.length===0) {reportIssues.push(issue("REQUIRED_REPORT_MISSING",{kind}));continue;}
  if(found.length!==1) {reportIssues.push(issue("REQUIRED_REPORT_DUPLICATE",{kind,count:found.length}));continue;}
  const candidate=found[0];
  if(!candidate.complete) {reportIssues.push(issue("REQUIRED_REPORT_INCOMPLETE",{kind,reason:candidate.error}));continue;}
  const value=candidate.parsed;
  requiredReports[kind]=candidate;
  if((kind==="situation"||kind==="autonomy") && value.code_revision!==publication.code_revision) reportIssues.push(issue("REPORT_REVISION_MISMATCH",{kind}));
  if(kind==="situation"||kind==="autonomy") {
   if(typeof value.passed!=="boolean") reportIssues.push(issue("REPORT_VERDICT_MISSING",{kind}));
  } else if(!isRecord(value.verdict)||typeof value.verdict.passed!=="boolean") reportIssues.push(issue("REPORT_VERDICT_MISSING",{kind}));
  if(kind==="autonomy") {
   if(!Array.isArray(value.cases)||value.cases.some(c=>!isRecord(c)||typeof c.scenario!=="string"||typeof c.passed!=="boolean")) {
    reportIssues.push(issue("AUTONOMY_CASES_INVALID"));
   } else {
    const actual=value.cases.map(c=>c.scenario);
    const expected=canonicalConfig.requiredAutonomyScenarios;
    if(actual.length!==expected.length || new Set(actual).size!==actual.length ||
       actual.slice().sort().some((name,index)=>name!==expected.slice().sort()[index])) reportIssues.push(issue("AUTONOMY_SCENARIO_SET_MISMATCH",{expected_count:expected.length,observed_count:actual.length}));
    if(value.passed===true && value.cases.some(c=>c.passed!==true)) reportIssues.push(issue("AUTONOMY_VERDICT_INCONSISTENT"));
    const actualProgress=progress.filter(p=>isRecord(p.parsed)&&typeof p.parsed.scenario==="string");
    for(const p of actualProgress) {
     if(!expected.includes(p.parsed.scenario)) reportIssues.push(issue("OUT_OF_SCOPE_AUTONOMY_PROGRESS"));
     const final=value.cases.find(c=>c.scenario===p.parsed.scenario);
     if(final && (p.parsed.passed!==final.passed || p.parsed.model_attempts!==final.model_attempts || p.parsed.model_http_requests!==final.model_http_requests)) reportIssues.push(issue("PROGRESS_FINAL_MISMATCH"));
    }
   }
  }
 }
 const coverage=state.coverage.slice().sort((a,b)=>a.start.localeCompare(b.start)||a.end.localeCompare(b.end));
 let cursor=created;
 const gaps=[];
 for(const interval of coverage) {
  if(interval.end<=cursor) continue;
  if(interval.start>cursor) gaps.push({startDate:cursor,endDate:interval.start});
  if(interval.end>cursor) cursor=interval.end;
 }
 if(cursor<state.coverage_target) gaps.push({startDate:cursor,endDate:state.coverage_target});
 const latest=state.statuses.slice().sort((a,b)=>a.received_at.localeCompare(b.received_at)||a.snapshot-b.snapshot).at(-1);
 const terminalStatuses=["CRASHED","FAILED","REMOVED","SKIPPED"];
 const terminal=!!latest&&terminalStatuses.includes(latest.status);
 const reportsComplete=state.blocking_errors.length===0 && reportIssues.length===0;
 const collectionComplete=reportsComplete&&terminal&&gaps.length===0;
 const reportedPasses=Object.fromEntries(canonicalConfig.requiredKinds.map(kind=>[
  kind,requiredReports[kind]?(kind==="public"?requiredReports[kind].parsed.verdict?.passed:requiredReports[kind].parsed.passed):null
 ]));
 state.summary={
  requiredKinds:canonicalConfig.requiredKinds.slice(),
  requiredAutonomyScenarios:canonicalConfig.requiredAutonomyScenarios.slice(),
  reports_complete:reportsComplete,collection_complete:collectionComplete,
  current_deployment_status:latest?.status??null,terminal_observed:terminal,
  required_report_passes:reportedPasses,
  required_reports_claim_pass:collectionComplete&&Object.values(reportedPasses).every(value=>value===true),
  semantic_acceptance:"not_assessed_by_collector",
  full_laundry_outcome_passed:requiredReports.situation?.parsed.full_laundry_outcome_passed??null,
  blocking_errors:state.blocking_errors.slice(),report_issues:reportIssues,
  read_error_count:state.read_errors.length,
  history_coverage_complete:gaps.length===0,history_gaps:gaps,
  next_history_query:gaps.length?{...gaps[0],limit:500,requires_smaller_windows_if_saturated:true}:null,
  raw_snapshot_count:state.snapshots.length,cached_log_rows:state.logs.length,
  out_of_scope_reports:Object.keys(prefixes).filter(kind=>!canonicalConfig.requiredKinds.includes(kind)).map(kind=>({
   kind,candidates:candidates[kind].length,complete:candidates[kind].filter(c=>c.complete).length,preserved:true,affects_required_verdict:false
  }))
 };
 return state;
}
return {collectTargetedReports,utf8Bytes,sha256Bytes,sha1Bytes};