# -*- coding: utf-8 -*-
"""采集链路自测：跳转壳解码 / 公司名提取 / 数据源并集 / 官网入口匹配。

运行：venv\\Scripts\\python.exe tests\\test_weblist.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ihub import channels                                   # noqa: E402
from ihub.crawlers.weblist import (_company_from_title,     # noqa: E402
                                   _real_apply_url, load_sources)

P = F = 0


def check(name, cond, extra=None):
    global P, F
    if cond:
        P += 1
        print("  ✓ " + name)
    else:
        F += 1
        print("  ✗ " + name + (f"  -> {extra!r}" if extra is not None else ""))


print("[1] 跳转壳 → 企业官方投递地址（应届生求职网的 thirdlink）")
check("解出建行校招网申页",
      _real_apply_url("https://q.yingjiesheng.com/thirdlink?url="
                      "https%3A%2F%2Fjob2.ccb.com%2Fcn%2Fjob%2Fplan_index.html%3FplanType%3DXY")
      == "https://job2.ccb.com/cn/job/plan_index.html?planType=XY",
      _real_apply_url("https://q.yingjiesheng.com/thirdlink?url=https%3A%2F%2Fjob2.ccb.com%2F"))
check("解出北森 hotjob 入口",
      _real_apply_url("https://q.yingjiesheng.com/thirdlink?url=https%3A%2F%2Fwecruit.hotjob.cn%2FSU620%2Fmc%2F")
      .startswith("https://wecruit.hotjob.cn/"))
check("解出飞书招聘入口",
      _real_apply_url("https://q.yingjiesheng.com/thirdlink?url=https%3A%2F%2Fx.jobs.feishu.cn%2F123")
      .startswith("https://x.jobs.feishu.cn/"))
check("不是壳的链接保持原样", _real_apply_url("https://campus.51job.com/cimc/") == "")
check("空值不炸", _real_apply_url("") == "" and _real_apply_url(None) == "")

print("[2] 公告标题 → 公司名")
cases = [("中国建设银行2027年度校园招聘", "中国建设银行"),
         ("第一创业证券2027届校园招聘", "第一创业证券"),
         ("中集集团2027届校招", "中集集团"),
         ("汇丰银行管培生计划", "汇丰银行")]
for title, want in cases:
    got = _company_from_title(title)
    check(f"{title} → {want}", got == want, got)
check("乱七八糟的标题不硬编出公司名", _company_from_title("招聘") == "",
      _company_from_title("招聘"))

print("[3] 数据源清单取并集（历史上的双份遮蔽 bug）")
srcs = load_sources()
check("源数量 ≥27", len(srcs) >= 27, len(srcs))
names = {s["name"] for s in srcs}
for kw in ("应届生求职网·2027校招公告", "云南省教育厅·公示公告", "昆明市人社局·通知公告",
           "云南航空产业投资集团·招聘"):
    check(f"包含 {kw}", kw in names)
check("应届生源开了 auto_company", any(s.get("auto_company") for s in srcs))
check("每个源都有 name", all(s.get("name") for s in srcs))

print("[3b] 采集健壮性：重试 / TLS 开关 / 慢站超时 / 事后公告过滤")
from ihub.crawlers import weblist as W                                # noqa: E402

# ① 失败一次后能重试成功（政府站高峰期常见 5xx / 连接重置）
_calls = {"n": 0}
_real_get = W.requests.get


class _FakeResp:
    status_code = 200
    text = "<html><body><a href='/a.html'>某某单位2027年公开招聘公告</a></body></html>"
    url = "https://example.com/"
    apparent_encoding = "utf-8"
    encoding = "utf-8"


def _flaky_get(url, **kw):
    _calls["n"] += 1
    if _calls["n"] == 1:
        raise RuntimeError("模拟首次连接被重置")
    return _FakeResp()


W.requests.get = _flaky_get
try:
    r = W._http_get("https://example.com/list.html")
    check("首次失败后自动重试并成功", _calls["n"] == 2 and r.status_code == 200, _calls["n"])
finally:
    W.requests.get = _real_get

# ② insecure_tls 真的会把证书校验关掉（老旧证书链的州/市级政府站）
_seen = {}


def _capture_get(url, **kw):
    _seen.update(kw)
    return _FakeResp()


W.requests.get = _capture_get
try:
    W._http_get("https://example.com/", insecure=True)
    check("insecure_tls=True → verify=False", _seen.get("verify") is False, _seen.get("verify"))
    _seen.clear()
    W._http_get("https://example.com/", insecure=False)
    check("默认仍然校验证书（verify=True）", _seen.get("verify") is True, _seen.get("verify"))
    check("请求头带 Accept-Language: zh-CN（部分站点按语言返回空壳页）",
          "zh-CN" in str((_seen.get("headers") or {}).get("Accept-Language")), _seen.get("headers"))
finally:
    W.requests.get = _real_get

check("默认单源超时 >= 20 秒（省级政府站首包常 >10s）", W.PER_SOURCE_TIMEOUT >= 20,
      W.PER_SOURCE_TIMEOUT)

# ③ 云南核心源必须是"栏目页"而不是首页，且事后公告有过滤
_srcs = {x["name"]: x for x in load_sources()}
_yn = _srcs.get("云南省人社厅·招聘公告")
check("云南省人社厅指向「招考招聘」栏目(ClassID=458)，不是首页",
      _yn and "ClassID=458" in _yn["url"], _yn and _yn["url"])
check("云南省人社厅带事后公告过滤（拟聘/公示/体检…）",
      _yn and "拟聘" in (_yn.get("exclude_keyword_regex") or ""), _yn and _yn.get("exclude_keyword_regex"))
_km = _srcs.get("昆明市人社局·通知公告")
check("昆明市人社局指向 /tzgg/ 栏目页", _km and _km["url"].endswith("/tzgg/"), _km and _km["url"])
check("昆明人社的链接正则匹配**相对**路径（列表页里是 /c/日期/id.shtml）",
      _km and not _km["link_regex"].startswith("http") and _km["link_regex"].startswith("c/"),
      _km and _km["link_regex"])
check("证书老旧的站点开了 insecure_tls",
      _srcs.get("大理州人社局·通知公告", {}).get("insecure_tls") is True
      and _srcs.get("云南农业大学就业网", {}).get("insecure_tls") is True)

print("[4] 官网入口匹配（必须取最长键，别把「红塔银行」配成「红塔集团」）")
check("云南中烟 → 中烟官网", channels.official_for("云南中烟工业有限责任公司") == "https://www.ynzy-tobacco.com/")
check("云南机场 → 航产投招聘页", channels.official_for("云南航空产业投资集团（云南机场集团）") == "https://hr.ynairport.com/zp/")
check("南方电网云南 → 电网招聘系统", channels.official_for("中国南方电网云南电网") == "https://zhaopin.csg.cn")
check("不认识的空公司名返回空", channels.official_for("某某科技") == "")
check("空公司名不炸", channels.official_for("") == "")

print("[5] 投递入口清单（官方入口 / 来源页要分清）")
from ihub.linklist import apply_links_text                     # noqa: E402
_recs = [
    # 应届生：link 是跳转壳，official_url 才是企业网申页 → 应显示为"官方投递"
    {"title": "中国建设银行2027年度校园招聘", "company": "中国建设银行", "city": "", "source": "应届生",
     "link": "https://q.yingjiesheng.com/thirdlink?url=https%3A%2F%2Fjob2.ccb.com%2F",
     "official_url": "https://job2.ccb.com/cn/job/plan_index.html?planType=XY",
     "deadline": "2026-10-15"},
    {"title": "某校招聘专员", "company": "某单位", "city": "昆明", "source": "云师大就业网",
     "link": "https://job.ynnu.edu.cn/info/1.html",
     "official_url": "https://job.ynnu.edu.cn/info/1.html", "deadline": ""},
]
_txt = apply_links_text(_recs)
check("清单含岗位标题", "中国建设银行2027年度校园招聘" in _txt)
check("有官方入口的写成 官方投递：", "官方投递：https://job2.ccb.com" in _txt)
check("official==link 的不冒充官方入口",
      "官方投递：—" in _txt and _txt.count("官方投递：https") == 1, _txt.count("官方投递：https"))
check("统计了缺失条数", "1 条没有官方入口" in _txt)
check("空输入不炸", apply_links_text([]).startswith("投递入口清单"))

print("[6] 项目里的 .bat 必须是 CRLF 换行")
import glob                                                    # noqa: E402
_bats = sorted(glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "*.bat")))
check("项目根至少有 3 个 bat", len(_bats) >= 3, [os.path.basename(b) for b in _bats])
for _b in _bats:
    with open(_b, "rb") as _f:
        _raw = _f.read()
    _crlf = _raw.count(b"\r\n")
    _bare = _raw.count(b"\n") - _crlf
    check(f"{os.path.basename(_b)} 全部是 CRLF（无裸 LF）", _bare == 0, f"裸LF={_bare}")
    check(f"{os.path.basename(_b)} 以 @echo off 开头", _raw.startswith(b"@echo off"),
          _raw[:20])

print(f"\n结果: {P} 通过, {F} 失败")
sys.exit(1 if F else 0)
