"""
58同城 m 端重庆二手房爬虫
URL 模板: https://m.58.com/cq/ershoufang/pn{页码}/
       或: https://m.58.com/cq/ershoufang/{区域}/pn{页码}/

反爬策略:
- 使用 curl_cffi 模拟真实 Chrome TLS 指纹
- 真实 cookie（用户提供的 58 账号）
- 请求延迟 3-5 秒
- 每 30 页换一次 cookie 上下文
- 检测到反爬时自动暂停 5 分钟重试
"""
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

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_DIR + "/spider_58m.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("spider58m")


# 58 m 端重庆区县（拼音 → 中文）
# 注意：58 URL 尚未更新两江新区，yubei 实际对应两江新区
# 已剔除：beibin(北滨路)/jiabin(江北)/nanping(南坪)/shaping(沙坪坝)/yangjiaping(杨家坪) 为子区域
# 已剔除：yueyang/shuangbei 重复；jiangbei 并入两江新区；wanshan 并入綦江
# 已剔除：kaixian/liangshan/peng'an/yilong/nanchong/guang'an/guangyuan 非重庆行政区
M58_DISTRICTS = {
    # 主城（8 区，江北区已并入两江新区）
    "yuzhong":   "渝中区",
    "yubei":     "两江新区",
    "nanan":     "南岸区",
    "shapingba": "沙坪坝区",
    "jiulongpo": "九龙坡区",
    "dadukou":   "大渡口区",
    "banan":     "巴南区",
    "beibei":    "北碚区",
    # 渝西
    "dazu":      "大足区",
    "jiangjin":  "江津区",
    "yongchuan": "永川区",
    "hechuan":   "合川区",
    "tongliang": "铜梁区",
    "bishan":    "璧山区",
    "qijiang":   "綦江区",
    "rongchang": "荣昌区",
    "tongnan":   "潼南区",
    # 渝东北
    "wanzhou":   "万州区",
    "kaizhou":   "开州区",
    "liangping": "梁平区",
    "changshou": "长寿区",
    "fengjie":   "奉节县",
    "wushan":    "巫山县",
    "wuxi":      "巫溪县",
    "yunyang":   "云阳县",
    "zhongxian": "忠县",
    "fengdu":    "丰都县",
    "dianjiang": "垫江县",
    "chengkou":  "城口县",
    # 渝东南
    "qianjiang": "黔江区",
    "nanchuan":  "南川区",
    "wulong":    "武隆区",
    "pengshui":  "彭水县",
    "youyang":   "酉阳县",
    "xiushan":   "秀山县",
    "shizhu":    "石柱县",
}

# 全部 36 个区县
CORE_DISTRICTS_M58 = list(M58_DISTRICTS.keys())


def load_cookie(cookie_file: str = None) -> str:
    """从文件加载 cookie"""
    if cookie_file and Path(cookie_file).exists():
        return Path(cookie_file).read_text(encoding="utf-8").strip()
    # 兜底用环境变量
    import os
    return os.environ.get("M58_COOKIE", "")


class M58Spider:
    BASE = "https://m.58.com/cq/ershoufang"

    def __init__(self, cookie_str: str, districts: list = None, max_pages: int = 30):
        self.cookie_str = cookie_str
        self.districts = districts or CORE_DISTRICTS_M58
        self.max_pages = max_pages
        self.session = self._build_session()
        self.total_new = 0
        self.antibot_streak = 0  # 连续被反爬次数

    def _build_session(self):
        s = cffi_requests.Session(impersonate="chrome120")
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "sec-ch-ua": '" Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })
        if self.cookie_str:
            s.headers["Cookie"] = self.cookie_str
        return s

    def _sleep(self, base: float = None):
        """页面间延迟：默认 15s（防限流）"""
        if base is None:
            base = random.uniform(14.0, 16.0)
        time.sleep(base)

    def _fetch(self, url: str) -> str:
        for i in range(5):
            try:
                r = self.session.get(url, timeout=20, allow_redirects=True)
                # 检测反爬
                if "antibot" in r.text or "verifycode" in r.text or len(r.text) < 1000:
                    self.antibot_streak += 1
                    if self.antibot_streak >= 5:
                        log.warning(f"连续被反爬 {self.antibot_streak} 次，暂停 3 分钟")
                        time.sleep(180)
                        self.antibot_streak = 0
                    else:
                        time.sleep(15)
                    continue
                # 正常
                self.antibot_streak = 0
                return r.text
            except Exception as e:
                log.warning(f"请求失败 {i+1}: {e}")
                time.sleep(5 * (i + 1))
        return ""

    @staticmethod
    def _parse_text_blob(text: str) -> dict:
        """
        58 m 端把房源信息拼在 a 的 text 字段里:
        "18中旁 城市印象 精装3房 业主诚心出售  安心卖3室2厅115.68㎡南
         两江新区北滨路南唯一住房近地铁104万8991元/㎡"
        """
        # 拆字段
        result = {
            "title": "",
            "layout": "",
            "area": None,
            "orientation": "",
            "bizcircle": "",
            "decoration": "",
            "tags": "",
            "total_price": 0.0,
            "unit_price": 0.0,
        }
        # 总价 + 单价（万/元/㎡，可能中间有空格）
        m = re.search(r'(\d+(?:\.\d+)?)\s*万\s*(\d+(?:,\d{3})*)\s*元\s*/\s*㎡', text)
        if m:
            result["total_price"] = float(m.group(1))
            result["unit_price"] = float(m.group(2).replace(",", ""))

        # 户型 + 面积
        m = re.search(r'(\d+)室(\d+)厅\s*(\d+(?:\.\d+)?)平?米?', text)
        if m:
            result["layout"] = f"{m.group(1)}室{m.group(2)}厅"
            result["area"] = float(m.group(3))
        else:
            # 备选：只有室没有厅
            m = re.search(r'(\d+)室\s*(\d+(?:\.\d+)?)平?米?', text)
            if m:
                result["layout"] = f"{m.group(1)}室"
                result["area"] = float(m.group(2))
            else:
                m = re.search(r'(\d+(?:\.\d+)?)平?米?', text)
                if m:
                    result["area"] = float(m.group(1))

        # 朝向：取【平米/㎡】后第一个连续方位词（1-4个字符）
        m = re.search(r'(?:平?米?|㎡)([东南西北]+)', text)
        if m and m.group(1):
            result["orientation"] = m.group(1)

        # 装修
        for dec in ['精装', '简装', '豪装', '毛坯', '其他']:
            if dec in text:
                result["decoration"] = dec
                break

        # 板块/区域（"两江新区北滨路南" 这样的格式）
        # 58 字段：区名 + 板块
        m = re.search(r'(渝中区|江北区|渝北区|南岸区|沙坪坝区|九龙坡区|大渡口区|巴南区|北碚区|两江新区|北部新区|高新区|经开区)', text)
        if m:
            result["district_name"] = m.group(1)

        # 板块（板块+方位）
        m = re.search(r'(两江新区|北部新区)?(北滨路|南滨路|解放碑|观音桥|南坪|杨家坪|沙坪坝|大坪|石桥铺|新牌坊|加州|冉家坝|人和|汽博|回兴|空港|龙头寺|红旗河沟|花卉园|花卉西|江北嘴|五里店|华新街|寸滩|唐家沱|弹子石|上新街|涂山路|南坪|铜元局|工贸|海峡路|四公里|南湖|弹子石)', text)
        if m:
            result["bizcircle"] = m.group(2)

        # 标题：取第一段不含数字单位的文字
        # 58 的 title 是 描述，含有 "精装3房" 等
        title_match = re.search(r'^(.*?)(?=\d+室|\d+平米|两江|江北|渝北|南岸|沙坪坝|九龙坡|大渡口|巴南|北碚)', text)
        if title_match:
            result["title"] = title_match.group(1).strip()
        else:
            result["title"] = text[:80]

        return result

    def _parse_page(self, html: str, district: str) -> list:
        """解析一页"""
        soup = BeautifulSoup(html, "lxml")
        # 58 m 端每个房源 a 标签 class 包含 "pic" 或在 .house-list 中
        # 简化: 找所有 a[href*="ershoufang/"][href*=".shtml"]
        items = []
        for a in soup.select('a[href*="ershoufang/"]'):
            href = a.get("href", "")
            if ".shtml" not in href:
                continue
            m = re.search(r'/ershoufang/(\d+)x?\.shtml', href)
            if not m:
                continue
            house_code = m.group(1)
            text = a.get_text(" ", strip=True)
            if not text or "万" not in text:
                continue

            parsed = self._parse_text_blob(text)
            parsed["house_code"] = house_code
            parsed["district"] = district
            parsed["url"] = href if href.startswith("http") else "https://m.58.com" + href
            parsed["raw_text"] = text[:200]
            items.append(parsed)
        return items

    def crawl_district(self, district: str):
        log.info(f"=== 开始: {district} ({M58_DISTRICTS.get(district, '')}) ===")
        page = 1
        new_in_district = 0
        batch = []
        empty_streak = 0
        page_times = []  # 记录每页耗时（秒）

        while page <= self.max_pages:
            url = f"{self.BASE}/{district}/pn{page}/"
            t0 = time.time()
            log.info(f"  [{district}] pn{page} 请求...")
            html = self._fetch(url)
            if not html:
                empty_streak += 1
                if empty_streak >= 3:
                    log.warning(f"  [{district}] 连续失败，停止")
                    break
                self._sleep()
                continue

            items = self._parse_page(html, district)
            elapsed = time.time() - t0
            page_times.append(elapsed)
            log.info(f"  [{district}] pn{page} 解析到 {len(items)} 条, 耗时 {elapsed:.1f}s")

            if not items:
                empty_streak += 1
                if empty_streak >= 2:
                    log.info(f"  [{district}] 连续空页，停止")
                    break
            else:
                empty_streak = 0
                for it in items:
                    if not it.get("unit_price") or it.get("unit_price", 0) <= 0:
                        continue
                    batch.append({
                        "house_code": it.get("house_code", ""),
                        "title": it.get("title", ""),
                        "district": it.get("district_name", district),
                        "bizcircle": it.get("bizcircle", ""),
                        "community": "",  # 列表里没解析到，留空
                        "layout": it.get("layout", ""),
                        "area": it.get("area"),
                        "orientation": it.get("orientation", ""),
                        "decoration": it.get("decoration", ""),
                        "floor_info": "",
                        "building_year": None,
                        "building_type": "",
                        "total_price": it.get("total_price", 0),
                        "unit_price": it.get("unit_price", 0),
                        "follow_count": 0,
                        "publish_time": "",
                        "tag": it.get("tags", ""),
                        "url": it.get("url", ""),
                    })

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
            log.info(f"=== {district} 完成, 本次入库 {new_in_district}, 未抓到页 ===")
        self.total_new += new_in_district
        return new_in_district

    def run(self):
        log.info(f"===== 58m 启动 =====")
        log.info(f"区县: {len(self.districts)}, 每区最多 {self.max_pages} 页")
        log.info(f"起始库: {count()}")
        log.info(f"翻页间隔: 14-16s")
        run_start = time.time()
        init_database()
        for d in self.districts:
            try:
                self.crawl_district(d)
            except KeyboardInterrupt:
                log.warning("中断")
                break
            except Exception as e:
                log.exception(f"{d} 出错: {e}")
                time.sleep(30)
        total_seconds = time.time() - run_start
        log.info(f"===== 完成, 本次新增 {self.total_new}, 总数 {count()}, "
                 f"总耗时 {total_seconds:.0f}s ({total_seconds/60:.1f}min) =====")


if __name__ == "__main__":
    import sys
    cookie = load_cookie("data/cookie.txt")
    if not cookie:
        print("请把 cookie 写入 data/cookie.txt")
        sys.exit(1)
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    districts = CORE_DISTRICTS_M58
    if len(sys.argv) > 2:
        districts = sys.argv[2].split(",")
    spider = M58Spider(cookie, districts=districts, max_pages=max_pages)
    spider.run()
