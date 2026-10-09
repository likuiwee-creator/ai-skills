---
name: chrome-cdp-drive
description: 在本机（Windows）用「系统 Chrome + 远程调试端口 + playwright-core 连 CDP」驱动浏览器做网页自动化，替代已损坏的 agent-browser。当需要打开网页、填表、点击、截取页面证据、或登录/注册类多步网页流程自动化时使用；尤其适用于 agent-browser 的 open 命令挂死、需要绕过持续动画导致截图超时的场景。
agent_created: true
---

# 用 CDP + playwright-core 驱动本机 Chrome

## 何时用
- `agent-browser open` 挂死 / 超时（本机 agent-browser 自带 Chromium 启动层已损坏，实测连 `about:blank` 都卡 70s+）
- 需要真实 GUI 浏览器（用户在屏幕前能看到并可以亲自接管某一步，如验证码拖拽）
- 需要避开持续 CSS 动画导致的 `page.screenshot` 超时

## 一、启动 Chrome（关键：必须后台 + 关沙箱）

```
"C:/Program Files/Google/Chrome/Application/chrome.exe" \
  --remote-debugging-port=9223 \
  --user-data-dir="D:\tmp_mp\chrome_profile" \
  --no-first-run --no-default-browser-check --no-proxy-server about:blank
```
- Bash 工具参数：`run_in_background: true` **且** `dangerouslyDisableSandbox: true`
- **不关沙箱的后果**：Chrome 启动 4 秒后被连同子进程一起回收，stderr 已打印 `DevTools listening on ws://...` 但端口立刻 ECONNREFUSED（排查时极易误判为"启动成功"）。
- 用独立 `--user-data-dir`，避免与用户日常 Chrome / 其他自动化任务（如软著用 9222 + `D:\tmp_cc\chrome_profile`）互相抢锁。

## 二、验证端口
```bash
# curl 在本机 Git Bash 下可能返回空，用 node 更稳：
NO_PROXY=127.0.0.1,localhost <node> -e "
const http=require('http');
http.get({host:'127.0.0.1',port:9223,path:'/json/version'},r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>console.log('OK',d.slice(0,80)))}).on('error',e=>console.log('DEAD',e.message));"
```
所有 node 调用都必须带 `NO_PROXY=127.0.0.1,localhost`（公司代理环境）。

## 三、连接（playwright-core 已装在 D:/tmp_cc）
```js
import { createRequire } from 'module';
const require = createRequire('file:///D:/tmp_cc/');
const { chromium } = require('playwright-core');
const browser = await chromium.connectOverCDP('http://127.0.0.1:9223');
const ctx = browser.contexts()[0];
const page = ctx.pages()[0];          // 或按 URL 找：ctx.pages().find(p=>p.url().includes('xxx'))
```
运行：`NO_PROXY=127.0.0.1,localhost <node> script.mjs`

## 四、必须避开的坑

| 坑 | 现象 | 解法 |
|---|---|---|
| `ctx.newCDPSession(page)` | **随机挂死**（同一写法有时成功有时永久卡住） | 外部套 `timeout 100`，别把它放在关键唯一路径上 |
| `page.screenshot()` | 页面有持续动画（验证码滑块）时 **永远超时** | 改用 CDP：`cdp.send('Page.captureScreenshot',{format:'png',clip:{x,y,width,height,scale:1}})` 后 base64 落盘 |
| `page.screenshot({animations:'disabled'})` | 同样常失败 | 同上 |
| `page.frames()` 里跨域 iframe URL 为空 | 按 `f.url().includes('captcha.gtimg.com')` **找不到 frame**（同一 frame 有时又能找到，不稳定） | **遍历所有 frame，用内部标记元素认**：`for (const f of page.frames()) { const ok = await f.evaluate(()=>!!document.querySelector('.tc-captcha')).catch(()=>false) }` |
| 连续点击已被遮罩层挡住的元素 | `locator.click` 超时，日志显示 `xxx intercepts pointer events` | 说明有弹层（如 `#t_mask`）没关；先处理弹层 |
| bash heredoc 写 JS | `Bad substitution` | 一律用 Write 工具落盘脚本，再执行 |
| **多标签页时连错页** | `ctx.pages()[0]` 是用户自己开的页（如 QQ 邮箱），不是目标任务页 | `const page = ctx.pages().find(p => /mp\.weixin\.qq\.com/.test(p.url())) ?? ctx.pages()[0]`；先跑一个脚本把所有页 `url + title` 列出来确认 |
| **页面有 `scroll-behavior: smooth`** | `scrollIntoView()` 后立刻 `getBoundingClientRect()` 拿到的是**滚动途中**的坐标，点击会打偏（点中相邻按钮） | 开头统一 `await page.addStyleTag({content:'html,body{scroll-behavior:auto !important}'})`；或直接用 `locator.click()` 让 playwright 自己等元素稳定 |
| **`locator.click()` 对自定义下拉 / 带持续动画的控件完全无效** | 30s 超时；`click({force:true})`、`el.click()`、`dispatchEvent(new MouseEvent('click'))`、`mouse.down()+up()` **全部不生效**（控件显示值不变） | **改用 CDP 底层输入事件**（见第五节），一次成功 |
| **mp.weixin.qq.com 后台 token 轮换后旧链接全挂** | 隔天回连长驻浏览器，侧边栏 href 还带旧 token；点「版本管理」或冷 goto 内页都渲染「登录超时，请重新登录」（页面壳能加载，数据 API 其实 ret:0，是 `caas/qrcheck` 安全校验失败顶掉页面） | **新开标签 goto `https://mp.weixin.qq.com/`**，cookie 有效会 302 到 home/guide 并带**新 token**，从最终 URL 正则取 `token=(\d+)`，之后用新 token 访问任何内页 |

## 五、点击无效时的终极手段：CDP Input 事件

微信公众平台 `weui-desktop` 的级联下拉（`dropdowncascade`）等控件带持续动画 / 重渲染，playwright 的 actionability 检查过不去，DOM 派发的事件也进不了其内部状态机。用 CDP 发**真实输入事件**可绕过：

```js
const cdp = await ctx.newCDPSession(page);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const click = async (x, y) => {
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved',    x, y, buttons: 0 });
  await sleep(60);
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed',  x, y, button: 'left', buttons: 1, clickCount: 1 });
  await sleep(90);
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 });
};
// x/y 取元素 getBoundingClientRect() 中心的**视口坐标**
const r = await page.evaluate(() => {
  const e = [...document.querySelectorAll('.目标选择器')].find(x => (x.innerText || '').trim() === '目标文本');
  const b = e.getBoundingClientRect();
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
});
await click(r.x, r.y);
```

**配套捷径 —— 直接从 Vue 组件读状态与候选数据**：这类控件多是 Vue（DOM 元素上有 `el.__vue__`），可读到组件的 `$data`（`pickedValue` / `innerValue` / `checkedPath` / `visible`）与 `options`：

```js
let comp = null, p = document.querySelector('.weui-desktop-form__dropdowncascade__dt');
for (let i = 0; i < 10 && p; i++) { if (p.__vue__) { comp = p.__vue__; break; } p = p.parentElement; }
// comp.options 里常带每个选项的 label/value/scope/qualifications（官方资质要求原文）
// comp.$data.pickedValue 比 DOM 文本更准（DOM innerText 可能滞后）
```

- 页面若有**多个同类控件**（如「机构类型」和「经营行业」都是 `.weui-desktop-form__dropdowncascade__dt`），务必用 `nth(i)` / `querySelectorAll()[i]` **明确取第几个**，否则会读到错的组件、得出错误结论。
- 级联下拉的选择节奏：点一级项（class 含 `module-has-options`，只切二级面板）→ 再点二级项（才真正写值）。

## 五之二、weui-desktop 表单排查套路（微信公众平台）

**症状：某个 checkbox 一直 `disabled`，怎么点都不动。**

不要怀疑选择器，**先查有没有必填项没填**。weui 的表单控件会被整页校验统一 enable/disable，缺一个必填红字就全锁。

排查顺序：
1. **dump 所有控件实际值**（比看截图准）：
   ```js
   [...document.querySelectorAll('input,textarea,select')]
     .filter(e => !['file','button','submit'].includes(e.type))
     .map(e => `[${e.type}] name=${e.name} value=${e.value} disabled=${e.disabled}`)
   ```
2. **抓红字校验提示**：提示文字是**行内红字**，用颜色筛最快：
   ```js
   [...document.querySelectorAll('*')]
     .filter(e => e.children.length === 0
       && /请输入|请完整|请上传/.test(e.innerText || '')
       && getComputedStyle(e).color.replace(/\s/g,'').includes('rgb(250'))  // 红
     ).map(e => e.innerText.trim())
   ```
3. **级联下拉的值不在 DOM 里**（不进 form 字段），要单独验：数每个
   `.weui-desktop-form__dropdowncascade` 内的 `li.checked`：
   ```js
   [...document.querySelectorAll('.weui-desktop-form__dropdowncascade')].map(c => ({
     label: c.closest('.weui-desktop-form__control-group')
              ?.querySelector('.weui-desktop-form__label')?.innerText.trim(),
     dt: [...c.querySelectorAll('.weui-desktop-form__dropdowncascade__dt__value_ele')]
           .map(e => e.innerText.trim()).filter(Boolean),
     checked: [...c.querySelectorAll('li.checked')].map(li => li.innerText.trim().split('\n')[0]),
   }))
   ```
4. **file input 认法**：别按顺序猜。向上遍历 parentElement 找到所属表单块，**按块内文本**（如「工商营业执照」）认：
   ```js
   [...document.querySelectorAll('input[type=file]')].map((i, idx) => {
     let n = i, label = '';
     for (let k = 0; k < 8 && n; k++) { n = n.parentElement; if (!n) break;
       const t = (n.innerText||'').replace(/\s+/g,' ');
       if (/工商营业执照|其他证明材料/.test(t) && t.length < 300) { label = t.slice(0,90); break; } }
     return { idx, multiple: i.multiple, label };
   })
   ```
   拿到 idx 后 `(await page.$$('input[type=file]'))[idx].setInputFiles(path)`。

**切换 radio 会重排表单**：如「主体验证方式」从「对公账户打款」切到「法人扫脸」，**开户名称/开户银行/账号三栏直接消失**，改为「法定代表人验证」二维码，`verify_code` 保留但「获取验证码」按钮复位。→ 切换前先把已填值 dump 出来存档，别指望切换后还在。

**二维码交给用户扫**：把二维码元素单独截图交付，`element.screenshot()` 常失败，用整页 `clip` 更稳：
```js
const b = await page.evaluate(() => { const i = [...document.images].find(x=>/qrcode/.test(x.src));
  i.scrollIntoView({block:'center'}); const r = i.getBoundingClientRect();
  return {x:Math.round(r.x), y:Math.round(r.y), width:Math.round(r.width), height:Math.round(r.height)}; });
await page.screenshot({ path: 'qr.png', clip: b });   // clip 用**视口**坐标
```
扫完回读状态：QR 块内文本会变成「已验证成功」/「已确认成功」。

## 五之三、长驻调试端口：让登录态跨脚本复用（强烈推荐）

默认「一个脚本干完一件事」的问题：**微信后台会话很短**（实测关掉浏览器即失效，重新连上就 `登录超时，请重新登录`），每次都要重新扫码。解法是让 Chrome **独立长驻**，脚本只负责"连上去做一步就走"：

```bash
# 后台启动（run_in_background + dangerouslyDisableSandbox）
"C:/Program Files/Google/Chrome/Application/chrome.exe" \
  --user-data-dir="<项目>/mp_profile" --remote-debugging-port=9224 \
  --no-first-run --no-default-browser-check --window-size=1440,900 "<目标URL>"
```
```js
const browser = await chromium.connectOverCDP('http://127.0.0.1:9224');
// ...操作...
await browser.close();   // ★ connectOverCDP 下这只断连，不会关掉 Chrome
```
- **验证过**：连续十几个脚本反复 `connectOverCDP` → `browser.close()`，Chrome 一直活着，扫码登录态保持。
- 起新脚本时**不要 `page.goto` 重载表单页**去做"干净状态"——重载会丢掉前端 JS 的内存态（如已上传文件的 `fid`、裁剪框选中区），且白白触发一次表单联动检查。
- 想重来就 `goto` 目标页**一次**，然后一口气把流程走完。

## 五之四、表单「点了没反应」的三步定位法

微信后台的提交按钮**校验失败只弹一个瞬时 toast**（几百毫秒消失），截图/延迟 dump 都抓不到，表现为"点了完全没反应"。按下面顺序查：

**1）找真正的提交按钮 id**（不要用 `text=提交` 的任意元素 —— 可能匹配到外层 DIV）
```js
[...document.querySelectorAll('a,button')].filter(e => (e.innerText||'').trim()==='提交')
  .map(e => ({ tag: e.tagName, id: e.id, cls: e.className }))
```
或直接抓页面 JS 里的绑定：`grep -o '\$("#[a-z_]*submit")' xxx.js`

**2）抓请求流**，看提交链到底发出去没有
```js
page.on('request', r => { const u=r.url();
  if (/cgi-bin|initprofile|wxopen/i.test(u) && !/\.(js|css|png|jpe?g|gif)/i.test(u))
    console.log(r.method(), u.replace(/https:\/\/mp\.weixin\.qq\.com/,'')); });
```
多字段表单的正常提交是**连续多个 POST**（例：`action=nickname` → `headimg?action=init_modify` → `action=intro`），最后 `location.href` 跳到首页 = 成功。**只有 1 个请求就断了 = 卡在校验**。

**3）抓瞬时 toast**
```js
[...document.querySelectorAll('[class*=toast],[class*=err],[class*=tips]')]
  .map(e=>(e.innerText||'').replace(/\s+/g,' ').trim()).filter(t=>t&&t.length<120)
```

### ⚠️ 头号陷阱：表单联动检查会**重建 DOM**，静默清空已上传/已填内容

实例：小程序「填写小程序信息」页，点提交前会先调 `check_nickname`；该接口**每次触发都会重渲上传区容器**，把已上传的营业执照 DOM 和隐藏字段一起抹掉。结果：UI 上还显示着文件名，`#organizeFile_hidden` 已是空 → 提交校验失败 → 静默中断。

**排查特征**：UI 显示"已上传/已填"，但**隐藏字段为空**
```js
[...document.querySelectorAll('input[type=hidden]')].map(e=>({id:e.id, v:(e.value||'').slice(0,60)}))
```
→ **`input[type=hidden]` 才是真实提交值；UI 上显示的文件名不算数。**

**正确顺序**：先填触发联动的字段（名称）→ 等联动检查跑完、区块渲染稳定 → **再上传文件/填后续字段** → **全程不再碰触发字段**（不要点它、不要让它 blur，blur 也会重跑检查）。

补充：字段的字数上限**可能是中文按 2 字符计**（介绍 60 字 → 页面显示 `117/120`），以页面计数器为准，不要按 `value.length` 判断。

## 五之五、页面内 fetch 被 CORS 拦时：用 curl 逆向 JS

想读页面自己的 JS 逻辑（判断校验条件），在页面里 `fetch('https://res.wx.qq.com/...')` 会被 CORS 拦掉（返回 19 字节空壳）。改**在终端 curl**（走公司代理 `http_proxy=127.0.0.1:58814` 已配好，直接可用）：
```bash
curl -s -o name.js "https://res.wx.qq.com/wxopenres/zh_CN/htmledition/js/setting/name5dceab.js"
```
- 页面 JS 按模块拆分且**文件名带 hash**：先从 `[...document.querySelectorAll('script[src]')].map(s=>s.src)` 拿全量 URL，再挑名字对得上的（`setting/name*`、`setting/app_info*`）下载。
- 组合加载 URL 形如 `/c/=/a.js,/b.js`，直接访问单个模块路径通常也能拿到。
- 顺带：**判据信息常藏在 `window.cgiData`**（各字段 `status`：0=已保存/1=待处理），比读 DOM 文本可靠。

## 六、把窗口调到前台（让用户接管某一步）
纯 HTTP，无需 WS：
```js
const list = JSON.parse(await get('/json/list'));
const pg = list.find(t => t.type==='page' && t.url.includes('目标域名'));
await get('/json/activate/' + pg.id);
```

## 七、设计原则
- **一个脚本干完一件事**：连接 → 操作 → 取证 → `process.exit(0)`。不要把"读状态"和"做动作"拆成多次运行（Chrome 可能中途退出，且 frame 查找不稳定）。
- 每个脚本结尾显式 `process.exit(0)`，否则 Playwright 保持连接不退出，看起来像"卡死"。
- 需要用户亲自完成的环节（验证码拖拽、扫脸、扫码、支付）**主动交给用户**：把窗口 activate 到前台 → 明确说出要点哪里 → 等用户回话。不要为此投入自动化成本。
