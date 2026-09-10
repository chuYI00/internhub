# 配置：城市、限速、合规开关等

# 默认抓取城市（可在网页/命令行中覆盖）
DEFAULT_CITIES = ["昆明", "大理", "潍坊", "济南", "青岛", "北京", "上海", "深圳", "广州", "成都", "杭州"]

# 省份 → 城市（供“按省份筛选”使用；站点本身按城市归档）
PROVINCE_CITIES = {
    "山东": ["济南", "青岛", "潍坊", "烟台", "威海", "淄博", "临沂", "济宁", "泰安", "日照", "德州"],
    "云南": ["昆明", "大理", "曲靖", "玉溪", "楚雄", "丽江", "保山", "昭通", "红河", "普洱"],
    "全国/远程": ["全国"],
}
PROVINCE_LABELS = sorted(PROVINCE_CITIES.keys())  # 如“山东”会显示在地区下拉里

# 每页间隔秒数（防反爬，勿小于 1）
REQUEST_DELAY = 1.5

# 单城市默认抓取页数（实习僧每页 20 条）
DEFAULT_PAGES = 2

# 是否严格尊重 robots.txt（为 True 时若站点禁止该路径则拒绝抓取）
RESPECT_ROBOTS = True

# 数据库路径（锚定项目根目录，避免因运行目录不同而漂移）
import os as _os

PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
DATA_DIR = _os.path.join(PROJECT_ROOT, "data")
DB_PATH = _os.path.join(DATA_DIR, "jobs.db")

# 数据源别名（用于扩展）
SOURCES = ["实习僧", "RSS订阅"]

# RSS / Atom 订阅源（官方渠道接入示例，可自行添加）：
#   示例：{"url": "https://example.com/feed.xml", "name": "某官方信息源"}
#   只有站点官方提供 RSS/Atom 时才有效；没有的站点请用 run_import.py 导入。
RSS_FEEDS = [
    # {"url": "https://www.xxx.edu.cn/rss.xml", "name": "XX高校就业信息网"},
]

# 网络超时
TIMEOUT = 15

# 浏览器 UA（普通浏览器访问，避免伪装成爬虫的高频行为）
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
