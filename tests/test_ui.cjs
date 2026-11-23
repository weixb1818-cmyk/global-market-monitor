const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const snap=JSON.parse(fs.readFileSync('data/snapshot.json','utf8'));
// Unit fixtures, kept independent of live data and not written to the snapshot.
for(const c of snap.indicators)Object.assign(c,{as_of:'2026-11-19',status:'ok',value:100,change_1:0,change_20:0,error:null});
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
 assert.match(vm.runInContext("spreadCheckText({status:'not_comparable'})",context),/尚未完成同日底层交叉核验/);
 assert.match(vm.runInContext("spreadCheckText(undefined)",context),/尚未完成/);
 assert.match(vm.runInContext("spreadCheckText({status:'ok',as_of:'2026-11-19'})",context),/已完成.*2026-11-19/);
 assert.match(vm.runInContext("spreadCheckText({status:'warning',as_of:'2026-11-19'})",context),/存在差异/);
 assert.match(elements['spread10y2y-check'].textContent,/尚未完成/);
 for(const status of ['stale','error']){
  const html=vm.runInContext(`cardHTML({...input.indicators[0],value:100,as_of:'2026-11-01',status:'${status}',error:'network'},input)`,context);
  assert.match(html,/数据延迟 · 更新失败，沿用历史/);assert.match(html,/截至 2026-11-01/);
 }
 const delayed=vm.runInContext("cardHTML({...input.indicators[0],value:100,as_of:'2026-11-01',status:'stale',error:null},input)",context);
 assert.match(delayed,/class="card-status">数据延迟<\/span>/);
 assert.doesNotMatch(delayed,/更新失败/);
 const failed=vm.runInContext("cardHTML({...input.indicators[1],status:'error',error:'network'},input)",context);
 assert.match(failed,/更新失败 · 沿用/);
 for(const status of ['error','stale','missing','unknown',undefined]){
  const altered=structuredClone(snap);altered.indicators.find(c=>c.id==='hy').status=status;context.altered=altered;
  assert.equal(vm.runInContext('currentMacro(altered).mode',context),'insufficient');
 }
 const errorAlert=structuredClone(snap);errorAlert.indicators.find(c=>c.id==='vix').status='error';context.errorAlert=errorAlert;
 assert.equal(vm.runInContext('currentAlerts(errorAlert).length',context),0);
 assert.match(failed,/仅保留历史/);
 assert.equal(vm.runInContext("updateOverdue({at:'2026-11-21T00:20:00Z'},new Date('2026-11-21T03:00:00Z'))",context),false);
 assert.equal(vm.runInContext("updateOverdue({at:'2026-11-20T00:20:00Z'},new Date('2026-11-21T03:00:00Z'))",context),true);
 console.log('UI: 17卡、宏观提示、日期/bp、曲线核验状态及延迟与失败组合提示通过');
},30);
