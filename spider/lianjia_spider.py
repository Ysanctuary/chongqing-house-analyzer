"""
链家 m 端重庆二手房爬虫（你已登录）
URL: https://m.lianjia.com/cq/ershoufang/{district}/pg{page}/

特点：
- 需要登录 cookie（data/lianjia_cookie_header.txt）
- TLS 指纹模拟（curl_cffi + chrome120）
- 30s/页（防限流）
- 记录每页耗时
- 区县分拼音：yuzhong, jiangbei, yubei, nanan, shapingba, jiulongpo, dadukou, banan, beibei
"""
import os
import sys
# 允许以两种方式运行：
#   1. python spider/lianjia_spider.py 100        (需要把项目根加入 path)
#   2. python -m spider.lianjia_spider 100        (推荐)
_this_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.dirname(_this_dir)
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

import re
import time
import random
import json
import logging
from pathlib import Path
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

import config
from db import batch_insert, init_database, count

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_DIR + "/spider_lianjia.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("spider_lj")

# 链家 m 端区县（重庆 37 个区县全覆盖）
LIANJIA_DISTRICTS = {
    # 主城九区
    "yuzhong":   "渝中区",
    "jiangbei":  "江北区",
    "yubei":     "渝北区",
    "nanan":     "南岸区",
    "shapingba": "沙坪坝区",
    "jiulongpo": "九龙坡区",
    "dadukou":   "大渡口区",
    "banan":     "巴南区",
    "beibei":    "北碚区",
    # 渝西
    "yongchuan":   "永川区",
    "hechuan":     "合川区",
    "jiangjin":    "江津区",
    "dazu":        "大足区",
    "qijiang":     "綦江区",
    "tongnan":     "潼南区",
    "tongliang":   "铜梁区",
    "bishan":      "璧山区",
    "rongchang":   "荣昌区",
    # 渝东北
    "wanzhou":     "万州区",
    "kaizhou":     "开州区",
    "liangping":   "梁平区",
    "changshou":   "长寿区",
    "fengjie":     "奉节县",
    "wushan":      "巫山县",
    "yunyang":     "云阳县",
    "zhongxian":   "忠县",
    "fengdu":      "丰都县",
    "dianjiang":   "垫江县",
    "wuxi":        "巫溪县",
    "chengkou":    "城口县",
    # 渝东南
    "nanchuan":    "南川区",
    "pengshui":    "彭水县",
    "youyang":     "酉阳县",
    "xiushan":     "秀山县",
    "shizhu":      "石柱县",
    "wulong":      "武隆区",
    "qianjiang":   "黔江区",
}
CORE_DISTRICTS_LJ = list(LIANJIA_DISTRICTS.keys())


def load_cookie(cookie_file: str = None) -> str:
    """加载链家 cookie（Header String 格式）"""
    if cookie_file and Path(cookie_file).exists():
        return Path(cookie_file).read_text(encoding="utf-8").strip()
    # 兜底：找项目里所有 cookie 文件
    for p in ["data/lianjia_cookie_header.txt", "data/lianjia_cookie.txt", "data/cookie.txt"]:
        full = config.BASE_DIR + "\\" + p
        if Path(full).exists():
            log.info(f"使用 cookie: {p}")
            return Path(full).read_text(encoding="utf-8").strip()
    return ""


class LianjiaSpider:
    BASE = "https://m.lianjia.com/cq/ershoufang"

    def __init__(self, cookie_str: str, districts: list = None, max_pages: int = 30,
                 sleep_min: float = 28.0, sleep_max: float = 32.0):
        self.cookie_str = cookie_str
        self.districts = districts or CORE_DISTRICTS_LJ
        self.max_pages = max_pages
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self.session = self._build_session()
        self.total_new = 0
        self.antibot_streak = 0

    def _build_session(self):
        s = cffi_requests.Session(impersonate="chrome120")
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "sec-ch-ua": '" Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"iOS"',
        })
        if self.cookie_str:
            s.headers["Cookie"] = self.cookie_str
        return s

    def _sleep(self):
        delay = random.uniform(self.sleep_min, self.sleep_max)
        time.sleep(delay)

    def _fetch(self, url: str) -> str:
        """带重试的请求"""
        for i in range(3):
            try:
                r = self.session.get(url, timeout=20, allow_redirects=True)
                # 检测反爬
                if "CAPTCHA" in r.text or "captcha" in r.text.lower()[:2000] or "登录" in r.text[:1000] and "请先登录" in r.text:
                    self.antibot_streak += 1
                    log.warning(f"被反爬/要求登录（第 {self.antibot_streak} 次）")
                    if self.antibot_streak >= 3:
                        log.warning("连续被反爬 3 次，暂停 5 分钟")
                        time.sleep(300)
                        self.antibot_streak = 0
                    time.sleep(20)
                    continue
                if len(r.text) < 5000:
                    log.warning(f"响应太短 {len(r.text)}B")
                    time.sleep(10)
                    continue
                self.antibot_streak = 0
                return r.text
            except Exception as e:
                log.warning(f"请求失败 {i+1}: {e}")
                time.sleep(5 * (i + 1))
        return ""

    @staticmethod
    def _parse_item(tile, district: str) -> dict:
        """解析单条房源（<div class="kem__house-tile-ershou">）"""
        try:
            data_id = tile.get("data-id", "")
            if not data_id:
                return None

            # 标题
            title_div = tile.select_one(".house-title")
            title = title_div.get_text(strip=True) if title_div else ""

            # 描述（包含户型/面积/朝向/小区）
            # 链家 m 端格式："2室1厅/51.33㎡/东南/橡树东村"  （用 / 分隔，title 存全）
            desc_div = tile.select_one(".house-desc")
            desc_attrs = {}
            if desc_div:
                desc_full = desc_div.get("title", "")
                if not desc_full:
                    desc_full = desc_div.get_text(strip=True)
                desc_attrs = {"raw": desc_full}
                # 用 / 分隔
                parts = [p.strip() for p in desc_full.split("/") if p.strip()]
                if len(parts) >= 1:
                    desc_attrs["layout"] = parts[0]
                if len(parts) >= 2:
                    # 链家 m 端用 "m²" （U+006D + U+00B2），而不是 "㎡"
                    m = re.search(r"([\d.]+)\s*m\u00b2", parts[1])
                    if m:
                        desc_attrs["area"] = float(m.group(1))
                if len(parts) >= 3:
                    desc_attrs["orientation"] = parts[2]
                if len(parts) >= 4:
                    desc_attrs["community"] = parts[3]
                if len(parts) >= 5:
                    desc_attrs["bizcircle"] = parts[4]

            # 标签
            tag_spans = tile.select(".house-tags .tag")
            tags = [s.get("title", s.get_text(strip=True)) for s in tag_spans]

            # 价格
            price_total = 0.0
            price_unit = 0.0
            total_span = tile.select_one(".price-total")
            if total_span:
                m = re.search(r"([\d.]+)", total_span.get_text())
                if m:
                    price_total = float(m.group(1))
            unit_span = tile.select_one(".price-unit")
            if unit_span:
                m = re.search(r"([\d,]+)", unit_span.get_text())
                if m:
                    price_unit = float(m.group(1).replace(",", ""))

            # 详情 URL（m 端规则）
            detail_url = f"https://m.lianjia.com/cq/ershoufang/{data_id}.html"

            return {
                "house_code": f"{district}_{data_id}",  # 链家同一房在多个区会重复列出，用 区县_ID 作为唯一键
                "title": title,
                "district": district,
                "bizcircle": desc_attrs.get("bizcircle", ""),
                "community": desc_attrs.get("community", ""),
                "layout": desc_attrs.get("layout", ""),
                "area": desc_attrs.get("area"),
                "orientation": desc_attrs.get("orientation", ""),
                "decoration": "",  # 列表里没显示
                "floor_info": "",
                "building_year": None,
                "building_type": "",
                "total_price": price_total,
                "unit_price": price_unit,
                "follow_count": 0,
                "publish_time": "",
                "tag": "|".join(tags),
                "url": detail_url,
            }
        except Exception as e:
            log.warning(f"解析失败: {e}")
            return None

    def _parse_page(self, html: str, district: str) -> list:
        """解析整页（30 条）"""
        soup = BeautifulSoup(html, "lxml")
        tiles = soup.select(".kem__house-tile-ershou")
        items = []
        for tile in tiles:
            item = self._parse_item(tile, district)
            if item and item.get("unit_price", 0) > 0:
                items.append(item)
        return items

    def crawl_district(self, district: str):
        log.info(f"=== 开始: {district} ({LIANJIA_DISTRICTS.get(district, '')}) ===")
        page = 1
        new_in_district = 0
        batch = []
        empty_streak = 0
        page_times = []

        while page <= self.max_pages:
            url = f"{self.BASE}/{district}/pg{page}/"
            t0 = time.time()
            log.info(f"  [{district}] pg{page} 请求...")
            html = self._fetch(url)
            if not html:
                empty_streak += 1
                if empty_streak >= 3:
                    log.warning(f"  [{district}] 连续 3 页失败，停止")
                    break
                self._sleep()
                continue

            items = self._parse_page(html, district)
            elapsed = time.time() - t0
            page_times.append(elapsed)
            log.info(f"  [{district}] pg{page} 解析到 {len(items)} 条, 耗时 {elapsed:.1f}s")

            if not items:
                empty_streak += 1
                if empty_streak >= 2:
                    log.info(f"  [{district}] 连续空页，已到末页")
                    break
            else:
                empty_streak = 0
                batch.extend(items)

                # 批量入库
                if len(batch) >= 50:
                    n = batch_insert(batch)
                    new_in_district += n
                    log.info(f"  累计入库 {new_in_district}")
                    batch = []

            page += 1
            self._sleep()

        # 收尾
        if batch:
            n = batch_insert(batch)
            new_in_district += n

        # 总结
        if page_times:
            avg = sum(page_times) / len(page_times)
            total = sum(page_times)
            log.info(f"=== {district} 完成: 入库 {new_in_district}, 爬取页 {len(page_times)}, "
                     f"总耗时 {total:.0f}s (平均 {avg:.1f}s/页) ===")
        else:
            log.info(f"=== {district} 完成: 未抓到页 ===")
        self.total_new += new_in_district
        return new_in_district

    def run(self):
        log.info(f"===== 链家 m 端启动 =====")
        log.info(f"区县: {len(self.districts)}, 每区最多 {self.max_pages} 页")
        log.info(f"翻页间隔: {self.sleep_min:.0f}-{self.sleep_max:.0f}s")
        log.info(f"起始库: {count()}")
        run_start = time.time()
        init_database()
        for d in self.districts:
            try:
                self.crawl_district(d)
            except KeyboardInterrupt:
                log.warning("用户中断")
                break
            except Exception as e:
                log.exception(f"{d} 出错: {e}")
                time.sleep(30)
        total_seconds = time.time() - run_start
        log.info(f"===== 完成, 本次新增 {self.total_new}, 总数 {count()}, "
                 f"总耗时 {total_seconds:.0f}s ({total_seconds/60:.1f}min) =====")


if __name__ == "__main__":
    import sys
    cookie = load_cookie()
    if not cookie:
        print("请把 cookie 写入 data/lianjia_cookie_header.txt")
        sys.exit(1)
    max_pages = 30
    districts = CORE_DISTRICTS_LJ
    if len(sys.argv) > 1:
        max_pages = int(sys.argv[1])
    if len(sys.argv) > 2:
        districts = sys.argv[2].split(",")
    spider = LianjiaSpider(cookie, districts=districts, max_pages=max_pages)
    spider.run()
