'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtDate = d => new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(d));
function nyParts(now) {
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}).formatToParts(now);
  return Object.fromEntries(parts.map(p=>[p.type,p.value]));
}
function dateAdd(d,n){ const t = new Date(d+'T00:00:00Z'); t.setUTCDate(t.getUTCDate()+n); return t.toISOString().slice(0,10); }
function stale(card, snap, now=new Date()) {
  if (!card.as_of || card.status==='missing') return true;
  if (card.calendar==='crypto') return now - new Date(dateAdd(card.as_of,1)+'T00:00:00Z') > snap.thresholds.crypto_stale_hours*3600000;
  const p=nyParts(now); let end=`${p.year}-${p.month}-${p.day}`;
  if (+p.hour<18) end=dateAdd(end,-1);
  if (!snap.calendar || !snap.calendar.nyse) return true;
  // Refuse to infer freshness if the bundled calendar does not reach today's date.
  const year=+end.slice(0,4); if (!snap.calendar.nyse.some(d=>+d.slice(0,4)===year)) return true;
  const sessions=snap.calendar[card.calendar];
  if (!sessions || !sessions.some(d=>+d.slice(0,4)===year)) return true;
  return sessions.filter(d=>d>card.as_of&&d<=end).length>snap.thresholds.max_missing_sessions;
}
function currentMacro(data,now=new Date()) {
 const required=['dxy','real10y','us2y','hy','vix'];
 const invalid=data.indicators.filter(c=>required.includes(c.id)&&(stale(c,data,now)||c.change_20===null||c.value===null));
 if(!invalid.length)return data.macro;
 if(invalid.every(c=>c.id==='dxy')&&data.limited_macro)return data.limited_macro;
 return {state:'数据不足：暂不判断',mode:'insufficient',reason:'关键数据缺失或过期：'+invalid.map(c=>c.name).join('、'),uncertainty:'无法可靠判断；仅展示仍有效的绝对风险水平',signals:[]};
}
function currentAlerts(data,now=new Date()) {
 return (data.risk_alerts||[]).filter(a=>{const c=data.indicators.find(c=>c.id===a.id);return c&&!stale(c,data,now);});
}
function signed(n,digits=2){ if(n===null||n===undefined||!Number.isFinite(n))return '—'; return (n>0?'+':'')+n.toFixed(digits); }
function value(c){if(c.value===null||c.value===undefined||!Number.isFinite(c.value))return '—'; const n=c.value; if(c.kind==='spread')return (n>0?'+':'')+n.toFixed(0); return n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:c.id==='usdjpy'||c.id==='usdcnh'?4:2});}
function change(c,n){if(n===null||n===undefined||!Number.isFinite(n))return '—'; if(c.kind==='yield'||c.kind==='spread')return signed(n,0)+' bp'; if(c.kind==='points')return signed(n,2)+' 点'; return signed(n,2)+'%';}
function cardHTML(c,snap){
  const delayed=stale(c,snap); const status=c.value===null?'missing':delayed?'stale':c.status;
  const labels={missing:'数据缺失',stale:'数据延迟',error:'更新失败 · 沿用',ok:''};
  const interpretation=delayed&&c.value!==null?'数据暂未更新，截至'+c.as_of:(c.interpretation||'数据暂不可用，等待有效行情');
  const source=c.source?`来源：${c.source}`:'来源待接入';
  return `<article class="card ${esc(status)}" title="${esc(source)}${c.error?'；'+esc(c.error):''}${c.warning?'；'+esc(c.warning):''}"><div class="card-top"><span>${esc(c.name)}</span><span class="card-group">${esc(c.group)}</span></div><div class="card-value">${esc(value(c))}<span class="unit">${esc(c.unit)}</span></div><div class="changes"><span><em>前期</em>${esc(change(c,c.change_1))}</span><span><em>近20期</em>${esc(change(c,c.change_20))}</span></div><p class="interpretation">${esc(interpretation)}</p><div class="card-bottom"><span>${esc(c.as_of?'截至 '+c.as_of:'日期未知')}</span><span class="card-status">${esc(labels[status]||'')}</span></div></article>`;
}
async function load(){
 try{
  const [r,attemptResponse]=await Promise.all([fetch('data/snapshot.json',{cache:'no-store'}),fetch('data/last_attempt.json',{cache:'no-store'}).catch(()=>null)]);
  if(!r.ok) throw new Error('快照文件不可用');
  const data=await r.json(); if(!Array.isArray(data.indicators)||data.indicators.length!==17||!data.macro)throw new Error('快照格式错误');
  const attempt=attemptResponse&&attemptResponse.ok?await attemptResponse.json():null;
  $('timestamp').textContent='生成于 '+fmtDate(data.generated_at)+' 东京时间';
  const m=currentMacro(data);
  $('state').textContent=m.state; $('state-tag').textContent=m.mode==='limited'?'结论不完整':m.mode==='insufficient'?'数据不足':m.state==='中性/信号分歧'?'信号分歧':'规则状态'; $('reason').textContent=m.reason; $('uncertainty').textContent='不确定因素：'+m.uncertainty;
  const alerts=currentAlerts(data);
  $('level-alerts').textContent=alerts.map(a=>`${a.id==='vix'?'VIX':'HY'} ${a.value.toFixed(a.id==='vix'?2:0)}${a.unit}：${a.message} · ${a.as_of}`).join('；');
  $('level-alerts').hidden=!alerts.length;
  $('signals').innerHTML=(m.signals.length?m.signals:['等待关键数据']).map(s=>`<span>${esc(s)}</span>`).join('');
  $('macro-cards').innerHTML=data.indicators.filter(c=>c.group==='宏观').map(c=>cardHTML(c,data)).join('');
  $('asset-cards').innerHTML=data.indicators.filter(c=>c.group!=='宏观').map(c=>cardHTML(c,data)).join('');
  const ctx=(attempt&&attempt.update_context)||data.update_context;
  if(ctx&&ctx.run_url){$('workflow-link').href=ctx.run_url;$('workflow-link').textContent=(ctx.event==='schedule'?'定时':'手动/本地')+'更新记录';$('workflow-link').hidden=false;}
  if(attempt&&attempt.status==='failed') {$('notice').textContent='最近一次更新失败，显示上次有效快照；本页数据截至各卡标注日期';$('notice').parentElement.classList.add('warning');}
  else if(data.sources_failed) {$('notice').textContent=`${data.sources_failed} 项来源更新失败或未配置；本页数据截至各卡标注日期`;$('notice').parentElement.classList.add('warning');}
 }catch(e){$('state').textContent='数据不足：暂不判断';$('state-tag').textContent='无法读取';$('reason').textContent='未能读取有效快照，请使用本地 HTTP 服务打开页面。';$('uncertainty').textContent='本页不会展示模拟行情。';$('notice').textContent='读取失败：'+e.message;}
}
load();
