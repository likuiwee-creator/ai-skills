# code-selfcheck · 提交前自检

跨项目的「提交即自检」方案：语法校验、单元测试、覆盖率下限、小程序页面单测、安全扫描、AI 代码审查（仅 critical/high 阻断）。

**设计原则**：缺工具只 SKIP 不 FAIL——换一台没装 semgrep 的电脑不会因为它卡住提交；只有真正跑起来的检查失败才阻断。

> 📘 **要写自己的 skill？** 看 [`SKILL-WRITING-GUIDE.md`](SKILL-WRITING-GUIDE.md)——目录规范、description 写法、自检清单、给 AI 的指令模板，可直接复制给 Codex/Trae/Cursor 等 AI 使用。
>
> ☁️ **要推到 GitLab / GitHub / 给同事用？** 看 [`PUSH-GUIDE.md`](PUSH-GUIDE.md)——什么是 remote、两步推送、SSH/HTTPS 两种方式、同事怎么用。

---

## 跨工具通用性（重要，先看这节）

本目录分两部分，通用性不同：

| 部分 | 文件 | 能否给 Codex / Trae / Cursor / Claude Code 用 |
|---|---|---|
| **执行器** | `scripts/selfcheck.cjs`、`scripts/ocr_gate.cjs` | ✅ **完全通用**。纯 Node 内置模块（fs/path/vm/child_process），零第三方依赖，不调用任何 AI 工具的私有 API。只要有 Node 18+ 就能跑。 |
| **说明书** | `SKILL.md` | ⚠️ 格式面向 WorkBuddy/Claude Code 的 skill 规范。其他工具不认这个格式，但里面的规则和用法可以直接读。 |

**所以结论**：
- 想让别的 AI 工具用**能力**（跑检查）→ 直接调用 `node scripts/selfcheck.cjs`，任何工具都能做。
- 想让别的 AI 工具**自动触发**→ 需要按那个工具的约定改配置，见下节。

### 各工具接入方式

**通用（任何能执行 shell 的 AI 工具）**
```bash
node scripts/selfcheck.cjs            # 跑全量自检
node scripts/selfcheck.cjs --list     # 看这个项目能跑哪些阶段
```

**Codex / Claude Code / Cursor 等有「自定义命令/规则」机制的工具**
把这些内容写进对应的规则文件（如 `AGENTS.md` / `.cursorrules` / `CLAUDE.md`）：
```markdown
提交代码前必须执行：node <此目录>/scripts/selfcheck.cjs
若返回非 0，则先修复问题，不得提交。临时跳过用 git commit --no-verify。
```
这样 AI 在生成/提交代码前会自动跑一遍。

**想完整触发 skill 语义** → 复制本目录到该工具的 skills 目录：
- Claude Code：`~/.claude/skills/code-selfcheck/`
- WorkBuddy：`~/.workbuddy/skills/code-selfcheck/`
- 其他工具按其约定放置

---

## 安装

### 1. 在项目里启用（本地提交即自检）
```bash
node scripts/selfcheck.cjs --install
```
会做三件事：
1. 写 `.githooks/pre-commit` 并设置 `git config core.hooksPath .githooks`
2. 写 `ci/precommit.sh`（若项目已有同名文件会保留不覆盖）
3. 提示你把 `coverage/` 加进 `.gitignore`

之后每次 `git commit` 自动跑。临时跳过：`git commit --no-verify`。

### 2. 作为 CI 门禁（团队强制，不依赖个人环境）
把 `scripts/` 整个目录放进项目仓库（如 `ci/selfcheck/`），`.gitlab-ci.yml` / GitHub Actions 里调用：
```yaml
unit-test:
  script: [node ci/selfcheck/scripts/selfcheck.cjs --only syntax,test,coverage]
```
CI 中需自行安装依赖（c8 / jest / semgrep），并通过 CI Variables 注入 OCR 的云端 API key。

### 3. 给同事
把本目录拷进对方的 skills 目录，或作为 git 子目录共享（推荐，便于 `git pull` 升级）。

---

## 六个阶段

| 阶段 | 做什么 | 依赖 | 缺依赖 |
|---|---|---|---|
| `syntax` | JS 用 `vm.Script` 编译校验；Python 用 `compileall` | 无 | — |
| `test` | 跑 `npm test` 或项目根 `.utest.js` | 无 | SKIP |
| `coverage` | c8 卡行覆盖率下限（默认 70%） | `npm i -D c8` | SKIP |
| `pagetest` | 小程序页面 jest 单测（wx/getApp/Page mock） | `npm i -D jest` + `miniprogram/jest.config.js` | SKIP |
| `security` | semgrep `auto` 规则集扫 ERROR/WARNING | `pip install semgrep` | SKIP |
| `ai` | OCR 审查最近提交 diff，仅 critical/high 阻断 | `@alibaba-group/open-code-review` + 云端 LLM | SKIP |

### 命令行参数
```bash
node scripts/selfcheck.cjs --list                 # 只探测，不执行
node scripts/selfcheck.cjs --only syntax,test    # 只跑指定阶段
node scripts/selfcheck.cjs --skip ai             # 跳过某些阶段
node scripts/selfcheck.cjs --install / --uninstall
```

### 环境变量
- `COVERAGE_LINES=80` 覆盖率下限（默认 70）
- `SELFCHECK_VERBOSE=1` 打印 PASS 阶段细节
- `OCR_INFRA_FAILS_PIPELINE=true` 让 OCR 自身报错（余额不足/网络失败）也算失败

---

## ⚠️ 已知坑（别重复踩）

1. **AI 审查不要用小模型做阻断门禁。** 实测 7B 本地模型会凭空点名不存在的函数（报 3 条 high，其中 2 条点名的函数在代码里根本没有）。若「high 即阻断」且跑本地小模型，会把干净的提交误杀。**用云端 LLM。**
2. **`.mjs` 是 ESM**，`vm.Script` 编译必失败，语法校验已排除；`.js` 里若有 ESM 语法需另行处理。
3. **jest 不走 `require.cache`**——想重新加载页面模块必须 `jest.resetModules()`，否则第二次 `require` 不会重新执行 `Page()`。
4. **`afterEach` 必须放 `setupFilesAfterEnv`**，放 `setupFiles` 会报「框架未注入」。
5. **jest 配置用相对路径会被当目录解析**，必须 `cd` 到该目录再跑。
6. **`coverage/` 记得 gitignore**，否则每次提交都污染仓库。
7. **OCR 抽风默认不冻结合并**（余额/网络失败时放行）。要改成硬性门禁，设 `OCR_INFRA_FAILS_PIPELINE=true`。
8. **Windows 上父进程与子进程同为 node.exe 时偶发 `spawnSync EBUSY`**，脚本已做重试 + shell 退路 + 降级 SKIP，不会误报失败。

---

## 小程序页面单测

见 `references/miniprogram-jest.md`：完整 wx mock 模板、`setData` 路径键实现、模块重载与状态复位的正确写法。

---

## AI 只作辅助
这套检查不替代人工 CR。AI 审查基于 LLM，有幻觉和漏报；semgrep 只覆盖已知规则模式。发现问题请先核对代码再动手。
