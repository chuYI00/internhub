/**
 * 书签版采集器（采集书签.txt）自测：书签是"免装扩展"的兜底方案，必须保证能跑通。
 * 做法：把 javascript: 前缀去掉后在打桩 DOM 里执行，捕获下载的 CSV 内容。
 * 运行： node tests/bookmarklet_test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dom = require('./lib/dom_stub.js');
const { El, makeDocument } = dom;

const FILE = process.argv[2] || path.join(__dirname, '..', '采集书签.txt');
let code = fs.readFileSync(FILE, 'utf8').trim();
if (!code.startsWith('javascript:')) {
  console.error('✗ 文件不是 javascript: 书签');
  process.exit(1);
}
code = code.slice('javascript:'.length);

/* 构造一个含岗位表格的页面 */
const root = new El('body');
root.appendChild(dom.table(
  ['序号', '岗位名称', '公司名称', '工作地点', '学历要求', '薪资待遇', '投递链接', '报名截止'],
  [
    ['1', '数据分析工程师', '云南机场集团', '昆明', '本科及以上', '8-12万/年', { text: '投递', url: 'https://x.com/a' }, '2026-11-30'],
    ['2', '新媒体运营专员', '云南中烟', '大理', '本科', '7-10万/年', { text: '投递', url: 'https://x.com/b' }, '2026-11-20'],
    ['3', '信息化管理岗', '广投集团', '昆明', '硕士', '10-15万/年', { text: '投递', url: 'https://x.com/c' }, '2026-12-05'],
  ]));

const sandbox = {
  console,
  setTimeout, clearTimeout,
  confirm: () => true,
  alert: m => { sandbox.__alert = m; },
  location: { hostname: 'job.example.edu.cn', href: 'https://job.example.edu.cn/list' },
  getComputedStyle: () => ({ overflowY: 'visible' }),
  Blob: class { constructor(parts, opt) { this.parts = parts; this.type = opt && opt.type; } },
  URL: {
    createObjectURL: b => { sandbox.__csv = b.parts.join(''); return 'blob:x'; },
    revokeObjectURL: () => {},
  },
};
sandbox.window = sandbox;
sandbox.document = makeDocument(root);
sandbox.window.addEventListener = () => {};

let pass = 0, fail = 0;
const check = (n, c, extra) => {
  if (c) { pass++; console.log('  ✓ ' + n); } else { fail++; console.log('  ✗ ' + n + (extra ? ' -> ' + extra : '')); }
};

try {
  vm.runInContext(code, vm.createContext(sandbox), { filename: 'bookmarklet' });
} catch (e) {
  console.log('  ✗ 执行抛异常: ' + e.message);
  fail++;
}

setTimeout(() => {
  const csv = sandbox.__csv || '';
  console.log('[书签版采集器]');
  check('未弹出"没识别到数据"', !sandbox.__alert, sandbox.__alert);
  check('产生了 CSV', csv.length > 0);
  check('CSV 含 BOM', csv.charCodeAt(0) === 0xFEFF);
  check('导出 3 条岗位', csv.split('\r\n').length === 4, csv.split('\r\n').length);
  check('含岗位名', csv.includes('数据分析工程师'));
  check('含公司名', csv.includes('云南机场集团'));
  check('含城市', csv.includes('大理'));
  check('含薪资列值', csv.includes('10-15万/年'));
  check('含链接', csv.includes('https://x.com/b'));
  check('含截止日期', csv.includes('2026-11-30'));
  check('未识别列(序号)进描述', /序号：1/.test(csv));
  console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
}, 2500);
