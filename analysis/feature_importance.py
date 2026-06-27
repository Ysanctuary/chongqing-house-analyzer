"""
特征重要性分析：什么因素最影响单价
使用随机森林回归
"""
import sys
sys.path.insert(0, '.')
import pymysql
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
import config


def load_data() -> pd.DataFrame:
    cfg = {k: v for k, v in config.MYSQL_CONFIG.items() if k != 'autocommit'}
    conn = pymysql.connect(**cfg)
    df = pd.read_sql("""
        SELECT unit_price, area, district, layout, decoration, orientation, building_year
        FROM houses
        WHERE unit_price > 0 AND unit_price < 50000
          AND area > 0 AND area < 500
    """, conn)
    conn.close()
    return df


def compute_feature_importance() -> dict:
    df = load_data()
    if df.empty or len(df) < 100:
        return {"features": [], "importance": [], "message": "数据不足"}

    # 特征工程
    df['room_num'] = df['layout'].str.extract(r'(\d+)室').astype(float)
    df['hall_num'] = df['layout'].str.extract(r'(\d+)厅').astype(float)

    # 类别编码
    encoders = {}
    for col in ['district', 'decoration', 'orientation']:
        le = LabelEncoder()
        df[col + '_enc'] = le.fit_transform(df[col].fillna('unknown').astype(str))
        encoders[col] = le

    features = ['area', 'room_num', 'hall_num', 'building_year',
                'district_enc', 'decoration_enc', 'orientation_enc']
    X = df[features].fillna(0)
    y = df['unit_price']

    rf = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    rf.fit(X, y)

    importances = rf.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]

    feature_names_zh = {
        'area': '面积',
        'room_num': '卧室数',
        'hall_num': '客厅数',
        'building_year': '建成年代',
        'district_enc': '区县',
        'decoration_enc': '装修',
        'orientation_enc': '朝向',
    }

    return {
        "features": [feature_names_zh.get(features[i], features[i]) for i in sorted_idx],
        "importance": [round(float(importances[i]), 4) for i in sorted_idx],
        "score": round(float(rf.score(X, y)), 3),
        "sample_count": int(len(df)),
        "message": "分析成功"
    }


if __name__ == "__main__":
    print(compute_feature_importance())
