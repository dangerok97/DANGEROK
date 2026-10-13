/** ORA Vision cinematic scan — no stock images, no fake depth/telemetry.
 * One-shot compositor animations, pointer-transparent, reduced-motion safe. */
export const SCAN_CINEMATIC_STYLES = `
.vx-scan-cinematic{z-index:18;pointer-events:none;overflow:hidden;
 color:#dffaff;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;}
.vx-scan-cinematic .vx-scan-surface-svg{filter:none;pointer-events:none;}
.vx-scan-cinematic .vx-scan-trace{fill:none;vector-effect:non-scaling-stroke;
 stroke-linejoin:round;stroke-linecap:round;filter:none;}
.vx-scan-cinematic .vx-scan-trace.is-pixel{stroke:#b6faff;stroke-width:1.7;
 stroke-dasharray:1000;stroke-dashoffset:1000;
 animation:vx2-outline 1.32s cubic-bezier(.17,.8,.24,1) .1s forwards;}
.vx-scan-cinematic .vx-scan-trace.is-box{stroke:rgba(141,202,222,.77);
 stroke-width:1.25;stroke-dasharray:8 10;animation:none;}
.vx-scan-cinematic .vx-hud-fill{opacity:0;animation:vx2-fill .6s ease .68s both;}
.vx-scan-cinematic .vx-hud-grid{opacity:0;animation:vx2-grid .7s ease .79s both;}
.vx-scan-cinematic .vx-hud-glow{fill:none;stroke:#37deff;
 stroke-width:7;vector-effect:non-scaling-stroke;
 animation:vx2-glow .83s ease .52s both;}
.vx-scan-cinematic .vx-hud-tracer{fill:none;stroke:#efffff;stroke-width:3;
 vector-effect:non-scaling-stroke;stroke-linecap:round;
 stroke-dasharray:165 835;stroke-dashoffset:1000;
 animation:vx2-tracer 1.54s ease-in-out .2s both;}
.vx-scan-cinematic .vx-hud-sweep{animation:vx2-pass 1.5s ease-in-out .17s both;
 will-change:transform;}
.vx-scan-cinematic .vx-hud-corners path{fill:none;stroke:#80ecff;
 stroke-width:1.65;vector-effect:non-scaling-stroke;
 animation:vx2-lock .4s ease-out .73s both;}
.vx-scan-cinematic.vx-scan-estimated .vx-hud-corners path{
 stroke:#8dadbf;stroke-width:1.05;stroke-dasharray:4 4;animation-delay:.1s;}
.vx-scan-cinematic .vx-hud-nodes{animation:vx2-lock .43s ease 1.02s both;}
.vx-scan-cinematic .vx-hud-node-ring{fill:#071827;fill-opacity:.75;
 stroke:#8cefff;stroke-width:1.25;vector-effect:non-scaling-stroke;}
.vx-scan-cinematic .vx-hud-node-core{fill:#e5ffff;}
.vx-scan-cinematic .vx-hud-reticle{fill:none;stroke:#89e5f2;
 stroke-width:1.25;vector-effect:non-scaling-stroke;
 animation:vx2-lock .43s ease 1.02s both;}
.vx-scan-cinematic .vx-hud-radial{stroke-dasharray:3 9;opacity:.75;
 transform-box:fill-box;transform-origin:center;
 animation:vx2-orbit 1.65s ease-out 1.08s both;}
.vx-scan-cinematic .vx-hud-center{fill:#dafdff;stroke:none;}
.vx-scan-cinematic .vx-hud-leader{fill:none;stroke:#96cde6;
 stroke-width:.85;vector-effect:non-scaling-stroke;
 animation:vx2-lock .4s ease 1.11s both;}
.vx-scan-cinematic .vx-scan-readout{position:absolute;z-index:1;
 width:197px;max-width:calc(100% - 14px);padding:8px 11px;
 background:linear-gradient(110deg,rgba(2,18,33,.93),rgba(4,53,72,.82));
 border:1px solid rgba(113,230,255,.57);border-left:2px solid #80ebff;
 box-shadow:0 10px 35px rgba(0,8,25,.48),inset 0 1px rgba(162,255,255,.14);
 clip-path:polygon(0 0,calc(100% - 12px) 0,100% 12px,100% 100%,0 100%);
 color:#d5f6fc;pointer-events:none;backdrop-filter:blur(6px);
 animation:vx2-readout .52s cubic-bezier(.17,.77,.21,1) 1.08s both;}
.vx-scan-cinematic.vx-scan-estimated .vx-scan-readout{
 border-color:rgba(131,181,200,.55);border-left-color:#96b6c9;}
.vx-scan-cinematic .vx-scan-readout-top{display:flex;gap:5px;
 align-items:center;font-size:8px;font-weight:600;letter-spacing:.8px;
 white-space:nowrap;color:#9bdae9;}
.vx-scan-cinematic .vx-scan-readout-top b{color:#efffff;}
.vx-scan-cinematic .vx-scan-readout-led{flex:none;width:5px;height:5px;
 border-radius:1px;background:#9affff;box-shadow:0 0 8px #5bfcff;}
.vx-scan-cinematic .vx-scan-readout-bars{margin-left:auto;
 display:flex;align-items:end;gap:2px;height:9px;}
.vx-scan-cinematic .vx-scan-readout-bars i{width:2px;height:3px;background:#8dcde2;}
.vx-scan-cinematic .vx-scan-readout-bars i:nth-child(2){height:7px;}
.vx-scan-cinematic .vx-scan-readout-bars i:nth-child(3){height:9px;}
.vx-scan-cinematic .vx-scan-readout-bars i:nth-child(4){height:5px;}
.vx-scan-cinematic .vx-scan-readout-divider{height:1px;margin:6px 0 6px;
 background:linear-gradient(90deg,rgba(146,235,255,.72),transparent);}
.vx-scan-cinematic .vx-scan-readout>strong{display:block;
 color:#f0feff;font-size:11px;font-weight:650;letter-spacing:.85px;line-height:1.35;}
.vx-scan-cinematic .vx-scan-readout>small{display:block;color:#b6d4de;
 font-size:9px;line-height:1.3;margin:3px 0 6px;letter-spacing:.13px;}
.vx-scan-cinematic .vx-scan-readout-category{display:block;padding-top:5px;
 font-size:8px;letter-spacing:1.15px;color:#8cdeee;font-weight:650;
 border-top:1px solid rgba(113,181,204,.24);}
.vx-stage.vx-scan-locked .vx-canvas,
.vx-stage.vx-scan-locked .vx-bp3d-panel iframe{
 animation:vx2-model-enter 1.1s ease-out both;}
@keyframes vx2-outline{0%{stroke-dashoffset:1000;opacity:.1}
 78%{opacity:1}100%{stroke-dashoffset:0;opacity:1}}
@keyframes vx2-fill{from{opacity:0}to{opacity:1}}
@keyframes vx2-grid{from{opacity:0}to{opacity:.6}}
@keyframes vx2-glow{0%{opacity:0}55%{opacity:.8}100%{opacity:.23}}
@keyframes vx2-tracer{0%{stroke-dashoffset:1000;opacity:0}
 20%{opacity:1}80%{opacity:1}100%{opacity:0;stroke-dashoffset:0}}
@keyframes vx2-pass{0%{opacity:0;transform:translateY(0)}
 17%{opacity:1}75%{opacity:.82}
 100%{opacity:0;transform:translateY(var(--vx-scan-travel,400px))}}
@keyframes vx2-lock{from{opacity:0}to{opacity:.95}}
@keyframes vx2-orbit{from{transform:rotate(-80deg)}to{transform:rotate(0deg)}}
@keyframes vx2-readout{from{opacity:0;transform:translateY(8px)}
 to{opacity:1;transform:translateY(0)}}
@keyframes vx2-model-enter{0%{opacity:0;filter:brightness(1.6) blur(2px)}
 45%{opacity:.1;filter:brightness(1.4) blur(.7px)}
 100%{opacity:1;filter:none}}
@media(max-width:650px){
 .vx-scan-cinematic .vx-scan-readout{width:160px;padding:7px 8px;backdrop-filter:blur(3px);}
 .vx-scan-cinematic .vx-scan-readout-top{font-size:7px;letter-spacing:.35px;}
 .vx-scan-cinematic .vx-scan-readout>strong{font-size:10px;letter-spacing:.25px;}
 .vx-scan-cinematic .vx-scan-readout>small{font-size:8px;}
 .vx-scan-cinematic .vx-scan-readout-category{font-size:7px;}
}
@media(prefers-reduced-motion:reduce){
 .vx-scan-cinematic .vx-scan-trace.is-pixel{animation:none!important;stroke-dashoffset:0!important;}
 .vx-scan-cinematic .vx-hud-tracer,.vx-scan-cinematic .vx-hud-sweep{display:none!important;}
 .vx-scan-cinematic .vx-hud-fill,.vx-scan-cinematic .vx-hud-grid,
 .vx-scan-cinematic .vx-hud-glow,.vx-scan-cinematic .vx-hud-corners path,
 .vx-scan-cinematic .vx-hud-nodes,.vx-scan-cinematic .vx-hud-reticle,
 .vx-scan-cinematic .vx-hud-leader,.vx-scan-cinematic .vx-scan-readout,
 .vx-stage.vx-scan-locked .vx-canvas,
 .vx-stage.vx-scan-locked .vx-bp3d-panel iframe{
 animation:none!important;opacity:1!important;transform:none!important;filter:none!important;}
}
`;
