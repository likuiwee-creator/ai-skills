---
name: workbuddy-contest-submit
description: "通过浏览器自动化向 WorkBuddy「一键成台」工作台模板共创大赛的网页表单投稿。当用户要参加 WorkBuddy 工作台模板大赛、说『大赛投稿』『参赛』『把作品提交到大赛页』，或要把一个已发布的 WorkBuddy 个人工作台/模板投到 workbuddy.link 大赛页时调用。该 skill 编码了：投稿页 URL、表单字段选择器(#fName/#fUrl/#fRaw/#fUid/#fAuthor/#fPhone/#fFile/#fOk/#fSub)、发布入口(发布作品→直接投稿)、微信扫码登录流程，以及反复踩过的坑(NODE_OPTIONS 清理、成功判据只看投稿 iframe 可见文本、整页跳登录需暂停等扫码)。它是通用流程——具体投稿内容(标题/模板链接/描述/UserID/昵称/手机号/截图/标签)由调用时用户提供。"
agent_created: true
---

# WorkBuddy 大赛网页投稿（浏览器自动化）

把用户已发布的 WorkBuddy「个人工作台 / 模板」投到「一键成台」工作台模板共创大赛。

## 一、投稿要求与赛程（务必先和用户确认在档期内）

- **作品形态**：必须是 WorkBuddy「个人工作台」——即用户已在资料库发布、拿到 `workbuddy.link/p/...` 公开模板链接的 HTML+CSV 双向同步工作台。投稿时填的就是这个**模板链接**，不是源码。
- **关键信息**（投稿表单要填）：作品名称、模板链接、作品介绍、UserID、作者昵称、手机号、作品截图（1~3 张）、参赛标签、参赛授权勾选。
- **评分构成**（影响怎么冲排名）：大众投票 50% + 创意 30% + 实用 20% + 社媒分享 +10 分。→ 拉票 + 社媒扩散都直接加分。
- **典型赛程**（以 2026 届为例，实际以大赛页公告为准）：
  - 投稿征集：8/13–8/27
  - 集中投票：8/28–8/30（注意：常误写成 8/27 开始，实际次日起）
  - 评审 8/31–9/3 ｜ 结果公示 9/4 ｜ 奖品发放 9/5–9/16
- **合规红线（作品本身必须守）**：不预测开奖/不保证中奖/不承诺收益，只讲记录、复盘、统计实验。介绍文案里写明这一点，避免违规下架。

## 二、操作流程（脚本自动跑，登录那步交给用户扫码）

1. 用 Playwright **有头(可见)浏览器** + `launch_persistent_context` 打开投稿页（只 `goto` 一次，避免 429 限流）。
2. 进入投稿 iframe（`workbuddy-space-static` 域名），点 `button#pub` → 点文本「我已经做好了，直接投稿」打开表单。
3. 填表：依次 fill `#fName #fUrl #fRaw #fUid #fAuthor #fPhone`，`#fFile` 用 `set_input_files` 传截图，`button.trkb`(has_text=标签) 选标签，`#fOk` 授权勾选（自定义复选框，见坑③）。
4. 点 `#fSub` 提交 → **整页跳 `codebuddy.cn/login`**（不是页内浮层）。
5. 登录页点 `.agree-btn` 出微信二维码 → **暂停，用户在可见窗口扫码**（可能弹「选择账号」需点选）→ 扫完跳回投稿页。
6. 带登录态**重新填表 + 二次提交** → 出现「提交成功，等待审核」即成功（此时表单/提交按钮消失）。

## 三、表单字段与选择器（投稿 iframe 内）

| 字段 | 选择器 | 说明 |
|------|--------|------|
| 作品名称 | `#fName` | fill |
| 模板链接 | `#fUrl` | fill，即 `workbuddy.link/p/...` |
| 作品介绍 | `#fRaw` | fill，多行 |
| UserID | `#fUid` | fill，用户在资料库/个人页查 |
| 作者昵称 | `#fAuthor` | fill |
| 手机号 | `#fPhone` | fill |
| 作品截图 | `#fFile` | `set_input_files([...])` 1~3 张 png |
| 参赛标签 | `button.trkb` has_text=标签名 | 如「理财记账」，点选其一 |
| 参赛授权 | `#fOk` | 自定义复选框，需特殊勾选 |
| 提交按钮 | `#fSub` | click 提交 |

## 四、关键坑（已验证，照做可一次过）

1. **必须 `os.environ.pop("NODE_OPTIONS", None)`**：否则 Playwright 的 node 驱动继承 `--use-system-ca` 报错 `Executable doesn't exist`。
2. **成功判据只看「投稿 iframe 内可见文本」**：父页 chrome / `<script>` 源码里写死的「提交成功/等待审核」字样会误判。绝不能用全页 `innerText` 或源码匹配。
3. **授权框 `#fOk` 是自定义样式**：直接 `check()` 不生效，按「label[for=fOk] → 父节点点击 → JS 置 checked+dispatchEvent」三级兜底。
4. **提交后整页跳登录页**：用 `wait_for_url` / 轮询所有 `browser.pages` 检测 `codebuddy.cn`，命中即停等扫码；不要误把「iframe 消失」当成功（那可能是正在跳登录）。
5. **只加载一次页面**，轮询用 `time.sleep` 而非反复 `goto`，否则触发 429 too many requests。
6. **二次提交**：扫码跳回后登录态才生效，需重新 `open_form`+`fill_form`+提交。

## 五、环境

- Python 3.13 系统解释器 `D:/Python/python.exe`（已装 `playwright==1.52.0`，ms-playwright chromium 缓存齐全）。
- 若换机：`pip install playwright && playwright install chromium`。
- 公司网络走代理：从 `HTTPS_PROXY` 读，传给 `launch_persistent_context(proxy=...)`。

## 六、即用脚本模板

参数化脚本见 `references/submit_template.py`：把顶部 `TITLE/LINK/DESC/UID/NICK/PHONE/SHOTS/TAG/URL` 替换为本次投稿内容即可直接运行（有头模式，扫码那步停在可见窗口）。建议后台启动 `run_in_background`，用户在桌面窗口扫码，跑完看 `contest-screenshots/headed_result.png` 确认「提交成功，等待审核」。
