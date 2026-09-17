#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""解码飞书多维表格抓包数据 → CSV（接 InternHub 导入）

用法（任选其一）：
    venv\\Scripts\\python.exe 解码飞书表格.py 抓包.txt        # 文件里是 base64 字符串或 JSON
    venv\\Scripts\\python.exe 解码飞书表格.py 抓包1.txt 抓包2.txt 抓包3.txt   # 分页抓了多次 → 合并
    venv\\Scripts\\python.exe 解码飞书表格.py 抓包目录\\        # 目录里所有 .txt/.json 一起解
    venv\\Scripts\\python.exe 解码飞书表格.py                 # 交互：把内容粘贴后回车，再按 Ctrl+Z 回车结束

内容可以是三种之一（自动识别）：
  1. Network 里复制的 base64（通常 H4sI 开头 = gzip 压缩的 JSON）
  2. 解压后的 JSON 文本（含 records 字段）
  3. 已经是表格文本的（直接转存）
多个文件会**按行合并并去重**（record_id 相同，或字段内容完全相同，只保留一条）——
这样分页接口（一页 20/100 条）抓几次也能拼成完整表。

输出：data/飞书岗位导出.csv（utf-8-sig，Excel/本工具导入向导都能直接用）
"""
import base64
import csv
import glob
import gzip
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 单元格归一化**复用** ihub/feishu.py 那一份（毫秒时间戳→日期、超链接取 URL、多选拼接…），
# 不在这里再写一套 —— 这个项目已经因为"两套实现各改各的"踩过两次坑（sources.json 双份、
# run_import 双份）。独立脚本单独跑时 import 失败也不要紧，下面有等价的本地兜底。
try:
    from ihub.feishu import cell_to_text as _feishu_cell_text
except Exception:                                   # pragma: no cover
    _feishu_cell_text = None


def try_decode(content: str):
    """把任意抓包内容转成 dict/list；失败返回 None"""
    content = content.strip()
    # 去 data: 前缀 / 引号
    content = re.sub(r'^data:[^,]*,', '', content).strip().strip('"').strip("'")
    # 1) 直接 JSON
    if content.startswith('{') or content.startswith('['):
        try:
            return json.loads(content)
        except Exception:
            pass
    # 2) base64（容忍换行和 URL 安全字符）
    b64 = re.sub(r'\s+', '', content).replace('-', '+').replace('_', '/')
    b64 += '=' * (-len(b64) % 4)
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        return None
    for data in (raw, ):
        # gzip
        if data[:2] == b'\x1f\x8b':
            try:
                data2 = gzip.decompress(data)
                try:
                    return json.loads(data2)
                except Exception:
                    pass
            except Exception:
                pass
        # 裸 base64 → JSON
        try:
            return json.loads(data.decode('utf-8'))
        except Exception:
            pass
        # zlib
        try:
            import zlib
            return json.loads(zlib.decompress(data).decode('utf-8'))
        except Exception:
            pass
    return None


def load_many(content: str):
    """把一段文本解成**多个** JSON 对象（分页抓包可能连着粘了好几个响应）。

    先按整体解析；不行再用 raw_decode 逐个扫（文件里粘了多个 JSON 时用得上）。
    """
    obj = try_decode(content)
    if obj is not None:
        return [obj]
    out = []
    text = content.strip()
    dec = json.JSONDecoder()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in "{[":
            i += 1
            continue
        try:
            val, end = dec.raw_decode(text, i)
            out.append(val)
            i = end
        except Exception:
            i += 1
    return out


# 递归时优先看的键（飞书的字段名就这么几种写法）
_RECORD_KEYS = ('records', 'recordList', 'rows', 'items', 'data', 'result')


def collect_records(obj, out=None):
    """递归收集**所有**长得像 records 的列表（一次抓包里可能有好几处）。

    老版本只返回第一处 —— 分页/多响应时就会漏数据，所以改成全收。
    """
    out = [] if out is None else out
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            out.extend(obj)
        else:
            for it in obj:
                collect_records(it, out)
        return out
    if isinstance(obj, dict):
        for key in _RECORD_KEYS:
            if key in obj:
                collect_records(obj[key], out)
        return out
    return out


def find_total(obj):
    """尽力找出服务端自报的总条数（hint 用）。"""
    if isinstance(obj, dict):
        for k in ('total', 'totalCount', 'total_count', 'count'):
            v = obj.get(k)
            if isinstance(v, int) and v >= 0:
                return v
        for v in obj.values():
            t = find_total(v)
            if t is not None:
                return t
    elif isinstance(obj, list):
        for v in obj:
            t = find_total(v)
            if t is not None:
                return t
    return None


def _drop_dup(records):
    """按 record_id 或字段内容去重（分页抓多次会重叠）。"""
    seen, out = set(), []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        key = rec.get('record_id') or rec.get('id')
        if not key:
            fields = rec.get('fields', rec)
            try:
                key = json.dumps(fields, ensure_ascii=False, sort_keys=True)
            except Exception:
                key = str(fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def cell_text(cell):
    """飞书字段可能是 str / list[{text:..}] / dict{type:text,...} / 数字，展平成字符串。

    优先用 ihub.feishu 那份实现（认得 13 位毫秒时间戳 = 日期），失败才走下面的本地版。
    """
    if _feishu_cell_text is not None:
        try:
            return _feishu_cell_text(cell)
        except Exception:
            pass
    if cell is None:
        return ''
    if isinstance(cell, (int, float, bool)):
        return str(cell)
    if isinstance(cell, str):
        return cell.strip()
    if isinstance(cell, list):
        parts = []
        for it in cell:
            if isinstance(it, dict):
                t = it.get('text') or it.get('name') or it.get('value') or ''
                if t:
                    parts.append(str(t))
            else:
                parts.append(cell_text(it))
        return ''.join(parts).strip()
    if isinstance(cell, dict):
        if 'text' in cell:
            return cell_text(cell['text'])
        if 'value' in cell:
            return cell_text(cell['value'])
        if 'name' in cell:
            return cell_text(cell['name'])
        return json.dumps(cell, ensure_ascii=False)
    return str(cell)


def to_rows(records):
    """records → (表头, 行列表)；每条 record 取 fields 展平"""
    rows, headers, seen = [], [], set()
    flat = []
    for rec in records:
        fields = rec.get('fields', rec) if isinstance(rec, dict) else {}
        row = {str(k): cell_text(v) for k, v in fields.items()}
        flat.append(row)
        for k in row:
            if k not in seen:
                seen.add(k)
                headers.append(k)
    for row in flat:
        rows.append([row.get(h, '') for h in headers])
    return headers, rows


def expand_paths(args):
    """把命令行参数摊平成文件列表：目录 → 里面的 .txt/.json；支持通配符。"""
    files = []
    for a in args:
        if os.path.isdir(a):
            for ext in ('*.txt', '*.json', '*.har'):
                files += sorted(glob.glob(os.path.join(a, ext)))
        elif any(ch in a for ch in '*?['):
            files += sorted(glob.glob(a))
        else:
            files.append(a)
    return files


def main():
    args = sys.argv[1:]
    total_hint = None
    records = []

    if args:
        files = expand_paths(args)
        if not files:
            print('❌ 没找到要解析的文件（目录里没有 .txt / .json）。')
            sys.exit(1)
        for path in files:
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except OSError as e:
                print(f'⚠️ 读不了 {path}：{e}')
                continue
            got = []
            for obj in load_many(content):
                got += collect_records(obj)
                t = find_total(obj)
                total_hint = t if (t is not None and (total_hint is None or t > total_hint)) else total_hint
            before = len(records)
            records += got
            records = _drop_dup(records)
            mark = '新增' if len(records) > before else '全是重复'
            print(f'  · {os.path.basename(path)}：认出 {len(got)} 条 → {mark}（累计 {len(records)} 条）')
    else:
        print('把 Network 里复制的 base64 / JSON 粘贴进来，结束后按 Ctrl+Z 再回车：')
        content = sys.stdin.read()
        for obj in load_many(content):
            records += collect_records(obj)
            t = find_total(obj)
            total_hint = t if (t is not None and (total_hint is None or t > total_hint)) else total_hint
        records = _drop_dup(records)

    if not records:
        print('❌ 内容里没找到 records。确认复制的是 base64（H4sI 开头最常见）或完整 JSON；'
              '也可以把这个文件发给阿枢看结构。')
        sys.exit(1)

    headers, rows = to_rows(records)
    out_dir = os.path.join(ROOT, 'data')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, '飞书岗位导出.csv')
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f'✅ 解出 {len(rows)} 行 × {len(headers)} 列 → {out}')
    if total_hint and total_hint > len(rows):
        print(f'⚠️ 接口自报总条数是 {total_hint}，你这次只拿到 {len(rows)} 条 —— **这是分页**。'
              f'把表往下滚/再抓几次（每次存一个 txt），然后一次传多个文件：'
              f'\n   venv\\Scripts\\python.exe 解码飞书表格.py 抓包1.txt 抓包2.txt 抓包3.txt')
    print('下一步：InternHub 岗位页「📥 导入我的岗位表」→ 通道① 上传这个 CSV（或通道③ 一键读取）。')
    print(f'\n识别到的列：{" | ".join(headers)}')
    if rows[:3]:
        print('\n前几行预览：')
        for r in rows[:3]:
            print(' | '.join(x[:20] for x in r))


if __name__ == '__main__':
    main()
