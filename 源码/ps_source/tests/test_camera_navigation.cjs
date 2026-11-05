// The database uses the user's device; entering it must not request board frames.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(),timers=new Map(),requests=[];let serial=0,statusCalls=0;
function node(id){if(!nodes.has(id))nodes.set(id,{dataset:{},hidden:true,textContent:'',src:'',classList:{toggle(){}},replaceChildren(){},after(){},append(){},removeAttribute(k){this[k]='';},getContext(){return {drawImage(){}};}});return nodes.get(id);}
const ctx={location:{hash:'#database'},console,Date,Uint8Array,performance:{now:()=>100},
 document:{hidden:false,getElementById:node,createElement:()=>({style:{}}),addEventListener(){}},
 setTimeout:(fn,delay)=>{timers.set(++serial,{fn,delay});return serial;},clearTimeout:id=>timers.delete(id),setInterval:()=>0,
 fetch:path=>{if(path.endsWith('/status')){statusCalls++;return Promise.resolve({ok:true,json:async()=>({ready:true,session:'s',frame_id:statusCalls,encoded:statusCalls})});}return new Promise(resolve=>requests.push(resolve));}};
ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(require.resolve('../npu_photo/camera_panel.js'),'utf8'),ctx);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 await flush();assert.equal(statusCalls,0);assert.equal(requests.length,0);assert.equal(timers.size,0);
 await ctx.setCameraViewActive(true);await flush();assert.equal(requests.length,1);assert.equal(statusCalls,1);
 const leaving=ctx.setCameraViewActive(false);requests[0]({status:409,ok:false,json:async()=>({error:'busy'})});await leaving;await flush();
 assert.equal(timers.size,0,'A completed old request must not resume polling in Database');assert.equal(node('camVideo').src,'');
 await ctx.setCameraViewActive(true);await flush();assert.equal(requests.length,2);
 const pause=ctx.pauseCameraDetection();requests[1]({status:409,ok:false,json:async()=>({error:'busy'})});await pause;
 await ctx.setCameraViewActive(false);await ctx.setCameraViewActive(true);await flush();
 assert.equal(requests.length,2,'A deliberate pause survives switching away and back');
 console.log('Database startup, active-view polling, pending request drain and manual pause preservation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
