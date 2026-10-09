#!/usr/bin/env node
/**
 * ci/ocr_gate.cjs —— Open Code Review(MR diff) 结果闸门
 *
 * 设计（对应流水线第2阶段「ai-code-review」的合并策略）：
 *   - 仅 critical / high 阻断合并（退出码 1，流水线失败 → MR 禁止合并）
 *   - medium / low 仅打印提示，不阻断（退出码 0）
 *   - 拿不到审查结果（OCR 基础设施故障 / LLM 抽风 / 网络 402）默认不冻结合并；
 *     若团队要求“审查必须成功否则也阻断”，设环境变量 OCR_INFRA_FAILS_PIPELINE=true
 *
 * 用法： node ci/ocr_gate.cjs <ocr_review.json>
 */
const fs = require('fs');

const file = process.argv[2] || 'ocr_review.json';

function bye(msg, code) { console.error(msg); process.exit(code); }

let raw;
try {
  raw = fs.readFileSync(file, 'utf8');
} catch (e) {
  console.warn('[ocr_gate] 未找到审查结果文件 ' + file + '（视为 OCR 基础设施故障）');
  bye('[ocr_gate] INFRA_ERROR', process.env.OCR_INFRA_FAILS_PIPELINE === 'true' ? 1 : 0);
}

let data;
try {
  data = JSON.parse(raw);
} catch (e) {
  console.warn('[ocr_gate] 审查结果 JSON 解析失败: ' + e.message);
  bye('[ocr_gate] INFRA_ERROR', process.env.OCR_INFRA_FAILS_PIPELINE === 'true' ? 1 : 0);
}

// 兼容 ocr 两种输出结构：scan 用 comments，review 用 results（有的版本是 results）
const items = data.comments || data.results || (Array.isArray(data) ? data : []);
const norm = items.filter(function (x) { return x && typeof x === 'object'; });

const BLOCK = ['critical', 'high'];
const block = norm.filter(function (x) { return BLOCK.indexOf((x.severity || '').toLowerCase()) >= 0; });
const warn = norm.filter(function (x) { return BLOCK.indexOf((x.severity || '').toLowerCase()) < 0; });

console.log('[ocr_gate] 总发现 ' + norm.length + ' 条 | 阻断级(critical/high) ' + block.length + ' | 提示级 ' + warn.length);

if (block.length) {
  block.slice(0, 30).forEach(function (c) {
    console.log('  🚫 ' + (c.severity || '?').toUpperCase() + '  ' + (c.path || '?') + ':' + (c.start_line || '?') + '  ' + String(c.content || '').slice(0, 140));
  });
  bye('[ocr_gate] 存在 ' + block.length + ' 条 critical/high 告警，合并被阻断。', 1);
}

if (warn.length) {
  warn.slice(0, 30).forEach(function (c) {
    console.log('  ℹ️  ' + (c.severity || '?').toUpperCase() + '  ' + (c.path || '?') + ':' + (c.start_line || '?') + '  ' + String(c.content || '').slice(0, 140));
  });
}

console.log('[ocr_gate] 无 critical/high，合并放行（中低告警见上，不阻断）。');
process.exit(0);
