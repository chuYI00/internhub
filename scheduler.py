"""定时抓取：python scheduler.py --hours 6 --cities 北京,上海"""
import argparse
import time

from ihub import config, db
from ihub.crawlers import CRAWLERS


def run_once(source="实习僧", cities=None, pages=None):
    db.init_db()
    crawler = CRAWLERS[source]()
    jobs = crawler.crawl(cities or config.DEFAULT_CITIES,
                         max_pages=pages or config.DEFAULT_PAGES)
    res = db.upsert_jobs(jobs)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 新增{res['inserted']} "
          f"更新{res['updated']} 疑似风险{res['flagged']} 共解析{len(jobs)}条")
    return res


def main():
    ap = argparse.ArgumentParser(description="常驻定时抓取（Ctrl+C 退出）")
    ap.add_argument("--hours", type=float, default=6)
    ap.add_argument("--cities", default=",".join(config.DEFAULT_CITIES))
    ap.add_argument("--pages", type=int, default=config.DEFAULT_PAGES)
    ap.add_argument("--source", default="实习僧", choices=list(CRAWLERS.keys()))
    args = ap.parse_args()
    cities = [c.strip() for c in args.cities.split(",") if c.strip()]

    run_once(args.source, cities, args.pages)
    while True:
        time.sleep(args.hours * 3600)
        run_once(args.source, cities, args.pages)


if __name__ == "__main__":
    main()
