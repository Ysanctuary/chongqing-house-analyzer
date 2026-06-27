"""
📡 data_fetcher.py - 通用 API 数据获取器

替代 58 同城 HTML 爬虫（反爬严格）
用户输入 API URL，后端调用并入库

使用示例（命令行）：
    python -c "from data_fetcher import fetch_from_api; print(fetch_from_api('https://api.example.com/ershoufang?page={page}', pages=3, page_size=25))"

API 返回 JSON 格式（约定）：
    {
        "data": [
            {
                "id": "abc123",
                "title": "...",
                "district": "渝北区",
                "total_price": 105.0,
                "unit_price": 10500,
                ...
            }
        ]
    }

如果 API 返回结构不同，可通过 field_mapping 参数自定义。
"""
import requests
import time
import logging
import json
from db import batch_insert

logger = logging.getLogger("data_fetcher")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)


# 默认字段映射：API 字段名 → 数据库 houses 表字段名
DEFAULT_FIELD_MAPPING = {
    'id': 'house_code',
    'house_code': 'house_code',
    'title': 'title',
    'district': 'district',
    'bizcircle': 'bizcircle',
    'community': 'community',
    'layout': 'layout',
    'area': 'area',
    'orientation': 'orientation',
    'decoration': 'decoration',
    'floor_info': 'floor_info',
    'building_year': 'building_year',
    'building_type': 'building_type',
    'total_price': 'total_price',
    'price': 'total_price',  # 备选字段名
    'unit_price': 'unit_price',
    'follow_count': 'follow_count',
    'publish_time': 'publish_time',
    'tag': 'tag',
    'url': 'url',
}


def fetch_from_api(api_url, pages=5, page_size=25,
                   extra_headers=None, data_path='data',
                   field_mapping=None, sleep_seconds=2.0,
                   progress_callback=None):
    """
    从用户提供的 API 获取数据并入库

    参数:
        api_url: API URL，支持 {page} / {page_size} / {offset} 占位符
        pages: 翻几页
        page_size: 每页几条
        extra_headers: 额外请求头 dict（如 {"Authorization": "Bearer xxx"}）
        data_path: JSON 里数据数组的路径（点分隔，如 "data.list"），默认 "data"
        field_mapping: 字段映射 dict（API 字段 → DB 字段），默认 DEFAULT_FIELD_MAPPING
        sleep_seconds: 每次请求间隔（防限流）
        progress_callback: 进度回调函数 fn(message: str) -> None

    返回:
        {
            'fetched': int,           # API 返回的有效数据条数
            'inserted': int,          # 实际入库条数
            'pages_ok': int,          # 成功的页数
            'pages_failed': int,      # 失败的页数
            'errors': [str, ...],     # 错误信息列表
        }
    """
    api_url = (api_url or '').strip()
    if not api_url:
        return _result(0, 0, 0, 0, ['API URL 为空'])

    if not api_url.startswith(('http://', 'https://')):
        return _result(0, 0, 0, 0, ['API URL 必须以 http:// 或 https:// 开头'])

    pages = max(1, int(pages))
    page_size = max(1, int(page_size))
    field_mapping = field_mapping or DEFAULT_FIELD_MAPPING

    # 设置 session
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })
    if extra_headers and isinstance(extra_headers, dict):
        session.headers.update(extra_headers)

    log(f"开始调用 API: {api_url[:80]}...")
    log(f"参数: pages={pages}, page_size={page_size}")

    all_items = []
    pages_ok = 0
    pages_failed = 0
    errors = []

    for page in range(1, pages + 1):
        try:
            # 替换 URL 占位符
            url = api_url
            url = url.replace('{page}', str(page))
            url = url.replace('{page_size}', str(page_size))
            url = url.replace('{offset}', str((page - 1) * page_size))

            log(f"  [{page}/{pages}] 请求: {url[:100]}...")

            r = session.get(url, timeout=20)
            r.raise_for_status()

            # 解析 JSON
            try:
                data = r.json()
            except ValueError:
                errors.append(f"Page {page}: 返回不是有效 JSON")
                pages_failed += 1
                continue

            # 提取数据数组
            items = _extract_list(data, data_path)
            if not isinstance(items, list):
                errors.append(f"Page {page}: 数据路径 '{data_path}' 不是数组")
                pages_failed += 1
                continue

            # 字段映射
            converted = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                row = _convert_item(item, field_mapping, all_items)
                if row.get('house_code'):
                    converted.append(row)

            all_items.extend(converted)
            pages_ok += 1
            log(f"  [{page}/{pages}] 获取 {len(items)} 条，转换 {len(converted)} 条")

            # 防限流
            if page < pages:
                time.sleep(sleep_seconds)

        except requests.exceptions.HTTPError as e:
            pages_failed += 1
            err = f"Page {page}: HTTP {e.response.status_code if e.response else '?'} - {str(e)[:80]}"
            errors.append(err)
            log(f"  [{page}/{pages}] {err}")
        except Exception as e:
            pages_failed += 1
            err = f"Page {page}: {str(e)[:100]}"
            errors.append(err)
            log(f"  [{page}/{pages}] {err}")

    # 批量入库
    inserted = 0
    if all_items:
        try:
            inserted = batch_insert(all_items)
            log(f"入库完成: {inserted} 条")
        except Exception as e:
            err = f"入库失败: {str(e)[:100]}"
            errors.append(err)
            log(err)
    else:
        log("没有有效数据可入库")

    result = _result(len(all_items), inserted, pages_ok, pages_failed, errors)
    log(f"完成: fetched={result['fetched']}, inserted={result['inserted']}, "
        f"成功 {result['pages_ok']} 页，失败 {result['pages_failed']} 页")
    return result


def _result(fetched, inserted, pages_ok, pages_failed, errors):
    return {
        'fetched': fetched,
        'inserted': inserted,
        'pages_ok': pages_ok,
        'pages_failed': pages_failed,
        'errors': errors or [],
    }


def _extract_list(data, path):
    """从 JSON 里按路径提取列表"""
    if not path:
        return data if isinstance(data, list) else []
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return []
    return current if isinstance(current, list) else []


def _convert_item(item, mapping, existing_items):
    """根据字段映射转换一条数据"""
    row = {}
    for api_field, db_field in mapping.items():
        if api_field in item:
            value = item[api_field]
            # 转换空值
            if value is None or value == '':
                continue
            row[db_field] = value

    # 确保 house_code 有值（用 title 哈希 或 序号 生成 fallback）
    if not row.get('house_code'):
        # 用 URL 末尾或 title 第一个词 + 序号
        import hashlib
        seed = (row.get('url', '') or row.get('title', '')) + str(len(existing_items))
        row['house_code'] = 'API_' + hashlib.md5(seed.encode()).hexdigest()[:14].upper()

    return row


def log(msg):
    """统一日志输出"""
    logger.info(msg)


# ==================== 命令行入口 ====================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python data_fetcher.py <api_url> [pages] [page_size]")
        print("示例: python data_fetcher.py 'https://api.example.com/ershoufang?page={page}' 5 25")
        sys.exit(1)

    api_url = sys.argv[1]
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    page_size = int(sys.argv[3]) if len(sys.argv) > 3 else 25

    result = fetch_from_api(api_url, pages=pages, page_size=page_size)
    print("\n=== 结果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
