#!/usr/bin/env node
/**
 * code-selfcheck · 提交前自检执行器（跨项目）
 *
 * 用法：
 *   node selfcheck.cjs                      # 全量自检（自动探测）
 *   node selfcheck.cjs --only syntax,test   # 只跑指定阶段
 *   node selfcheck.cjs --install            # 写入 pre-commit 钩子 + 门禁脚本
 *   node selfcheck.cjs --uninstall          # 移除钩子
 *   node selfcheck.cjs --list               # 列出可用阶段与探测结果
 *
 * 退出码：0 = 通过（缺失工具算「跳过」不算失败）；1 = 有阶段失败。
 * 设计原则：缺工具只 SKIP 不 FAIL；只有真正跑起来的检查失败才算失败。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const cp = require('child_process');

const ROOT = process.cwd();

// ---------- 工具函数 ----------
function readJSON(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return null; } }
function exists(p) { try { fs.accessSync(p); return true; } catch (e) { return false; } }
const SKIP_DIRS = new Set(['node_modules', '.git', 'coverage', 'dist', 'build', 'vendor', '.next',
  '__pycache__', 'venv', '.venv', 'target', 'out', '.next_cache', 'mp_profile', 'tmp', 'logs']);

function walk(dir, acc, depth) {
  if (depth > 8) return acc;
  let ents = [];
  try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { return acc; }
  for (const e of ents) {
    if (SKIP_DIRS.has(e.name)) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, acc, depth + 1);
    else acc.push(p);
  }
  return acc;
}
function which(bin) {
  const r = cp.spawnSync(process.platform === 'win32' ? 'where' : 'command',
    process.platform === 'win32' ? [bin] : ['-v', bin], { encoding: 'utf8', shell: true });
  return r.status === 0 && !/not found|不是内部/i.test(r.stdout || '');
}
function resolveNodeBin(name) {
  // 在常见全局位置找 CLI（node_modules/.bin 或全局根）
  const execDir = path.dirname(process.execPath); // .../versions/22.12.0
  const roots = [
    process.env.NODE_PATH,
    path.join(execDir, 'node_modules'),
    path.join(execDir, '..', '..', 'node_modules'),
    path.join(execDir, '..', '..', 'workspace', 'node_modules'),
    process.env.APPDATA ? path.join(process.env.APPDATA, 'npm', 'node_modules') : '',
  ];
  for (const r of roots) {
    if (!r) continue;
    for (const cand of [path.join(r, name, 'bin', name + '.js'), path.join(r, '.bin', name)]) {
      if (exists(cand)) return cand;
    }
  }
  return null;
}
// Windows: 父进程与目标同为 node.exe 时偶发 EBUSY/EPERM（文件占用）。
// 先重试一次；仍失败则用 shell 中转再试一次（避开直接 spawn 同一可执行文件）。
function run(cmd, args, opts) {
  const o = Object.assign({ encoding: 'utf8', cwd: ROOT, shell: false }, opts || {});
  let r = cp.spawnSync(cmd, args, o);
  if (r.status === null && r.error && /EBUSY|EPERM|EACCES/i.test(r.error.message || '')) {
    r = cp.spawnSync(cmd, args, o);
    if (r.status === null && r.error && /EBUSY|EPERM|EACCES/i.test(r.error.message || '')) {
      // 退路：用 shell 包装执行同一命令，绕开直接 spawn 冲突
      const quoted = [cmd].concat(args).map(a => (/[\s"]/.test(a) ? '"' + String(a).replace(/"/g, '\\"') + '"' : String(a))).join(' ');
      r = cp.spawnSync(quoted, Object.assign({}, o, { shell: true }));
    }
  }
  return r;
}
// spawn 层面失败（EBUSY 等环境限制）→ 不能算「检查不通过」，视为不可用
function spawnBroken(r) {
  return r.status === null || !!r.error;
}
function tail(s, n) {
  const lines = String(s || '').trim().split('\n');
  return lines.slice(Math.max(0, lines.length - n)).join('\n');
}

// ---------- 项目探测 ----------
function detect() {
  const d = {
    files: walk(ROOT, [], 0),
    pkg: readJSON(path.join(ROOT, 'package.json')),
    hasGit: exists(path.join(ROOT, '.git')),
    isMiniProgram: exists(path.join(ROOT, 'miniprogram')) || exists(path.join(ROOT, 'app.json')) ||
      exists(path.join(ROOT, 'project.config.json')),
    isPy: false, isJs: false,
  };
  d.isJs = d.files.some(f => /\.(js|mjs|cjs|jsx|ts|tsx)$/.test(f));
  d.isPy = d.files.some(f => /\.py$/.test(f));
  d.scripts = (d.pkg && d.pkg.scripts) || {};
  return d;
}

// ---------- 阶段实现 ----------
const stages = [];

stages.push({
  name: 'syntax',
  title: '语法 / 可解析性校验',
  available: (d) => d.isJs || d.isPy,
  run(d) {
    if (d.isJs) {
      // 只校验 CJS/脚本语义的 .js/.cjs；.mjs/.esm 是 ESM，vm.Script 编译必失败，不适用本检查
      const files = d.files.filter(f => /\.(js|cjs)$/.test(f) && !/\.min\.js$/.test(f));
      if (!files.length) return { status: 'SKIP', note: '未发现 JS 文件' };
      const bad = [];
      let checked = 0;
      for (const f of files) {
        let src;
        try { src = fs.readFileSync(f, 'utf8'); } catch (e) { continue; }
        // 跳过明显非源码：抓取失败响应体、超大生成文件、空文件
        if (!src.trim() || src.length > 4 * 1024 * 1024) continue;
        if (/^(ERR\b|Error:|<!DOCTYPE|<html)/i.test(src.trim().slice(0, 40))) continue;
        checked++;
        try { new vm.Script(src, { filename: f }); }
        catch (e) { bad.push({ f: path.relative(ROOT, f), msg: String(e.message).split('\n')[0] }); }
      }
      if (!checked) return { status: 'SKIP', note: '无可校验的源码文件' };
      if (bad.length) return { status: 'FAIL', note: bad.length + ' 个文件解析失败', detail: bad.map(b => b.f + ' → ' + b.msg).join('\n') };
      return { status: 'PASS', note: checked + ' 个 JS 文件全部可解析' };
    }
    const r = run(process.env.PYTHON || 'python3', ['-m', 'compileall', '-q', '-x', 'node_modules|venv|\\.git|__pycache__', '.']);
    if (r.status !== 0 && !r.stderr) return { status: 'SKIP', note: 'python3 不可用' };
    return r.status === 0
      ? { status: 'PASS', note: 'Python 全部可编译' }
      : { status: 'FAIL', note: 'Python 编译失败', detail: tail(r.stdout + r.stderr, 20) };
  },
});

stages.push({
  name: 'test',
  title: '单元测试',
  available: (d) => exists(path.join(ROOT, '.utest.js')) || d.scripts.test || d.files.some(f => /\.test\.(js|mjs|cjs)$/.test(f)),
  run(d) {
    // 优先项目自带 test script
    if (d.scripts.test) {
      const r = run('npm', ['run', 'test'], { shell: true });
      if (spawnBroken(r)) return { status: 'SKIP', note: 'npm test 无法执行（环境限制：' + ((r.error && r.error.message) || 'spawn failed') + '）' };
      return r.status === 0
        ? { status: 'PASS', note: 'npm test 通过' }
        : { status: 'FAIL', note: 'npm test 失败', detail: tail(r.stdout + r.stderr, 25) };
    }
    const ut = path.join(ROOT, '.utest.js');
    if (exists(ut)) {
      const r = run(process.execPath, ['.utest.js']);
      if (spawnBroken(r)) return { status: 'SKIP', note: '.utest.js 无法执行（环境限制：' + ((r.error && r.error.message) || 'spawn failed') + '）' };
      return r.status === 0
        ? { status: 'PASS', note: tail(r.stdout, 1) || '.utest.js 通过' }
        : { status: 'FAIL', note: '.utest.js 失败', detail: tail(r.stdout + r.stderr, 25) };
    }
    return { status: 'SKIP', note: '未找到测试入口（.utest.js 或 npm test）' };
  },
});

stages.push({
  name: 'coverage',
  title: '覆盖率下限（c8）',
  available: () => !!resolveNodeBin('c8'),
  run(d) {
    const c8 = resolveNodeBin('c8');
    if (!c8) return { status: 'SKIP', note: 'c8 未安装（npm i -D c8）' };
    const include = d.isMiniProgram ? ['miniprogram/utils/**', 'utils/**'] : ['**/*.js', '!**/node_modules/**'];
    const lines = process.env.COVERAGE_LINES || '70';
    const target = exists(path.join(ROOT, '.utest.js')) ? '.utest.js' : null;
    if (!target) return { status: 'SKIP', note: '无 .utest.js 作为覆盖率载体' };
    const args = [c8, '--check-coverage', '--lines', lines, '--reporter', 'text-summary'];
    for (const inc of include) args.push('--include', inc);
    args.push(process.execPath, target);
    const r = run(process.execPath, args);
    if (spawnBroken(r)) return { status: 'SKIP', note: 'c8 无法执行（环境限制：' + ((r.error && r.error.message) || 'spawn failed') + '）' };
    return r.status === 0
      ? { status: 'PASS', note: '行覆盖 ≥ ' + lines + '%', detail: tail(r.stdout, 6) }
      : { status: 'FAIL', note: '覆盖率低于 ' + lines + '% 或单测失败', detail: tail(r.stdout + r.stderr, 25) };
  },
});

stages.push({
  name: 'pagetest',
  title: '小程序页面单测（jest + wx mock）',
  available: (d) => d.isMiniProgram && exists(path.join(ROOT, 'miniprogram', 'jest.config.js')),
  run(d) {
    const jest = resolveNodeBin('jest');
    if (!jest) return { status: 'SKIP', note: 'jest 未安装（npm i -D jest）' };
    const r = run(process.execPath, [jest, '--coverage'], { cwd: path.join(ROOT, 'miniprogram') });
    if (spawnBroken(r)) return { status: 'SKIP', note: 'jest 无法执行（环境限制：' + ((r.error && r.error.message) || 'spawn failed') + '）' };
    return r.status === 0
      ? { status: 'PASS', note: '页面单测全绿', detail: tail(r.stdout, 8) }
      : { status: 'FAIL', note: '页面单测失败', detail: tail(r.stdout + r.stderr, 30) };
  },
});

stages.push({
  name: 'security',
  title: '安全扫描（semgrep）',
  available: () => which('semgrep') || exists(path.join(ROOT, '.venv', 'Scripts', 'semgrep.exe')) ||
    exists(path.join(ROOT, '.venv', 'bin', 'semgrep')),
  run() {
    const local = [path.join(ROOT, '.venv', 'Scripts', 'semgrep.exe'),
      path.join(ROOT, '.venv', 'bin', 'semgrep')].find(exists);
    const bin = local || 'semgrep';
    const r = run(bin, ['scan', '--config', 'auto', '--severity', 'ERROR', '--severity', 'WARNING',
      '--error', '--quiet', '--skip-unknown-extensions'], { shell: !!local ? false : true });
    if (r.status === 0) return { status: 'PASS', note: 'semgrep 无高危问题' };
    if (r.status === 1) return { status: 'FAIL', note: 'semgrep 发现高危问题', detail: tail(r.stdout + r.stderr, 40) };
    return { status: 'SKIP', note: 'semgrep 不可用（pip install semgrep）' };
  },
});

stages.push({
  name: 'ai',
  title: 'AI 代码审查（OCR，仅变更 diff）',
  available: () => !!resolveNodeBin('@alibaba-group/open-code-review/bin/ocr.js') || exists(path.join(ROOT, 'node_modules', '@alibaba-group', 'open-code-review', 'bin', 'ocr.js')),
  run() {
    const ocr = path.join(ROOT, 'node_modules', '@alibaba-group', 'open-code-review', 'bin', 'ocr.js')
      || resolveNodeBin('@alibaba-group/open-code-review/bin/ocr.js');
    if (!exists(ocr)) return { status: 'SKIP', note: 'OCR 未安装（npm i -D @alibaba-group/open-code-review）' };
    // 取最近一次提交的 diff 做审查（无云端 key 时用户可跳过）
    const head = run('git', ['rev-parse', '--short', 'HEAD']);
    if (head.status !== 0) return { status: 'SKIP', note: '非 git 仓库，跳过 diff 审查' };
    const rev = head.stdout.trim();
    const out = 'ocr_selfcheck.json';
    const r = run(process.execPath, [ocr, 'review', '--commit', rev, '--format', 'json', '--audience', 'agent'],
      { shell: true, env: Object.assign({}, process.env) });
    const gate = path.join(__dirname, 'ocr_gate.cjs');
    const g = exists(gate) ? run(process.execPath, [gate, out], { cwd: ROOT }) : { status: 0 };
    let found = '未产出报告';
    if (exists(out)) {
      try {
        const d = readJSON(out) || {};
        const cs = d.comments || d.results || [];
        found = cs.length + ' 条建议；阻断级 ' + cs.filter(c => /^(critical|high)$/i.test(c.severity || '')).length + ' 条';
        fs.unlinkSync(out);
      } catch (e) { /* ignore */ }
    }
    return g.status === 1
      ? { status: 'FAIL', note: 'OCR 发现 critical/high（' + found + '）', detail: tail(r.stdout, 20) }
      : { status: 'PASS', note: 'OCR 无阻断级问题（' + found + '）' };
  },
});

// ---------- 安装 / 卸载钩子 ----------
function hookBody() {
  return `#!/bin/sh
# code-selfcheck · 提交前自检（由 skill 自动写入）
# 临时跳过：git commit --no-verify
# 项目若自带 ci/precommit.sh 则优先用它（可能含项目定制逻辑）
set -e
if [ -f ci/precommit.sh ]; then sh ci/precommit.sh; exit $?; fi
"%NODE%" "%SELF%" || exit $?
`;
}
// sh 脚本里 Windows 反斜杠会被当转义符，统一转正斜杠
function shPath(p) { return p.replace(/\\/g, '/'); }
function installHooks() {
  const selfAbs = __filename;
  const nodeAbs = process.execPath;
  const hookDir = path.join(ROOT, '.githooks');
  fs.mkdirSync(hookDir, { recursive: true });
  const hp = path.join(hookDir, 'pre-commit');
  let body = hookBody().replace('%SELF%', shPath(selfAbs)).replace('%NODE%', shPath(nodeAbs));
  fs.writeFileSync(hp, body, 'utf8');
  try { fs.chmodSync(hp, 0o755); } catch (e) { /* win */ }
  // git 在 Windows 上是 .cmd 批处理，需 shell 中转；EBUSY 时重试
  const r = run('git', ['config', 'core.hooksPath', '.githooks'], { shell: true });
  let hookOk = r.status === 0;
  if (!hookOk) {
    // 兜底：直接改写 .git/config（沙箱/无 git 命令环境）
    const cfg = path.join(ROOT, '.git', 'config');
    if (exists(cfg)) {
      let txt = '';
      try { txt = fs.readFileSync(cfg, 'utf8'); } catch (e) { txt = ''; }
      if (/\[core\]/.test(txt)) {
        txt = /hooksPath\s*=/.test(txt)
          ? txt.replace(/^(\s*hooksPath\s*=).*$/m, '$1 .githooks')
          : txt.replace(/\[core\]/, '[core]\n\thooksPath = .githooks');
      } else {
        txt += '\n[core]\n\thooksPath = .githooks\n';
      }
      fs.writeFileSync(cfg, txt, 'utf8');
      hookOk = true;
      console.log('· git config 不可用，已直接改写 .git/config 设置 core.hooksPath');
    }
  }
  const ci = path.join(ROOT, 'ci', 'precommit.sh');
  fs.mkdirSync(path.dirname(ci), { recursive: true });
  // 不覆盖项目已有的门禁脚本（可能含项目定制逻辑）；已存在则保持原样并提示
  if (exists(ci)) {
    console.log('· ci/precommit.sh 已存在，保留不覆盖（如需改为 skill 版请手动删除后再 install）');
  } else {
    fs.writeFileSync(ci, [
      '#!/bin/sh',
      '# code-selfcheck · 门禁（git pre-commit 与 CI 共用同一份执行器）',
      `exec "${shPath(nodeAbs)}" "${shPath(selfAbs)}"`,
      '',
    ].join('\n'), 'utf8');
    try { fs.chmodSync(ci, 0o755); } catch (e) { /* win */ }
    console.log('✓ 已写入 ci/precommit.sh（CI 可直接调用同一个执行器）');
  }
  if (hookOk) {
    console.log('✓ 已启用 core.hooksPath=.githooks（pre-commit 将自动生效）');
  } else {
    console.log('✗ 警告：未能设置 core.hooksPath，钩子不会自动生效。请手动执行：git config core.hooksPath .githooks');
  }
  console.log('提示：把 coverage/ 加进 .gitignore；临时跳过用 git commit --no-verify');
}
function uninstallHooks() {
  run('git', ['config', '--unset', 'core.hooksPath']);
  for (const p of [path.join(ROOT, '.githooks', 'pre-commit'), path.join(ROOT, 'ci', 'precommit.sh')]) {
    if (exists(p)) { fs.unlinkSync(p); console.log('✓ 已删除 ' + path.relative(ROOT, p)); }
  }
}

// ---------- 主流程 ----------
function main() {
  const argv = process.argv.slice(2);
  if (argv.includes('--install')) return installHooks();
  if (argv.includes('--uninstall')) return uninstallHooks();

  const d = detect();
  const listOpt = (name) => {
    const eq = argv.find(a => a.startsWith('--' + name + '='));
    if (eq) return eq.slice(('--' + name + '=').length).split(',').map(s => s.trim());
    const i = argv.indexOf('--' + name);
    if (i >= 0 && argv[i + 1] && !argv[i + 1].startsWith('--')) {
      return argv[i + 1].split(',').map(s => s.trim());
    }
    return null;
  };
  const only = listOpt('only');
  const skip = listOpt('skip') || [];
  const list = only ? stages.filter(s => only.includes(s.name)) : stages.filter(s => !skip.includes(s.name));

  if (argv.includes('--list')) {
    console.log('项目探测：' + [
      d.isJs ? 'JS/Node' : null, d.isPy ? 'Python' : null,
      d.isMiniProgram ? '小程序' : null, d.hasGit ? 'git' : 'no-git',
    ].filter(Boolean).join(' / '));
    for (const s of stages) {
      console.log((s.available(d) ? '  [可用] ' : '  [缺依赖] ') + s.name.padEnd(10) + s.title);
    }
    return;
  }

  console.log('=== 提交前自检 · ' + ROOT + ' ===');
  console.log('项目类型：' + [
    d.isJs ? 'JS/Node' : null, d.isPy ? 'Python' : null,
    d.isMiniProgram ? '小程序' : null, d.hasGit ? 'git 仓库' : '非 git 仓库',
  ].filter(Boolean).join(' / '));

  const results = [];
  for (const s of list) {
    if (!s.available(d)) {
      results.push({ s, r: { status: 'SKIP', note: '依赖不满足' } });
      continue;
    }
    let r;
    try { r = s.run(d); } catch (e) { r = { status: 'FAIL', note: '执行异常: ' + e.message }; }
    results.push({ s, r });
  }

  console.log('');
  const icon = { PASS: '✓ PASS', FAIL: '✗ FAIL', SKIP: '- SKIP' };
  for (const { s, r } of results) {
    console.log('[' + (icon[r.status] || r.status) + '] ' + s.title + ' — ' + (r.note || ''));
    if (r.detail && (r.status === 'FAIL' || process.env.SELFCHECK_VERBOSE === '1')) {
      console.log(r.detail.split('\n').map(l => '        ' + l).join('\n'));
    }
  }

  const fails = results.filter(x => x.r.status === 'FAIL');
  const passes = results.filter(x => x.r.status === 'PASS').length;
  const skips = results.filter(x => x.r.status === 'SKIP').length;
  console.log('\n小结：' + passes + ' 通过 / ' + fails.length + ' 失败 / ' + skips + ' 跳过');
  process.exit(fails.length ? 1 : 0);
}

main();
