const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {detectionDelay}=require('../npu_photo/camera_panel.js');
assert.equal(detectionDelay(0,0,0),1000);
assert.equal(detectionDelay(0,1,1),50);
assert.equal(detectionDelay(0,4,1),50);
assert.equal(detectionDelay(1,0,0),500);
assert.equal(detectionDelay(2,0,0),1000);
assert.equal(detectionDelay(20,0,1),4500);
assert.notEqual(detectionDelay(1,0,0),detectionDelay(1,0,1));
const nodes=new Map(),timers=new Map();let now=100,id=0,status=200,calls=0,interval;
function node(name){if(!nodes.has(name))nodes.set(name,{textContent:'',dataset:{},classList:{toggle(){}},replaceChildren(){},after(){},append(){},getContext(){return {drawImage(){}};}});return nodes.get(name);}
const frame={width:960,height:540,frame_id:7,session:'s',boot_id:'b',source_rgb565_sha256:'h'};
const result={camera_frame:frame,faces:[],identities:[],face_count:1,elapsed_ms:800,presentation_attack_detection:{...frame,status:'model_live',frame_age_ms:200,max_age_ms:3000}};
const ctx={console,Uint8Array,Date,performance:{now:()=>now},
 document:{hidden:false,getElementById:node,createElement:()=>({style:{}}),addEventListener(){}},
 setTimeout:(fn,delay)=>{timers.set(++id,{fn,delay});return id;},clearTimeout:i=>timers.delete(i),setInterval:fn=>{interval=fn;},
 Image:class {constructor(){this.naturalWidth=960;this.naturalHeight=540;}set src(v){queueMicrotask(()=>this.onload());}},
 fetch:async path=>{if(path.includes('/status'))return {ok:true,json:async()=>({ready:true,session:'s',frame_id:8})};calls++;return {status,ok:status===200,json:async()=>status===200?{entry:{image:'fixture',result}}:{error:'busy'}};}
};ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(require.resolve('../npu_photo/camera_panel.js'),'utf8'),ctx);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function detectTick(){const [key,timer]=[...timers].find(([,t])=>t.delay!==250);timers.delete(key);now+=timer.delay;timer.fn();await flush();}
(async()=>{
 await flush();assert.match(node('camPad').textContent,/模型判断为真人/);
 status=409;await detectTick();assert.equal(calls,2);assert.match(node('camPad').textContent,/模型判断为真人/,'A temporary conflict must not overwrite a valid result');assert.match(node('camMessage').textContent,/资源暂被占用/);
 now+=3100;interval();assert.match(node('camPad').textContent,/过期/,'Conflict must not extend the evidence lifetime');
 status=200;await detectTick();assert.match(node('camPad').textContent,/模型判断为真人/);
 await ctx.pauseCameraDetection();status=409;await node('camOnce').onclick();assert.match(node('camPad').textContent,/本次未开始/);assert(![...timers.values()].some(t=>t.delay!==250),'Manual conflict must not silently enable automatic detection');
 console.log('Contention backoff, jitter, valid-result preservation, expiry, recovery and manual conflict passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
