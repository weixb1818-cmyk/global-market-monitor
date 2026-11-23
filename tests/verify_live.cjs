const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const base=process.env.DASHBOARD_URL;
if(!base)throw new Error('DASHBOARD_URL is required');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const checks=[];fs.mkdirSync('verification',{recursive:true});
 try{
  // Real Chromium negative-path tests: retained fresh values must never create
  // normal macro/level conclusions after a failed or unknown current fetch.
  const seedPage=await browser.newPage();
  const seed=await (await seedPage.request.get(new URL('data/snapshot.json',base).href)).json();await seedPage.close();
  const negative=[];
  for(const test of [{key:'hy',status:'error',expected:'insufficient'},{key:'dxy',status:'error',expected:'limited'},{key:'vix',status:'unknown',expected:'insufficient'},{total:true,expected:'insufficient'}]){
   const snap=structuredClone(seed);for(const c of snap.indicators){c.status='ok';c.error=null;}
   snap.macro={state:'金融条件趋紧',mode:'full',reason:'fixture',uncertainty:'fixture',signals:['fixture']};
   snap.limited_macro={state:'有限风险提示',mode:'limited',reason:'fixture',uncertainty:'DXY异常，结论不完整',signals:[]};
   snap.risk_alerts=[{id:'hy',value:500,unit:'bp',message:'信用利差处于较高水平',as_of:snap.indicators.find(c=>c.id==='hy').as_of}];
   if(test.key){const c=snap.indicators.find(c=>c.id===test.key);c.status=test.status;c.error=test.status==='error'?'fixture source failure':null;}
   const page=await browser.newPage();
   await page.route('**/data/snapshot.json',route=>route.fulfill({json:snap}));
   await page.route('**/data/last_attempt.json',route=>route.fulfill({json:{status:test.total?'failed':'partial',at:new Date().toISOString(),update_context:seed.update_context}}));
   await page.goto(base,{waitUntil:'networkidle'});await page.waitForSelector('.card');
   assert.equal(await page.locator('#state').textContent(),test.expected==='limited'?'有限风险提示':'数据不足：暂不判断');
   if(test.key==='hy'||test.total)assert.equal(await page.locator('#level-alerts').isVisible(),false);
   if(test.key){const i=snap.indicators.findIndex(c=>c.id===test.key);const card=page.locator('.card').nth(i);assert.match(await card.locator('.interpretation').textContent(),/仅保留历史|数据暂未更新/);assert.ok((await card.locator('.card-value').textContent()).length>1);}
   negative.push({...test,passed:true});await page.close();
  }
  fs.writeFileSync('verification/status-boundary-browser.json',JSON.stringify(negative,null,2));
  for(const [name,size] of [['desktop',{width:1440,height:900}],['mobile',{width:390,height:844}]]){
   const page=await browser.newPage({viewport:size});const errors=[];page.on('pageerror',e=>errors.push(e.message));
   const response=await page.goto(base,{waitUntil:'networkidle',timeout:60000});assert.equal(response.status(),200);
   await page.waitForSelector('.card',{timeout:20000});assert.equal(await page.locator('.card').count(),17);assert.deepEqual(errors,[]);
   await page.screenshot({path:`verification/${name}.png`,fullPage:true});
   const dimensions=await page.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,cardBottom:Math.max(...Array.from(document.querySelectorAll('.card'),c=>c.getBoundingClientRect().bottom))}));
   console.log(name,JSON.stringify(dimensions));
   assert.ok(dimensions.scroll<=dimensions.width,`${name}: horizontal overflow ${JSON.stringify(dimensions)}`);
   if(name==='desktop')assert.ok(dimensions.cardBottom<=900,`desktop cards do not fit first screen: ${dimensions.cardBottom}`);
   const actual=await (await page.request.get(new URL('data/snapshot.json',base).href)).json();assert.equal(actual.indicators.length,17);
   if(process.env.EXPECTED_RUN_URL)assert.equal(actual.update_context.run_url,process.env.EXPECTED_RUN_URL,'snapshot must belong to the workflow that triggered verification');
   if(process.env.EXPECTED_EVENT)assert.equal(actual.update_context.event,process.env.EXPECTED_EVENT,'actual GitHub trigger must survive publication');
   if(process.env.EXPECTED_EVENT==='schedule')assert.ok(['15 0 * * *','45 0 * * *','15 2 * * *'].includes(actual.update_context.schedule));
   const renderedNames=await page.locator('.card-top>span:first-child').allTextContents();assert.deepEqual(renderedNames,actual.indicators.map(c=>c.name));
   for(let i=0;i<actual.indicators.length;i++)if(actual.indicators[i].series_definition?.includes('reference'))assert.equal(await page.locator('.card-group').nth(i).textContent(),'参考','reference label must remain visible even when the full title is truncated');
   const expected=await page.evaluate(s=>currentMacro(s),actual);
   assert.equal(await page.locator('#state').textContent(),expected.state);
   if(expected.mode==='limited')assert.match(await page.locator('#uncertainty').textContent(),/DXY.*不完整/);
   for(let i=0;i<actual.indicators.length;i++)if(actual.indicators[i].as_of){
    assert.ok((await page.locator('.card-bottom>span:first-child').nth(i).textContent()).includes(actual.indicators[i].as_of));
   }
   const activeAlerts=await page.evaluate(s=>currentAlerts(s),actual);
   for(const c of actual.indicators.filter(c=>c.provider==='frankfurter'&&c.value!==null)){
    assert.ok(c.name.includes('参考'),'blended data must be visibly labelled reference');
    assert.ok(c.source_components.length>0,'blended dates must be retained');
    assert.ok(c.source_components.every(p=>p.date<=c.as_of),'no future source dates');
    assert.ok(c.source_components.some(p=>p.date===c.as_of),'do not redate an entirely old blend');
   }
   if(activeAlerts.length){assert.equal(await page.locator('#level-alerts').isVisible(),true);assert.match(await page.locator('#level-alerts').textContent(),/较高水平/);}
   assert.ok(await page.locator('.access-details').count());
   const missing=actual.indicators.filter(c=>c.value===null).length;
   assert.equal(await page.locator('.card.missing').count(),missing);
   const copperIndex=actual.indicators.findIndex(c=>c.id==='copper');const copper=actual.indicators[copperIndex];
   if(copper.value!==null&&copper.source?.includes('末笔快照')){
    assert.equal(await page.locator('.card-group').nth(copperIndex).textContent(),'快照');
    assert.match(copper.source,/非官方结算/);
    if(copper.observation_count<21){assert.equal(copper.change_20,null);assert.match(await page.locator('.interpretation').nth(copperIndex).textContent(),/不足|未更新/);}
   }
   await page.screenshot({path:`verification/${name}.png`,fullPage:true});
   assert.equal(await page.locator('#methodology').getAttribute('open'),null,'methodology should start collapsed');
   await page.locator('#methodology>summary').click();
   assert.equal(await page.locator('.methodology-table tbody tr').count(),17);
   assert.deepEqual(await page.locator('.methodology-table tbody tr').evaluateAll(rows=>rows.map(r=>r.dataset.indicator)),actual.indicators.map(c=>c.id));
   assert.ok(await page.locator('.methodology-table a').count()>=17,'every indicator needs an official source link');
   assert.match(await page.locator('.calculation-rules').textContent(),/至少需要21个值/);
   for(const id of ['spread10y2y','spread10y3m']){
    const check=actual.spread_checks.find(c=>c.id===id);
    const text=await page.locator('#'+id+'-check').textContent();
    assert.match(text,check.status==='ok'?/已完成同日底层交叉核验/:check.status==='warning'?/存在差异/:/尚未完成同日底层交叉核验/);
   }
   for(let i=0;i<actual.indicators.length;i++){
    const c=actual.indicators[i];
    if(c.value!==null&&(c.error||c.status==='error')&&await page.evaluate(({c,s})=>stale(c,s),{c,s:actual}))
     assert.match(await page.locator('.card-status').nth(i).textContent(),/数据延迟.*更新失败.*沿用历史/);
   }
   const history=actual.history_checks.find(c=>c.id==='copper');
   if(history.status==='ok'){assert.equal(history.observations,history.unique_dates);assert.equal(history.ascending,true);assert.deepEqual(history.missing_sessions,[]);}
   const expandedWidth=await page.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
   assert.ok(expandedWidth.scroll<=expandedWidth.width,`${name}: methodology overflows page`);
   if(name==='mobile'){const widths=await page.locator('.methodology-table tbody tr:first-child').evaluate(row=>({row:row.getBoundingClientRect().width,heading:row.querySelector('th').getBoundingClientRect().width}));assert.ok(widths.heading>=widths.row-4,'mobile indicator heading must fill its row');}
   await page.screenshot({path:`verification/${name}-methodology.png`,fullPage:true});
   checks.push({viewport:name,dimensions,cards:17,missing,console_errors:errors,macro:await page.locator('#state').textContent(),mode:expected.mode,absolute_alerts:activeAlerts,independent_dates_checked:true,methodology_rows:17,methodology_no_overflow:true,update_context:actual.update_context});
   await page.close();
  }
  fs.writeFileSync('verification/browser-report.json',JSON.stringify({url:base,checked_at:new Date().toISOString(),checks},null,2));
  console.log(JSON.stringify(checks,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
