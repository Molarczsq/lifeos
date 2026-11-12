import {test, expect, Page} from '@playwright/test';

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
  await expect(page.getByRole('button', {name:'记录一餐',exact:true})).toHaveCount(0);
  await expect(page.getByLabel('邮箱', {exact:true})).toHaveCount(0);
  await register(page, username);
  const session = (await page.context().cookies()).find(c => c.name === 'lifeos_session');
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe('Strict');
  await page.getByRole('button', {name:'记录我的一餐'}).click();
  await page.getByLabel('克数', {exact:true}).fill('180');
  await page.getByRole('button', {name:'确认并保存记录'}).click();
  await expect(page.getByRole('status').filter({hasText:'已保存到你的饮食记录'})).toBeVisible();
  await page.getByRole('button', {name:'下一餐灵感',exact:true}).click();
  await page.getByRole('button', {name:'生成下一餐建议'}).click();
  await expect(page.getByRole('heading', {name:'青蔬鸡肉糙米碗'})).toBeVisible();
  await page.getByRole('button', {name:'打开AI顾问'}).click();
  await page.getByLabel('顾问问题').fill('下一餐蔬菜怎么选');
  await page.getByRole('button', {name:'发送问题'}).click();
  await expect(page.getByText('模式：rules')).toBeVisible();
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
  await page.getByRole('button',{name:'食物目录',exact:true}).click();
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
  await page.getByRole('button',{name:'食物目录',exact:true}).click();
  await expect(page.locator('.catalog-tile')).toHaveCount(6);
  await expect(page.getByLabel('食物名称',{exact:true})).toHaveCount(0);
  const image=page.locator('.catalog-cover img').first();
  await expect(image).toBeVisible();
  expect(await image.evaluate((node:HTMLImageElement)=>node.complete&&node.naturalWidth>0)).toBe(true);
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
  await page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'记录一餐'}).click();
  await expect(page.getByRole('heading',{name:'拍一张，认识这一餐'})).toBeVisible();
 });
}
