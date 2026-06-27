"""
🛑 重庆二手房分析系统 - 完全退出工具

两种使用方式：
1. 双击运行：弹窗确认 → 杀进程 → 关窗
2. 命令行无 GUI：python exit.py --force
3. 被 import：from exit import full_shutdown  ← 供 web/app.py 调用

杀进程范围：
- Flask 后端（端口 5000）
- 爬虫子进程
- launcher.pyw（如果还在跑）
- 数据库连接（随 Flask 关闭自动断）

保留：
- 当前退出工具自身（自己杀自己前先关窗）
- 其他无关的 Python 进程（PyCharm、其他项目等）
"""
import subprocess
import re
import os
import sys
import tkinter as tk


# ==================== 进程操作 ====================

def run_cmd(cmd):
    """运行 shell 命令（静默）"""
    return subprocess.run(
        cmd, capture_output=True, text=True,
        shell=True, encoding='gbk', errors='ignore'
    )


def get_pid_by_port(port):
    """通过端口找进程 PID（Flask 后端 = 5000）"""
    result = run_cmd(f'netstat -ano | findstr :{port}')
    for line in result.stdout.split('\n'):
        if f':{port}' in line and 'LISTENING' in line:
            match = re.search(r'(\d+)\s*$', line.strip())
            if match:
                return int(match.group(1))
    return None


def get_child_pids(parent_pid):
    """递归找子进程（爬虫是 Flask 的子进程）"""
    result = run_cmd(f'wmic process where (ParentProcessId={parent_pid}) get ProcessId /format:list')
    pids = []
    for line in result.stdout.split('\n'):
        line = line.strip()
        if line.isdigit():
            child_pid = int(line)
            pids.append(child_pid)
            pids.extend(get_child_pids(child_pid))  # 递归找孙子进程
    return pids


def get_python_procs():
    """获取所有 python.exe 进程的 PID + 命令行"""
    result = run_cmd('wmic process where name="python.exe" get ProcessId,CommandLine /format:list')
    procs = []
    current_pid = None
    current_cmd = ''
    for line in result.stdout.split('\n'):
        if not line.strip():
            continue
        if line.startswith('CommandLine='):
            current_cmd = line[len('CommandLine='):]
        elif line.startswith('ProcessId='):
            pid_str = line[len('ProcessId='):].strip()
            if pid_str.isdigit():
                procs.append({'pid': int(pid_str), 'cmd': current_cmd})
            current_cmd = ''
    return procs


def is_target_process(cmd):
    """判断命令行是否属于本项目"""
    if not cmd:
        return False
    targets = [
        '学年设计2',
        'web\\app.py',
        'web/app.py',
        'launcher.pyw',
        'launcher.py',
        'spider\\',
        'spider/',
        'wuba_spider',
        'lianjia_spider',
    ]
    return any(t in cmd for t in targets)


def kill_pid(pid):
    """杀指定 PID"""
    run_cmd(f'taskkill /F /PID {pid} 2>nul')


# ==================== 主逻辑（可被 import）====================

def full_shutdown(skip_pids=None):
    """
    完全退出主逻辑（可被 web/app.py import 调用）。

    参数:
        skip_pids: 要跳过的 PID 列表（默认只跳过自己）
                   调用方如果是 Flask 主进程，需要传 [os.getpid()]
                   避免 Flask 试图自杀（自杀留给 _os._exit(0)）

    返回: 被杀的进程描述列表
    """
    skip_pids = skip_pids or [os.getpid()]
    killed = []

    # 1. 杀 Flask 后端（端口 5000） + 它的子进程（爬虫）
    flask_pid = get_pid_by_port(5000)
    if flask_pid and flask_pid not in skip_pids:
        # 先杀子进程
        for child_pid in get_child_pids(flask_pid):
            kill_pid(child_pid)
            killed.append(f'子进程 PID {child_pid}')
        # 再杀 Flask
        kill_pid(flask_pid)
        killed.append(f'Flask PID {flask_pid}')

    # 2. 扫所有 python.exe，杀匹配本项目的（跳过 skip_pids）
    for proc in get_python_procs():
        if proc['pid'] in skip_pids:
            continue
        if is_target_process(proc['cmd']):
            # 杀子进程
            for child_pid in get_child_pids(proc['pid']):
                kill_pid(child_pid)
            # 杀自己
            kill_pid(proc['pid'])
            # 简化描述
            if 'launcher' in proc['cmd']:
                killed.append(f'启动器 PID {proc["pid"]}')
            elif 'spider' in proc['cmd']:
                killed.append(f'爬虫 PID {proc["pid"]}')
            else:
                killed.append(f'项目进程 PID {proc["pid"]}')

    return killed


# ==================== GUI ====================

class ShutdownGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("完全退出")
        self.root.geometry("440x280")
        self.root.resizable(False, False)
        self.root.configure(bg='#0a0a0f')

        # 警告图标
        tk.Label(root, text="⚠️", font=("Microsoft YaHei", 40),
                 bg='#0a0a0f', fg='#ffd93d').pack(pady=(24, 4))

        # 标题
        tk.Label(root, text="完全退出 重庆二手房分析系统？",
                 font=("Microsoft YaHei", 12, "bold"),
                 bg='#0a0a0f', fg='#ffffff').pack(pady=(0, 6))

        # 说明
        tk.Label(root, text="将关闭后端、爬虫、启动器，释放所有内存",
                 font=("Microsoft YaHei", 9),
                 bg='#0a0a0f', fg='#a0aec0').pack()

        # 状态显示
        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(root, textvariable=self.status_var,
                                    font=("Microsoft YaHei", 9),
                                    bg='#0a0a0f', fg='#6ee7b7',
                                    wraplength=400, justify='center')
        self.status_lbl.pack(pady=12, padx=20)

        # 按钮
        btn_frame = tk.Frame(root, bg='#0a0a0f')
        btn_frame.pack(pady=8)

        self.confirm_btn = tk.Button(
            btn_frame, text="✅ 确认退出",
            font=("Microsoft YaHei", 10, "bold"),
            bg='#f5576c', fg='#ffffff', relief='flat',
            activebackground='#ff4757',
            padx=24, pady=8, cursor='hand2',
            command=self.on_confirm
        )
        self.confirm_btn.pack(side='left', padx=6)

        tk.Button(
            btn_frame, text="❌ 取消",
            font=("Microsoft YaHei", 10, "bold"),
            bg='#2a2a35', fg='#ffffff', relief='flat',
            activebackground='#3a3a45',
            padx=24, pady=8, cursor='hand2',
            command=root.destroy
        ).pack(side='left', padx=6)

        # 鼠标悬停效果
        self.confirm_btn.bind('<Enter>', lambda e: self.confirm_btn.config(bg='#ff4757'))
        self.confirm_btn.bind('<Leave>', lambda e: self.confirm_btn.config(bg='#f5576c'))

    def on_confirm(self):
        # 禁用按钮防止重复点
        self.confirm_btn.config(state='disabled', bg='#6c7293')
        self.status_var.set("🔄 正在停止所有进程...")
        self.root.update()

        try:
            killed = full_shutdown()
            if killed:
                msg = f"✅ 已停止: {', '.join(killed)}"
                self.status_var.set(msg)
            else:
                self.status_var.set("✅ 系统已空闲，没有运行中的进程")
        except Exception as e:
            self.status_var.set(f"❌ 出错: {e}")

        # 2 秒后关闭窗口
        self.root.after(2000, self.root.destroy)


# ==================== 入口 ====================

def main():
    # 方式 1：GUI 模式（双击 .pyw 或 .py）
    # 方式 2：命令行直接退出（python exit.py --force）
    if '--force' in sys.argv:
        killed = full_shutdown()
        if killed:
            print(f"✅ 已停止: {', '.join(killed)}")
        else:
            print("✅ 没有运行中的进程")
        sys.exit(0)
    else:
        root = tk.Tk()
        ShutdownGUI(root)
        root.mainloop()


if __name__ == "__main__":
    main()
