import {test, expect, Page} from '@playwright/test';

// Each scenario gets its own rate-limit window on the CI-only server.
// Production keeps its normal limit and does not expose this endpoint.
test.beforeEach(async({request})=>{
 await expect.poll(async()=>{
  try{return (await request.post((process.env.API_INTERNAL_URL||'http://127.0.0.1:8000')+'/__test/reset-rate-limits',{timeout:2000})).status()}catch{return 0}
 },{timeout:10000}).toBe(204);
});

// Only the CI-only test server generates this known image; production is always random.
const captchaAnswer = 'K7M9Q';
async function register(page: Page, username: string) {
  await page.getByLabel('用户名', {exact:true}).fill(username);
  await page.getByLabel('密码 · 至少10个字符').fill('test-long-password');
  await page.getByLabel('图案验证码', {exact:true}).fill(captchaAnswer);
  const registration = page.waitForResponse(r => r.url().endsWith('/api/v1/auth/register') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'创建账户，开启日常'}).click();
  const response = await registration;
  expect(response.status(), await response.text()).toBe(200);
  await expect(page.getByRole('navigation', {name:'主导航'})).toBeVisible();
}

test('mobile registration → meal → advisor → cookie restore → login data sync', async ({page}) => {
  const username = 'e2e_' + Date.now();
  await page.goto('/');
  await expect(page.getByRole('navigation')).toHaveCount(0);
  await expect(page.getByRole('button', {name:'AI识餐',exact:true})).toHaveCount(0);
  await expect(page.getByLabel('邮箱', {exact:true})).toHaveCount(0);
  await register(page, username);
  const session = (await page.context().cookies()).find(c => c.name === 'lifeos_session');
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe('Strict');
  await page.getByRole('button', {name:'AI识餐',exact:true}).click();
  await page.getByLabel('克数', {exact:true}).fill('180');
  await page.getByRole('button', {name:'确认并保存记录'}).click();
  await expect(page.getByRole('status').filter({hasText:'已保存到你的饮食记录'})).toBeVisible();
  await page.getByRole('button', {name:'AI饮食规划',exact:true}).click();
  await page.getByRole('button', {name:'生成下一餐',exact:true}).click();
  await expect(page.getByRole('alert').filter({hasText:'模型'}).last()).toBeVisible();
  await page.getByRole('button', {name:'打开AI顾问'}).click();
  await page.getByLabel('顾问问题').fill('下一餐蔬菜怎么选');
  await page.getByRole('button', {name:'发送问题'}).click();
  await expect(page.getByText('模式：unavailable')).toBeVisible();
  await page.getByRole('button', {name:'关闭顾问'}).click();
  await page.reload();
  await expect(page.getByRole('navigation', {name:'主导航'})).toBeVisible();
  await page.getByRole('button', {name:'历史记录',exact:true}).click();
  await expect(page.getByText('糙米饭 180g', {exact:false})).toBeVisible();
  await page.getByRole('button', {name:'退出登录'}).click();
  await expect(page.getByRole('navigation')).toHaveCount(0);
  expect((await page.context().cookies()).some(c => c.name === 'lifeos_session')).toBe(false);
  await page.getByRole('button', {name:'已有账户？登录'}).click();
  await expect(page.getByLabel('图案验证码', {exact:true})).toHaveCount(0);
  await page.getByLabel('用户名', {exact:true}).fill(username);
  await page.getByLabel('密码 · 至少10个字符').fill('test-long-password');
  await page.getByRole('button', {name:'登录',exact:true}).click();
  await expect(page.getByRole('navigation', {name:'主导航'})).toBeVisible();
  await page.getByRole('button', {name:'历史记录',exact:true}).click();
  await expect(page.getByText('糙米饭 180g', {exact:false})).toBeVisible();
  // A different account must not inherit the previous user's cache or records.
  await page.getByRole('button', {name:'退出登录'}).click();
  await register(page, username + '_other');
  await page.getByRole('button', {name:'历史记录',exact:true}).click();
  await expect(page.getByText('暂无饮食记录，先去记录一餐吧。')).toBeVisible();
  await expect(page.getByText('糙米饭 180g', {exact:false})).toHaveCount(0);
});

test('invalid image code rejects registration and refreshes the challenge', async ({page}) => {
  await page.goto('/');
  await page.getByLabel('用户名', {exact:true}).fill('reject_' + Date.now());
  await page.getByLabel('密码 · 至少10个字符').fill('test-long-password');
  await page.getByLabel('图案验证码', {exact:true}).fill('WRONG');
  await page.getByRole('button', {name:'创建账户，开启日常'}).click();
  await expect(page.getByRole('alert').filter({hasText:'验证码错误或已过期'})).toBeVisible();
  await expect(page.getByRole('navigation')).toHaveCount(0);
  await expect(page.getByLabel('图案验证码', {exact:true})).toHaveValue('');
  await page.getByLabel('图案验证码', {exact:true}).fill(captchaAnswer);
  await page.getByRole('button', {name:'创建账户，开启日常'}).click();
  await expect(page.getByRole('navigation', {name:'主导航'})).toBeVisible();
});


test('privacy defaults are enabled and manual changes survive reload', async ({page}) => {
  await page.goto('/');
  await register(page, 'privacy_' + Date.now());
  await page.getByRole('button', {name:'数据与隐私',exact:true}).click();
  await expect(page.getByRole('heading', {name:'数据源连接',exact:true})).toHaveCount(0);
  await page.route('**/api/v1/consents',async route=>{
    if(route.request().method()==='PUT') await new Promise(resolve=>setTimeout(resolve,250));
    await route.continue();
  });
  const options=page.locator('label.consent input[type="checkbox"]');
  await expect(options).toHaveCount(3);
  for (let i=0;i<3;i++) await expect(options.nth(i)).toBeChecked();
  for (let i=0;i<3;i++) {
    const saved=page.waitForResponse(r=>r.url().endsWith('/api/v1/consents') && r.request().method()==='PUT');
    await options.nth(i).uncheck();
    expect((await saved).status()).toBe(200);
    await expect(options.nth(i)).not.toBeChecked();
    await expect(options.nth(i)).toBeEnabled();
  }
  await page.reload();
  await page.getByRole('button', {name:'数据与隐私',exact:true}).click();
  for (let i=0;i<3;i++) await expect(options.nth(i)).not.toBeChecked();
});


test('privacy save failure restores the previous choice', async ({page}) => {
  await page.goto('/');
  await register(page,'rollback_'+Date.now());
  await page.getByRole('button',{name:'数据与隐私',exact:true}).click();
  await page.route('**/api/v1/consents',async route=>{
    if(route.request().method()==='PUT')
      await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'测试：保存失败'})});
    else await route.continue();
  });
  const option=page.locator('label.consent input[type="checkbox"]').first();
  await expect(option).toBeChecked();
  await option.click();
  await expect(page.getByText('测试：保存失败',{exact:true})).toBeVisible();
  await expect(option).toBeChecked();
  await expect(option).toBeEnabled();
  await page.reload();
  await page.getByRole('button',{name:'数据与隐私',exact:true}).click();
  await expect(option).toBeChecked();
});

test('dynamic food persists and full advisor keeps conversations isolated', async ({page}) => {
  await page.goto('/');
  await register(page,'catalog_'+Date.now());
  await page.getByRole('button',{name:'AI食物知识库',exact:true}).click();
  const food='测试蔬菜汤'+Date.now();
  await page.getByRole('button',{name:'添加食物',exact:true}).click();
  await page.getByRole('button',{name:'完全手动录入',exact:false}).click();
  await page.getByLabel('食物名称',{exact:true}).fill(food);
  await page.getByLabel('热量 kcal / 100g',{exact:true}).fill('40');
  await page.getByRole('button',{name:'保存食物到目录',exact:true}).click();
  await page.locator('.catalog-tile').filter({hasText:food}).getByRole('button',{name:'详情',exact:true}).click();
  await page.getByRole('button',{name:'编辑',exact:true}).click();
  await page.getByLabel('热量 kcal / 100g',{exact:true}).fill('45');
  await page.getByRole('button',{name:'保存食物到目录',exact:true}).click();
  await page.locator('.catalog-tile').filter({hasText:food}).getByRole('button',{name:'选择',exact:true}).click();
  await expect(page.getByLabel('搜索食物',{exact:true})).toHaveValue(food);
  await page.getByRole('button',{name:'确认并保存记录'}).click();
  await expect(page.getByRole('status').filter({hasText:'已保存到你的饮食记录'})).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:'历史记录',exact:true}).click();
  await expect(page.getByText(food+' 100g',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'数据与隐私',exact:true}).click();
  await expect(page.getByRole('heading',{name:'AI 供应商配置'})).toHaveCount(0);
  await page.getByRole('button',{name:'打开AI顾问'}).click();
  await page.getByRole('link',{name:'打开完整 AI 对话中心 ↗'}).click();
  await expect(page).toHaveURL(/\/advisor/);
  await page.getByLabel('输入问题',{exact:true}).fill('下一餐蔬菜怎么选');
  await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByRole('button',{name:'复制消息',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'重新生成',exact:true}).click();
  await expect(page.getByRole('button',{name:'停止生成',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'复制消息',exact:true})).toHaveCount(1);
  await page.getByRole('button',{name:'展开历史对话',exact:true}).click();
  await page.getByRole('button',{name:'＋ 新建对话',exact:true}).click();
  await expect(page.getByRole('button',{name:'复制消息',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'展开历史对话',exact:true}).click();
  await page.getByRole('navigation',{name:'历史对话'}).getByRole('button',{name:'下一餐蔬菜怎么选',exact:true}).click();
  await expect(page.getByRole('button',{name:'复制消息',exact:true})).toHaveCount(1);
  await page.screenshot({path:'test-results/advisor-mobile.png',fullPage:true});
  await page.reload();
  await expect(page.getByRole('button',{name:'复制消息',exact:true})).toHaveCount(1);
  const width=await page.evaluate(()=>document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390);
});

test.describe('desktop advisor',()=>{
  test.use({viewport:{width:1280,height:900},isMobile:false,deviceScaleFactor:1});
  test('desktop history can be renamed and deleted',async({page})=>{
    await page.goto('/');
    await register(page,'desktop_'+Date.now());
    await page.getByRole('button',{name:'打开AI顾问'}).click();
    await page.getByRole('link',{name:'打开完整 AI 对话中心 ↗'}).click();
    await page.getByLabel('输入问题',{exact:true}).fill('如何搭配蔬菜');
    await page.getByRole('button',{name:'发送',exact:true}).click();
    await expect(page.getByRole('button',{name:'复制消息',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'展开历史对话',exact:true}).click();
    await expect(page.getByRole('navigation',{name:'历史对话'})).toBeVisible();
    page.once('dialog',dialog=>dialog.accept('我的饮食计划'));
    await page.getByRole('button',{name:'重命名 如何搭配蔬菜',exact:true}).click();
    await expect(page.getByRole('navigation',{name:'历史对话'}).getByRole('button',{name:'我的饮食计划',exact:true})).toBeVisible();
    await page.getByLabel('搜索历史对话').fill('我的饮食');
    await page.screenshot({path:'test-results/advisor-desktop.png',fullPage:true});
    page.once('dialog',dialog=>dialog.accept());
    await page.getByRole('button',{name:'删除 我的饮食计划',exact:true}).click();
    await expect(page.getByRole('button',{name:'复制消息',exact:true})).toHaveCount(0);
    await expect(page.getByRole('navigation',{name:'历史对话'}).getByRole('button',{name:'我的饮食计划',exact:true})).toHaveCount(0);
  });
});

for(const width of [375,768,1024,1440]){
 test('shared shell and catalog at '+width+'px',async({page})=>{
  await page.setViewportSize({width,height:900});
  await page.goto('/');await register(page,'design_'+width+'_'+Date.now());
  await page.getByRole('button',{name:'AI食物知识库',exact:true}).click();
  await expect(page.locator('.catalog-tile')).toHaveCount(6);
  await expect(page.getByLabel('食物名称',{exact:true})).toHaveCount(0);
  const image=page.locator('.catalog-cover img').first();
  await expect(image).toBeVisible();
  await expect.poll(()=>image.evaluate((node:HTMLImageElement)=>node.complete&&node.naturalWidth>0)).toBe(true);
  await page.getByRole('button',{name:'添加食物',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'添加食物'})).toBeVisible();
  await page.getByRole('button',{name:'输入名称，让 AI 补充',exact:false}).click();
  await page.route('**/api/v1/food/catalog/suggest',route=>route.fulfill({json:{proposal:{name:'草稿汤',category:'汤',ingredients:['蔬菜'],kcal:30,protein:2,fat:1,carbs:3,image_id:null},warning:'估算',saved:false}}));
  await page.getByLabel('食物名称',{exact:true}).fill('草稿汤');
  await page.getByRole('button',{name:'生成草稿',exact:true}).click();
  await expect(page.getByLabel('热量 kcal / 100g',{exact:true})).toHaveValue('30');
  await page.getByRole('button',{name:'关闭弹窗'}).click();
  await expect(page.locator('.catalog-tile')).toHaveCount(6);
  await page.screenshot({path:'test-results/catalog-'+width+'.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'问问智膳'}).click();
  await expect(page.getByRole('heading',{name:'今天，想从哪里开始？'})).toBeVisible();
  await expect(page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'问问智膳'})).toHaveAttribute('aria-current','page');
  await expect(page.locator('.suggestion-grid button')).toHaveCount(4);
  if(width<=760){const selected=await page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'问问智膳'}).boundingBox();expect(selected!.x).toBeGreaterThanOrEqual(0);expect(selected!.x+selected!.width).toBeLessThanOrEqual(width)}
  await expect(page.getByRole('navigation',{name:'历史对话'})).toHaveCount(0);
  await page.getByRole('button',{name:'展开历史对话'}).click();
  await expect(page.getByRole('dialog',{name:'历史对话'})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const composer=await page.locator('.advisor-composer').boundingBox();
  expect(composer!.y+composer!.height).toBeLessThan(900-(width<=760?69:0));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.screenshot({path:'test-results/advisor-'+width+'.png',fullPage:true});
  await page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'AI识餐'}).click();
  await expect(page.getByRole('heading',{name:'拍一张，认识这一餐'})).toBeVisible();
 });
}


test('advisor retries a transient session error without showing registration',async({page})=>{
 await page.goto('/');await register(page,'retry_'+Date.now());
 let fail=true;
 await page.route('**/api/v1/me',route=>fail?route.fulfill({status:429,body:'Too many requests'}):route.continue());
 await page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'问问智膳'}).click();
 await expect(page.getByRole('alert').filter({hasText:'请求过于频繁'})).toBeVisible();
 await expect(page.getByRole('form',{name:'账户注册'})).toHaveCount(0);
 fail=false;await page.getByRole('button',{name:'重试恢复会话'}).click();
 await expect(page.getByRole('heading',{name:'今天，想从哪里开始？'})).toBeVisible();
});

test('knowledge retrieval, profile skip and unavailable AI are explicit',async({page})=>{
 await page.goto('/');await register(page,'ai_flow_'+Date.now());
 await page.getByRole('button',{name:'AI食物知识库',exact:true}).click();
 await page.getByLabel('知识检索问题').fill('全谷物 燕麦 主食');
 await page.getByRole('button',{name:'检索知识',exact:true}).click();
 await expect(page.getByRole('heading',{name:'全谷物与主食搭配'})).toBeVisible();
 await expect(page.getByRole('link',{name:'查看来源 ↗'}).first()).toHaveAttribute('href',/who.int/);
 await page.getByRole('link',{name:'带着问题问问智膳 ↗'}).click();
 await expect(page.getByLabel('输入问题',{exact:true})).toHaveValue('全谷物 燕麦 主食');
 await page.getByRole('button',{name:'饮食建档',exact:true}).click();
 await page.getByRole('button',{name:'跳过',exact:true}).click();
 await expect(page.getByRole('button',{name:'确认保存',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'关闭弹窗'}).click();
 await page.getByRole('button',{name:'发送',exact:true}).click();
 await expect(page.getByRole('button',{name:'复制消息',exact:true})).toBeVisible();
 await expect(page.getByText(/AI当前不可用/)).toBeVisible();
});

test('voice transcript remains editable and is not sent automatically',async({page})=>{
 // Test-only browser API double; this does not validate microphone hardware/service.
 await page.addInitScript(()=>{
  class Recognition {
   lang='';interimResults=false;onresult:((e:unknown)=>void)|null=null;onend:(()=>void)|null=null;
   start(){setTimeout(()=>{this.onresult?.({resultIndex:0,results:[[{transcript:'今晚想吃蔬菜汤'}]]});this.onend?.()},30)}
   stop(){this.onend?.()}abort(){}
  }
  Object.defineProperty(window,'SpeechRecognition',{value:Recognition,configurable:true});
 });
 await page.goto('/');await register(page,'voice_'+Date.now());
 await page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'问问智膳'}).click();
 page.once('dialog',d=>d.accept());
 await page.getByRole('button',{name:'语音输入',exact:true}).click();
 await expect(page.getByLabel('输入问题',{exact:true})).toHaveValue('今晚想吃蔬菜汤');
 await expect(page.getByRole('button',{name:'复制消息',exact:true})).toHaveCount(0);
 await page.getByLabel('输入问题',{exact:true}).fill('今晚想吃面');
 await expect(page.getByLabel('输入问题',{exact:true})).toHaveValue('今晚想吃面');
});

test('background remains stable, changes between pages and preserves reading surfaces',async({page})=>{
 // Exercise cached A → B → A selection instead of depending on random luck.
 await page.addInitScript(()=>{Math.random=()=>0});
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto('/');
 const background=page.getByTestId('random-background');
 await expect(background).toHaveAttribute('data-state','ready');
 const welcome=await background.locator('img').last().getAttribute('data-background-id');
 await page.getByLabel('用户名',{exact:true}).fill('background_'+Date.now());
 await expect(background.locator('img').last()).toHaveAttribute('data-background-id',welcome!);
 await register(page,'bg_'+Date.now());
 await expect(background).toHaveAttribute('data-page','overview');
 await expect(background).toHaveAttribute('data-state','ready');
 const first=await background.locator('img').last().getAttribute('data-background-id');
 expect(first).not.toBe(welcome);
 await page.getByRole('button',{name:'AI饮食规划',exact:true}).click();
 await expect(background).toHaveAttribute('data-page','plan');
 await expect(background).toHaveAttribute('data-state','ready');
 expect(await background.locator('img').last().getAttribute('data-background-id')).not.toBe(first);
 const image=background.locator('img').last();
 expect(await image.evaluate((el:HTMLImageElement)=>el.complete&&el.naturalWidth>0)).toBe(true);
 const src=await image.getAttribute('src');
 const response=await page.request.get(src!);
 expect(response.headers()['cache-control']).toContain('immutable');
 await page.getByRole('button',{name:'AI识餐',exact:true}).click();
 await expect(background).toHaveAttribute('data-page','scan');
 await expect(background).toHaveAttribute('data-state','ready');
 expect(errors.filter(error=>/hydration/i.test(error))).toEqual([]);
});

test('background image failure preserves brand fallback and reduced motion',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.route('**/backgrounds/**',route=>route.abort());
 await page.goto('/');
 await expect(page.getByTestId('random-background')).toHaveAttribute('data-state','fallback');
 await expect(page.getByRole('button',{name:'创建账户，开启日常'})).toBeEnabled();
 await page.getByRole('button',{name:'切换深色模式'}).click();
 await expect(page.locator('.app')).toHaveClass(/dark/);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

for(const width of [375,768,1024,1440])test(`full viewport glass background and contrast at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:900});
 await page.goto('/');
 const background=page.getByTestId('random-background');
 await expect(background).toHaveAttribute('data-state','ready');
 for(const dark of [false,true]){
  if(dark)await page.getByRole('button',{name:'切换深色模式'}).click();
  const geometry=await background.evaluate(el=>{const r=el.getBoundingClientRect();const image=el.querySelector('img')!;const ir=image.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,imageWidth:ir.width,imageHeight:ir.height,imageX:ir.x,imageY:ir.y,mask:getComputedStyle(image).maskImage,fit:getComputedStyle(image).objectFit,position:getComputedStyle(el).position,pointer:getComputedStyle(el).pointerEvents}});
  expect(geometry).toMatchObject({x:0,y:0,width,height:900,imageWidth:width,imageHeight:900,imageX:0,imageY:0,mask:'none',fit:'cover',position:'fixed',pointer:'none'});
  await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
  expect((await background.boundingBox())?.y).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  const readings=await page.evaluate(()=>{
   const rgb=(s:string)=>s.match(/[\d.]+/g)!.map(Number);
   const luminance=(c:number[])=>c.slice(0,3).map(v=>{const s=v/255;return s<=.04045?s/12.92:((s+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
   const ratio=(a:number[],b:number[])=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
   const bg=rgb(getComputedStyle(document.querySelector('.card')!).backgroundColor),alpha=bg[3]??1;
   const inks=['label','small','.ghost'].map(selector=>rgb(getComputedStyle(document.querySelector('.welcome '+selector)!).color));
   const contrasts=inks.flatMap(ink=>[0,255].map(extreme=>ratio(ink,bg.slice(0,3).map(v=>v*alpha+extreme*(1-alpha)))));
   const style=getComputedStyle(document.querySelector('.welcome form button:not([type])')!);
   const border=rgb(getComputedStyle(document.querySelector('.welcome input')!).borderColor);
   const boundaries=[0,255].map(extreme=>ratio(border,bg.slice(0,3).map(v=>v*alpha+extreme*(1-alpha))));
   return {alpha,contrasts,boundaries,button:ratio(rgb(style.color),rgb(style.backgroundColor)),opacity:getComputedStyle(document.querySelector('.card')!).opacity};
  });
  expect(readings.alpha).toBeLessThan(1);
  expect(readings.opacity).toBe('1');
  for(const ratio of readings.contrasts)expect(ratio).toBeGreaterThanOrEqual(4.5);
  expect(readings.button).toBeGreaterThanOrEqual(4.5);
  for(const ratio of readings.boundaries)expect(ratio).toBeGreaterThanOrEqual(3);
  await page.getByLabel('用户名',{exact:true}).fill(dark?'dark_readable':'light_readable');
 }
});
