// 读取软著登记各状态 tab 的件数 + 消息中心通知（只读）
// 前置：已登录（见 solve_yidun_slider.mjs），Chrome 运行在 9222
import { createRequire } from 'module';
// playwright-core 装在 D:/tmp_cc/node_modules，用 createRequire 定向解析
const _req = createRequire('file:///D:/tmp_cc/');
const { chromium } = _req('playwright-core');
import fs from 'fs';
process.env.NO_PROXY = '127.0.0.1,localhost';
const sleep = ms => new Promise(r => setTimeout(r, ms));

let CFG = { centerUrl: 'https://register.ccopyright.com.cn/account.html?current=soft_register', msgUrl: 'https://register.ccopyright.com.cn/msgcenter.html', flowNumber: '', downloadDir: 'D:\\图文内容\\软著材料' };
try { CFG = { ...CFG, ...JSON.parse(fs.readFileSync('D:/tmp_cc/_cc_login.json', 'utf8')) }; } catch (e) { }

const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const ctx = browser.contexts()[0];
const page = ctx.pages().find(p => p.url().includes('ccopyright')) || ctx.pages()[0];
await page.bringToFront();

await page.goto(CFG.centerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => { });
if (CFG.flowNumber) {
  await page.waitForFunction(f => document.body.innerText.includes(f), CFG.flowNumber, { timeout: 40000 }).catch(() => { });
}
await sleep(2500);

const loggedIn = await page.evaluate(() => (document.body.innerText || '').includes('退出登录'));
console.log('LOGGED_IN =', loggedIn);
if (!loggedIn) { console.log('NOT_LOGGED_IN: 请先跑 solve_yidun_slider.mjs'); process.exit(2); }

const tabs = ['全部', '草稿箱', '待提交', '待受理', '待审查', '待补正', '待发放', '已发放'];
console.log('\n--- 状态 tab 计数 ---');
for (const tb of tabs) {
  try { await page.getByText(tb, { exact: true }).first().click({ timeout: 4000 }); } catch (e) { console.log(tb, 'click fail'); continue; }
  await sleep(3200);
  const n = await page.evaluate(() => (document.body.innerText.match(/流水号[:：]/g) || []).length);
  console.log(`${tb} = ${n}`);
}
await page.getByText('全部', { exact: true }).first().click({ timeout: 4000 }).catch(() => { });
await sleep(3000);

console.log('\n--- 列表原文 ---');
const t = await page.evaluate(() => document.body.innerText || '');
const s = t.indexOf('软件登记');
console.log(t.slice(s, s + 900).replace(/\n{2,}/g, '\n'));

if (CFG.downloadDir) {
  try { fs.mkdirSync(CFG.downloadDir, { recursive: true }); } catch (e) { }
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const out = `${CFG.downloadDir}\\状态_${stamp}.png`;
  await page.screenshot({ path: out, timeout: 20000 }).catch(() => { });
  console.log('\n截图 ->', out);
}

console.log('\n--- 消息中心 ---');
await page.goto(CFG.msgUrl, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => { });
await sleep(6000);
const m = await page.evaluate(() => document.body.innerText || '');
const mi = m.indexOf('消息中心');
console.log(m.slice(mi, mi + 900).replace(/\n{2,}/g, '\n'));
process.exit(0);
