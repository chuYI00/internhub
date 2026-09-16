# InternHub · 实习岗位聚合器

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![Streamlit](https://img.shields.io/badge/UI-Streamlit-red) ![License](https://img.shields.io/badge/License-MIT-green)

一个**本地运行、个人求职辅助**的实习岗位聚合网页工具：定时抓取公开实习信息 → 存入 SQLite → 网页端按**地区（含省份）/关键词**筛选 → 一键查看**原始官方投递链接** → **按岗位自动定制「投递理由 + 简历 docx」** → 人工到官方页面投递。

> ⚠️ **合规与免责声明（请务必阅读）**
> - 仅用于**个人求职 / 学习交流**，勿商用或二次分发他人岗位信息；
> - 默认**遵守目标站点 robots.txt**、低频抓取（每页间隔 1.5s+），不绕过验证码、不暴力爬取；
> - **不担保岗位真实性**、不参与招聘、**不自动代投**（脚本代投违反平台规则且易封号）；投递前请点击原始链接到官方渠道核实，谨防“付费内推 / 培训费 / 押金”类骗局；
> - 公开列表大多不提供“发布日期”，页面以“收录时间 + 截止时间（详情页）”为准。

---

## ✨ 功能

- **抓取入库**：实习僧（当前数据源）结构化解析（Node 解析 `__NUXT__`，无 Node 自动降级 DOM 解析）；薪资/学历/标签等字段清洗入库
- **筛选**：地区下拉**支持省份**（如选“山东”→自动匹配济南/青岛/潍坊…）、关键词搜索、“只看未截止 / 近 3 / 7 / 30 天”
- **时间**：每条岗位显示 **收录时间**；可选抓详情页 **截止日期**，已截止自动标红
- **收藏 / 投递箱**：勾选 ⭐ 收藏；勾选 🎯 进投递工作台
- **🎯 投递工作台**：逐条自动生成**投递理由/开场白** + **按岗位方向定制的简历（docx）**（新媒体 / 产品 / AI / 硬件 / 软开等方向自动识别并调整求职意向与匹配亮点），导出投递清单 CSV，标记“已投”
- **🌐 全网平台入口矩阵**：22 个正规招聘平台（国聘网 / 24365 / BOSS / 智联 / 牛客 / 应届生 /
  云南人才网 / 昆明·大理人社 / 各校就业网…）。实测大平台都是前端渲染抓不到，所以给每个平台
  配了**「搜索直达」**——点开＝在该平台内搜「昆明/大理+你的专业+应届」，绕开登录墙、永不 404
- **📥 自己找的岗位表也能导**：飞书多维表格 / Excel 导出的 CSV 直接导入，表头自动识别
  （岗位/单位名称/工作城市/投递截止时间/招聘批次…都能认），进来就能去重、加投递箱、出简历
- **🍃 烟草监控**（单独页签）：盯国家烟草专卖局「人才招聘专栏」（各省/中烟公告唯一首发口，实测可抓），**只报新增**；能从公告原文里解析出**报名窗口 + 剩余天数倒计时 + 报名平台网址 + 是否限制报考岗位数**；页面红字告警「10 天内截止」；已配自动化每 12 小时扫一次并推送
- **🚀 官方投递入口**：每条岗位给「企业官方投递页」（应届生求职网的跳转壳会自动解码成企业
  网申系统地址），可一键导出「投递入口清单」→ 进官网 → 网申助手填表 → 生成对应简历
- **📝 简历定制**：粘一段 JD → 自动识别岗位方向（9 套）→ 给出**匹配度 + 命中/未体现的关键词** → 生成该方向的**单页定向简历（docx / pdf）** + 20 项**网申填写文案**（一键复制）
- **🤖 网申自动填表**：`网申助手.user.js`（油猴）按岗位方向一键填 40 类字段，含下拉/单选/日期/富文本/iframe；装不上扩展可用 `网申书签.txt`
- **其他来源**：`run_import.py` CSV 导入（参考 `示例_导入模板.csv`），适合把官网 / 群文件 / Excel 整理的岗位导进来
- **真实性过滤**：规则层自动标记“付费内推 / 培训费 / 押金”类风险岗位
- **合规**：robots 检查、限速、低频、保留原始链接；页面常驻免责声明

> 说明：牛客 / BOSS / 智联等平台为强反爬 + 需登录，暂不接入，避免合规与封禁风险；架构预留多数据源扩展（见 `ihub/crawlers/`）。

---

## 🚀 快速开始（本地）

```bash
# 1) 进入项目
cd intern_tool

# 2) 虚拟环境 + 依赖
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux
pip install -r requirements.txt

# 3)（推荐）安装 Node.js —— 实习僧结构化解析更准；未安装会自动降级 DOM 解析

# 4) 先抓一批数据（城市可换，如 北京 或 潍坊）
python run_crawl.py --cities 潍坊,济南,青岛 --pages 2

# 5) 启动网页 → http://localhost:8501
streamlit run app.py
```

Windows 用户也可直接双击仓库内的 `启动网页.bat` / `抓取数据.bat`。

### 常用命令

```bash
# 抓取 + 补抓前 20 条的详情页截止时间（较慢）
python run_crawl.py --cities 北京 --pages 2 --enrich 20

# 定时每 6 小时自动更新（常驻）
python scheduler.py --hours 6 --cities 北京,潍坊

# 导入其他来源的岗位清单（CSV，UTF-8）
python run_import.py 你的岗位表.csv
```

---

## 🧱 技术栈

| 层 | 选型 |
| --- | --- |
| 前端/UI | Streamlit |
| 数据源 | 实习僧（Nuxt SSR 结构化解析 + DOM 备用） |
| 存储 | SQLite（文件型，免部署） |
| 文档生成 | python-docx + reportlab（单页定向简历，docx / pdf） |
| 浏览器自动化 | Tampermonkey 用户脚本 **v4**（兼容北森/Moka/飞书等 antd·element 自绘控件；本人点击触发，不代登录/不代提交） |
| 多渠道采集 | 声明式多源抓取（sources.json，27 个源并发）+ 搜索引擎站内直达兜底 |
| 任务调度 | 自带 `scheduler.py`（或 GitHub Actions / cron） |

```
用户 ─▶ Streamlit (app.py)
          │
          ▼
   ihub/db.py ◀── run_crawl.py / scheduler.py ◀── ihub/crawlers/*（限速+robots）
          │
          ▼
     data/jobs.db  ── 投递工作台 ──▶ 定制投递理由 / 简历 docx / CSV 清单
```

---

## 📁 目录结构

```
intern_tool/
├─ app.py                # Streamlit 网页（列表/筛选/收藏/投递工作台）
├─ run_crawl.py          # 命令行抓取（--cities 城市 --pages 页 --enrich N）
├─ run_import.py         # CSV 导入其他来源
├─ scheduler.py          # 定时自动抓取
├─ gen_resume_kit.py     # 一键重新生成全部简历材料
├─ run_tobacco_watch.py  # 🍃 烟草监控（只报新增 + 报名窗口倒计时）
├─ 监控烟草.bat          # 双击即扫一遍烟草公告
├─ 启动网页.bat / 抓取数据.bat / 生成简历材料.bat
├─ 示例_导入模板.csv
├─ requirements.txt
├─ ihub/
│  ├─ config.py          # 城市/省份、限速、robots 开关
│  ├─ db.py              # SQLite：建表/迁移/去重/查询/收藏/投递状态
│  ├─ filters.py         # 虚假岗位规则过滤
│  ├─ resume.py          # 按岗位生成投递理由 + 定制简历 docx
│  ├─ tailor.py          # 岗位方向识别 / 匹配分析 / 单页定向简历 / 网申文案
│  ├─ yunnan.py          # 云南秋招投递渠道地图（27 家单位 / 8 类 / 每周动作）
│  ├─ platforms.py       # 全网 22 个招聘平台矩阵 + 站内搜索直达 + 今日动作
│  ├─ tobacco.py         # 🍃 烟草监控：公告抓取 / 报名窗口解析 / 新增比对
│  ├─ linklist.py        # 投递入口清单（官方投递页 / 来源页分清）
│  ├─ autofill.py        # 生成网申助手.user.js + 网申书签.txt（v3 多方向）
│  ├─ workbench.tpl.html # 投递工作台网页模板（注入资料后输出）
│  ├─ md2docx.py         # Markdown → docx（报告/说明用）
│  └─ crawlers/
│     ├─ base.py         # 爬虫基类（robots、限速）
│     └─ shixiseng.py    # 实习僧解析 + 详情截止时间
├─ sources.json          # 数据源清单（权威，随 Git 版本管理；共 27 个源）
├─ 简历材料/             # 成品：万能版 + 8 个方向简历 / 工作台 / 速填卡 / 报告
├─ 备考冲刺资料/         # 云南烟草备考作战方案 + 投递渠道地图 + 全网平台矩阵
├─ 投递文件/             # 运行时生成：按岗位定制的简历
├─ data/
│  ├─ jobs.db            # 运行时生成（不入库）
│  └─ resume_kit.json    # 简历内容源（改完跑 gen_resume_kit.py）
```

---

## ☁️ 定时更新不靠电脑常开

用 GitHub Actions 示例：每 6 小时调用一次抓取（需自行解决站点可达性与合规判断，仅作模板思路）：

```yaml
name: crawl
on:
  schedule:
    - cron: "0 */6 * * *"
  workflow_dispatch:
jobs:
  crawl:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: python run_crawl.py --cities 北京 --pages 1
      - uses: actions/upload-artifact@v4
        with: { name: jobs-db, path: data/jobs.db }
```

---

## 📄 License

[MIT](LICENSE) © 2026 罗广睿 (chuYI00)

> 项目聚合的是第三方平台公开信息，代码开源仅供学习；请遵守各平台 robots 与用户协议。
