"""
基于真实数据 + 重庆 37 区县经济地理特征的智能生成器
生成 5 万条高质量重庆二手房数据

设计原则：
1. 保留 1671 条真实数据（链家 152 + 58 1519）
2. 基于真实数据的字段分布（layout/area/orientation/decoration/floor/year）
3. 各区县根据 GDP/商圈/房价梯队调整价格
4. 户型/面积/楼层/年代/装修 等根据区县特征加权
"""
import sys
import os
import time
import random
import json
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
import config


# ============================================================
# 重庆 37 区县经济/房价档案（基于公开资料整理）
# ============================================================
# GDP 单位：亿元（2024 年估算）
# unit_price_range：元/㎡（参考 2024-2025 重庆二手房均价）
# bizcircle：核心商圈/特色板块

DISTRICT_PROFILES = {
    # ============ 主城核心 9 区（高房价）============
    'yuzhong': {
        'name': '渝中区', 'tier': 'core', 'gdp_rank': 5, 'gdp_billion': 1691,
        'unit_price_range': (12000, 35000),
        'bizcircles': ['解放碑', '朝天门', '大坪', '化龙桥', '两路口', '上清寺', '大溪沟', '鹅岭', '储奇门', '较场口'],
        'communities': ['协信公馆', '重庆中心', '鹅岭峯', '国泰艺术中心', '融创白象街', '万科翡翠都会', '重庆天地', '万科御澜道', '国浩18T', '重庆天地雍江艺庭'],
        'area_weight': {'小户型': 0.4, '中户型': 0.4, '大户型': 0.2},
        'floor_pref': '中高层为主', 'year_range': (2000, 2022),
        'decoration_weight': {'精装': 0.6, '简装': 0.25, '毛坯': 0.05, '豪装': 0.10},
    },
    'jiangbei': {
        'name': '江北区', 'tier': 'core', 'gdp_rank': 3, 'gdp_billion': 1924,
        'unit_price_range': (13000, 32000),
        'bizcircles': ['观音桥', '江北嘴', '五里店', '大石坝', '北滨路', '石马河', '寸滩', '海尔路', '洋河', '黄泥磅'],
        'communities': ['北滨壹号', '国金中心', '万科观澜', '中海天钻', '龙湖源著', '协信中心', '凯德九章', '金融城', '珠江太阳城', '金科廊桥水岸'],
        'area_weight': {'小户型': 0.3, '中户型': 0.45, '大户型': 0.25},
        'floor_pref': '中高层为主', 'year_range': (2003, 2023),
        'decoration_weight': {'精装': 0.55, '简装': 0.30, '毛坯': 0.05, '豪装': 0.10},
    },
    'yubei': {
        'name': '渝北区', 'tier': 'core', 'gdp_rank': 1, 'gdp_billion': 2769,
        'unit_price_range': (10000, 25000),
        'bizcircles': ['新牌坊', '龙溪', '冉家坝', '回兴', '两路', '龙塔', '黄泥磅', '龙头寺', '鸳鸯', '悦来', '中央公园', '礼嘉'],
        'communities': ['龙湖紫都城', '棕榈泉', '融创御锦', '万科城', '金科天籁城', '恒大御景湾', '协信星都会', '华宇北国风光', '金科金砂水岸', '万科未来城'],
        'area_weight': {'小户型': 0.25, '中户型': 0.5, '大户型': 0.25},
        'floor_pref': '中高层为主', 'year_range': (2005, 2024),
        'decoration_weight': {'精装': 0.5, '简装': 0.35, '毛坯': 0.10, '豪装': 0.05},
    },
    'nanan': {
        'name': '南岸区', 'tier': 'core', 'gdp_rank': 7, 'gdp_billion': 1050,
        'unit_price_range': (9000, 22000),
        'bizcircles': ['南坪', '弹子石', '南滨路', '茶园', '四公里', '海棠溪', '铜元局', '回龙湾', '学府大道', '长生桥'],
        'communities': ['融侨城', '上海城', '万达广场', '江南国际', '协信城', '国美江天御府', '金科中央公园', '和记黄埔御峰', '华宇江南枫庭', '东海长洲'],
        'area_weight': {'小户型': 0.30, '中户型': 0.50, '大户型': 0.20},
        'floor_pref': '中高层为主', 'year_range': (2003, 2023),
        'decoration_weight': {'精装': 0.45, '简装': 0.40, '毛坯': 0.10, '豪装': 0.05},
    },
    'shapingba': {
        'name': '沙坪坝区', 'tier': 'core', 'gdp_rank': 8, 'gdp_billion': 1220,
        'unit_price_range': (8000, 20000),
        'bizcircles': ['三峡广场', '大学城', '西永', '磁器口', '歌乐山', '井口', '双碑', '石井坡', '土主', '回龙坝'],
        'communities': ['龙湖U城', '富力城', '协信城立方', '金科廊桥水岸', '万达华府', '华宇金沙东岸', '首创城', '金融街融景城', '融创滨江壹号', '龙湖拉特芳斯'],
        'area_weight': {'小户型': 0.30, '中户型': 0.50, '大户型': 0.20},
        'floor_pref': '中高层为主', 'year_range': (2003, 2023),
        'decoration_weight': {'精装': 0.45, '简装': 0.40, '毛坯': 0.10, '豪装': 0.05},
    },
    'jiulongpo': {
        'name': '九龙坡区', 'tier': 'core', 'gdp_rank': 2, 'gdp_billion': 2060,
        'unit_price_range': (8000, 19000),
        'bizcircles': ['杨家坪', '万象城', '石桥铺', '谢家湾', '黄桷坪', '中梁山', '白市驿', '西彭', '陶家', '二郎'],
        'communities': ['华润二十四城', '万科西城', '富力城', '金科太阳海岸', '保利爱尚里', '中粮鸿云', '龙湖西苑', '协信天骄城', '兴茂盛世北辰', '斌鑫江南御府'],
        'area_weight': {'小户型': 0.30, '中户型': 0.50, '大户型': 0.20},
        'floor_pref': '中高层为主', 'year_range': (2003, 2023),
        'decoration_weight': {'精装': 0.45, '简装': 0.40, '毛坯': 0.10, '豪装': 0.05},
    },
    'dadukou': {
        'name': '大渡口区', 'tier': 'core', 'gdp_rank': 28, 'gdp_billion': 506,
        'unit_price_range': (6500, 14000),
        'bizcircles': ['九宫庙', '茄子溪', '跳磴', '新山村', '春晖路', '八桥', '建胜', '钓鱼嘴'],
        'communities': ['佳禾钰茂', '中交丽景', '东海假日', '国瑞城', '天泰凤阳小镇', '晋愉V时代', '蓝谷小镇', '祥和御馨园', '科能路100号', '顺祥壹街'],
        'area_weight': {'小户型': 0.40, '中户型': 0.45, '大户型': 0.15},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.35, '简装': 0.45, '毛坯': 0.15, '豪装': 0.05},
    },
    'banan': {
        'name': '巴南区', 'tier': 'core', 'gdp_rank': 14, 'gdp_billion': 950,
        'unit_price_range': (6500, 15000),
        'bizcircles': ['李家沱', '龙洲湾', '鱼洞', '花溪', '南泉', '界石', '一品', '木洞', '麻柳嘴'],
        'communities': ['协信天骄星城', '融汇半岛', '中交锦悦', '旭辉城', '华宇锦绣花城', '江上公馆', '龙洲湾一号', '云篆世家', '巴南府', '融科金色时代'],
        'area_weight': {'小户型': 0.35, '中户型': 0.50, '大户型': 0.15},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2023),
        'decoration_weight': {'精装': 0.40, '简装': 0.45, '毛坯': 0.10, '豪装': 0.05},
    },
    'beibei': {
        'name': '北碚区', 'tier': 'core', 'gdp_rank': 16, 'gdp_billion': 720,
        'unit_price_range': (5500, 13000),
        'bizcircles': ['北碚城区', '城南新区', '歇马', '蔡家', '水土', '静观', '柳荫', '三圣'],
        'communities': ['海宇中央府', '金科城', '中庚城', '北温泉九号', '奥林匹克花园', '正源福源', '融创紫泉枫丹', '龙湖椿山', '金科集美嘉悦', '华宇观澜华府'],
        'area_weight': {'小户型': 0.35, '中户型': 0.50, '大户型': 0.15},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2023),
        'decoration_weight': {'精装': 0.35, '简装': 0.50, '毛坯': 0.10, '豪装': 0.05},
    },
    # ============ 渝西 8 区（中房价）============
    'jiangjin': {
        'name': '江津区', 'tier': 'west', 'gdp_rank': 9, 'gdp_billion': 1490,
        'unit_price_range': (4500, 11000),
        'bizcircles': ['几江', '鼎山', '双福', '德感', '珞璜', '白沙', '油溪', '石门'],
        'communities': ['江津金科中央公园城', '祥瑞城', '乾和新天汇', '港龙花园', '鼎山雅苑', '江湾城', '金科世界城', '福城家园', '祥瑞水木年华', '华城丽都'],
        'area_weight': {'小户型': 0.40, '中户型': 0.50, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2023),
        'decoration_weight': {'精装': 0.30, '简装': 0.55, '毛坯': 0.10, '豪装': 0.05},
    },
    'yongchuan': {
        'name': '永川区', 'tier': 'west', 'gdp_rank': 11, 'gdp_billion': 1180,
        'unit_price_range': (4500, 10000),
        'bizcircles': ['萱花路', '渝西广场', '兴龙湖', '神女湖', '凤凰湖', '三教', '板桥', '朱沱'],
        'communities': ['协信中心', '金科中央公园城', '万达广场', '凰城华府', '永川国际', '兴龙湖一号', '华森盛世', '恒大翡翠湾', '东方剑桥', '名豪国际'],
        'area_weight': {'小户型': 0.40, '中户型': 0.50, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2023),
        'decoration_weight': {'精装': 0.30, '简装': 0.55, '毛坯': 0.10, '豪装': 0.05},
    },
    'hechuan': {
        'name': '合川区', 'tier': 'west', 'gdp_rank': 12, 'gdp_billion': 1100,
        'unit_price_range': (4000, 9500),
        'bizcircles': ['合阳城', '钓鱼城', '南津街', '大石', '云门', '钱塘', '草街'],
        'communities': ['合川缤果城', '金科天籁城', '宝龙城市广场', '北城华府', '江城明珠', '东郡华府', '水映长滩', '合川中学教师公寓', '丽景花园', '江上城'],
        'area_weight': {'小户型': 0.40, '中户型': 0.50, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2023),
        'decoration_weight': {'精装': 0.30, '简装': 0.55, '毛坯': 0.10, '豪装': 0.05},
    },
    'dazu': {
        'name': '大足区', 'tier': 'west', 'gdp_rank': 19, 'gdp_billion': 750,
        'unit_price_range': (3500, 8500),
        'bizcircles': ['棠香', '龙岗', '双桥', '龙水', '万古', '三驱', '珠溪'],
        'communities': ['大足印象', '香山美地', '海棠国际', '万和华府', '金科中央公园城', '盛世华城', '宏声花园', '棠城御府', '东方家园', '圣境新城'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.25, '简装': 0.60, '毛坯': 0.10, '豪装': 0.05},
    },
    'qijiang': {
        'name': '綦江区', 'tier': 'west', 'gdp_rank': 22, 'gdp_billion': 650,
        'unit_price_range': (3500, 8000),
        'bizcircles': ['古南', '文龙', '三江', '打通', '石角', '东溪', '赶水'],
        'communities': ['綦江金科', '恒大御景湾', '新都汇', '翡翠城', '凤凰城', '盛邦华府', '东方新城', '天和人家', '江润国际', '锦辉雅居'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.20, '简装': 0.65, '毛坯': 0.10, '豪装': 0.05},
    },
    'tongnan': {
        'name': '潼南区', 'tier': 'west', 'gdp_rank': 20, 'gdp_billion': 700,
        'unit_price_range': (3500, 8000),
        'bizcircles': ['桂林', '梓潼', '凉风垭', '上和', '塘坝', '小渡', '古溪'],
        'communities': ['潼南金福新区', '御景江山', '巴川府', '书香门第', '上和园', '隆鑫中央公园', '龙湖春江天镜', '华厦城', '融创滨江一号', '锦和华府'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.20, '简装': 0.65, '毛坯': 0.10, '豪装': 0.05},
    },
    'tongliang': {
        'name': '铜梁区', 'tier': 'west', 'gdp_rank': 18, 'gdp_billion': 800,
        'unit_price_range': (3800, 9000),
        'bizcircles': ['巴川', '东城', '南城', '蒲吕', '旧县', '安居', '虎峰'],
        'communities': ['铜梁金科', '御景天成', '城市今典', '龙城御府', '尚风名居', '金悦城', '丹桂花园', '东方明珠', '巴川御府', '盛世豪庭'],
        'area_weight': {'小户型': 0.40, '中户型': 0.50, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.25, '简装': 0.60, '毛坯': 0.10, '豪装': 0.05},
    },
    'bishan': {
        'name': '璧山区', 'tier': 'west', 'gdp_rank': 13, 'gdp_billion': 1000,
        'unit_price_range': (4500, 10500),
        'bizcircles': ['璧城', '璧泉', '青杠', '大兴', '河边', '正兴', '广普'],
        'communities': ['璧山金科', '绿城上岛', '御湖一号', '新加坡花园', '万和华府', '恒大御景湾', '璧山中学教师公寓', '秀湖鹭岛', '北城丽景', '南园'],
        'area_weight': {'小户型': 0.40, '中户型': 0.50, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2023),
        'decoration_weight': {'精装': 0.30, '简装': 0.55, '毛坯': 0.10, '豪装': 0.05},
    },
    'rongchang': {
        'name': '荣昌区', 'tier': 'west', 'gdp_rank': 17, 'gdp_billion': 830,
        'unit_price_range': (3500, 8000),
        'bizcircles': ['昌元', '昌州', '广顺', '峰高', '双河', '安富', '仁义'],
        'communities': ['荣昌金科', '荣城御景', '金福花园', '新世纪花园', '香国大城', '国泰花园', '西部陶都', '龙湖观萃', '城南人家', '东方明珠'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.20, '简装': 0.65, '毛坯': 0.10, '豪装': 0.05},
    },
    # ============ 渝东北 11 区（低房价）============
    'wanzhou': {
        'name': '万州区', 'tier': 'northeast', 'gdp_rank': 6, 'gdp_billion': 1200,
        'unit_price_range': (4500, 9000),
        'bizcircles': ['高笋塘', '太白', '钟鼓楼', '周家坝', '天城', '五桥', '百安坝', '龙都', '新田', '余家'],
        'communities': ['万州金科', '万达广场', '万州御景', '江南CBD', '新世纪花园', '科友星城', '海宁皮草城公寓', '万二中教师公寓', '飞川花园', '锦江花园'],
        'area_weight': {'小户型': 0.40, '中户型': 0.50, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.25, '简装': 0.60, '毛坯': 0.10, '豪装': 0.05},
    },
    'kaizhou': {
        'name': '开州区', 'tier': 'northeast', 'gdp_rank': 15, 'gdp_billion': 850,
        'unit_price_range': (3500, 7500),
        'bizcircles': ['汉丰', '云枫', '镇东', '丰乐', '文峰', '赵家', '临江', '长沙'],
        'communities': ['开州金科', '开州广场', '假日国际', '汉丰湖畔', '新世纪花园', '北苑新城', '金科天湖小镇', '海通花园', '龙珠名都', '御景天下'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.20, '简装': 0.65, '毛坯': 0.10, '豪装': 0.05},
    },
    'liangping': {
        'name': '梁平区', 'tier': 'northeast', 'gdp_rank': 21, 'gdp_billion': 680,
        'unit_price_range': (3200, 7000),
        'bizcircles': ['梁山', '双桂', '新城', '老城', '屏锦', '袁驿', '新盛'],
        'communities': ['梁平金科', '双桂新城', '梁平中学教师公寓', '兴茂花园', '新世纪花园', '北苑花园', '东方新城', '城市今典', '锦绣华府', '锦绣家园'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'changshou': {
        'name': '长寿区', 'tier': 'northeast', 'gdp_rank': 10, 'gdp_billion': 1078,
        'unit_price_range': (3800, 8500),
        'bizcircles': ['凤城', '晏家', '江南', '渡舟', '八颗', '新市', '邻封'],
        'communities': ['长寿金科', '长寿湖', '新市花园', '东方剑桥', '北城华府', '中央公园', '城投花园', '长寿中学教师公寓', '凤山花园', '锦江花园'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.20, '简装': 0.65, '毛坯': 0.10, '豪装': 0.05},
    },
    'fengjie': {
        'name': '奉节县', 'tier': 'northeast', 'gdp_rank': 27, 'gdp_billion': 450,
        'unit_price_range': (3000, 7000),
        'bizcircles': ['永安', '鱼复', '夔州', '白帝', '草堂', '兴隆', '吐祥'],
        'communities': ['奉节金科', '夔州新城', '人民广场', '白帝城', '新世纪花园', '兴隆花园', '西部新区', '三马后山', '西部国际', '国际广场'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'wushan': {
        'name': '巫山县', 'tier': 'northeast', 'gdp_rank': 32, 'gdp_billion': 280,
        'unit_price_range': (3000, 7000),
        'bizcircles': ['高唐', '龙门', '巫峡', '庙宇', '大昌', '福田', '官渡'],
        'communities': ['巫山金科', '高唐新区', '巫峡广场', '人民广场', '新世纪花园', '滨江花园', '龙门花园', '巫山中学教师公寓', '西坪花园', '中央公园'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2021),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'yunyang': {
        'name': '云阳县', 'tier': 'northeast', 'gdp_rank': 23, 'gdp_billion': 600,
        'unit_price_range': (3200, 7500),
        'bizcircles': ['双江', '青龙', '人和', '盘石', '江口', '南溪', '高阳'],
        'communities': ['云阳金科', '双江新区', '云阳广场', '新世纪花园', '北城花园', '三合花园', '江上城', '中央公园', '盘石新城', '两江广场'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.20, '简装': 0.65, '毛坯': 0.10, '豪装': 0.05},
    },
    'zhongxian': {
        'name': '忠县', 'tier': 'northeast', 'gdp_rank': 26, 'gdp_billion': 480,
        'unit_price_range': (3000, 7000),
        'bizcircles': ['忠州', '白公', '新生', '乌杨', '任家', '新立', '东溪'],
        'communities': ['忠县金科', '忠州广场', '人民广场', '白公新城', '新世纪花园', '御景江山', '忠县中学教师公寓', '三马路花园', '城投花园', '东方新城'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2021),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'fengdu': {
        'name': '丰都县', 'tier': 'northeast', 'gdp_rank': 29, 'gdp_billion': 380,
        'unit_price_range': (3000, 6800),
        'bizcircles': ['三合', '名山', '高家', '社坛', '虎威', '树人', '龙河'],
        'communities': ['丰都金科', '名山新城', '新世纪花园', '平都花园', '丰都中学教师公寓', '滨江花园', '城投花园', '龙河新城', '三合花园', '御景江山'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2021),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'dianjiang': {
        'name': '垫江县', 'tier': 'northeast', 'gdp_rank': 30, 'gdp_billion': 350,
        'unit_price_range': (3000, 7000),
        'bizcircles': ['桂溪', '桂阳', '新民', '沙坪', '周嘉', '高安', '澄溪'],
        'communities': ['垫江金科', '桂溪花园', '新世纪花园', '北苑花园', '东方新城', '城投花园', '垫江中学教师公寓', '三合花园', '南部新城', '中央公园'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2021),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'wuxi': {
        'name': '巫溪县', 'tier': 'northeast', 'gdp_rank': 35, 'gdp_billion': 180,
        'unit_price_range': (2500, 5500),
        'bizcircles': ['柏杨', '城厢', '凤凰', '宁厂', '上磺', '古路', '文峰'],
        'communities': ['巫溪金科', '柏杨新城', '人民广场', '新世纪花园', '巫溪中学教师公寓', '城投花园', '三合花园', '马镇坝', '中央公园', '城厢花园'],
        'area_weight': {'小户型': 0.55, '中户型': 0.35, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2020),
        'decoration_weight': {'精装': 0.10, '简装': 0.65, '毛坯': 0.20, '豪装': 0.05},
    },
    'chengkou': {
        'name': '城口县', 'tier': 'northeast', 'gdp_rank': 37, 'gdp_billion': 100,
        'unit_price_range': (2200, 5000),
        'bizcircles': ['葛城', '复兴', '庙坝', '修齐', '高观', '明通', '岚天'],
        'communities': ['城口金科', '葛城新城', '人民广场', '新世纪花园', '城口中学教师公寓', '城投花园', '复兴花园', '三合花园', '中央公园', '城北花园'],
        'area_weight': {'小户型': 0.55, '中户型': 0.35, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2020),
        'decoration_weight': {'精装': 0.10, '简装': 0.65, '毛坯': 0.20, '豪装': 0.05},
    },
    # ============ 渝东南 6 区（最低房价）============
    'nanchuan': {
        'name': '南川区', 'tier': 'southeast', 'gdp_rank': 25, 'gdp_billion': 500,
        'unit_price_range': (3800, 8500),
        'bizcircles': ['东城', '西城', '南城', '水江', '大观', '金山', '鸣玉'],
        'communities': ['南川金科', '南川中学教师公寓', '新世纪花园', '中央公园', '北苑花园', '东方新城', '城投花园', '隆化花园', '三合花园', '锦绣华府'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.20, '简装': 0.65, '毛坯': 0.10, '豪装': 0.05},
    },
    'pengshui': {
        'name': '彭水县', 'tier': 'southeast', 'gdp_rank': 31, 'gdp_billion': 384,
        'unit_price_range': (3000, 7000),
        'bizcircles': ['汉葭', '绍庆', '靛水', '保家', '郁山', '桑柘', '鹿角'],
        'communities': ['彭水金科', '汉葭新城', '人民广场', '新世纪花园', '彭水中学教师公寓', '城投花园', '三合花园', '郁山花园', '中央公园', '北苑花园'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2021),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'youyang': {
        'name': '酉阳县', 'tier': 'southeast', 'gdp_rank': 33, 'gdp_billion': 260,
        'unit_price_range': (2800, 6500),
        'bizcircles': ['桃花源', '钟多', '龙潭', '麻旺', '酉酬', '大溪', '涂市'],
        'communities': ['酉阳金科', '桃花源新城', '人民广场', '新世纪花园', '酉阳中学教师公寓', '城投花园', '三合花园', '龙潭花园', '中央公园', '北苑花园'],
        'area_weight': {'小户型': 0.55, '中户型': 0.35, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2020),
        'decoration_weight': {'精装': 0.10, '简装': 0.65, '毛坯': 0.20, '豪装': 0.05},
    },
    'xiushan': {
        'name': '秀山县', 'tier': 'southeast', 'gdp_rank': 28, 'gdp_billion': 447,
        'unit_price_range': (3200, 7500),
        'bizcircles': ['中和', '乌杨', '平凯', '清溪', '石耶', '洪安', '龙池'],
        'communities': ['秀山金科', '中和新城', '人民广场', '新世纪花园', '秀山中学教师公寓', '城投花园', '三合花园', '北苑花园', '中央公园', '乌杨花园'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2021),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'shizhu': {
        'name': '石柱县', 'tier': 'southeast', 'gdp_rank': 30, 'gdp_billion': 350,
        'unit_price_range': (3000, 6800),
        'bizcircles': ['南宾', '西沱', '黄水', '悦崃', '临溪', '大歇', '桥头'],
        'communities': ['石柱金科', '南宾新城', '人民广场', '新世纪花园', '石柱中学教师公寓', '城投花园', '三合花园', '北苑花园', '中央公园', '西沱花园'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2021),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'wulong': {
        'name': '武隆区', 'tier': 'southeast', 'gdp_rank': 31, 'gdp_billion': 280,
        'unit_price_range': (3000, 7500),
        'bizcircles': ['巷口', '桐梓', '仙女山', '白马', '江口', '羊角', '平桥'],
        'communities': ['武隆金科', '巷口新城', '人民广场', '新世纪花园', '武隆中学教师公寓', '城投花园', '三合花园', '仙女山花园', '中央公园', '北苑花园'],
        'area_weight': {'小户型': 0.50, '中户型': 0.40, '大户型': 0.10},
        'floor_pref': '中低楼层', 'year_range': (2005, 2021),
        'decoration_weight': {'精装': 0.15, '简装': 0.65, '毛坯': 0.15, '豪装': 0.05},
    },
    'qianjiang': {
        'name': '黔江区', 'tier': 'southeast', 'gdp_rank': 27, 'gdp_billion': 393,
        'unit_price_range': (3500, 8000),
        'bizcircles': ['城东', '城南', '城西', '正阳', '舟白', '冯家', '濯水'],
        'communities': ['黔江金科', '正阳新城', '人民广场', '新世纪花园', '黔江中学教师公寓', '城投花园', '三合花园', '北苑花园', '中央公园', '舟白花园'],
        'area_weight': {'小户型': 0.45, '中户型': 0.45, '大户型': 0.10},
        'floor_pref': '中楼层为主', 'year_range': (2005, 2022),
        'decoration_weight': {'精装': 0.20, '简装': 0.65, '毛坯': 0.10, '豪装': 0.05},
    },
}


# 户型模板（基于真实数据统计）
LAYOUT_TEMPLATES = [
    # 占比从 58/链家 真实数据估算
    ('1室1厅', 0.10, 35, 55),
    ('2室1厅', 0.30, 55, 85),
    ('2室2厅', 0.18, 75, 110),
    ('3室1厅', 0.10, 80, 110),
    ('3室2厅', 0.22, 90, 140),
    ('4室2厅', 0.07, 130, 200),
    ('4室3厅', 0.02, 180, 280),
    ('5室2厅', 0.01, 200, 320),
]

ORIENTATIONS = ['南', '南北', '东南', '南西', '东', '西', '北', '东北', '西南']
ORIENTATION_WEIGHTS = [0.30, 0.25, 0.15, 0.08, 0.08, 0.05, 0.04, 0.03, 0.02]

FLOOR_TYPES = ['低楼层', '中楼层', '高楼层', '顶层', '底层']
FLOOR_WEIGHTS = [0.20, 0.50, 0.20, 0.05, 0.05]

BUILDING_TYPES = ['板楼', '塔楼', '板塔结合', '平房']
BUILDING_WEIGHTS = [0.45, 0.20, 0.30, 0.05]

TAGS_POOL = ['地铁', '近地铁', '学区房', '南北通透', '满五唯一', '近商圈', '江景房', '公园', '品质小区', '随时看房', 'VR看房', '拎包入住', '新上', '降价', '热门', '次新', '老破小', '大平层', '复式', '跃层']


def weighted_choice(choices_with_weights):
    """带权重随机选择"""
    items, weights = zip(*choices_with_weights)
    return random.choices(items, weights=weights, k=1)[0]


def pick_layout():
    """根据权重选户型"""
    templates = [(t, w) for t, w, _, _ in LAYOUT_TEMPLATES]
    return weighted_choice(templates)


def pick_area_for_layout(layout):
    """根据户型返回面积范围"""
    for t, _, a_min, a_max in LAYOUT_TEMPLATES:
        if t == layout:
            return random.uniform(a_min, a_max)
    return 80.0


def pick_orientation():
    return random.choices(ORIENTATIONS, weights=ORIENTATION_WEIGHTS, k=1)[0]


def pick_floor():
    return random.choices(FLOOR_TYPES, weights=FLOOR_WEIGHTS, k=1)[0]


def pick_building_type():
    return random.choices(BUILDING_TYPES, weights=BUILDING_WEIGHTS, k=1)[0]


def pick_decoration(weight_dict):
    return weighted_choice(list(weight_dict.items()))


def pick_year(year_range):
    return random.randint(year_range[0], year_range[1])


def pick_tags(profile):
    """根据区县 tier 决定 tag 数量和种类"""
    tier = profile['tier']
    if tier == 'core':
        n_tags = random.choices([1, 2, 3, 4], weights=[0.4, 0.4, 0.15, 0.05])[0]
    elif tier == 'west':
        n_tags = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
    else:
        n_tags = random.choices([0, 1, 2, 3], weights=[0.2, 0.5, 0.25, 0.05])[0]
    if n_tags == 0:
        return ''
    return '|'.join(random.sample(TAGS_POOL, min(n_tags, len(TAGS_POOL))))


def pick_unit_price(profile):
    """在区县价格范围内随机（含一些极端值）"""
    lo, hi = profile['unit_price_range']
    # 用 beta 分布，更集中在中位数附近
    r = random.betavariate(2, 2)
    price = lo + (hi - lo) * r
    # 20% 概率出现极端值（更接近两端）
    if random.random() < 0.2:
        if random.random() < 0.5:
            price = lo + (hi - lo) * random.uniform(0, 0.15)
        else:
            price = lo + (hi - lo) * random.uniform(0.85, 1.0)
    # 2% 概率出现离谱值（拉宽分布）
    if random.random() < 0.02:
        price = price * random.uniform(0.5, 0.7)  # 低价
    return round(price / 100) * 100  # 100 取整


def pick_bizcircle(profile):
    return random.choice(profile['bizcircles'])


def pick_community(profile):
    return random.choice(profile['communities'])


def make_title(district_name, bizcircle, layout, area, community, tags, decoration):
    """生成房源标题"""
    parts = []
    if '地铁' in tags or '近地铁' in tags:
        parts.append('地铁口')
    if '学区' in tags:
        parts.append('学区房')
    if '江景' in tags:
        parts.append('江景')
    if '公园' in tags:
        parts.append('公园旁')
    parts.append(lay := f'{layout.replace("室", "室")}')
    if decoration == '豪装':
        parts.append('豪装')
    elif decoration == '精装':
        parts.append('精装')
    if '大平层' in tags or area > 200:
        parts.append('大平层')
    if '南北通透' in tags:
        parts.append('南北通透')
    parts.append(f'{area:.0f}㎡')
    parts.append(f'{community}')
    return ' '.join(parts)


def make_floor_info(floor_type, total_floors):
    """生成楼层信息"""
    return f'{floor_type}/共{total_floors}层'


def gen_publish_time(days_ago_max=365):
    """随机发布时间（过去 N 天内）"""
    days_ago = random.randint(0, days_ago_max)
    seconds = random.randint(0, 86400)
    return time.strftime('%Y-%m-%d', time.localtime(time.time() - days_ago * 86400 - seconds))


def gen_follow_count():
    """关注人数：通常 0-500，但有少量热门房"""
    if random.random() < 0.05:
        return random.randint(200, 1000)
    return random.choices(
        [0, random.randint(1, 10), random.randint(10, 50), random.randint(50, 200)],
        weights=[0.30, 0.30, 0.25, 0.15]
    )[0]


def gen_total_price(unit_price, area):
    return round(unit_price * area / 10000, 1)  # 转为万元


def gen_house(district, profile, idx):
    """生成单条房源"""
    layout = pick_layout()
    area = pick_area_for_layout(layout)
    # 20% 概率跟户型建议不符（小户型偶尔很大或大户型偶尔很小）
    if random.random() < 0.05:
        area = random.uniform(30, 350)
    area = round(area, 1)

    orientation = pick_orientation()
    floor = pick_floor()
    total_floors = random.randint(6, 33)
    floor_info = make_floor_info(floor, total_floors)

    decoration = pick_decoration(profile['decoration_weight'])
    year = pick_year(profile['year_range'])
    building_type = pick_building_type()

    bizcircle = pick_bizcircle(profile)
    community = pick_community(profile)

    unit_price = pick_unit_price(profile)
    total_price = gen_total_price(unit_price, area)

    # 户型细分
    if random.random() < 0.05:
        layout = layout + '带书房'
    elif random.random() < 0.03:
        layout = layout + '带花园'
    elif random.random() < 0.02:
        layout = layout + '带车位'

    tags = pick_tags(profile)
    title = make_title(profile['name'], bizcircle, layout, area, community, tags, decoration)

    return {
        'house_code': f"SYN_{district}_{int(time.time() * 1000)}_{idx}",
        'title': title,
        'district': district,
        'bizcircle': bizcircle,
        'community': community,
        'layout': layout,
        'area': area,
        'orientation': orientation,
        'decoration': decoration,
        'floor_info': floor_info,
        'building_year': year,
        'building_type': building_type,
        'total_price': total_price,
        'unit_price': unit_price,
        'follow_count': gen_follow_count(),
        'publish_time': gen_publish_time(),
        'tag': tags,
        'url': f'https://generated.local/{district}/{idx}',
    }


def main(target=50000):
    """
    智能生成数据到目标数量（默认 5 万）

    流程：
      1. 读取 houses 表当前数量
      2. 计算缺口 = 目标 - 当前
      3. 按 37 区县经济特征（GDP + tier）分配数量
      4. 用真实楼盘名 + beta 分布生成单价
      5. 批量入库（ON DUPLICATE KEY UPDATE 自动去重）

    返回：dict { inserted, total, message }
    """
    print(f'=== 智能生成数据到 {target} 条 ===')
    print()
    print('【1】读取当前数据...')
    conn = pymysql.connect(**{k:v for k,v in config.MYSQL_CONFIG.items() if k != 'autocommit'})
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM houses")
    current_count = cur.fetchone()[0]
    print(f'   当前数据: {current_count} 条')
    print()

    target_total = target
    need_to_generate = target_total - current_count
    if need_to_generate <= 0:
        print(f'   ✅ 已达到目标 ({current_count} >= {target_total})，无需生成')
        conn.close()
        return {
            "inserted": 0,
            "total": current_count,
            "message": f"数据已充足：{current_count} 条（目标 {target_total}）"
        }
    print(f'【2】目标总数: {target_total} 条')
    print(f'   需要生成: {need_to_generate} 条')
    print()

    # 7 个 tier 权重分配（基于真实数据分布 + 房源集中度）
    # 主城 9 区核心商圈集中
    tier_weights = {
        'core': 0.55,       # 9 区
        'west': 0.25,       # 8 区
        'northeast': 0.13,  # 11 区
        'southeast': 0.07,  # 6 区
    }

    # 计算每区权重
    district_weights = {}
    for d, p in DISTRICT_PROFILES.items():
        # 综合：tier 权重 + GDP 排名 + 1/距离
        tier_w = tier_weights[p['tier']]
        gdp_w = 1.0 / (p['gdp_rank'] + 1)  # 排名越前权重越大
        district_weights[d] = tier_w * (1 + gdp_w * 0.3)

    total_w = sum(district_weights.values())
    district_alloc = {d: int(need_to_generate * w / total_w) for d, w in district_weights.items()}

    # 调整总数
    diff = need_to_generate - sum(district_alloc.values())
    if diff > 0:
        # 加到 yuzhong（最贵最热门）
        district_alloc['yuzhong'] += diff
    elif diff < 0:
        # 从最少数据区减
        for d in sorted(district_alloc, key=lambda x: district_alloc[x])[:abs(diff)]:
            district_alloc[d] -= 1

    print('【3】每区分配数量（前 10）:')
    for d, n in sorted(district_alloc.items(), key=lambda x: -x[1])[:10]:
        p = DISTRICT_PROFILES[d]
        print(f'   {d:12s} ({p["name"]:6s}): {n:5d} 条, 价格 {p["unit_price_range"]}, 排名 {p["gdp_rank"]}')
    print(f'   ... (共 37 区县)')
    print(f'   总分配: {sum(district_alloc.values())} 条')
    print()

    # 开始生成
    print('【4】开始生成...')
    all_houses = []
    for district, count in district_alloc.items():
        profile = DISTRICT_PROFILES[district]
        for i in range(count):
            all_houses.append(gen_house(district, profile, i))
        if count > 0 and district in ['yuzhong', 'jiangbei', 'yubei']:
            print(f'   ✓ {district} ({profile["name"]}): {count} 条')

    print(f'   生成完毕: {len(all_houses)} 条')
    print()

    # 入库
    print('【5】写入数据库...')
    from db import batch_insert
    BATCH = 500
    inserted = 0
    t0 = time.time()
    for i in range(0, len(all_houses), BATCH):
        batch = all_houses[i:i+BATCH]
        n = batch_insert(batch)
        inserted += n
        if (i // BATCH) % 20 == 0:
            elapsed = time.time() - t0
            speed = (i + len(batch)) / max(elapsed, 0.1)
            print(f'   进度: {min(i+len(batch), len(all_houses))}/{len(all_houses)} 速度 {speed:.0f}条/秒')

    print()
    print('【6】统计最终结果...')
    cur.execute("SELECT COUNT(*) FROM houses")
    final = cur.fetchone()[0]
    print(f'   ✅ houses 总数: {final}')

    cur.execute("SELECT COUNT(*) FROM houses WHERE url LIKE '%lianjia%'")
    lj = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM houses WHERE url LIKE '%58%'")
    wu = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM houses WHERE url LIKE '%generated.local%'")
    gen = cur.fetchone()[0]
    print(f'   链家: {lj}, 58: {wu}, 生成: {gen}')

    conn.close()
    print()
    print('✅ 完成！')

    return {
        "inserted": inserted,
        "total": final,
        "message": f"生成完成：本次新增 {inserted} 条，总计 {final} 条"
    }


if __name__ == '__main__':
    main()
