# 规则层岗位风险/真实性过滤：拦截明显是付费内推、培训机构骗局的岗位并打标。
# 说明：规则无法 100% 识别，仅作辅助；网页必须展示免责声明，投递请到官方链接核实。

RISK_KEYWORDS = [
    "付费内推", "内推费", "收费内推", "买offer", "包offer", "保offer", "保录取",
    "培训费", "先交钱", "先交费", "交押金", "缴纳押金", "保证金", "贷培训",
    "贷款培训", "分期付款", "付费培训", "包就业", "内推收费", "招转培",
    "交费入职", "下载app注册", "充值", "会费", "入会费", "买课",
]

def risk_scan(text: str) -> str:
    """对文本做风险扫描，命中返回原因，否则返回空字符串。"""
    if not text:
        return ""
    for kw in RISK_KEYWORDS:
        if kw in text:
            return f"命中风险词：{kw}"
    return ""

def scan_job(job: dict) -> tuple:
    """返回 (is_fake, reason)"""
    blob = " ".join([
        str(job.get("title", "")),
        str(job.get("company", "")),
        str(job.get("requirement", "") or ""),
        str(job.get("tags", "") or ""),
        str(job.get("description", "") or ""),
    ])
    reason = risk_scan(blob)
    return (True, reason) if reason else (False, "")
