/* Mount the existing recorder only when its tab is first opened. */
(function(){
 'use strict';
 window.ensureRecordingPanel=function(){
  if(document.getElementById('recordingPanel'))return;
  const section=document.createElement('section');section.id='recordingPanel';section.className='recording-shell';
  const configured=document.querySelector('meta[name="wcis-recorder-url"]');
  const url=configured?new URL(configured.content):new URL(window.location.href);
  if(!configured){url.port='8093';url.pathname='/';url.search='';url.hash='';}
  const frame=document.createElement('iframe');frame.title='录像控制与录像文件';frame.src=url.href;frame.className='recording-frame';
  const link=document.createElement('a');link.href=url.href;link.target='_blank';link.rel='noopener';link.textContent='单独打开录像页面';link.className='recording-link';
  section.append(frame,link);const mount=document.getElementById('recordingMount');
  if(mount)mount.append(section);else{const camera=document.getElementById('cameraPanel');if(camera)camera.after(section);else document.body.append(section);}
 };
 if(!document.getElementById('recordingMount'))window.ensureRecordingPanel();
})();
