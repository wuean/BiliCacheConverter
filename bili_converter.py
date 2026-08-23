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
        self.root.title("B站缓存转换工具 v1.0  ·  作者: 乐福学长  ·  https://lefuo.com")
        self.root.geometry("980x680")
        self.root.minsize(820, 520)

        self.cache_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.videos = []
        self.converting = False
        self.log_queue = queue.Queue()

        self.ffmpeg_path = self.find_ffmpeg()

        self.build_ui()
        self.poll_log()

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

        # 遍历 m4s
        m4s_files = sorted(video_dir.glob('*.m4s'), key=lambda f: -f.stat().st_size)
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
                uname = data.get('up_name', '')
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

    def add_video(self, video):
        idx = len(self.videos)
        self.videos.append(video)
        self.tree.insert('', 'end', iid=str(idx), values=(
            video['title'], video['uname'],
            f"{video['size_mb']:.1f}", '待转换',
        ), tags=('pending',))

    # ---------- UI ----------
    def build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill='both', expand=True)

        # 顶部: 目录配置
        top = ttk.LabelFrame(main, text="目录配置", padding=8)
        top.pack(fill='x', pady=(0, 8))

        ttk.Label(top, text="缓存目录:").grid(row=0, column=0, sticky='w', padx=(0,4))
        ttk.Entry(top, textvariable=self.cache_dir, width=70).grid(row=0, column=1, sticky='we', padx=4)
        ttk.Button(top, text="浏览...", command=self.browse_cache).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="扫描", command=self.scan_cache).grid(row=0, column=3, padx=4)

        ttk.Label(top, text="输出目录:").grid(row=1, column=0, sticky='w', padx=(0,4), pady=(4,0))
        ttk.Entry(top, textvariable=self.output_dir, width=70).grid(row=1, column=1, sticky='we', padx=4, pady=(4,0))
        ttk.Button(top, text="浏览...", command=self.browse_output).grid(row=1, column=2, padx=4, pady=(4,0))
        ttk.Label(top, text="(留空输出到缓存目录)", foreground='gray').grid(row=1, column=3, padx=4, pady=(4,0), sticky='w')
        top.columnconfigure(1, weight=1)

        # 中间: 视频列表
        mid = ttk.LabelFrame(main, text="视频列表 (双击行打开所在目录)", padding=4)
        mid.pack(fill='both', expand=True, pady=(0, 8))

        cols = ('title', 'uname', 'size', 'status')
        self.tree = ttk.Treeview(mid, columns=cols, show='headings', selectmode='extended')
        self.tree.heading('title', text='标题')
        self.tree.heading('uname', text='UP主')
        self.tree.heading('size', text='大小(MB)')
        self.tree.heading('status', text='状态')
        self.tree.column('title', width=520, anchor='w')
        self.tree.column('uname', width=180, anchor='w')
        self.tree.column('size', width=80, anchor='e')
        self.tree.column('status', width=100, anchor='center')

        self.tree.tag_configure('pending', foreground='#666666')
        self.tree.tag_configure('converting', foreground='#0066cc')
        self.tree.tag_configure('done', foreground='#008800')
        self.tree.tag_configure('error', foreground='#cc0000')

        vsb = ttk.Scrollbar(mid, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        self.tree.bind('<Double-1>', lambda e: self.open_in_explorer())

        # 底部: 操作 + 进度
        bottom = ttk.Frame(main)
        bottom.pack(fill='x')

        btns = ttk.Frame(bottom)
        btns.pack(side='left')
        ttk.Button(btns, text="全选", command=self.select_all).pack(side='left', padx=2)
        ttk.Button(btns, text="清空选择", command=self.clear_selection).pack(side='left', padx=2)
        ttk.Button(btns, text="转换选中", command=self.convert_selected).pack(side='left', padx=8)
        ttk.Button(btns, text="全部转换", command=self.convert_all).pack(side='left', padx=2)

        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(bottom, variable=self.progress_var, maximum=100)
        self.progress.pack(side='left', fill='x', expand=True, padx=12)
        self.progress_label = ttk.Label(bottom, text="0/0", width=10)
        self.progress_label.pack(side='left')

        # 日志区
        log_frame = ttk.LabelFrame(main, text="日志", padding=4)
        log_frame.pack(fill='x', pady=(8, 0))
        self.log_text = tk.Text(log_frame, height=7, wrap='word', state='disabled',
                                font=('Consolas', 9))
        log_vsb = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        log_vsb.pack(side='right', fill='y')

        # 状态栏
        self.status_var = tk.StringVar(value=f"ffmpeg: {self.ffmpeg_path}")
        status_frame = ttk.Frame(main)
        status_frame.pack(fill='x', pady=(4, 0))
        ttk.Label(status_frame, textvariable=self.status_var, foreground='gray').pack(side='left')

        # 作者信息(可点击打开链接)
        author_frame = ttk.Frame(status_frame)
        author_frame.pack(side='right')
        ttk.Label(author_frame, text="作者: 乐福学长  |  ",
                  foreground='gray').pack(side='left')
        author_link = tk.Label(author_frame, text="https://lefuo.com",
                               foreground='#0066cc', cursor='hand2')
        author_link.pack(side='left')
        author_link.bind('<Button-1>', lambda e: self.open_url('https://lefuo.com'))
        author_link.bind('<Enter>', lambda e: author_link.config(foreground='#cc0000'))
        author_link.bind('<Leave>', lambda e: author_link.config(foreground='#0066cc'))

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

            cmd = [
                self.ffmpeg_path, '-y',
                '-i', video['video'],
                '-i', video['audio'],
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
