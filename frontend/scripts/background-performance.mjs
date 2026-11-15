/* global window, PerformanceObserver, performance, document, innerWidth */
import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import console from 'node:console';
const browser=await chromium.launch();
const results=[];
try{
 for(const width of [375,1440])for(const enabled of [false,true])for(let sample=0;sample<3;sample++){
  const context=await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'});
  const page=await context.newPage();
  if(!enabled)await page.route('**/backgrounds/**',route=>route.abort());
  await page.addInitScript(()=>{
   window.backgroundMetrics={lcp:null,cls:0};
   new PerformanceObserver(list=>{for(const e of list.getEntries())window.backgroundMetrics.lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});
   new PerformanceObserver(list=>{for(const e of list.getEntries())if(!e.hadRecentInput)window.backgroundMetrics.cls+=e.value}).observe({type:'layout-shift',buffered:true});
  });
  await page.goto(process.env.BASE_URL||'http://localhost:3206');
  if(enabled)await page.locator('[data-testid="random-background"][data-state="ready"]').waitFor();
  await page.waitForTimeout(1500);
  results.push({width,enabled,sample,...await page.evaluate(()=>({...window.backgroundMetrics,overflow:document.documentElement.scrollWidth>innerWidth,images:performance.getEntriesByType('resource').filter(e=>e.name.includes('/backgrounds/')).map(e=>({bytes:e.encodedBodySize,duration:e.duration}))}))});
  if(sample===0&&enabled){await mkdir('test-results',{recursive:true});await page.screenshot({path:`test-results/background-${width}.png`,fullPage:true});}
  await context.close();
 }
 await mkdir('test-results',{recursive:true});await writeFile('test-results/background-performance.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
}finally{await browser.close()}
