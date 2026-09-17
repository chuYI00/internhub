#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""解码飞书多维表格抓包数据 → CSV（接 InternHub 导入）

用法（任选其一）：
    venv\\Scripts\\python.exe 解码飞书表格.py 抓包.txt        # 文件里是 base64 字符串或 JSON
    venv\\Scripts\\python.exe 解码飞书表格.py                 # 交互：把内容粘贴后回车，再按 Ctrl+Z 回车结束

内容可以是三种之一（自动识别）：
  1. Network 里复制的 base64（通常 H4sI 开头 = gzip 压缩的 JSON）
  2. 解压后的 JSON 文本（含 records 字段）
  3. 已经是表格文本的（直接转存）

输出：data/飞书岗位导出.csv（utf-8-sig，Excel/本工具导入向导都能直接用）
"""
import base64
import csv
import gzip
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


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


def find_records(obj):
    """递归找长得像 records 列表的字段"""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict):
        for key in ('records', 'recordList', 'rows', 'items', 'data'):
            if key in obj:
                found = find_records(obj[key])
                if found:
                    return found
        # 兜底：遍历所有值
        for v in obj.values():
            if isinstance(v, (list, dict)):
                found = find_records(v)
                if found:
                    return found
    return None


def cell_text(cell):
    """飞书字段可能是 str / list[{text:..}] / dict{type:text,...} / 数字，展平成字符串"""
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


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
        with open(path, encoding='utf-8', errors='replace') as f:
            content = f.read()
    else:
        print('把 Network 里复制的 base64 / JSON 粘贴进来，结束后按 Ctrl+Z 再回车：')
        content = sys.stdin.read()

    obj = try_decode(content)
    if obj is None:
        print('❌ 没认出来。确认复制的是 base64（H4sI 开头最常见）或完整 JSON。')
        sys.exit(1)

    records = find_records(obj)
    if not records:
        print('❌ 内容里没找到 records。把整个 JSON 发给阿枢看结构。')
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
    print('下一步：InternHub 岗位页「📥 导入我的岗位表」→ 上传这个 CSV。')
    if rows[:3]:
        print('\n前几行预览：')
        for r in rows[:3]:
            print(' | '.join(x[:20] for x in r))


if __name__ == '__main__':
    main()
