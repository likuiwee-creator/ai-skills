---
name: code-selfcheck
description: "代码提交前自检。在任何 JS/Node/Python 项目里跑多阶段检查：语法校验、单元测试、c8 覆盖率下限、小程序页面 jest 单测(wx/getApp/Page mock)、semgrep 安全扫描、Open Code Review 变更diff 审查(仅 critical/high 阻断)。可一键安装 git pre-commit 钩子实现「提交即自检」，也可生成 GitLab CI 门禁。当用户说「提交前自检」「commit 前检查」「装个自检钩子」「代码质检」「提交前跑一遍测试」「覆盖率门禁」「安全扫描」「AI 审查」「代码审查流水线」时使用。"
agent_created: true
---

# 代码提交前自检（code-selfcheck）

跨项目的「提交即自检」方案：一个脚本跑完所有检查，可挂进 git pre-commit，也可作 CI 门禁。**缺工具只跳过、不误报失败**，所以在任何机器上都不会因为没装某个工具而卡住你。

## 何时使用
- 用户说「提交前自检」「装个提交钩子」「commit 前检查一遍」「代码质检一下」。
- 用户要提 MR 前想先跑一遍安全 + 测试 + 覆盖率。
- 用户问「有没有办法让 AI 在提交时自动审查代码」。
- 关键词：自检 / 质检 / pre-commit / 覆盖率门禁 / semgrep / AI 代码审查 / 提交前检查。

## 核心设计原则（务必遵守，勿改坏）

1. **缺工具 = SKIP，不是 FAIL。** 没装 semgrep/jest/OCR 时只提示「跳过」，绝不让提交失败。否则换台电脑就被卡死，用户会直接卸载。
2. **只有真正跑起来的检查失败才阻断。** 语法错、单测挂、覆盖率不达标、高危安全问题、OCR 报 critical/high → 才 `exit 1`。
3. **自动探测，不写死路径。** 识别 JS / Python / 微信小程序（有 `app.json` 或 `project.config.json`）/ git 仓库，按项目类型选检查项。
4. **AI 审查只扫变更 diff，不扫全量**，避免慢和不相关噪音。

## 用法

```bash
# 先看这个项目能跑哪些阶段（探测结果，不执行）
node "<skill_dir>/scripts/selfcheck.cjs" --list

# 全量自检（工作目录 = 项目根）
node "<skill_dir>/scripts/selfcheck.cjs"

# 只跑部分阶段 / 跳过某些阶段
node "<skill_dir>/scripts/selfcheck.cjs" --only syntax,test,coverage
node "<skill_dir>/scripts/selfcheck.cjs" --skip ai,security

# 一键装 git pre-commit 钩子（提交即自检）
node "<skill_dir>/scripts/selfcheck.cjs" --install
node "<skill_dir>/scripts/selfcheck.cjs" --uninstall   # 卸载
```

环境变量：
- `COVERAGE_LINES=80` 覆盖行覆盖率下限（默认 70）
- `SELFCHECK_VERBOSE=1` 打印 PASS 阶段的细节
- `OCR_INFRA_FAILS_PIPELINE=true` 让 OCR 自身报错（余额不足/网络失败）也算失败

临时跳过：`git commit --no-verify`。

## 六个阶段

| 阶段 | 做什么 | 依赖 | 缺依赖时 |
|---|---|---|---|
| `syntax` | 所有 JS 用 `vm.Script` 编译校验；Python 用 `compileall` | 无 | — |
| `test` | 跑 `npm test`，或项目根的 `.utest.js` | 无 | SKIP |
| `coverage` | c8 量行覆盖率并卡下限 | `npm i -D c8` | SKIP |
| `pagetest` | 小程序页面 jest 单测 | `npm i -D jest` + `miniprogram/jest.config.js` | SKIP |
| `security` | semgrep `auto` 规则集，扫 ERROR/WARNING | `pip install semgrep` | SKIP |
| `ai` | OCR 审查最近一次提交 diff，仅 critical/high 阻断 | `npm i -D @alibaba-group/open-code-review` + 云端 LLM key | SKIP |

## 一键安装钩子后发生了什么

`--install` 会做三件事：
1. 写 `.githooks/pre-commit`，并设 `git config core.hooksPath .githooks`（避开各家 hook 目录差异）。
2. 写 `ci/precommit.sh`（薄壳，转调同一个脚本）——**CI 与本地共用同一份逻辑**，不会出现"本地过了线上挂"。
3. 提示不要提交 `coverage/` 到仓库。

## 新项目接入建议

- **JS/Node 普通项目**：`npm i -D c8 @alibaba-group/open-code-review`，加一个 `test` script，`--install` 即可。
- **微信小程序项目**：额外需要 jest 配置 + `wx`/`getApp`/`Page` mock。照抄本 skill 的 `references/miniprogram-jest.md`，里面踩过的坑都在（关键：jest 模块注册表不走 `require.cache`，必须 `jest.resetModules()` 才能重新捕获 `Page()`；`afterEach` 必须放 `setupFilesAfterEnv`）。
- **Python 项目**：`syntax` 阶段直接可用；覆盖率建议 `pytest --cov`。

## ⚠️ 已知坑（别重复踩）

1. **OCR 绝不能用小模型本地跑来做阻断门禁。** 7B 本地模型会凭空点名不存在的函数（本 skill 交付时实测：报 3 条 high，其中 2 条点名的函数在代码里根本不存在）。若"high 即阻断"且跑在本地小模型上，会把干净提交误杀。OCR 门禁必须走云端 LLM。
2. **覆盖率载体**：小程序页面的 `utils/` 之外，页面级要靠 `pagetest` 阶段量；只用 c8 量 `utils/**` 会低估实际覆盖。
3. **jest 配置路径**：`jest --config relative/path/jest.config.js` 会把相对路径当目录解析，必须 `cd` 到该目录再跑。
4. **测试产物 `coverage/` 必须 gitignore**，否则每次提交都会污染仓库。
5. **OCR 抽风不冻结合并**（默认）：LLM 审查可能因余额/网络失败，此时默认放行；要改成"审查必须成功"需显式设 `OCR_INFRA_FAILS_PIPELINE=true`。

## 配套：GitLab CI 门禁（服务器侧）

本地钩子管「提交前」，CI 管「合并前」，两者用同一个 `selfcheck.cjs`。`.gitlab-ci.yml` 骨架：

```yaml
stages: [fast-gate, ai-code-review, unit-test]
fast-gate:
  stage: fast-gate
  image: returntocorp/semgrep          # semgrep 官方镜像，自带工具
  script: [semgrep scan --config auto --severity ERROR --severity WARNING --error --quiet]
ai-code-review:
  stage: ai-code-review
  image: node:22
  script:
    - npm i -D @alibaba-group/open-code-review
    - node .githooks/../<skill>/scripts/selfcheck.cjs --only ai   # OCR 走云端，key 从 CI Variables 注入
  rules: [if: $CI_PIPELINE_SOURCE == "merge_request_event"]
unit-test:
  stage: unit-test
  image: node:22
  script: [node <skill>/scripts/selfcheck.cjs --only syntax,test,coverage,pagetest]
```

**必须去项目 Settings ▸ Merge requests 打开 "Pipelines must succeed"**，否则流水线失败也拦不住合并。

## AI 只作辅助
这套检查是辅助手段，不替代人工 CR。OCR 的判断基于 LLM，有幻觉和漏报；semgrep 只覆盖已知规则模式。发现问题时，先核对代码再动手。
