const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const base=process.env.DASHBOARD_URL;
if(!base)throw new Error('DASHBOARD_URL is required');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const checks=[];fs.mkdirSync('verification',{recursive:true});
 try{
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
   const renderedNames=await page.locator('.card-top>span:first-child').allTextContents();assert.deepEqual(renderedNames,actual.indicators.map(c=>c.name));
   const expected=await page.evaluate(s=>currentMacro(s),actual);
   assert.equal(await page.locator('#state').textContent(),expected.state);
   if(expected.mode==='limited')assert.match(await page.locator('#uncertainty').textContent(),/DXY.*不完整/);
   for(let i=0;i<actual.indicators.length;i++)if(actual.indicators[i].as_of){
    assert.ok((await page.locator('.card-bottom>span:first-child').nth(i).textContent()).includes(actual.indicators[i].as_of));
   }
   const activeAlerts=await page.evaluate(s=>currentAlerts(s),actual);
   if(activeAlerts.length){assert.equal(await page.locator('#level-alerts').isVisible(),true);assert.match(await page.locator('#level-alerts').textContent(),/较高水平/);}
   assert.ok(await page.locator('.access-details').count());
   const missing=actual.indicators.filter(c=>c.value===null).length;
   assert.equal(await page.locator('.card.missing').count(),missing);
   await page.screenshot({path:`verification/${name}.png`,fullPage:true});
   checks.push({viewport:name,dimensions,cards:17,missing,console_errors:errors,macro:await page.locator('#state').textContent(),mode:expected.mode,absolute_alerts:activeAlerts,independent_dates_checked:true,update_context:actual.update_context});
   await page.close();
  }
  fs.writeFileSync('verification/browser-report.json',JSON.stringify({url:base,checked_at:new Date().toISOString(),checks},null,2));
  console.log(JSON.stringify(checks,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
