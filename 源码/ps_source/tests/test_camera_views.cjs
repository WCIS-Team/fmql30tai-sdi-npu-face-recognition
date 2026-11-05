const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(),timers=new Map(),events={},requests=[];let now=100,id=0,source=0,interval;
function node(name){if(!nodes.has(name))nodes.set(name,{textContent:'',hidden:name==='camCanvas',dataset:{},classList:{toggle(){}},replaceChildren(){},after(){},append(){},removeAttribute(){},getContext:()=>({drawImage(){}})});return nodes.get(name);}
const ctx={console,Date,Uint8Array,performance:{now:()=>now},
 document:{hidden:false,getElementById:node,createElement:()=>({style:{}}),addEventListener:(name,fn)=>events[name]=fn},
 setTimeout:(fn,delay)=>{timers.set(++id,{fn,delay});return id;},clearTimeout:key=>timers.delete(key),setInterval:fn=>{interval=fn;},
 Image:class{constructor(){this.naturalWidth=960;this.naturalHeight=540;}set src(v){queueMicrotask(()=>this.onload());}},
 fetch:path=>path.includes('/status')?Promise.resolve({ok:true,json:async()=>({ready:true,session:'s',frame_id:100*(++source),encoded:source})}):new Promise(resolve=>requests.push(resolve))};
ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(require.resolve('../npu_photo/camera_panel.js'),'utf8'),ctx);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function tick(delay){const entry=[...timers].find(([,t])=>t.delay===delay);assert(entry,'Expected scheduled delay '+delay);timers.delete(entry[0]);now+=delay;entry[1].fn();await flush();}
async function finish(index,faces,frameId){now+=600;const frame={width:960,height:540,frame_id:frameId,session:'s',boot_id:'b',source_rgb565_sha256:'h'};
 requests[index]({ok:true,status:200,json:async()=>({entry:{image:'fixture',result:{camera_frame:frame,face_count:faces,faces:[],identities:[],elapsed_ms:600}}})});await flush();}
(async()=>{
 await flush();const stream=node('camVideo').src;
 node('camDetectionTile').onclick();assert.equal(node('cameraPanel').dataset.mainView,'preview','Cannot enlarge an unavailable detection image');
 await tick(250);assert.equal(node('camPreviewFps').textContent,'4.0 fps','Preview rate uses encoded-frame count rather than skipped source IDs');
 await finish(0,0,1);assert([...timers.values()].some(t=>t.delay===1000),'No face must select a one-second delay');
 node('camDetectionTile').onclick();assert.equal(node('cameraPanel').dataset.mainView,'detection');assert.equal(node('camDetectionTile').ariaPressed,'true');
 node('camPreviewTile').onclick();assert.equal(node('cameraPanel').dataset.mainView,'preview');assert.equal(node('camPreviewTile').ariaPressed,'true');
 let prevented=0;node('camDetectionTile').onkeydown({key:'Enter',preventDefault(){prevented++;}});assert.equal(node('cameraPanel').dataset.mainView,'detection');
 node('camPreviewTile').onkeydown({key:' ',preventDefault(){prevented++;}});assert.equal(prevented,2);assert.equal(node('cameraPanel').dataset.mainView,'preview');
 assert.equal(node('camVideo').src,stream,'View changes cannot reconnect the video');assert.equal(requests.length,1,'View changes cannot request inference');
 await tick(1000);assert.equal(requests.length,2);await finish(1,1,101);assert([...timers.values()].some(t=>t.delay===50),'A face must select a 50 ms delay');
 assert.equal(node('camDetectFps').textContent,'0.63 fps','Detection rate counts distinct processed frames, not frame-ID increments');
 await tick(50);await finish(2,0,201);assert([...timers.values()].some(t=>t.delay===1000),'Returning to no-face must restore the one-second delay');
 const count=Number(node('camCanvas').dataset.results);node('camDetectionTile').onclick();assert.equal(Number(node('camCanvas').dataset.results),count);assert.equal(node('camCanvas').dataset.frame,'201');
 now+=3100;interval();assert.equal(node('camDetectFps').textContent,'0.0 fps','Stalled results must not keep showing an old positive rate');
 await ctx.pauseCameraDetection();assert.equal(node('camDetectFps').textContent,'已暂停');assert.equal(node('camVideo').src,stream);
 ctx.document.hidden=true;events.visibilitychange();ctx.document.hidden=false;events.visibilitychange();await flush();assert.equal(node('camPreviewFps').textContent,'统计中','Returning to a tab resets preview timing');
 console.log('No-face/face cadence, independent FPS, mouse/keyboard view swaps, frame preservation and stale-rate checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
