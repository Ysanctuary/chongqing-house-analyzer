<div align="center">

# 🏠 重庆二手房数据分析系统

**爬虫 → 入库 → 机器学习 → 可视化（端到端 Demo）**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.13-blue.svg)
![MySQL](https://img.shields.io/badge/mysql-8.0-orange.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![Stars](https://img.shields.io/github/stars/Ysanctuary/chongqing-house-analyzer?style=social)

</div>

---

## 📖 项目简介

本项目是一个**端到端的重庆二手房数据分析系统**：从公开渠道（58 同城、链家 m 端）抓取二手房数据 → 入库到 MySQL → 使用 scikit-learn 做机器学习 → 通过 Flask + ECharts 提供可视化仪表盘。

- **区县覆盖**：重庆 37 个区县全覆盖
- **机器学习**：特征重要性 / KMeans 聚类 / 价格预测

## ✨ 核心特点

| 模块 | 能力 |
|---|---|
| 🕷️ **多源爬虫** | 58 同城 + 链家 m 端双源；普通模式 + 人机协作模式（Playwright 自动接管验证码）|
| 🤖 **机器学习** | RF 特征重要性 / KMeans 聚类 / RF 价格预测（±15% 区间）|
| 📊 **可视化仪表盘** | 6 个页面 / 19+ 张 ECharts 图 / 深空蓝 + 蓝紫渐变风格 |
| 🎛️ **总控面板** | Web 版管理后台，一键启停爬虫 / 训练模型 / 补足数据 / 导出 SQL |
| 🖥️ **GUI 启动壳** | tkinter 启动器 + 退出器，零命令行也能用 |
| 🧪 **高保真合成数据** | 37 区县全覆盖，按 GDP 分层 + beta 分布 + 真实楼盘名 |

## 🏗️ 系统架构

```
┌────────────┐     ┌──────────────┐     ┌─────────┐     ┌────────────┐
│ 58 / 链家  │ ──> │  spider/     │ ──> │  db.py  │ ──> │  MySQL     │
│ (HTML 页面)│     │ (curl_cffi)  │     │         │     │ chongqing_ │
└────────────┘     └──────────────┘     └─────────┘     │   house    │
       │                                       │        └─────┬──────┘
       ↓                                       ↓              │
┌────────────────┐                       ┌────────────┐     │
│ cleaner/       │                       │ analysis/  │ <───┘
│ (合成数据补足)  │                       │ (sklearn)  │
└────────────────┘                       └─────┬──────┘
                                               │ JSON
                                               ↓
                                       ┌────────────────┐
                                       │ web/app.py     │ <── 浏览器
                                       │ (Flask API)    │
                                       └───────┬────────┘
                                               ↓
                                       ┌────────────────┐
                                       │ templates/*.html│
                                       │ + control.html │
                                       └────────────────┘
```

## 📦 项目依赖

### 完整依赖清单

| 包 | 版本要求 | 作用 | 用在哪些文件 |
|---|---|---|---|
| **Flask** | >=3.1,<4.0 | Web 框架 | `web/app.py`（所有 33 个路由）|
| **flask-cors** | >=4.0 | 跨域支持 | `web/app.py`（前端跨域请求）|
| **PyMySQL** | >=1.1 | MySQL 驱动 | `db.py` / `cleaner/` / 所有 SQL 操作 |
| **pandas** | >=2.2 | DataFrame / 数据清洗 | `cleaner/` / `analysis/` |
| **numpy** | >=1.26 | 数值计算 | `analysis/`（ML 必备）|
| **scikit-learn** | >=1.4 | ML 算法库 | `analysis/feature_importance.py` (RF) / `analysis/cluster.py` (KMeans) / `analysis/price_predict.py` (RF) |
| **lxml** | >=5.0 | HTML/XML 解析器 | `spider/*.py` |
| **beautifulsoup4** | >=4.12 | HTML 解析库 | `spider/*.py` |
| **requests** | >=2.31 | HTTP 客户端 | `data_fetcher.py` / 备用爬虫 |
| **curl_cffi** ⭐ | >=0.7 | **TLS 指纹伪装**（反爬核心）| `spider/wuba_spider.py` 等 |
| **brotli** | >=1.1 | Brotli 解压 | `spider/*.py`（解压 58 返回内容）|
| **playwright** | >=1.40 | 浏览器自动化（**可选**）| `spider/*_pro.py`（人机协作爬虫）|

完整依赖清单见 [`requirements.txt`](./requirements.txt)。**一键安装**：

```bash
pip install -r requirements.txt
```

### 关键依赖说明

⭐ **`curl_cffi` 是核心反爬依赖**：普通 `requests` 会被 58/链家一秒识破（TLS 指纹不对），用 `curl_cffi` 伪装成 Chrome 120 才能正常抓取。

⭐ **`playwright` 是可选**：只在你想用「人机协作爬虫」（`*_pro.py`）时才需要。默认调用系统已装的 Chrome，**不用 `playwright install`**。

⭐ **`brotli` 不能省**：58 返回的内容是 brotli 压缩的，没装会报 `DecodeError`。

⭐ **`tkinter` 是 Python 自带**：launcher / exit 用到的 GUI 库，**不需要 pip install**。

## 🚀 快速开始（小白友好版）

### Step 1：装两个软件

| 软件 | 下载地址 | 验证装好了 |
|---|---|---|
| **Python 3.13+** | <https://www.python.org/downloads/> | 终端跑 `python --version`，应显示 `3.13.x` |
| **MySQL 8.0+** | <https://dev.mysql.com/downloads/mysql/> | 终端跑 `mysql --version`，应显示 `8.0.x` |

⚠️ **Windows 安装 Python 时务必勾选「Add Python to PATH」**

⚠️ **MySQL 安装时记住你设的 root 密码**，下面要用

### Step 2：把代码拿到手

```powershell
# 方式 A：用 git（推荐）
git clone https://github.com/Ysanctuary/chongqing-house-analyzer.git
cd chongqing-house-analyzer

# 方式 B：在 GitHub 网页点 "Code" → "Download ZIP"，解压后 cd 进去
```

### Step 3：装 Python 依赖包

```bash
pip install -r requirements.txt
```

**装完验证**（全部能 import 就 OK）：

```bash
python -c "import flask, pymysql, sklearn, curl_cffi, brotli; print('OK')"
```

应输出 `OK`。如果 `ModuleNotFoundError`，再跑一次 `pip install -r requirements.txt`。

### Step 4：启动 MySQL + 配置

> ⚠️ **clone 后项目里的状态**：
> 
> | 文件 | 在仓库里吗 | 是什么 |
> |---|---|---|
> | `config.example.py` | ✅ 是 | 配置模板（不含密码、可以公开）|
> | `config.py` | ❌ 否 | 你的本地配置（含密码，已加 `.gitignore`，**你必须自己创建**）|
> 
> 💡 **为什么需要两个文件？**
> 
> 配置文件里有两类东西：
> 
> | 类型 | 例子 | 能否公开 |
> |---|---|---|
> | **共用参数**（结构、默认值）| 数据库地址、端口、爬虫延迟 | ✅ 可以公开 |
> | **私有密钥**（每个人的不一样）| 你的 MySQL 密码、你的 cookie | ❌ 不能公开 |
> 
> **两个文件的模式** 就是为了解决这个矛盾：
> - `config.example.py` — 仓库里的**模板**，填共用参数 + 占位符（你的密码处填 `YOUR_M…WORD`）
> - `config.py` — 你本地**从模板复制**，把占位符换成你的真实密码
> 
> 这样仓库代码能被所有人共享，同时每个人的密码**永远不会上传到 GitHub**。
> 
> 这个模式在开源界很常见（Ruby on Rails 的 `database.yml.example`、12-Factor App 的 `.env.example` 都是同一思路）。
> 
> 所以你的第一件事是：**复制 `config.example.py` 为 `config.py`，然后填入密码**。

#### 4.1 启动 MySQL 服务

如果 MySQL 没自动启动，**用管理员身份**打开 PowerShell（右键开始菜单 → 终端（管理员）），跑：

```powershell
net start mysql
```

看到「MySQL 服务正在启动 ... 服务已启动」 = OK。

> 💡 如果提示「服务名无效」，说明 MySQL 服务没注册。重新打开 MySQL Installer → 选「Reconfigure」即可。

#### 4.2 测试 MySQL 连接（验证你的密码对不对）

在 PowerShell 跑：

```powershell
mysql -u root -p
```

**这一步会提示你输入密码**：

```
Enter password: ********
```

- `-p` 后**不要接密码**（这样密码不会显示在屏幕上，也不会被记到命令历史）
- 光标不移动是正常现象（密码输入默认隐藏）
- **输入你安装 MySQL 时设的 root 密码**，按回车

**进入成功的标志**：看到类似这样的提示符：

```
mysql>
```

**怎么退出 MySQL**：

```sql
exit;
```

看到「Bye」 = OK，回到 PowerShell。

> ❌ 如果提示 `Access denied for user 'root'@'localhost'` —— 密码错了。回去检查 MySQL 安装时设的密码。

#### 4.3 复制配置模板 → 创建你自己的 config.py

**你现在**只有 `config.example.py`，**没有** `config.py`。要跑项目，必须手动创建：

```powershell
# Windows（cmd 或 PowerShell）
copy config.example.py config.py

# macOS / Linux
cp config.example.py config.py
```

跑完后，项目根下会多出一个 `config.py` 文件。**这就是你要填密码的那个文件**。

> 💡 两个文件的区别：
> - `config.example.py` — 仓库里的模板，**不要改它**
> - `config.py` — 你的本地副本，**改这个**，密码填这里

#### 4.4 编辑 config.py（填入密码）

用记事本打开：

```powershell
notepad config.py
```

**找到第 24 行附近**的这段：

```python
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "YOUR_M…WORD",   # ← 改成你的 MySQL 密码
    "database": "chongqing_house",
    "charset": "utf8mb4",
    "autocommit": False,
}
```

**把 `"YOUR_M…WORD"` 替换成你 MySQL 的 root 密码**。

例如你的 MySQL 密码是 `abc123`：

```python
"password": "abc123",
```

**改完后**：
- 按 **Ctrl+S** 保存
- 关掉记事本

#### 4.5 验证改对了

```powershell
# 用 type 命令把文件内容打印出来
type config.py
```

应该能看到 `"password": "你的密码"` 这一行。

> ⚠️ **常见小白错误**：
> - 密码忘了引号 → `"password": abc123,` 报错
> - 多了空格 → `"password": " abc123 ",` 实际密码带空格
> - 漏了逗号 → 改了密码行忘记把前一行的逗号留着
> - 密码含特殊字符（如 `#`、`"`、`\`）→ 需要用反斜杠转义，最简单的办法是把密码改成不含特殊字符的

#### 4.6 一键验证（Python 直连 MySQL）

跑这条命令，能成功输出版本号就证明配置全对：

```powershell
python -c "import pymysql; c=pymysql.connect(host='127.0.0.1',port=3306,user='root',password=open('config.py').read().split('password')[1].split('\"')[1],database='chongqing_house'); print('MySQL版本:', c.get_server_info()); c.close()"
```

**看到这个就 OK**：

```
MySQL版本: 8.0.xx
```

如果报错 `Access denied` → 回去检查 4.4 步骤。

### Step 5：建库 + 造数据

**5.1 建表**：

```bash
python db.py
```

看到「数据库初始化完成」 = OK。

**5.2 生成 5 万条合成数据**：

```bash
python -c "from cleaner.realistic_generator import main; main()"
```

看到「已生成 X 条」 = OK。

### Step 6：启动 Web + 看效果

**6.1 启动服务**：

直接在项目文件夹双击launcher.py即可
退出直接在总控面板点击一键退出或双击exit.py

### 🆘 常见坑

| 报错 | 原因 | 解决 |
|---|---|---|
| `pymysql.err.OperationalError: (2003, ...)` | MySQL 没启动 | `net start mysql` |
| `Access denied for user 'root'` | 密码错 | 改 `config.py` 里的 password |
| `Address already in use` | 5000 端口被占 | 改 `config.py` 里 `FLASK_CONFIG["port"]` 为别的（如 5001）|
| `ModuleNotFoundError: No module named 'curl_cffi'` | 依赖没装全 | 再跑 `pip install -r requirements.txt` |
| `brotli` 解压报错 | 漏装 | `pip install brotli` |
| 启动后浏览器打不开 | 防火墙拦了 | 关防火墙再试 / 换端口 |
| 中文显示乱码 | 终端编码问题 | 用 PowerShell 而不是 cmd |

## 📂 项目结构

```
chongqing-house-analyzer/
├── config.py                  # ⚠️ 本地配置（**不在仓库**，用户需自行复制创建）
├── config.example.py          # 配置模板（在仓库里，随 clone 下来）
├── db.py                      # 数据库抽象层
├── data_fetcher.py            # API 数据获取器（可选数据源）
├── launcher.py / .pyw         # GUI 启动器
├── exit.py / .pyw             # GUI 退出器
├── 启动系统.bat               # Windows 一键启动（fallback）
├── spider/                    # 爬虫模块
│   ├── wuba_spider.py             # 58 同城
│   ├── lianjia_spider.py          # 链家
│   ├── wuba_spider_pro.py         # 58 + 验证码接管
│   └── lianjia_spider_pro.py      # 链家 + 验证码接管
├── cleaner/
│   └── realistic_generator.py     # 37 区县合成数据生成
├── analysis/                  # 机器学习
│   ├── feature_importance.py      # RF 特征重要性
│   ├── cluster.py                 # KMeans 聚类
│   └── price_predict.py           # RF 价格预测
├── web/                       # Web 层
│   ├── app.py                     # Flask 主程序（33 个路由）
│   ├── templates/                 # 5 个 Jinja2 页面
│   ├── static/css/style.css       # 全局样式
│   ├── static/js/main.js          # 粒子 / 光标 / 图表辅助
│   └── control.html               # 总控面板（独立页面）
├── docs/                      # 用户文档
└── requirements.txt
```

## 数据清洗问题
当前项目暂未制作数据清洗功能，仅对原始数据进行简单处理，数据清洗功能需用户自己编写。

## 🤖 机器学习模型

| 模块 | 算法 | 输入特征 | 用途 | 关键参数 |
|---|---|---|---|---|
| **特征重要性** | `RandomForestRegressor` | 面积 / 区县编码 / 装修 / 朝向 / 建成年 / 室 / 厅 | 哪个因素最影响房价 | n_estimators=100, max_depth=10 |
| **聚类分析** | `KMeans` | 单价 + 面积 + 年代（标准化后）| 自动划分 4 个价位段 | n_clusters=4 |
| **价格预测** | `RandomForestRegressor` | 同上 | 输入特征 → 输出预测单价 ±15% | n_estimators=200, max_depth=15 |

> 三个模块均固定 `random_state=42`，结果可复现。

## ⚙️ 配置说明

复制 `config.example.py` 为 `config.py` 后**必须**修改：

```python
MYSQL_CONFIG = {
    "password": "你的 MySQL 密码",   # ← 唯一必改项
    ...
}
```

**可选**修改：

- `FLASK_CONFIG["port"]` — 默认 5000
- `SPIDER_CONFIG["request_delay_*"]` — 反爬延迟（**不要低于 2 秒**）
- `CORE_DISTRICTS` — 重点爬取的 9 个主城区

## 🕷️ 关于爬虫的说明

爬虫模块使用 `curl_cffi` 模拟 Chrome 120 的 TLS 指纹，对**移动端** 58/链家进行抓取：

| 模式 | 文件 | 反爬策略 |
|---|---|---|
| 普通模式 | `wuba_spider.py` / `lianjia_spider.py` | TLS 指纹 + UA 轮换 + Cookie |
| 人机协作 | `*_pro.py` | 普通模式 + 检测到验证码时弹浏览器人工接管 |

> ⚠️ **重要**：本项目爬虫仅抓取**公开移动端页面**，不绕过登录、不存储个人信息。生产环境使用前请遵守目标网站的服务条款。

## ⚖️ 法律声明

本项目**仅供学习与技术研究**。爬虫仅抓取公开网页，不存储个人信息。**生产环境使用前请**：

- ✅ 遵守目标网站（58 同城 / 链家）的 robots.txt 和服务条款
- ✅ 控制请求频率（默认 ≥ 2 秒间隔）
- ✅ 不将爬取数据用于商业用途
- ❌ 不要对目标服务器造成负担

**作者不对任何滥用本项目代码造成的后果负责。**

---

## 🙏 致谢

- 数据来源：[58 同城](https://cq.58.com/ershoufang/) / [链家](https://cq.lianjia.com/ershoufang/)
- 图表库：[ECharts](https://echarts.apache.org/) (Apache-2.0)
- ML 框架：[scikit-learn](https://scikit-learn.org/) (BSD)
- TLS 模拟：[curl_cffi](https://github.com/yifeikong/curl_cffi) (MIT)

## 📮 反馈

- 🐛 提 Issue：<https://github.com/Ysanctuary/chongqing-house-analyzer/issues>
- 💬 讨论：<https://github.com/Ysanctuary/chongqing-house-analyzer/discussions>

如果觉得有帮助，欢迎 ⭐ Star！