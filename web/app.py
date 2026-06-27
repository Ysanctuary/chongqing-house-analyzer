"""
Flask Web 应用
重庆二手房数据分析系统
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import pymysql
from pymysql.cursors import DictCursor

import config

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')
CORS(app)


def db():
    cfg = {k: v for k, v in config.MYSQL_CONFIG.items() if k != 'autocommit'}
    return pymysql.connect(**cfg)


def query(sql, params=None, fetch='all'):
    conn = db()
    try:
        with conn.cursor(DictCursor) as cur:
            cur.execute(sql, params or ())
            if fetch == 'one':
                return cur.fetchone()
            return cur.fetchall()
    finally:
        conn.close()


# ================= 页面 =================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/map')
def map_view():
    return render_template('map.html')


@app.route('/charts')
def charts_view():
    return render_template('charts.html')


@app.route('/analysis')
def analysis_view():
    return render_template('analysis.html')


@app.route('/conclusion')
def conclusion_view():
    return render_template('conclusion.html')


# ================= 总控面板 =================
import subprocess
import threading
from datetime import datetime
import signal
import os as _os

# 爬虫进程管理
_spider_process = None
_spider_log_offset = 0  # 当前爬虫启动时日志文件的字节偏移量


@app.route('/control')
def control_view():
    """总控面板页面"""
    return send_from_directory('.', 'control.html')


@app.route('/api/control/status')
def api_control_status():
    """总控状态"""
    try:
        cnt = query("SELECT COUNT(*) AS c FROM houses", fetch='one')['c']
        districts = query("SELECT COUNT(DISTINCT district) AS c FROM houses WHERE district IS NOT NULL", fetch='one')['c']
        db_ok = True
    except Exception as e:
        cnt = 0
        districts = 0
        db_ok = False

    return jsonify({
        "web_running": True,
        "db_ok": db_ok,
        "data_count": cnt,
        "district_count": districts,
        "spider_running": _spider_process is not None and _spider_process.poll() is None,
        "pid": _os.getpid(),
        "now": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


@app.route('/api/control/spider')
def api_control_spider():
    """启动/停止数据获取（三种数据源并存）

    参数（GET）:
        action: start | stop
        source: lianjia | wuba | api（start 时必填）
        pages: 翻几页
                - 链家/58 爬虫：每区最多页数（默认 5，建议先小量测试）
                - API：总页数（默认 5）
        page_size: 仅 API（每页几条，默认 25）
        api_url: 仅 API（必填，支持 {page} {page_size} {offset} 占位符）
        headers: 仅 API（JSON 字符串，可选），如 {"Authorization":"Bearer xxx"}
    """
    global _spider_process
    import json as _json_spider
    action = request.args.get('action', 'start')

    # ============== 停止 ==============
    if action == 'stop':
        if _spider_process and _spider_process.poll() is None:
            try:
                _spider_process.terminate()
                _spider_process.wait(timeout=5)
                return jsonify({"message": "数据获取已停止"})
            except Exception as e:
                return jsonify({"message": f"停止超时: {e}"}), 500
        return jsonify({"message": "数据获取未在运行"})

    # ============== 启动 ==============
    if _spider_process and _spider_process.poll() is None:
        return jsonify({"message": "数据获取已在运行中", "pid": _spider_process.pid})

    source = request.args.get('source', '').strip()
    if not source:
        return jsonify({
            "message": "请指定数据源：source=lianjia | wuba | wuba_pro | lianjia_pro | api",
            "available_sources": ["lianjia", "wuba", "wuba_pro", "lianjia_pro", "api"]
        }), 400

    pages = int(request.args.get('pages', 5))

    # 记录当前日志文件的字节偏移量（只读取本次爬取的日志）
    log_map_start = {
        'lianjia': 'spider_lianjia.log',
        'wuba': 'spider_58m.log',
        'wuba_pro': 'spider_58m_pro.log',
        'lianjia_pro': 'spider_lianjia_pro.log',
        'api': 'spider_bg.log',
    }
    global _spider_log_offset
    log_file_for_source = log_map_start.get(source, 'spider_bg.log')
    log_path_for_offset = config.LOG_DIR + "/" + log_file_for_source
    if _os.path.exists(log_path_for_offset):
        _spider_log_offset = _os.path.getsize(log_path_for_offset)
    else:
        _spider_log_offset = 0

    log_path = config.LOG_DIR + "/spider_bg.log"
    log_file = open(log_path, 'a', encoding='utf-8')

    # ------- 1. 链家 m 端 HTML 爬虫 -------
    if source == 'lianjia':
        _spider_process = subprocess.Popen(
            [sys.executable, '-m', 'spider.lianjia_spider', str(pages)],
            cwd=config.BASE_DIR,
            stdout=log_file, stderr=log_file
        )
        return jsonify({
            "message": f"🐝 链家爬虫已后台启动 (PID={_spider_process.pid})，每区最多 {pages} 页",
            "pid": _spider_process.pid,
            "source": source,
            "log": "logs/spider_lianjia.log"
        })

    # ------- 2. 58 同城 HTML 爬虫 -------
    elif source == 'wuba':
        _spider_process = subprocess.Popen(
            [sys.executable, '-m', 'spider.wuba_spider', str(pages)],
            cwd=config.BASE_DIR,
            stdout=log_file, stderr=log_file
        )
        return jsonify({
            "message": f"🐜 58 同城爬虫已后台启动 (PID={_spider_process.pid})，每区最多 {pages} 页（反爬严格）",
            "pid": _spider_process.pid,
            "source": source,
            "log": "logs/spider_58m.log"
        })

    # ------- 2b. 58 同城人机协作爬虫 (Pro) -------
    elif source == 'wuba_pro':
        _spider_process = subprocess.Popen(
            [sys.executable, '-m', 'spider.wuba_spider_pro', str(pages)],
            cwd=config.BASE_DIR,
            stdout=log_file, stderr=log_file
        )
        return jsonify({
            "message": f"🤝 58 人机协作爬虫已启动 (PID={_spider_process.pid})，每区最多 {pages} 页（遇验证码弹浏览器）",
            "pid": _spider_process.pid,
            "source": source,
            "log": "logs/spider_58m_pro.log"
        })

    # ------- 2c. 链家人机协作爬虫 (Pro) -------
    elif source == 'lianjia_pro':
        _spider_process = subprocess.Popen(
            [sys.executable, '-m', 'spider.lianjia_spider_pro', str(pages)],
            cwd=config.BASE_DIR,
            stdout=log_file, stderr=log_file
        )
        return jsonify({
            "message": f"🤝 链家人机协作爬虫已启动 (PID={_spider_process.pid})，每区最多 {pages} 页（遇验证码弹浏览器）",
            "pid": _spider_process.pid,
            "source": source,
            "log": "logs/spider_lianjia_pro.log"
        })

    # ------- 3. 通用 API 数据获取器 -------
    elif source == 'api':
        api_url = request.args.get('api_url', '').strip()
        if not api_url:
            return jsonify({"message": "请先输入 API URL"}), 400
        page_size = int(request.args.get('page_size', 25))
        headers_str = request.args.get('headers', '{}').strip()
        # 验证 headers 是有效 JSON
        try:
            headers_dict = _json_spider.loads(headers_str) if headers_str else {}
            if not isinstance(headers_dict, dict):
                raise ValueError("headers 必须是 JSON 对象")
        except Exception as e:
            return jsonify({"message": f"headers 不是有效 JSON 对象: {e}"}), 400
        # 启子进程调 data_fetcher（用 sys.argv 传参，避免转义问题）
        _spider_process = subprocess.Popen(
            [sys.executable, '-c',
             'import sys, json; '
             f'sys.path.insert(0, r"{config.BASE_DIR}"); '
             'from data_fetcher import fetch_from_api; '
             'result = fetch_from_api('
             'sys.argv[1], '
             'pages=int(sys.argv[2]), '
             'page_size=int(sys.argv[3]), '
             'extra_headers=json.loads(sys.argv[4])); '
             'print("\n=== 最终结果 ==="); '
             'print(json.dumps(result, ensure_ascii=False))',
             api_url, str(pages), str(page_size), headers_str],
            stdout=log_file, stderr=log_file
        )
        return jsonify({
            "message": f"🔌 API 数据获取已后台启动 (PID={_spider_process.pid})，共 {pages} 页 × {page_size} 条",
            "pid": _spider_process.pid,
            "source": source,
            "log": "logs/spider_bg.log"
        })

    # ------- 未知 source -------
    else:
        return jsonify({
            "message": f"未知数据源: {source}",
            "available_sources": ["lianjia", "wuba", "wuba_pro", "lianjia_pro", "api"]
        }), 400




@app.route('/api/control/generate_data')
def api_control_generate_data():
    """补足数据到 5 万（基于 37 区县经济特征的高质量生成器）"""
    try:
        from cleaner.realistic_generator import main as run_generator
        # 在后台线程跑（避免请求超时）
        result_holder = {'msg': None, 'err': None, 'result': None}
        def run():
            try:
                import io
                import contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    result = run_generator(target=50000)
                result_holder['msg'] = buf.getvalue().split('\n')[-2] if buf.getvalue() else "完成"
                result_holder['result'] = result
            except Exception as e:
                result_holder['err'] = str(e)
        t = threading.Thread(target=run)
        t.start()
        t.join(timeout=180)  # 3 分钟超时
        if t.is_alive():
            return jsonify({"message": "数据生成中（后台运行），请稍后刷新状态查看"}), 202
        if result_holder['err']:
            return jsonify({"message": f"失败: {result_holder['err']}"}), 500
        # 优先使用新版生成器返回的 message
        msg = (result_holder['result'] or {}).get('message') or result_holder['msg'] or "数据生成完成"
        return jsonify({
            "message": msg,
            "inserted": (result_holder['result'] or {}).get('inserted', 0),
            "total": (result_holder['result'] or {}).get('total', 0),
        })
    except Exception as e:
        return jsonify({"message": f"错误: {e}"}), 500


@app.route('/api/control/train')
def api_control_train():
    """训练机器学习模型"""
    import time
    t = request.args.get('type', '')
    start = time.time()
    try:
        if t == 'feature_importance':
            from analysis.feature_importance import compute_feature_importance
            result = compute_feature_importance()
        elif t == 'clustering':
            from analysis.cluster import run_clustering
            result = run_clustering()
        elif t == 'price_predict':
            from analysis.price_predict import predict_price
            result = predict_price(100, "3室2厅", "渝北区", "精装", "南北")
        else:
            return jsonify({"message": f"未知类型: {t}"}), 400
        elapsed = time.time() - start
        return jsonify({"message": f"{t} 训练完成", "elapsed": elapsed, "result_keys": list(result.keys()) if isinstance(result, dict) else None})
    except Exception as e:
        return jsonify({"message": f"训练失败: {e}"}), 500


@app.route('/api/control/data')
def api_control_data():
    """危险操作：清空/删表"""
    action = request.args.get('action', '')
    try:
        conn = db()
        with conn.cursor() as cur:
            if action == 'clear':
                cur.execute("DELETE FROM houses")
                conn.commit()
                return jsonify({"message": f"已清空数据表（删除了 {cur.rowcount} 条）"})
            elif action == 'drop':
                cur.execute("DROP TABLE IF EXISTS houses")
                conn.commit()
                # 重建
                from db import init_database
                init_database()
                return jsonify({"message": "表已删除并重建"})
        conn.close()
    except Exception as e:
        return jsonify({"message": str(e)}), 500


@app.route('/api/control/log')
def api_control_log():
    """返回爬虫日志（仅本次爬取）

    参数（GET）:
        source: spider | wuba | lianjia | wuba_pro | lianjia_pro | bg（默认 spider）
        lines:  返回行数（默认 100）
    """
    source = request.args.get('source', 'spider').strip()
    n_lines = min(int(request.args.get('lines', 100)), 500)

    log_map = {
        'spider':   'spider.log',
        'wuba':     'spider_58m.log',
        'wuba_pro': 'spider_58m_pro.log',
        'lianjia':  'spider_lianjia.log',
        'lianjia_pro': 'spider_lianjia_pro.log',
        'bg':       'spider_bg.log',
    }
    filename = log_map.get(source, 'spider.log')
    log_path = config.LOG_DIR + "/" + filename

    if not _os.path.exists(log_path):
        return jsonify({"logs": [f"({filename} 不存在)"], "source": source, "file": filename})
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            # 跳到本次爬取开始的位置
            f.seek(_spider_log_offset)
            lines = f.readlines()
            # 取最后 N 行
            lines = lines[-n_lines:] if len(lines) > n_lines else lines

        # 添加提示
        notice = "💡 仅显示本次爬取日志，若要查看之前的日志请前往 logs/ 文件夹内查看"
        result = [notice, ""] + [l.rstrip() for l in lines]
        return jsonify({"logs": result, "source": source, "file": filename})
    except Exception as e:
        return jsonify({"logs": [f"读取失败: {e}"]})


@app.route('/api/control/restart')
def api_control_restart():
    """重启 Web 服务：启用独立子进程，自杀让位"""
    import time as _time

    def _do_restart():
        _time.sleep(0.8)  # 等待响应发出去
        # 1. 启动一个独立的新进程（debug=False 避免产生 reloader parent）
        log_path = config.LOG_DIR + "/restart.log"
        log_file = open(log_path, "a", encoding="utf-8")
        subprocess.Popen(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, r'{config.BASE_DIR}'); "
             f"import os; os.chdir(r'{config.BASE_DIR}'); "
             f"import web.app as _a; "
             f"_a.app.run(host='{config.FLASK_CONFIG['host']}', port={config.FLASK_CONFIG['port']}, debug=False, use_reloader=False)"],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            close_fds=True,
        )
        _time.sleep(2.0)  # 等新进程绑好 5000 端口
        # 2. 自杀
        _os._exit(0)

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"message": "重启中...6 秒后浏览器将自动刷新"})


def _ensure_restart_guard():
    pass



@app.route('/api/control/shutdown')
def api_control_shutdown():
    """完全退出：杀干净所有相关进程 + Flask 自身"""
    def kill():
        try:
            # 延迟 import（避免循环依赖 + 减少启动开销）
            from exit import full_shutdown
            # 跳过 Flask 自己（自杀留给 _os._exit(0)）
            killed = full_shutdown(skip_pids=[os.getpid()])
            if killed:
                print(f"[Shutdown] 已停止: {', '.join(killed)}")
        except Exception as e:
            print(f"[Shutdown] 杀进程失败: {e}")
        # 最后自杀
        _os._exit(0)
    threading.Timer(0.5, kill).start()
    return jsonify({"message": "再见，所有相关进程已停止"})




# ================= API =================

@app.route('/api/overview')
def api_overview():
    """总览数据"""
    total = query("SELECT COUNT(*) AS c FROM houses", fetch='one')['c']
    avg_unit_price = query("SELECT AVG(unit_price) AS p FROM houses WHERE unit_price > 0", fetch='one')['p'] or 0
    avg_total_price = query("SELECT AVG(total_price) AS p FROM houses WHERE total_price > 0", fetch='one')['p'] or 0
    max_unit = query("SELECT MAX(unit_price) AS p FROM houses", fetch='one')['p'] or 0
    min_unit = query("SELECT MIN(unit_price) AS p FROM houses WHERE unit_price > 1000", fetch='one')['p'] or 0
    district_count = query("SELECT COUNT(DISTINCT district) AS c FROM houses", fetch='one')['c']
    biz_count = query("SELECT COUNT(DISTINCT bizcircle) AS c FROM houses WHERE bizcircle != ''", fetch='one')['c']

    return jsonify({
        "total": total,
        "avg_unit_price": round(avg_unit_price, 0),
        "avg_total_price": round(avg_total_price, 0),
        "max_unit_price": round(max_unit, 0),
        "min_unit_price": round(min_unit, 0),
        "district_count": district_count,
        "bizcircle_count": biz_count,
    })


@app.route('/api/district_stats')
def api_district_stats():
    """各区县统计"""
    rows = query("""
        SELECT district,
               COUNT(*) AS cnt,
               ROUND(AVG(unit_price), 0) AS avg_unit,
               ROUND(AVG(total_price), 0) AS avg_total,
               ROUND(AVG(area), 0) AS avg_area,
               ROUND(MIN(unit_price), 0) AS min_unit,
               ROUND(MAX(unit_price), 0) AS max_unit
        FROM houses
        WHERE district IS NOT NULL AND district != ''
        GROUP BY district
        ORDER BY avg_unit DESC
    """)
    return jsonify({"data": rows})


@app.route('/api/bizcircle_stats')
def api_bizcircle_stats():
    """板块统计（TOP 30）"""
    rows = query("""
        SELECT bizcircle, district,
               COUNT(*) AS cnt,
               ROUND(AVG(unit_price), 0) AS avg_unit
        FROM houses
        WHERE bizcircle IS NOT NULL AND bizcircle != ''
        GROUP BY bizcircle, district
        ORDER BY avg_unit DESC
        LIMIT 30
    """)
    return jsonify({"data": rows})


@app.route('/api/price_distribution')
def api_price_distribution():
    """单价分布直方图"""
    rows = query("""
        SELECT
            CASE
                WHEN unit_price < 5000 THEN '0-5k'
                WHEN unit_price < 8000 THEN '5-8k'
                WHEN unit_price < 10000 THEN '8-10k'
                WHEN unit_price < 12000 THEN '10-12k'
                WHEN unit_price < 15000 THEN '12-15k'
                WHEN unit_price < 20000 THEN '15-20k'
                WHEN unit_price < 30000 THEN '20-30k'
                ELSE '30k+'
            END AS bucket,
            COUNT(*) AS cnt
        FROM houses
        WHERE unit_price > 0
        GROUP BY bucket
        ORDER BY MIN(unit_price)
    """)
    return jsonify({"data": rows})


@app.route('/api/total_price_distribution')
def api_total_price_distribution():
    """总价分布"""
    rows = query("""
        SELECT
            CASE
                WHEN total_price < 50 THEN '50万以下'
                WHEN total_price < 80 THEN '50-80万'
                WHEN total_price < 100 THEN '80-100万'
                WHEN total_price < 150 THEN '100-150万'
                WHEN total_price < 200 THEN '150-200万'
                WHEN total_price < 300 THEN '200-300万'
                WHEN total_price < 500 THEN '300-500万'
                ELSE '500万以上'
            END AS bucket,
            COUNT(*) AS cnt
        FROM houses
        WHERE total_price > 0
        GROUP BY bucket
        ORDER BY MIN(total_price)
    """)
    return jsonify({"data": rows})


@app.route('/api/layout_distribution')
def api_layout_distribution():
    """户型分布"""
    rows = query("""
        SELECT layout, COUNT(*) AS cnt
        FROM houses
        WHERE layout IS NOT NULL AND layout != ''
        GROUP BY layout
        ORDER BY cnt DESC
    """)
    return jsonify({"data": rows})


@app.route('/api/decoration_distribution')
def api_decoration_distribution():
    """装修分布"""
    rows = query("""
        SELECT decoration, COUNT(*) AS cnt, ROUND(AVG(unit_price), 0) AS avg_unit
        FROM houses
        WHERE decoration IS NOT NULL AND decoration != ''
        GROUP BY decoration
        ORDER BY cnt DESC
    """)
    return jsonify({"data": rows})


@app.route('/api/orientation_distribution')
def api_orientation_distribution():
    """朝向分布"""
    rows = query("""
        SELECT orientation, COUNT(*) AS cnt, ROUND(AVG(unit_price), 0) AS avg_unit
        FROM houses
        WHERE orientation IS NOT NULL AND orientation != ''
        GROUP BY orientation
        ORDER BY cnt DESC
    """)
    return jsonify({"data": rows})


@app.route('/api/area_distribution')
def api_area_distribution():
    """面积分布"""
    rows = query("""
        SELECT
            CASE
                WHEN area < 50 THEN '50以下'
                WHEN area < 80 THEN '50-80'
                WHEN area < 100 THEN '80-100'
                WHEN area < 120 THEN '100-120'
                WHEN area < 150 THEN '120-150'
                WHEN area < 200 THEN '150-200'
                ELSE '200以上'
            END AS bucket,
            COUNT(*) AS cnt,
            ROUND(AVG(unit_price), 0) AS avg_unit
        FROM houses
        WHERE area > 0
        GROUP BY bucket
        ORDER BY MIN(area)
    """)
    return jsonify({"data": rows})


@app.route('/api/building_year_distribution')
def api_building_year_distribution():
    """建成年代分布"""
    rows = query("""
        SELECT building_year, COUNT(*) AS cnt, ROUND(AVG(unit_price), 0) AS avg_unit
        FROM houses
        WHERE building_year > 0
        GROUP BY building_year
        ORDER BY building_year
    """)
    return jsonify({"data": rows})


@app.route('/api/floor_distribution')
def api_floor_distribution():
    """楼层分布"""
    rows = query("""
        SELECT floor_info, COUNT(*) AS cnt, ROUND(AVG(unit_price), 0) AS avg_unit
        FROM houses
        WHERE floor_info IS NOT NULL AND floor_info != ''
        GROUP BY floor_info
        ORDER BY cnt DESC
    """)
    return jsonify({"data": rows})


@app.route('/api/price_vs_area')
def api_price_vs_area():
    """单价 vs 面积 散点图（采样 1000 条）"""
    rows = query("""
        SELECT unit_price, area, total_price, district
        FROM houses
        WHERE unit_price > 0 AND area > 0
        ORDER BY RAND()
        LIMIT 1000
    """)
    return jsonify({"data": rows})


@app.route('/api/top_communities')
def api_top_communities():
    """TOP 小区"""
    rows = query("""
        SELECT community, district, COUNT(*) AS cnt, ROUND(AVG(unit_price), 0) AS avg_unit
        FROM houses
        WHERE community IS NOT NULL AND community != ''
        GROUP BY community, district
        ORDER BY cnt DESC
        LIMIT 20
    """)
    return jsonify({"data": rows})


@app.route('/api/expensive_communities')
def api_expensive_communities():
    """最贵小区"""
    rows = query("""
        SELECT community, district, COUNT(*) AS cnt, ROUND(AVG(unit_price), 0) AS avg_unit
        FROM houses
        WHERE community IS NOT NULL AND community != ''
        GROUP BY community, district
        HAVING cnt >= 5
        ORDER BY avg_unit DESC
        LIMIT 20
    """)
    return jsonify({"data": rows})


@app.route('/api/cost_effective')
def api_cost_effective():
    """性价比小区（同等条件下单价最低）"""
    rows = query("""
        SELECT community, district, ROUND(AVG(unit_price), 0) AS avg_unit, COUNT(*) AS cnt
        FROM houses
        WHERE community IS NOT NULL AND community != ''
        GROUP BY community, district
        HAVING cnt >= 5
        ORDER BY avg_unit ASC
        LIMIT 20
    """)
    return jsonify({"data": rows})


@app.route('/api/feature_importance')
def api_feature_importance():
    """特征重要性（来自随机森林）"""
    from analysis.feature_importance import compute_feature_importance
    result = compute_feature_importance()
    return jsonify(result)


@app.route('/api/clustering')
def api_clustering():
    """聚类结果"""
    from analysis.cluster import run_clustering
    result = run_clustering()
    return jsonify(result)


@app.route('/api/price_predict')
def api_price_predict():
    """价格预测示例"""
    from analysis.price_predict import predict_price
    area = float(request.args.get('area', 100))
    layout = request.args.get('layout', '3室2厅')
    district = request.args.get('district', '渝北区')
    decoration = request.args.get('decoration', '精装')
    orientation = request.args.get('orientation', '南北')
    result = predict_price(area, layout, district, decoration, orientation)
    return jsonify(result)


@app.route('/api/district_geo')
def api_district_geo():
    """区县地理坐标（用于地图）"""
    geo = {
        "渝中区":   [106.580, 29.555],
        "江北区":   [106.580, 29.610],
        "渝北区":   [106.640, 29.720],
        "南岸区":   [106.640, 29.520],
        "沙坪坝区": [106.460, 29.560],
        "九龙坡区": [106.510, 29.500],
        "大渡口区": [106.490, 29.490],
        "巴南区":   [106.520, 29.380],
        "北碚区":   [106.400, 29.800],
        "两江新区": [106.620, 29.650],
    }
    rows = query("""
        SELECT district,
               COUNT(*) AS cnt,
               ROUND(AVG(unit_price), 0) AS avg_unit,
               ROUND(AVG(total_price), 0) AS avg_total
        FROM houses
        WHERE district IS NOT NULL AND district != ''
        GROUP BY district
    """)
    features = []
    for r in rows:
        d = r['district']
        if d in geo:
            features.append({
                "name": d,
                "value": r['avg_unit'],
                "count": r['cnt'],
                "coord": geo[d],
            })
    return jsonify({"data": features})
@app.route('/api/control/recent_data')
def api_control_recent_data():
    """展示最近爬取的数据（按数据源过滤）

    参数（GET）:
        source: all | lianjia | wuba | api | synth（默认 all）
        limit:  每页条数（默认 50，最大 500）
        offset: 偏移量（默认 0）

    数据源识别规则（按 house_code 前缀）:
        API_xxx         → api
        SYN_xxx         → synth（演示合成数据）
        全数字           → wuba
        其他（下划线分隔）→ lianjia
    """
    source = request.args.get('source', 'all').strip()
    try:
        limit = min(int(request.args.get('limit', 50)), 500)
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(int(request.args.get('offset', 0)), 0)
    except (TypeError, ValueError):
        offset = 0

    # --- source 过滤条件（用 LEFT() 比 LIKE 更安全，不需要转义下划线）---
    if source == 'api':
        where = "LEFT(house_code, 4) = 'API_'"
    elif source == 'synth':
        where = "LEFT(house_code, 4) = 'SYN_'"
    elif source == 'wuba':
        where = "house_code REGEXP '^[0-9]+$'"
    elif source == 'lianjia':
        where = ("house_code NOT REGEXP '^[0-9]+$' "
                 "AND LEFT(house_code, 4) <> 'API_' "
                 "AND LEFT(house_code, 4) <> 'SYN_'")
    elif source == 'all':
        where = "1=1"
    else:
        return jsonify({
            "message": f"未知数据源: {source}",
            "available_sources": ["all", "lianjia", "wuba", "api", "synth"]
        }), 400

    # --- 统计各来源数量 ---
    by_source = {"lianjia": 0, "wuba": 0, "api": 0, "synth": 0}
    try:
        rows = query("""
            SELECT
              CASE
                WHEN LEFT(house_code, 4) = 'API_' THEN 'api'
                WHEN LEFT(house_code, 4) = 'SYN_' THEN 'synth'
                WHEN house_code REGEXP '^[0-9]+$' THEN 'wuba'
                ELSE 'lianjia'
              END AS src,
              COUNT(*) AS cnt
            FROM houses
            GROUP BY src
        """)
        for r in rows:
            by_source[r['src']] = r['cnt']
    except Exception:
        pass  # 统计失败不影响主流程

    # --- 总数（按当前 source 过滤）---
    try:
        total = query(f"SELECT COUNT(*) AS c FROM houses WHERE {where}", fetch='one')['c']
    except Exception as e:
        return jsonify({"error": f"查询总数失败: {e}"}), 500

    # --- 数据列表 ---
    items = []
    if total > 0 and limit > 0:
        try:
            items = query(f"""
                SELECT house_code, title, district, bizcircle, community,
                       layout, area, orientation, decoration,
                       total_price, unit_price, building_year, building_type,
                       floor_info, tag, url, publish_time
                FROM houses
                WHERE {where}
                ORDER BY id DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
        except Exception as e:
            return jsonify({"error": f"查询明细失败: {e}"}), 500

    return jsonify({
        "source": source,
        "total": total,
        "by_source": by_source,
        "items": items,
        "limit": limit,
        "offset": offset,
    })


@app.route('/api/control/export_sql')
def api_control_export_sql():
    """流式导出 houses 表为 MySQL dump 格式 SQL 文件

    参数（GET）:
        source: all | lianjia | wuba | api | synth（默认 all）

    返回: application/sql 响应，Content-Disposition 触发浏览器下载
    """
    from datetime import datetime
    from decimal import Decimal

    source = request.args.get('source', 'all').strip()

    # --- source 过滤条件 ---
    if source == 'api':
        where = "LEFT(house_code, 4) = 'API_'"
    elif source == 'synth':
        where = "LEFT(house_code, 4) = 'SYN_'"
    elif source == 'wuba':
        where = "house_code REGEXP '^[0-9]+$'"
    elif source == 'lianjia':
        where = ("house_code NOT REGEXP '^[0-9]+$' "
                 "AND LEFT(house_code, 4) <> 'API_' "
                 "AND LEFT(house_code, 4) <> 'SYN_'")
    elif source == 'all':
        where = "1=1"
    else:
        return jsonify({
            "error": "未知 source: " + source,
            "available_sources": ["all", "lianjia", "wuba", "api", "synth"]
        }), 400

    def _sql_val(v):
        """Python 值 → SQL 字面量"""
        if v is None:
            return 'NULL'
        if isinstance(v, bool):
            return '1' if v else '0'
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, datetime):
            return "'" + v.strftime('%Y-%m-%d %H:%M:%S') + "'"
        if isinstance(v, (bytes, bytearray)):
            return "0x" + v.hex().upper()
        # 字符串：转义反斜杠 / 单引号 / 换行 / 控制字符
        s = str(v)
        s = (s.replace('\\', '\\\\')
              .replace("'", "\\'")
              .replace('\n', '\\n')
              .replace('\r', '\\r')
              .replace('\x00', '\\0')
              .replace('\x1a', '\\Z'))
        return "'" + s + "'"

    def _row_to_values(row):
        """一行 → SQL VALUES 子句"""
        return '(' + ','.join(_sql_val(v) for v in row) + ')'

    def generate():
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        yield '-- MySQL dump 10.13\n'
        yield '--\n'
        yield '-- Host: ' + config.MYSQL_CONFIG['host'] + '    Database: ' + config.MYSQL_CONFIG['database'] + '\n'
        yield '-- Export time: ' + ts + '\n'
        yield '-- Source filter: ' + source + '\n'
        yield '-- ------------------------------------------------------\n'
        yield '\n'
        yield '/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;\n'
        yield '/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;\n'
        yield '/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;\n'
        yield '/*!40101 SET NAMES utf8mb4 */;\n'
        yield '/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;\n'
        yield '/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;\n'
        yield "/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;\n"
        yield '/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;\n'
        yield '\n'

        conn = None
        row_count = 0
        try:
            conn = db()
            with conn.cursor() as cur:
                # 1. 表结构（SHOW CREATE TABLE 动态拿）
                cur.execute('SHOW CREATE TABLE `houses`')
                _, create_sql = cur.fetchone()
                yield '--\n-- Table structure for table `houses`\n--\n\n'
                yield 'DROP TABLE IF EXISTS `houses`;\n'
                yield '/*!40101 SET @saved_cs_client     = @@character_set_client */;\n'
                yield '/*!40101 SET character_set_client = utf8mb4 */;\n'
                yield create_sql + ';\n'
                yield '/*!40101 SET character_set_client = @saved_cs_client */;\n'
                yield '\n'

                # 2. 数据（流式游标，每 200 条合一组）
                yield '--\n-- Dumping data for table `houses`\n--\n\n'
                yield '/*!40000 ALTER TABLE `houses` DISABLE KEYS */;\n'

                cur.execute('SELECT * FROM `houses` WHERE ' + where + ' ORDER BY id')

                BATCH = 200
                batch = []
                for row in cur:
                    row_count += 1
                    batch.append(_row_to_values(row))
                    if len(batch) >= BATCH:
                        yield 'INSERT INTO `houses` VALUES\n  ' + ',\n  '.join(batch) + ';\n'
                        batch = []
                if batch:
                    yield 'INSERT INTO `houses` VALUES\n  ' + ',\n  '.join(batch) + ';\n'

                yield '/*!40000 ALTER TABLE `houses` ENABLE KEYS */;\n'
                yield '\n-- Dump completed: ' + str(row_count) + ' rows (source=' + source + ')\n'

        except Exception as e:
            yield '\n-- ERROR: ' + str(e) + '\n'
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        # 还原全局变量
        yield '\n'
        yield '/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;\n'
        yield '/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;\n'
        yield '/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;\n'
        yield '/*!40101 SET NAMES utf8 */;\n'
        yield '/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;\n'
        yield '/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;\n'
        yield '/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;\n'
        yield '/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;\n'
        yield '\n-- End of dump\n'

    ts2 = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = 'houses_' + source + '_' + ts2 + '.sql'

    return Response(
        generate(),
        mimetype='application/sql; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename="' + filename + '"',
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )



if __name__ == '__main__':
    cfg = config.FLASK_CONFIG
    print(f"启动: http://{cfg['host']}:{cfg['port']}")
    # debug=False 以避免 reloader 产生多进程
    app.run(host=cfg['host'], port=cfg['port'], debug=False, use_reloader=False)
