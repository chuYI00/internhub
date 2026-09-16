# -*- coding: utf-8 -*-
"""导入链路自测：采集助手导出的 CSV（12 列表头）能否正确入库。

覆盖：中文字段映射、薪资列、描述里的未识别列、去重（重复导入不新增）、
以及"网页表格"来源（飞书多维表格导出）也能正常入库。

运行： venv\\Scripts\\python.exe tests\\test_import_csv.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ihub import config, db, importer  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name}" + (f"  -> {extra}" if extra is not None else ""))


def collector_csv() -> str:
    """与 采集助手.user.js 输出完全一致的形状：BOM + CRLF + 全字段加引号 + 12 列。"""
    head = ["岗位", "公司", "城市", "学历", "标签", "链接", "截止日期", "描述",
            "岗位类型", "届别", "来源", "薪资"]
    rows = [
        ["数据分析工程师", "云南机场集团", "昆明", "本科及以上", "", "https://x.com/a",
         "2026-11-30", "序号：1 | 备注：五险一金", "秋招", "2027届", "feishu.cn", "8-12万/年"],
        ["新媒体运营专员", "云南中烟", "大理", "本科", "", "https://x.com/b",
         "2026-11-20", "序号：2 | 备注：党员优先", "秋招", "2027届", "feishu.cn", "7-10万/年"],
        ["信息化管理岗", "广投集团", "昆明", "硕士", "", "https://x.com/c",
         "2026-12-05", "序号：3", "秋招", "2027届", "feishu.cn", "10-15万/年"],
    ]
    q = lambda v: '"' + str(v).replace('"', '""') + '"'  # noqa: E731
    lines = [",".join(q(h) for h in head)]
    lines += [",".join(q(c) for c in r) for r in rows]
    return "\ufeff" + "\r\n".join(lines) + "\r\n"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        config.DB_PATH = os.path.join(tmp, "test_jobs.db")
        db.init_db()

        csv_text = collector_csv()
        res = importer.import_csv_text(csv_text, source="采集书签")
        print("[1] 首次导入")
        check("解析到 3 行", res["rows"] == 3, res["rows"])
        check("新增 3 条", res.get("inserted") == 3, res)
        check("字段映射识别到 title", "title" in res["mapping"], res["mapping"])
        check("字段映射识别到 salary", "salary" in res["mapping"], res["mapping"])
        check("无告警（BOM 已正确处理）", not res.get("warnings"), res.get("warnings"))

        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM jobs ORDER BY title").fetchall()
        check("库里 3 条", len(rows) == 3, len(rows))
        by_title = {r["title"]: r for r in rows}
        j = by_title.get("数据分析工程师")
        check("公司正确", j and j["company"] == "云南机场集团", j and j["company"])
        check("城市正确", j and j["city"] == "昆明", j and j["city"])
        check("学历正确", j and j["degree"] == "本科及以上", j and j["degree"])
        check("薪资正确", j and j["salary"] == "8-12万/年", j and j["salary"])
        check("截止日期正确", j and j["deadline"] == "2026-11-30", j and j["deadline"])
        check("链接正确", j and j["link"] == "https://x.com/a", j and j["link"])
        check("描述含未识别列", j and "序号：1" in (j["description"] or ""), j and j["description"])
        check("岗位类型=秋招", j and j["job_type"] == "秋招", j and j["job_type"])
        check("届别=2027届", j and j["batch"] == "2027届", j and j["batch"])
        check("来源=CSV 里的域名（优先于导入时填的批次名）",
              j and j["source"] == "feishu.cn", j and j["source"])

        print("[2] 重复导入（同一份 CSV 再来一次，应更新而不是新增）")
        res2 = importer.import_csv_text(csv_text, source="采集书签")
        n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        check("库内仍是 3 条（去重生效）", n == 3, n)
        check("没有新增", res2.get("inserted", 0) == 0, res2)

        print("[3] 岗位类型/城市筛选可用（秋招 + 昆明 应命中 2 条）")
        n2 = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE job_type='秋招' AND city='昆明'").fetchone()[0]
        check("昆明秋招 2 条", n2 == 2, n2)

        print("[4] 中文表头别名 + 完全认不出表头时的兜底")
        plain = ("序号,职位名称,单位名称,工作城市\r\n"
                 "1,数据采集工程师,某科技公司,昆明\r\n"
                 "2,AI 训练师,某互联网公司,大理\r\n")
        res3 = importer.import_csv_text(plain, source="手工整理")
        check("『职位名称/单位名称/工作城市』别名全部识别", res3["rows"] == 2, res3)
        check("别名齐全时不该有告警", not res3.get("warnings"), res3.get("warnings"))
        n3 = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE source='手工整理'").fetchone()[0]
        check("来源回退为导入批次名（手工整理 2 条）", n3 == 2, n3)
        row = conn.execute(
            "SELECT * FROM jobs WHERE title='数据采集工程师'").fetchone()
        check("岗位名取『职位名称』列", row is not None)
        check("单位取『单位名称』列", row and row["company"] == "某科技公司", row and row["company"])
        check("城市取『工作城市』列", row and row["city"] == "昆明", row and row["city"])

        weird = "序号,内容,地区\r\n1,云南机场集团校园招聘公告,昆明\r\n"
        res4 = importer.import_csv_text(weird, source="认不出表头")
        check("认不出表头也能导入（不整份丢弃）", res4["rows"] == 1, res4)
        check("给出告警提示用了第一列", bool(res4.get("warnings")), res4.get("warnings"))
        row2 = conn.execute("SELECT * FROM jobs WHERE source='认不出表头'").fetchone()
        check("兜底用第一列当岗位名", row2 and row2["title"] == "1", row2 and row2["title"])
        conn.close()

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
