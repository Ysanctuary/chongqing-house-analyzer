"""
聚类分析：哪些区域属于"价格高位区"、哪些是"洼地"
使用 K-Means 聚类
"""
import sys
sys.path.insert(0, '.')
import pymysql
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import config


def load_data() -> pd.DataFrame:
    cfg = {k: v for k, v in config.MYSQL_CONFIG.items() if k != 'autocommit'}
    conn = pymysql.connect(**cfg)
    df = pd.read_sql("""
        SELECT unit_price, total_price, area, building_year, district, bizcircle
        FROM houses
        WHERE unit_price > 1000 AND unit_price < 50000
          AND area > 0 AND area < 500
    """, conn)
    conn.close()
    return df


def run_clustering(n_clusters: int = 4) -> dict:
    df = load_data()
    if df.empty or len(df) < 100:
        return {"clusters": [], "message": "数据不足"}

    # 特征
    features = ['unit_price', 'area', 'building_year']
    X = df[features].fillna(0)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df['cluster'] = km.fit_predict(X_scaled)

    # 统计每个 cluster
    result_clusters = []
    for c in range(n_clusters):
        sub = df[df['cluster'] == c]
        result_clusters.append({
            "id": int(c),
            "name": _cluster_name(sub['unit_price'].mean()),
            "count": int(len(sub)),
            "avg_unit_price": round(float(sub['unit_price'].mean()), 0),
            "avg_total_price": round(float(sub['total_price'].mean()), 0),
            "avg_area": round(float(sub['area'].mean()), 0),
            "avg_year": round(float(sub['building_year'].mean() or 0), 0),
        })

    # 排序按单价
    result_clusters.sort(key=lambda x: x['avg_unit_price'], reverse=True)

    # 重新分配 id
    for i, c in enumerate(result_clusters):
        c['id'] = i

    return {
        "clusters": result_clusters,
        "sample_count": int(len(df)),
        "message": "聚类完成"
    }


def _cluster_name(avg_unit_price: float) -> str:
    if avg_unit_price >= 18000:
        return "高位区（核心商圈）"
    elif avg_unit_price >= 13000:
        return "中高位区（主城优质）"
    elif avg_unit_price >= 8000:
        return "中位区（主城/近郊）"
    elif avg_unit_price >= 5000:
        return "中低位区（渝西/近郊）"
    else:
        return "洼地区（远郊/区县）"


if __name__ == "__main__":
    import json
    print(json.dumps(run_clustering(), ensure_ascii=False, indent=2))
