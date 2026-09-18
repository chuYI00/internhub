# -*- coding: utf-8 -*-
"""网申自动填写助手 v3：根据个人资料生成本地用户脚本（Tampermonkey）+ 免装扩展的书签版。

设计原则（合规、安全）：
- 只在**你本人打开的网页**上工作，由你点按钮触发填写，**不登录、不提交、不绕过验证码、不联网**；
- 资料来自本机 data/profile.json（可叠加 data/resume_kit.json 的岗位方向话术），
  也能在页面上就地补改（存在浏览器 localStorage / 油猴存储，不出本机）；
- 填充后逐个高亮，由你核对后再自己点提交。

v3 相比 v2 的变化：
1. **按岗位方向切换**：面板第一行多了「岗位方向」下拉，选完点填入，自我评价 / 技能 / 亮点
   会换成该方向的口径（9 套：万能通用 + 嵌入式 / IoT / AI / 自动化 / 测试运维 / 民航国企 / 产品 / 内容运营）。
2. **可见性判断修好了**：不再用"零尺寸"判隐藏（折叠区与无布局环境下会误杀整页字段），
   改成"有尺寸即视为可见，否则查 display/visibility 样式链"。
3. **单选组识别更准**：用共同祖先取"整组题目文字"，避免只拿到选项文字（"男"）而匹配不到"性别"。
4. **富文本判断更稳**：查 contenteditable 属性，不只依赖 el.isContentEditable。
5. 非 input/textarea/select 的自造控件不再走原生 value setter（避免 Illegal invocation）。
"""
import json
import os
import re

from . import config, profile as profile_mod

SCRIPT_NAME = "网申助手.user.js"
BOOKMARK_NAME = "网申书签.txt"

# 嵌入脚本的资料键（多出来的键也会一起带上，面板里能改）
try:
    from . import tailor as _tailor
    KEYS = list(_tailor.SCRIPT_KEYS)
except Exception:                                     # pragma: no cover - 兜底
    _tailor = None
    KEYS = [
        "name", "gender", "birth", "political", "nation", "idcard",
        "phone", "email", "wechat", "qq",
        "school", "college", "major", "degree", "edu_range", "enroll", "graduate_year",
        "gpa", "rank", "city", "hometown", "address", "postal",
        "english", "certificates", "scholarship",
        "intent", "expected_city", "expected_salary", "available",
        "self_eval", "highlights", "skills", "experiences", "reason",
        "emergency_name", "emergency_phone", "emergency_relation", "marital",
    ]

# v5 新增：国企 / 央国企网申的特色字段（原 40 类不够用，补齐到 70 类）
EXTRA_KEYS = [
    "height", "weight", "health", "rewards", "family",
    "obey_adjust", "exam_province", "household_type", "join_party", "relative",
    "computer_level", "mandarin", "training_mode", "schooling_length", "major_category",
    "source", "hobby", "student_cadre", "social_practice", "research",
    "thesis", "patent", "archive", "bank", "volunteer1",
    "cet4", "teacher", "emergency_addr", "spouse", "children",
    "specialty", "mentor", "research_area", "work_years", "cet6",
]
for _k in EXTRA_KEYS:
    if _k not in KEYS:
        KEYS.append(_k)

# 「基本不会错、但每次手填很烦」的默认值。用户资料里有的以资料为准，
# 面板里改过会存本机（override），不会写回 profile.json。
EXTRA_DEFAULTS = {
    "obey_adjust": "是",          # 是否服从调剂 —— 国企网申不勾基本等于弃权
    "health": "健康",
    "training_mode": "统招",
    "schooling_length": "四年",
    "degree_type": "学士",
    "relative": "否",             # 有无亲属在本单位工作
}


def _packs() -> dict:
    if _tailor is None:
        return {}
    try:
        return _tailor.packs()
    except Exception:
        return {}


_TEMPLATE = r"""// ==UserScript==
// @name         网申助手 v5（本地·本人使用）
// @namespace    internhub.local
// @version      5.0
// @description  在网申/校招表单页一键填入个人资料（70 类字段，含国企特色字段）；三级标签识别 + 字段学习（教一次终身认识）+ 填充报告；本人点击触发，不代登录、不代提交、不联网
// @match        *://*/*
// @match        file:///*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @run-at       document-idle
// ==/UserScript==
// 注意：这里故意声明 GM_* 权限而不是 @grant none。
// @grant none 时脚本会以"页面脚本"的方式注入，遇到政府/国企网站的严格内容安全策略(CSP)会被拦掉，
// 表现就是"页面上什么都没有"。声明 GM_* 后 Tampermonkey 在自己的沙箱里执行，不受页面 CSP 影响。
(function () {
  'use strict';

  var BASE = __PAYLOAD__;
  var PACKS = __PACKS__;
  var LS_KEY = 'ihub_profile_overrides_v1';
  var LS_DIR = 'ihub_autofill_dir_v1';

  /* ==================== 存储（优先油猴存储，退化为 localStorage） ==================== */
  var GM_OK = (typeof GM_getValue === 'function' && typeof GM_setValue === 'function');
  function storeGet(k) {
    try { if (GM_OK) return GM_getValue(k, null); } catch (e) {}
    try { return localStorage.getItem(k); } catch (e) {}
    return null;
  }
  function storeSet(k, v) {
    try { if (GM_OK) { GM_setValue(k, v); return true; } } catch (e) {}
    try { localStorage.setItem(k, v); return true; } catch (e) {}
    return false;
  }
  function storeDel(k) {
    try { if (typeof GM_deleteValue === 'function') { GM_deleteValue(k); return true; } } catch (e) {}
    try { localStorage.removeItem(k); return true; } catch (e) {}
    return false;
  }

  /* ==================== 资料 ==================== */
  function overrides() {
    try { return JSON.parse(storeGet(LS_KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function readOverrides() { return overrides(); }
  function setOverride(k, v) {
    var o = overrides();
    if (v) { o[k] = v; } else { delete o[k]; }
    storeSet(LS_KEY, JSON.stringify(o));
  }
  function clearOverrides() { storeDel(LS_KEY); }
  function getDir() {
    var d = storeGet(LS_DIR) || 'universal';
    return PACKS[d] ? d : 'universal';
  }
  function setDir(d) { storeSet(LS_DIR, d); }

  // 最终资料 = 内置 BASE ← 岗位方向包 PACKS[dir] ← 本机手动覆盖
  function P() {
    var out = {}, k;
    for (k in BASE) out[k] = BASE[k];
    var pk = PACKS[getDir()];
    if (pk) { for (k in pk) out[k] = pk[k]; }
    /* 多档数据：同一个字段按岗位方向取不同值（期望薪资 / 求职意向 / 到岗时间） */
    var rv = ROLE_VALS, d = getDir();
    for (k in rv) {
      var byRole = rv[k] || {};
      var v = byRole[d];
      if (v === undefined || v === '') v = byRole.universal;
      // 只在资料里没值时才补 —— 你手填过的东西绝不被"方向默认值"悄悄改掉
      if (v && !out[k]) out[k] = v;
    }
    var ov = overrides();
    for (k in ov) out[k] = ov[k];
    return out;
  }
  /* 明确点一下才用「本方向的值」覆盖（求职意向 / 期望薪资 / 到岗时间） */
  function applyRoleDefaults() {
    var rv = ROLE_VALS, d = getDir(), n = 0;
    for (var k in rv) {
      var v = (rv[k] || {})[d];
      if (v === undefined || v === '') v = (rv[k] || {}).universal;
      if (v) { setOverride(k, v); n++; }
    }
    return n;
  }

  /* ==================== 字段字典 ==================== */
  // keys 里不要放"城市""时间"这种会跟别的字段打架的短词；匹配时取"命中关键词最长"的那个字段
  var FIELDS = [
    { k: 'name',      label: '姓名',     keys: ['姓名', '真实姓名', '中文姓名', 'name', 'fullname'] },
    { k: 'gender',    label: '性别',     keys: ['性别', 'gender', 'sex'] },
    { k: 'birth',     label: '出生日期', keys: ['出生日期', '出生年月', '生日', 'birthday', 'birth'] },
    { k: 'political', label: '政治面貌', keys: ['政治面貌', 'party'] },
    { k: 'nation',    label: '民族',     keys: ['民族', 'nation', 'ethnic'] },
    { k: 'idcard',    label: '身份证号', keys: ['身份证号', '身份证件号', '身份证', 'idcard', 'idnumber'] },
    { k: 'phone',     label: '手机号',   keys: ['手机号', '手机号码', '联系电话', '联系方式', '手机', '电话', 'phone', 'mobile', 'tel'] },
    { k: 'email',     label: '邮箱',     keys: ['电子邮箱', '邮箱', '邮件', 'email', 'mail'] },
    { k: 'wechat',    label: '微信',     keys: ['微信号', '微信', 'wechat', 'weixin'] },
    { k: 'qq',        label: 'QQ',       keys: ['qq号', 'qq号码', 'qq'] },
    { k: 'school',    label: '毕业院校', keys: ['毕业院校', '毕业学校', '就读院校', '学校名称', '所在院校', '院校', '学校', 'school', 'university'] },
    { k: 'college',   label: '学院',     keys: ['学院', '院系', '系别', '所在学院', 'college', 'department', 'faculty'] },
    { k: 'major',     label: '专业',     keys: ['所学专业', '专业名称', '就读专业', '专业', 'major'] },
    { k: 'degree',    label: '学历',     keys: ['学历', '学位', '最高学历', 'degree', 'education'] },
    { k: 'edu_range', label: '就读时间', keys: ['在校时间', '就读时间', '起止时间', '就读起止', '教育起止'] },
    { k: 'enroll',    label: '入学时间', keys: ['入学时间', '入学年月', '入学年份', 'enrollment'] },
    { k: 'graduate_year', label: '毕业时间', keys: ['毕业时间', '毕业年月', '毕业年份', '预计毕业', 'graduation', 'graduate'] },
    { k: 'gpa',       label: 'GPA',      keys: ['gpa', '绩点', '平均分', '平均成绩'] },
    { k: 'rank',      label: '专业排名', keys: ['专业排名', '年级排名', '排名', 'rank'] },
    { k: 'city',      label: '现居地',   keys: ['现居住地', '现居地', '目前居住', '居住城市', '所在地', '当前城市', '现居', 'currentcity'] },
    { k: 'hometown',  label: '籍贯',     keys: ['籍贯', '生源地', '户籍所在地', '户籍地', '户口所在地', 'hometown', 'nativeplace'] },
    { k: 'address',   label: '通讯地址', keys: ['通讯地址', '联系地址', '邮寄地址', '详细地址', '家庭住址', 'address'] },
    { k: 'postal',    label: '邮编',     keys: ['邮编', '邮政编码', 'postal', 'zip'] },
    { k: 'english',   label: '外语水平', keys: ['外语水平', '英语水平', '英语等级', '四六级', 'cet', 'englishlevel'] },
    { k: 'certificates', label: '证书',  keys: ['证书', '资格证书', '职业资格', '资格证', 'certificate'] },
    { k: 'scholarship', label: '奖学金/荣誉', keys: ['奖学金', '获奖情况', '荣誉', '奖励', 'scholarship', 'award', 'honor'] },
    { k: 'intent',    label: '求职意向', keys: ['求职意向', '应聘岗位', '意向岗位', '期望职位', '申请职位', '目标岗位', '求职方向'] },
    { k: 'expected_city', label: '期望城市', keys: ['期望工作城市', '期望城市', '意向城市', '期望工作地', '工作城市', 'preferredcity'] },
    { k: 'expected_salary', label: '期望薪资', keys: ['期望薪资', '期望月薪', '薪资要求', '期望年薪'] },
    { k: 'available', label: '到岗时间', keys: ['到岗时间', '最快到岗', '可实习时间', '实习时长', '可到岗'] },
    { k: 'self_eval', label: '自我评价', keys: ['自我评价', '自我介绍', '个人评价', '个人简介', '个人优势', 'selfevaluation', 'aboutme'] },
    { k: 'experiences', label: '项目/实习经历', keys: ['项目经历', '实习经历', '工作经历', '实践经历', '项目经验', 'experience'] },
    { k: 'skills',    label: '技能特长', keys: ['技能', '专业技能', '特长', '擅长', 'skill'] },
    { k: 'specialty', label: '文体特长', keys: ['文体特长', '个人特长', '运动特长', '体育特长', 'specialty'] },
    { k: 'highlights', label: '个人亮点', keys: ['个人亮点', '主要成绩', '优势亮点', 'highlight'] },
    { k: 'reason',    label: '申请理由', keys: ['申请理由', '求职信', '自荐信', '申请说明', 'coverletter'] },
    { k: 'emergency_name', label: '紧急联系人', keys: ['紧急联系人', '紧急联络人', '联系人姓名', 'emergencyname'] },
    { k: 'emergency_phone', label: '紧急联系人电话', keys: ['紧急联系人电话', '紧急联系电话', '联系人电话', 'emergencyphone'] },
    { k: 'emergency_relation', label: '与本人关系', keys: ['与本人关系', '联系人与本人关系', '关系', 'relation'] },
    { k: 'emergency_addr', label: '紧急联系人地址', keys: ['紧急联系人地址', '紧急联系人通讯地址', '联系人地址', 'emergencyaddress'] },
    { k: 'marital',   label: '婚姻状况', keys: ['婚姻状况', '婚否', 'marital'] },
    { k: 'spouse',    label: '配偶信息', keys: ['配偶姓名', '配偶情况', '配偶', 'spouse'] },
    { k: 'children',  label: '子女情况', keys: ['子女情况', '子女', '生育情况', 'children'] },
    /* ---- v5 新增：国企 / 央国企网申特色字段 ---- */
    { k: 'height',    label: '身高',     keys: ['身高', 'height'] },
    { k: 'weight',    label: '体重',     keys: ['体重', 'weight'] },
    { k: 'health',    label: '健康状况', keys: ['健康状况', '身体状况', '健康情况', '健康', 'health'] },
    { k: 'rewards',   label: '奖惩情况', keys: ['奖惩情况', '奖惩', '所受处分', '处分情况', '处分'] },
    { k: 'family',    label: '家庭成员', keys: ['家庭主要成员', '主要家庭成员', '家庭成员', '家属信息', '直系亲属', 'family'] },
    { k: 'obey_adjust', label: '是否服从调剂', keys: ['是否服从调剂', '服从调剂', '是否接受调剂', '是否服从分配', '接受调配', '是否接受调配'] },
    { k: 'exam_province', label: '高考省份', keys: ['高考省份', '高考所在地', '高考生源地', '生源地省份'] },
    { k: 'household_type', label: '户口性质', keys: ['户口性质', '户籍性质', '农业非农业', '户口类别'] },
    { k: 'join_party', label: '入党/入团时间', keys: ['入党时间', '入党日期', '入党年月', '入团时间', '政治面貌时间'] },
    { k: 'relative',  label: '亲属是否在本单位', keys: ['是否有亲属在本单位', '亲属在本单位', '有无亲属', '是否有亲属'] },
    { k: 'computer_level', label: '计算机等级', keys: ['计算机等级', '计算机水平', '全国计算机', '计算机证书'] },
    { k: 'cet4',      label: '英语四级成绩', keys: ['四级成绩', '英语四级', 'cet4', 'cet-4'] },
    { k: 'mandarin',  label: '普通话水平', keys: ['普通话水平', '普通话等级', '普通话'] },
    { k: 'training_mode', label: '培养方式', keys: ['培养方式', '统招', '定向'] },
    { k: 'schooling_length', label: '学制', keys: ['学制', '学习年限'] },
    { k: 'degree_type', label: '学位',    keys: ['学位', '学士学位', '授予学位'] },
    { k: 'major_category', label: '专业类别', keys: ['专业类别', '学科门类', '专业大类', '专业门类'] },
    { k: 'source',    label: '信息来源', keys: ['信息来源', '从何处了解', '了解渠道', '招聘信息来源', '获知渠道'] },
    { k: 'hobby',     label: '兴趣爱好', keys: ['兴趣爱好', '个人爱好', '特长爱好', 'hobby'] },
    { k: 'student_cadre', label: '学生干部', keys: ['学生干部', '是否担任学生干部', '担任职务', '班干部', '校内职务'] },
    { k: 'social_practice', label: '社会实践', keys: ['社会实践', '社会活动', '实践活动'] },
    { k: 'research',  label: '研究方向', keys: ['研究方向', '研究内容', 'research'] },
    { k: 'thesis',    label: '论文',     keys: ['毕业论文', '发表论文', '论文情况', '论文'] },
    { k: 'patent',    label: '专利',     keys: ['专利情况', '发明专利', '专利'] },
    { k: 'archive',   label: '档案所在地', keys: ['档案所在地', '档案地址', '档案存放', '档案接收'] },
    { k: 'bank',      label: '银行卡号', keys: ['银行卡号', '银行卡', '开户行', '工资卡'] },
    { k: 'volunteer1', label: '第一志愿', keys: ['第一志愿', '第一意向', '志愿岗位', '报考志愿'] },
    { k: 'teacher',   label: '辅导员/导师', keys: ['辅导员', '班主任', '指导教师', '导师姓名'] }
  ];

  /* 面板里按组展示（70 个字段平铺会看花眼） */
  var GROUPS = [
    { g: 'base',    name: '基本信息' },
    { g: 'edu',     name: '教育背景' },
    { g: 'contact', name: '联系方式' },
    { g: 'job',     name: '求职意向' },
    { g: 'family',  name: '家庭与紧急联系人' },
    { g: 'other',   name: '其他（奖惩 / 证书 / 附加）' }
  ];
  var GROUP_OF = {
    name: 'base', gender: 'base', birth: 'base', political: 'base', nation: 'base',
    idcard: 'base', marital: 'base', height: 'base', weight: 'base', health: 'base',
    household_type: 'base', hobby: 'base', source: 'base',
    school: 'edu', college: 'edu', major: 'edu', major_category: 'edu', degree: 'edu',
    degree_type: 'edu', edu_range: 'edu', enroll: 'edu', graduate_year: 'edu',
    gpa: 'edu', rank: 'edu', training_mode: 'edu', schooling_length: 'edu',
    student_cadre: 'edu', research: 'edu', thesis: 'edu', patent: 'edu', teacher: 'edu',
    phone: 'contact', email: 'contact', wechat: 'contact', qq: 'contact',
    city: 'contact', hometown: 'contact', address: 'contact', postal: 'contact',
    exam_province: 'contact', archive: 'contact', bank: 'contact',
    intent: 'job', expected_city: 'job', expected_salary: 'job', available: 'job',
    self_eval: 'job', highlights: 'job', skills: 'job', experiences: 'job',
    reason: 'job', volunteer1: 'job', obey_adjust: 'job', social_practice: 'job',
    emergency_name: 'family', emergency_phone: 'family', emergency_relation: 'family',
    emergency_addr: 'family', family: 'family', spouse: 'family', children: 'family',
    relative: 'family',
    english: 'other', cet4: 'other', computer_level: 'other', mandarin: 'other',
    certificates: 'other', scholarship: 'other', rewards: 'other', join_party: 'other'
  };
  FIELDS.forEach(function (f) { f.g = GROUP_OF[f.k] || 'other'; });

  /* 多档数据：同一个字段，不同岗位方向填不同的值（技术岗 / 央国企岗口径不一样）
     ⚠️ 这里的 key 必须跟 ihub/tailor.py 的 ORDER 对齐（换一套方向时两边一起改，
        不然「多档数据」会悄悄失效——panel 上选了方向却取不到值，只会拿 universal 兜底）。 */
  var ROLE_VALS = {
    expected_salary: {
      universal: '6000-8000', iotembed: '7000-9000', ee: '7000-9000',
      aiapp: '8000-10000', soe: '5000-7000',
      mfg: '6500-8500', test: '6000-8000', ops: '6000-8000', trainee: '6000-8000'
    },
    intent: {
      universal: '物联网 / 嵌入式 · 电子信息与电气自动化 · AI 应用相关技术岗',
      iotembed: '物联网嵌入式开发 / 嵌入式软件',
      ee: '电子工程师 / 硬件工程师 / 电气自动化',
      aiapp: 'AI 应用开发 / 智能化系统集成',
      soe: '国企信息化运维 / 生产设备技术支持 / 机电电气技术岗',
      mfg: '智能制造 / 自动化设备 / 产线集成调试',
      test: '测试工程师 / 嵌入式硬件测试',
      ops: '技术支持工程师 / IT 运维 / 现场实施',
      trainee: '技术类管培生 / 综合技术培训生'
    },
    available: {
      universal: '随时可到岗', iotembed: '随时可到岗', ee: '随时可到岗',
      aiapp: '随时可到岗', soe: '毕业后可即刻到岗，服从单位安排',
      mfg: '随时可到岗', test: '随时可到岗', ops: '随时可到岗', trainee: '随时可到岗'
    }
  };

  /* ==================== 工具 ==================== */
  function norm(s) { return String(s == null ? '' : s).replace(/[\s\u3000*＊:：?？()（）、,，.。/|]/g, '').toLowerCase(); }
  function visText(el) { return String((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim(); }
  function isVisible(el) {
    if (!el) return true;
    try { if (el.hidden) return false; } catch (e) {}
    // 1) 有实际尺寸 → 可见
    try {
      var r = el.getBoundingClientRect && el.getBoundingClientRect();
      if (r && r.width > 0 && r.height > 0) return true;
    } catch (e) {}
    // 2) 尺寸为 0（折叠区 / 隐藏域 / 无布局环境）→ 再看样式链：
    //    只有真的 display:none / visibility:hidden / opacity:0 才当成不可见，
    //    避免"整页零尺寸"的环境（含测试打桩 DOM）下把表单全部跳过。
    var n = el, depth = 0, view = el.ownerDocument && el.ownerDocument.defaultView;
    while (n && n.nodeType === 1 && depth < 8) {
      try {
        var cs = view && view.getComputedStyle ? view.getComputedStyle(n) : null;
        if (cs) {
          if (cs.display === 'none' || cs.visibility === 'hidden') return false;
          if (cs.opacity === '0') return false;
        }
      } catch (e) {}
      n = n.parentElement; depth++;
    }
    return true;
  }
  function controlCount(node) {
    if (!node || !node.querySelectorAll) return 0;
    try { return node.querySelectorAll('input,textarea,select,[contenteditable="true"]').length; } catch (e) { return 0; }
  }
  function attr(el, n) { try { return el.getAttribute ? el.getAttribute(n) : null; } catch (e) { return null; } }

  /* ==================== 标签识别（v1 的坑就在这） ==================== */
  function labelOf(el, doc) {
    var parts = [];
    function push(v) { if (v) parts.push(String(v)); }

    push(attr(el, 'aria-label'));
    var lb = attr(el, 'aria-labelledby');
    if (lb && doc.getElementById) {
      lb.split(/\s+/).forEach(function (id) {
        var n = doc.getElementById(id);
        if (n) push(visText(n));
      });
    }
    push(attr(el, 'placeholder'));
    push(attr(el, 'title'));
    push(attr(el, 'data-label'));
    push(attr(el, 'data-field'));
    push(attr(el, 'data-name'));
    push(attr(el, 'name'));

    if (el.id && doc.querySelector) {
      var forLab = null;
      try { forLab = doc.querySelector('label[for="' + String(el.id).replace(/"/g, '\\"') + '"]'); } catch (e) {}
      if (forLab) push(visText(forLab));
    }
    var wrapLab = el.closest ? el.closest('label') : null;
    if (wrapLab) push(visText(wrapLab));

    // 逐级向上：只采信"控件数 ≤2 的小容器"里的文字（避免把整个表单当字段名）
    var n = el.parentElement, depth = 0;
    while (n && depth < 4) {
      if (controlCount(n) <= 2) {
        var t = visText(n);
        if (t && t.length <= 40) { push(t); break; }
        if (t) break;
      }
      n = n.parentElement; depth++;
    }

    // 前面的兄弟文本：<span>姓名</span><input>
    var sib = el.previousElementSibling, hop = 0;
    while (sib && hop < 3) {
      if (controlCount(sib) === 0) {
        var st = visText(sib);
        if (st && st.length <= 20) push(st);
        break;
      }
      sib = sib.previousElementSibling; hop++;
    }

    // 老式表格：<td>姓名</td><td><input></td>
    var td = el.closest ? el.closest('td') : null;
    if (td && td.previousElementSibling) push(visText(td.previousElementSibling));

    return parts.filter(Boolean).join(' | ');
  }

  // 单选组：第一项的 labelOf 往往只拿到选项文字（"男"），还要向上取"整组的题目文字"
  function commonAncestor(nodes) {
    if (!nodes || !nodes.length) return null;
    var a = nodes[0];
    while (a && a.nodeType === 1) {
      var all = true;
      for (var i = 1; i < nodes.length; i++) {
        if (!(a.contains && a.contains(nodes[i]))) { all = false; break; }
      }
      if (all) return a;
      a = a.parentElement;
    }
    return null;
  }
  function groupLabel(group, doc) {
    var parts = [labelOf(group[0], doc)];
    if (group[0].name) parts.push(group[0].name);
    var anc = commonAncestor(group), depth = 0;
    while (anc && depth < 4) {
      var t = visText(anc);
      if (t && t.length <= 60) { parts.push(t); break; }
      anc = anc.parentElement; depth++;
    }
    return parts.filter(Boolean).join(' | ');
  }

  /* ==================== 字段学习（v5 核心：越用越聪明） ====================
     遇到没认出来的字段，你在面板里指定一次「这栏是身高」，
     之后**任何网站**再遇到同样叫法的栏目都会自动填。
     学习库存在本机（油猴存储优先），可导出/导入换电脑。                       */
  var LEARN_KEY = 'ihub_field_learn_v1';
  function learnMap() {
    try { return JSON.parse(storeGet(LEARN_KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function learnSave(m) { storeSet(LEARN_KEY, JSON.stringify(m || {})); }
  function learnAdd(label, fieldKey) {
    var k = norm(label);
    if (!k || !fieldKey) return false;
    var m = learnMap();
    m[k] = { k: fieldKey, ts: Date.now() };
    learnSave(m);
    return true;
  }
  function learnDel(label) {
    var m = learnMap();
    delete m[norm(label)];
    learnSave(m);
  }
  // 三级第 0 级：先查学习库（精确 → 特征包含 → 反包含）
  function learnLookup(label) {
    var L = norm(label);
    if (!L) return null;
    var m = learnMap(), k;
    if (m[L] && m[L].k) return m[L].k;
    for (k in m) {
      if (k.length >= 3 && L.indexOf(k) >= 0) return m[k].k;
      if (L.length >= 3 && k.indexOf(L) >= 0) return m[k].k;
    }
    return null;
  }
  function fieldByKey(k) {
    for (var i = 0; i < FIELDS.length; i++) { if (FIELDS[i].k === k) return FIELDS[i]; }
    return null;
  }

  /* 三级识别：
     L1 精确  norm(label) 与关键词完全相等          → 1000+
     L2 模糊  关键词是 label 的一部分                → 100+（取最长）
     L3 上下文 上面都没中，改从「分组标题 / 表头 / 前驱文本」再认一次 */
  function scoreField(f, L) {
    var best = 0;
    for (var j = 0; j < f.keys.length; j++) {
      var nk = norm(f.keys[j]);
      if (!nk || nk.length < 2) continue;
      var s = 0;
      if (L === nk) s = 1000 + nk.length * 10;
      else if (L.indexOf(nk) >= 0) s = 100 + nk.length * 10;
      else if (nk.length >= 3 && nk.indexOf(L) >= 0) s = 60 + L.length * 10;
      if (s > best) best = s;
    }
    return best;
  }
  function bestScored(L) {
    var best = null, bs = 0;
    for (var i = 0; i < FIELDS.length; i++) {
      var s = scoreField(FIELDS[i], L);
      if (s > bs) { bs = s; best = FIELDS[i]; }
    }
    return { f: best, s: bs };
  }
  // L3 上下文：fieldset legend / 表单项标题 / 表格行首列 / 前驱大标题
  function contextLabel(el, doc) {
    var parts = [];
    function add(v) {
      var t = String(v || '').trim();
      if (!t) return;
      for (var i = 0; i < parts.length; i++) { if (parts[i] === t) return; }  /* 去重 */
      parts.push(t);
    }
    try {
      var fs = el.closest ? el.closest('fieldset') : null;
      if (fs) { var lg = fs.querySelector ? fs.querySelector('legend') : null; if (lg) add(visText(lg)); }
      var th = el.closest ? el.closest('tr') : null;
      if (th) { var first = th.children ? th.children[0] : null; if (first && first !== el) add(visText(first)); }
    } catch (e) {}
    var n = el && el.parentElement, d = 0;
    while (n && d < 5) {
      var t = visText(n);
      if (t && t.length <= 60 && controlCount(n) <= 3) { add(t); break; }
      n = n.parentElement; d++;
    }
    return parts.join(' | ');
  }
  function bestField(label, el, doc) {
    var L = norm(label);
    var r = { f: null, s: 0 };
    if (L) {
      /* L0：学习库（用户教过的优先，且权重最高） */
      var lk = learnLookup(L);
      if (lk) { var lf = fieldByKey(lk); if (lf) return lf; }
      /* L1 精确 / L2 模糊 */
      r = bestScored(L);
      if (r.f && r.s >= 100) return r.f;
    }
    /* L3：上下文再试一次（裸输入框在「政治面貌」分组里、表格行首列当题目…） */
    if (el && doc) {
      var ctx = norm(contextLabel(el, doc));
      if (ctx && ctx !== L) {
        var lk2 = learnLookup(ctx);
        if (lk2) { var lf2 = fieldByKey(lk2); if (lf2) return lf2; }
        var r2 = bestScored(ctx);
        if (r2.f && r2.s >= 100) return r2.f;
      }
    }
    /* 都不中，但模糊分还算高（>=60，关键词包含 label）时也认 —— 例如 label 只有"邮箱"两字 */
    return (r.f && r.s >= 60) ? r.f : null;
  }

  /* ==================== 写值 ==================== */
  function fire(el) {
    ['input', 'change', 'blur'].forEach(function (t) {
      try { el.dispatchEvent(new Event(t, { bubbles: true })); } catch (e) {}
    });
  }
  function setNative(el, val) {
    var tag = el.tagName, proto = null;
    if (tag === 'TEXTAREA') proto = window.HTMLTextAreaElement && HTMLTextAreaElement.prototype;
    else if (tag === 'SELECT') proto = window.HTMLSelectElement && HTMLSelectElement.prototype;
    else if (tag === 'INPUT') proto = window.HTMLInputElement && HTMLInputElement.prototype;
    if (!proto) { try { el.value = val; } catch (e) {} fire(el); return; }   /* div 等自造控件 */
    var d = Object.getOwnPropertyDescriptor(proto, 'value');
    try { if (d && d.set) d.set.call(el, val); else el.value = val; }
    catch (e) { try { el.value = val; } catch (e2) {} }
    fire(el);
  }
  function mark(el, ok) {
    try { el.style.outline = ok ? '2px solid #1a7f37' : '2px solid #d97706'; el.style.outlineOffset = '1px'; } catch (e) {}
  }
  function looseMatch(want, text) {
    var w = norm(want), t = norm(text);
    if (!w || !t) return false;
    if (w === t) return true;
    if (w.indexOf(t) >= 0 || t.indexOf(w) >= 0) return true;
    if (w.length >= 2 && t.length >= 2 && w.slice(0, 2) === t.slice(0, 2)) return true;  /* 云南大理 ↔ 云南省 */
    return false;
  }
  /* 下拉选项同义词：资料里写「本科」，选项里只有「学士」—— 必须认成同一个 */
  var OPT_SYN = [
    ['本科', '学士', '大学本科', '大学', '本科及以上'],
    ['硕士', '研究生', '硕士研究生', '硕士研究生及以上'],
    ['博士', '博士研究生'],
    ['大专', '专科', '高职', '专科及以上'],
    ['共青团员', '团员', '共青团'],
    ['中共党员', '党员', '预备党员', '中共预备党员'],
    ['群众', '无党派人士', '无党派'],
    ['汉族', '汉'],
    ['男', '男性'], ['女', '女性'],
    ['未婚', '未'], ['已婚', '已'],
    ['是', '愿意', '同意', '接受', '服从', '有'],
    ['否', '不愿意', '不同意', '不接受', '不服从', '无']
  ];
  function synMatch(want, text) {
    var w = norm(want), t = norm(text);
    if (!w || !t) return false;
    for (var i = 0; i < OPT_SYN.length; i++) {
      var g = OPT_SYN[i], inW = false, inT = false, j;
      for (j = 0; j < g.length; j++) {
        if (g[j] === w) inW = true;
        if (g[j] === t) inT = true;
      }
      if (inW && inT) return true;
    }
    return false;
  }
  function fillSelect(el, val) {
    var opts = Array.prototype.slice.call(el.options || []);
    if (!opts.length) return false;
    var hit = null, i;
    for (i = 0; i < opts.length; i++) {   /* 1) 精确 */
      if (norm(opts[i].value) === norm(val) || norm(opts[i].textContent) === norm(val)) { hit = opts[i]; break; }
    }
    if (!hit) for (i = 0; i < opts.length; i++) {   /* 2) 互相包含 / 前两字相同 */
      if (looseMatch(val, opts[i].textContent) || looseMatch(val, opts[i].value)) { hit = opts[i]; break; }
    }
    if (!hit) for (i = 0; i < opts.length; i++) {   /* 3) 同义词：本科 ↔ 学士 */
      if (synMatch(val, opts[i].textContent) || synMatch(val, opts[i].value)) { hit = opts[i]; break; }
    }
    if (!hit) return false;
    try { el.value = hit.value; } catch (e) {}
    if (el.value !== hit.value) { hit.selected = true; }
    if (el.selectedIndex >= 0 && el.options[el.selectedIndex] &&
        norm(el.options[el.selectedIndex].textContent) !== norm(hit.textContent)) { hit.selected = true; }
    fire(el);
    return true;
  }
  function toYM(val, withDay) {
    var s = String(val || '');
    var ym = s.match(/(19|20)\d{2}[.\-\/年]?\s*(\d{1,2})?/);
    var y = (s.match(/(19|20)\d{2}/) || [])[0] || '';
    if (!y) return '';
    var mo = ym && ym[2] ? String(ym[2]).padStart(2, '0') : '';
    if (withDay && mo) return y + '-' + mo + '-01';
    if (withDay) return y + '-01-01';
    return mo ? y + '-' + mo : y + '-01';
  }
  function adapt(el, raw) {
    var t = String(attr(el, 'type') || 'text').toLowerCase(), s = String(raw == null ? '' : raw);
    if (el.tagName === 'SELECT') return s;
    if (t === 'date') return toYM(s, true);
    if (t === 'month') return toYM(s, false);
    if (t === 'number' || t === 'range') { var m = s.match(/-?\d+(\.\d+)?/); return m ? m[0] : ''; }
    if (t === 'tel') return s.replace(/[^\d+\-]/g, '');
    if (t === 'email') { var e = s.match(/[\w.+-]+@[\w-]+\.[\w.]+/); return e ? e[0] : s; }
    return s;
  }

  /* ==================== 主流程 ==================== */
  function isEditable(el) {
    try { if (el.isContentEditable) return true; } catch (e) {}
    return String(attr(el, 'contenteditable') || '').toLowerCase() === 'true';
  }
  function hasValue(el) {
    if (isEditable(el)) return visText(el).length > 0;
    if (el.tagName === 'SELECT') return el.selectedIndex > 0;
    return String(el.value == null ? '' : el.value).trim().length > 0;
  }
  function collect(doc) {
    var out = [];
    var list;
    try { list = doc.querySelectorAll('input,textarea,select,[contenteditable="true"]'); } catch (e) { return out; }
    Array.prototype.slice.call(list).forEach(function (el) {
      var t = String(attr(el, 'type') || 'text').toLowerCase();
      if (['hidden', 'file', 'submit', 'button', 'reset', 'image', 'password'].indexOf(t) >= 0) return;
      if (!isVisible(el)) return;
      // 面板自己的输入框不算表单字段（Shadow DOM 里其实扫不到，非 Shadow 的降级环境要挡一下）
      try { if (el.closest && el.closest('[data-ihub-panel]')) return; } catch (e) {}
      out.push(el);
    });
    return out;
  }

  // 「需人工」清单：填不进去的每一项都留着元素引用，面板里点一下就能滚过去
  function needHuman(failed, el, label, f, reason) {
    failed.push({
      el: el,
      label: String(label || '').slice(0, 40),
      key: f ? f.k : '',
      keyLabel: f ? f.label : '',
      reason: reason
    });
  }

  function fillCheckboxes(doc, prof, onlyEmpty, report, failed) {
    var n = 0, boxes;
    try { boxes = doc.querySelectorAll('input[type=checkbox]'); } catch (e) { return 0; }
    Array.prototype.slice.call(boxes).forEach(function (b) {
      if (!isVisible(b)) return;
      if (onlyEmpty && b.checked) return;
      var lab = labelOf(b, doc);
      var f = bestField(lab, b, doc);
      if (!f) return;
      var val = String(prof[f.k] || '').trim();
      if (!val) { needHuman(failed, b, lab, f, '资料里没有「' + f.label + '」的值'); return; }
      if (!/^(是|有|愿意|同意|接受|true|1|yes|y)$/i.test(val)) return;   /* "否"就不勾 */
      try {
        if (!b.checked) { b.checked = true; fire(b); }
        mark(b, true); n++;
        report.push(f.label + '→已勾选');
      } catch (e) {}
    });
    return n;
  }

  function fillRadios(doc, prof, onlyEmpty, report, failed) {
    var groups = {};
    var radios;
    try { radios = doc.querySelectorAll('input[type=radio]'); } catch (e) { return 0; }
    Array.prototype.slice.call(radios).forEach(function (r) {
      if (!isVisible(r)) return;
      var key = r.name || ('__g' + Array.prototype.indexOf.call(radios, r));
      (groups[key] = groups[key] || []).push(r);
    });
    var n = 0;
    Object.keys(groups).forEach(function (key) {
      var g = groups[key];
      if (onlyEmpty && g.some(function (r) { return r.checked; })) return;
      var _gl = groupLabel(g, doc);
      var f = bestField(_gl, g[0], doc);
      if (!f) { needHuman(failed, g[0], _gl, null, '没认出这是什么字段'); return; }
      var val = prof[f.k];
      if (!val) { needHuman(failed, g[0], _gl, f, '资料里没有「' + f.label + '」的值'); return; }
      var hit = g.filter(function (r) {
        var own = visText(r.closest && r.closest('label') ? r.closest('label') : r.parentElement);
        return norm(own) === norm(val) || looseMatch(val, own) || norm(r.value) === norm(val);
      })[0];
      if (!hit) { needHuman(failed, g[0], _gl, f, '选项里没有「' + val + '」（需手点）'); return; }
      try { hit.checked = true; fire(hit); mark(hit, true); n++; if (report) report.push(f.label + '→' + val); } catch (e) {}
    });
    return n;
  }

  /* ============ 自绘控件（ATS 专用） ============
     北森(hotjob)、Moka、飞书招聘、用友这些网申系统用的是 antd / element-ui 的自绘控件：
     下拉不是 <select> 而是 div + 弹出层，单选不是 <input type=radio> 而是卡片 div。
     光给它赋 value 无效 —— 必须真的"点开 → 点选项"。以下两个函数处理这一类。 */
  var OPTION_SEL = '.ant-select-item-option,[role=option],.el-select-dropdown__item,' +
    '.ivu-select-item,.van-picker-column__item,.ant-cascader-menu-item,.select-option,.dropdown-item';
  var FAKE_SEL_BOXES = '[role=combobox],.ant-select,.el-select,.ivu-select,.ant-cascader';

  // 自绘控件的容器文字 == 它当前的显示值（"请选择"），往上直接取容器文字会把
  // 显示值当题目。这里跳过"文字与控件本身相同"的祖先层，直到祖先里出现了更多文字。
  function boxLabel(b, doc) {
    var parts = [labelOf(b, doc)];
    var own = norm(visText(b));
    var n = b.parentElement, d = 0;
    while (n && d < 5) {
      var t = visText(n);
      if (t && t.length <= 80 && norm(t) !== own) { parts.push(t); break; }
      n = n.parentElement; d++;
    }
    return parts.filter(Boolean).join(' | ');
  }

  function clickOption(want, doc) {
    var opts;
    try { opts = doc.querySelectorAll(OPTION_SEL); } catch (e) { return false; }
    var hit = null;
    Array.prototype.slice.call(opts).forEach(function (o) {
      if (hit || !isVisible(o)) return;
      var t = visText(o);
      if (t && (norm(t) === norm(want) || looseMatch(want, t))) hit = o;
    });
    if (!hit) {
      Array.prototype.slice.call(opts).forEach(function (o) {
        if (hit || !isVisible(o)) return;
        var t = visText(o);
        if (t && synMatch(want, t)) hit = o;   /* 本科 ↔ 学士 */
      });
    }
    if (!hit) return false;
    try { hit.click(); return true; } catch (e) { return false; }
  }

  // 返回"尝试点开的下拉数"。选项是点开后才渲染的，所以用 setTimeout 错开去点。
  function fillFakeSelects(doc, prof, report) {
    var boxes;
    try { boxes = doc.querySelectorAll(FAKE_SEL_BOXES); } catch (e) { return 0; }
    var pending = [];
    Array.prototype.slice.call(boxes).forEach(function (b) {
      if (!isVisible(b)) return;
      // 外层内层都命中时只处理最外层（antd 结构：.ant-select > selector > input[role=combobox]）
      var anc = (b.parentElement && b.parentElement.closest) ? b.parentElement.closest(FAKE_SEL_BOXES) : null;
      if (anc) return;
      var f = bestField(boxLabel(b, doc));
      if (!f) return;
      var val = prof[f.k];
      if (!val) return;
      var shown = visText(b);
      if (shown && (norm(shown) === norm(val) || looseMatch(val, shown))) return;  // 已经是对的了
      pending.push([b, val, f]);
    });
    if (!pending.length) return 0;
    pending.forEach(function (p, i) {
      try {
        p[0].click();
        p[0].dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      } catch (e) {}
      setTimeout(function () {
        if (clickOption(p[1], doc)) {
          mark(p[0], true);
          if (report) report.push(p[2].label + '→' + String(p[1]).slice(0, 12) + '（自绘下拉）');
        }
      }, 70 * (i + 1));
    });
    return pending.length;
  }

  // 卡片式单选（antd Radio / element Radio / 通用 role=radio）
  function fillCardRadios(doc, prof, report, failed) {
    var items;
    try {
      items = doc.querySelectorAll('[role=radio],.ant-radio-wrapper,.el-radio,' +
        '.ant-radio-button-wrapper,.el-radio-button,.ivu-radio-wrapper');
    } catch (e) { return 0; }
    var groups = [];
    var CARD_SEL = '[role=radio],.ant-radio-wrapper,.el-radio,.ant-radio-button-wrapper,' +
      '.el-radio-button,.ivu-radio-wrapper';
    Array.prototype.slice.call(items).forEach(function (o) {
      if (!isVisible(o)) return;
      // 只保留"最内层"的选项元素：外层容器（label.ant-radio-wrapper 里还包着 span[role=radio]）
      // 点它不一定有事件，点最里面的那层才是真的选中。
      var inner = o.querySelectorAll ? o.querySelectorAll(CARD_SEL) : [];
      if (inner && inner.length) return;
      var host = null, n = o.parentElement, d = 0;
      while (n && d < 3) {
        if (controlCount(n) === 0 && n.querySelectorAll && n.querySelectorAll('[role=radio],.ant-radio-wrapper,.el-radio').length > 1) {
          host = n; break;
        }
        n = n.parentElement; d++;
      }
      host = host || o.parentElement;
      var g = null;
      for (var i = 0; i < groups.length; i++) { if (groups[i].host === host) { g = groups[i]; break; } }
      if (!g) { g = { host: host, opts: [] }; groups.push(g); }
      g.opts.push(o);
    });
    var n = 0;
    groups.forEach(function (g) {
      // 选项容器本身只写着"男 女"，题目（"性别"）在更外层的表单项里 —— 往上找一层
      var lab = visText(g.host);
      var cur = norm(lab);
      var anc = g.host.parentElement, d = 0;
      while (anc && d < 4) {
        var t = visText(anc);
        if (t && norm(t) !== cur && t.length <= 80) { lab = t + ' ' + lab; break; }
        anc = anc.parentElement; d++;
      }
      var f = bestField(lab.slice(0, 80), g.opts[0], doc);
      if (!f) { needHuman(failed, g.opts[0], lab, null, '没认出这是什么字段'); return; }
      var val = prof[f.k];
      if (!val) { needHuman(failed, g.opts[0], lab, f, '资料里没有「' + f.label + '」的值'); return; }
      var hit = g.opts.filter(function (o) {
        var t = visText(o);
        return t && (norm(t) === norm(val) || looseMatch(val, t));
      })[0];
      if (!hit) { needHuman(failed, g.opts[0], lab, f, '选项里没有「' + val + '」（需手点）'); return; }
      try {
        hit.click(); mark(hit, true); n++;
        if (report) report.push(f.label + '→' + String(val).slice(0, 12) + '（卡片单选）');
      } catch (e) {}
    });
    return n;
  }

  // 扫出"没认出来 / 认出来但没值"的字段 —— 面板里的「🧠 字段学习」用它
  function scanUnknown(doc) {
    var prof = P(), out = [], seen = {};
    collect(doc).forEach(function (el) {
      var t = String(attr(el, 'type') || 'text').toLowerCase();
      if (t === 'radio' || t === 'checkbox') return;
      var lab = labelOf(el, doc);
      var f = bestField(lab, el, doc);
      if (f && prof[f.k]) return;                 // 已经能自动填的不算
      var key = norm(lab).slice(0, 40) || ('__' + out.length);
      if (seen[key]) return;
      seen[key] = 1;
      out.push({ el: el, label: String(lab || '').slice(0, 40), field: f, hasValue: hasValue(el) });
    });
    return out;
  }

  function fillDoc(doc, mode) {
    var prof = P();
    var onlyEmpty = mode !== 'overwrite';
    var report = [], failed = [];
    var filled = fillRadios(doc, prof, onlyEmpty, report, failed);
    filled += fillCardRadios(doc, prof, report, failed);      // 卡片式单选（自绘）
    filled += fillCheckboxes(doc, prof, onlyEmpty, report, failed);
    collect(doc).forEach(function (el) {
      var t = String(attr(el, 'type') || 'text').toLowerCase();
      if (t === 'radio' || t === 'checkbox') return;
      if (onlyEmpty && hasValue(el)) return;
      var lab = labelOf(el, doc);
      var f = bestField(lab, el, doc);
      if (!f) { needHuman(failed, el, lab, null, '没认出这是什么字段'); return; }
      var raw = prof[f.k];
      if (!raw) { needHuman(failed, el, lab, f, '资料里没有「' + f.label + '」的值'); return; }
      var val = adapt(el, raw);
      if (!val) return;
      var ok = false;
      try {
        if (el.tagName === 'SELECT') ok = fillSelect(el, val);
        else if (isEditable(el)) { el.innerText = val; fire(el); ok = true; }
        else if (String(attr(el, 'readonly')) === 'true' || el.readOnly) {
          needHuman(failed, el, lab, f, '这是只读框（点右边 📋 复制后手填）'); return;
        } else { setNative(el, val); ok = true; }
      } catch (e) { ok = false; }
      if (ok) { mark(el, true); filled++; report.push(f.label + '→' + String(val).slice(0, 14)); }
      else { needHuman(failed, el, lab, f, '填不进去（可能是自绘控件，用 📋 复制）'); }
    });
    // 自绘下拉：点开后选项才渲染，异步完成；这里只回报"尝试了几个"
    var fake = fillFakeSelects(doc, prof, report);
    return { filled: filled, report: report, failed: failed, fakeSelects: fake, unknown: failed.length };
  }

  // 一键滚到那个字段并高亮 —— 报告里点一下就跳过去（填完最费时间的就是找它）
  function locate(el) {
    if (!el) return;
    try { if (el.scrollIntoView) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) {}
    try { if (el.focus && el.focus) el.focus(); } catch (e) {}
    try {
      el.style.outline = '3px solid #d1242f';
      el.style.outlineOffset = '2px';
      el.style.boxShadow = '0 0 0 4px rgba(209,36,47,.18)';
      setTimeout(function () {
        try { el.style.outline = ''; el.style.boxShadow = ''; } catch (e2) {}
      }, 2600);
    } catch (e) {}
  }

  /* ==================== 跨 iframe ==================== */
  // __BOOKMARK_CUT__ 书签版从这里截断（书签版没法往子框架注入脚本）
  var isTop = (function () { try { return window.top === window; } catch (e) { return false; } })();
  function broadcast(mode) {
    var msg = { __ihub: 'fill', __lgr: 'fill', mode: mode, dir: getDir() };
    try { for (var i = 0; i < window.frames.length; i++) window.frames[i].postMessage(msg, '*'); } catch (e) {}
  }
  window.addEventListener('message', function (ev) {
    var d = ev.data;
    if (!d || (d.__ihub !== 'fill' && d.__lgr !== 'fill')) return;
    if (ev.source === window) return;   /* 别理自己 */
    if (d.dir && PACKS[d.dir]) setDir(d.dir);
    var st = fillDoc(document, d.mode);
    try {
      var up = isTop ? window : window.parent;
      up.postMessage({ __ihub: 'filled', n: st.filled }, '*');
    } catch (e) {}
  });

  /* ==================== 面板 ==================== */
  var panel = null, statusEl = null, listEl = null, dirSel = null;
  var reportEl = null, learnEl = null, filterEl = null, hostEl = null, mountEl = null;
  var missBtnEl = null;
  var lastFailed = [], lastReport = [], lastStats = null;

  /* 面板样式：放在 Shadow DOM 里，跟网站自己的 CSS 完全隔离
     （碰过太多网申站把 z-index / font / box-sizing 全局改掉，面板一进去就散架） */
  var CSS = [
    '.ihub-p{position:fixed;right:16px;bottom:16px;z-index:2147483647;width:372px;max-height:80vh;',
    'overflow:auto;background:#fff;border:1px solid #d0d7de;border-radius:12px;',
    'box-shadow:0 10px 32px rgba(0,0,0,.22);font:13px/1.55 -apple-system,"Microsoft YaHei",sans-serif;',
    'color:#1f2328;box-sizing:border-box}',
    '.ihub-p *{box-sizing:border-box;font-family:inherit}',
    '.ihub-hd{display:flex;align-items:center;justify-content:space-between;padding:9px 11px;',
    'border-bottom:1px solid #eaeef2;background:#f6f8fa;border-radius:12px 12px 0 0;position:sticky;top:0;z-index:2}',
    '.ihub-bd{padding:10px 11px}',
    '.ihub-b{padding:5px 9px;border:1px solid #d0d7de;border-radius:7px;background:#f6f8fa;',
    'cursor:pointer;font-size:12px;color:#1f2328}',
    '.ihub-b:hover{background:#eef1f4}',
    '.ihub-b.pri{background:#1f6feb;color:#fff;border-color:#1f6feb}',
    '.ihub-b.ok{background:#1a7f37;color:#fff;border-color:#1a7f37}',
    '.ihub-row{display:flex;gap:6px;align-items:center;margin:3px 0}',
    '.ihub-tag{flex:0 0 88px;color:#57606a;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.ihub-in{flex:1;min-width:0;padding:3px 6px;border:1px solid #d0d7de;border-radius:6px;font-size:12px;color:#1f2328;background:#fff}',
    '.ihub-grp{margin:8px 0 2px;color:#0969da;font-size:11px;font-weight:600;border-top:1px solid #eaeef2;padding-top:6px}',
    '.ihub-sec{margin-top:9px;border-top:1px solid #eaeef2;padding-top:8px}',
    '.ihub-sec b{font-size:12px}',
    '.ihub-fail{display:flex;gap:6px;align-items:center;margin:3px 0;padding:3px 5px;border-radius:6px;background:#fff8f6;cursor:pointer}',
    '.ihub-fail:hover{background:#ffebe9}',
    '.ihub-fail span{flex:1;min-width:0;font-size:11px;color:#a40e26;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.ihub-fail em{font-style:normal;font-size:10px;color:#8c959f;flex:0 0 auto}',
    '.ihub-x{padding:2px 7px;border:1px solid #d0d7de;border-radius:5px;background:#fff;font-size:11px;cursor:pointer;flex:0 0 auto}',
    '.ihub-fab{position:fixed;right:16px;bottom:16px;z-index:2147483647;padding:10px 14px;background:#1f6feb;',
    'color:#fff;border-radius:24px;cursor:pointer;font:13px -apple-system,"Microsoft YaHei",sans-serif;',
    'box-shadow:0 4px 14px rgba(0,0,0,.28);user-select:none}'
  ].join('');

  // Shadow DOM 宿主：不支持就退回普通 div（打桩/老浏览器），功能一模一样
  function ensureHost() {
    if (hostEl && document.body && document.body.contains && document.body.contains(hostEl)) return mountEl;
    hostEl = document.createElement('div');
    hostEl.setAttribute('data-ihub', 'v5');
    try { hostEl.style.cssText = 'all:initial'; } catch (e) {}
    try { document.body.appendChild(hostEl); } catch (e) { return null; }
    var sh = null;
    try { sh = hostEl.attachShadow ? hostEl.attachShadow({ mode: 'open' }) : null; } catch (e2) { sh = null; }
    mountEl = sh || hostEl;
    try {
      var st = document.createElement('style');
      st.textContent = CSS;
      mountEl.appendChild(st);
    } catch (e3) {}
    return mountEl;
  }

  function copyText(t) {
    var s = String(t == null ? '' : t);
    if (!s) return false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(s); return true; }
    } catch (e) {}
    try {   /* 老浏览器 / iframe 里 clipboard 不可用时的兜底 */
      var ta = document.createElement('textarea');
      ta.value = s; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      var ok = document.execCommand && document.execCommand('copy');
      document.body.removeChild(ta);
      return !!ok;
    } catch (e) { return false; }
  }

  // ───────── 投递台账（第 3 步重构：填完/投完当场记一笔，防"投了不知道投过"）─────────
  // 油猴脚本碰不到 InternHub 的本地数据库，所以走**剪贴板**：
  // 点「记录本次投递」→ 存进本机 localStorage → 点「复制待同步记录」→
  // 回到网页「📮 投递与网申」页的粘贴框，粘贴即入库。
  var LEDGER_KEY = 'ihub_ledger_v1';
  var STAGES = ['未投', '已投', '笔试', '面试', 'Offer', '未通过'];

  function readLedger() {
    try { return JSON.parse(localStorage.getItem(LEDGER_KEY) || '[]') || []; }
    catch (e) { return []; }
  }
  function writeLedger(arr) {
    try { localStorage.setItem(LEDGER_KEY, JSON.stringify(arr.slice(-300))); } catch (e) {}
  }

  function guessCompany() {
    // 优先用站点名 / 页面主标题；都是"猜"，面板里可以改
    var cands = [];
    var meta = document.querySelector('meta[property="og:site_name"],meta[name="application-name"]');
    if (meta && meta.content) cands.push(meta.content);
    var h1 = document.querySelector('h1,h2,.logo,[class*="logo"] img');
    if (h1) cands.push(h1.getAttribute && h1.getAttribute('alt') || h1.textContent || '');
    cands.push(document.title || '');
    for (var i = 0; i < cands.length; i++) {
      var t = String(cands[i] || '').trim();
      if (!t) continue;
      t = t.split(/[-_|｜·—–]/)[0].trim();
      if (t.length >= 2 && t.length <= 30) return t;
    }
    try { return location.hostname.replace(/^www\./, ''); } catch (e) { return ''; }
  }
  function guessJob() {
    var el2 = document.querySelector('h1,h2,[class*="job"][class*="title"],[class*="position"]');
    var t = el2 ? String(el2.textContent || '').trim().slice(0, 40) : '';
    return t || (document.title || '').slice(0, 40);
  }
  function today() {
    var d = new Date();
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }
  function ledgerTsv(arr) {
    var cols = ['公司', '岗位', '城市', '状态', '投递日期', '链接', '备注'];
    var out = [cols.join('\t')];
    arr.forEach(function (r) {
      out.push([r.company, r.title, r.city, r.stage, r.applied_at, r.url, r.note]
        .map(function (v) { return String(v == null ? '' : v).replace(/\t/g, ' '); }).join('\t'));
    });
    return out.join('\n');
  }
  function ledgerNote(el2) {
    var n = readLedger().length;
    if (el2) el2.textContent = n
      ? '本机已记 ' + n + ' 条待同步 —— 点「复制待同步记录」后，回 InternHub 的「📮 投递与网申」页粘进「📥 粘贴导入」框。'
      : '还没有待同步记录。投完一家就在上面点「记录本次投递」。';
  }

  function el(tag, css, text) {
    var d = document.createElement(tag);
    if (css) d.style.cssText = css;
    if (text != null) d.textContent = text;
    return d;
  }
  function btn(text, css, fn) {
    var b = el('button', 'padding:5px 9px;border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa;' +
      'cursor:pointer;font-size:12px;' + (css || ''), text);
    b.type = 'button';
    b.addEventListener('click', fn);
    return b;
  }

  function fieldEditor(f, prof, ov) {
    var row = el('div', 'display:flex;gap:6px;align-items:center;margin:3px 0');
    var tag = el('div', 'flex:0 0 88px;color:' + (f.k in ov ? '#9a3412' : '#57606a') + ';font-size:12px' +
      ';overflow:hidden;text-overflow:ellipsis;white-space:nowrap',
      f.label + (f.k in ov ? ' *' : ''));
    var inp = el('input', 'flex:1;min-width:0;padding:3px 6px;border:1px solid #d0d7de;border-radius:5px;font-size:12px');
    inp.setAttribute('data-ihub-panel', '1');
    inp.value = prof[f.k] || '';
    inp.placeholder = '未填（可在这里补）';
    inp.addEventListener('change', function () {
      var v = inp.value.trim();
      if (v === (BASE[f.k] || '')) setOverride(f.k, ''); else setOverride(f.k, v);
      refreshList();
    });
    // 每个字段一个复制按钮：遇到"填不进去"的奇葩页面（自绘控件、只读框、富文本编辑器），
    // 直接复制粘贴也能把这一栏搞定 —— 这是"任何网页都能用"的兜底。
    var cp = btn('📋', 'padding:2px 7px;font-size:11px;flex:0 0 auto', (function (key, label, box) {
      return function () {
        var v = (P()[key] || box.value || '');
        var ok = copyText(v);
        if (statusEl) {
          statusEl.textContent = ok
            ? '已复制「' + label + '」：' + String(v).slice(0, 24) + '… —— 到页面上粘贴即可'
            : '复制失败，请手动选中输入框内容复制';
        }
      };
    })(f.k, f.label, inp));
    row.appendChild(tag); row.appendChild(inp); row.appendChild(cp);
    return row;
  }

  var onlyMissing = false;
  function missingCount(prof) {
    var n = 0;
    FIELDS.forEach(function (f) { if (!String(prof[f.k] || '').trim()) n++; });
    return n;
  }
  function refreshList() {
    if (!listEl) return;
    listEl.textContent = '';
    var prof = P(), ov = readOverrides();
    if (missBtnEl) {                       // 「只看缺的（N）」按钮上的数字
      var mn = missingCount(prof);
      missBtnEl.textContent = onlyMissing ? '← 看全部' : ('只看缺的（' + mn + '）');
      missBtnEl.style.background = mn > 12 ? '#fff8f6' : '#f6f8fa';
      missBtnEl.style.borderColor = mn > 12 ? '#ffcecb' : '#d0d7de';
      missBtnEl.style.color = mn > 12 ? '#a40e26' : '#1f2328';
    }
    var q = norm(filterEl ? filterEl.value : '');
    var shown = 0;
    GROUPS.forEach(function (g) {
      var items = FIELDS.filter(function (f) {
        if (f.g !== g.g) return false;
        // 「只看缺的」：填过的一律跳过 —— 补齐一次，以后每份网申都 100%
        if (onlyMissing && String(prof[f.k] || '').trim()) return false;
        if (!q) return true;
        if (norm(f.label).indexOf(q) >= 0 || norm(f.k).indexOf(q) >= 0) return true;
        return String(prof[f.k] || '').toLowerCase().indexOf(q) >= 0;
      });
      if (!items.length) return;
      listEl.appendChild(el('div', 'margin:8px 0 2px;color:#0969da;font-size:11px;font-weight:600;' +
        'border-top:1px solid #eaeef2;padding-top:6px', g.name + '（' + items.length + '）'));
      items.forEach(function (f) { listEl.appendChild(fieldEditor(f, prof, ov)); shown++; });
    });
    if (!shown) listEl.appendChild(el('div', 'color:#8c959f;font-size:12px;padding:6px 0',
      '没有匹配「' + (filterEl ? filterEl.value : '') + '」的字段。'));
  }

  function buildDirSelect(host) {
    var keys = Object.keys(PACKS);
    if (!keys.length) return;
    var wrap = el('div', 'display:flex;gap:6px;align-items:center;margin-bottom:6px');
    wrap.appendChild(el('div', 'flex:0 0 84px;color:#57606a;font-size:12px', '岗位方向'));
    dirSel = el('select', 'flex:1;padding:3px 6px;border:1px solid #d0d7de;border-radius:5px;font-size:12px');
    keys.forEach(function (k) {
      var o = document.createElement('option');
      o.value = k; o.textContent = (PACKS[k] && PACKS[k].label) || k;
      dirSel.appendChild(o);
    });
    dirSel.value = getDir();
    dirSel.addEventListener('change', function () {
      setDir(dirSel.value);
      refreshList();
      roleHint(dirSel.value);
      if (statusEl) {
        statusEl.textContent = '已切到「' + ((PACKS[dirSel.value] || {}).label || dirSel.value) +
          '」的自我评价 / 技能 / 亮点，直接点「填入空字段」即可。';
      }
    });
    wrap.appendChild(dirSel);
    host.appendChild(wrap);
    roleHintEl = el('div', 'font-size:11px;color:#8c959f;margin:0 0 6px 90px');
    host.appendChild(roleHintEl);
    roleHint(getDir());
  }
  var roleHintEl = null;
  function roleHint(dir) {
    if (!roleHintEl) return;
    var d = dir || getDir();
    var bits = [];
    ['expected_salary', 'intent', 'available'].forEach(function (k) {
      var v = (ROLE_VALS[k] || {})[d] || (ROLE_VALS[k] || {}).universal;
      if (v) bits.push((k === 'expected_salary' ? '期望薪资 ' : k === 'intent' ? '意向 ' : '到岗 ') + v);
    });
    roleHintEl.textContent = '本方向默认值：' + bits.join('　｜　') +
      '（资料里已有值的以资料为准，想换成这版点右边 ⤵）';
  }

  /* ============ 📊 填充报告：填完不静默，成功/需人工各列一份 ============ */
  function renderReport(st) {
    if (!reportEl) return;
    reportEl.textContent = '';
    var okN = st.filled, badN = (st.failed || []).length;
    var head = el('div', 'display:flex;align-items:center;justify-content:space-between');
    head.appendChild(el('b', 'font-size:12px;color:' + (badN ? '#9a6700' : '#1a7f37'),
      '📊 ' + (badN ? '已填 ' + okN + ' 项，还有 ' + badN + ' 项要你来处理' : '全部搞定：已填 ' + okN + ' 项')));
    var fold = btn(okN ? '收起' : '展开', 'padding:2px 7px;font-size:11px', function () {
      var b = reportEl.querySelector ? reportEl.querySelectorAll('div.ihub-oklist')[0] : null;
      if (b) { b.style.display = (b.style.display === 'none' ? 'block' : 'none'); fold.textContent = (b.style.display === 'none' ? '展开' : '收起'); }
    });
    head.appendChild(fold);
    reportEl.appendChild(head);

    if (okN) {
      var ol = el('div', 'max-height:132px;overflow:auto;margin:4px 0 0;font-size:11px;color:#1a7f37;line-height:1.7');
      ol.setAttribute('class', 'ihub-oklist');
      (st.report || []).forEach(function (r) { ol.appendChild(el('div', '', '✅ ' + r)); });
      reportEl.appendChild(ol);
    }
    if (badN) {
      reportEl.appendChild(el('div', 'font-size:11px;color:#a40e26;margin:6px 0 2px',
        '⚠️ 需人工（点一下直接跳到那一栏，并红框标出）'));
      (st.failed || []).slice(0, 30).forEach(function (it) {
        var row = el('div', 'display:flex;gap:6px;align-items:center;margin:3px 0;padding:3px 5px;' +
          'border-radius:6px;background:#fff8f6;cursor:pointer;font-size:11px');
        row.setAttribute('class', 'ihub-fail');
        row.addEventListener('click', function () { locate(it.el); });
        var t = el('span', 'flex:1;min-width:0;color:#a40e26;overflow:hidden;text-overflow:ellipsis;white-space:nowrap',
          (it.keyLabel ? it.keyLabel + '：' : '') + it.reason);
        var why = el('em', 'font-style:normal;font-size:10px;color:#8c959f;flex:0 0 auto',
          String(it.label || '').slice(0, 12) || '（无标签）');
        var cp = btn('📋', 'padding:1px 6px;font-size:11px;flex:0 0 auto', function (ev) {
          try { ev.stopPropagation(); } catch (e) {}
          var v = (it.key && P()[it.key]) || '';
          copyText(v || String(it.label || ''));
        });
        row.appendChild(why); row.appendChild(t); row.appendChild(cp);
        reportEl.appendChild(row);
      });
      if (st.failed.length > 30) {
        reportEl.appendChild(el('div', 'font-size:11px;color:#8c959f',
          '…还有 ' + (st.failed.length - 30) + ' 项，先处理上面这些。'));
      }
    }
    if (st.fakeSelects) {
      reportEl.appendChild(el('div', 'font-size:11px;color:#0969da;margin-top:4px',
        '另有 ' + st.fakeSelects + ' 个自绘下拉已自动点开选择（等 1~2 秒看结果）。'));
    }
  }

  /* ============ 🧠 字段学习：教一次，以后任何网站都认得 ============ */
  function renderLearn() {
    if (!learnEl) return;
    learnEl.textContent = '';
    var unk = [];
    try { unk = scanUnknown(document); } catch (e) {}
    var m = learnMap(), learnedN = Object.keys(m).length;
    var head = el('div', 'display:flex;align-items:center;justify-content:space-between');
    head.appendChild(el('b', 'font-size:12px', '🧠 字段学习（已记住 ' + learnedN + ' 个）'));
    var bar = el('div', 'display:flex;gap:5px');
    bar.appendChild(btn('🔄 重新扫描', 'padding:2px 7px;font-size:11px', function () { renderLearn(); }));
    bar.appendChild(btn('📤 导出', 'padding:2px 7px;font-size:11px', function () {
      copyText(JSON.stringify(learnMap(), null, 1));
      if (statusEl) statusEl.textContent = '学习库已复制到剪贴板（换电脑时用「导入」粘回来）。';
    }));
    bar.appendChild(btn('📥 导入', 'padding:2px 7px;font-size:11px', function () {
      var s = null;
      try { s = window.prompt ? window.prompt('把导出的学习库 JSON 粘进来：') : null; } catch (e) {}
      if (!s) return;
      try {
        var o = JSON.parse(s);
        var cur = learnMap(), n = 0;
        for (var k in o) { if (o[k] && o[k].k) { cur[k] = o[k]; n++; } }
        learnSave(cur); renderLearn();
        if (statusEl) statusEl.textContent = '已导入 ' + n + ' 条学习记录。';
      } catch (e2) { if (statusEl) statusEl.textContent = '这段不是有效的 JSON，导入取消。'; }
    }));
    bar.appendChild(btn('🗑', 'padding:2px 7px;font-size:11px', function () {
      learnSave({}); renderLearn();
      if (statusEl) statusEl.textContent = '已清空学习库。';
    }));
    head.appendChild(bar);
    learnEl.appendChild(head);

    if (!unk.length) {
      learnEl.appendChild(el('div', 'font-size:11px;color:#8c959f;margin:3px 0',
        learnedN ? '这一页没有不认识的字段了 ✅' : '这一页的字段都认得（或都填好了）。'));
      return;
    }
    learnEl.appendChild(el('div', 'font-size:11px;color:#57606a;margin:3px 0',
      '下面 ' + unk.length + ' 栏没认出来 —— 选一下它是什么，点「记住」，下次全世界的网申页都会自己填：'));
    unk.slice(0, 12).forEach(function (u) {
      var row = el('div', 'display:flex;gap:5px;align-items:center;margin:3px 0');
      var nm = el('div', 'flex:0 0 108px;font-size:11px;color:#1f2328;overflow:hidden;' +
        'text-overflow:ellipsis;white-space:nowrap', String(u.label || '（无标签）').slice(0, 18));
      var sel = el('select', 'flex:1;min-width:0;padding:2px 4px;border:1px solid #d0d7de;' +
        'border-radius:5px;font-size:11px');
      sel.setAttribute('data-ihub-panel', '1');
      var none = document.createElement('option');
      none.value = ''; none.textContent = '（这是什么？）';
      sel.appendChild(none);
      if (u.field) { var guess = document.createElement('option'); guess.value = u.field.k; guess.textContent = '像是：' + u.field.label; guess.selected = true; sel.appendChild(guess); }
      FIELDS.forEach(function (f) {
        var o = document.createElement('option');
        o.value = f.k; o.textContent = f.label;
        sel.appendChild(o);
      });
      var save = btn('记住', 'padding:2px 7px;font-size:11px;flex:0 0 auto', function () {
        if (!sel.value) { if (statusEl) statusEl.textContent = '先在下拉里选一个字段类型。'; return; }
        learnAdd(u.label, sel.value);
        // 页面上已经手填过的值也一起记住，下次直接填
        try {
          var cur = isEditable(u.el) ? visText(u.el) : String(u.el.value || '');
          if (cur && cur.trim()) setOverride(sel.value, cur.trim());
        } catch (e) {}
        var f2 = fieldByKey(sel.value);
        try {
          var v2 = P()[sel.value];
          if (v2 && !hasValue(u.el)) {
            if (u.el.tagName === 'SELECT') fillSelect(u.el, v2);
            else if (isEditable(u.el)) { u.el.innerText = v2; fire(u.el); }
            else setNative(u.el, adapt(u.el, v2));
            mark(u.el, true);
          }
        } catch (e2) {}
        if (statusEl) statusEl.textContent = '记住了：「' + String(u.label).slice(0, 16) + '」= ' +
          (f2 ? f2.label : sel.value) + '。以后任何网站遇到这个叫法都会自动填。';
        renderLearn(); refreshList();
      });
      var go2 = btn('定位', 'padding:2px 6px;font-size:11px;flex:0 0 auto', function () { locate(u.el); });
      row.appendChild(nm); row.appendChild(sel); row.appendChild(save); row.appendChild(go2);
      learnEl.appendChild(row);
    });
    if (unk.length > 12) {
      learnEl.appendChild(el('div', 'font-size:11px;color:#8c959f',
        '…还有 ' + (unk.length - 12) + ' 栏，先教这几个，剩下的再点「重新扫描」。'));
    }
  }

  function doFill(mode) {
    var st = fillDoc(document, mode);
    lastFailed = st.failed || [];
    lastReport = st.report || [];
    lastStats = st;
    broadcast(mode);
    renderReport(st);
    if (statusEl) {
      statusEl.textContent = '已填 ' + st.filled + ' 个字段' +
        (st.fakeSelects ? '，另有 ' + st.fakeSelects + ' 个自绘下拉已自动点选（稍等片刻）' : '') +
        (st.filled || st.fakeSelects
          ? '：' + st.report.slice(0, 6).join('，') + (st.report.length > 6 ? ' …' : '')
          : '（没有匹配到可填字段）');
    }
    renderLearn();
    setTimeout(function () {
      if (statusEl && st.filled === 0) {
        statusEl.textContent += '。若页面在 iframe 里，稍等 1~2 秒；也可以先点一下表单区域再点填入。';
      }
    }, 1300);
  }

  function buildPanel() {
    var mount = ensureHost();
    if (!mount) return;
    if (panel && mount.contains && mount.contains(panel)) { panel.style.display = 'block'; refreshList(); return; }
    panel = el('div', 'position:fixed;right:16px;bottom:16px;z-index:2147483647;width:372px;max-height:80vh;' +
      'overflow:auto;background:#fff;border:1px solid #d0d7de;border-radius:12px;' +
      'box-shadow:0 10px 32px rgba(0,0,0,.22);font:13px/1.55 -apple-system,"Microsoft YaHei",sans-serif;color:#1f2328');
    panel.setAttribute('class', 'ihub-p');
    panel.setAttribute('data-ihub-panel', '1');
    var head = el('div', 'display:flex;align-items:center;justify-content:space-between;padding:9px 11px;' +
      'border-bottom:1px solid #eaeef2;background:#f6f8fa;border-radius:12px 12px 0 0');
    head.appendChild(el('b', 'font-size:13px', '📝 网申助手 v5（70 类字段 · 会学习）'));
    var x = btn('收起', '', function () { panel.style.display = 'none'; if (fab) fab.style.display = 'block'; });
    head.appendChild(x);
    panel.appendChild(head);

    var body = el('div', 'padding:10px 11px');
    buildDirSelect(body);

    var bar = el('div', 'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px');
    bar.appendChild(btn('🚀 填入空字段', 'background:#1f6feb;color:#fff;border-color:#1f6feb', function () { doFill('empty'); }));
    bar.appendChild(btn('覆盖全部', '', function () { doFill('overwrite'); }));
    bar.appendChild(btn('恢复内置', '', function () {
      clearOverrides(); refreshList();
      if (statusEl) statusEl.textContent = '已清空本机手动修改，回到内置资料。';
    }));
    bar.appendChild(btn('⤵ 用本方向值', '', function () {
      var n = applyRoleDefaults();
      refreshList();
      if (statusEl) statusEl.textContent = '已把求职意向 / 期望薪资 / 到岗时间换成「' +
        ((PACKS[getDir()] || {}).label || getDir()) + '」这一档（' + n + ' 项），可在下面资料区改回。';
    }));
    bar.appendChild(btn('📋 导出资料', '', function () {
      var s = JSON.stringify(P(), null, 2);
      try { if (navigator.clipboard) navigator.clipboard.writeText(s); } catch (e) {}
      if (statusEl) statusEl.textContent = '资料 JSON 已复制到剪贴板（可粘到投递工作台的「从 JSON 导入」）。';
    }));
    body.appendChild(bar);

    statusEl = el('div', 'color:#57606a;font-size:12px;margin:6px 0 6px',
      '先选「岗位方向」，再点「🚀 填入空字段」。填完会出报告：哪些填好了、哪些要你处理。');
    body.appendChild(statusEl);

    // 📊 填充报告区（填完才有内容）
    var secR = el('div', 'margin-top:9px;border-top:1px solid #eaeef2;padding-top:8px');
    reportEl = el('div');
    secR.appendChild(reportEl);
    body.appendChild(secR);

    // 🧠 字段学习区
    var secL = el('div', 'margin-top:9px;border-top:1px solid #eaeef2;padding-top:8px');
    learnEl = el('div');
    secL.appendChild(learnEl);
    body.appendChild(secL);

    // ---- 📮 投递登记：填完/投完当场记一笔，回 InternHub 粘贴入库 ----
    var lg = el('div', 'border-top:1px solid #eaeef2;margin-top:8px;padding-top:8px');
    lg.appendChild(el('div', 'font-weight:600;font-size:12px;margin-bottom:4px',
      '📮 投递登记（防"投了不知道投过"）'));
    function lrow(label, val, ph) {
      var w = el('div', 'display:flex;gap:6px;align-items:center;margin:3px 0');
      w.appendChild(el('div', 'flex:0 0 52px;color:#57606a;font-size:12px', label));
      var i2 = el('input', 'flex:1;min-width:0;padding:3px 6px;border:1px solid #d0d7de;border-radius:5px;font-size:12px');
      i2.value = val || ''; i2.placeholder = ph || '';
      w.appendChild(i2);
      return { wrap: w, input: i2 };
    }
    var cComp = lrow('公司', guessCompany(), '投递的公司');
    var cJob = lrow('岗位', guessJob(), '岗位名');
    var cStage = el('div', 'display:flex;gap:6px;align-items:center;margin:3px 0');
    cStage.appendChild(el('div', 'flex:0 0 52px;color:#57606a;font-size:12px', '状态'));
    var stSel = el('select', 'flex:1;padding:3px 6px;border:1px solid #d0d7de;border-radius:5px;font-size:12px');
    STAGES.forEach(function (s) {
      var o = document.createElement('option'); o.value = s; o.textContent = s;
      if (s === '已投') o.selected = true;
      stSel.appendChild(o);
    });
    cStage.appendChild(stSel);
    lg.appendChild(cComp.wrap); lg.appendChild(cJob.wrap); lg.appendChild(cStage);

    var lbar = el('div', 'display:flex;gap:6px;flex-wrap:wrap;margin:5px 0');
    lbar.appendChild(btn('📮 记录本次投递', 'background:#1a7f37;color:#fff;border-color:#1a7f37', function () {
      var comp = cComp.input.value.trim() || guessCompany();
      if (!comp) {
        if (statusEl) statusEl.textContent = '先填「公司」名再记录（自动猜的没认出来）。';
        return;
      }
      var arr = readLedger();
      arr.push({
        company: comp, title: cJob.input.value.trim(), city: '',
        stage: stSel.value, applied_at: today(),
        url: (location.href || '').slice(0, 300), note: '网申助手记录',
      });
      writeLedger(arr);
      ledgerNote(ledgerStatus);
      if (statusEl) statusEl.textContent = '已记下「' + comp +
        '」。投完这家记得点「复制待同步记录」回 InternHub 入库。';
    }));
    lbar.appendChild(btn('📋 复制待同步记录', '', function () {
      var arr = readLedger();
      if (!arr.length) { if (statusEl) statusEl.textContent = '本机还没有待同步记录。'; return; }
      var ok = copyText(ledgerTsv(arr));
      if (statusEl) statusEl.textContent = ok
        ? '已复制 ' + arr.length + ' 条 —— 回 InternHub「📮 投递与网申」页，粘进「📥 粘贴导入」框即可入库。'
        : '复制失败，请在下面的记录框里手动选中复制。';
      if (taEl) { taEl.value = ledgerTsv(arr); taEl.style.display = 'block'; }
    }));
    lbar.appendChild(btn('🗑 清空本机记录', '', function () {
      writeLedger([]); ledgerNote(ledgerStatus);
      if (taEl) { taEl.value = ''; taEl.style.display = 'none'; }
      if (statusEl) statusEl.textContent = '已清空本机待同步记录（InternHub 里已入库的不会删）。';
    }));
    lg.appendChild(lbar);
    var ledgerStatus = el('div', 'color:#8c959f;font-size:11px', '');
    ledgerNote(ledgerStatus);
    lg.appendChild(ledgerStatus);
    var taEl = el('textarea', 'display:none;width:100%;height:78px;margin-top:4px;font-size:11px;' +
      'border:1px solid #d0d7de;border-radius:5px;padding:4px');
    lg.appendChild(taEl);
    lg.appendChild(el('div', 'color:#8c959f;font-size:11px;margin-top:3px',
      '⚠️ 烟草系统同一批次只能报 1 个单位 1 个岗位，重复投递取消资格 —— ' +
      '入库时 InternHub 会自动拦你。'));
    body.appendChild(lg);

    // 📝 资料区（70 个字段分组展示 + 搜索）
    var secP = el('div', 'margin-top:9px;border-top:1px solid #eaeef2;padding-top:8px');
    var ph = el('div', 'display:flex;gap:6px;align-items:center;margin-bottom:4px');
    ph.appendChild(el('b', 'font-size:12px;flex:0 0 auto', '📝 我的资料'));
    filterEl = el('input', 'flex:1;min-width:0;padding:3px 7px;border:1px solid #d0d7de;' +
      'border-radius:6px;font-size:12px');
    filterEl.setAttribute('data-ihub-panel', '1');
    filterEl.placeholder = '搜字段（如 身高 / 期望薪资）';
    filterEl.addEventListener('input', function () { refreshList(); });
    ph.appendChild(filterEl);
    secP.appendChild(ph);

    // 「只看缺的」：填充率上不去的唯一原因就是资料有空 —— 这里一次补齐，以后全是 100%
    var missBar = el('div', 'display:flex;gap:6px;align-items:center;margin-bottom:4px');
    var missBtn = btn('', 'padding:3px 8px;font-size:11px;flex:0 0 auto', function () {
      onlyMissing = !onlyMissing;
      refreshList();
    });
    missBar.appendChild(missBtn);
    missBar.appendChild(el('div', 'flex:1;font-size:11px;color:#8c959f',
      '资料有空就填不满 —— 补一次，以后每份网申都是 100%'));
    secP.appendChild(missBar);
    missBtnEl = missBtn;
    listEl = el('div');
    secP.appendChild(listEl);
    body.appendChild(secP);

    body.appendChild(el('div', 'color:#8c959f;font-size:11px;margin-top:6px',
      '只在你本人点击时填表，不联网、不提交、不绕过验证码。定稿前请逐个核对。'));
    panel.appendChild(body);
    mount.appendChild(panel);
    refreshList();
    renderLearn();
  }

  var fab = null;
  function buildFab() {
    var mount = ensureHost();
    if (!mount) return;
    if (fab && mount.contains(fab)) return;
    fab = el('div', 'position:fixed;right:16px;bottom:16px;z-index:2147483647;padding:10px 14px;' +
      'background:#1f6feb;color:#fff;border-radius:24px;cursor:pointer;' +
      'font:13px -apple-system,"Microsoft YaHei",sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.28);user-select:none',
      '📝 网申助手 v5');
    fab.setAttribute('class', 'ihub-fab');
    fab.setAttribute('data-ihub-panel', '1');
    fab.addEventListener('click', function () {
      buildPanel();
      if (panel) panel.style.display = 'block';
      fab.style.display = 'none';
    });
    mount.appendChild(fab);
  }

  function ensureMounted() {
    if (!document.body) return;
    var ok = hostEl && document.body.contains(hostEl);
    if (!ok || !fab || (mountEl && mountEl.contains && !mountEl.contains(fab))) buildFab();
  }

  if (isTop) {
    ensureMounted();
    setInterval(ensureMounted, 2500);  /* SPA/前端框架会重渲染 body */
  }

  // 调试/自测入口（沙箱模式下写 window 可能被拒，忽略即可）
  var API = {
    labelOf: labelOf, bestField: bestField, fillDoc: fillDoc, adapt: adapt,
    fillSelect: fillSelect, FIELDS: FIELDS, profile: P, setOverride: setOverride,
    getOverrides: readOverrides, overrides: readOverrides, clearOverrides: clearOverrides,
    getDir: getDir, setDir: setDir, PACKS: PACKS, groupLabel: groupLabel,
    isVisible: isVisible, buildPanel: buildPanel,
    // v5：多档数据 / 填充报告 / 字段学习
    ROLE_VALS: ROLE_VALS, GROUPS: GROUPS, contextLabel: contextLabel,
    applyRoleDefaults: applyRoleDefaults, roleHint: roleHint,
    learnMap: learnMap, learnAdd: learnAdd, learnDel: learnDel, learnLookup: learnLookup,
    LEARN_KEY: LEARN_KEY, scanUnknown: scanUnknown, locate: locate,
    renderReport: renderReport, renderLearn: renderLearn, fieldByKey: fieldByKey,
    // 投递台账（第 3 步重构）：本机暂存 + 导出 TSV，回 InternHub 粘贴入库
    readLedger: readLedger, writeLedger: writeLedger, ledgerTsv: ledgerTsv,
    guessCompany: guessCompany, LEDGER_KEY: LEDGER_KEY, STAGES: STAGES,
  };
  try { window.__IHUB_AUTOFILL__ = API; } catch (e) {}
  try { window.__LGR_AUTOFILL__ = API; } catch (e) {}
})();
"""


def build_js(prof=None) -> str:
    prof = prof or profile_mod.load()
    data = {k: (prof.get(k) or "") for k in KEYS}
    # resume_kit 里更权威的字段（学院、GPA 等）补进来，但仍以「我的资料」为准
    if _tailor is not None:
        try:
            for k, v in _tailor.base_fields().items():
                if not data.get(k):
                    data[k] = v
        except Exception:
            pass
    for _k, _v in EXTRA_DEFAULTS.items():
        if not data.get(_k):
            data[_k] = _v
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    pks = json.dumps(_packs(), ensure_ascii=False, indent=2)
    return _TEMPLATE.replace("__PAYLOAD__", payload).replace("__PACKS__", pks)


def _atomic_write(path: str, content: str) -> None:
    """先写临时文件再替换：生成失败时绝不把已能用的旧文件清空。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def save_userscript(path: str = None, prof=None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, SCRIPT_NAME)
    content = build_js(prof)                 # 先完整生成，再落盘
    _atomic_write(path, content)
    return path


_BOOKMARK_HEAD = "javascript:"
_BOOKMARK_TAIL = "go();})()"


def _minify(js: str) -> str:
    """压成一行（先把行尾 // 注释改成块注释，再补 ASI 需要的分号）。"""
    lines = []
    for line in js.split("\n"):
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        m = re.match(r"^(.*?[{;])\s*//\s*(.+)$", s)
        if m and "*/" not in m.group(2):
            s = m.group(1) + "  /* " + m.group(2).strip() + " */"
        lines.append(s)
    out = []
    for i, s in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if nxt[:1] in ("(", "[", "+", "-") and not s.endswith(
                (";", "{", "}", ",", "(", "[", ":", "=", "=>", "&&", "||", "?", "+", "-", "*", "/")):
            s += ";"
        out.append(s)
    text = " ".join(out)
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def build_bookmarklet(prof=None) -> str:
    """从同一份源码生成书签版（免装扩展）：点书签即按「只填空字段」填一遍当前页。"""
    js = build_js(prof)
    idx = js.find("(function () {")
    body = js[idx:]
    sentinel = "// __BOOKMARK_CUT__"
    cut = body.find(sentinel)
    if cut < 0:
        raise RuntimeError("网申脚本缺少 __BOOKMARK_CUT__ 哨兵，无法生成书签版")
    body = _minify(body[:cut])
    for i in range(len(body) - 1):
        if body[i:i + 2] == "//" and (i == 0 or body[i - 1] != ":"):
            raise RuntimeError(
                f"书签版源码里有会吞代码的 // 注释（位置 {i}）：{body[max(0, i - 60):i + 60]!r}")
    boot = (
        "function go(){try{var st=fillDoc(document,'empty');var m='网申助手（书签版）：已填 '+st.filled+' 个字段';"
        "if(st.filled){m+='\\n'+st.report.slice(0,10).join('，');}"
        "else{m+='\\n\\n没匹配到字段。若是 iframe 表单，书签版填不了，请用油猴版；"
        "也可以先在页面滚动一下再点一次。';}"
        "m+='\\n\\n请逐个核对后再提交。';alert(m);}catch(e){alert('网申助手出错：'+e.message);}}"
    )
    return _BOOKMARK_HEAD + body + boot + _BOOKMARK_TAIL


def save_bookmarklet(path: str = None, prof=None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, BOOKMARK_NAME)
    content = build_bookmarklet(prof)         # 先完整生成，再落盘
    _atomic_write(path, content + "\n")
    return path


if __name__ == "__main__":
    print(save_userscript())
    print(save_bookmarklet())
