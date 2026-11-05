const assert=require('node:assert/strict');
const {drawFaces,padView}=require('../npu_photo/camera_panel.js');
const boxes=[],labels=[];
const context={strokeRect:(...v)=>boxes.push(v),fillText:t=>labels.push(t),fillRect(){},beginPath(){},arc(){},fill(){},measureText:t=>({width:t.length*9})};
drawFaces(context,[{box:[10,20,110,140],score:.93,landmarks:[[20,30]]},{box:[200,70,280,170],score:.87,landmarks:[]}],[{face_index:1,name:'Registered person'}],960);
assert.deepEqual(boxes,[[10,20,100,120],[200,70,80,100]]);
assert(labels[0].includes('未提取身份')&&labels[0].includes('93.0%'));
assert(labels[1].includes('Registered person')&&labels[1].includes('87.0%'));
const frame={frame_id:9,session:'a',boot_id:'b',source_rgb565_sha256:'hash'};
const result={faces:[{},{}],camera_frame:frame,presentation_attack_detection:{...frame,status:'evaluated',frame_age_ms:700,max_age_ms:3000,
 faces:[{face_index:1,status:'model_non_live'},{face_index:0,status:'model_live'}]}};
const overlay=[0,1].map(i=>padView(result,0,false,'',i));labels.length=0;boxes.length=0;
drawFaces(context,[{box:[10,20,110,140],score:.93,landmarks:[]},{box:[200,70,280,170],score:.87,landmarks:[]}],[],960,overlay);
assert.match(labels[1],/模型判断为真人/);assert.match(labels[3],/疑似攻击/);
assert.match(padView(result,2301,false,'',0).text,/过期/);
result.presentation_attack_detection.faces[1].face_index=1;
assert.match(padView(result,0,false,'',0).text,/不匹配/);
console.log('Overlay coordinates and per-face identity association passed.');
