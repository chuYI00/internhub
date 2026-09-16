/**
 * 采集助手（采集助手.user.js）自测：用极简 DOM 打桩，验证
 *  1) 标准 HTML <table> 岗位表 → 正确按表头映射成 InternHub CSV
 *  2) 飞书式 [role=grid] 多维表格 → 正确解析
 *  3) 岗位卡片列表 → 仍然可用（回归）
 * 运行： node tests/collector_dom_test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const { El, makeDocument, table, grid, cards } = require('./lib/dom_stub.js');

const NAME = process.argv[2] || path.join(__dirname, '..', '采集助手.user.js');
const code = fs.readFileSync(NAME, 'utf8');

function run(root) {
  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    setInterval: () => 0,
    clearInterval: () => {},
    confirm: () => true,
    alert: msg => { sandbox.__alert = msg; },
    location: { hostname: 'job.example.edu.cn', href: 'https://job.example.edu.cn/list' },
    getComputedStyle: () => ({ overflowY: 'visible' }),
    Blob: class { constructor(parts) { this.parts = parts; } },
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} },
  };
  sandbox.window = sandbox;
  sandbox.document = makeDocument(root);
  sandbox.window.addEventListener = () => {};
  vm.runInContext(code, vm.createContext(sandbox), { filename: NAME });
  return sandbox.window.__IHUB_COLLECTOR__;
}

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + (extra ? '  -> ' + extra : '')); }
}

/* ---- 用例 1：标准 HTML 岗位表 ---- */
console.log('[1] 标准 HTML 岗位表（含链接列 / 未识别列兜底）');
{
  const root = new El('body');
  root.appendChild(table(
    ['序号', '招聘岗位', '用人单位', '工作地点', '学历要求', '薪资待遇', '报名链接', '截止时间', '备注'],
    [
      ['1', '数据分析工程师', '云南机场集团', '昆明', '本科及以上', '8-12万/年', { text: '查看', url: 'https://x.com/a' }, '2026-11-30', '五险一金'],
      ['2', '新媒体运营专员', '云南中烟', '大理', '本科', '7-10万/年', { text: '查看', url: 'https://x.com/b' }, '2026-11-20', '党员优先'],
      ['3', '信息化管理岗', '广投集团', '昆明', '硕士', '10-15万/年', { text: '查看', url: 'https://x.com/c' }, '2026-12-05', ''],
    ]));
  const api = run(root);
  const g = api.readGrid();
  check('识别到表格 3 行', g && g.rows.length === 3, g && g.rows.length);
  const rows = api.rowsFromGrid(g);
  check('解析出 3 条岗位', rows.length === 3, rows.length);
  check('岗位名正确', rows[0].title === '数据分析工程师', rows[0].title);
  check('单位正确', rows[0].company === '云南机场集团', rows[0].company);
  check('城市正确', rows[0].city === '昆明', rows[0].city);
  check('学历正确', rows[0].degree === '本科及以上', rows[0].degree);
  check('薪资正确', rows[0].salary === '8-12万/年', rows[0].salary);
  check('截止日期正确', rows[0].deadline === '2026-11-30', rows[0].deadline);
  check('链接正确', rows[0].link === 'https://x.com/a', rows[0].link);
  check('未识别列进描述', /序号：1/.test(rows[0].text), rows[0].text);
  const csv = api.csv(rows);
  check('CSV 含 BOM', csv.charCodeAt(0) === 0xFEFF);
  check('CSV 表头含 薪资', csv.split('\r\n')[0].includes('薪资'));
  check('CSV 行数 = 表头 + 3', csv.split('\r\n').length === 4, csv.split('\r\n').length);
  check('CSV 引号已转义且字段数正确', csv.split('\r\n')[1].split('","').length === 12,
    csv.split('\r\n')[1].split('","').length);
}

/* ---- 用例 2：飞书式多维表格 ---- */
console.log('[2] 飞书式多维表格 [role=grid]');
{
  const root = new El('body');
  root.appendChild(grid(
    ['岗位名称', '公司', '城市', '学历', '投递链接'],
    [
      ['数据采集工程师', '某科技公司', '昆明', '本科', 'https://a.com/1'],
      ['AI 产品经理', '某互联网公司', '大理', '硕士', 'https://a.com/2'],
    ]));
  const api = run(root);
  const g = api.readGrid();
  check('识别到网格 2 行', g && g.rows.length === 2, g && g.rows.length);
  const rows = api.rowsFromGrid(g);
  check('解析出 2 条', rows.length === 2, rows.length);
  check('岗位名正确', rows[0].title === '数据采集工程师', rows[0].title);
  check('纯文本 URL 被识别为链接', rows[0].link === 'https://a.com/1', rows[0].link);
  check('城市正确', rows[1].city === '大理', rows[1].city);
}

/* ---- 用例 3：岗位卡片（回归） ---- */
console.log('[3] 岗位卡片列表（回归）');
{
  const root = new El('body');
  root.appendChild(cards([
    ['昆明数据分析工程师招聘', '云南某集团', 'https://j.com/1', '昆明 本科'],
    ['大理新媒体运营专员招聘', '某文旅公司', 'https://j.com/2', '大理 本科'],
  ]));
  const api = run(root);
  const rows = api.rowsFromCards();
  check('识别到 2 条卡片', rows.length === 2, rows.length);
  check('标题正确', rows[0].title === '昆明数据分析工程师招聘', rows[0].title);
  check('链接正确', rows[0].link === 'https://j.com/1', rows[0].link);
}

/* ---- 用例 4：无表头的中文表（只有 td，无 th） ---- */
console.log('[4] 无表头 / 岗位列名不标准（兜底取最长文本列）');
{
  const root = new El('body');
  root.appendChild(table(
    ['类别', '内容', '地区'],
    [
      ['招聘', '云南机场集团 2027 届校园招聘公告（含数据、运营、职能岗）', '昆明'],
      ['招聘', '云南中烟工业有限责任公司 2027 届高校毕业生招聘公告', '云南'],
      ['宣讲', '中国民航大学 2027 届秋季双选会通知（昆明专场）', '昆明'],
    ]));
  const api = run(root);
  const g = api.readGrid();
  const rows = api.rowsFromGrid(g);
  check('兜底解析出 3 条', rows.length === 3, rows.length);
  check('用最长文本列当岗位名', /云南机场集团/.test(rows[0].title), rows[0].title);
  check('城市识别正确', rows[0].city === '昆明', rows[0].city);
}

/* ---- 用例 5：飞书式多维表格（class 名完全是随机的，只能靠"重复行"结构兜底） ---- */
console.log('[5] 飞书式多维表格：随机 class 名 + 左侧勾选列 + 无 role 属性');
{
  function cell(text) {                       // 飞书单元格：div > div > span 文字
    const c = new El('div'); c.setAttribute('class', 'ud__cell__' + Math.random().toString(36).slice(2, 8));
    const inner = new El('div'); inner.setAttribute('class', 'cell-content');
    const sp = new El('span'); sp.appendText(String(text));
    inner.appendChild(sp); c.appendChild(inner);
    return c;
  }
  function row(vals) {
    const r = new El('div'); r.setAttribute('class', 'grid-row-x');
    const cb = new El('div'); cb.setAttribute('class', 'row-check');   // 勾选列（无文字）
    cb.appendChild(new El('input'));
    r.appendChild(cb);
    vals.forEach(v => r.appendChild(cell(v)));
    return r;
  }
  function feishuTable(headers, dataRows) {
    const box = new El('div'); box.setAttribute('class', 'bitable-grid-body-xyz');
    box.appendChild(row(headers));            // 表头行
    dataRows.forEach(d => box.appendChild(row(d)));
    return box;
  }
  const root = new El('body');
  root.appendChild(feishuTable(
    ['更新日期', '公司名称', '所属行业', '届别', '学历', '招聘类型', '备注', '可投岗位'],
    [
      ['2026/09/15', '东吴证券', '金融/银行/保险', '27届', '本科', '27届秋招', '尽快投递', '投行项目助理、债券承做'],
      ['2026/09/15', '能研院（上海成套院）', '能源/化工/环保', '27届', '本科', '27届秋招', '党员优先', '应届生到手岗、研发工程师'],
      ['2026/09/15', '爱慕股份', '快消/零售/消费', '27届', '本科', '27届秋招', '—', '产品企划、服装设计'],
      ['2026/09/15', '共创草坪', '农业/林业/其他', '27届', '本科', '27届秋招', '—', '营销类管培生、产品类'],
    ]));
  const api = run(root);
  const g = api.readGrid();
  check('兜底识别到网格', !!g, g && g.mode);
  check('识别方式标为"重复行结构(兜底)"', g && /兜底/.test(g.mode), g && g.mode);
  check('拿到 4 行数据', g && g.rows.length === 4, g && g.rows.length);
  const rows = api.rowsFromGrid(g);
  check('解析出 4 条岗位', rows.length === 4, rows.length);
  check('公司名正确', rows[0].company === '东吴证券', rows[0].company);
  check('岗位名取"可投岗位"列（模糊匹配）',
    /投行项目助理/.test(rows[0].title), rows[0].title);
  check('学历列正确', rows[0].degree === '本科', rows[0].degree);
  check('届别列正确', rows[0].batch === '27届', rows[0].batch);
  check('招聘类型列正确', rows[0].jobType === '27届秋招', rows[0].jobType);
  check('备注进标签', /尽快投递/.test(rows[0].tags), rows[0].tags);
}

/* ---- 用例 6：纯 canvas 渲染的表格要能"明确说抓不到"，而不是假成功 ---- */
console.log('[6] 诊断能力：canvas 表格应被识别为"抓不到"');
{
  const root = new El('body');
  const cv = new El('canvas');
  root.appendChild(cv);
  const api = run(root);
  const g = api.readGrid();
  check('canvas 页面不返回假表格', g === null, g && g.mode);
  check('诊断函数可调用且不抛错', (function () {
    try { api.diagnose(); return true; } catch (e) { return false; }
  })());
}

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail ? 1 : 0);
