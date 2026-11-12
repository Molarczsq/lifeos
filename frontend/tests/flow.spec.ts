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
  const options=page.locator('label.consent input[type="checkbox"]');
  await expect(options).toHaveCount(3);
  for (let i=0;i<3;i++) await expect(options.nth(i)).toBeChecked();
  for (let i=0;i<3;i++) {
    const saved=page.waitForResponse(r=>r.url().endsWith('/api/v1/consents') && r.request().method()==='PUT');
    await options.nth(i).uncheck();
    expect((await saved).status()).toBe(200);
  }
  await page.reload();
  await page.getByRole('button', {name:'数据与隐私',exact:true}).click();
  for (let i=0;i<3;i++) await expect(options.nth(i)).not.toBeChecked();
});
