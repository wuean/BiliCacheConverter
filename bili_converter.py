#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站缓存转换工具
将 B 站客户端下载的 m4s 缓存合并为 mp4 文件
依赖: ffmpeg.exe(同目录或 PATH)
仅做本地转换,不联网,不调用 B 站 API
"""

import os
import re
import sys
import json
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime


class BiliConverter:
    # Windows 文件名非法字符(仅半角,全角符号均合法)
    ILLEGAL_CHARS = '<>:"/\\|?*'

    def __init__(self, root):
        self.root = root
        self.root.title("B站缓存转换工具 v1.2  ·  作者: 乐福学长  ·  https://lefuo.com")
        self.root.geometry("980x680")
        self.root.minsize(820, 520)

        self.cache_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.videos = []
        self.converting = False
        self.log_queue = queue.Queue()

        self.ffmpeg_path = self.find_ffmpeg()

        self.setup_style()
        self.build_ui()
        self.poll_log()

    # ---------- 样式 ----------
    def hex_to_rgb(self, h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def draw_gradient(self, canvas, color1, color2):
        """在 Canvas 上绘制垂直渐变背景"""
        canvas.update_idletasks()
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 2 or h < 2:
            return
        r1, g1, b1 = self.hex_to_rgb(color1)
        r2, g2, b2 = self.hex_to_rgb(color2)
        for i in range(h):
            ratio = i / h
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            canvas.create_line(0, i, w, i, fill=f'#{r:02x}{g:02x}{b:02x}')

    def make_card(self, parent, title=None, padding=14, header_right=None):
        """创建带阴影的卡片容器,返回 (外框, 内容Frame)

        header_right: 可选,传入一个函数 build(parent) -> widget,
                      该函数会在标题栏 Frame 内创建并返回右侧控件
        """
        # 阴影层(深灰)
        shadow = tk.Frame(parent, bg='#d4d4d8')
        # 卡片白底层
        card = tk.Frame(shadow, bg='#ffffff')
        card.pack(fill='both', expand=True, padx=(0, 1), pady=(0, 1))
        if title:
            header = tk.Frame(card, bg='#ffffff')
            header.pack(fill='x', padx=padding, pady=(padding, 6))
            tk.Label(header, text=title, bg='#ffffff', fg='#18181b',
                     font=('Microsoft YaHei UI', 10, 'bold')).pack(side='left')
            if header_right is not None:
                right_widget = header_right(header)
                if right_widget is not None:
                    right_widget.pack(side='right')
            # 标题下的装饰线
            line = tk.Frame(card, bg='#2563eb', height=2)
            line.pack(fill='x', padx=padding)
            inner = tk.Frame(card, bg='#ffffff')
            inner.pack(fill='both', expand=True, padx=padding, pady=(8, padding))
        else:
            inner = tk.Frame(card, bg='#ffffff')
            inner.pack(fill='both', expand=True, padx=padding, pady=padding)
        return shadow, inner

    def setup_style(self):
        """配置 ttk 主题与全局配色"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        # 配色方案 - 蓝色系主题
        BG = '#f4f4f5'            # 主背景(浅灰)
        FG = '#18181b'            # 主文字
        MUTED = '#a1a1aa'         # 次要文字
        ACCENT = '#2563eb'        # 主色(蓝)
        ACCENT_HOVER = '#3b82f6'
        ACCENT_PRESS = '#1d4ed8'
        ACCENT_SOFT = '#eff6ff'   # 蓝色浅底
        BORDER = '#e5e7eb'
        ENTRY_BG = '#ffffff'

        style.configure('.', background=BG, foreground=FG,
                        font=('Microsoft YaHei UI', 9))

        # Frame / Label
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=FG)
        style.configure('Muted.TLabel', background=BG, foreground=MUTED)
        style.configure('Card.TLabel', background='#ffffff', foreground=FG)
        style.configure('CardMuted.TLabel', background='#ffffff', foreground=MUTED)

        # Entry(细边框,1px)
        style.configure('TEntry', fieldbackground=ENTRY_BG, foreground=FG,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        borderwidth=1, padding=6)
        style.map('TEntry', bordercolor=[('focus', ACCENT)],
                  lightcolor=[('focus', ACCENT)], darkcolor=[('focus', ACCENT)])

        # 主按钮(蓝色实心)
        style.configure('Accent.TButton', background=ACCENT, foreground='#ffffff',
                        borderwidth=0, focusthickness=0, padding=(18, 8),
                        font=('Microsoft YaHei UI', 9, 'bold'))
        style.map('Accent.TButton',
                  background=[('active', ACCENT_HOVER), ('pressed', ACCENT_PRESS),
                              ('disabled', '#d4d4d8')],
                  foreground=[('disabled', '#ffffff')])

        # 次按钮(白底蓝边)
        style.configure('Secondary.TButton', background=ENTRY_BG, foreground=FG,
                        borderwidth=1, bordercolor=BORDER, focusthickness=0,
                        padding=(14, 7), font=('Microsoft YaHei UI', 9))
        style.map('Secondary.TButton',
                  background=[('active', ACCENT_SOFT)],
                  bordercolor=[('active', ACCENT)],
                  foreground=[('active', ACCENT_PRESS)])

        # Treeview
        style.configure('Treeview', background=ENTRY_BG, fieldbackground=ENTRY_BG,
                        foreground=FG, bordercolor=BORDER, rowheight=32,
                        font=('Microsoft YaHei UI', 9))
        style.configure('Treeview.Heading', background='#fafafa', foreground=FG,
                        bordercolor=BORDER, font=('Microsoft YaHei UI', 9, 'bold'),
                        padding=(8, 6))
        style.map('Treeview',
                  background=[('selected', ACCENT_SOFT)],
                  foreground=[('selected', ACCENT_PRESS)])
        style.map('Treeview.Heading',
                  background=[('active', '#f4f4f5')])

        # Progressbar
        style.configure('Horizontal.TProgressbar', background=ACCENT,
                        troughcolor='#f4f4f5', bordercolor=BORDER,
                        lightcolor=ACCENT, darkcolor=ACCENT, thickness=22)

        # Scrollbar
        style.configure('Vertical.TScrollbar', background='#d4d4d8',
                        troughcolor=BG, bordercolor=BG, arrowcolor=FG,
                        arrowsize=14)
        style.map('Vertical.TScrollbar',
                  background=[('active', '#a1a1aa')])
        style.configure('Horizontal.TScrollbar', background='#d4d4d8',
                        troughcolor=BG, bordercolor=BG, arrowcolor=FG,
                        arrowsize=14)
        style.map('Horizontal.TScrollbar',
                  background=[('active', '#a1a1aa')])

        # 根窗口背景
        self.root.configure(bg=BG)


    # ---------- 工具方法 ----------
    def find_ffmpeg(self):
        """查找 ffmpeg.exe: PyInstaller打包目录 -> 当前目录 -> 脚本目录 -> PATH"""
        candidates = []
        # PyInstaller 打包后,资源解压到 sys._MEIPASS
        if hasattr(sys, '_MEIPASS'):
            candidates.append(os.path.join(sys._MEIPASS, 'ffmpeg.exe'))
        candidates.append(os.path.join(os.getcwd(), 'ffmpeg.exe'))
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            candidates.append(os.path.join(script_dir, 'ffmpeg.exe'))
        except NameError:
            pass
        for p in candidates:
            if os.path.exists(p):
                return os.path.abspath(p)
        return 'ffmpeg'

    def sanitize_filename(self, name):
        if not name:
            return 'untitled'
        for c in self.ILLEGAL_CHARS:
            name = name.replace(c, '_')
        name = name.rstrip(' .')
        return name or 'untitled'

    def find_m4s(self, video_dir, cid):
        """在视频目录中识别音视频 m4s 文件"""
        video_dir = Path(video_dir)
        video_m4s = None
        audio_m4s = None

        # 优先用原工具留下的临时文件
        video_temp = video_dir / 'video.temp'
        audio_temp = video_dir / 'audio.temp'
        if video_temp.exists() and audio_temp.exists():
            return str(video_temp), str(audio_temp)

        # 遍历 m4s(递归搜索,适配手机APP的 <qn>/ 子目录结构)
        m4s_files = sorted(video_dir.rglob('*.m4s'), key=lambda f: -f.stat().st_size)
        for m4s in m4s_files:
            name = m4s.name
            name_lower = name.lower()

            # 模式1: 文件名含 video/audio 关键字
            if 'video' in name_lower:
                if not video_m4s:
                    video_m4s = str(m4s)
                continue
            if 'audio' in name_lower:
                if not audio_m4s:
                    audio_m4s = str(m4s)
                continue

            # 模式2: PC 客户端命名 cid-1-XXXXX.m4s
            #   视频: 30064, 30080, 30077, 30121, 30125 ... (>=30200 之外)
            #   音频: 30280, 30232, 30216 ... (>=30200)
            match = re.match(r'^(\d+)-1-(\d+)\.m4s$', name)
            if match:
                file_cid, code = match.group(1), int(match.group(2))
                if str(cid) and file_cid != str(cid):
                    continue
                if code >= 30200:
                    if not audio_m4s:
                        audio_m4s = str(m4s)
                else:
                    if not video_m4s:
                        video_m4s = str(m4s)

        return video_m4s, audio_m4s

    # ---------- 扫描 ----------
    def scan_cache(self):
        cache_dir = self.cache_dir.get().strip()
        if not cache_dir or not os.path.isdir(cache_dir):
            messagebox.showerror("错误", "请选择有效的缓存目录")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.videos = []
        self.progress_var.set(0)
        self.progress_label.config(text="0/0")
        self.header_stat.config(text="扫描中...")

        self.log(f"开始扫描: {cache_dir}")
        root = Path(cache_dir)
        found = 0
        seen_dirs = set()

        # 模式1: videoInfo.json (本工具/PC 客户端)
        for info_file in root.rglob('videoInfo.json'):
            try:
                with open(info_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                title = info.get('title') or info.get('tabName') or f"视频{info.get('cid','')}"
                cid = info.get('cid') or info.get('itemId') or ''
                uname = info.get('uname', '')
                video_dir = info_file.parent
                seen_dirs.add(video_dir.resolve())

                v, a = self.find_m4s(video_dir, cid)
                if v and a:
                    self.add_video({
                        'dir': video_dir, 'title': title, 'cid': cid,
                        'uname': uname, 'video': v, 'audio': a,
                        'size_mb': (Path(v).stat().st_size + Path(a).stat().st_size) / (1024*1024),
                    })
                    found += 1
                else:
                    self.log(f"  跳过(缺少 m4s): {video_dir}")
            except Exception as e:
                self.log(f"  解析失败 {info_file.name}: {e}")

        # 模式2: entry.json (手机 APP)
        for entry_file in root.rglob('entry.json'):
            try:
                if entry_file.parent.resolve() in seen_dirs:
                    continue
                with open(entry_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                page_data = data.get('page_data', {}) or {}
                title = (page_data.get('download_subtitle')
                         or page_data.get('part')
                         or data.get('title', ''))
                cid = page_data.get('cid', '')
                uname = data.get('owner_name') or data.get('up_name', '')
                video_dir = entry_file.parent
                seen_dirs.add(video_dir.resolve())

                v, a = self.find_m4s(video_dir, cid)
                if v and a:
                    self.add_video({
                        'dir': video_dir, 'title': title or f"视频{cid}",
                        'cid': cid, 'uname': uname, 'video': v, 'audio': a,
                        'size_mb': (Path(v).stat().st_size + Path(a).stat().st_size) / (1024*1024),
                    })
                    found += 1
            except Exception as e:
                self.log(f"  解析失败 {entry_file.name}: {e}")

        # 模式3: 裸 m4s(无元信息), 按 cid 分组
        if found == 0:
            self.log("未找到 videoInfo.json/entry.json, 尝试扫描裸 m4s...")
            groups = {}
            for m4s in root.rglob('*.m4s'):
                m = re.match(r'^(\d+)-1-\d+.*\.m4s$', m4s.name)
                if m:
                    groups.setdefault(m.group(1), []).append(m4s.parent)
            for cid, dirs in groups.items():
                video_dir = dirs[0]
                if video_dir.resolve() in seen_dirs:
                    continue
                v, a = self.find_m4s(video_dir, cid)
                if v and a:
                    self.add_video({
                        'dir': video_dir, 'title': f"视频_{cid}", 'cid': cid,
                        'uname': '', 'video': v, 'audio': a,
                        'size_mb': (Path(v).stat().st_size + Path(a).stat().st_size) / (1024*1024),
                    })
                    found += 1

        self.log(f"扫描完成,共找到 {found} 个视频")
        self.header_stat.config(text=f"共 {found} 个视频" if found else "未找到视频")

    def add_video(self, video):
        idx = len(self.videos)
        self.videos.append(video)
        self.tree.insert('', 'end', iid=str(idx), values=(
            video['title'], video['uname'],
            f"{video['size_mb']:.1f}", '待转换',
        ), tags=('pending',))

    # ---------- UI ----------
    def build_ui(self):
        main = tk.Frame(self.root, bg='#f4f4f5')
        main.pack(fill='both', expand=True)

        # ===== 渐变标题栏(蓝色) =====
        header_canvas = tk.Canvas(main, height=76, highlightthickness=0, bg='#2563eb')
        header_canvas.pack(fill='x')
        header_canvas.bind('<Configure>',
                           lambda e: self.draw_gradient(header_canvas, '#3b82f6', '#1d4ed8'))

        # 标题栏内容(叠加在 Canvas 上)
        header_inner = tk.Frame(header_canvas, bg='#2563eb')
        header_canvas.create_window(0, 0, anchor='nw', window=header_inner,
                                    tags='header_inner')
        header_canvas.bind('<Configure>',
                           lambda e: header_canvas.itemconfig('header_inner',
                                                              width=e.width, height=e.height))

        title_frame = tk.Frame(header_inner, bg='#2563eb')
        title_frame.pack(side='left', padx=20, pady=14)
        tk.Label(title_frame, text="🎬  B站缓存转换工具", bg='#2563eb', fg='#ffffff',
                 font=('Microsoft YaHei UI', 16, 'bold')).pack(anchor='w')
        tk.Label(title_frame, text="将 m4s 缓存合并为 mp4  ·  纯本地操作  ·  v1.2",
                 bg='#2563eb', fg='#dbeafe',
                 font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(2, 0))

        # 标题栏右侧状态
        right_frame = tk.Frame(header_inner, bg='#2563eb')
        right_frame.pack(side='right', padx=20, pady=14)
        self.header_stat = tk.Label(right_frame, text="就绪", bg='#2563eb', fg='#ffffff',
                                    font=('Microsoft YaHei UI', 10, 'bold'))
        self.header_stat.pack(anchor='e')

        # 主体内容区
        body = tk.Frame(main, bg='#f4f4f5', padx=12, pady=12)
        body.pack(fill='both', expand=True)

        # ===== 卡片1: 目录配置(grid 布局,确保两行对齐) =====
        dir_card, dir_inner = self.make_card(body, title="📁  目录配置")
        dir_card.pack(fill='x', pady=(0, 10))

        dir_inner.columnconfigure(1, weight=1)
        # 缓存目录行
        tk.Label(dir_inner, text="缓存目录", bg='#ffffff', fg='#52525b',
                 font=('Microsoft YaHei UI', 9)).grid(row=0, column=0, sticky='w', padx=(0, 8))
        ttk.Entry(dir_inner, textvariable=self.cache_dir).grid(row=0, column=1, sticky='we', padx=(0, 8))
        ttk.Button(dir_inner, text="浏览...", command=self.browse_cache,
                   style='Secondary.TButton').grid(row=0, column=2, padx=(0, 6))
        ttk.Button(dir_inner, text="🔍 扫描", command=self.scan_cache,
                   style='Accent.TButton').grid(row=0, column=3)
        # 输出目录行
        tk.Label(dir_inner, text="输出目录", bg='#ffffff', fg='#52525b',
                 font=('Microsoft YaHei UI', 9)).grid(row=1, column=0, sticky='w', padx=(0, 8), pady=(10, 0))
        ttk.Entry(dir_inner, textvariable=self.output_dir).grid(row=1, column=1, sticky='we', padx=(0, 8), pady=(10, 0))
        ttk.Button(dir_inner, text="浏览...", command=self.browse_output,
                   style='Secondary.TButton').grid(row=1, column=2, padx=(0, 6), pady=(10, 0))
        tk.Label(dir_inner, text="留空则输出到缓存目录", bg='#ffffff', fg='#a1a1aa',
                 font=('Microsoft YaHei UI', 8)).grid(row=1, column=3, sticky='w', pady=(10, 0))

        # ===== 卡片2: 视频列表(转换按钮放在标题栏右侧,确保始终可见) =====
        def build_list_buttons(header):
            """在标题栏右侧创建操作按钮组"""
            btns = tk.Frame(header, bg='#ffffff')
            ttk.Button(btns, text="☑ 全选", command=self.select_all,
                       style='Secondary.TButton').pack(side='left', padx=(0, 6))
            ttk.Button(btns, text="☐ 清空", command=self.clear_selection,
                       style='Secondary.TButton').pack(side='left', padx=(0, 12))
            ttk.Button(btns, text="⚡ 转换选中", command=self.convert_selected,
                       style='Accent.TButton').pack(side='left', padx=(0, 6))
            ttk.Button(btns, text="🚀 全部转换", command=self.convert_all,
                       style='Accent.TButton').pack(side='left')
            return btns

        list_card, list_inner = self.make_card(body, title="📋  视频列表  (双击行打开所在目录)",
                                               header_right=build_list_buttons)
        list_card.pack(fill='both', expand=True, pady=(0, 10))

        cols = ('title', 'uname', 'size', 'status')
        self.tree = ttk.Treeview(list_inner, columns=cols, show='headings',
                                 selectmode='extended')
        self.tree.heading('title', text='标题')
        self.tree.heading('uname', text='UP主')
        self.tree.heading('size', text='大小(MB)')
        self.tree.heading('status', text='状态')
        self.tree.column('title', width=520, anchor='w')
        self.tree.column('uname', width=180, anchor='w')
        self.tree.column('size', width=80, anchor='e')
        self.tree.column('status', width=100, anchor='center')

        self.tree.tag_configure('pending', foreground='#71717a', background='#ffffff')
        self.tree.tag_configure('converting', foreground='#1d4ed8', background='#eff6ff')
        self.tree.tag_configure('done', foreground='#16a34a', background='#f0fdf4')
        self.tree.tag_configure('error', foreground='#dc2626', background='#fef2f2')

        vsb = ttk.Scrollbar(list_inner, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        self.tree.bind('<Double-1>', lambda e: self.open_in_explorer())

        # ===== 进度条(单独一行,在日志上方) =====
        prog_bar = tk.Frame(body, bg='#f4f4f5')
        prog_bar.pack(fill='x', pady=(0, 10))
        tk.Label(prog_bar, text="进度", bg='#f4f4f5', fg='#52525b',
                 font=('Microsoft YaHei UI', 9)).pack(side='left', padx=(0, 8))
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(prog_bar, variable=self.progress_var, maximum=100)
        self.progress.pack(side='left', fill='x', expand=True)
        self.progress_label = tk.Label(prog_bar, text="0/0", bg='#f4f4f5', fg='#52525b',
                                       font=('Microsoft YaHei UI', 9, 'bold'), width=8)
        self.progress_label.pack(side='left', padx=(10, 0))

        # ===== 卡片3: 日志 =====
        log_card, log_inner = self.make_card(body, title="📟  运行日志")
        log_card.pack(fill='x')

        self.log_text = tk.Text(log_inner, height=7, wrap='word', state='disabled',
                                font=('Consolas', 9), bg='#1e1e2e', fg='#cdd6f4',
                                insertbackground='#cdd6f4', selectbackground='#45475a',
                                relief='flat', borderwidth=0, padx=8, pady=6)
        log_vsb = ttk.Scrollbar(log_inner, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        log_vsb.pack(side='right', fill='y')

        # ===== 底部状态栏 =====
        status_frame = tk.Frame(body, bg='#f4f4f5')
        status_frame.pack(fill='x', pady=(8, 0))
        self.status_var = tk.StringVar(value=f"ffmpeg: {self.ffmpeg_path}")
        tk.Label(status_frame, textvariable=self.status_var, bg='#f4f4f5', fg='#a1a1aa',
                 font=('Microsoft YaHei UI', 8)).pack(side='left')

        author_frame = tk.Frame(status_frame, bg='#f4f4f5')
        author_frame.pack(side='right')
        tk.Label(author_frame, text="作者: 乐福学长  |  ", bg='#f4f4f5', fg='#a1a1aa',
                 font=('Microsoft YaHei UI', 8)).pack(side='left')
        author_link = tk.Label(author_frame, text="https://lefuo.com",
                               foreground='#2563eb', cursor='hand2', bg='#f4f4f5',
                               font=('Microsoft YaHei UI', 8, 'underline'))
        author_link.pack(side='left')
        author_link.bind('<Button-1>', lambda e: self.open_url('https://lefuo.com'))
        author_link.bind('<Enter>', lambda e: author_link.config(foreground='#3b82f6'))
        author_link.bind('<Leave>', lambda e: author_link.config(foreground='#2563eb'))


    def log(self, msg):
        self.log_queue.put(msg)

    def poll_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                ts = datetime.now().strftime('%H:%M:%S')
                self.log_text.configure(state='normal')
                self.log_text.insert('end', f"[{ts}] {msg}\n")
                self.log_text.see('end')
                self.log_text.configure(state='disabled')
        except queue.Empty:
            pass
        self.root.after(100, self.poll_log)

    # ---------- 事件 ----------
    def open_url(self, url):
        """用默认浏览器打开 URL"""
        try:
            os.startfile(url)
        except Exception as e:
            self.log(f"打开链接失败: {e}")

    def make_input_uri(self, path):
        """根据 m4s 文件头部决定 ffmpeg 输入 URI。

        B 站新版客户端(2024+)在 m4s 开头加了 9 个 ASCII '0'(0x30)字节
        作为防直放标记,ffmpeg 无法直接识别(报 Invalid data)。
        用 ffmpeg 的 subfile 协议按字节偏移读取,无需复制大文件。

        若文件无该头部(老格式或其他来源),原样返回路径。
        """
        M4S_HEADER = b'\x30' * 9  # 9 个 ASCII '0'
        try:
            with open(path, 'rb') as f:
                if f.read(9) == M4S_HEADER:
                    # subfile 协议格式: subfile,,start,OFFSET,,:PATH
                    # Windows 路径用 / 替换 \ 避免转义问题
                    norm = path.replace('\\', '/')
                    return f"subfile,,start,9,,:{norm}"
        except Exception as e:
            self.log(f"检测 m4s 头部失败({path}): {e}")
        return path

    def browse_cache(self):
        d = filedialog.askdirectory(title="选择 B 站缓存目录")
        if d:
            self.cache_dir.set(d)

    def browse_output(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_dir.set(d)

    def select_all(self):
        for item in self.tree.get_children():
            self.tree.selection_add(item)

    def clear_selection(self):
        self.tree.selection_remove(self.tree.selection())

    def open_in_explorer(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        path = str(self.videos[idx]['dir'])
        try:
            os.startfile(path)
        except Exception as e:
            messagebox.showerror("错误", str(e))

    # ---------- 转换 ----------
    def convert_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要转换的视频")
            return
        self.start_conversion([int(s) for s in sel])

    def convert_all(self):
        if not self.videos:
            messagebox.showinfo("提示", "请先扫描视频")
            return
        self.start_conversion(list(range(len(self.videos))))

    def start_conversion(self, idxs):
        if self.converting:
            messagebox.showwarning("警告", "正在转换中,请等待完成")
            return

        # ffmpeg 可用性检查
        if not os.path.exists(self.ffmpeg_path):
            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            except Exception:
                messagebox.showerror("错误",
                    f"未找到 ffmpeg.exe\n请将 ffmpeg.exe 放到程序同目录或加入 PATH\n\n当前查找路径: {self.ffmpeg_path}")
                return

        self.converting = True
        self.progress_var.set(0)
        self.progress_label.config(text=f"0/{len(idxs)}")
        threading.Thread(target=self.convert_worker, args=(idxs,), daemon=True).start()

    def convert_worker(self, idxs):
        total = len(idxs)
        self.root.after(0, lambda: self.header_stat.config(text="转换中..."))
        for i, idx in enumerate(idxs):
            video = self.videos[idx]
            self.update_status(idx, 'converting')
            self.log(f"[{i+1}/{total}] 开始转换: {video['title']}")

            output_dir = self.output_dir.get().strip() or str(video['dir'])
            os.makedirs(output_dir, exist_ok=True)
            safe_title = self.sanitize_filename(video['title'])
            output_path = os.path.join(output_dir, f"{safe_title}.mp4")

            if os.path.exists(output_path):
                self.log(f"  已存在,跳过: {output_path}")
                self.update_status(idx, 'done')
                self.update_progress(i + 1, total)
                continue

            # 检测并构建 ffmpeg 输入 URI
            # B 站新版客户端在 m4s 开头加 9 个 '0' 字节作为防直放标记,
            # ffmpeg 无法直接识别,用 subfile 协议按字节偏移读取(无需复制文件)
            v_uri = self.make_input_uri(video['video'])
            a_uri = self.make_input_uri(video['audio'])

            cmd = [
                self.ffmpeg_path, '-y',
                '-i', v_uri,
                '-i', a_uri,
                '-c', 'copy',
                output_path,
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding='utf-8', errors='replace',
                )
                if result.returncode == 0:
                    size_mb = os.path.getsize(output_path) / (1024*1024)
                    self.log(f"  完成: {safe_title}.mp4 ({size_mb:.1f} MB)")
                    self.update_status(idx, 'done')
                else:
                    tail = (result.stderr or '')[-400:].strip().replace('\n', ' | ')
                    self.log(f"  失败: {video['title']}")
                    self.log(f"  原因: {tail}")
                    self.update_status(idx, 'error')
            except Exception as e:
                self.log(f"  异常: {video['title']} - {e}")
                self.update_status(idx, 'error')

            self.update_progress(i + 1, total)

        self.log(f"全部结束,共处理 {total} 个")
        self.root.after(0, lambda: self.header_stat.config(text="就绪"))
        self.converting = False

    def update_status(self, idx, status):
        status_map = {
            'pending': '待转换', 'converting': '转换中',
            'done': '已完成', 'error': '失败',
        }
        v = self.videos[idx]
        self.root.after(0, lambda: self.tree.item(str(idx), values=(
            v['title'], v['uname'], f"{v['size_mb']:.1f}",
            status_map.get(status, status),
        ), tags=(status,)))

    def update_progress(self, done, total):
        self.root.after(0, lambda: (
            self.progress_var.set(done / total * 100),
            self.progress_label.config(text=f"{done}/{total}")
        ))


def main():
    root = tk.Tk()
    BiliConverter(root)
    root.mainloop()


if __name__ == '__main__':
    main()
