# -*- coding: utf-8 -*-
"""网申自动填写助手：根据个人资料生成本地用户脚本（Tampermonkey）。

设计原则（合规、安全）：
- 只在**你本人打开的网页**上工作，由你点按钮触发填写，**不登录、不提交、不绕过验证码**；
- 只填充匹配到的输入框（姓名/手机/邮箱/学校/专业/学历/毕业时间/GPA 等），填充后高亮，由你核对；
- 资料来自本机 data/profile.json，脚本不联网上传任何数据。
"""
import json
import os

from . import config, profile as profile_mod

SCRIPT_NAME = "网申助手.user.js"


def build_js(prof=None) -> str:
    prof = prof or profile_mod.load()
    data = {
        "name": prof.get("name", ""),
        "gender": prof.get("gender", ""),
        "phone": prof.get("phone", ""),
        "email": prof.get("email", ""),
        "city": prof.get("city", ""),
        "school": prof.get("school", ""),
        "major": prof.get("major", ""),
        "degree": prof.get("degree", ""),
        "edu_range": prof.get("edu_range", ""),
        "graduate_year": prof.get("graduate_year", ""),
        "gpa": prof.get("gpa", ""),
        "scholarship": prof.get("scholarship", ""),
        "english": prof.get("english", ""),
        "intent": prof.get("intent", ""),
        "self_eval": prof.get("self_eval", ""),
        "certificates": prof.get("certificates", ""),
    }
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return f"""// ==UserScript==
// @name         网申助手（本地·本人使用）
// @namespace    internhub.local
// @version      1.0
// @description  在网申页面一键填入个人资料（由本人点击触发，不代登录、不代提交）
// @match        *://*/*
// @grant        none
// ==/UserScript==
(function () {{
  'use strict';
  const DATA = {payload};

  // 标签关键词 → 资料字段（按顺序匹配，先精确后模糊）
  const RULES = [
    [['姓名', 'name', '真实姓名'], DATA.name],
    [['性别', 'gender'], DATA.gender],
    [['手机', '电话', 'mobile', 'phone', '联系方式'], DATA.phone],
    [['邮箱', 'email', 'mail', '电子信箱'], DATA.email],
    [['学校', '院校', '毕业院校', 'school', 'university'], DATA.school],
    [['专业', 'major'], DATA.major],
    [['学历', '学位', 'degree'], DATA.degree],
    [['在校时间', '起止时间', '就读时间', 'edu_range'], DATA.edu_range],
    [['毕业时间', '毕业年月', '毕业年份', 'graduation', 'graduate'], DATA.graduate_year],
    [['GPA', '绩点', '成绩'], DATA.gpa],
    [['奖学金', '荣誉', '获奖'], DATA.scholarship],
    [['英语', '四六级', 'CET', '外语'], DATA.english],
    [['求职意向', '意向岗位', '应聘岗位', '期望职位', 'intent'], DATA.intent],
    [['自我评价', '自我介绍', '个人简介', 'self'], DATA.self_eval],
    [['证书', '资格证'], DATA.certificates],
    [['现居', '所在地', '生源地', '籍贯', '城市'], DATA.city],
  ];

  function labelOf(el) {{
    let parts = [];
    if (el.placeholder) parts.push(el.placeholder);
    if (el.name) parts.push(el.name);
    if (el.id) {{
      parts.push(el.id);
      const lab = document.querySelector('label[for="' + el.id + '"]');
      if (lab) parts.push(lab.innerText);
    }}
    const wrap = el.closest('div,td,li,tr,section');
    if (wrap && wrap.innerText) parts.push(wrap.innerText.slice(0, 60));
    return parts.join(' ').toLowerCase();
  }}

  function setValue(el, val) {{
    if (!val) return false;
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, val);
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    el.style.outline = '2px solid #015187';
    return true;
  }}

  function fillPage() {{
    const els = Array.from(document.querySelectorAll('input, textarea'));
    let n = 0;
    els.forEach(el => {{
      const t = (el.type || '').toLowerCase();
      if (['hidden', 'file', 'submit', 'button', 'checkbox', 'radio', 'password'].includes(t)) return;
      if (el.value) return;                       // 已有内容不覆盖
      const lab = labelOf(el);
      for (const [keys, val] of RULES) {{
        if (!val) continue;
        if (keys.some(k => lab.includes(k.toLowerCase()))) {{
          if (setValue(el, val)) {{ n++; break; }}
        }}
      }}
    }});
    alert('网申助手：已尝试填写 ' + n + ' 个字段（蓝色边框为已填），请核对后再提交。');
  }}

  const btn = document.createElement('button');
  btn.textContent = '📝 填入我的资料';
  btn.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:999999;padding:10px 14px;' +
    'background:#015187;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;' +
    'box-shadow:0 2px 8px rgba(0,0,0,.25)';
  btn.onclick = fillPage;
  window.addEventListener('load', () => document.body.appendChild(btn));
}})();
"""


def save_userscript(path: str = None, prof=None) -> str:
    path = path or os.path.join(config.PROJECT_ROOT, SCRIPT_NAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_js(prof))
    return path
