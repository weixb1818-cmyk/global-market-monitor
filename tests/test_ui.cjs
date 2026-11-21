const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const snap=JSON.parse(fs.readFileSync('data/snapshot.json','utf8'));
// Keep this failure-state test independent from future live provider availability.
const missingDxy=snap.indicators.find(c=>c.id==='dxy');
Object.assign(missingDxy,{value:null,change_20:null,status:'missing'});
const elements={};
const document={getElementById(id){return elements[id] ||= {textContent:'',innerHTML:'',parentElement:{classList:{add(){}}}};}};
const context={document,console,Intl,Date,Set,Number,String,Object,Error,fetch:async(url)=>({ok:true,json:async()=>url.includes('snapshot')?snap:{status:'ok'}})};
vm.createContext(context);
vm.runInContext(fs.readFileSync('app.js','utf8'),context);
setTimeout(()=>{
  const count = (elements['macro-cards'].innerHTML+elements['asset-cards'].innerHTML).match(/<article /g) || [];
  assert.equal(count.length,17);
  assert.match(elements['state'].textContent,/数据不足/);
  assert.match(elements['macro-cards'].innerHTML,/美元指数 DXY/);
  assert.match(elements['asset-cards'].innerHTML,/美元 \/ 离岸人民币/);
  assert.equal(vm.runInContext("change({kind:'yield'},25)",context),'+25 bp');
  assert.equal(vm.runInContext("value({kind:'spread',value:-50})",context),'-50');
  console.log('UI: 17 张卡片、缺失状态及单位格式通过');
},30);
