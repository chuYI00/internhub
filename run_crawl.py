"""命令行单次抓取：python run_crawl.py --cities 北京,大理 --pages 2 [--enrich 20]"""
import argparse
import time

from ihub import config, db
from ihub.crawlers import CRAWLERS


def main():
    ap = argparse.ArgumentParser(description="抓取实习岗位入库")
    ap.add_argument("--cities", default=",".join(config.DEFAULT_CITIES),
                    help="城市，逗号分隔，如 北京,上海,潍坊")
    ap.add_argument("--pages", type=int, default=config.DEFAULT_PAGES,
                    help="每城市页数（每页20条）")
    ap.add_argument("--source", default="实习僧", choices=list(CRAWLERS.keys()))
    ap.add_argument("--enrich", type=int, default=0,
                    help="额外抓取详情页截止时间的前 N 条（较慢，建议≤30）")
    args = ap.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()]
    db.init_db()

    crawler_cls = CRAWLERS[args.source]
    crawler = crawler_cls()
    print(f"抓取源：{args.source} | 城市：{cities} | 页数：{args.pages}")
    t0 = time.time()
    # 多源 / RSS 类数据源与城市无关：只跑一次
    once = any(k in args.source for k in ("多源", "RSS"))
    jobs = crawler.crawl([""] if once else cities, max_pages=args.pages)
    if args.enrich and jobs and hasattr(crawler, "enrich_deadlines"):
        print(f"补充抓取详情页截止时间（前 {min(args.enrich, len(jobs))} 条）…")
        crawler.enrich_deadlines(jobs, cap=args.enrich)
    res = db.upsert_jobs(jobs)
    print(f"\n完成：解析 {len(jobs)} 条 → 新增 {res['inserted']} / 更新 {res['updated']} / "
          f"疑似风险 {res['flagged']}，耗时 {time.time() - t0:.1f}s")
    print("数据库：", config.DB_PATH)


if __name__ == "__main__":
    main()
