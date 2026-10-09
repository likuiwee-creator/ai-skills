# ai-skills · 个人 AI 技能全家桶

我在用的 AI 技能集合，共 14 个。装一次全套可用，换机同步只需 `git pull`。

> 只想装代码自检 → 见 [`code-selfcheck/SKILL.md`](code-selfcheck/SKILL.md)
> 想写自己的 skill → 见 [`code-selfcheck/SKILL-WRITING-GUIDE.md`](code-selfcheck/SKILL-WRITING-GUIDE.md)

---

## 安装（同事 / 换机）

```bash
git clone git@github.com:likuiwee-creator/ai-skills.git ~/ai-skills
cd ~/ai-skills && sh sync.sh          # 一键安装全部 14 个
```

手动安装方式：

```bash
# 全量
cp -r ~/ai-skills/* ~/.workbuddy/skills/

# 或只装需要的（macOS/Linux）
cp -r ~/ai-skills/code-selfcheck ~/.workbuddy/skills/
```

Windows 把 `~/.workbuddy/skills/` 换成 `%USERPROFILE%\.workbuddy\skills\`。

装完下次对话直接说「提交前自检」「合并抖音账单」这类话，AI 会自动加载对应 skill。

**升级**：`cd ~/ai-skills && git pull && cp -r */ ~/.workbuddy/skills/`

---

## 技能清单

### 💼 财务 / 账单核对（OTA 月度例行）

| 技能 | 作用 |
|---|---|
| [`douyin-bill-merge`](douyin-bill-merge/) | 抖音分账明细月度合并（正向/退款/补偿 3 sheet 合并，退款按订单号并入） |
| [`ctrip-bill-extract`](ctrip-bill-extract/) | 携程账单「订单明细」提取 + 表头归一化（OTA订单号/打款金额） |
| [`meituan-bill-extract`](meituan-bill-extract/) | 美团「订单详情」提取，兼容改扩展名的 xlsx 与老 OLE2 .xls |
| [`meituan-bill-merge`](meituan-bill-merge/) | 美团多周账单按列对齐合并，追加「来源」标记周文件 |
| [`tongcheng-bill-extract`](tongcheng-bill-extract/) | 同程「对账单详情」提取 + 表头归一化 |

### 🔍 代码质量

| 技能 | 作用 |
|---|---|
| [`code-selfcheck`](code-selfcheck/) | **提交前自检**：语法 / 单测 / 覆盖率 / 小程序页面测试 / 安全扫描 / AI 审查（仅 critical+high 阻断） |

### 🖼️ 图片处理

| 技能 | 作用 |
|---|---|
| [`photo-to-scan`](photo-to-scan/) | 手机拍的纸质文档照片 → 干净扫描件（自动转正、裁边、提清晰度、A4 比例 PDF） |
| [`ai-image-watermark-removal`](ai-image-watermark-removal/) | 去 AI 生图水印（"AI生成"/"WORKBUDD>"），输出无缝干净图 |
| [`amap-poi-photos`](amap-poi-photos/) | 高德开放平台批量抓 POI 实景图（景区/商场/门店配图） |

### 🌐 自动化 / 运维

| 技能 | 作用 |
|---|---|
| [`chrome-cdp-drive`](chrome-cdp-drive/) | 系统 Chrome + CDP 远程调试端口驱动浏览器做网页自动化（登录/注册/多步流程） |
| [`phddns-troubleshoot`](phddns-troubleshoot/) | 花生壳内网穿透掉线/映射不通的排查与根治 |
| [`ai-companion-local-run`](ai-companion-local-run/) | 开源 AI 伴侣 / 虚拟人项目（AIRI、Open-LLM-VTuber 等）本地部署 |
| [`soft-copyright-progress`](soft-copyright-progress/) | 软著登记全流程自动化：查进度、读补正原因、下载证书 |

### 🏆 其他

| 技能 | 作用 |
|---|---|
| [`workbuddy-contest-submit`](workbuddy-contest-submit/) | 向 WorkBuddy 模板共创大赛网页表单投稿 |

---

## 通用性说明

| 部分 | 能否跨 AI 工具 |
|---|---|
| `scripts/*.cjs` 执行器 | ✅ 完全通用。零第三方依赖，只用 Node 内置模块；WorkBuddy / Codex / Cursor / Trae / Claude Code 都能 `node xxx.cjs` |
| `SKILL.md` | ⚠️ 仅 WorkBuddy / Claude Code 认这个 skill 格式，其它工具需拷进各自 skills 目录 |
| Markdown / Python 脚本 | ✅ 通用 |

给 Codex / Cursor / Trae 接入，在它们的规则文件里写一句：

```markdown
提交代码前必须执行：node <仓库路径>/code-selfcheck/scripts/selfcheck.cjs
若返回非 0，先修复问题，不得提交。
```

---

## 不含的内容

以下两个 skill **不在本仓库**，因为它们不是自建的（可能来自官方市场），再分发有许可问题：

- `article-publish-automation`
- `multi-platform-publisher`

本仓库已扫描确认**不含任何硬编码密钥、token、cookie 或证书文件**。

---

## 许可

MIT，见 [LICENSE](LICENSE)。各 skill 的详细说明见各自目录内的 `SKILL.md`。
