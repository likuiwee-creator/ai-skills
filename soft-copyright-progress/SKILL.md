---
name: soft-copyright-progress
description: 中国版权保护中心（register.ccopyright.com.cn）软著登记全流程自动化：查申请进度、读补正原因、下载证书，以及在用户明确要求时上传签章页并提交。当用户问"软著进度/受理没有/有没有补正/证书下来没"、要"上传签章页/提交申请"，或需要自动登录该平台（网易易盾滑块验证码）时使用。含易盾滑块自动求解方案。
agent_created: true
---

# 软著登记进度查询（中国版权保护中心）

## 适用场景
- 查某流水号软著申请的当前状态（待上传签章页 / 待提交 / 待受理 / 待审查 / 待补正 / 待发放 / 已发放）
- 抓取补正/驳回原因，判断要不要补材料
- 下载受理通知书 / 电子证书（若有）

## 铁律
**默认只读：不提交、不修改申请。** 不要点「提交」「确认填报」「删除申请」。
唯一的例外：用户**明确要求**上传签章页/完成提交时，才可执行下面「上传签章页」一节。

## 上传签章页并提交（写操作，仅用户明确授权时执行）

1. 入口**直接导航**，别去点页头：
   ```
   https://register.ccopyright.com.cn/account.html?current=soft_register
   ```
   ⚠️ 页头「用户中心」按钮在 CDP 自动化下点击**无任何反应**（实现是 `toCenter(){window.open("./account.html","userCenter")}`，
   Playwright 的 click / hover / getByText 全都无效）。直接 goto 该 URL，不要在它上面浪费轮次。
2. 列表行状态为 `待上传签章页` 时，行内有 `打印签章页 / 上传签章页 / 删除申请` 三个按钮。
3. 上传（按钮会触发隐藏 input，用 filechooser 事件接）：
   ```js
   const [chooser] = await Promise.all([
     page.waitForEvent('filechooser', { timeout: 12000 }),
     page.locator('button:visible', { hasText: '上传签章页' }).first().click()
   ]);
   await chooser.setFiles('D:\\图文内容\\软著材料\\签章页_已签署_<流水号>.pdf');
   ```
   **只接受 PDF。** 传 JPG 时接口不报错、页面也不变，状态仍是「待上传签章页」（会误以为失败）；换 PDF 立刻成功。
4. 成功后行内变为：文件名 + `删除签章页` + `确认提交`。
5. 点 `确认提交` → 弹出 `请确认是否提交？确定/取消` → 点 `确定`。
6. 验证链路（三个接口都要看到 SUCCESS）：
   - `oss.ccopyright.com.cn/oss/upload` → `{"returnCode":"SUCCESS","data":{"filePath":"temp/...pdf","pageNum":"1"}}`
   - `.../userCenter/saveSealMaterial/{userId}/{流水号}` → `{"msg":"Operate success"}`
   - `.../userCenter/submitSealMaterial/{userId}/{流水号}` → `{"msg":"Operate success"}`
   列表状态随即变为 **待受理**（并显示提交日期）。

## 环境准备

1. 启动带调试端口的 Chrome（**必须用 run_in_background 常驻**，用 `&` 会随 shell 退出被杀）：
```bash
"C:/Program Files/Google/Chrome/Application/chrome.exe" --remote-debugging-port=9222 \
  --user-data-dir="D:\tmp_cc\chrome_profile" --no-first-run --no-default-browser-check --no-proxy-server
```
2. 确认端口：`curl -s -m 8 --noproxy '*' http://127.0.0.1:9222/json/version`
3. 所有 node 调用都要带 `NO_PROXY=127.0.0.1,localhost`。

## 关键步骤

### 1. 登录（易盾滑块，必过）
```bash
NO_PROXY=127.0.0.1,localhost <managed-node> scripts/solve_yidun_slider.mjs
```
- 会自动：打开 login.html → 点「机构」tab → 填账号密码 → 点「立即登录」→ 求解易盾滑块 → 重试。
- 账号密码取自 `D:/tmp_cc/_cc_login.json`（`{"user":"...","pass":"..."}`），不存在则用脚本内默认值。
- 成功标志：页头由「登录 注册」变成「用户中心」。

### 2. 读状态
登录后「用户中心」是**新标签页** `account.html?current=soft_register`（不要再用 `registration.html#/personalCenter`、`#/myPage`，这两个路由是错的，会被重定向回 `#/index`）。
等页面出现流水号文本再截图/取数：
```js
await page.waitForFunction(()=>document.body.innerText.includes('<流水号>'), {timeout:40000});
```
逐个点 tab 数「流水号：」出现次数即可判断各状态是否有件：全部/草稿箱/待提交/待受理/待审查/待补正/待发放/已发放。
消息中心 = `msgcenter.html`（实名认证结果等通知在这里）。

### 3. 有补正/证书时落盘
下载目录：`D:\图文内容\软著材料\`

## 易盾滑块求解原理（踩过的坑，务必照做）

**坑 1：不要用「截图 + 明暗阈值」找缺口。** 截图的 devicePixelRatio 缩放、缺口浮层明暗随图变化，都会让定位错得离谱。
**正解**：直接从 `img.yidun_bg-img` / `img.yidun_jigsaw` 的 `src` **下载原始图片**（320x160 的 bg，60x158 RGBA 的拼图，alpha 就是形状），1:1 无缩放。
用 alpha 形状当模板在 bg 上滑窗，按 `轮廓梯度均值 - 0.45*内部梯度均值` 取最大 → 稳定命中缺口。
脚本：`scripts/yidun_detect_gap.py`，输出 `GAPX / ALPHA_X0 / DRAG_CSS`，并生成 `_match_check.png` 可目视校验。

**坑 2（真凶）：拼图块位移 ≠ 滑块位移。**
实测：滑块移 70px → 拼图只移 58.5px；滑块 140 → 拼图 128.5。
即**近似 1:1 斜率但带约 -11px 固定偏置**，起点还有死区。任何"按比例算一次就拖到位"都会打偏。
**正解：拖动中闭环控制。** mousedown 后分多次小幅移动，每次读 `jigsaw.x - bg.x`，
用最近两次采样估局部斜率，算下一步位移，迭代收敛到 `|误差| ≤ 0.7px` 再松手。这套对任何单调映射都成立。

**坑 3：失败太多会被锁**，页面出现「失败过多，点此重试」，脚本里已自动点击重试。
失败后图片往往**不刷新**（同样两张图会重复失败），必要时点 `.yidun_refresh`。

## 依赖
- Node + playwright-core（连 CDP，无需装浏览器）。位于 `D:\tmp_cc\node_modules`，脚本内用 `createRequire('file:///D:/tmp_cc/')` 定向解析；若该目录变动需同步改。
- Python3 + numpy + scipy + Pillow（`D:/Python/python.exe` 可直接用）

## 快速复跑（最短路径）
```bash
# 1) 启动 Chrome（run_in_background）
# 2) 登录 + 过滑块
NO_PROXY=127.0.0.1,localhost <node> "C:/Users/Administrator/.workbuddy/skills/soft-copyright-progress/scripts/solve_yidun_slider.mjs"
# 3) 读状态 + 截图落盘
NO_PROXY=127.0.0.1,localhost <node> "C:/Users/Administrator/.workbuddy/skills/soft-copyright-progress/scripts/check_status.mjs"
```
`check_status.mjs` 会打印 LOGGED_IN、各 tab 计数、列表原文、消息中心通知，并把截图存到 `D:\图文内容\软著材料\状态_YYYYMMDD.png`。

## 已知不可靠点（2026-09-15 验证）
- **tab 计数不可信**：`check_status.mjs` 逐个点 tab 数「流水号：」会出现 全部=1/草稿箱=1/待提交=1/待受理=1/待补正=1 这类互相矛盾的结果（SPA 切 tab 时列表未真正刷新）。
  **判定状态只认两处**：① 用户中心列表行的「状态」列文案；② 详情页「申请状态：…」。不要用 tab 计数推断有无补正/证书。
- **Chrome 后台进程会中途退出**，导致正在跑的脚本报 `Target page, context or browser has been closed`（常发生在列表取数之后）。
  解法：跑之前先 `curl http://127.0.0.1:9222/json/version`，DOWN 就重新 run_in_background 启动；并把「列表+详情+消息中心」合并到**一个脚本一次跑完**（参考 `D:\tmp_cc\check_r11.mjs` / `check_r11b.mjs`），不要分多次调用。

## 其他备忘
- 详情页可**直接 goto**（不必点「查看详情」）：
  `https://register.ccopyright.com.cn/accountDetails.html?flowNumber=<流水号>&current=soft_register`
  页内含进度条 提交→受理→审查→发放 +「申请状态：已提交材料」+「已上传资料 查看申请表」。
- 详情页上的「登记证书预览 / 下载」弹窗是**隐藏模板 DOM**（rect 0x0），出现不等于有证书；
  「点击此处下载」是浏览器升级提示（跳 google.cn）。判断有无证书/通知书以 tab 计数 + 申请状态为准。
- 站点有多个验证码 SDK（网易易盾 cstaticdun + 腾讯 TCaptcha），机构登录走易盾 `type:2` 滑块。
- `localStorage.webUserInfo` 里有 `authorization_token`(JWT)，但 SPA 不认这个 token，仍必须走登录。
- 校验接口 `c.dun.163.com/api/v3/check` 只返回 `{"result":false}` 不给原因，别指望从响应里读失败原因，要自己量误差。
