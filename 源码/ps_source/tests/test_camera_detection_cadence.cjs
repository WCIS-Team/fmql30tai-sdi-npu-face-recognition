// UI request lifecycle: fast success cadence and one-shot adoption of in-flight work.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../npu_photo/camera_panel.js'),'utf8');
function harness(){
 const nodes=new Map(),timers=new Map(),events={},requests=[];let id=0,draws=0,now=100;
 const node=name=>{if(!nodes.has(name))nodes.set(name,{textContent:'',hidden:false,dataset:{},classList:{toggle(){}},replaceChildren(){},after(){},append(){},removeAttribute(){},getContext:()=>({drawImage(){draws++;}})});return nodes.get(name);};
 const context={console,Date,Uint8Array,performance:{now:()=>now},
  document:{hidden:false,getElementById:node,createElement:()=>({style:{}}),addEventListener:(name,fn)=>events[name]=fn},
  setTimeout:(fn,delay)=>{timers.set(++id,{fn,delay});return id;},clearTimeout:key=>timers.delete(key),setInterval:()=>0,
  Image:class{constructor(){this.naturalWidth=960;this.naturalHeight=540;}set src(value){queueMicrotask(()=>this.onload());}},
  fetch:path=>path.includes('/status')?Promise.resolve({ok:true,json:async()=>({ready:true,session:'s',frame_id:1})}):new Promise(resolve=>requests.push(resolve))};
 context.window=context;vm.createContext(context);vm.runInContext(source,context);
 return {node,timers,events,requests,context,get draws(){return draws;},
  finish(index,status=200,faceCount=0){now+=600;const frame={width:960,height:540,frame_id:index+1,session:'s',boot_id:'b',source_rgb565_sha256:'h'};
   requests[index]({status,ok:status===200,json:async()=>({entry:{image:'fixture',result:{camera_frame:frame,faces:[],identities:[],face_count:faceCount,elapsed_ms:600,presentation_attack_detection:{...frame,status:'not_applicable',reason:'no_face',frame_age_ms:600,max_age_ms:3000}}}})});},
  tick(){const entry=[...timers].find(([,t])=>t.delay===50);assert(entry,'Success must schedule the next request after 50 ms');timers.delete(entry[0]);now+=50;entry[1].fn();}
 };
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const detectionTimers=h=>[...h.timers.values()].filter(t=>t.delay!==250);
(async()=>{
 let h=harness();await flush();assert.equal(h.requests.length,1);
 const once=h.node('camOnce').onclick(),again=h.node('camOnce').onclick();
 assert.equal(h.requests.length,1,'Repeated one-shot clicks must share the current inference');
 h.finish(0);await Promise.all([once,again]);await flush();
 assert.equal(h.requests.length,1);assert.equal(h.draws,1,'Adopted result must render');
 assert.match(h.node('camPad').textContent,/未检测到人脸/);assert.equal(detectionTimers(h).length,0,'One-shot must leave automatic detection paused');
 await h.node('camAuto').onclick();assert.equal(h.requests.length,2);h.finish(1,200,1);await flush();h.tick();
 assert.equal(h.requests.length,3);assert.equal(detectionTimers(h).length,0,'No next request may be queued while one is pending');
 const adopted=h.node('camOnce').onclick();const paused=h.context.pauseCameraDetection();h.finish(2);await Promise.all([adopted,paused]);await flush();
 assert.equal(h.draws,2,'Explicit pause after adoption must suppress the in-flight result');assert.equal(detectionTimers(h).length,0);
 h=harness();await flush();const pausing=h.context.pauseCameraDetection();const manual=h.node('camOnce').onclick();h.finish(0);await Promise.all([pausing,manual]);await flush();
 assert.equal(h.requests.length,1,'One-shot may adopt a request invalidated by a preceding pause');assert.equal(h.draws,1);
 h=harness();await flush();const busy=h.node('camOnce').onclick();h.finish(0,409);await busy;await flush();
 assert.match(h.node('camPad').textContent,/本次未开始/);assert.equal(h.requests.length,1);assert.equal(detectionTimers(h).length,0);
 h=harness();await flush();const hiding=h.node('camOnce').onclick();h.context.document.hidden=true;h.events.visibilitychange();h.finish(0);await hiding;await flush();
 assert.equal(h.draws,0,'Hiding the tab invalidates adopted work');assert.equal(detectionTimers(h).length,0);
 console.log('50 ms cadence, single in-flight work, repeated manual adoption, pause, busy and hidden-tab checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
