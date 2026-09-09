from .base import BaseCrawler
from .shixiseng import ShixisengCrawler

CRAWLERS = {
    "实习僧": ShixisengCrawler,
}

__all__ = ["BaseCrawler", "ShixisengCrawler", "CRAWLERS"]
