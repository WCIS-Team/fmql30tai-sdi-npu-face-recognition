// Regression: a slow/paused detector must never block the live video status.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(),events={},timers=new Map();let timerId=0,now=100,sourceFrames=0,inferences=0,resolveFirst,ready=true,draws=0;
function node(id){if(!nodes.has(id))nodes.set(id,{dataset:{},hidden:true,textContent:'',src:'',classList:{toggle(){}},replaceChildren(){},after(){},append(){},removeAttribute(key){this[key]='';},getContext(){return {drawImage(){draws++;}};}});return nodes.get(id);}
const result=()=>({entry:{image:'data:image/jpeg;base64,test',result:{camera_frame:{width:960,height:540,frame_id:1,session:'a',boot_id:'b',source_rgb565_sha256:'hash'},presentation_attack_detection:{status:'not_applicable',reason:'no_face',frame_id:1,session:'a',boot_id:'b',source_rgb565_sha256:'hash',frame_age_ms:100,max_age_ms:3000},faces:[],identities:[],face_count:0,elapsed_ms:400}}});
const context={document:{hidden:false,getElementById:node,createElement:()=>({style:{}}),addEventListener:(name,fn)=>events[name]=fn},
 performance:{now:()=>now},Date,console,Uint8Array,
 setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),setInterval:()=>0,
 Image:class {constructor(){this.naturalWidth=960;this.naturalHeight=540;}set src(value){queueMicrotask(()=>this.onload());}},
 fetch:async path=>{
  if(path==='/api/camera/status')return {ok:true,json:async()=>({ready,session:'a',frame_id:10*(++sourceFrames),encoded:sourceFrames})};
  assert.equal(path,'/api/recognize-camera');inferences++;
  if(inferences===1)return new Promise(resolve=>resolveFirst=()=>resolve({ok:true,json:async()=>result()}));
  return {ok:true,json:async()=>result()};
 }};
context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../npu_photo/camera_panel.js'),'utf8'),context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function statusTick(){const entry=[...timers].find(([,value])=>value.delay===250);assert(entry,'Live status must have its own timer');timers.delete(entry[0]);now+=250;entry[1].fn();await flush();}
(async()=>{
 await flush();assert.equal(inferences,1);const initial=node('camVideo').src;assert(initial.startsWith('/api/camera/stream.mjpg'));
 await statusTick();assert.equal(node('camVideo').dataset.publishedFrame,'20');assert.equal(inferences,1);assert.equal(draws,0,'Unfinished inference cannot redraw the detection frame');
 assert(node('camCaption').textContent.includes('4.0'),'Skipped source IDs must not inflate the received frame rate');
 resolveFirst();await flush();assert.equal(draws,1);assert.equal(node('camCanvas').dataset.frame,'1');
 await context.pauseCameraDetection();await statusTick();assert.equal(node('camVideo').src,initial);assert.equal(node('camVideo').hidden,false);assert.equal(inferences,1,'Pause must not enqueue another inference');assert(node('camPad').textContent.includes('暂停'));
 await node('camOnce').onclick();await flush();assert.equal(inferences,2);assert.equal(draws,2);assert(node('camResultCaption').textContent.includes('检测已暂停'));assert(node('camPad').textContent.includes('未检测到人脸'),'One-shot detection must still show PAD while auto mode stays paused');
 node('camVideo').onerror();await statusTick();assert.equal(node('camVideo').hidden,true,'Healthy source metadata must not unhide a broken stream');
 context.document.hidden=true;events.visibilitychange();assert.equal(node('camVideo').src,'');
 context.document.hidden=false;events.visibilitychange();await flush();assert.equal(inferences,2,'Returning to a paused tab must not start detection');
 ready=false;await statusTick();assert.equal(node('camVideo').hidden,true,'Stale source must hide live video');assert.equal(node('camCanvas').dataset.frame,'1','Historical detection frame stays explicitly separate');
 console.log('Live stream independence, one in-flight inference, pause/once, stale/error and hidden-tab regression passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
