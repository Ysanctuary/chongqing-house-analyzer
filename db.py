"""
数据库模块
负责 MySQL 连接的创建、表结构的初始化、批量插入与查询
"""
import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
import config


def get_connection(database: str = None):
    """获取数据库连接"""
    cfg = config.MYSQL_CONFIG.copy()
    if database:
        cfg["database"] = database
    else:
        cfg.pop("database", None)
    return pymysql.connect(**cfg)


@contextmanager
def conn_ctx(database: str = None):
    """连接上下文管理器"""
    conn = get_connection(database)
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """初始化数据库与表结构"""
    db_name = config.MYSQL_CONFIG["database"]

    # 1. 创建数据库
    with conn_ctx() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()

    # 2. 创建表
    with conn_ctx(database=db_name) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS houses (
                    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
                    house_code      VARCHAR(64) UNIQUE,
                    title           VARCHAR(255),
                    district        VARCHAR(32),
                    bizcircle       VARCHAR(64),
                    community       VARCHAR(128),
                    layout          VARCHAR(64),
                    area            DECIMAL(10,2),
                    orientation     VARCHAR(32),
                    decoration      VARCHAR(32),
                    floor_info      VARCHAR(64),
                    building_year   INT,
                    building_type   VARCHAR(32),
                    total_price     DECIMAL(12,2),
                    unit_price      DECIMAL(12,2),
                    follow_count    INT DEFAULT 0,
                    publish_time    VARCHAR(64),
                    tag             VARCHAR(255),
                    url             VARCHAR(1024),
                    crawl_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_district (district),
                    INDEX idx_bizcircle (bizcircle),
                    INDEX idx_unit_price (unit_price),
                    INDEX idx_crawl_time (crawl_time)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    print(f"[DB] 初始化完成: {db_name}.houses")


def batch_insert(houses: list):
    """批量插入（增量：ON DUPLICATE KEY UPDATE 仅更新爬取时间）"""
    if not houses:
        return 0

    sql = """
        INSERT INTO houses
        (house_code, title, district, bizcircle, community, layout, area,
         orientation, decoration, floor_info, building_year, building_type,
         total_price, unit_price, follow_count, publish_time, tag, url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            crawl_time = CURRENT_TIMESTAMP,
            total_price = VALUES(total_price),
            unit_price  = VALUES(unit_price),
            follow_count= VALUES(follow_count)
    """
    rows = []
    for h in houses:
        rows.append((
            h.get("house_code", ""),
            h.get("title", ""),
            h.get("district", ""),
            h.get("bizcircle", ""),
            h.get("community", ""),
            h.get("layout", ""),
            h.get("area") or 0,
            h.get("orientation", ""),
            h.get("decoration", ""),
            h.get("floor_info", ""),
            h.get("building_year"),
            h.get("building_type", ""),
            h.get("total_price") or 0,
            h.get("unit_price") or 0,
            h.get("follow_count", 0),
            h.get("publish_time", ""),
            h.get("tag", ""),
            h.get("url", ""),
        ))

    # 先查重，统计会撞的
    new_codes = []
    with conn_ctx(database=config.MYSQL_CONFIG["database"]) as conn:
        with conn.cursor() as cur:
            codes = [r[0] for r in rows if r[0]]
            if codes:
                placeholders = ",".join(["%s"] * len(codes))
                cur.execute(
                    f"SELECT house_code FROM houses WHERE house_code IN ({placeholders})",
                    codes
                )
                existing = {row[0] for row in cur.fetchall()}
            else:
                existing = set()

            cur.executemany(sql, rows)
        conn.commit()

    # 真正新增的 = 总数 - 已存在的
    new_count = sum(1 for r in rows if r[0] and r[0] not in existing)
    return new_count


def fetch_all(sql: str, params: tuple = None) -> list:
    """查询所有（返回字典列表）"""
    with conn_ctx(database=config.MYSQL_CONFIG["database"]) as conn:
        with conn.cursor(DictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def fetch_one(sql: str, params: tuple = None) -> dict:
    """查询单条"""
    with conn_ctx(database=config.MYSQL_CONFIG["database"]) as conn:
        with conn.cursor(DictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def count(sql: str = "SELECT COUNT(*) AS cnt FROM houses", params: tuple = None) -> int:
    """统计行数"""
    row = fetch_one(sql, params)
    return int(row["cnt"]) if row else 0


if __name__ == "__main__":
    init_database()
    print(f"当前房源总数: {count()}")
