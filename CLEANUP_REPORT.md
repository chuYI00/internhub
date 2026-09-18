# CLEANUP_REPORT.md · 清理报告

> 执行时间：2026-09-18 11:45–11:50　|　范围：仅 `D:\罗广睿\intern_tool` 项目内　|　原则：只移动、不永久删除，全程可回滚。

## 一、已移入 `.trash_20260918_1145/`（可安全清理的临时文件）

| 类别 | 数量 | 说明 |
|---|---|---|
| `tests/_*.py` 临时调试脚本 | 8 | 查 bug 时临时写的探针/校验脚本 |
| `tests/_*.txt` 调试输出 | 19 | 测试重定向的中间产物 |
| `tests/run_all_out.txt` | 1 | 上次全量测试 stdout 快照 |
| `_cleaned.txt`（根目录空文件） | 1 | 误产的空文件 |
| `data/飞书岗位导出.csv.bak_test` | 1 | 测试残留备份 |
| `__pycache__/` 及 `*.pyc` | 3 目录 | 运行时缓存，会自动重建 |

> 说明：`__pycache__` 已由 `.gitignore` 排除，删除纯属让目录干净；测试运行时会自动重建（本次验证时已重建）。

## 二、已归档到 `archive/`（详见 `archive/ARCHIVE_INDEX.md`）

- **旧版本**：3 个 `.bak` + 顶层 `md2docx.py` + `tools_scan_cleanup.py` + 25 个 patch
- **旧文档**：3 份重构指令 + 待清理清单 + 被取代的冲刺备考资料（md/docx）+ 旧导航页
- **旧数据**：数据源合并前快照 + 旧体检结果 + 冗余的 `data/sources.json`

## 三、未操作（重要文件，原地保留）

- `.git/`、`.gitignore`、`requirements.txt`、`LICENSE`、`README.md`
- `app.py`、`ihub/` 全部源码、`sources.json`（权威数据源）
- `data/` 下运行时数据（`jobs.db`、`profile.json`、`resume_kit.json`、`tobacco_seen.json`、`link_health.json`）
- `简历材料/`（交付成品，含个人信息）、`token.txt`、`.streamlit/config.toml`
- 所有 `run_*.py`、`scheduler.py` 入口脚本
- `网申助手.user.js`、`采集助手.user.js`、`网申书签.txt`、`采集书签.txt`（生成产物）
- `venv/`（本地运行环境，496M）

## 四、按用户要求保留（未归档、未删除）

- `投递文件/` 下 9 份旧简历 + `投递清单_2026-09-09.csv`（用户要求「留」）
- `backup/internhub_未推送.bundle`（被 `推送GitHub.bat` 引用，可能含未推送提交）
- `解码飞书表格.py`、`飞书只读表格导出实操指南.md`、`导入教程.md`（仍被文档引用）

## 五、项目验证结果

✅ `venv\Scripts\python.exe tests\run_all.py` → **21 组全部通过**

## 六、回滚方法

- **回收站文件**：从 `.trash_20260918_1145/` 按相对路径移回原位即可。
- **归档文件**：从 `archive/` 按 `ARCHIVE_INDEX.md` 的「原路径」列移回原位。
- **最终兜底**：Git 历史（112 个 tracked 文件），`git checkout -- <路径>` 可恢复。
- 全部确认无误后，可手动删除 `.trash_20260918_1145/` 目录（本报告生成时未清空，等你确认）。
