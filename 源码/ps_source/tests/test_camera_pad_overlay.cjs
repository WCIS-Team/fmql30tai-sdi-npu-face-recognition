const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
let now=100,interval,fetches=0,draws=0;const nodes=new Map(),labels=[];
function node(id){if(!nodes.has(id))nodes.set(id,{dataset:{},textContent:'',hidden:false,classList:{toggle(){}},replaceChildren(){},after(){},append(){},removeAttribute(){},getContext:()=>({drawImage(){draws++;labels.length=0;},strokeRect(){},fillText:t=>labels.push(t),fillRect(){},beginPath(){},arc(){},fill(){},measureText:t=>({width:t.length*9})})});return nodes.get(id);}
const frame={frame_id:9,session:'s',boot_id:'b',source_rgb565_sha256:'hash',width:960,height:540};
const result={camera_frame:frame,faces:[{box:[10,80,110,180],score:.9,landmarks:[]}],identities:[],face_count:1,elapsed_ms:600,
 presentation_attack_detection:{...frame,status:'model_live',frame_age_ms:600,max_age_ms:3000}};
const ctx={console,Date,Uint8Array,performance:{now:()=>now},document:{hidden:false,getElementById:node,createElement:()=>({style:{}}),addEventListener(){}},
 setTimeout:()=>1,clearTimeout(){},setInterval:fn=>{interval=fn;},
 Image:class{constructor(){this.naturalWidth=960;this.naturalHeight=540;}set src(v){queueMicrotask(()=>this.onload());}},
 fetch:async path=>path.includes('/status')?{ok:true,json:async()=>({ready:true,session:'s',frame_id:9})}:(fetches++,{status:200,ok:true,json:async()=>({entry:{image:'fixture',result}})})};
ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(require.resolve('../npu_photo/camera_panel.js'),'utf8'),ctx);
(async()=>{
 await new Promise(resolve=>setImmediate(resolve));assert.match(labels[1],/模型判断为真人/);const initial=draws;
 interval();assert.equal(draws,initial,'Unchanged PAD labels must not redraw the full image');
 now+=2500;interval();assert.match(labels[1],/过期/);assert.equal(draws,initial+1,'Expiry must replace the text already painted into the image');
 assert.equal(fetches,1,'Updating overlay freshness must not run another inference');
 await ctx.pauseCameraDetection();assert.match(labels[1],/暂停/);assert.equal(fetches,1);assert.equal(node('camCanvas').dataset.frame,'9');
 console.log('Canvas PAD freshness, pause invalidation, same-frame retention and no extra inference passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
