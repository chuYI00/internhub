# -*- coding: utf-8 -*-
"""CSV 导入（命令行）：把其他来源（Excel / 飞书多维表格 / 官网 / 群文件）的岗位清单导入库。

用法：
    venv\\Scripts\\python.exe run_import.py 你的文件.csv
    venv\\Scripts\\python.exe run_import.py 飞书导出.csv --source 飞书表1

说明：**解析逻辑统一在 ihub/importer.py**，这里只是命令行外壳。
      以前这个文件里另有一套表头别名表，两处各改各的、慢慢就不一致了
      （同类坑：项目里曾有两个 sources.json，往被遮蔽的那个里加东西永远不生效）。

表头怎么填都行（自动识别别名，认不出的列会写进"描述"不丢数据）：
    岗位 / 职位名称 / 招聘岗位　　　公司 / 单位名称 / 招聘单位
    工作城市 / 工作地点 / 地点　　　投递链接 / 岗位链接 / 报名入口
    截止时间 / 投递截止时间　　　　招聘批次 / 届别 / 毕业年份
    薪资 / 学历要求 / 岗位职责 / 备注 …
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ihub import config, db, importer  # noqa: E402


def _read_text(path: str) -> str:
    """按 UTF-8-SIG 读 —— 飞书/Excel 导出的 CSV 常带 BOM，会让第一列表头认不出来。"""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def main() -> int:
    ap = argparse.ArgumentParser(description="导入 CSV/TSV 岗位清单（其他来源）")
    ap.add_argument("csv", help="CSV/TSV 文件路径（UTF-8，可带 BOM）")
    ap.add_argument("--source", default="CSV导入", help="数据来源标记（默认 CSV导入）")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print("找不到文件：", args.csv)
        return 1

    db.init_db()
    text = _read_text(args.csv)
    res = importer.import_csv_text(text, source=args.source)

    print(f"读取 {res.get('rows', 0)} 行 → 新增 {res.get('inserted', 0)} / "
          f"更新 {res.get('updated', 0)} / 疑似风险 {res.get('flagged', 0)}")
    print("表头映射：", res.get("mapping") or "（一列都没认出，已按第一列当岗位名兜底）")
    for w in res.get("warnings") or []:
        print("  [提醒]", w)
    print("数据库：", config.DB_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
