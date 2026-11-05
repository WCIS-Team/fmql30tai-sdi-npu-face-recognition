const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const flush=()=>new Promise(r=>setImmediate(r));
class Events{
 constructor(){this.events=new Map();}
 addEventListener(n,f){if(!this.events.has(n))this.events.set(n,new Set());this.events.get(n).add(f);}
 removeEventListener(n,f){this.events.get(n)?.delete(f);}
 emit(n){for(const f of [...(this.events.get(n)||[])])f();}
 count(){return [...this.events.values()].reduce((s,q)=>s+q.size,0);}
}
function setup(config={}){
 const h={now:0,errors:[],seeks:[],requests:[],appended:[],revoked:[],queue:[],...config};
 let current=0,waiting;
 h.video={paused:true,seeking:false,playbackRate:1,buffered:{length:0},pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();},removeAttribute(){},load(){},get currentTime(){return current;},set currentTime(v){current=v;h.seeks.push(v);}};
 h.reader={read(){if(h.queue.length)return Promise.resolve(h.queue.shift());return new Promise((resolve,reject)=>waiting={resolve,reject});},cancel(){h.cancelled=true;waiting?.resolve({done:true});return Promise.resolve();}};
 h.push=(range)=>{const value=new Uint8Array([1]);value.range=range;const q={value,done:false};if(waiting){const w=waiting;waiting=null;w.resolve(q);}else h.queue.push(q);};
 class Buffer extends Events{
  appendBuffer(value){h.appended.push(value);h.complete=()=>{if(value.range){const r=value.range;h.video.buffered={length:1,start:()=>r[0],end:()=>r[1]};}this.emit('updateend');};if(!h.holdAppend)queueMicrotask(h.complete);}
  remove(){queueMicrotask(()=>this.emit('updateend'));}
 }
 class Source extends Events{static isTypeSupported(){return true;}constructor(){super();h.source=this;}addSourceBuffer(){h.buffer=new Buffer();return h.buffer;}}
 const context={Date:{now:()=>h.now},AbortController,MediaSource:Source,URL:{createObjectURL(s){queueMicrotask(()=>s.emit('sourceopen'));return 'blob:stream';},revokeObjectURL(u){h.revoked.push(u);}},fetch:async(url)=>{h.requests.push(url);if(h.holdFetch)await new Promise(r=>h.releaseFetch=r);return {ok:!h.badHTTP,body:{getReader:()=>h.reader},headers:{get:n=>n==='X-Live-Codec'?(h.codec||'avc1.4d001e'):'100.5'}};}};
 context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../lan_stream/h264_player.js'),'utf8'),context);
 h.player=new context.H264Player(h.video,'/media/',e=>h.errors.push(e.message));return h;
}
test('waits for initial buffered data, then starts near its end at nonzero PTS',async()=>{
 const h=setup(),started=h.player.start('one');await flush();h.push([100,100.033]);await flush();assert.equal(h.seeks.length,0);h.push([100,100.5]);await started;assert.equal(h.video.currentTime,100.25);assert.equal(h.video.paused,false);assert.equal(h.requests.length,1);assert.match(h.requests[0],/live.mp4\?session=one/);h.player.stop();
});
test('stop during a pending stream read cancels startup and releases listeners',async()=>{
 const h=setup(),started=h.player.start('one');await flush();h.player.stop();await started;assert(h.cancelled);assert.equal(h.buffer.count(),0);assert.equal(h.errors.length,0);assert.equal(h.revoked.length,1);
});
test('late fetch completion after stop cannot attach a source',async()=>{
 const h=setup({holdFetch:true}),started=h.player.start('one');await flush();h.player.stop();h.releaseFetch();await started;assert.equal(h.source,undefined);assert.equal(h.errors.length,0);
});
test('HTTP and invalid codec failures report once without starting a decoder',async()=>{
 for(const config of [{badHTTP:true},{codec:'bad'}]){const h=setup(config);await h.player.start('one');assert.equal(h.errors.length,1);assert.equal(h.source,undefined);}
});
test('decoder failure removes append listeners and closes the stream',async()=>{
 const h=setup({holdAppend:true}),started=h.player.start('one');await flush();h.push([100,100.5]);await flush();h.buffer.emit('error');await started;assert.equal(h.errors.length,1);assert.equal(h.buffer.count(),0);assert(h.cancelled);
});
test('steady supply uses bounded playback rate without repeated seeks',async()=>{
 const h=setup(),started=h.player.start('one');await flush();h.push([100,100.5]);await started;h.push([100,101]);await flush();assert.equal(h.seeks.length,1);assert(h.video.playbackRate>=.97&&h.video.playbackRate<=1.03);h.player.stop();
});

test('network backlog catches up only after appended data and is rate limited',async()=>{
 const h=setup(),started=h.player.start('one');await flush();h.push([100,100.5]);await started;h.now=3500;h.push([100,103]);await flush();assert.equal(h.seeks.length,2);assert.equal(h.video.currentTime,102.75);h.now=4000;h.push([100,105]);await flush();assert.equal(h.seeks.length,2);h.player.stop();
});
test('paused playback is never forced to seek forward',async()=>{
 const h=setup(),started=h.player.start('one');await flush();h.push([100,100.5]);await started;h.video.pause();h.now=5000;h.push([100,103]);await flush();assert.equal(h.seeks.length,1);h.player.stop();
});
