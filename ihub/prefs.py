# -*- coding: utf-8 -*-
"""求职偏好（用于岗位打分推荐）。保存在本机 data/preferences.json。"""
import json
import os

from . import config

PREF_PATH = os.path.join(config.DATA_DIR, "preferences.json")

DEFAULT = {
    # 三个维度的权重（会自动归一化）
    "w_salary": 0.40,   # 钱多
    "w_match": 0.35,    # 与专业/技能契合
    "w_easy": 0.25,     # 轻松程度（启发式）
    "min_salary": 100,  # 期望最低日薪（元/天），低于此值降权
    "major_keywords": [
        "物联网", "嵌入式", "单片机", "硬件", "电子", "通信", "计算机", "软件",
        "测试", "数据", "AI", "人工智能", "算法", "自动化", "电气", "信息", "系统",
        "运维", "技术支持", "网络", "产品", "低代码", "数字",
    ],
    "easy_tags": [
        "远程实习", "线上办公", "时间灵活自由", "零基础实习", "实习证明", "接受大一大二",
        "不加班", "双休", "弹性", "文职", "助理", "数据整理", "文档", "接受小白",
    ],
    "hard_keywords": [
        "销售", "地推", "电话", "客服", "一线", "倒班", "夜班", "加班", "高强度",
        "出差", "体力", "搬运", "促销", "业绩", "提成", "KPI", "机务", "地勤", "装卸",
        "餐饮", "门店", "导购", "驻场",
    ],
}


def load() -> dict:
    data = dict(DEFAULT)
    try:
        if os.path.exists(PREF_PATH):
            with open(PREF_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if v not in (None, "", []):
                    data[k] = v
    except Exception:
        pass
    return data


def save(prefs: dict) -> str:
    os.makedirs(os.path.dirname(PREF_PATH), exist_ok=True)
    with open(PREF_PATH, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)
    return PREF_PATH


def lists(text: str):
    return [x.strip() for x in (text or "").replace("，", ",").split(",") if x.strip()]
