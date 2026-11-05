'use strict';
const $=id=>document.getElementById(id),names={idle:'已停止',armed:'等待人脸',starting:'正在开始',recording:'正在录像',finishing:'正在保存收尾',error:'录像异常'};
const dateText=t=>new Date(t*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
const sizeText=n=>n>=1073741824?(n/1073741824).toFixed(2)+' GiB':n>=1048576?(n/1048576).toFixed(1)+' MiB':n>=1024?(n/1024).toFixed(1)+' KiB':n+' B';
let sending=false,page=1,pages=1,listVersion=0,listBusy=false;
let confirmResolve=null;
function ask(message){if(confirmResolve)return Promise.resolve(false);$('confirmText').textContent=message;$('confirmDialog').showModal();return new Promise(resolve=>confirmResolve=resolve);}
function answer(value){$('confirmDialog').close();const resolve=confirmResolve;confirmResolve=null;if(resolve)resolve(value);}
$('confirmCancel').onclick=()=>answer(false);$('confirmAccept').onclick=()=>answer(true);$('confirmDialog').oncancel=e=>{e.preventDefault();answer(false);};
const player={id:null,duration:0,pos:0,playing:false,version:0,timer:null,request:null,url:null,base:0,started:0};
async function api(path,body){const r=await fetch(path,{cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});const q=await r.json();if(!r.ok)throw Error(q.error||'服务暂不可用');return q;}
async function storage(){try{const q=await api('/api/storage');
 $('compressionSpace').textContent='副本 '+q.compressed_count+' 段 · '+sizeText(q.compressed_bytes);
 $('storageActive').textContent=sizeText(q.active_bytes)+' · '+q.active_count+' 段';
 $('storageTrash').textContent=sizeText(q.trash_bytes)+' · '+q.trash_count+' 段';
 $('storageUnfinished').textContent=sizeText(q.unfinished_bytes)+' · '+q.unfinished_count+' 段';
 $('storageQuota').textContent=sizeText(q.quota_used_bytes)+' / '+sizeText(q.quota_bytes);
 $('storageDisk').textContent=sizeText(q.disk_free_bytes)+' / '+sizeText(q.disk_total_bytes);
 $('storageAvailable').textContent=sizeText(q.available_recording_bytes);
 $('storageBar').value=Math.min(100,100*q.quota_used_bytes/q.quota_bytes);
 $('storageDetail').textContent='存储信息已更新';
 }catch(e){for(const id of ['storageActive','storageTrash','storageUnfinished','storageQuota','storageDisk','storageAvailable'])$(id).textContent='—';$('storageBar').value=0;$('storageDetail').textContent='存储信息暂不可用：'+e.message;}}
async function status(){try{const q=await api('/api/status');$('state').textContent=(names[q.state]||q.state)+' · '+({off:'关闭',auto:'自动模式',manual:'手动模式'}[q.mode]);
 if($('formatInfo'))$('formatInfo').textContent=q.source_ready?'当前画面：'+q.width+'×'+q.height:'当前没有可用录像输入。';
 $('metrics').textContent='已写 '+q.written_frames+' 帧 · 队列丢帧 '+q.dropped_frames+' · 已用 '+(q.used_bytes/1073741824).toFixed(2)+' GiB / '+(q.quota_bytes/1073741824).toFixed(0)+' GiB · 磁盘可用 '+(q.disk_free_bytes/1073741824).toFixed(1)+' GiB'+(q.last_detection?' · 最近检测 '+q.last_detection.faces+' 张脸（'+q.detection_age_s.toFixed(1)+' 秒前）':'');
 $('warning').textContent=q.error||(!q.source_ready?'摄像头暂无新鲜画面，不能录像。':q.mode==='auto'&&!q.trigger_healthy?'后台检测尚无新鲜结果，自动触发当前不可保证。':'');
 }catch(e){$('state').textContent='连接中断';$('warning').textContent=e.message+'；页面无法确认后台录像状态。';}}
function halt(){player.playing=false;player.version++;clearTimeout(player.timer);if(player.request)player.request.abort();player.request=null;const v=$('playVideo');if(v)v.pause();$('playPause').textContent='播放';}
function closePlayer(){halt();player.id=null;$('player').hidden=true;$('playImage').removeAttribute('src');const v=$('playVideo');if(v){v.pause();v.removeAttribute('src');v.load();v.hidden=true;}if(player.url)URL.revokeObjectURL(player.url);player.url=null;}
async function display(at){const version=player.version,id=player.id,controller=new AbortController();player.request=controller;
 try{const r=await fetch('/api/recordings/'+encodeURIComponent(id)+'/frame?at='+at.toFixed(4),{cache:'no-store',signal:controller.signal});if(!r.ok){const q=await r.json();throw Error(q.error||'回放帧读取失败');}
 const url=URL.createObjectURL(await r.blob()),image=new Image();image.src=url;
 try{await image.decode();}catch(e){URL.revokeObjectURL(url);throw e;}
 if(version!==player.version||id!==player.id){URL.revokeObjectURL(url);return;}
 const old=player.url;player.url=url;$('playImage').src=url;if(old)URL.revokeObjectURL(old);
 player.pos=at;$('playSeek').value=String(at);$('playTime').textContent=at.toFixed(1)+' / '+player.duration.toFixed(1)+' 秒';$('playError').textContent='';
 }catch(e){if(version===player.version&&e.name!=='AbortError'){halt();$('playError').textContent=e.message;}}
 finally{if(player.request===controller)player.request=null;}}
async function tick(){if(!player.playing||!player.id)return;const version=player.version;const at=Math.min(player.duration,player.base+(performance.now()-player.started)/1000*Number($('playRate').value));await display(at);if(version!==player.version||!player.playing)return;if(at>=player.duration){halt();return;}player.timer=setTimeout(tick,100);}
function play(){if(!player.id)return;halt();if(player.pos>=player.duration)player.pos=0;player.playing=true;player.base=player.pos;player.started=performance.now();$('playPause').textContent='暂停';tick();}
function openPlayer(item,compressed=false){closePlayer();player.id=item.id;player.duration=item.capture_span_s;player.pos=0;$('playSeek').max=String(player.duration);$('playSeek').value='0';$('playTitle').textContent='回放 · '+dateText(item.first.received_unix)+(compressed?' · 压缩副本':' · 原片');$('player').hidden=false;$('playError').textContent='';const h264=compressed||item.format==='h264_mp4';$('playImage').hidden=h264;for(const id of ['playPause','playRateLabel','playSeek','playTime'])$(id).hidden=h264;const v=$('playVideo');if(h264){v.hidden=false;v.src='/api/recordings/'+encodeURIComponent(item.id)+(compressed?'/compressed':'/video');v.play().catch(()=>{});}else play();$('player').scrollIntoView({block:'start',behavior:'smooth'});}
$('playPause').onclick=()=>player.playing?halt():play();$('playClose').onclick=closePlayer;
$('playSeek').oninput=()=>{halt();player.pos=Number($('playSeek').value);display(player.pos);};
$('playRate').onchange=()=>{if(player.playing)play();};
document.addEventListener('visibilitychange',()=>{if(document.hidden)halt();});
async function mutate(path,item){if(sending)return;if(path==='/api/trash'&&!await ask('将这段录像移入回收站？可以恢复，暂不释放空间。'))return;if(path==='/api/purge'&&!await ask('永久删除这段录像和时间索引？此操作无法恢复。'))return;
 sending=true;$('manageError').textContent='';try{if(player.id===item.id)closePlayer();await api(path,{id:item.id,...(path==='/api/purge'?{confirm:item.id}:{})});await files();await status();await storage();}catch(e){$('manageError').textContent=e.message;}finally{sending=false;}}
async function files(){const version=++listVersion;listBusy=true;try{const query=new URLSearchParams({page:String(page),limit:'20',from:$('dateFrom').value,to:$('dateTo').value,trash:$('view').value==='trash'?'1':'0'});const q=await api('/api/recordings?'+query);if(version!==listVersion)return;
 if(page>q.pages){page=q.pages;return files();}pages=q.pages;$('files').replaceChildren();$('pageInfo').textContent='第 '+page+' / '+pages+' 页 · 共 '+q.total+' 段';$('prev').disabled=page<=1;$('next').disabled=page>=pages;
 $('filesState').textContent=(q.recordings.length?'':'没有符合条件的录像。')+(q.incomplete_files?' 有 '+q.incomplete_files+' 个未完成文件，已保留供检查。':'')+(q.invalid_records?' 有 '+q.invalid_records+' 条损坏记录未列出。':'');
 for(const item of q.recordings){const li=document.createElement('li'),text=document.createElement('div');text.textContent=dateText(item.first.received_unix)+' · '+item.frames+' 帧 · '+item.capture_span_s.toFixed(1)+' 秒 · '+(item.bytes/1048576).toFixed(1)+' MiB · '+(item.event.trigger==='auto'?'人脸触发':'手动');li.append(text);
 const button=(label,fn)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=fn;li.append(b);};
 if(item.deleted_at!==null){const p=document.createElement('div');p.className='muted';p.textContent='移入回收站：'+dateText(item.deleted_at);li.append(p);button('恢复',()=>mutate('/api/restore',item));button('永久删除',()=>mutate('/api/purge',item));}
 else{button('回放原片',()=>openPlayer(item));for(const [suffix,label] of [[item.format==='h264_mp4'?'mp4':'mjpeg','下载原片'],['frames.jsonl','时间索引'],['json','记录信息']]){const a=document.createElement('a');a.textContent=label;a.href='/files/'+encodeURIComponent(item.id)+'.'+suffix;a.download='';li.append(a);}
 const c=item.compression;if(c&&c.state==='complete'){button('回放压缩版',()=>openPlayer(item,true));const a=document.createElement('a');a.textContent='下载压缩版';a.href='/files/'+encodeURIComponent(item.id)+'.compressed.mp4';a.download='';li.append(a);const info=document.createElement('div');info.className='muted';info.textContent='压缩版 '+sizeText(c.bytes)+'，缩小 '+(100*(1-c.bytes/c.original_bytes)).toFixed(1)+'%；原片保留。';li.append(info);}else if(c){const info=document.createElement('div');info.className='muted';info.textContent=c.state==='skipped'?'已跳过：原片很小或压缩收益不足':'压缩未完成，原片保留。';li.append(info);}
 button('移入回收站',()=>mutate('/api/trash',item));}$('files').append(li);}
 }catch(e){if(version===listVersion)$('filesState').textContent=e.message;}finally{if(version===listVersion)listBusy=false;}}
function renderView(){const trash=$('view').value==='trash';$('filesTitle').textContent=trash?'回收站':'录像文件';$('backToRecordings').hidden=!trash;$('openTrash').textContent=trash?'返回录像':'回收站';}
function switchView(view,clearDates=false,scroll=false){closePlayer();$('view').value=view;if(clearDates){$('dateFrom').value='';$('dateTo').value='';}page=1;renderView();files();if(scroll)$('filesTitle').scrollIntoView({block:'start',behavior:'smooth'});}
$('filter').onsubmit=e=>{e.preventDefault();page=1;files();};$('resetFilter').onclick=()=>switchView('active',true);
$('view').onchange=()=>switchView($('view').value);
$('backToRecordings').onclick=()=>switchView('active',true,true);
$('openTrash').onclick=()=>switchView($('view').value==='trash'?'active':'trash',true,true);
renderView();
$('prev').onclick=()=>{if(page>1){page--;files();}};$('next').onclick=()=>{if(page<pages){page++;files();}};
async function retention(){try{const q=await api('/api/retention');$('retentionEnabled').checked=q.policy.enabled;$('retentionDays').value=q.policy.days;$('trashDays').value=q.policy.trash_days;$('retentionState').textContent=q.error||('自动清理'+(q.policy.enabled?'已启用':'已关闭'));}catch(e){$('retentionState').textContent=e.message;}}
$('retention').onsubmit=async e=>{e.preventDefault();const policy={enabled:$('retentionEnabled').checked,days:Number($('retentionDays').value),trash_days:Number($('trashDays').value)};
 if(policy.enabled&&!await ask('启用后：录像保留 '+policy.days+' 天后移入回收站；回收站内容满 '+policy.trash_days+' 天后永久删除，无法恢复。规则也适用于已有文件。确定启用？'))return;
 try{await api('/api/retention',{policy,confirm:policy.enabled?'delete_after_retention':undefined});await retention();}catch(e){$('retentionState').textContent=e.message;}};
for(const b of document.querySelectorAll('[data-mode]'))b.onclick=async()=>{if(sending)return;sending=true;document.querySelectorAll('[data-mode]').forEach(x=>x.disabled=true);try{await api('/api/mode',{mode:b.dataset.mode});await status();await files();}catch(e){$('warning').textContent=e.message;}finally{sending=false;document.querySelectorAll('[data-mode]').forEach(x=>x.disabled=false);}};
const compressionPhases={waiting:'等待空闲',paused:'已暂停，等待空闲',working:'正在压缩 / 校验',up_to_date:'已处理完可压缩的录像',error:'压缩异常'};
async function compressionStatus(){try{const q=await api('/api/compression');$('compressionEnabled').checked=q.enabled;$('compressionState').textContent=(q.enabled?(compressionPhases[q.phase]||q.phase):'闲时压缩已关闭')+(q.current?' · '+q.current:'')+(q.error?' · '+q.error:'');}catch(e){$('compressionState').textContent=e.message;}}
$('compressionEnabled').onchange=async()=>{const box=$('compressionEnabled');box.disabled=true;try{await api('/api/compression',{policy:{enabled:box.checked}});await compressionStatus();}catch(e){$('compressionState').textContent=e.message;}finally{box.disabled=false;}};
let count=0;async function poll(){await status();if(count%5===0){await storage();await compressionStatus();}if(count++%10===0&&!listBusy&&!sending)await files();setTimeout(poll,1000);}retention();poll();
