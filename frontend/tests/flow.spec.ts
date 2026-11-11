import {test,expect} from '@playwright/test';
test('mobile account → corrected meal → planner → advisor',async({page})=>{
 await page.goto('/');
 await page.getByLabel('邮箱',{exact:true}).fill(`e2e-${Date.now()}@example.com`);
 await page.getByLabel('密码 · 至少10个字符').fill('test-long-password');
 await page.getByRole('button',{name:'创建账户，开启日常'}).click();
 await page.getByRole('button',{name:'记录我的一餐'}).click();
 await page.getByLabel('克数',{exact:true}).fill('180');
 await page.getByRole('button',{name:'确认并保存记录'}).click();
 await expect(page.getByRole('status')).toContainText('已保存');
 await page.getByRole('button',{name:'下一餐灵感',exact:true}).click();
 await page.getByRole('button',{name:'生成下一餐建议'}).click();
 await expect(page.getByRole('heading',{name:'青蔬鸡肉糙米碗'})).toBeVisible();
 await page.getByRole('button',{name:'打开AI顾问'}).click();
 await page.getByLabel('顾问问题').fill('下一餐蔬菜怎么选');
 await page.getByRole('button',{name:'发送问题'}).click();
 await expect(page.getByText('模式：rules')).toBeVisible();
});
