"""
链家 m 端人机协作爬虫（Pro 版）

在原版 lianjia_spider.py 基础上增加 Playwright 人机验证接管：
- 正常爬取阶段使用 curl_cffi（快）
- 检测到反爬/验证码时，自动弹出系统 Chrome 浏览器窗口
- 用户在弹出的浏览器中手动完成验证
- 验证通过后自动提取 cookie 回传给 curl_cffi 继续爬取
- 支持多次验证（每区最多 3 次，防止无限弹窗）

依赖: pip install playwright（使用系统已安装的 Chrome，无需额外下载浏览器）
"""
import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_proj_root = os.path.dirname(_this_dir)
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

import re
import time
import random
import logging
from pathlib import Path

from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

import config
from db import batch_insert, init_database, count

# ── 日志 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_DIR + "/spider_lianjia_pro.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("spider_lj_pro")

# ── 常量 ──────────────────────────────────────────────
BASE = "https://m.lianjia.com/cq/ershoufang"

# 连续被反爬多少次后触发 Playwright 验证
CAPTCHA_TRIGGER_STREAK = 2
# 每个区连续验证失败几次后停止弹窗（成功不计入，防止无限弹窗但不限制成功次数）
MAX_VERIFY_FAILS = 3
# Playwright 等待用户验证的最长时间（秒）
VERIFY_TIMEOUT = 150

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
    for p in ["data/lianjia_cookie_header.txt", "data/lianjia_cookie.txt", "data/cookie.txt"]:
        full = config.BASE_DIR + "\\" + p
        if Path(full).exists():
            log.info(f"使用 cookie: {p}")
            return Path(full).read_text(encoding="utf-8").strip()
    return ""


# ═══════════════════════════════════════════════════════
#  LianjiaProSpider — 人机协作版
# ═══════════════════════════════════════════════════════
class LianjiaProSpider:

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
        self.verify_fail_streak = 0    # 当前区连续验证失败次数（成功时归零）
        self.total_verifies = 0        # 全局验证成功次数统计

    # ── session ──────────────────────────────────────
    def _build_session(self):
        s = cffi_requests.Session(impersonate="chrome120")
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                "Mobile/15E148 Safari/604.1"
            ),
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

    # ── 反爬检测 ─────────────────────────────────────
    @staticmethod
    def _is_captcha_page(text: str) -> bool:
        """判断响应是否为验证码 / 反爬拦截页

        实际验证码页 (hip.lianjia.com/captcha) 特征:
        - ~1850 字符
        - 包含 "人机验证"、"CAPTCHA"、"验证失败"、"重新验证"
        - 不包含房源列表内容
        """
        if not text:
            return True
        low = text.lower()
        # 链家验证码页确切关键词
        if "人机验证" in text:
            return True
        if "captcha" in low:
            return True
        # 频率限制（保留）
        if "访问过于频繁" in text:
            return True
        # 页面极短（验证码页 ~1850 字符；正常移动列表页通常 >3000）
        if len(text) < 2000:
            return True
        return False

    # ── Playwright 人机验证 ──────────────────────────
    def _playwright_verify(self, url: str) -> bool:
        """
        弹出真实 Chrome 浏览器让用户手动完成验证码。
        验证通过后提取 cookie 回传给 curl_cffi session。
        返回 True = 验证成功，False = 失败 / 超时 / 用户关闭。
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error(
                "Playwright 未安装。请执行:\n"
                "  pip install playwright"
            )
            return False

        if self.verify_fail_streak >= MAX_VERIFY_FAILS:
            log.warning(
                f"本区连续验证失败 {self.verify_fail_streak} 次（上限 {MAX_VERIFY_FAILS}），跳过"
            )
            return False

        log.info(f"━━━ 人机验证（本区失败 {self.verify_fail_streak}/{MAX_VERIFY_FAILS}） ━━━")
        log.info(f"  URL: {url}")
        log.info("  >>> 即将弹出浏览器窗口，请在窗口中完成验证 <<<")

        pw = None
        browser = None
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            context = browser.new_context(
                viewport={"width": 430, "height": 932},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
            )

            # 把当前 cookie 注入到 Playwright
            if self.cookie_str:
                cookies = []
                for pair in self.cookie_str.split(";"):
                    pair = pair.strip()
                    if "=" in pair:
                        name, value = pair.split("=", 1)
                        cookies.append({
                            "name": name.strip(),
                            "value": value.strip(),
                            "domain": ".lianjia.com",
                            "path": "/",
                        })
                if cookies:
                    context.add_cookies(cookies)

            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1)

            title = page.title()
            log.info(f"  浏览器已打开 (标题: {title})")
            log.info("  >>> 请在浏览器中完成验证，等待自动检测... <<<")

            # ── 轮询等待用户完成验证 ──
            waited = 0
            verified = False
            while waited < VERIFY_TIMEOUT:
                time.sleep(2)
                waited += 2

                try:
                    cur_url = page.url
                    cur_title = page.title()
                    cur_text = page.inner_text("body")
                    cur_html = page.content()
                except Exception:
                    log.warning("  浏览器窗口已关闭")
                    break

                cur_len = len(cur_text)

                # 强信号：URL 已离开验证码域 → 验证通过
                if "captcha" not in cur_url.lower():
                    has_listings = (
                        ("kem__house-tile-ershou" in cur_html)
                        or ("室" in cur_text and "厅" in cur_text and "万" in cur_text)
                    )
                    if has_listings:
                        verified = True
                        log.info(f"  ✅ 验证通过！(URL 已离开验证码域, 耗时 {waited}s)")
                        break
                    # URL 离开了验证码域但还没列表 — 可能还在加载
                    if waited % 5 == 0:
                        log.info(f"  ⏳ URL 已跳转但列表未加载 (len={cur_len}, "
                                 f"url={cur_url[:60]})")
                    continue

                # 仍在验证码域 — 用内容检测
                still_captcha = self._is_captcha_page(cur_text)

                # 每 5 秒输出调试信息
                if waited % 5 == 0:
                    log.info(f"  ⏳ 等待验证... ({waited}s/{VERIFY_TIMEOUT}s, "
                             f"len={cur_len}, captcha={still_captcha}, "
                             f"url={cur_url[:60]})")

                if not still_captcha:
                    # 内容已不是验证码页
                    has_listings = (
                        ("kem__house-tile-ershou" in cur_html)
                        or ("室" in cur_text and "厅" in cur_text and "万" in cur_text)
                    )
                    if has_listings:
                        verified = True
                        log.info(f"  ✅ 验证通过！(耗时 {waited}s, 新标题: {cur_title})")
                        break

            if not verified:
                self.verify_fail_streak += 1
                if waited >= VERIFY_TIMEOUT:
                    log.warning(f"  ⏰ 验证超时（连续失败 {self.verify_fail_streak}/{MAX_VERIFY_FAILS}）")
                else:
                    log.warning(f"  ❌ 验证未完成（连续失败 {self.verify_fail_streak}/{MAX_VERIFY_FAILS}）")

            # ── 提取 cookie 回传 ──
            if verified:
                self.verify_fail_streak = 0
                self.total_verifies += 1
                try:
                    new_cookies = context.cookies()
                    cookie_parts = [
                        f"{c['name']}={c['value']}"
                        for c in new_cookies
                        if c.get("domain", "").endswith("lianjia.com")
                    ]
                    if cookie_parts:
                        self.cookie_str = "; ".join(cookie_parts)
                        self.session = self._build_session()
                        log.info(f"  🍪 已提取 {len(cookie_parts)} 个 cookie 并回传")
                except Exception as e:
                    log.warning(f"  提取 cookie 失败: {e}")

            return verified

        except Exception as e:
            log.error(f"  Playwright 验证异常: {e}")
            return False

        finally:
            try:
                if browser:
                    browser.close()
                if pw:
                    pw.stop()
            except Exception:
                pass

    # ── 带验证码处理的请求 ──────────────────────────
    def _fetch(self, url: str) -> str:
        """请求页面，遇到反爬时触发 Playwright 人机验证"""
        for i in range(5):
            try:
                r = self.session.get(url, timeout=20, allow_redirects=True)

                if self._is_captcha_page(r.text):
                    self.antibot_streak += 1
                    log.warning(f"  反爬检测 (streak={self.antibot_streak})")

                    if self.antibot_streak >= CAPTCHA_TRIGGER_STREAK:
                        # ── 尝试人机验证 ──
                        if self.verify_fail_streak < MAX_VERIFY_FAILS:
                            log.info("  🤝 触发 Playwright 人机协作验证...")
                            ok = self._playwright_verify(url)
                            if ok:
                                self.antibot_streak = 0
                                # 用新 cookie 重试当前 URL
                                try:
                                    r2 = self.session.get(url, timeout=20,
                                                        allow_redirects=True)
                                    if not self._is_captcha_page(r2.text):
                                        return r2.text
                                except Exception:
                                    pass
                                # 重试也失败 → 回到循环下一轮
                                continue
                            else:
                                log.warning("  验证失败，退回到等待模式")
                                self.antibot_streak = 0

                        # 验证次数耗尽 or 验证失败 → 纯等待
                        if self.antibot_streak >= 3:
                            log.warning("  连续被反爬 3 次，暂停 5 分钟")
                            time.sleep(300)
                            self.antibot_streak = 0
                        else:
                            time.sleep(20)
                    else:
                        time.sleep(15)
                    continue

                # 正常响应
                self.antibot_streak = 0
                return r.text

            except Exception as e:
                log.warning(f"  请求失败 {i+1}: {e}")
                time.sleep(5 * (i + 1))

        return ""

    # ── 解析（复用原版逻辑） ────────────────────────
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

            # 描述（户型/面积/朝向/小区/板块）
            desc_div = tile.select_one(".house-desc")
            desc_attrs = {}
            if desc_div:
                desc_full = desc_div.get("title", "")
                if not desc_full:
                    desc_full = desc_div.get_text(strip=True)
                desc_attrs = {"raw": desc_full}
                parts = [p.strip() for p in desc_full.split("/") if p.strip()]
                if len(parts) >= 1:
                    desc_attrs["layout"] = parts[0]
                if len(parts) >= 2:
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

            # 详情 URL
            detail_url = f"https://m.lianjia.com/cq/ershoufang/{data_id}.html"

            return {
                "house_code": f"{district}_{data_id}",
                "title": title,
                "district": district,
                "bizcircle": desc_attrs.get("bizcircle", ""),
                "community": desc_attrs.get("community", ""),
                "layout": desc_attrs.get("layout", ""),
                "area": desc_attrs.get("area"),
                "orientation": desc_attrs.get("orientation", ""),
                "decoration": "",
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
        """解析整页"""
        soup = BeautifulSoup(html, "lxml")
        tiles = soup.select(".kem__house-tile-ershou")
        items = []
        for tile in tiles:
            item = self._parse_item(tile, district)
            if item and item.get("unit_price", 0) > 0:
                items.append(item)
        return items

    # ── 爬取逻辑 ────────────────────────────────────
    def crawl_district(self, district: str):
        log.info(f"=== [Pro] 开始: {district} ({LIANJIA_DISTRICTS.get(district, '')}) ===")
        self.verify_fail_streak = 0  # 每个区重置连续失败计数
        page = 1
        new_in_district = 0
        batch = []
        empty_streak = 0
        page_times = []

        while page <= self.max_pages:
            url = f"{BASE}/{district}/pg{page}/"
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
            log.info(f"=== [Pro] {district} 完成: 入库 {new_in_district}, "
                     f"爬取页 {len(page_times)}, "
                     f"总耗时 {total:.0f}s (平均 {avg:.1f}s/页) ===")
        else:
            log.info(f"=== [Pro] {district} 完成, 本次入库 {new_in_district}, 未抓到页 ===")
        self.total_new += new_in_district
        return new_in_district

    def run(self):
        log.info("===== 链家 Pro (人机协作) 启动 =====")
        log.info(f"区县: {len(self.districts)}, 每区最多 {self.max_pages} 页")
        log.info(f"翻页间隔: {self.sleep_min:.0f}-{self.sleep_max:.0f}s")
        log.info(f"起始库: {count()}")
        log.info(f"反爬策略: 连续 {CAPTCHA_TRIGGER_STREAK} 次被拦 → 弹 Playwright 验证")
        log.info(f"每区连续验证失败上限 {MAX_VERIFY_FAILS} 次（成功不计）")
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
        log.info(f"===== [Pro] 完成, 本次新增 {self.total_new}, "
                 f"总数 {count()}, "
                 f"人机验证 {self.total_verifies} 次, "
                 f"总耗时 {total_seconds:.0f}s ({total_seconds/60:.1f}min) =====")


if __name__ == "__main__":
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
    spider = LianjiaProSpider(cookie, districts=districts, max_pages=max_pages)
    spider.run()
