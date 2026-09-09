# -*- coding: utf-8 -*-
"""企业官方招聘渠道映射。

说明：
- OFFICIAL_URLS：内置常用企业官方招聘入口（已核验的才放）。
- 用户可在 data/official_urls.json 里覆盖/新增，格式 {"公司名": "https://..."}，
  覆盖优先级高于内置表。
- 未收录的公司 official_url 为空，界面会显示“—”，可按上文方法自行补充。
"""
import json
import os

from . import config

# 仅收录确认可用的官方入口（2026-09 核验）
OFFICIAL_URLS = {
    "字节跳动": "https://jobs.bytedance.com/campus/",
    "NIO蔚来": "https://nio.jobs.feishu.cn/campus/",
    "蔚来": "https://nio.jobs.feishu.cn/campus/",
}


def _user_overrides() -> dict:
    p = os.path.join(config.DATA_DIR, "official_urls.json")
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def official_for(company: str) -> str:
    if not company:
        return ""
    merged = dict(OFFICIAL_URLS)
    merged.update(_user_overrides())
    # 1) 精确名 → 2) 包含匹配
    if company in merged:
        return merged[company]
    for key, url in merged.items():
        if key in company or company in key:
            return url
    return ""
