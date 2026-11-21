const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const snap=JSON.parse(fs.readFileSync('data/snapshot.json','utf8'));
// Unit fixtures, kept independent of live data and not written to the snapshot.
for(const c of snap.indicators)Object.assign(c,{as_of:'2026-11-19',status:'ok',value:100,change_1:0,change_20:0});
Object.assign(snap.indicators.find(c=>c.id==='dxy'),{value:null,change_20:null,status:'missing'});
Object.assign(snap.indicators.find(c=>c.id==='vix'),{value:28});
snap.macro={state:'有限风险提示',mode:'limited',reason:'波动率上升',uncertainty:'DXY缺失，结论不完整',signals:['VIX · 2026-11-19']};
snap.limited_macro=snap.macro;snap.risk_alerts=[{id:'vix',as_of:'2026-11-19',value:28,unit:'点',message:'波动率处于较高水平'}];
const fixed='2026-11-21T07:00:00Z';
class FixedDate extends Date{constructor(...args){super(...(args.length?args:[fixed]));}static now(){return new Date(fixed).getTime();}}
const elements={};const document={getElementById(id){return elements[id]||=( {textContent:'',innerHTML:'',parentElement:{classList:{add(){}}}} );}};
const context={document,console,Intl,Date:FixedDate,Set,Number,String,Object,Error,input:snap,fetch:async url=>({ok:true,json:async()=>url.includes('snapshot')?snap:{status:'ok'}})};
vm.createContext(context);vm.runInContext(fs.readFileSync('app.js','utf8'),context);
setTimeout(()=>{
 const count=(elements['macro-cards'].innerHTML+elements['asset-cards'].innerHTML).match(/<article /g)||[];
 assert.equal(count.length,17);assert.equal(elements.state.textContent,'有限风险提示');assert.match(elements.uncertainty.textContent,/DXY/);
 assert.equal(elements['state-tag'].textContent,'结论不完整');assert.match(elements['level-alerts'].textContent,/较高水平/);
 assert.match(elements['asset-cards'].innerHTML,/美元 \/ 离岸人民币/);assert.match(elements['macro-cards'].innerHTML,/截至 2026-11-19/);
 assert.equal(vm.runInContext("change({kind:'yield'},25)",context),'+25 bp');assert.equal(vm.runInContext("value({kind:'spread',value:-50})",context),'-50');
 assert.equal(vm.runInContext("currentMacro(input,new Date('2026-11-25T23:00:00Z')).mode",context),'insufficient');
 assert.equal(vm.runInContext("currentAlerts(input,new Date('2026-11-25T23:00:00Z')).length",context),0);
 assert.equal(vm.runInContext("currentMacro(input).mode",context),'limited');
 console.log('UI: 17卡、DXY有限提示、绝对风险、独立日期、过期抑制和bp单位通过');
},30);
