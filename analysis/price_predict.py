"""
价格预测：输入特征 → 预测单价
使用随机森林
"""
import sys
sys.path.insert(0, '.')
import pymysql
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
import config


_model = None
_encoders = None
_feature_cols = None


def _train():
    global _model, _encoders, _feature_cols

    cfg = {k: v for k, v in config.MYSQL_CONFIG.items() if k != 'autocommit'}
    conn = pymysql.connect(**cfg)
    df = pd.read_sql("""
        SELECT unit_price, area, district, layout, decoration, orientation
        FROM houses
        WHERE unit_price > 1000 AND unit_price < 50000
          AND area > 0 AND area < 500
    """, conn)
    conn.close()

    df['room_num'] = df['layout'].str.extract(r'(\d+)室').astype(float)
    df['hall_num'] = df['layout'].str.extract(r'(\d+)厅').astype(float)

    encoders = {}
    for col in ['district', 'decoration', 'orientation']:
        le = LabelEncoder()
        df[col + '_enc'] = le.fit_transform(df[col].fillna('unknown').astype(str))
        encoders[col] = le

    _feature_cols = ['area', 'room_num', 'hall_num',
                     'district_enc', 'decoration_enc', 'orientation_enc']
    X = df[_feature_cols].fillna(0)
    y = df['unit_price']

    model = RandomForestRegressor(n_estimators=200, max_depth=15, random_state=42, n_jobs=-1)
    model.fit(X, y)
    _model = model
    _encoders = encoders
    return model.score(X, y)


def predict_price(area: float, layout: str, district: str,
                  decoration: str, orientation: str) -> dict:
    global _model, _encoders, _feature_cols
    if _model is None:
        score = _train()
    else:
        score = None

    import re
    m = re.search(r'(\d+)室', layout)
    room = int(m.group(1)) if m else 3
    m = re.search(r'(\d+)厅', layout)
    hall = int(m.group(1)) if m else 2

    # 编码
    encs = {}
    for col, val in [('district', district), ('decoration', decoration), ('orientation', orientation)]:
        le = _encoders[col]
        try:
            encs[col + '_enc'] = int(le.transform([val])[0])
        except ValueError:
            encs[col + '_enc'] = 0  # 未知值用 0

    import pandas as pd
    X = pd.DataFrame([{
        'area': area,
        'room_num': room,
        'hall_num': hall,
        **encs,
    }])

    pred = float(_model.predict(X)[0])
    # 给个 ±15% 的合理区间
    return {
        "predicted_unit_price": round(pred, 0),
        "predicted_total_price": round(pred * area / 10000, 0),  # 万
        "min_unit_price": round(pred * 0.85, 0),
        "max_unit_price": round(pred * 1.15, 0),
        "model_score": round(score, 3) if score is not None else None,
    }


if __name__ == "__main__":
    print(predict_price(100, "3室2厅", "渝北区", "精装", "南北"))
