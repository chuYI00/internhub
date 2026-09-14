from .base import BaseCrawler
from .shixiseng import ShixisengCrawler
from .rss import RssCrawler
from .weblist import WebListCrawler

CRAWLERS = {
    "实习僧": ShixisengCrawler,
    "网页列表(多源)": WebListCrawler,
    "RSS订阅": RssCrawler,
}

__all__ = ["BaseCrawler", "ShixisengCrawler", "RssCrawler", "WebListCrawler", "CRAWLERS"]