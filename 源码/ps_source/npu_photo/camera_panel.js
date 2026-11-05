/* Render a camera frame together with its own result; never reuse old boxes. */
(function(global){
 'use strict';
 function detectionDelay(busyCount,faceCount=0,random=Math.random()){
  if(!busyCount)return faceCount>0?50:1000;
  const base=Math.min(4000,500*2**Math.min(busyCount-1,3));
  return Math.round(base+Math.max(0,Math.min(1,random))*500);
 }
 function padView(result,elapsed=0,paused=false,unavailable='',faceIndex=null){
  const prefix='活体防伪：';
  if(unavailable)return {text:prefix+unavailable,error:true};
  if(paused)return {text:prefix+'检测已暂停，请重新检测',error:false};
  const p=result&&result.presentation_attack_detection,f=result&&result.camera_frame;
  if(!p)return {text:prefix+'等待防伪结果',error:false};
  if(p.status==='not_evaluated')return {text:prefix+'本次未评估',error:false};
  if(!f||p.frame_id!==f.frame_id||p.session!==f.session||p.boot_id!==f.boot_id||p.source_rgb565_sha256!==f.source_rgb565_sha256)return {text:prefix+'结果与检测帧不匹配',error:true};
  if(!Number.isFinite(p.frame_age_ms)||p.frame_age_ms<0||!Number.isFinite(p.max_age_ms)||p.max_age_ms<=0||p.status==='stale'||p.frame_age_ms+Math.max(0,elapsed)>p.max_age_ms)return {text:prefix+'结果已过期，等待重新检测',error:true};
  if(p.status==='not_applicable')return {text:prefix+(p.reason==='no_face'?'未检测到人脸':p.reason==='multiple_faces'?'检测到多人，请单人正对摄像头':'本帧不适用'),error:false};
  const labels={model_live:'模型判断为真人',model_non_live:'模型判断为疑似攻击',inconclusive:'模型结果不确定',failed:'防伪失败',error:'防伪失败'};
  if(faceIndex!==null&&(result.faces||[]).length!==1&&p.status!=='evaluated'&&p.status!=='partial')return {text:prefix+'本脸未评估',error:true};
  if(p.status==='evaluated'||p.status==='partial'){
   const entries=p.faces,count=(result.faces||[]).length;
   if(!Array.isArray(entries)||entries.length!==count||new Set(entries.map(x=>x.face_index)).size!==count||entries.some(x=>!Number.isSafeInteger(x.face_index)||x.face_index<0||x.face_index>=count))return {text:prefix+'逐人结果与检测人脸不匹配',error:true};
   const label=x=>labels[x.status]||(x.status==='stale'?'结果已过期':x.reason==='face_limit'?'超出本帧处理上限，未评估':x.status==='failed'||x.status==='error'?'防伪失败':'未完成评估');
   if(faceIndex!==null){const item=entries.find(x=>x.face_index===faceIndex);return item?{text:prefix+label(item),error:item.status!=='model_live'}:{text:prefix+'本脸未评估',error:true};}
   const text=entries.map(x=>'人脸 '+(x.face_index+1)+'：'+label(x)).join('；');
   return {text:prefix+text+' · 检测帧 '+f.frame_id,error:entries.some(x=>x.status!=='model_live')};
  }
  return {text:prefix+(labels[p.status]||'无法判断')+' · 检测帧 '+f.frame_id,error:p.status!=='model_live'};
 }
 function drawFaces(ctx,faces,identities,width,padLabels=[]){
  ctx.lineWidth=Math.max(2,width/350);ctx.font=Math.max(16,width/48)+'px sans-serif';
  for(let index=0;index<faces.length;index++){
   const face=faces[index],person=identities.find(p=>p.face_index===index),[x1,y1,x2,y2]=face.box;
   const pad=padLabels[index],color=!pad?'#70f1be':pad.text.includes('疑似攻击')?'#ff9a9a':!pad.error&&pad.text.includes('模型判断为真人')?'#70f1be':'#ffd07a';
   ctx.strokeStyle=color;ctx.strokeRect(x1,y1,x2-x1,y2-y1);
   for(const point of face.landmarks||[]){ctx.fillStyle='#ffbb72';ctx.beginPath();ctx.arc(point[0],point[1],Math.max(3,width/230),0,Math.PI*2);ctx.fill();}
   const label='人脸 '+(index+1)+' · '+(person?person.name:'已检测 · 未提取身份')+' · '+(face.score*100).toFixed(1)+'%';
   const height=pad?58:29,top=Math.max(0,y1-height),left=Math.max(0,Math.min(x1,width-20));
   const labelWidth=Math.max(20,Math.min(Math.max(ctx.measureText(label).width,pad?ctx.measureText(pad.text).width:0)+16,width-left));
   ctx.fillStyle='#07291fea';ctx.fillRect(left,top,labelWidth,height);ctx.fillStyle='#a0ffdb';ctx.fillText(label,left+7,top+21,labelWidth-14);
   if(pad){ctx.fillStyle=color;ctx.fillText(pad.text,left+7,top+50,labelWidth-14);}
  }
 }
 if(typeof module!=='undefined'&&module.exports){module.exports={drawFaces,padView,detectionDelay};return;}
 const byId=id=>document.getElementById(id),canvas=byId('camCanvas'),video=byId('camVideo');if(!canvas||!video)return;
 const ctx=canvas.getContext('2d');let viewActive=!["#database","#galleryPanel","#recordings"].includes(global.location?.hash||''),paused=false,pending=null,generation=0,timer=null,statusTimer=null,statusPending=false,streamTimer=null;
 const live=document.createElement('video');live.id='camH264';live.muted=true;live.autoplay=true;live.playsInline=true;live.hidden=true;live.style.cssText='width:100%;height:100%;object-fit:contain';video.after(live);
 let h264Player=null,h264Mode=false,playerLoading=null;
 async function h264Stream(session){
  if(!global.H264Player){if(!playerLoading)playerLoading=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/h264_player.js';script.onload=resolve;script.onerror=reject;document.head.append(script);});await playerLoading;}
  if(!h264Player)h264Player=new global.H264Player(live,'/api/camera/h264/',()=>{streamFailed=true;live.hidden=true;});
  await h264Player.start(session);
 }
 let lastAt=0,results=0,lastFrame=null,lastSession=null,sourceFrame=0,sourceAt=0,viewRate=null,streamFailed=false;
 let detectionSamples=[],detectionSession=null,detectionKey=null;
 let padResult=null,padAt=0,padUnavailable='';
 let overlayImage=null,overlayResult=null,overlayAt=0,overlaySignature='';
 let busyCount=0,nextDelay=50,pendingRequest=null;
 function renderPad(){const el=byId('camPad');if(!el)return;const p=padView(padResult,padAt?performance.now()-padAt:0,paused&&!padResult,padUnavailable);el.textContent=p.text;el.classList.toggle('camera-error',p.error);refreshOverlay();}
 function overlayLabels(result,at){return (result.faces||[]).map((_,index)=>padView(result,performance.now()-at,paused&&!padResult,padUnavailable||(!padResult&&!paused?'对应结果已失效':''),index));}
 function refreshOverlay(){
  if(!overlayImage||!overlayResult)return;
  const labels=overlayLabels(overlayResult,overlayAt),signature=JSON.stringify(labels);
  if(signature===overlaySignature)return;
  ctx.drawImage(overlayImage,0,0);drawFaces(ctx,overlayResult.faces||[],overlayResult.identities||[],canvas.width,labels);overlaySignature=signature;
 }
 const imageFrom=source=>new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(Error('摄像头图片加载失败'));image.src=source;});
 function state(title,message,error=false){byId('camState').textContent=title;byId('camMessage').textContent=message;byId('camMessage').classList.toggle('camera-error',error);}
 function controls(){byId('camAuto').textContent=paused?'开始自动检测':'暂停自动检测';byId('camAuto').classList.toggle('selected',!paused);byId('camPreview').classList.toggle('selected',paused);}
 function setMainView(detection){
  if(detection&&canvas.hidden)return;
  byId('cameraPanel').classList.toggle('detection-large',detection);byId('cameraPanel').dataset.mainView=detection?'detection':'preview';
  byId('camPreviewTile').ariaPressed=String(!detection);byId('camDetectionTile').ariaPressed=String(detection);
  byId('camPreviewTile').title=detection?'点击放大实时预览':'实时预览已放大';
  byId('camDetectionTile').title=detection?'检测图已放大':'点击放大检测图';
  byId('camDetectionLabel').textContent=detection?'检测图 · 当前放大':'检测图 · 点击可放大';
 }
 for(const [id,detection] of [['camPreviewTile',false],['camDetectionTile',true]]){
  byId(id).onclick=()=>setMainView(detection);
  byId(id).onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setMainView(detection);}};
 }
 function resetDetectionRate(){detectionSamples=[];detectionSession=null;detectionKey=null;}
 function renderRates(){
  byId('camPreviewFps').textContent=streamFailed||(h264Mode?live.hidden:video.hidden)?'—':viewRate===null?'统计中':viewRate.toFixed(1)+' fps';
  const age=lastAt?performance.now()-lastAt:Infinity;
  byId('camDetectFps').textContent=paused?'已暂停':document.hidden?'页面隐藏':detectionSamples.length<2?'统计中':age>3000?'0.0 fps':
   ((detectionSamples.length-1)*1000/(detectionSamples[detectionSamples.length-1]-detectionSamples[0])).toFixed(2)+' fps';
 }
 function stream(){clearTimeout(streamTimer);if(document.hidden||!viewActive||h264Mode)return;streamFailed=false;video.src='/api/camera/stream.mjpg?v='+Date.now();}
 video.onerror=()=>{streamFailed=true;video.hidden=true;byId('camCaption').textContent='视频连接中断，正在等待新画面';clearTimeout(streamTimer);if(!document.hidden&&viewActive)streamTimer=setTimeout(stream,1000);};
 async function sourceStatus(){
  if(statusPending||document.hidden||!viewActive)return;statusPending=true;
  try{
   const response=await fetch('/api/camera/status',{cache:'no-store'}),q=await response.json();
   if(!viewActive)return;
   if(!response.ok||!q.ready)throw Error('摄像头尚无新鲜画面');
   h264Mode=q.codec==='h264';
   if(h264Mode){video.removeAttribute('src');video.hidden=true;streamFailed=false;await h264Stream(q.session);if(!viewActive){h264Player.stop();return;}live.hidden=false;}
   else{if(h264Player)h264Player.stop();live.hidden=true;}
   if(q.session!==lastSession){lastSession=q.session;sourceFrame=0;sourceAt=0;viewRate=null;resetDetectionRate();video.hidden=true;padResult=null;renderPad();}
   const current=h264Mode&&Number.isFinite(q.h264_encoded_at)?q.h264_encoded_at*1000:performance.now();
   const delivered=Number.isSafeInteger(q.encoded)?q.encoded:q.frame_id;
   if(sourceAt&&current>sourceAt){const sample=Math.max(0,delivered-sourceFrame)*1000/(current-sourceAt);viewRate=viewRate===null?sample:.65*viewRate+.35*sample;}
   sourceFrame=delivered;sourceAt=current;video.dataset.publishedFrame=String(q.frame_id);video.dataset.session=q.session;video.dataset.source='camera';video.hidden=h264Mode||streamFailed;
   byId('camCaption').textContent='实时预览 · '+q.width+'×'+q.height+(h264Mode?' · H.264':'')+(viewRate===null?'':' · 源约 '+viewRate.toFixed(1)+' 帧/秒');renderRates();
  }catch(error){video.hidden=true;live.hidden=true;if(h264Player)h264Player.stop();sourceAt=0;viewRate=null;padResult=null;renderPad();byId('camCaption').textContent=error.message+' · 请勿将缓存画面视作实时视频';}
  finally{statusPending=false;if(!document.hidden&&viewActive)statusTimer=setTimeout(sourceStatus,250);}
 }
 function render(entry,image,receivedAt){
  const result=entry.result,frame=result.camera_frame;
  if(!frame||image.naturalWidth!==frame.width||image.naturalHeight!==frame.height)throw Error('检测结果与画面尺寸不匹配');
  canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
  overlayImage=image;overlayResult=result;overlayAt=receivedAt;overlaySignature='';
  // Bind the new PAD result before drawing labels for this exact image.
  padResult=result;padAt=receivedAt;padUnavailable='';
  ctx.drawImage(image,0,0);const labels=overlayLabels(result,receivedAt);drawFaces(ctx,result.faces||[],result.identities||[],canvas.width,labels);overlaySignature=JSON.stringify(labels);canvas.hidden=false;
  canvas.dataset.source='camera';canvas.dataset.mode='detection';canvas.dataset.session=frame.session;canvas.dataset.frame=String(frame.frame_id);canvas.dataset.results=String(++results);
  byId('camCount').textContent=String(result.face_count);byId('camTime').textContent=(result.elapsed_ms/1000).toFixed(2)+' 秒';byId('camFrame').textContent=String(frame.frame_id);
  const timing=result.pipeline_timing_ms;
  if(timing&&Number.isFinite(timing.identity)&&Number.isFinite(timing.pad))byId('camTime').textContent+='（人脸 '+(timing.identity/1000).toFixed(2)+' / 防伪 '+(timing.pad/1000).toFixed(2)+'）';
  byId('camPeople').replaceChildren();
  for(let index=0;index<(result.faces||[]).length;index++){
   const face=result.faces[index],person=(result.identities||[]).find(p=>p.face_index===index),row=document.createElement('li');
   row.textContent='人脸 '+(index+1)+' · '+(person?person.name:'未提取身份')+' · 检测 '+(face.score*100).toFixed(1)+'%'+(person&&Number.isFinite(person.similarity)?' · 相似度 '+person.similarity.toFixed(3):'');byId('camPeople').append(row);
  }
  const current=performance.now(),session=frame.boot_id+'/'+frame.session,key=session+'/'+frame.frame_id;
  if(session!==detectionSession){resetDetectionRate();detectionSession=session;}
  if(key!==detectionKey){detectionSamples.push(current);if(detectionSamples.length>8)detectionSamples.shift();detectionKey=key;}
  lastAt=current;lastFrame=frame.frame_id;
  padResult=result;padAt=receivedAt;padUnavailable='';
  state(result.face_count?'最近检测到 '+result.face_count+' 人':'最近检测：无人脸','检测框只属于对应检测图；实时预览独立播放。');resultAge();
 }
 function resultAge(){if(lastAt)byId('camResultCaption').textContent='检测帧 '+lastFrame+' · '+((performance.now()-lastAt)/1000).toFixed(1)+' 秒前返回'+(paused?' · 检测已暂停':'');renderPad();renderRates();}
 function schedule(){clearTimeout(timer);if(viewActive&&!paused&&!document.hidden)timer=setTimeout(()=>detect(),nextDelay);}
 function detect(once=false){
  if(pending)return pending;if((paused||document.hidden||!viewActive)&&!once)return Promise.resolve();
  const request={version:generation,once};pendingRequest=request;
  if(!lastAt)state('检测中','视频持续播放，正在获取第一份检测结果。');
  pending=(async()=>{
   const response=await fetch('/api/recognize-camera',{method:'POST',body:new Uint8Array(0),cache:'no-store'}),data=await response.json();
   if(response.status===409||response.status===429){if(request.version===generation){busyCount++;nextDelay=detectionDelay(busyCount);if(!padResult)padUnavailable=request.once?'本次未开始，请稍后再检测':'等待检测资源';renderPad();const message=request.once?'另一请求正在处理，本次未开始；请稍后再点击“检测一次”。':'检测资源暂被占用，约 '+(nextDelay/1000).toFixed(1)+' 秒后重试；上次结果仅对应右侧帧，过期会自动标明。';if(!lastAt)state('等待检测',message);else byId('camMessage').textContent=message;}return;}
   if(!response.ok)throw Error(data.error||'检测暂不可用');busyCount=0;nextDelay=detectionDelay(0,data.entry.result.face_count);const receivedAt=performance.now(),image=await imageFrom(data.entry.image);if(request.version===generation)render(data.entry,image,receivedAt);
  })().catch(error=>{if(request.version!==generation)return;paused=true;padUnavailable='本次检测失败，请重试';renderPad();controls();state('检测已暂停',error.message+'；视频继续播放，可点击“检测一次”重试。',true);}).finally(()=>{pending=null;pendingRequest=null;schedule();});return pending;
 }
 async function pause(){paused=true;padResult=null;padUnavailable="";generation++;clearTimeout(timer);controls();if(pending)await pending;state('自动检测已暂停','视频继续播放，可以登记或上传照片。');resultAge();}
 global.pauseCameraDetection=pause;
 global.setCameraViewActive=async active=>{
  active=Boolean(active);if(active===viewActive)return;viewActive=active;generation++;
  clearTimeout(timer);clearTimeout(statusTimer);clearTimeout(streamTimer);
  if(!active){video.removeAttribute('src');video.hidden=true;live.hidden=true;if(h264Player)h264Player.stop();sourceAt=0;viewRate=null;if(pending)await pending;}
  else if(viewActive){stream();sourceStatus();if(!paused&&!pending)detect();}
 };
 byId('camAuto').onclick=async()=>{if(!paused){await pause();return;}paused=false;generation++;resetDetectionRate();controls();detect();};
 byId('camOnce').onclick=async()=>{
  paused=true;generation++;clearTimeout(timer);controls();
  // Adopt the request already using the hardware instead of discarding its
  // result and starting a second inference. Later pauses still invalidate it.
  if(pending&&pendingRequest){pendingRequest.version=generation;pendingRequest.once=true;await pending;return;}
  padResult=null;padUnavailable='';renderPad();await detect(true);
 };
 byId('camPreview').onclick=async()=>{await pause();state('实时预览中','视频持续播放，右侧保留的检测帧带有时间标记。');};
 document.addEventListener('visibilitychange',()=>{
  generation++;clearTimeout(timer);clearTimeout(statusTimer);clearTimeout(streamTimer);
  if(document.hidden){video.removeAttribute('src');video.hidden=true;live.hidden=true;if(h264Player)h264Player.stop();sourceAt=0;viewRate=null;resetDetectionRate();}
  else if(viewActive){stream();sourceStatus();if(!paused&&!pending)detect();}
 });
 setInterval(resultAge,250);controls();setMainView(false);stream();sourceStatus();detect();
})(typeof window==='undefined'?globalThis:window);
