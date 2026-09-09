from .base import BaseCrawler
from .shixiseng import ShixisengCrawler
from .rss import RssCrawler

CRAWLERS = {
    "实习僧": ShixisengCrawler,
    "RSS订阅": RssCrawler,
}

__all__ = ["BaseCrawler", "ShixisengCrawler", "RssCrawler", "CRAWLERS"]
