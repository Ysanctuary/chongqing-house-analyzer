"""
🏙️ 重庆二手房分析系统 - 启动器 v1.0

双击运行：
  环境检测（Python 依赖 / MySQL / 端口）
  → 点 [🚀 启动系统] 按钮
  → 启 Flask 后端
  → 自动打开浏览器到 /control
  → 启动器窗口自动关闭

风格与 control.html v2 / exit.py 保持一致（深空蓝 + 蓝紫渐变）
"""
import subprocess
import threading
import time
import socket
import webbrowser
import tkinter as tk
import sys
import os
from pathlib import Path


# ==================== 路径处理（兼容开发/打包）====================
def get_project_dir():
    """兼容开发模式 + 未来 PyInstaller 打包模式"""
    if getattr(sys, 'frozen', False):
        # 打包后：exe 同级目录下的"项目文件"子目录
        return Path(sys.executable).parent / "项目文件"
    # 开发模式：launcher.py 所在目录
    return Path(__file__).resolve().parent

PROJECT_DIR = get_project_dir()
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)


# ==================== 工具函数 ====================
def is_port_in_use(port=5000):
    """检测端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def check_python():
    """检查 Python 和关键依赖"""
    missing = []
    for mod in ['flask', 'pymysql', 'pandas', 'sklearn']:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return False, f"缺: {', '.join(missing)}"
    return True, "正常"


def check_mysql():
    """检查 MySQL 连接（用项目的 config.py）"""
    try:
        import config
        import pymysql
        cfg = {k: v for k, v in config.MYSQL_CONFIG.items() if k != 'autocommit'}
        cfg['connect_timeout'] = 2
        conn = pymysql.connect(**cfg)
        conn.close()
        return True, "已连接"
    except Exception as e:
        msg = str(e)
        # 简化错误信息
        if 'Access denied' in msg:
            return False, "密码错误"
        elif 'Connection refused' in msg or 'connect' in msg.lower():
            return False, "MySQL 未启动"
        elif 'Unknown database' in msg:
            return False, "数据库不存在"
        return False, msg[:30]


def start_backend():
    """启动 Flask（后台，不弹黑窗）"""
    kwargs = {}
    if sys.platform == 'win32':
        # Windows：不弹黑色终端窗口
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        [sys.executable, 'web/app.py'],
        cwd=str(PROJECT_DIR),
        **kwargs
    )


# ==================== GUI ====================
class Launcher:
    def __init__(self, root):
        self.root = root
        self.root.title("重庆二手房分析系统 - 启动器")
        self.root.geometry("500x400")
        self.root.resizable(False, False)
        self.root.configure(bg='#0a0a0f')

        # 标题
        tk.Label(root, text="🏙️ 重庆二手房数据分析系统",
                 font=("Microsoft YaHei", 14, "bold"),
                 bg='#0a0a0f', fg='#b8c4e0').pack(pady=(24, 4))
        tk.Label(root, text=f"启动器 v1.0  |  项目: {PROJECT_DIR.name}",
                 font=("Microsoft YaHei", 9),
                 bg='#0a0a0f', fg='#6c7293').pack()

        # 环境检测区
        env_frame = tk.Frame(root, bg='#1a1a25')
        env_frame.pack(pady=16, padx=40, fill='x')

        self.env_python = self._add_env_row(env_frame, "🐍 Python + 依赖")
        self.env_mysql = self._add_env_row(env_frame, "🗄️ MySQL 数据库")
        self.env_port = self._add_env_row(env_frame, "🔌 端口 5000")

        # 状态
        self.status_var = tk.StringVar(value="⏸  待启动")
        self.status_lbl = tk.Label(root, textvariable=self.status_var,
                                    font=("Microsoft YaHei", 11),
                                    bg='#0a0a0f', fg='#ffffff')
        self.status_lbl.pack(pady=(12, 4))

        # 进度条（Canvas 渐变）
        self.progress = tk.Canvas(root, height=4, bg='#1a1a25',
                                   highlightthickness=0)
        self.progress.pack(fill='x', padx=60, pady=4)
        self.progress_running = False

        # 启动按钮
        self.btn = tk.Button(root, text="🚀 启 动 系 统",
                             font=("Microsoft YaHei", 13, "bold"),
                             bg='#667eea', fg='#ffffff',
                             activebackground='#f093fb',
                             activeforeground='#ffffff',
                             relief='flat', cursor='hand2',
                             padx=30, pady=8,
                             command=self.on_start)
        self.btn.pack(pady=14)

        tk.Label(root, text="点击后会自动启动后端 + 打开总控面板",
                 font=("Microsoft YaHei", 9),
                 bg='#0a0a0f', fg='#6c7293').pack(pady=(0, 12))

        # 鼠标悬停效果
        self.btn.bind('<Enter>', lambda e: self.btn.config(bg='#f093fb'))
        self.btn.bind('<Leave>', lambda e: self.btn.config(bg='#667eea'))

        # 启动时自动检测
        self.root.after(300, self.check_environment)

    def _add_env_row(self, parent, label):
        frame = tk.Frame(parent, bg='#1a1a25')
        frame.pack(fill='x', padx=12, pady=3)
        tk.Label(frame, text=label, font=("Microsoft YaHei", 10),
                 bg='#1a1a25', fg='#a0aec0', anchor='w').pack(side='left')
        var = tk.Label(frame, text="检测中...",
                       font=("Microsoft YaHei", 10),
                       bg='#1a1a25', fg='#ffd93d')
        var.pack(side='right')
        return var

    def set_env_status(self, widget, ok, text):
        widget.config(text=text,
                      fg='#6ee7b7' if ok else '#f5576c')

    def check_environment(self):
        """环境检测（启动时跑一次）"""
        # Python 依赖
        ok, msg = check_python()
        self.set_env_status(self.env_python, ok,
                            "✅ 正常" if ok else f"❌ {msg}")

        # MySQL
        ok, msg = check_mysql()
        self.set_env_status(self.env_mysql, ok,
                            "✅ 连接" if ok else f"❌ {msg}")

        # 端口
        in_use = is_port_in_use()
        self.set_env_status(self.env_port, not in_use,
                            "🟡 已被占用" if in_use else "✅ 空闲")

    def set_status(self, text, color='#ffffff'):
        self.status_var.set(text)
        self.status_lbl.config(fg=color)

    def start_progress(self):
        self.progress_running = True
        self._animate(0)

    def stop_progress(self):
        self.progress_running = False
        self.progress.delete('all')

    def _animate(self, x):
        """渐变进度条动画（蓝紫→粉）"""
        if not self.progress_running:
            return
        self.progress.delete('all')
        w = self.progress.winfo_width()
        bar_w = 80
        for i in range(bar_w):
            ratio = i / bar_w
            r = int(102 + (240 - 102) * ratio)   # 667eea → f093fb
            g = int(126 + (147 - 126) * ratio)
            b = int(234 + (251 - 234) * ratio)
            color = f'#{r:02x}{g:02x}{b:02x}'
            self.progress.create_line(x + i, 0, x + i, 4, fill=color)
        self.root.after(20, self._animate, (x + 5) % (w + bar_w))

    def on_start(self):
        """点击启动按钮"""
        # 禁用按钮
        self.btn.config(state='disabled', bg='#6c7293')
        self.btn.unbind('<Enter>')
        self.btn.unbind('<Leave>')

        # 异步启动
        def task():
            try:
                if is_port_in_use():
                    # 端口已被占用 → Flask 已在跑
                    self.set_status("✅ Flask 已在运行（端口 5000）", '#6ee7b7')
                else:
                    # 启动 Flask
                    self.set_status("🚀 正在启动后端服务...", '#667eea')
                    self.start_progress()
                    start_backend()
                    # 等待端口就绪
                    for _ in range(30):
                        if is_port_in_use():
                            break
                        time.sleep(0.5)
                    self.stop_progress()
                    self.set_status("✅ 后端启动成功", '#6ee7b7')

                # 打开浏览器
                time.sleep(0.5)
                self.set_status("🌐 正在打开总控面板...", '#ffd93d')
                webbrowser.open('http://localhost:5000/control')

                # 1.5 秒后关闭启动器
                time.sleep(1.5)
                self.root.destroy()

            except Exception as e:
                self.stop_progress()
                self.set_status(f"❌ 启动失败: {e}", '#f5576c')
                self.btn.config(state='normal', bg='#667eea')
                self.btn.bind('<Enter>', lambda e: self.btn.config(bg='#f093fb'))
                self.btn.bind('<Leave>', lambda e: self.btn.config(bg='#667eea'))

        threading.Thread(target=task, daemon=True).start()


def main():
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
