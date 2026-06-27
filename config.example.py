"""
全局配置文件
=====================
重庆二手房数据分析系统

使用方法：
    1. 复制本文件为 config.py：cp config.example.py config.py
    2. 修改 MYSQL_CONFIG["password"] 为你的 MySQL 密码
    3. 其他参数一般不用动

注意：真实 config.py 含敏感信息，已在 .gitignore 中排除。
"""
import os

# 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# MySQL 配置
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "YOUR_MYSQL_PASSWORD",   # ← 改成你的 MySQL 密码
    "database": "chongqing_house",
    "charset": "utf8mb4",
    "autocommit": False,
}

# 链家重庆二手房主域
LIANJIA_BASE = "https://cq.lianjia.com"
LIANJIA_ERSHOUFANG = "https://cq.lianjia.com/ershoufang"

# 重庆市主要区县及其在链家 URL 中的标识
DISTRICTS = {
    "yuzhong":   "渝中区",
    "jiangbei":  "江北区",
    "yubei":     "渝北区",
    "nanan":     "南岸区",
    "shapingba": "沙坪坝区",
    "jiulongpo": "九龙坡区",
    "yueyang":   "渝中区",  # 占位
    "dadukou":   "大渡口区",
    "banan":     "巴南区",
    "beibei":    "北碚区",
    "bishan":    "璧山区",
    "jiangjin":  "江津区",
    "hechuan":   "合川区",
    "yongchuan": "永川区",
    "tongliang": "铜梁区",
    "dazu":      "大足区",
    "rongchang": "荣昌区",
    "qijiang":   "綦江区",
    "wanshan":   "万盛区",
    "nanchuan":  "南川区",
    "tongnan":   "潼南区",
    "kaizhou":   "开州区",
    "liangping": "梁平区",
    "wulong":    "武隆区",
    "fengdu":    "丰都县",
    "dianjiang": "垫江县",
    "chengkou":  "城口县",
    "wushan":    "巫山县",
    "wuxi":      "巫溪县",
    "pengshui":  "彭水县",
    "youyang":   "酉阳县",
    "xiushan":   "秀山县",
    "shizhu":    "石柱县",
    "yunyang":   "云阳县",
    "fengjie":   "奉节县",
    "zigui":     "秭归县",
}

# 重庆主城九区（重点爬取）
CORE_DISTRICTS = [
    "yuzhong", "jiangbei", "yubei", "nanan", "shapingba",
    "jiulongpo", "dadukou", "banan", "beibei"
]

# 爬虫参数
SPIDER_CONFIG = {
    "max_pages_per_district": 100,  # 每个区最多翻 100 页
    "page_size": 30,                # 链家每页 30 条
    "request_delay_min": 2.0,       # 最小延迟（秒）
    "request_delay_max": 4.0,       # 最大延迟（秒）
    "max_retries": 3,               # 失败重试次数
    "batch_size": 100,              # 每 100 条入库一次
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ],
    "headers_extra": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    },
}

# Flask 配置
FLASK_CONFIG = {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": False,
}