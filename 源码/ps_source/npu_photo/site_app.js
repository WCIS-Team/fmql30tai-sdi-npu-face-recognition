
const $=id=>document.getElementById(id), canvas=$('picture'), ctx=canvas.getContext('2d');
let selected=null, showOverlay=true, currentImage=null, generation=0;
let galleryBusy=false, enrollmentAvailable=false, uploadAvailable=false;
let selectionBusy=false, selectedPhotos=[], galleryData=null, currentView="live", deviceStream=null, cameraPending=false, cameraTicket=0, facingMode="user";
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function draw(){if(!selected||!currentImage)return;const im=currentImage;canvas.width=im.naturalWidth;canvas.height=im.naturalHeight;ctx.drawImage(im,0,0);if(!showOverlay)return;
 const faces=selected.face?[selected.face]:(selected.faces||[]);ctx.lineWidth=Math.max(2,canvas.width/350);
 for(const [index,face] of faces.entries()){const [x1,y1,x2,y2]=face.box;const person=(selected.result.identities||[]).find(p=>p.face_index===index);ctx.strokeStyle='#67f0c8';ctx.strokeRect(x1,y1,x2-x1,y2-y1);for(const [x,y] of face.landmarks){ctx.fillStyle='#ffba75';ctx.beginPath();ctx.arc(x,y,Math.max(3,canvas.width/200),0,Math.PI*2);ctx.fill();}if(selected.result.identities){const label=person?person.name:'超出4人上限';ctx.font=Math.max(15,canvas.width/50)+'px sans-serif';ctx.fillStyle='#67f0c8';ctx.fillText(label,x1,Math.max(20,y1-7));}}
}
async function choose(entry){
 $('photoResults').hidden=false;selected=entry;currentImage=null;generation++;const request=generation;
 ctx.clearRect(0,0,canvas.width,canvas.height);canvas.style.visibility='hidden';
 const r=entry.result,multi=r.face_count>1;$('filename').textContent=entry.file;
 $('identity').textContent=multi?'检测'+r.face_count+'人 · 已处理'+r.processed_face_count+'人':r.status==='no_face'?'无人脸 · 无法识别':r.name||'未知';
 $('identity').classList.toggle('unknown',r.status==='unknown'||r.status==='no_face');$('verdict').textContent='本次上传 · '+(r.elapsed_ms/1000).toFixed(2)+' 秒';
 $('score').textContent=Number.isFinite(r.similarity)?r.similarity.toFixed(4):'—';$('threshold').textContent=Number.isFinite(r.threshold)?r.threshold.toFixed(4):'—';$('scores').replaceChildren();
 if(multi){for(const person of r.identities||[]){const line=node('div',undefined,'score');line.append(node('span','人脸'+(person.face_index+1)+'：'+person.name),node('span',Number.isFinite(person.similarity)?person.similarity.toFixed(4):'—'));$('scores').append(line);}if(r.skipped_face_count)$('scores').append(node('p','另有'+r.skipped_face_count+'张人脸未识别；每帧最多处理4人。','muted'));}
 else{for(const [name,value] of Object.entries(r.scores||{})){const line=node('div',undefined,'score');line.append(node('span',name),node('span',Number.isFinite(value)?value.toFixed(4):'—'));$('scores').append(line);}}
 $('crop').style.display=entry.aligned?'flex':'none';if(entry.aligned)$('aligned').src=entry.aligned;
 $('description').textContent=r.status==='no_face'?'未检测到人脸，请换一张清晰照片。':'绿色框与橙色五点仅对应本次上传照片。';$('details').replaceChildren(node('div','使用当前人员库识别；上传照片不会自动登记。'));
 const im=new Image();im.onload=()=>{if(request!==generation)return;currentImage=im;draw();canvas.style.visibility='visible';};im.onerror=()=>{if(request===generation)$('description').textContent='上传照片预览加载失败，请重新上传。';};im.src=entry.image;
}
async function init(){
 if(galleryBusy)return;enrollmentAvailable=false;uploadAvailable=false;setGalleryBusy(false);$('serviceStatus').textContent='正在检查登记服务…';
 await Promise.allSettled([
  (async()=>{try{const health=await requestJSON('/api/health');enrollmentAvailable=health.gallery_management===true;uploadAvailable=health.photo_input===true;$('backendBadge').textContent='服务已连接';$('serviceStatus').textContent=enrollmentAvailable?'登记服务就绪':'当前服务未启用人员登记，请检查服务配置。';}catch(error){$('backendBadge').textContent='服务连接异常';$('serviceStatus').textContent='登记服务暂不可用：'+error.message+'。请稍后点击“刷新人员库”重试。';}finally{setGalleryBusy(galleryBusy);}})(),
  refreshGallery().catch(error=>{$('galleryLoadStatus').textContent='人员库读取失败：'+error.message+'。请点击“刷新人员库”重试。';})
 ]);
}
function setGalleryBusy(value){
 galleryBusy=value;const locked=value||selectionBusy;
 $('uploadButton').disabled=locked||!uploadAvailable;
 $('enrollButton').disabled=locked||!enrollmentAvailable||selectedPhotos.length===0;
 $('refreshGalleryButton').disabled=locked;$('personName').disabled=locked;
 for(const id of ['chooseEnrollFiles','systemCameraButton','enrollFiles','devicePhotoFile'])$(id).disabled=locked;
 $('openDeviceCamera').disabled=locked||cameraPending;
 $('takeDevicePhoto').disabled=locked||cameraPending||!deviceStream||!$('deviceCameraVideo').videoWidth;
 $('switchDeviceCamera').disabled=locked||cameraPending;
 $('clearSelectedPhotos').disabled=locked||!selectedPhotos.length;
 for(const button of document.querySelectorAll('[data-gallery-action]'))button.disabled=locked||!enrollmentAvailable;
 for(const button of document.querySelectorAll('[data-remove-selection]'))button.disabled=locked;
}
async function requestJSON(url,options){const response=await fetch(url,{cache:'no-store',signal:options?.method?undefined:AbortSignal.timeout(10000),...options});const value=await response.json();if(!response.ok)throw Error(value.error||'操作失败');return value;}
async function refreshGallery(){renderGallery(await requestJSON('/api/gallery'));}
function renderGallery(data){
 galleryData=data;const query=$('personSearch').value.trim().toLocaleLowerCase(),people=data.people.filter(p=>p.name.toLocaleLowerCase().includes(query));
 const featuresOnly=data.storage_policy==='one_original_per_person';$('galleryLoadStatus').textContent='已登记 '+data.people.length+' 人'+(query?' · 匹配 '+people.length+' 人':'');$('galleryPeople').replaceChildren();
 if(!people.length)$('galleryPeople').append(node('p',data.people.length?'没有找到匹配人员。':'人员库为空，请先登记。','muted'));
 for(const person of people){
  const card=node('article',undefined,'panel');card.append(node('h2',person.name+' · '+person.count+(featuresOnly?' 份特征':' 张照片')));
  const actions=node('div',undefined,'enroll-actions');
  const add=node('button','补充照片','toggle');add.type='button';add.dataset.galleryAction='true';add.onclick=()=>{$('personName').value=person.name;$('galleryPanel').scrollIntoView({behavior:'smooth'});$('enrollStatus').textContent='已选择 '+person.name+'；拍照或上传照片后点击“确认登记”。';$('personName').focus();};
  const remove=node('button','删除人员','toggle');remove.type='button';remove.dataset.galleryAction='true';remove.setAttribute('aria-label','删除人员 '+person.name);remove.onclick=()=>deleteEnrollment(person);actions.append(add,remove);card.append(actions);
  const photos=node('div');photos.style.cssText='display:flex;gap:10px;flex-wrap:wrap';
  for(const photo of person.photos){const item=node('div');if(photo.image){const image=node('img');image.src=photo.image;image.alt=person.name+' 登记照片';image.style.cssText='width:80px;height:80px;object-fit:cover;border-radius:6px;display:block';item.append(image);}if(featuresOnly)item.append(node('div',photo.file,'muted'));const del=node('button',featuresOnly?'删除特征':'删除照片','toggle');del.type='button';del.dataset.galleryAction='true';del.setAttribute('aria-label','删除照片 '+person.name+' '+photo.file);del.onclick=()=>deleteEnrollment(person,photo);item.append(del);photos.append(item);}card.append(photos);$('galleryPeople').append(card);
 }
 setGalleryBusy(galleryBusy);
}
async function deleteEnrollment(person,photo){if(galleryBusy||selectionBusy)return;if(!window.confirm(photo?'确定删除 '+person.name+' 的这份登记特征？':'确定删除人员 '+person.name+' 及其全部登记资料？'))return;await window.pauseCameraDetection?.();setGalleryBusy(true);try{const data=await requestJSON('/api/gallery/'+person.id+(photo?'/'+photo.id:''),{method:'DELETE'});renderGallery(data);$('enrollStatus').textContent='已删除 '+person.name+(photo?' 的照片 '+photo.file:' 的全部登记')+(data.deletion_policy==='remove_active_data'?'；已移除所选特征；删除最后一份特征时同时移除原图。':'；立即停止使用，回收备份保留在板端。');}catch(error){$('enrollStatus').textContent=error.message;}finally{setGalleryBusy(false);}}
$('enrollForm').onsubmit=async event=>{
 event.preventDefault();if(galleryBusy||selectionBusy||!enrollmentAvailable)return;
 const name=$('personName').value.trim(),batch=[...selectedPhotos];if(!name||!batch.length)return;
 setGalleryBusy(true);await window.pauseCameraDetection?.();let passed=0;const errors=[];
 try{for(let i=0;i<batch.length;i++){const item=batch[i];$('enrollStatus').textContent='正在登记 '+(i+1)+'/'+batch.length+'：'+item.file.name;
  try{const result=await requestJSON('/api/enroll',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Photo-Name':encodeURIComponent(item.file.name),'X-Person-Name':encodeURIComponent(name)},body:item.file});passed++;selectedPhotos=selectedPhotos.filter(p=>p!==item);URL.revokeObjectURL(item.url);renderGallery(result.gallery);}
  catch(error){errors.push(item.file.name+'：'+error.message);}
 }$('enrollStatus').textContent='登记完成：'+passed+'/'+batch.length+' 张成功'+(errors.length?'；未成功照片已保留，可检查后重试。'+errors.join('；'):'。可使用另一张照片测试识别。');}
 finally{renderSelectedPhotos();setGalleryBusy(false);}
};
 $('uploadForm').onsubmit=async event=>{event.preventDefault();if(galleryBusy||!uploadAvailable)return;const file=$('photoFile').files[0];if(!file)return;if(file.size>8*1024*1024){$('uploadStatus').textContent='照片需在 8 MB 以内';return;}await window.pauseCameraDetection?.();setGalleryBusy(true);$('uploadStatus').textContent='正在板端检测与识别…';try{const response=await fetch('/api/recognize',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Photo-Name':encodeURIComponent(file.name)},body:file});const data=await response.json();if(!response.ok)throw Error(data.error||'识别请求失败');await choose(data.entry);$('uploadStatus').textContent='本次推理完成 · '+(data.entry.result.elapsed_ms/1000).toFixed(2)+' 秒';}catch(error){$('uploadStatus').textContent=error.message;}finally{setGalleryBusy(false);}};
 $('refreshGalleryButton').onclick=init;
 $('toggle').onclick=()=>{showOverlay=!showOverlay;$('toggle').textContent=showOverlay?'隐藏框与五点':'显示框与五点';$('toggle').setAttribute('aria-pressed',String(showOverlay));draw();};

function renderSelectedPhotos(){
 $('selectedPhotoPreviews').replaceChildren();$('selectedPhotoCount').textContent=selectedPhotos.length?'待登记 '+selectedPhotos.length+' 张（确认前不会上传）':'尚未选择照片';
 for(const item of selectedPhotos){const card=node('div',undefined,'selected-photo'),img=node('img');img.src=item.url;img.alt='待登记照片 '+item.file.name;const remove=node('button','移除','toggle');remove.type='button';remove.dataset.removeSelection='true';remove.setAttribute('aria-label','移除待登记照片 '+item.file.name);remove.onclick=()=>{selectedPhotos=selectedPhotos.filter(p=>p!==item);URL.revokeObjectURL(item.url);renderSelectedPhotos();};card.append(img,node('p',item.file.name),remove);$('selectedPhotoPreviews').append(card);}setGalleryBusy(galleryBusy);
}
async function normalizePhoto(file){
 if(!file.type.startsWith('image/'))throw Error('请选择图片文件');
 if(file.size>32*1024*1024)throw Error('原始照片超过 32 MB，请选择较小的图片');
 const url=URL.createObjectURL(file),im=new Image();
 try{im.src=url;await im.decode();const scale=Math.min(1,1600/Math.max(im.naturalWidth,im.naturalHeight));
  if(!im.naturalWidth||!im.naturalHeight)throw Error('无法读取照片尺寸');
  const c=document.createElement('canvas');c.width=Math.max(1,Math.round(im.naturalWidth*scale));c.height=Math.max(1,Math.round(im.naturalHeight*scale));const context=c.getContext('2d');context.fillStyle='#fff';context.fillRect(0,0,c.width,c.height);context.drawImage(im,0,0,c.width,c.height);
  const blob=await new Promise(resolve=>c.toBlob(resolve,'image/jpeg',.92));if(!blob||blob.size>8*1024*1024)throw Error('照片处理后超过 8 MB，请换一张照片');
  return new File([blob],file.name.replace(/\.[^.]*$/,'')+'.jpg',{type:'image/jpeg',lastModified:Date.now()});
 }catch(error){throw Error(error.message||'照片无法读取，请使用 JPEG、PNG 或 WebP');}finally{URL.revokeObjectURL(url);}
}
async function addSelectedPhotos(files){
 if(galleryBusy||selectionBusy)return;const list=Array.from(files);if(!list.length)return;
 if(selectedPhotos.length+list.length>30){$('enrollStatus').textContent='一次最多准备 30 张照片，请先移除多余照片。';return;}
 selectionBusy=true;setGalleryBusy(galleryBusy);$('enrollStatus').textContent='正在准备照片预览…';const errors=[];
 try{for(const original of list){try{const file=await normalizePhoto(original);selectedPhotos.push({file,url:URL.createObjectURL(file)});}catch(error){errors.push(original.name+'：'+error.message);}}}
 finally{selectionBusy=false;renderSelectedPhotos();$('enrollStatus').textContent=errors.length?errors.join('；'):'照片已准备好，请确认登记。';}
}
function closeDeviceCamera(){
 const hadCamera=Boolean(deviceStream)||cameraPending;cameraTicket++;cameraPending=false;if(deviceStream){deviceStream.getTracks().forEach(track=>track.stop());deviceStream=null;}
 $('deviceCameraVideo').srcObject=null;$('deviceCameraPanel').hidden=true;if(hadCamera)$('cameraCaptureStatus').textContent='设备摄像头已关闭，已拍照片仍可确认登记。';setGalleryBusy(galleryBusy);
}
async function openDeviceCamera(){
 if(galleryBusy||selectionBusy||cameraPending)return;
 if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){
  $('cameraCaptureStatus').replaceChildren(node('span','当前网址不能直接调用设备摄像头。手机可点“手机系统拍照”；电脑请先启动桌面入口，再 '));
  const link=node('a','打开本机登记页面');link.href='http://localhost:18091/#database';link.style.color='#9ee5d0';$('cameraCaptureStatus').append(link);return;
 }
 closeDeviceCamera();const ticket=++cameraTicket;cameraPending=true;$('deviceCameraPanel').hidden=false;setGalleryBusy(galleryBusy);$('cameraCaptureStatus').textContent='请允许此网页使用当前设备的摄像头…';
 try{const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:facingMode},width:{ideal:1280},height:{ideal:720}}});
  if(ticket!==cameraTicket||currentView!=='database'||document.hidden){stream.getTracks().forEach(track=>track.stop());return;}
  deviceStream=stream;const video=$('deviceCameraVideo');video.srcObject=stream;await video.play();if(ticket!==cameraTicket)return;
  $('cameraCaptureStatus').textContent='请正对镜头，保持画面内只有一人，然后点击“拍一张”。';
 }catch(error){if(ticket!==cameraTicket)return;closeDeviceCamera();const message={NotAllowedError:'摄像头权限未获允许。可在浏览器中授权，或改用手机系统拍照 / 文件上传。',NotFoundError:'未找到摄像头，请连接摄像头或上传照片。',NotReadableError:'摄像头可能正被其他软件使用，请关闭占用程序后重试。'};$('cameraCaptureStatus').textContent=message[error.name]||'摄像头暂不可用，请重试或上传照片。';}
 finally{if(ticket===cameraTicket){cameraPending=false;setGalleryBusy(galleryBusy);}}
}
async function takeDevicePhoto(){
 if(!deviceStream||galleryBusy||selectionBusy)return;const video=$('deviceCameraVideo');if(!video.videoWidth){$('cameraCaptureStatus').textContent='摄像头还在准备，请稍后再拍。';return;}
 const c=document.createElement('canvas');c.width=video.videoWidth;c.height=video.videoHeight;c.getContext('2d').drawImage(video,0,0);
 const blob=await new Promise(resolve=>c.toBlob(resolve,'image/jpeg',.95));if(!blob)return;
 await addSelectedPhotos([new File([blob],'设备拍照-'+Date.now()+'.jpg',{type:'image/jpeg'})]);
}
const views={live:{panel:'viewLive',tab:'tabLive',subtitle:'实时画面与识别'},recordings:{panel:'viewRecordings',tab:'tabRecordings',subtitle:'录像控制、回放与文件管理'},database:{panel:'viewDatabase',tab:'tabDatabase',subtitle:'用手机或电脑拍照，登记和管理人员'}};
function switchView(name,updateHash=true){
 if(!views[name])name='live';if(name!=='database')closeDeviceCamera();currentView=name;
 for(const [key,value] of Object.entries(views)){const active=key===name;$(value.panel).hidden=!active;$(value.tab).setAttribute('aria-selected',String(active));$(value.tab).tabIndex=active?0:-1;}
 $('viewSubtitle').textContent=views[name].subtitle;
 window.setCameraViewActive?.(name==='live');if(name==='recordings')window.ensureRecordingPanel?.();
 if(updateHash&&location.hash!=='#'+name)history.replaceState(null,'','#'+name);
 window.scrollTo({top:0,behavior:'instant'});
}
function viewFromHash(){return location.hash==='#galleryPanel'?'database':location.hash.slice(1);}
for(const [name,value] of Object.entries(views)){
 $(value.tab).onclick=()=>switchView(name);
 $(value.tab).onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const keys=Object.keys(views),index=keys.indexOf(name),next=event.key==='Home'?0:event.key==='End'?keys.length-1:(index+(event.key==='ArrowRight'?1:-1)+keys.length)%keys.length;switchView(keys[next]);$(views[keys[next]].tab).focus();};
}
window.addEventListener('hashchange',()=>switchView(viewFromHash(),false));
window.addEventListener('pagehide',()=>{closeDeviceCamera();selectedPhotos.forEach(p=>URL.revokeObjectURL(p.url));});
document.addEventListener('visibilitychange',()=>{if(document.hidden)closeDeviceCamera();});
$('openDeviceCamera').onclick=openDeviceCamera;$('closeDeviceCamera').onclick=()=>{closeDeviceCamera();$('cameraCaptureStatus').textContent='摄像头已关闭，已拍照片仍可确认登记。';};
$('switchDeviceCamera').onclick=()=>{facingMode=facingMode==='user'?'environment':'user';openDeviceCamera();};$('takeDevicePhoto').onclick=takeDevicePhoto;
$('deviceCameraVideo').onloadedmetadata=()=>setGalleryBusy(galleryBusy);
$('chooseEnrollFiles').onclick=()=>$('enrollFiles').click();$('systemCameraButton').onclick=()=>$('devicePhotoFile').click();
$('enrollFiles').onchange=async()=>{await addSelectedPhotos($('enrollFiles').files);$('enrollFiles').value='';};
$('devicePhotoFile').onchange=async()=>{await addSelectedPhotos($('devicePhotoFile').files);$('devicePhotoFile').value='';};
$('clearSelectedPhotos').onclick=()=>{selectedPhotos.forEach(p=>URL.revokeObjectURL(p.url));selectedPhotos=[];renderSelectedPhotos();};
$('personSearch').oninput=()=>{if(galleryData)renderGallery(galleryData);};
switchView(viewFromHash());renderSelectedPhotos();init();
