"""爬虫基类：robots 检查 + 限速 + 统一的输出字段结构。"""
import time
import urllib.robotparser
from urllib.parse import urlparse

from .. import config


class BaseCrawler:
    """所有数据源爬虫的基类。

    子类需实现 fetch_city(city, max_pages) -> list[dict]。
    每条 dict 字段（与 db.upsert_jobs 对应）：
      source, job_id, title, company, city, salary, salary_min, salary_max,
      degree, duration, tags, industry, link
    """

    name = "基类"
    # 是否允许被 robots 判定为禁止后仍然抓取（默认否 = 合规优先）
    allow_if_disallowed = False

    def __init__(self, delay=None):
        self.delay = delay if delay is not None else config.REQUEST_DELAY
        self._rp = None
        self._robots_ok = True

    def robots_allows(self, url: str) -> bool:
        """检查目标 robots.txt。

        注意：用带 UA 的请求读取；若 robots.txt 不存在 / 返回 4xx / 为空，
        按业界惯例视为“无限制”（RobotFileParser 默认不带 UA 会被部分站点 403，
        从而误判为全禁止）。
        """
        if not config.RESPECT_ROBOTS:
            return True
        o = urlparse(url)
        base = f"{o.scheme}://{o.netloc}"
        robots = f"{base}/robots.txt"
        if self._rp is None:
            import requests as _req
            try:
                r = _req.get(robots, headers={"User-Agent": config.USER_AGENT},
                             timeout=8)
                if r.status_code != 200:
                    self._rp = True  # 视为无 robots 限制
                    return True
                text = r.text or ""
                self._rp = urllib.robotparser.RobotFileParser()
                self._rp.parse(text.splitlines())
            except Exception:
                return True  # 读取失败视为允许
        if self._rp is True:
            return True
        return self._rp.can_fetch("*", url)

    def check_robots(self, url: str) -> bool:
        ok = self.robots_allows(url)
        if not ok:
            print(f"[合规] robots.txt 禁止抓取 {url}，已跳过（如确需请手动关闭 RESPECT_ROBOTS）")
        return ok

    def crawl(self, cities, max_pages=1, on_page=None, verbose=True):
        """按城市逐个抓取。on_page(page_no, jobs): 可选回调。返回合并后的列表。"""
        all_jobs = []
        for city in cities:
            if verbose:
                print(f"\n== [{self.name}] 城市：{city}，最多 {max_pages} 页 ==")
            try:
                jobs = self.fetch_city(city, max_pages=max_pages, verbose=verbose)
                if jobs:
                    all_jobs.extend(jobs)
                    if on_page:
                        on_page(city, len(jobs))
            except Exception as e:
                print(f"[{self.name}] {city} 抓取异常：{e}")
        return all_jobs

    # ---- 子类实现 ----
    def fetch_city(self, city, max_pages=1, verbose=True):
        raise NotImplementedError

    def _throttle(self):
        if self.delay:
            time.sleep(self.delay)
