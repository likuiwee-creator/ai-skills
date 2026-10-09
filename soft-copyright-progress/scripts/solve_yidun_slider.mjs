// 易盾滑块求解 v5：原生图定位缺口 + 闭环控制（拖动中实时读取拼图偏移并逼近目标）
import { createRequire } from 'module';
// playwright-core 装在 D:/tmp_cc/node_modules，用 createRequire 定向解析
const _req = createRequire('file:///D:/tmp_cc/');
const { chromium } = _req('playwright-core');
import { execFileSync } from 'child_process';
import fs from 'fs';
process.env.NO_PROXY = '127.0.0.1,localhost';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 账号密码：优先读 D:/tmp_cc/_cc_login.json，其次环境变量，最后内置默认
let USER = 'lkw12345', PASS = 'Q6rA8HpYiPtyvjw';
try {
  const c = JSON.parse(fs.readFileSync('D:/tmp_cc/_cc_login.json', 'utf8'));
  if (c.user) USER = c.user;
  if (c.pass) PASS = c.pass;
} catch (e) { }
if (process.env.CC_USER) USER = process.env.CC_USER;
if (process.env.CC_PASS) PASS = process.env.CC_PASS;

const DET = new URL('./yidun_detect_gap.py', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');

const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const ctx = browser.contexts()[0];
const page = ctx.pages().find(p => p.url().includes('ccopyright')) || ctx.pages()[0];
await page.bringToFront();

async function detect() {
  const urls = await page.evaluate(() => ({
    bg: (document.querySelector('img.yidun_bg-img') || {}).src,
    jig: (document.querySelector('img.yidun_jigsaw') || {}).src
  }));
  if (!urls.bg || !urls.jig) return null;
  for (const [k, u] of Object.entries(urls)) {
    const r = await fetch(u);
    fs.writeFileSync(`D:/tmp_cc/_raw_${k}.png`, Buffer.from(await r.arrayBuffer()));
  }
  const out = execFileSync('D:/Python/python.exe', [DET], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  const g = out.match(/GAPX=(\d+)/), a = out.match(/ALPHA_X0=(\d+)/);
  if (!g) return null;
  return { gapX: +g[1], alphaX0: a ? +a[1] : 3 };
}

async function offsets() {
  return page.evaluate(() => {
    const b = document.querySelector('img.yidun_bg-img').getBoundingClientRect();
    const j = document.querySelector('img.yidun_jigsaw').getBoundingClientRect();
    const s = document.querySelector('.yidun_slider').getBoundingClientRect();
    return { pieceX: +(j.x - b.x).toFixed(2), pieceW: +j.width.toFixed(2), slX: +(s.x - b.x).toFixed(2) };
  });
}

async function unlock() {
  const t = await page.evaluate(() => document.body.innerText || '');
  if (t.includes('失败过多')) {
    try { await page.getByText('点此重试').first().click({ timeout: 4000 }); } catch (e) { }
    await sleep(3500);
  }
}

async function summonCaptcha() {
  if (await page.$('.yidun_slider')) return true;
  console.log('[login] summoning captcha...');
  await page.goto('https://register.ccopyright.com.cn/login.html', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => { });
  await sleep(4000);
  try { await page.getByText('机构', { exact: true }).first().click(); } catch (e) { }
  await sleep(1200);
  const inputs = await page.$$eval('input', els => els.map((e, i) => ({ i, type: e.type, vis: !!(e.offsetWidth || e.offsetHeight) })));
  const vis = inputs.filter(x => x.vis);
  const acc = vis.find(x => x.type !== 'password' && x.type !== 'checkbox' && x.type !== 'hidden');
  const pwd = vis.find(x => x.type === 'password');
  if (acc) await page.locator('input').nth(acc.i).fill(USER);
  if (pwd) await page.locator('input').nth(pwd.i).fill(PASS);
  try { await page.getByText('立即登录', { exact: true }).first().click(); } catch (e) { }
  await sleep(5000);
  await unlock();
  return !!(await page.$('.yidun_slider'));
}

await summonCaptcha();

for (let attempt = 1; attempt <= 5; attempt++) {
  console.log(`\n=== attempt ${attempt} ===`);
  if (!(await page.$('.yidun_slider'))) { console.log('RESULT: NO_CAPTCHA'); process.exit(0); }
  await unlock();

  const d = await detect();
  if (!d) { console.log('  detect failed'); break; }
  const o0 = await offsets();
  const alphaCss = d.alphaX0 * (o0.pieceW / 60);
  const target = d.gapX - alphaCss;
  console.log(`  gapX=${d.gapX} target pieceX=${target.toFixed(2)}`);

  const slider = await page.$('.yidun_slider');
  const box = await slider.boundingBox();
  const sx0 = box.x + box.width / 2, sy = box.y + box.height / 2;

  await page.mouse.move(sx0, sy); await sleep(240);
  await page.mouse.down(); await sleep(170);

  let cur = 0;
  let last = await offsets();
  const samples = [[0, last.pieceX]];
  const MAXIT = 16;

  for (let it = 0; it < MAXIT; it++) {
    const err = target - last.pieceX;
    if (Math.abs(err) <= 0.7) { console.log(`  converged it=${it} err=${err.toFixed(2)}`); break; }
    let slope = 1;
    if (samples.length >= 2) {
      const [a1, b1] = samples[samples.length - 2];
      const [a2, b2] = samples[samples.length - 1];
      if (Math.abs(a2 - a1) > 0.5) slope = (b2 - b1) / (a2 - a1);
      if (!isFinite(slope) || Math.abs(slope) < 0.25) slope = 1;
    }
    let dx = err / slope;
    dx = Math.max(-70, Math.min(70, dx));
    if (Math.abs(dx) < 1.2) dx = Math.sign(err) * 1.2;
    const from = cur, to = cur + dx;
    const sub = Math.max(3, Math.min(10, Math.round(Math.abs(dx) / 7)));
    for (let i = 1; i <= sub; i++) {
      const t = i / sub;
      const e = 1 - Math.pow(1 - t, 1.8);
      await page.mouse.move(sx0 + from + (to - from) * e + (Math.random() - 0.5) * 0.9,
        sy + (Math.random() - 0.5) * 1.8, { steps: 2 });
      await sleep(12 + Math.random() * 26);
    }
    cur = to;
    await sleep(130);
    last = await offsets();
    samples.push([cur, last.pieceX]);
    console.log(`  it=${it} slider=${cur.toFixed(1)} pieceX=${last.pieceX} err=${(target - last.pieceX).toFixed(2)}`);
  }

  await sleep(120);
  await page.mouse.move(sx0 + cur + 1.2, sy, { steps: 2 }); await sleep(80);
  await page.mouse.move(sx0 + cur, sy, { steps: 2 }); await sleep(240);
  await page.mouse.up();
  await sleep(5000);

  if (!(await page.$('.yidun_slider'))) {
    console.log('RESULT: SOLVED');
    await page.screenshot({ path: 'D:/tmp_cc/_cap_ok.png' });
    process.exit(0);
  }
  console.log('  failed');
  await sleep(2000);
}
console.log('RESULT: FAILED_ALL');
await page.screenshot({ path: 'D:/tmp_cc/_cap_fail.png', fullPage: true });
process.exit(0);
