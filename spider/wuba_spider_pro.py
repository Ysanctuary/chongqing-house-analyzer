"""
58同城 m 端人机协作爬虫（Pro 版）

在原版 wuba_spider.py 基础上增加 Playwright 人机验证接管：
- 正常爬取阶段使用 curl_cffi（快）
- 检测到反爬/验证码时，自动弹出系统 Chrome 浏览器窗口
- 用户在弹出的浏览器中手动完成验证
- 验证通过后自动提取 cookie 回传给 curl_cffi 继续爬取
- 支持多次验证（每区最多 3 次，防止无限弹窗）

依赖: pip install playwright（使用系统已安装的 Chrome，无需额外下载浏览器）
"""

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
        logging.FileHandler(config.LOG_DIR + "/spider_58m_pro.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("spider58pro")

# ── 常量 ──────────────────────────────────────────────
BASE = "https://m.58.com/cq/ershoufang"

# 连续被反爬多少次后触发 Playwright 验证（而不是纯等待）
CAPTCHA_TRIGGER_STREAK = 2
# 每个区连续验证失败几次后停止弹窗（成功不计入，防止无限弹窗但不限制成功次数）
MAX_VERIFY_FAILS = 3
# Playwright 等待用户验证的最长时间（秒）
VERIFY_TIMEOUT = 150

# 58 m 端重庆区县（拼音 → 中文）
# 注意：58 URL 尚未更新两江新区，yubei 实际对应两江新区
# 已剔除：beibin(北滨路)/jiabin(江北)/nanping(南坪)/shaping(沙坪坝)/yangjiaping(杨家坪) 为子区域非行政区
# 已剔除：yueyang/shuangbei 为重复条目；jiangbei 已并入两江新区；wanshan 已并入綦江区
M58_DISTRICTS = {
    # 主城（8 区，江北区已并入两江新区）
    "yuzhong": "渝中区", "yubei": "两江新区",
    "nanan": "南岸区", "shapingba": "沙坪坝区", "jiulongpo": "九龙坡区",
    "dadukou": "大渡口区", "banan": "巴南区", "beibei": "北碚区",
    # 渝西
    "dazu": "大足区", "jiangjin": "江津区",
    "yongchuan": "永川区", "hechuan": "合川区", "tongliang": "铜梁区",
    "bishan": "璧山区", "qijiang": "綦江区",
    "rongchang": "荣昌区", "tongnan": "潼南区",
    # 渝东北
    "wanzhou": "万州区", "kaizhou": "开州区",
    "liangping": "梁平区", "changshou": "长寿区",
    "fengjie": "奉节县", "wushan": "巫山县", "wuxi": "巫溪县",
    "yunyang": "云阳县", "zhongxian": "忠县",
    "fengdu": "丰都县", "dianjiang": "垫江县", "chengkou": "城口县",
    # 渝东南
    "qianjiang": "黔江区", "nanchuan": "南川区",
    "wulong": "武隆区",
    "pengshui": "彭水县", "youyang": "酉阳县", "xiushan": "秀山县",
    "shizhu": "石柱县",
}

CORE_DISTRICTS_M58 = list(M58_DISTRICTS.keys())


def load_cookie(cookie_file: str = None) -> str:
    if cookie_file and Path(cookie_file).exists():
        return Path(cookie_file).read_text(encoding="utf-8").strip()
    import os
    return os.environ.get("M58_COOKIE", "")


# ═══════════════════════════════════════════════════════
#  M58ProSpider — 人机协作版
# ═══════════════════════════════════════════════════════
class M58ProSpider:

    def __init__(self, cookie_str: str, districts: list = None, max_pages: int = 30):
        self.cookie_str = cookie_str
        self.districts = districts or CORE_DISTRICTS_M58
        self.max_pages = max_pages
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
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
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
        if base is None:
            base = random.uniform(14.0, 16.0)
        time.sleep(base)

    # ── 反爬检测 ─────────────────────────────────────
    @staticmethod
    def _is_captcha_page(text: str) -> bool:
        """判断响应是否为验证码 / 反爬拦截页"""
        if not text:
            return True
        low = text.lower()
        if len(text) < 1000:
            return True
        for kw in ("antibot", "verifycode", "captcha", "验证",
                    "请输入验证码", "安全验证", "人机验证",
                    "访问过于频繁", "请稍后重试"):
            if kw in low:
                return True
        return False

    # ── Playwright 人机验证 ──────────────────────────
    def _playwright_verify(self, url: str) -> bool:
        """
        弹出真实 Chromium 浏览器让用户手动完成验证码。
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
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Mobile/15E148 Safari/604.1"
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
                            "domain": ".58.com",
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
                    cur_title = page.title()
                    cur_text = page.inner_text("body")
                except Exception:
                    log.warning("  浏览器窗口已关闭")
                    break

                # 检测页面是否恢复正常（出现房源列表特征）
                has_listings = (
                    ("室" in cur_text and "厅" in cur_text and "万" in cur_text)
                    or "ershoufang" in (page.url or "")
                )
                still_captcha = self._is_captcha_page(cur_text)

                if has_listings and not still_captcha:
                    verified = True
                    log.info(f"  ✅ 验证通过！(耗时 {waited}s, 新标题: {cur_title})")
                    break

                # 每 10 秒提示一次
                if waited % 10 == 0:
                    remaining = VERIFY_TIMEOUT - waited
                    log.info(f"  ⏳ 等待验证中... ({waited}s / {VERIFY_TIMEOUT}s, "
                             f"剩余 {remaining}s)")

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
                        if c.get("domain", "").endswith("58.com")
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
                        if self.antibot_streak >= 5:
                            log.warning("  连续被反爬 5 次，暂停 3 分钟")
                            time.sleep(180)
                            self.antibot_streak = 0
                        else:
                            time.sleep(15)
                    else:
                        time.sleep(10)
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
    def _parse_text_blob(text: str) -> dict:
        """
        58 m 端把房源信息拼在 a 的 text 字段里:
        "18中旁 城市印象 精装3房 业主诚心出售  安心卖3室2厅115.68㎡南
         两江新区北滨路南唯一住房近地铁104万8991元/㎡"
        """
        result = {
            "title": "", "layout": "", "area": None,
            "orientation": "", "bizcircle": "", "decoration": "",
            "tags": "", "total_price": 0.0, "unit_price": 0.0,
        }
        # 总价 + 单价
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
            m = re.search(r'(\d+)室\s*(\d+(?:\.\d+)?)平?米?', text)
            if m:
                result["layout"] = f"{m.group(1)}室"
                result["area"] = float(m.group(2))
            else:
                m = re.search(r'(\d+(?:\.\d+)?)平?米?', text)
                if m:
                    result["area"] = float(m.group(1))
        # 朝向
        m = re.search(r'(?:平?米?|㎡)([东南西北]+)', text)
        if m and m.group(1):
            result["orientation"] = m.group(1)
        # 装修
        for dec in ['精装', '简装', '豪装', '毛坯', '其他']:
            if dec in text:
                result["decoration"] = dec
                break
        # 区县
        m = re.search(
            r'(渝中区|江北区|渝北区|南岸区|沙坪坝区|九龙坡区|大渡口区|巴南区|北碚区|'
            r'两江新区|北部新区|高新区|经开区)', text)
        if m:
            result["district_name"] = m.group(1)
        # 板块
        m = re.search(
            r'(两江新区|北部新区)?'
            r'(北滨路|南滨路|解放碑|观音桥|南坪|杨家坪|沙坪坝|大坪|石桥铺|'
            r'新牌坊|加州|冉家坝|人和|汽博|回兴|空港|龙头寺|红旗河沟|花卉园|'
            r'花卉西|江北嘴|五里店|华新街|寸滩|唐家沱|弹子石|上新街|涂山路|'
            r'南坪|铜元局|工贸|海峡路|四公里|南湖|弹子石)', text)
        if m:
            result["bizcircle"] = m.group(2)
        # 标题
        title_match = re.search(
            r'^(.*?)(?=\d+室|\d+平米|两江|江北|渝北|南岸|沙坪坝|九龙坡|大渡口|巴南|北碚)',
            text)
        if title_match:
            result["title"] = title_match.group(1).strip()
        else:
            result["title"] = text[:80]
        return result

    def _parse_page(self, html: str, district: str) -> list:
        soup = BeautifulSoup(html, "lxml")
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

    # ── 爬取逻辑（与原版一致） ──────────────────────
    def crawl_district(self, district: str):
        log.info(f"=== [Pro] 开始: {district} ({M58_DISTRICTS.get(district, '')}) ===")
        self.verify_fail_streak = 0  # 每个区重置连续失败计数
        page = 1
        new_in_district = 0
        batch = []
        empty_streak = 0
        page_times = []

        while page <= self.max_pages:
            url = f"{BASE}/{district}/pn{page}/"
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
                        "community": "",
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

            if len(batch) >= 50:
                n = batch_insert(batch)
                new_in_district += n
                log.info(f"  累计入库 {new_in_district}")
                batch = []

            page += 1
            self._sleep()

        if batch:
            n = batch_insert(batch)
            new_in_district += n

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
        log.info("===== 58m Pro (人机协作) 启动 =====")
        log.info(f"区县: {len(self.districts)}, 每区最多 {self.max_pages} 页")
        log.info(f"起始库: {count()}")
        log.info(f"翻页间隔: 14-16s")
        log.info(f"反爬策略: 连续 {CAPTCHA_TRIGGER_STREAK} 次被拦 → 弹 Playwright 验证")
        log.info(f"每区连续验证失败上限 {MAX_VERIFY_FAILS} 次（成功不计）")
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
        log.info(f"===== [Pro] 完成, 本次新增 {self.total_new}, "
                 f"总数 {count()}, "
                 f"人机验证 {self.total_verifies} 次, "
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
    spider = M58ProSpider(cookie, districts=districts, max_pages=max_pages)
    spider.run()
