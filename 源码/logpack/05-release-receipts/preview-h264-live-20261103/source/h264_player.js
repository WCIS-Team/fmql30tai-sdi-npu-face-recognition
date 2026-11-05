/* Continuous fMP4 from the existing hardware H264 encoder. */
(function(root){
 'use strict';
 class H264Player{
  constructor(video,prefix,onError=()=>{}){this.video=video;this.prefix=prefix;this.onError=onError;this.generation=0;}
  stop(){this.generation++;if(this.abort)this.abort.abort();if(this.reader)this.reader.cancel().catch(()=>{});this.reader=null;this.video.pause();this.video.playbackRate=1;this.video.removeAttribute('src');this.video.load();if(this.url)URL.revokeObjectURL(this.url);this.url=null;this.session=null;}
  async start(session){
   if(this.session===session)return;
   this.stop();this.session=session;this.abort=new AbortController();const signal=this.abort.signal,generation=this.generation;
   const check=()=>{if(signal.aborted||generation!==this.generation)throw Error('aborted');};
   const fail=e=>{if(generation===this.generation){this.stop();this.onError(e);}};
   const update=(buffer,operation)=>new Promise((resolve,reject)=>{
    const clean=()=>{buffer.removeEventListener('updateend',done);buffer.removeEventListener('error',bad);signal.removeEventListener('abort',cancel);},done=()=>{clean();resolve();},bad=()=>{clean();reject(Error('视频解码失败'));},cancel=()=>{clean();reject(Error('aborted'));};
    buffer.addEventListener('updateend',done);buffer.addEventListener('error',bad);signal.addEventListener('abort',cancel,{once:true});try{check();operation();}catch(e){clean();reject(e);}
   });
   try{
    const response=await fetch(this.prefix+'live.mp4?session='+encodeURIComponent(session),{cache:'no-store',signal});check();
    if(!response.ok||!response.body)throw Error('等待新鲜 H.264 画面');
    const codec=response.headers.get('X-Live-Codec'),initialEnd=Number(response.headers.get('X-Live-End'));
    if(!/^avc1\.[0-9a-f]{6}$/i.test(codec)||!Number.isFinite(initialEnd))throw Error('视频初始化无效');
    const mime='video/mp4; codecs="'+codec+'"';if(!root.MediaSource||!MediaSource.isTypeSupported(mime))throw Error('浏览器不支持此 H.264 视频');
    const source=new MediaSource(),opened=new Promise((resolve,reject)=>{const clean=()=>{source.removeEventListener('sourceopen',done);signal.removeEventListener('abort',cancel);},done=()=>{clean();resolve();},cancel=()=>{clean();reject(Error('aborted'));};source.addEventListener('sourceopen',done);signal.addEventListener('abort',cancel,{once:true});});
    this.url=URL.createObjectURL(source);this.video.src=this.url;await opened;check();
    const buffer=source.addSourceBuffer(mime);this.reader=response.body.getReader();const reader=this.reader;let playing=false,trimmed=0,lastRate=0,lastSeek=0;
    const startup=new Promise((resolve,reject)=>{
     const run=async()=>{while(true){const {value,done}=await reader.read();check();if(done)throw Error('视频连接中断');
      if(!value||!value.byteLength)continue;
      await update(buffer,()=>buffer.appendBuffer(value));check();
      if(!this.video.buffered.length)continue;
      const i=this.video.buffered.length-1,end=this.video.buffered.end(i),start=this.video.buffered.start(i);
      if(!playing&&end>=initialEnd-.005){this.video.currentTime=Math.max(start+.001,end-.25);this.video.playbackRate=.985;lastRate=lastSeek=Date.now();this.video.play().catch(()=>{});playing=true;resolve();}
      if(playing&&!this.video.paused&&!this.video.seeking){const lag=end-this.video.currentTime,now=Date.now();if(lag>.9&&now-lastSeek>=3000){this.video.currentTime=Math.max(start+.001,end-.25);lastSeek=now;if(this.video.playbackRate!==.985)this.video.playbackRate=.985;lastRate=now;}else{let rate=this.video.playbackRate;if(lag>.5)rate=1.01;else if(lag<.08)rate=.97;else if((rate>1&&lag<.25)||(rate<.98&&lag>.2))rate=.985;if(now-lastRate>=2000&&Math.abs(rate-this.video.playbackRate)>.001){this.video.playbackRate=rate;lastRate=now;}}}
      if(playing&&this.video.currentTime-trimmed>20){trimmed=this.video.currentTime;await update(buffer,()=>buffer.remove(0,Math.max(0,trimmed-10)));check();}
     }};
     run().catch(e=>{reject(e);fail(e);});
    });
    await startup;
   }catch(e){fail(e);}
  }
 }
 root.H264Player=H264Player;
})(typeof window==='undefined'?globalThis:window);
