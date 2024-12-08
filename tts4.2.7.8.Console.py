import json
import qianfan
import os
import re
import sys
import shutil
import time
import glob
import threading
import pyperclip
# import base64
# import hashlib
# import hmac
# import ssl
# import websocket
import tkinter as tk
# import _thread as thread
from tkinter import filedialog, ttk, messagebox, scrolledtext
from tkinter.ttk import Progressbar, Notebook
from tkinter.scrolledtext import ScrolledText
from gradio_client import Client, handle_file
from datetime import datetime
from PIL import Image, ImageTk
from pydub import AudioSegment
from openai import OpenAI, RateLimitError
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QPushButton, QLabel, QListWidget, QComboBox, QDialog)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QEvent

# from sparkai.llm.llm import ChatSparkLLM, ChunkPrintHandler
# from sparkai.core.messages import ChatMessage
# from urllib.parse import urlparse, urlencode
# from wsgiref.handlers import format_date_time

client = None

# 创建全局锁
api_lock = threading.Lock()
api_lock_baidu = threading.Lock()
api_lock_kimi = threading.Lock()
api_lock_ali = threading.Lock()


def acquire_lock(lock):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not lock.acquire(blocking=False):  # 尝试非阻塞式获取锁
                raise Exception("当前API被占用")
            try:
                result = func(*args, **kwargs)  # 执行函数
            finally:
                lock.release()  # 确保在函数结束时释放锁
            return result

        return wrapper

    return decorator


def check_using_api(func):
    def wrapper(*args, **kwargs):
        # 尝试获取锁，非阻塞式获取
        if not api_lock.acquire(blocking=False):
            messagebox.showwarning("API被其他操作占用",
                                   "有其他操作占用API期间部分功能不可用")
            return
        try:
            result = func(*args, **kwargs)  # 执行函数
        finally:
            api_lock.release()  # 确保在函数结束时释放锁
        return result

    return wrapper


class StartMenu:
    def __init__(self, root, text_preprocessor):
        self.root = root

        # 初始化 API 密钥属性
        self.config = {}  # 用于存储所有配置项
        self.projects = {}  # 用于存储项目数据
        self.text_preprocessor = text_preprocessor
        self.chat_window = None  # 用来存储 ChatGUI 窗口实例

        # 创建 path_frame 容纳左、右两列
        path_frame = tk.Frame(self.root)
        path_frame.pack(fill=tk.X, padx=10, pady=10)

        # 左侧列
        left_frame = tk.Frame(path_frame)
        left_frame.grid(row=0, column=0, padx=(10, 5), sticky='nsw')

        tk.Label(left_frame, text="选择项目：").grid(row=0, column=0, sticky='w', pady=5)

        # 选择项目行
        self.select_project_frame = tk.Frame(left_frame)
        self.select_project_frame.grid(row=1, column=0, sticky='ew')

        # 使用 Combobox 替换项目名文本框
        self.project_name_combobox = ttk.Combobox(self.select_project_frame, width=28)
        self.project_name_combobox.grid(row=0, column=0, sticky='ew', pady=5)
        self.project_name_combobox.bind("<<ComboboxSelected>>", self.load_selected_project)  # 绑定选择事件

        # 删除项目按钮
        self.delete_project_button = tk.Button(self.select_project_frame, text="删除", command=self.delete_project)
        self.delete_project_button.grid(row=0, column=1, padx=(5, 0))

        # 设置按钮
        tk.Label(left_frame, text="配置AI：").grid(row=2, column=0, sticky='w', pady=(4, 5))
        self.settings_button = tk.Button(left_frame, text="设置", command=self.open_settings_window)
        self.settings_button.grid(row=3, column=0, sticky='we')

        # 右侧列
        right_frame = tk.Frame(path_frame)
        right_frame.grid(row=0, column=1, padx=(15, 5), sticky='nsew')

        # 确保右侧列的 Entry 随窗口变化
        path_frame.grid_columnconfigure(1, weight=1)

        tk.Label(right_frame, text="工作文件夹路径：").grid(row=0, column=0, sticky='w', pady=5)
        self.folder_path_var = tk.StringVar()
        self.folder_path_entry = tk.Entry(right_frame, textvariable=self.folder_path_var)
        self.folder_path_entry.grid(row=1, column=0, sticky='ew', pady=5)
        self.select_folder_button = tk.Button(right_frame, text="浏览...", command=self.select_folder)
        self.select_folder_button.grid(row=1, column=1, sticky='w', padx=5)

        tk.Label(right_frame, text="小说原文路径：").grid(row=2, column=0, sticky='w', pady=5)
        self.text_file_path_var = tk.StringVar()
        self.text_file_path_entry = tk.Entry(right_frame, textvariable=self.text_file_path_var)
        self.text_file_path_entry.grid(row=3, column=0, sticky='ew', pady=5)
        self.select_text_file_button = tk.Button(right_frame, text="浏览...", command=self.select_text_file)
        self.select_text_file_button.grid(row=3, column=1, sticky='w', padx=5)

        # 确保右侧列的按钮也随窗口变化
        right_frame.grid_columnconfigure(0, weight=1)

        # 测试按钮行
        self.test_button_frame = tk.Frame(path_frame)
        self.test_button_frame.grid(row=1, column=0, sticky='ew')

        # 新建 ChatGUI 按钮
        self.open_chat_button = tk.Button(self.test_button_frame, text="测试大模型", command=self.open_chat_window,
                                          width=16)
        self.open_chat_button.grid(row=0, column=0, padx=(10, 9), pady=(20, 5), sticky='we')

        # 占位
        self.blank_frame = tk.Frame(self.test_button_frame, width=6)
        self.blank_frame.grid(row=0, column=1)

        # 新建 GPT-SoVITS 按钮
        self.open_GPT_SoVITS_Button = tk.Button(self.test_button_frame, text="测试GPT-SoVITS",
                                                command=self.toggle_example_window, width=16)
        self.open_GPT_SoVITS_Button.grid(row=0, column=2, padx=5, pady=(20, 5), sticky='we')

        # 创建项目按钮
        self.create_project_button = tk.Button(path_frame, text="创建项目/进入项目", command=self.create_project)
        self.create_project_button.grid(row=1, column=1, padx=(15, 10), pady=(20, 5), sticky='ew')

        # 添加一个按钮来刷新选项卡2的内容
        # self.refresh_button = tk.Button(path_frame, text="刷新选项卡2内容", command=self.refresh_tab2)
        # self.refresh_button.grid(row=2, columnspan=2, padx=5, pady=10, sticky='ew')

        # 创建可滚动画布
        self.create_scrollable_canvas()

        # 初始化配置
        self.load_config()  # Load existing keys if available
        self.populate_project_names()  # Populate project names in Combobox

        # print(self.config)

        # 实例化 ExampleWindow 并保存其引用
        self.example_window = GPTSoVITSWindow(self.root)

        # self.run_connect_to_gradio_start()

    def save_config(self):
        """将配置保存回 config.json"""
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump({"config": self.config, "projects": self.projects}, f, ensure_ascii=False, indent=4)

    def delete_project(self):
        """删除选择的项目"""
        selected_project = self.project_name_combobox.get()  # 获取下拉框选择的项目名称

        if selected_project:
            # 检查项目是否存在于 projects 字典中
            if selected_project in self.projects:
                # 删除项目
                del self.projects[selected_project]
                # 保存更新后的配置
                self.save_config()
                # 更新下拉框中的项目列表
                self.populate_project_names()
                print(f"项目 '{selected_project}' 已删除.")
            else:
                print(f"未找到项目 '{selected_project}'.")

    def toggle_example_window(self):
        # 控制 ExampleWindow 窗口的显示与隐藏
        if self.example_window.window.winfo_ismapped():  # 如果窗口已显示，则隐藏
            self.example_window.hide_window()
        else:  # 如果窗口未显示，则显示
            self.example_window.show_window()

    def open_chat_window(self):
        """点击按钮时打开 ChatGUI 窗口"""
        if not self.chat_window:
            self.chat_window = ChatGUI()  # 如果窗口还没创建，创建一个新的实例
        self.chat_window.show()  # 显示窗口

    def load_config(self):
        """从 config.json 加载配置"""
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
                self.config = config_data.get("config", {})  # Load keys from config
                self.projects = config_data.get("projects", {})  # Load projects
        else:
            # 如果 config.json 不存在，则初始化配置
            self.config = {}
            self.projects = {}

    def populate_project_names(self):
        project_names = []

        # 检查 config.json 是否存在
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
                # 从 config_data 中提取项目名
                if "projects" in config_data:
                    project_names = list(config_data["projects"].keys())

        # 添加“新建项目”选项
        project_names.append("新建项目")

        # 更新 Combobox 的选项
        self.project_name_combobox['values'] = project_names

        # 检查 config.json 是否存在
        if not os.path.exists("config.json"):
            # 如果 config.json 不存在，默认选择“新建项目”
            self.project_name_combobox.current(project_names.index("新建项目"))
        else:
            # 只有在项目名称不为空时，选择最新创建的项目
            if project_names and len(project_names) > 1:  # 确保有项目可供选择
                # 筛选出有效项目（不包括“新建项目”）
                valid_projects = [name for name in project_names if name != "新建项目"]

                if valid_projects:  # 确保有效项目列表不为空
                    latest_project = max(valid_projects, key=lambda name: self.projects[name]['created_time'])
                    self.project_name_combobox.current(self.project_name_combobox['values'].index(latest_project))

                    # 填充最新项目的配置到控件
                    self.fill_project_config(latest_project)

                    project_name = self.project_name_combobox.get()
                    folder_path = self.folder_path_var.get()
                    text_file_path = self.text_file_path_var.get()
                    created_time = self.projects[latest_project]['created_time']

                    # 将项目数据保存到 projects 字典中
                    self.projects[project_name] = {
                        "folder_path": folder_path,
                        "text_file_path": text_file_path,
                        "created_time": created_time
                    }

                    # 更新画布中的项目详细信息
                    self.update_project_details_in_canvas(project_name)

    def get_text_file_stats(self, file_path):
        """获取文本文档的字符数和行数"""
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                char_count = len(content)
                line_count = content.count('\n') + 1  # 计算行数
            return char_count, line_count
        return 0, 0

    def fill_project_config(self, project_name):
        """填充选定项目的配置到控件"""
        if project_name in self.projects:
            project_data = self.projects[project_name]
            self.folder_path_var.set(project_data['folder_path'])
            self.text_file_path_var.set(project_data['text_file_path'])
        else:
            # 清空文件夹路径和文本文档路径
            self.folder_path_var.set("")
            self.text_file_path_var.set("")

    def load_selected_project(self, event):
        """加载选定的项目到输入框"""
        selected_project = self.project_name_combobox.get()
        if selected_project != "新建项目":
            project_data = self.projects[selected_project]
            self.folder_path_var.set(project_data['folder_path'])
            self.text_file_path_var.set(project_data['text_file_path'])

            # 显示项目的创建时间、字符数和行数
            created_time = project_data['created_time']
            char_count, line_count = self.get_text_file_stats(project_data['text_file_path'])

            details = (
                f"项目名: {selected_project}\n"
                f"创建时间/修改时间: {created_time}\n"
                f"字符数: {char_count}\n"
                f"行数: {line_count}"
            )
            self.project_details_label.config(text=details)
            self.update_project_details_in_canvas(selected_project)
            self.refresh_tab2()
        else:
            # 清空文件夹路径和文本文档路径
            self.folder_path_var.set("")
            self.text_file_path_var.set("")
            self.project_details_label.config(text="")

    def refresh_tab2_content(self):
        """刷新选项卡2的内容"""
        self.text_preprocessor.update_content()

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.folder_path_var.set(folder_path)

    def select_text_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file_path:
            self.text_file_path_var.set(file_path)

    def open_settings_window(self):
        # 创建设置窗口
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("设置")
        self.settings_window.geometry("820x480")  # 调整窗口大小，确保能容纳所有控件
        self.settings_window.minsize(820, 485)

        # 上方框架
        top_frame = tk.Frame(self.settings_window)
        top_frame.pack(side="top", fill=tk.BOTH, expand=True)

        # 左侧框架
        left_frame = tk.Frame(top_frame)
        left_frame.pack(side="left", fill="both", expand=True)

        # 右侧框架
        right_frame = tk.Frame(top_frame)
        right_frame.pack(side="right", fill="both", expand=True)

        # 右上方框架
        button_frame = tk.Frame(right_frame)
        button_frame.pack(side="top", fill="x")

        # 创建按钮来添加新的文本框
        self.canvas_frame = tk.Frame(right_frame)
        self.canvas_frame.pack(side="bottom", fill="both", expand=True)

        # 创建一个框架来放置URL输入框和连接按钮
        url_frame = tk.Frame(left_frame)
        url_frame.pack(side="top", fill="both")

        # 创建另一个框架放置服务的选项卡
        services_frame = tk.Frame(left_frame)
        services_frame.pack(side="bottom", fill="both", expand=True)

        # 在url_frame上方新建一个Notebook控件
        notebook_url = ttk.Notebook(url_frame)
        notebook_url.pack(padx=10, pady=10, fill="both")

        # 创建“GPT-SoVITS”标签页
        gpt_sovits_tab = tk.Frame(notebook_url)
        notebook_url.add(gpt_sovits_tab, text="GPT-SoVITS")

        # 在“GPT-SoVITS”标签页中放置现有的URL输入框和连接按钮
        tk.Label(gpt_sovits_tab, text="Gradio URL：").pack(anchor='w', padx=10, pady=5)
        self.gradio_url_var = tk.StringVar(value="http://localhost:9872/")
        self.gradio_url_entry = tk.Entry(gpt_sovits_tab, textvariable=self.gradio_url_var, width=30)
        self.gradio_url_entry.pack(side='left', padx=10, fill="x", expand=True)

        # 连接按钮
        connect_button = tk.Button(gpt_sovits_tab, text="连接", command=self.connect_gradio)
        connect_button.pack(side='left', padx=(0, 10), pady=(0, 5))

        # 创建“更多”标签页
        more_tab = tk.Frame(notebook_url)
        notebook_url.add(more_tab, text="更多")

        # 在“更多”标签页中显示“暂不支持”
        label_more = tk.Label(more_tab, text="暂不支持", font=("font", 16))
        label_more.pack(padx=10, pady=10)

        self.charactor_label = tk.Label(button_frame, text="角色管理器设置：")
        self.charactor_label.pack(side='left', padx=10)

        # 新建一个按钮来添加文本框
        self.add_textbox_button = tk.Button(button_frame, text="添加预设路径", command=self.add_textbox)
        self.add_textbox_button.pack(side='left', padx=(5, 0))

        # 创建Canvas和滚动条
        self.canvas_window = tk.Canvas(self.canvas_frame, height=100, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas_window.yview)
        self.canvas_window.config(yscrollcommand=self.scrollbar.set)

        # 将Canvas放入滚动窗口
        self.scrollable_frame_window = tk.Frame(self.canvas_window)
        self.canvas_window.create_window((0, 0), window=self.scrollable_frame_window, anchor="nw")
        self.scrollable_frame_window.columnconfigure(0, weight=1)  # 使第0列可扩展

        self.scrollable_frame_window.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
        self.scrollable_frame_window.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
        self.scrollable_frame_window.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

        self.scrollbar.pack(side="right", fill="y")
        self.canvas_window.pack(side="left", fill="both", expand=True)

        # 让Canvas能够自动调整大小
        self.scrollable_frame_window.bind(
            "<Configure>",
            lambda e: self.canvas_window.config(scrollregion=self.canvas_window.bbox("all"))
        )

        self.textbox_counter = 0  # 用于计数创建的文本框数量

        # 创建服务的选项卡
        services = ["百度", "KIMI", "阿里", "讯飞", "腾讯", "自定义", "更多"]
        self.tab_frames = {}
        self.entries = {}  # 存储每个选项卡的entry，以便保存时读取
        self.model_vars = {}  # 存储每个服务的模型选择

        # 新建一个Notebook控件来放置服务选项卡
        notebook_services = ttk.Notebook(services_frame)
        notebook_services.pack(padx=10, pady=10, expand=True, fill="both")

        for service in services:
            tab_frame = tk.Frame(notebook_services)
            notebook_services.add(tab_frame, text=service)
            self.tab_frames[service] = tab_frame

            if service == "KIMI":
                tk.Label(tab_frame, text=f"{service} API_KEY：").pack(anchor='w', padx=10, pady=5)
                secret_key_entry = tk.Entry(tab_frame, width=30)
                secret_key_entry.pack(anchor='w', padx=10, fill="both")

            elif service == "阿里":
                tk.Label(tab_frame, text=f"{service} API_KEY：").pack(anchor='w', padx=10, pady=5)
                secret_key_entry = tk.Entry(tab_frame, width=30)
                secret_key_entry.pack(anchor='w', padx=10, fill="both")

            elif service == "讯飞":
                tk.Label(tab_frame, text=f"{service} APPID：").pack(anchor='w', padx=10, pady=5)
                access_key_entry = tk.Entry(tab_frame, width=30)
                access_key_entry.pack(anchor='w', padx=10, fill="both")

                tk.Label(tab_frame, text=f"{service} APISecret：").pack(anchor='w', padx=10, pady=5)
                secret_key_entry = tk.Entry(tab_frame, width=30)
                secret_key_entry.pack(anchor='w', padx=10, fill="both")

                tk.Label(tab_frame, text=f"{service} APIKey：").pack(anchor='w', padx=10, pady=5)
                api_key_entry = tk.Entry(tab_frame, width=30)
                api_key_entry.pack(anchor='w', padx=10, fill="both")

                # 特别处理：将 api_key_entry 也加入到 self.entries[service] 中
                self.entries[service] = {
                    "access_key": access_key_entry,
                    "secret_key": secret_key_entry,
                    "api_key": api_key_entry,  # 存储 API_KEY
                }

                # 清空 tab_frame 中已有的控件
                for widget in tab_frame.winfo_children():
                    widget.pack_forget()  # 或者 widget.destroy()

                tk.Label(tab_frame, text="暂不支持", font=("font", 16)).pack(padx=10, pady=10)

            elif service == "腾讯":
                # 清空 tab_frame 中已有的控件
                for widget in tab_frame.winfo_children():
                    widget.pack_forget()  # 或者 widget.destroy()

                tk.Label(tab_frame, text="暂不支持", font=("font", 16)).pack(padx=10, pady=10)

            elif service == "自定义":
                choose_custom_config_frame = tk.Frame(tab_frame)
                choose_custom_config_frame.pack(anchor='w', fill="x")
                tk.Label(choose_custom_config_frame, text="自定义预设").pack(anchor='w', padx=10, pady=5)
                self.custom_config_var = tk.StringVar()
                custom_config = ttk.Combobox(choose_custom_config_frame, textvariable=self.custom_config_var)
                custom_config.pack(side='left', padx=10, fill="x", expand=True)
                custom_config.bind("<<ComboboxSelected>>", lambda event: self.load_selected_preset(custom_config))

                create_custom_config = tk.Button(choose_custom_config_frame, text="创建",
                                                 command=self.create_custom_preset)
                create_custom_config.pack(side='left', padx=(0, 5))
                self.custom_config_combobox = custom_config

                delete_custom_config = tk.Button(choose_custom_config_frame, text="删除",
                                                 command=lambda: self.delete_custom_preset(custom_config))
                delete_custom_config.pack(side='left', padx=(5, 10))

                tk.Label(tab_frame, text=f"{service} base_url：").pack(anchor='w', padx=10, pady=(0, 5))
                access_key_entry = tk.Entry(tab_frame, width=30)
                access_key_entry.pack(anchor='w', padx=10, fill="both")

                tk.Label(tab_frame, text=f"{service} API_KEY：").pack(anchor='w', padx=10, pady=5)
                secret_key_entry = tk.Entry(tab_frame, width=30)
                secret_key_entry.pack(anchor='w', padx=10, fill="both")

                # 导入配置时，填充“自定义”选项卡的下拉栏
                self.load_custom_presets(custom_config)

            elif service == "更多":
                label_more2 = tk.Label(tab_frame, text="请按“文本预处理”\n选项卡内具体要求使用", font=("font", 16))
                label_more2.pack(padx=10, pady=10)

            else:
                tk.Label(tab_frame, text=f"{service} ACCESS_KEY：").pack(anchor='w', padx=10, pady=5)
                access_key_entry = tk.Entry(tab_frame, width=30)
                access_key_entry.pack(anchor='w', padx=10, fill="both")

                tk.Label(tab_frame, text=f"{service} SECRET_KEY：").pack(anchor='w', padx=10, pady=5)
                secret_key_entry = tk.Entry(tab_frame, width=30)
                secret_key_entry.pack(anchor='w', padx=10, fill="both")

            if service != "讯飞":
                self.entries[service] = {"access_key": access_key_entry, "secret_key": secret_key_entry}

            if service != "更多":
                # 添加模型选择下拉框
                model_var = tk.StringVar(value="待定")
                self.model_vars[service] = model_var

            model_options = ["待定"]
            if service == "百度":
                model_options = [
                    "ERNIE-4.0-Turbo-128K",
                    "ERNIE-4.0-Turbo-8K-Latest",
                    "ERNIE-4.0-Turbo-8K-Preview",
                    "ERNIE-4.0-Turbo-8K",
                    "ERNIE-4.0-8K-Latest",
                    "ERNIE-4.0-8K-Preview",
                    "ERNIE-4.0-8K",
                    "ERNIE-3.5-128K",
                    "ERNIE-3.5-8K-Preview",
                    "ERNIE-3.5-8K",
                    "ERNIE-Speed-Pro-128K",
                    "ERNIE-Speed-128K",
                    "ERNIE-Speed-8K",
                    "ERNIE-Lite-Pro-128K",
                    "ERNIE-Lite-8K-0308",
                    "ERNIE-Tiny-8K",
                    "ERNIE-Character-8K",
                    "ERNIE-Character-Fiction-8K",
                    "ERNIE-Novel-8K",
                    "Qianfan-Chinese-Llama-2-70B",
                    "Llama-2-70b-chat"
                ]
                model_var.set("ERNIE-4.0-Turbo-128K")  # 默认选中百度的第一个模型选项

            if service == "KIMI":
                model_options = [
                    "moonshot-v1-8k",
                    "moonshot-v1-32k",
                    "moonshot-v1-128k",
                    "moonshot-v1-auto"
                ]
                model_var.set("moonshot-v1-128k")

            if service == "阿里":
                model_options = [
                    "qwen-long",
                    "qwen-turbo",
                    "qwen-plus",
                    "qwen-max"
                ]
                model_var.set("qwen-long")

            if service == "讯飞":
                model_options = [
                    "lite",
                    "generalv3",
                    "generalv3.5",
                    "pro-128k",
                    "max-32k",
                    "4.0Ultra",
                ]
                model_var.set("pro-128k")

            choose_model_label = tk.Label(tab_frame, text="选择模型")
            choose_model_label.pack(anchor='w', padx=10, pady=5)
            model_combobox = ttk.Combobox(tab_frame, textvariable=model_var, values=model_options, width=27)
            model_combobox.pack(anchor='w', padx=10, fill="both")

            # 在“更多”选项卡中，隐藏模型选择下拉框
            if service == "更多":
                model_combobox.pack_forget()  # 隐藏模型选择下拉框
                choose_model_label.pack_forget()

        # 从 config.json 读取配置并填充控件
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)

            # 设置每个服务的 ACCESS_KEY、SECRET_KEY 和模型选择
            for service in services:
                if service != "更多":
                    try:
                        access_key = config_data.get("config", {}).get(service, {}).get("ACCESS_KEY", "")
                        secret_key = config_data.get("config", {}).get(service, {}).get("SECRET_KEY", "")
                        model_choice = config_data.get("config", {}).get(service, {}).get("MODEL", "待定")

                        # 特别处理“讯飞”选项卡，获取 API_KEY
                        if service == "讯飞":
                            api_key = config_data.get("config", {}).get(service, {}).get("API_KEY", "")
                            # 填充讯飞的 API_KEY
                            self.entries[service]["api_key"].delete(0, tk.END)
                            self.entries[service]["api_key"].insert(0, api_key)

                        # 填充每个服务的控件
                        self.entries[service]["access_key"].delete(0, tk.END)
                        self.entries[service]["access_key"].insert(0, access_key)
                        self.entries[service]["secret_key"].delete(0, tk.END)
                        self.entries[service]["secret_key"].insert(0, secret_key)

                        self.model_vars[service].set(model_choice)

                    except Exception as e:
                        continue

            # 读取 character_folder 并在滚动画布中创建文本框
            character_folder_content = config_data.get("config", {}).get("character_folder", [])
            for content in character_folder_content:
                # 增加文本框计数器
                self.textbox_counter += 1

                # 创建一个 Frame 用于容纳该行的控件
                row_frame = tk.Frame(self.scrollable_frame_window)
                row_frame.grid_columnconfigure(1, weight=1)
                row_frame.grid_columnconfigure(2, weight=0)  # 使第1列不扩展
                row_frame.grid_columnconfigure(3, weight=0)  # 使第2列不扩展

                row_frame.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
                row_frame.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
                row_frame.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

                # 创建文本框并填充初始内容
                new_textbox = tk.Entry(row_frame, width=30)
                new_textbox.insert(0, content)
                new_textbox.grid(row=0, column=0, pady=5, padx=10, sticky="ew")

                # 为该文本框创建“浏览...”按钮
                def browse_folder(textbox=new_textbox):  # 使用默认参数来绑定当前文本框
                    folder_path = filedialog.askdirectory()  # 打开选择文件夹对话框
                    if folder_path:  # 如果选择了路径，则填充到文本框
                        textbox.delete(0, tk.END)
                        textbox.insert(0, folder_path)

                # 创建“浏览...”按钮并放置在文本框的右侧
                browse_button = tk.Button(row_frame, text="浏览...", command=browse_folder)
                browse_button.grid(row=0, column=1, pady=5, padx=(0, 10), sticky="w")

                # 为每个文本框和浏览按钮创建删除按钮
                def delete_row(frame=row_frame):
                    # 删除当前行的所有控件
                    frame.destroy()

                # 创建“删除”按钮并放置在浏览按钮的右侧
                delete_button = tk.Button(row_frame, text="删除", command=delete_row)
                delete_button.grid(row=0, column=2, pady=5, padx=(0, 10), sticky="w")

                # 将这一行的所有控件（文本框、浏览按钮、删除按钮）添加到框架中
                row_frame.grid(row=self.textbox_counter, column=0, pady=5, padx=10, sticky="ew")

                for widget in row_frame.winfo_children():
                    widget.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
                    widget.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
                    widget.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动
        else:
            print("配置文件 config.json 不存在，使用默认配置")

        # 保存按钮
        save_button = tk.Button(self.settings_window, text="保存", command=self.save_keys_and_close_window)
        save_button.pack(anchor='w', padx=10, pady=10, fill="both")

        self.canvas_window.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
        self.canvas_window.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
        self.canvas_window.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

        self.load_selected_preset(custom_config)

    def delete_custom_preset(self, custom_config):
        """删除自定义预设"""
        selected_preset = self.custom_config_var.get()

        # 确保选中一个预设
        if selected_preset:
            # 读取现有的 config.json 文件
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    existing_data = json.load(f)

                # 检查是否存在自定义预设配置
                if "自定义" in existing_data["config"]:
                    custom_presets = existing_data["config"]["自定义"]

                    # 如果选中的预设存在于自定义预设中，则删除
                    if selected_preset in custom_presets:
                        del custom_presets[selected_preset]

                        # 更新自定义预设
                        existing_data["config"]["自定义"] = custom_presets

                        # 如果删除的是当前选中的预设，清空选择
                        if self.custom_config_var.get() == selected_preset:
                            self.custom_config_var.set("")  # 清空选择

                        # 写入更新后的配置文件
                        with open("config.json", "w", encoding="utf-8") as f:
                            json.dump(existing_data, f, ensure_ascii=False, indent=4)

                        # 从下拉栏中移除已删除的预设
                        self.load_custom_presets(custom_config)

                        print(f"预设 '{selected_preset}' 已被删除")
                    else:
                        print(f"未找到预设 '{selected_preset}'")
                else:
                    print("没有自定义预设可删除")
            else:
                print("配置文件不存在")
        else:
            print("没有选中任何预设")

    def load_custom_presets(self, custom_config):
        """读取并填充所有自定义预设名称到下拉栏"""
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if "自定义" in data["config"]:
                    custom_presets = data["config"]["自定义"]

                    # 排除“已选择”项并获取所有预设名称
                    preset_names = [name for name in custom_presets.keys()]

                    # 将自定义预设的名称填充到下拉栏
                    custom_config['values'] = preset_names + ["新建配置"]

                    # 默认选中“自定义已选择”项对应的预设
                    selected_preset = data["config"].get("自定义已选择")  # 获取“自定义已选择”项
                    if selected_preset and selected_preset in preset_names:
                        # 如果“自定义已选择”项存在且在预设名称中，设置为默认选中项
                        self.custom_config_var.set(selected_preset)
                    elif preset_names:
                        # 如果没有“自定义已选择”项，默认选中第一个预设
                        self.custom_config_var.set(preset_names[0])

    def load_selected_preset(self, custom_config):
        """根据选择的自定义预设填充相关配置"""
        selected_preset = custom_config.get()  # 获取选中的自定义预设名称

        if not selected_preset:
            return  # 如果没有选择预设，则不进行填充

        # 如果选中了“新建配置”，直接清空控件内容
        if selected_preset == "新建配置":
            # 假设控件的名称是 "access_key", "secret_key", "model" 等
            self.entries["自定义"]["access_key"].delete(0, tk.END)
            self.entries["自定义"]["secret_key"].delete(0, tk.END)
            self.model_vars["自定义"].set("")  # 清空模型选择
            return

        # 获取配置文件中的自定义预设项
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if "自定义" in data["config"]:
                    custom_presets = data["config"]["自定义"]
                    if selected_preset in custom_presets:
                        preset_config = custom_presets[selected_preset]

                        # 填充到相应的控件
                        if "ACCESS_KEY" in preset_config:
                            self.entries["自定义"]["access_key"].delete(0, tk.END)
                            self.entries["自定义"]["access_key"].insert(0, preset_config["ACCESS_KEY"])

                        if "SECRET_KEY" in preset_config:
                            self.entries["自定义"]["secret_key"].delete(0, tk.END)
                            self.entries["自定义"]["secret_key"].insert(0, preset_config["SECRET_KEY"])

                        if "MODEL" in preset_config:
                            self.model_vars["自定义"].set(preset_config["MODEL"])  # 选择模型

                        # 如果有其他控件需要填充，可以继续添加

    def create_custom_preset(self):
        # 获取“自定义预设”下拉框的内容（即用户输入的名称）
        custom_preset_name = self.tab_frames["自定义"].winfo_children()[0].winfo_children()[1].get()
        custom_config_combobox = self.custom_config_combobox

        # 如果名称为空，则不执行操作
        if not custom_preset_name:
            messagebox.showwarning("警告","请输入预设名称!")
            return

        if custom_preset_name == "新建配置":
            messagebox.showwarning("警告","请修改预设名称！")
            return

        # 获取用户填写的其他信息
        # 获取"base_url"、"API_KEY"和"MODEL"输入框的内容
        base_url = self.entries["自定义"]["access_key"].get()  # 假设 "access_key" 对应的是 base_url
        api_key = self.entries["自定义"]["secret_key"].get()  # 假设 "secret_key" 对应的是 API_KEY
        model = self.model_vars["自定义"].get()  # 获取模型的选择项

        # 打印获取到的值（可选，调试用）
        print(f"正在保存自定义预设：{custom_preset_name}")
        print(f"Base URL: {base_url}")
        print(f"API_KEY: {api_key}")
        print(f"MODEL: {model}")

        # 读取 config.json 文件并更新配置
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
        else:
            print("配置文件 config.json 不存在，创建配置文件")
            self.save_keys()  # 调用 self.save_keys 函数创建配置文件
            # 重新加载配置文件
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)

        # 获取或初始化 "自定义" 配置项
        custom_config = config_data.get("config", {}).get("自定义", {})

        # 将用户填写的内容保存到配置中，覆盖已存在的内容
        custom_config[custom_preset_name] = {
            "ACCESS_KEY": base_url,  # 用 base_url 填充 ACCESS_KEY
            "SECRET_KEY": api_key,  # 用 api_key 填充 SECRET_KEY
            "MODEL": model  # 用 model 填充 MODEL
        }

        # 将更新后的配置写回 config.json 文件
        config_data["config"]["自定义"] = custom_config
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)

        print(f"自定义预设 {custom_preset_name} 已保存!")

        self.load_custom_presets(custom_config_combobox)

    def add_textbox(self):
        # 创建一个新的文本框计数器
        self.textbox_counter += 1

        # 创建一个 Frame 用于容纳该行的控件
        row_frame = tk.Frame(self.scrollable_frame_window)
        row_frame.grid_columnconfigure(0, weight=1)
        row_frame.grid_columnconfigure(1, weight=0)  # 使第1列不扩展
        row_frame.grid_columnconfigure(2, weight=0)  # 使第2列不扩展

        row_frame.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
        row_frame.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
        row_frame.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

        # 创建新的文本框
        new_textbox = tk.Entry(row_frame, width=30)
        new_textbox.grid(row=0, column=0, pady=5, padx=10, sticky="ew")

        # 为每个新文本框创建一个“浏览...”按钮
        def browse_folder(textbox=new_textbox):  # 使用默认参数来绑定当前文本框
            folder_path = filedialog.askdirectory()  # 打开选择文件夹对话框
            if folder_path:  # 如果选择了路径，则填充到文本框
                textbox.delete(0, tk.END)
                textbox.insert(0, folder_path)

        # 创建“浏览...”按钮并放置在文本框的右侧
        browse_button = tk.Button(row_frame, text="浏览...", command=browse_folder)
        browse_button.grid(row=0, column=1, pady=5, padx=(0, 10), sticky="w")

        # 创建“删除”按钮，并绑定删除功能
        def delete_row(frame=row_frame):
            # 删除当前行的所有控件
            frame.destroy()

        # 创建“删除”按钮并放置在浏览按钮的右侧
        delete_button = tk.Button(row_frame, text="删除", command=delete_row)
        delete_button.grid(row=0, column=2, pady=5, padx=(0, 10), sticky="w")

        # 将这一行的所有控件（文本框、浏览按钮、删除按钮）添加到框架中
        row_frame.grid(row=self.textbox_counter, column=0, pady=5, padx=10, sticky="ew")

        for widget in row_frame.winfo_children():
            widget.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
            widget.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
            widget.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

    def _on_mouse_wheel(self, event):
        """处理鼠标滚轮事件以滚动画布"""
        if event.num == 4 or event.delta > 0:
            self.canvas_window.yview_scroll(-1, "units")  # 向上滚动
        elif event.num == 5 or event.delta < 0:
            self.canvas_window.yview_scroll(1, "units")  # 向下滚动

    def connect_gradio(self):
        # 获取输入框中的 URL
        url = self.gradio_url_var.get() or "http://localhost:9872/"  # 如果为空则使用默认值
        thread_url = threading.Thread(target=self.connect_to_gradio, args=(url,))  # 使用 args 传递参数
        thread_url.start()

    def connect_to_gradio(self, url):
        global client  # 确保在函数中修改全局变量
        try:
            client = Client(url)  # 初始化 Gradio 客户端
            folder_audio_viewer.set_client(client)  # 将 client 赋值给 FolderAudioViewer 实例
            voice_generator_app.set_client(client)  # 将 client 赋值给 VoiceGeneratorApp 实例
            self.example_window.set_client(client)  # 将 client 赋值给 GPTSoVITSWindow 实例
            print(f"Connected to {url}")
            tk.messagebox.showinfo("Connection", f"Connected to {url}")
        except Exception as e:
            print(f"Failed to connect to {url}: {e}")
            tk.messagebox.showerror("Connection Error",
                                    f"Failed to connect to {url}: 请启动WebUI并开启TTS推理，在推理UI启动后连接到WebUI地址{e}")

    def run_connect_to_gradio_start(self):
        threading.Thread(target=self.connect_to_gradio_start).start()

    def connect_to_gradio_start(self):
        global client  # 确保在函数中修改全局变量

        # 从 config.json 中读取 Gradio URL
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
                url = config_data.get("config", {}).get("Gradio_URL", "http://localhost:9872/")
        except FileNotFoundError:
            url = "http://localhost:9872/"
            print("config.json 文件未找到，使用默认 URL")

        try:
            client = Client(url)  # 初始化 Gradio 客户端
            folder_audio_viewer.set_client(client)  # 将 client 赋值给 FolderAudioViewer 实例
            voice_generator_app.set_client(client)  # 将 client 赋值给 VoiceGeneratorApp 实例
            self.example_window.set_client(client)

            print(f"Connected to {url}")
            tk.messagebox.showinfo("Connection", f"Connected to {url}")
        except Exception as e:
            print(f"Failed to connect to {url}: {e}")
            tk.messagebox.showerror("Connection Error",
                                    f"无法连接至 {url} 请先启动WebUI并开启TTS推理，在推理UI启动后重新连接：{e}")

        # 使用 after() 方法确保 start_display_folders 在主线程中执行
        self.example_window.root.after(0, folder_audio_viewer.start_display_folders)

    def create_settings_tab(self, notebook, tab_name):
        """创建设置窗口中的每个选项卡"""
        frame = tk.Frame(notebook)
        notebook.add(frame, text=tab_name)

        tk.Label(frame, text=f"{tab_name} ACCESS_KEY：").pack(anchor='w', padx=10, pady=5)
        access_key_entry = tk.Entry(frame, width=30)
        access_key_entry.pack(anchor='w', padx=10)

        tk.Label(frame, text=f"{tab_name} SECRET_KEY：").pack(anchor='w', padx=10, pady=5)
        secret_key_entry = tk.Entry(frame, width=30)
        secret_key_entry.pack(anchor='w', padx=10)

        # 将entry添加到字典中
        self.entries[tab_name] = {"access_key": access_key_entry, "secret_key": secret_key_entry}

    def save_keys_and_close_window(self):
        self.save_keys()
        # 关闭设置窗口
        self.settings_window.destroy()

    def save_keys(self):
        """保存每个选项卡的 ACCESS_KEY、SECRET_KEY 和模型选择"""
        config_data = {"config": {}, "projects": self.projects}

        # 记录当前的自定义预设配置
        custom_presets = {}

        # 保存Gradio URL
        config_data["config"]["Gradio_URL"] = self.gradio_url_var.get()

        # 遍历每个选项卡，保存 ACCESS_KEY、SECRET_KEY 和模型选择
        for tab_name, entry_dict in self.entries.items():
            if tab_name == "自定义" or tab_name == "更多":
                continue  # 跳过自定义和更多选项卡的配置

            # 特殊处理“讯飞”选项卡
            if tab_name == "讯飞":
                access_key = entry_dict["access_key"].get()
                secret_key = entry_dict["secret_key"].get()
                api_key = entry_dict["api_key"].get()  # 获取APIKey
                model_choice = self.model_vars[tab_name].get()  # 获取模型选择

                # 保存“讯飞”选项卡的配置
                config_data["config"]["讯飞"] = {
                    "ACCESS_KEY": access_key,
                    "SECRET_KEY": secret_key,
                    "API_KEY": api_key,  # 保存API_KEY
                    "MODEL": model_choice  # 保存模型选择
                }
            else:
                access_key = entry_dict["access_key"].get()
                secret_key = entry_dict["secret_key"].get()
                model_choice = self.model_vars[tab_name].get()  # 获取模型选择

                # 保存其他选项卡的配置
                config_data["config"][tab_name] = {
                    "ACCESS_KEY": access_key,
                    "SECRET_KEY": secret_key,
                    "MODEL": model_choice  # 保存模型选择
                }

        # 获取滚动画布中所有文本框的内容
        character_folder_content = []

        def collect_textbox_content(frame):
            """递归遍历每个Frame，收集其中所有Entry的内容"""
            for child in frame.winfo_children():
                if isinstance(child, tk.Entry):  # 检查组件是否为文本框
                    text = child.get()
                    if text:  # 确保文本框中有内容才保存
                        character_folder_content.append(text)
                elif isinstance(child, tk.Frame):  # 如果子控件是Frame，则递归
                    collect_textbox_content(child)

        # 从滚动画布的根框架开始递归遍历
        collect_textbox_content(self.scrollable_frame_window)

        # 清空原有的 character_folder 内容并保存新的内容
        config_data["config"]["character_folder"] = character_folder_content

        # 获取当前选中的自定义预设
        selected_custom_preset = self.custom_config_var.get()

        # 保存当前选中的自定义预设配置到 config_data["config"]
        config_data["config"]["自定义已选择"] = selected_custom_preset

        # 检查 config.json 是否存在
        if os.path.exists("config.json"):
            # 如果存在，读取现有数据并更新
            with open("config.json", "r", encoding="utf-8") as f:
                existing_data = json.load(f)

            # 获取现有的自定义预设配置
            custom_presets = existing_data.get("config", {}).get("自定义", {})

            # 如果当前选中的自定义预设不存在，则创建
            if selected_custom_preset not in custom_presets:
                self.create_custom_preset()  # 调用函数创建自定义预设
                # 重新加载配置文件以获取新的自定义预设
                with open("config.json", "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                custom_presets = existing_data.get("config", {}).get("自定义", {})

            # 将自定义预设配置重新保存到 config_data 中
            config_data["config"]["自定义"] = custom_presets

            # 更新配置部分
            existing_data["config"] = config_data["config"]

            # 写入更新后的数据
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)
        else:
            # 如果不存在，创建新文件并写入数据
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)

    def create_scrollable_canvas(self):
        # 创建框架容器
        frame_canvas = tk.Frame(self.root)
        frame_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 创建画布
        self.canvas = tk.Canvas(frame_canvas)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 添加垂直滚动条
        self.scrollbar = ttk.Scrollbar(frame_canvas, orient="vertical", command=self.canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # 在画布上创建一个框架
        self.scrollable_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')

        # 使画布能够滚动
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # 绑定鼠标滚轮事件
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)  # Windows/Linux
        self.canvas.bind("<Button-4>", self._on_mousewheel)  # macOS Scroll Up
        self.canvas.bind("<Button-5>", self._on_mousewheel)  # macOS Scroll Down

        # 用于显示项目详细信息的标签
        self.project_details_label = tk.Label(self.scrollable_frame, text="项目详情示例内容", justify=tk.LEFT)
        self.project_details_label.pack(pady=10)

        self.project_details_label.bind("<MouseWheel>", self._on_mousewheel)  # Windows/Linux
        self.project_details_label.bind("<Button-4>", self._on_mousewheel)  # macOS Scroll Up
        self.project_details_label.bind("<Button-5>", self._on_mousewheel)  # macOS Scroll Down

    def _on_mousewheel(self, event):
        # 鼠标滚轮滚动实现
        if event.num == 4:  # macOS Scroll Up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:  # macOS Scroll Down
            self.canvas.yview_scroll(1, "units")
        else:  # Windows/Linux
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def create_project(self):
        """创建新项目并保存数据"""
        project_name = self.project_name_combobox.get()
        folder_path = self.folder_path_var.get()
        text_file_path = self.text_file_path_var.get()

        # 如果名称为空，则不执行操作
        if not project_name:
            messagebox.showwarning("警告", "请输入项目名称!")
            return

        if project_name == "新建配置":
            messagebox.showwarning("警告", "请修改项目名称！")
            return

        # 获取当前时间戳
        created_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 将项目数据保存到 projects 字典中
        self.projects[project_name] = {
            "folder_path": folder_path,
            "text_file_path": text_file_path,
            "created_time": created_time
        }

        # 检查 config.json 是否存在
        if os.path.exists("config.json"):
            # 如果存在，直接更新项目数据
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)

            config_data["projects"] = self.projects  # 只更新项目数据

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        else:
            # 如果不存在，创建新文件并写入数据
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump({"config": self.config, "projects": self.projects}, f, ensure_ascii=False, indent=4)

        print(f"项目 '{project_name}' 的数据已保存。")

        # 将新项目名称添加到列表中
        self.populate_project_names()

        self.refresh_tab2()

        # 更新画布中的项目详细信息
        self.update_project_details_in_canvas(project_name)

        voice_generator_app.clear_current_display()

        # 切换到选项卡2
        notebook_main.select(main_tab2)

        root.tk.call('tk', 'scaling', 1.25)

    def update_project_details_in_canvas(self, project_name):
        """在画布上显示项目的创建时间、字符数、行数及文件夹中相关信息"""
        if project_name in self.projects:
            project_data = self.projects[project_name]
            created_time = project_data['created_time']
            char_count, line_count = self.get_text_file_stats(project_data['text_file_path'])

            # 从 StringVar 获取路径的实际字符串值
            folder_path = self.folder_path_var.get()

            # 列举 Chapters 文件夹内的所有 .txt 文件
            chapters_path = os.path.join(folder_path, 'Chapters')
            chapters_files = [f for f in os.listdir(chapters_path) if f.endswith('.txt')] if os.path.exists(
                chapters_path) else []
            chapters_files_display = "\n".join(chapters_files) if chapters_files else "暂无"

            # 列举 Chapters_marked 文件夹内的所有 .txt 文件
            chapters_marked_path = os.path.join(folder_path, 'Chapters_marked')
            chapters_marked_files = [f for f in os.listdir(chapters_marked_path) if
                                     f.endswith('.txt')] if os.path.exists(chapters_marked_path) else []
            chapters_marked_files_display = "\n".join(chapters_marked_files) if chapters_marked_files else "暂无"

            # 列举 Chapters_tts 文件夹内的所有文件夹
            chapters_tts_path = os.path.join(folder_path, 'Chapters_tts')
            chapters_tts_folders = [f for f in os.listdir(chapters_tts_path)
                                    if os.path.isdir(os.path.join(chapters_tts_path, f))] if os.path.exists(
                chapters_tts_path) else []
            chapters_tts_folders_display = "\n".join(chapters_tts_folders) if chapters_tts_folders else "暂无"

            # 汇总信息
            details = (
                f"项目名: {project_name}\n"
                f"创建时间: {created_time}\n"
                f"字符数: {char_count}\n"
                f"行数: {line_count}\n\n"
                f"已分章节:\n{chapters_files_display}\n\n"
                f"已标记章节:\n{chapters_marked_files_display}\n\n"
                f"待合成章节:\n{chapters_tts_folders_display}"
            )

            # 更新画布上的标签文本
            self.project_details_label.config(text=details)

    def mouse_wheel(self, event):
        """处理鼠标滚轮事件以滚动画布"""
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")  # 向上滚动
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")  # 向下滚动

    def refresh_tab2(self):
        """刷新选项卡2内容的函数"""
        # print("Refreshing Tab 2...")  # 调试输出
        self.text_preprocessor.reset_chapter_selection()  # 调用TextPreprocessor中的加载函数


class GPTSoVITSWindow:
    def __init__(self, root):
        # 新建窗口
        self.root = root
        self.window = tk.Toplevel(root)  # 使用 Toplevel 创建一个新窗口
        self.window.title("测试GPT-SoVITS")  # 设置窗口标题
        self.window.geometry("1000x600")  # 设置窗口大小
        self.window.minsize(1000, 600)
        self.client = None

        # 初始化任务参数
        self.total_tasks = 0  # 总任务量
        self.current_task = 0  # 当前任务量
        self.start_time = None  # 任务开始时间
        self.progress_bar_done = True

        self.sovits_choices = []
        self.gpt_choices = []

        # 设置窗口的 grid 行列自适应
        self.window.grid_rowconfigure(0, weight=1)  # 第0行自适应高度
        self.window.grid_columnconfigure(0, weight=1)  # 第0列自适应宽度
        self.window.grid_columnconfigure(1, weight=0, minsize=200)  # 第1列宽度固定

        # 框架
        self.left_frame = tk.Frame(self.window)
        self.left_frame.grid(row=0, column=0, sticky="nsew")
        self.right_frame = tk.Frame(self.window)
        self.right_frame.grid(row=0, column=1, sticky="nsew")
        self.bottom_frame = tk.Frame(self.window)
        self.bottom_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")

        # 设置框架的自适应行为
        self.left_frame.grid_rowconfigure(1, weight=1)  # 让文本框填充剩余空间
        self.left_frame.grid_columnconfigure(0, weight=1)  # 让第一列填充宽度
        self.left_frame.grid_columnconfigure(1, weight=0)  # 第二列用于top_k，宽度固定

        self.right_frame.grid_rowconfigure(0, weight=0)  # 右边框架的高度不随窗口变化
        self.right_frame.grid_columnconfigure(0, weight=0)  # 右边框架的宽度固定

        self.bottom_frame.grid_rowconfigure(0, weight=1)  # 底部框架的高度填充
        self.bottom_frame.grid_columnconfigure(1, weight=1)  # 底部框架的宽度随窗口变化

        # 文本框
        tk.Label(self.left_frame, text="要合成的文本:").grid(row=0, column=0, sticky="w")
        self.text_entry = scrolledtext.ScrolledText(self.left_frame, height=15, width=50)
        self.text_entry.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

        # top_k
        tk.Label(self.left_frame, text="top_k").grid(row=2, column=0, sticky="w")
        self.top_k_var = tk.StringVar(value="15")
        tk.Entry(self.left_frame, textvariable=self.top_k_var).grid(row=2, column=1, padx=5, pady=2, sticky="w")

        # top_p
        tk.Label(self.left_frame, text="top_p:").grid(row=3, column=0, sticky="w", pady=2)
        self.top_p_var = tk.StringVar(value="1")
        tk.Entry(self.left_frame, textvariable=self.top_p_var).grid(row=3, column=1, padx=5, pady=2, sticky="w")

        # temperature
        tk.Label(self.left_frame, text="温度:").grid(row=4, column=0, sticky="w", pady=2)
        self.temperature_var = tk.StringVar(value="1")
        tk.Entry(self.left_frame, textvariable=self.temperature_var).grid(row=4, column=1, padx=5, pady=2, sticky="w")

        # 语速
        tk.Label(self.left_frame, text="语速:").grid(row=5, column=0, sticky="w", pady=2)
        self.speed_var = tk.StringVar(value="1")
        tk.Entry(self.left_frame, textvariable=self.speed_var).grid(row=5, column=1, padx=5, pady=2, sticky="w")

        # 无参考模式
        tk.Label(self.left_frame, text="无参考模式:").grid(row=6, column=0, sticky="w", pady=2)
        self.ref_free_var = tk.BooleanVar()
        tk.Checkbutton(self.left_frame, variable=self.ref_free_var).grid(row=6, column=1, padx=5, pady=2, sticky="w")

        # 冻结设置
        tk.Label(self.left_frame, text="冻结设置:").grid(row=7, column=0, sticky="w", pady=2)
        self.if_freeze_var = tk.BooleanVar()
        tk.Checkbutton(self.left_frame, variable=self.if_freeze_var).grid(row=7, column=1, padx=5, pady=2, sticky="w")

        # 选择配置行
        self.config_frame = tk.Frame(self.right_frame)
        self.config_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")

        # 角色列表路径
        self.config1_frame = tk.Frame(self.config_frame)
        self.config1_frame.grid(row=0, column=0, sticky="nsew")
        tk.Label(self.config1_frame, text="角色列表路径").grid(row=0, column=0, sticky="w")
        self.character_list_path_var = tk.StringVar()
        self.character_list_path = ttk.Combobox(self.config1_frame, textvariable=self.character_list_path_var, width=10)
        self.character_list_path.grid(row=1, column=0, padx=0, pady=2, sticky="w")

        self.character_list_path.bind("<<ComboboxSelected>>", self.update_charactor_options_window)

        # 绑定鼠标进入事件，悬停时刷新选项
        self.character_list_path.bind("<Enter>", self.populate_folder_dropdown_window)

        # 角色列表
        self.config2_frame = tk.Frame(self.config_frame)
        self.config2_frame.grid(row=0, column=1, sticky="nsew")
        tk.Label(self.config2_frame, text="选择角色").grid(row=0, padx=9, column=0, sticky="w")
        self.character_list_var = tk.StringVar(value="当前角色")
        self.character_list = ttk.Combobox(self.config2_frame, textvariable=self.character_list_var, width=10)
        self.character_list.grid(row=1, column=0, padx=9, pady=2, sticky="w")

        # 绑定选择事件
        self.character_list.bind("<<ComboboxSelected>>", self.on_charactor_selected_window)

        # 绑定鼠标进入事件，悬停时刷新选项
        self.character_list.bind("<Enter>", self.update_charactor_options_window)

        # 配置列表
        self.config3_frame = tk.Frame(self.config_frame)
        self.config3_frame.grid(row=0, column=2, sticky="nsew")
        tk.Label(self.config3_frame, text="选择配置").grid(row=0, column=0, sticky="w")
        self.config_list_var = tk.StringVar()
        self.config_list = ttk.Combobox(self.config3_frame, textvariable=self.config_list_var, width=10)
        self.config_list.grid(row=1, column=0, padx=0, pady=2, sticky="w")

        self.config_list.bind("<<ComboboxSelected>>", self.on_json_file_selected_window)

        # 绑定鼠标进入事件，悬停时刷新选项
        self.config_list.bind("<Enter>", self.update_json_options_window)

        # 导出按钮
        self.config4_frame = tk.Frame(self.config_frame)
        self.config4_frame.grid(row=0, column=3, sticky="nsew")
        self.output_button = tk.Button(self.config4_frame, text="导出", command=self.export_character_config)
        self.output_button.grid(row=1, column=0, padx=5, pady=(19, 0), sticky="w")

        self.populate_folder_dropdown_window()
        self.update_charactor_options_window()
        self.update_json_options_window()

        # 参考音频
        tk.Label(self.right_frame, text="参考音频路径:").grid(row=2, column=0, sticky="w", pady=1)
        self.ref_wav_path_entry = tk.StringVar()
        self.ref_wav_path = ttk.Combobox(self.right_frame, textvariable=self.ref_wav_path_entry, width=38)
        self.ref_wav_path.grid(row=3, column=0, pady=1, sticky="w")
        tk.Button(self.right_frame, text="浏览...", command=lambda: self.browse_file(self.ref_wav_path)).grid(
            row=3, column=1,
            padx=5, pady=1,
            sticky="w")

        # 提示文本
        tk.Label(self.right_frame, text="提示文本:").grid(row=4, column=0, sticky="w", pady=1)
        self.prompt_text_entry = tk.Entry(self.right_frame, width=40)
        self.prompt_text_entry.grid(row=5, column=0, pady=1, sticky="w", columnspan=2)

        # 选择模型框架
        self.in_right_frame = tk.Frame(self.right_frame)
        self.in_right_frame.grid(row=6, column=0, columnspan=2, rowspan=5, sticky="wn")

        # SoVITS模型下拉栏
        tk.Label(self.in_right_frame, text="SoVITS模型:").grid(row=0, column=1, sticky="w", pady=1, padx=5)
        self.sovits_var = tk.StringVar(value="请选择")
        self.sovits_menu = tk.OptionMenu(self.in_right_frame, self.sovits_var, [])
        self.sovits_menu.grid(row=0, column=2, padx=5, pady=1, sticky="w", columnspan=2)
        self.sovits_menu.config(width=15)

        # GPT模型下拉栏
        tk.Label(self.in_right_frame, text="GPT模型:").grid(row=1, column=1, sticky="w", pady=1, padx=5)
        self.gpt_var = tk.StringVar(value="请选择")
        self.gpt_menu = tk.OptionMenu(self.in_right_frame, self.gpt_var, [])
        self.gpt_menu.grid(row=1, column=2, padx=5, pady=1, sticky="w", columnspan=2)
        self.gpt_menu.config(width=15)

        # 刷新模型按钮
        tk.Button(self.in_right_frame, text="刷新模型", command=self.run_update_model_choices).grid(row=0, column=0,
                                                                                                    pady=5,
                                                                                                    sticky="w")

        # 确认模型按钮
        tk.Button(self.in_right_frame, text="确认模型", command=self.run_submit).grid(row=1, column=0, pady=5,
                                                                                      sticky="w")

        # 参考语言
        tk.Label(self.in_right_frame, text="参考语言:").grid(row=3, column=0, columnspan=2, sticky="w", pady=1)
        self.prompt_language_var = tk.StringVar(value="请选择")
        self.prompt_language_menu = tk.OptionMenu(self.in_right_frame, self.prompt_language_var, "请先确认模型")
        self.prompt_language_menu.grid(row=3, column=2, padx=5, pady=1, sticky="w")
        self.prompt_language_menu.config(width=15)

        # 生成语言
        tk.Label(self.in_right_frame, text="生成语言:").grid(row=4, column=0, columnspan=2, sticky="w", pady=1)
        self.text_language_var = tk.StringVar(value="请选择")
        self.text_language_menu = tk.OptionMenu(self.in_right_frame, self.text_language_var, "请先确认模型")
        self.text_language_menu.grid(row=4, column=2, padx=5, pady=1, sticky="w")
        self.text_language_menu.config(width=15)

        # 分句内切割方式
        tk.Label(self.in_right_frame, text="分句内切割方式:").grid(row=5, column=0, columnspan=2, sticky="w", pady=1)
        self.cut_method_var = tk.StringVar(value="不切")
        self.cut_method_menu = tk.OptionMenu(self.in_right_frame, self.cut_method_var, "不切", "凑四句一切",
                                             "凑50字一切", "按中文句号。切", "按英文句号.切", "按标点符号切")
        self.cut_method_menu.grid(row=5, column=2, padx=5, pady=1, sticky="w")
        self.cut_method_menu.config(width=15)

        # 自定义分句符号
        tk.Label(self.right_frame, text="分句符号(留空为不分句,输出一个完整音频):").grid(row=11, column=0, sticky="w",
                                                                                         pady=1)
        self.delimiter_entry = tk.Entry(self.right_frame, width=40)
        self.delimiter_entry.grid(row=12, column=0, pady=1, sticky="w", columnspan=2)
        self.delimiter_entry.insert(0, "|")

        # 选择输出目录
        tk.Label(self.right_frame, text="选择输出目录:").grid(row=13, column=0, sticky="w", pady=1)
        self.output_dir_entry = tk.Entry(self.right_frame, width=40)
        self.output_dir_entry.grid(row=14, column=0, pady=1, sticky="w")
        tk.Button(self.right_frame, text="浏览...", command=lambda: self.browse_directory(self.output_dir_entry)).grid(
            row=14,
            column=1,
            padx=5, pady=1,
            sticky="w")

        # 文件名前缀
        tk.Label(self.right_frame, text="文件名前缀:").grid(row=15, column=0, sticky="w", pady=1)
        self.filename_prefix_entry = tk.Entry(self.right_frame, width=40)
        self.filename_prefix_entry.grid(row=16, column=0, pady=1, sticky="w", columnspan=2)

        # 进度百分比
        self.progress_percentage_label = tk.Label(self.bottom_frame, text="进度: 0%")
        self.progress_percentage_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = Progressbar(self.bottom_frame, variable=self.progress_var, orient="horizontal")
        self.progress_bar.grid(row=0, column=1, padx=1, sticky="ew")

        # 运行时间和剩余时间
        self.time_label = tk.Label(self.bottom_frame, text="运行时间|剩余时间: 00:00:00|00:00:00")
        self.time_label.grid(row=0, column=2, padx=1, pady=5, sticky="e")

        # 提交按钮
        tk.Button(self.bottom_frame, text="生成语音", command=self.run_generate_audio_files).grid(row=0, column=3,
                                                                                                  pady=5,
                                                                                                  padx=10)

        self.ref_wav_path.bind(
            "<<ComboboxSelected>>",
            lambda event: self.update_text_window(
                self.ref_wav_path_entry.get(),
                self.prompt_text_entry,
                self.prompt_language_var,
                self.text_language_var
            )
        )

        # 默认设置窗口为隐藏
        self.window.withdraw()  # 初始时窗口不显示

        # 重载窗口的关闭事件，使窗口关闭时不销毁实例
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

    def set_client(self, client):
        self.client = client  # 设置 client
        # print(f"Client set in GPTSoVITSWindow: {self.client}")
        self.run_update_model_choices()

    def on_charactor_selected_window(self, event=None):
        """处理角色选择事件，更新配置文件和音频文件"""
        self.update_json_options_window()  # 更新 json 配置文件下拉框
        self.update_audio_files_window()  # 更新音频文件下拉框
        self.auto_choice_model()
        self.update_text_window(self.ref_wav_path_entry.get(),
                                self.prompt_text_entry,
                                self.prompt_language_var,
                                self.text_language_var)

    def auto_choice_model(self):
        """根据selected_charactor值更新下拉框选择项"""
        # 获取当前行的下拉菜单变量
        sovits_menu = self.sovits_menu  # SoVITS下拉菜单
        gpt_menu = self.gpt_menu  # GPT下拉菜单
        selected_charactor = self.character_list_var.get()

        # 提取文件名并匹配selected_charactor
        sovits_model_paths = [
            path for path in self.sovits_choices if selected_charactor in os.path.basename(path)
        ]
        gpt_model_paths = [
            path for path in self.gpt_choices if selected_charactor in os.path.basename(path)
        ]

        # 设置默认选择项（如果没有匹配的模型，则选择第一个选项，或显示"无匹配模型"）
        selected_sovits = sovits_model_paths[0] if sovits_model_paths else "请选择"
        selected_gpt = gpt_model_paths[0] if gpt_model_paths else "请选择"

        # 更新SoVITS菜单的当前选择
        sovits_menu.setvar(sovits_menu.cget("textvariable"), selected_sovits)

        # 更新GPT菜单的当前选择
        gpt_menu.setvar(gpt_menu.cget("textvariable"), selected_gpt)

    def update_charactor_options_window(self, event=None):
        """更新角色下拉框选项"""
        # print("update_charactor_options_window")
        folder_path = self.character_list_path_var.get()
        # print(folder_path)
        if os.path.exists(folder_path):
            folders = [name for name in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, name))]
            self.character_list['values'] = folders + ["当前角色"]
        else:
            self.character_list['values'] = ["当前角色"]

    def update_json_options_window(self, event=None):
        """更新 JSON 文件下拉框选项"""
        # print("update_json_options_window")
        selected_folder = self.character_list_var.get()

        if selected_folder != "当前角色":
            # 处理非“当前角色”的情况
            folder_path = self.character_list_path_var.get()
            json_folder_path = os.path.join(folder_path, selected_folder)

            if os.path.exists(json_folder_path):
                json_files = [name[:-5] for name in os.listdir(json_folder_path) if name.endswith('.json')]
                # 更新对应行的 combo_box_config 的值
                combo_box_config = self.config_list  # 获取 ttk.Combobox 对象
                combo_box_config['values'] = json_files + ["新建配置"]  # 更新下拉选项
            else:
                combo_box_config = self.config_list
                combo_box_config['values'] = ["新建配置"]  # 没有可用的 JSON 文件，仅提供“新建配置”
        else:
            # 如果选择了“当前角色”
            label_name = "当前角色"  # 从 row_variables 中获取 label_name
            combo_box_config = self.config_list  # 获取 ttk.Combobox 对象

            # 为 combo_box_config 添加 label_name 和 “新建配置” 两个选项
            combo_box_config['values'] = ["当前角色", "新建配置"]

            # 自动填充 combo_box_config 的文本框内容为 label_name
            combo_box_config.set("当前角色")

    def update_audio_files_window(self):
        """更新参考音频下拉框选项，并自动选择路径最短且文件名最长的 .wav 文件"""
        selected_folder = self.character_list_var.get()

        # 获取文件夹路径
        folder_path = os.path.join(self.character_list_path_var.get(), selected_folder)  # 获取文件夹路径

        # 获取所有 .wav 文件路径列表
        audio_files = self.get_audio_files_window(folder_path)

        if not audio_files:
            # 如果没有 .wav 文件，清空下拉框并退出
            combo_box = self.ref_wav_path
            combo_box['values'] = []
            return

        # 找到路径最短且在路径相同时文件名最长的文件
        def get_file_priority(file_path):
            dir_path, file_name = os.path.split(file_path)
            return (len(dir_path), -len(file_name))  # 按路径长度升序，文件名长度降序排序

        selected_file = min(audio_files, key=get_file_priority)

        # 更新下拉框
        combo_box = self.ref_wav_path
        combo_box['values'] = audio_files  # 更新下拉框的值
        combo_box.set(selected_file)  # 自动选择最优文件

    def get_audio_files_window(self, folder):
        return glob.glob(os.path.join(folder, "**/*.wav"), recursive=True)

    def on_json_file_selected_window(self, event=None):
        """选择 JSON 文件后应用配置"""
        selected_file = self.config_list_var.get()
        folder_path = self.character_list_var.get()

        # 检查是否选择了“新建配置”
        if selected_file == "新建配置":
            return

        # 继续处理其他选项
        main_folder_path = self.character_list_path_var.get()
        config_file_path = os.path.join(main_folder_path, folder_path, f"{selected_file}.json")

        try:
            with open(config_file_path, 'r', encoding='utf-8') as file:
                config_data = json.load(file)

            # 更新对应的变量
            self.top_k_var.set(config_data.get('top_k', '15'))  # 默认值为 15
            self.top_p_var.set(config_data.get('top_p', '1'))  # 默认值为 1
            self.temperature_var.set(config_data.get('temperature', '1'))  # 默认值为 1
            self.speed_var.set(config_data.get('speed', '1'))  # 默认值为 1
            self.ref_free_var.set(config_data.get('ref_free', False))  # 默认值为 False
            self.if_freeze_var.set(config_data.get('if_freeze', False))  # 默认值为 False
            self.sovits_var.set(config_data.get('sovits', '请选择'))  # 默认值为 '请选择'
            self.gpt_var.set(config_data.get('gpt', '请选择'))  # 默认值为 '请选择'
            self.ref_wav_path_entry.set(config_data.get('ref_wav_path', ''))  # 默认值为 ''
            self.prompt_text_entry.delete(0, tk.END)
            self.prompt_text_entry.insert(0, config_data.get('prompt', ''))  # 默认值为 ''
            self.prompt_language_var.set(config_data.get('ref_language', '请选择'))  # 默认值为 '请选择'
            self.text_language_var.set(config_data.get('text_language', '请选择'))  # 默认值为 '请选择'
            self.cut_method_var.set(config_data.get('cut_method', '凑四句一切'))  # 默认值为 '凑四句一切'
            self.delimiter_entry.delete(0, tk.END)
            self.delimiter_entry.insert(0, config_data.get('delimiter', '|'))  # 默认值为 '|'

        except FileNotFoundError:
            messagebox.showerror("错误", f"找不到配置文件：{config_file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导入配置时发生错误：{str(e)}")

    def export_character_config(self):
        # 获取配置
        folder_path = self.character_list_var.get()
        selected_option = self.config_list_var.get()
        top_k = self.top_k_var.get()
        top_p = self.top_p_var.get()
        temperature = self.temperature_var.get()
        speed = self.speed_var.get()
        ref_free = self.ref_free_var.get()
        if_freeze = self.if_freeze_var.get()
        sovits = self.sovits_var.get()
        gpt = self.gpt_var.get()
        ref_wav_path = self.ref_wav_path_entry.get()
        prompt = self.prompt_text_entry.get()
        ref_language = self.prompt_language_var.get()
        text_language = self.text_language_var.get()
        cut_method = self.cut_method_var.get()
        delimiter = self.delimiter_entry.get()
        show_message = True

        # 获取主文件夹路径
        main_folder_path = self.character_list_path_var.get()

        # 如果 folder_path 是 "当前角色"，使用 self.folder_path_var 路径
        if folder_path == "当前角色":
            full_folder_path = self.output_dir_entry.get()
        else:
            full_folder_path = os.path.join(main_folder_path, folder_path)

        # 检查路径是否存在
        if not full_folder_path:
            messagebox.showerror("错误", "请选择一个有效的文件夹路径")
            return

        # 创建配置数据
        config_data = {
            "top_k": top_k,
            "top_p": top_p,
            "temperature": temperature,
            "speed": speed,
            "ref_free": ref_free,
            "if_freeze": if_freeze,
            "sovits": sovits,
            "gpt": gpt,
            "ref_wav_path": ref_wav_path,
            "prompt": prompt,
            "ref_language": ref_language,
            "text_language": text_language,
            "cut_method": cut_method,
            "delimiter": delimiter
        }

        # 使用下拉框选项命名配置文件
        config_path = os.path.join(full_folder_path, f"{selected_option}.json")

        # 写入配置到指定路径
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            if show_message:
                messagebox.showinfo("成功", f"角色配置已导出到: {config_path}")
            return config_path  # 返回导出的文件路径
        except Exception as e:
            messagebox.showerror("错误", f"导出配置文件时出错: {str(e)}")
            return None

    def populate_folder_dropdown_window(self, event=None):
        """将config.json中的character_folder加载到下拉框中"""
        # print("刷新了4")
        config_file = "config.json"
        if os.path.exists(config_file):
            # 读取配置文件
            with open(config_file, 'r', encoding='utf-8') as file:
                config_data = json.load(file)

            # 获取character_folder并更新下拉框
            character_folders = config_data.get('config', {}).get('character_folder', [])
            if character_folders:
                # 将folder paths加入到下拉框
                self.character_list_path['values'] = character_folders
                self.character_list_path_var.set(character_folders[0])  # 默认选择第一个文件夹
            else:
                print(f"配置文件中未找到 'character_folder' 项！")
        else:
            print(f"配置文件 {config_file} 不存在!")

    def update_progress(self):
        # 强制完成进度条
        if self.progress_bar_done:
            self.current_task = self.total_tasks

        # 确保当前任务量不会超过总任务量
        if self.current_task > self.total_tasks:
            return

        # 计算进度百分比
        progress_percentage = (self.current_task / self.total_tasks) * 100
        self.progress_var.set(progress_percentage)
        self.progress_percentage_label.config(text=f"进度: {int(progress_percentage)}%")

        # 计算运行时间
        elapsed_time = time.time() - self.start_time
        remaining_time = (elapsed_time / self.current_task) * (
                self.total_tasks - self.current_task) if self.current_task > 0 else 0

        # 格式化时间显示
        elapsed_time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
        remaining_time_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))

        # 更新时间标签
        self.time_label.config(text=f"运行时间|剩余时间: {elapsed_time_str}|{remaining_time_str}")

        # 如果当前任务未完成，继续每秒更新进度
        if self.current_task < self.total_tasks:
            self.root.after(1000, self.update_progress)

    def run_update_model_choices(self):
        threading.Thread(target=self.update_model_choices).start()
        # print("Update model choices running")

    def run_submit(self):
        threading.Thread(target=self.submit).start()

    def run_generate_audio_files(self):
        # 初始化进度条参数
        self.progress_bar_done = False
        self.current_task = 0  # 当前任务量
        self.start_time = time.time()  # 任务开始时间初始化为当前时间

        # 获取 text_entry 中的文本
        text = self.text_entry.get("1.0", tk.END).strip()

        # 获取 delimiter_entry 中的分隔符
        delimiter = self.delimiter_entry.get().strip()

        # 按照分隔符分割文本
        segments = text.split(delimiter)

        # 设置任务总数为分割出的段数
        self.total_tasks = len(segments)

        # 重置进度条和百分比标签
        self.progress_bar['value'] = 0  # 重置进度条
        self.progress_percentage_label.config(text="进度: 0%")  # 重置进度百分比
        self.update_progress()  # 更新进度条显示

        # 打印调试信息，查看段数是否正确（可选）
        # print(f"Total segments: {self.total_tasks}")

        threading.Thread(target=self.generate_audio_files).start()

    def update_model_choices(self):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return
        # Request model choices from the API
        result = self.client.predict(api_name="/change_choices")

        # Extract SoVITS and GPT model choices from the result
        self.sovits_choices = [choice[0] for choice in result[0]['choices']]
        self.gpt_choices = [choice[0] for choice in result[1]['choices']]

        # Update the options in the dropdown menus
        self.sovits_menu['menu'].delete(0, 'end')
        self.gpt_menu['menu'].delete(0, 'end')

        for choice in self.sovits_choices:
            self.sovits_menu['menu'].add_command(label=choice, command=tk._setit(self.sovits_var, choice))

        for choice in self.gpt_choices:
            self.gpt_menu['menu'].add_command(label=choice, command=tk._setit(self.gpt_var, choice))

    def submit(self):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return
        sovits_model = self.sovits_var.get()
        gpt_model = self.gpt_var.get()

        # Submit the selected SoVITS model to the API
        sovits_result = self.client.predict(
            sovits_path=sovits_model,
            api_name="/change_sovits_weights"
        )

        # Submit the selected GPT model to the API
        gpt_result = self.client.predict(
            gpt_path=gpt_model,
            api_name="/change_gpt_weights"
        )

        # 提取参考语言和生成语言的选项
        ref_language_choices = [choice[0] for choice in sovits_result[0]['choices']]
        gen_language_choices = [choice[0] for choice in sovits_result[1]['choices']]

        # 更新参考语言下拉菜单的选项
        self.prompt_language_menu['menu'].delete(0, 'end')
        for choice in ref_language_choices:
            self.prompt_language_menu['menu'].add_command(label=choice,
                                                          command=tk._setit(self.prompt_language_var, choice))

        # 更新生成语言下拉菜单的选项
        self.text_language_menu['menu'].delete(0, 'end')
        for choice in gen_language_choices:
            self.text_language_menu['menu'].add_command(label=choice, command=tk._setit(self.text_language_var, choice))

    @check_using_api
    def generate_audio_files(self):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        try:
            # 获取当前行的所有参数
            sovits_model = self.sovits_var.get()
            gpt_model = self.gpt_var.get()
            ref_wav_path = handle_file(self.ref_wav_path_entry.get().strip())  # 参考音频路径

            ref_free = self.ref_free_var.get()  # 是否使用自由音频

            # 当 ref_free 为 True 时，将 prompt_text 设为空
            if ref_free:
                prompt_text = ""  # 提示文本为空
            else:
                prompt_text = self.prompt_text_entry.get().strip()  # 获取提示文本

            ref_language = self.prompt_language_var.get().strip()  # 获取参考音频语言
            text_language = self.text_language_var.get().strip()  # 合成文本语言
            cut_method = self.cut_method_var.get().strip()  # 切割方式
            top_k = int(self.top_k_var.get().strip())  # top_k 参数
            top_p = float(self.top_p_var.get().strip())  # top_p 参数
            temperature = float(self.temperature_var.get().strip())  # 温度
            speed = float(self.speed_var.get().strip())  # 语速
            if_freeze = self.if_freeze_var.get()  # 是否冻结
            filename_prefix = self.filename_prefix_entry.get()
            delimiter = self.delimiter_entry.get().strip()  # 分隔符
            # row_name = self.row_variables[idx]['label_name'].cget("text")  # 获取行的名称

            print(
                f"获取的参数：{sovits_model}, {gpt_model}, {ref_wav_path}, {prompt_text}, {ref_language}, {text_language}, "
                f"{top_k}, {top_p}, {temperature}, {speed}, {ref_free}, {if_freeze}, {cut_method}, {delimiter}")

            # 确认模型是否有效
            if sovits_model != "请选择" and gpt_model != "请选择":
                try:
                    # 提交 SoVITS 和 GPT 模型到 API
                    self.client.predict(sovits_path=sovits_model, api_name="/change_sovits_weights")
                    self.client.predict(gpt_path=gpt_model, api_name="/change_gpt_weights")
                    print(f"执行的模型 {sovits_model}, {gpt_model}")

                except Exception as e:
                    messagebox.showerror("错误", str(e))
                    # failed_rows.append(row_name)  # 记录出错的行名
                    return

            # 选择保存路径
            save_path = self.output_dir_entry.get()
            # audio_cache_path = os.path.join(save_path, "AudioCache")
            os.makedirs(save_path, exist_ok=True)
            output_dir = save_path

            text_content = self.text_entry.get("1.0", tk.END).strip()

            # 使用自定义分隔符分割文本
            sentences = self.split_text(text_content, delimiter)

            temp_files = []  # 临时文件路径

            # 逐句生成音频
            for idx, sentence in enumerate(sentences):
                if not all(
                        [ref_wav_path, ref_language, text_language, cut_method, top_k, top_p, temperature,
                         speed, sentence]):
                    # failed_rows.append(row_name)  # 记录出错的行名
                    return

                try:
                    result = self.client.predict(
                        ref_wav_path=ref_wav_path,
                        prompt_text=prompt_text,
                        prompt_language=ref_language,
                        text_language=text_language,
                        how_to_cut=cut_method,
                        top_k=top_k,
                        top_p=top_p,
                        temperature=temperature,
                        speed=speed,
                        ref_free=ref_free,
                        if_freeze=if_freeze,
                        text=sentence,
                        inp_refs=[],
                        api_name="/get_tts_wav"
                    )

                    print(
                        f"实际执行的参数：{sovits_model}, {gpt_model}, {ref_wav_path}, {prompt_text}, {ref_language}, {text_language}, "
                        f"{top_k}, {top_p}, {temperature}, {speed}, {ref_free}, {if_freeze}, {cut_method}, {delimiter}, {sentence}")

                    # 获取音频文件路径
                    audio_file_path = result[0] if isinstance(result, tuple) and len(result) > 0 else result
                    if os.path.exists(audio_file_path):
                        dest_path = os.path.join(output_dir, f"{filename_prefix} {idx + 1}.wav")
                        shutil.move(audio_file_path, dest_path)

                        # 更新进度条
                        # self.update_progress

                    temp_files.append(audio_file_path)

                    self.current_task += 1
                    print(self.current_task)
                    self.update_progress()  # 更新进度条显示

                except Exception as e:
                    messagebox.showerror("错误", f"音频生成失败: {str(e)}")
                    # failed_rows.append(row_name)  # 记录出错的行名

            # 调用清理函数清理临时文件
            # self.cleanup_temp_files(temp_files)

            self.progress_bar_done = True
            self.update_progress()  # 更新进度条显示

        except Exception as e:
            # 捕获异常并将出错的行记录到 failed_rows 中
            # row_name = self.row_variables[idx]['label_name'].cget("text")
            # failed_rows.append(row_name)
            print(f"生成第 {idx} 行语音时出错: {e}")

    def split_text(self, text, delimiter):
        """根据给定的分隔符分割文本"""
        if delimiter:
            # 转义自定义分隔符
            escaped_delimiter = self.escape_regex_chars(delimiter)
            # 使用转义后的分隔符进行分割
            sentences = re.split(escaped_delimiter, text)
        else:
            sentences = [text]
        return [s.strip() for s in sentences if s.strip()]

    def escape_regex_chars(self, pattern):
        """转义正则表达式中的特殊字符"""
        return re.escape(pattern)

    def browse_directory(self, entry_widget):
        """浏览目录并设置路径"""
        directory = filedialog.askdirectory()
        if directory:  # 仅在用户选择了目录后更新路径框
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, directory)

    # 浏览文件函数
    def browse_file(self, entry):
        file_path = filedialog.askopenfilename(filetypes=[("WAV files", "*.wav")])
        if file_path:
            entry.delete(0, tk.END)
            entry.insert(0, file_path)
            # 调用 update_text 函数，传入选定的文件路径
            self.update_text_window(file_path, self.prompt_text_entry, self.prompt_language_var, self.text_language_var)

    def update_text_window(self, audio_file, prompt_text_entry, prompt_language_var, text_language_var):
        filename = os.path.basename(audio_file)
        # print("更新")

        if "#" in filename:
            # 分割文件名，获取最后一个 '#' 后的部分
            parts = filename.split("#")
            if len(parts) >= 2:  # 确保有足够的 '#' 来获取最后两个 '#'
                # 使用原有方法判断
                text_between_hash = parts[-2]

                # 根据文本判断语言并设置 prompt_language_var 和 text_language_var
                if text_between_hash in ["zh", "中文"]:
                    prompt_language_var.set("中文")
                    text_language_var.set("中文")
                elif text_between_hash in ["en", "英文"]:
                    prompt_language_var.set("英文")
                    text_language_var.set("英文")
                elif text_between_hash in ["ja", "日文"]:
                    prompt_language_var.set("日文")
                    text_language_var.set("日文")

                # 处理最后一个 '#' 后面的文本
                text_after_hash = parts[-1]
                last_dot_index = text_after_hash.rfind('.')
                if last_dot_index != -1:
                    text_after_hash = text_after_hash[:last_dot_index]
                prompt_text_entry.delete(0, tk.END)  # 清空输入框
                prompt_text_entry.insert(0, text_after_hash)  # 填充提示文本
            else:
                prompt_text_entry.delete(0, tk.END)  # 如果没有足够的 '#'，则清空 prompt_text_entry
        else:
            # 删除末尾的 .wav 扩展名
            cleaned_text = filename.rstrip('.wav').strip()

            # 删除句子前【】符号内的内容
            cleaned_text = re.sub(r'【.*?】', '', cleaned_text).strip()

            # 判断语言
            def contains_chinese(text):
                return bool(re.search(r'[\u4e00-\u9fff]', text))

            def contains_japanese(text):
                return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF\u32D0-\u32FF]', text))

            def contains_english(text):
                return bool(re.search(r'[a-zA-Z]', text))

            # 语言检测
            has_chinese = contains_chinese(cleaned_text)
            has_japanese = contains_japanese(cleaned_text)
            has_english = contains_english(cleaned_text)

            # 语言组合逻辑：日文优先
            if has_japanese and has_english:
                self.prompt_language_var.set("日英混合")
                self.text_language_var.set("日英混合")
            elif has_japanese:
                self.prompt_language_var.set("日文")
                self.text_language_var.set("日文")
            elif has_chinese and has_english:
                self.prompt_language_var.set("中英混合")
                self.text_language_var.set("中英混合")
            elif has_chinese:
                self.prompt_language_var.set("中文")
                self.text_language_var.set("中文")
            elif has_english:
                self.prompt_language_var.set("英文")
                self.text_language_var.set("英文")
            else:
                self.prompt_language_var.set("未知")
                self.text_language_var.set("未知")

            # 设置提示文本
            self.prompt_text_entry.delete(0, tk.END)  # 清空输入框
            self.prompt_text_entry.insert(0, cleaned_text)  # 填充提示文本

    def on_button_click(self):
        print("按钮被点击了！")

    def on_close(self):
        # 当用户点击窗口的关闭按钮时，不销毁实例，只隐藏窗口
        print("窗口被关闭，但实例仍然存在")
        self.window.withdraw()  # 隐藏窗口

    def show_window(self):
        self.window.deiconify()  # 显示窗口

    def hide_window(self):
        self.window.withdraw()  # 隐藏窗口


class StreamThread(QThread):
    partial_text_signal = pyqtSignal(str)  # 每次接收到部分内容时发送信号

    def __init__(self, messages, selected_option):
        super().__init__()
        self.messages = messages
        self.selected_option = selected_option  # 将选项作为类的属性
        self.config = {}

    def run(self):
        self.config = {}

        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
                self.config = config_data.get("config", {})  # Load keys from config
                print(self.config)

        else:
            # 如果 config.json 不存在，则初始化配置
            self.config = {}

        try:
            if self.selected_option == "百度":
                self.baidu()

            elif self.selected_option == "阿里":
                self.ali()

            elif self.selected_option == "KIMI":
                self.kimi()

            elif self.selected_option == "讯飞":
                self.xunfei()

            elif self.selected_option == "腾讯":
                self.tengxun()

            else:
                select_option = self.selected_option

                # 从配置文件读取
                if os.path.exists("config.json"):
                    with open("config.json", "r", encoding="utf-8") as f:
                        config_data = json.load(f)

                    # 获取自定义项中的所有配置
                    custom_configs = config_data.get('config', {}).get('自定义', {})

                    # 检查当前选择的选项是否在自定义配置中
                    if select_option in custom_configs:
                        selected_config = custom_configs[select_option]
                        base_url = selected_config.get('ACCESS_KEY', '')
                        api_key = selected_config.get('SECRET_KEY', '')
                        selected_model = selected_config.get('MODEL', '')
                    else:
                        # 如果选项不存在，提供默认值或抛出异常
                        print(f"警告: 选项 '{select_option}' 不在自定义配置中！")
                        base_url, api_key, selected_model = '', '', ''
                else:
                    print("错误: 找不到配置文件 'config.json'")
                    base_url, api_key, selected_model = '', '', ''

                # 使用阿里云API调用方法，启用流式输出
                client = OpenAI(
                    api_key=api_key,  # 确保环境变量DASHSCOPE_API_KEY已设置
                    base_url=base_url
                )

                accumulated_text = ""  # 保存当前响应的所有累积内容

                # 调用阿里模型接口，设置stream=True以流式返回
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=self.messages,
                    stream=True  # 启用流式返回
                )

                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        text_part = chunk.choices[0].delta.content
                        accumulated_text += text_part
                        self.partial_text_signal.emit(accumulated_text)

        except Exception as e:
            messagebox.showwarning("警告", f"警告：{e}")

    @acquire_lock(api_lock_baidu)
    def baidu(self):
        # 从配置字典中获取百度 API 的认证信息和模型
        baidu_config = self.config.get('百度', {})
        access_key = baidu_config.get('ACCESS_KEY')
        secret_key = baidu_config.get('SECRET_KEY')
        selected_model = baidu_config.get('MODEL')

        print(f"百度配置：\naccess_key：{access_key}\nsecret_key:{secret_key}\nselected_model:{selected_model}")

        # 使用现有API调用方法
        os.environ["QIANFAN_ACCESS_KEY"] = access_key
        os.environ["QIANFAN_SECRET_KEY"] = secret_key

        # 初始化ERNIE对话接口
        chat_comp = qianfan.ChatCompletion()

        accumulated_text = ""  # 保存当前响应的所有累积内容

        # 调用ERNIE模型接口，设置为流式返回
        response = chat_comp.do(
            model=selected_model,
            messages=self.messages,
            temperature=0.8,
            top_p=0.8,
            stream=True  # 流式返回
        )

        # 逐步处理流式返回的数据块
        for chunk in response:
            text_part = chunk.get("result", "")  # 提取当前数据块的文本部分
            accumulated_text += text_part  # 将新的文本部分累加到总响应中

            # 发射信号，将当前累积的AI响应传递给主线程
            self.partial_text_signal.emit(accumulated_text)

    @acquire_lock(api_lock_ali)
    def ali(self):
        # 从配置字典中获取阿里 API 的认证信息和模型
        ali_config = self.config.get('阿里', {})
        access_key = ali_config.get('ACCESS_KEY')
        api_key = ali_config.get('SECRET_KEY')
        selected_model = ali_config.get('MODEL')

        print(f"阿里配置：\napi_key:{api_key}\nselected_model:{selected_model}")

        # 使用阿里云API调用方法，启用流式输出
        client = OpenAI(
            api_key=api_key,  # 确保环境变量DASHSCOPE_API_KEY已设置
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        accumulated_text = ""  # 保存当前响应的所有累积内容

        # 调用阿里模型接口，设置stream=True以流式返回
        response = client.chat.completions.create(
            model=selected_model,
            messages=self.messages,
            stream=True  # 启用流式返回
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                text_part = chunk.choices[0].delta.content
                accumulated_text += text_part
                self.partial_text_signal.emit(accumulated_text)

    @acquire_lock(api_lock_kimi)
    def kimi(self):
        # 从配置字典中获取kimi API 的认证信息和模型
        kimi_config = self.config.get('KIMI', {})
        access_key = kimi_config.get('ACCESS_KEY')
        api_key = kimi_config.get('SECRET_KEY')
        selected_model = kimi_config.get('MODEL')

        print(f"KIMI配置：\napi_key:{api_key}\nselected_model:{selected_model}")

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1",
        )

        accumulated_text = ""  # 保存当前响应的所有累积内容

        response = client.chat.completions.create(
            model=selected_model,
            messages=self.messages,
            stream=True,
            temperature=0.3,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                text_part = chunk.choices[0].delta.content
                accumulated_text += text_part
                self.partial_text_signal.emit(accumulated_text)

    def xunfei(self):
        # 从配置字典中获取讯飞 API 的认证信息和模型
        xunfei_config = self.config.get('讯飞', {})
        SPARKAI_APP_ID = xunfei_config.get('ACCESS_KEY')
        SPARKAI_API_SECRET = xunfei_config.get('SECRET_KEY')
        SPARKAI_API_KEY = xunfei_config.get('API_KEY')
        SPARKAI_DOMAIN = xunfei_config.get('MODEL')

        print(
            f"讯飞配置：\nAPP_ID：{SPARKAI_APP_ID}\nAPI_SECRET:{SPARKAI_API_SECRET}\nselected_model:{SPARKAI_DOMAIN}")

        # 根据不同模型选择不同的API URL
        SPARKAI_URL = "wss://spark-api.xf-yun.com/chat/pro-128k"  # 默认URL

        if SPARKAI_DOMAIN == "lite":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/v1.1/chat"
        elif SPARKAI_DOMAIN == "generalv3":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/v3.1/chat"
        elif SPARKAI_DOMAIN == "generalv3.5":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/v3.5/chat"
        elif SPARKAI_DOMAIN == "pro-128k":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/chat/pro-128k"
        elif SPARKAI_DOMAIN == "max-32k":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/chat/max-32k"
        elif SPARKAI_DOMAIN == "4.0Ultra":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/v4.0/chat"

        if self.selected_option == "讯飞":
            accumulated_text = "暂不支持讯飞API"
            self.partial_text_signal.emit(accumulated_text)
            return

        """# 生成URL和鉴权
        now = datetime.now()
        date = format_date_time(time.mktime(now.timetuple()))
        host = urlparse(SPARKAI_URL).netloc
        path = urlparse(SPARKAI_URL).path
        signature_origin = "host: " + host + "\n" + "date: " + date + "\n" + "GET " + path + " HTTP/1.1"
        signature_sha = hmac.new(SPARKAI_API_SECRET.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha_base64 = base64.b64encode(signature_sha).decode('utf-8')
        authorization_origin = f'api_key="{SPARKAI_API_KEY}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')

        # 构建请求URL
        url_params = {
            "authorization": authorization,
            "date": date,
            "host": host
        }
        ws_url = SPARKAI_URL + '?' + urlencode(url_params)

        # WebSocket回调函数定义
        def on_error(ws, error):
            print("### error:", error)

        def on_close(ws, close_status_code, close_msg):
            print("WebSocket Closed")

        def on_open(ws):
            thread.start_new_thread(run, (ws,))

        def run(ws):
            # 发送请求的数据
            data = json.dumps({
                "header": {
                    "app_id": SPARKAI_APP_ID,
                    "uid": "1234"
                },
                "parameter": {
                    "chat": {
                        "domain": SPARKAI_DOMAIN,
                        "temperature": 0.8,
                        "max_tokens": 2048,
                        "top_k": 5,
                        "auditing": "default"
                    }
                },

                "payload": {
                    "message": {
                        "text": self.messages  # 用户的消息
                    }
                }
            })
            ws.send(data)

        def on_message(ws, message):
            # 处理返回的消息
            data = json.loads(message)
            code = data['header']['code']
            if code != 0:
                print(f'请求错误: {code}, {data}')
                ws.close()
            else:
                choices = data["payload"]["choices"]
                status = choices["status"]
                content = choices["text"][0]["content"]
                print(content, end="")

                # 通过信号传递文本内容
                self.partial_text_signal.emit(content)
                if status == 2:
                    ws.close()

        # 连接 WebSocket
        websocket.enableTrace(False)
        ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_close=on_close,
                                    on_open=on_open)
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})"""

    def tengxun(self):
        # 从配置字典中获取腾讯 API 的认证信息和模型
        tengxun_config = self.config.get('腾讯', {})
        access_key = tengxun_config.get('ACCESS_KEY')
        secret_key = tengxun_config.get('SECRET_KEY')
        selected_model = tengxun_config.get('MODEL')

        accumulated_text = "暂不支持腾讯API"
        self.partial_text_signal.emit(accumulated_text)


class ChatGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("测试大模型")
        self.resize(1000, 600)  # 调整窗口大小

        # 创建主布局
        main_layout = QHBoxLayout()  # 使用 QHBoxLayout 以便左右并排布局

        # 创建左侧布局的容器
        left_widget = QWidget()  # 创建一个 QWidget 作为左侧布局的容器
        left_layout = QVBoxLayout()  # 使用 QVBoxLayout 以便垂直排列

        # 创建 Qt 下拉框 (self.model_selector)
        self.model_selector = QComboBox()
        self.model_selector.addItems(["百度", "KIMI", "阿里", "腾讯"])  # 初始项
        self.model_selector.setCurrentText("百度")
        left_layout.addWidget(self.model_selector)

        # 绑定鼠标进入事件
        self.model_selector.installEventFilter(self)  # 安装事件过滤器

        # self.safe_refresh_ai_options()

        # 添加新建会话按钮
        self.new_session_button = QPushButton("新建会话")
        self.new_session_button.clicked.connect(self.add_new_session)  # 连接新会话创建
        left_layout.addWidget(self.new_session_button)  # 将按钮添加到左侧布局中

        # 会话列表
        self.session_list = QListWidget()
        self.session_list.addItem("会话 1")  # 默认会话
        self.session_list.currentRowChanged.connect(self.load_session)  # 连接会话切换
        left_layout.addWidget(self.session_list)

        left_widget.setLayout(left_layout)  # 设置左侧布局的容器
        left_widget.setFixedWidth(200)  # 设置容器的固定宽度为200像素

        # 将左侧布局的容器添加到主布局中
        main_layout.addWidget(left_widget)  # 将 left_widget 添加到主布局

        # 创建右侧布局的容器
        right_widget = QWidget()  # 创建一个 QWidget 作为右侧布局的容器
        right_layout = QVBoxLayout()  # 右侧布局使用 QVBoxLayout

        # 显示当前会话名的标签
        self.session_label = QLabel("当前会话: 会话 1")  # 默认会话名
        right_layout.addWidget(self.session_label)

        # 显示对话记录的区域
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        right_layout.addWidget(self.chat_history)

        # 输入栏和发送按钮
        input_layout = QHBoxLayout()  # 输入框和发送按钮使用 QHBoxLayout
        self.user_input = QTextEdit()  # 改为 QTextEdit 来支持多行输入
        self.user_input.setPlaceholderText("在这里输入信息...")
        self.user_input.setMaximumHeight(100)  # 设置最大高度为100像素
        self.user_input.textChanged.connect(self.adjust_input_height)  # 监听文本变化
        input_layout.addWidget(self.user_input)
        self.user_input.setFixedHeight(25)  # 设置新的高度

        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)

        right_layout.addLayout(input_layout)  # 将输入框和发送按钮添加到右侧布局

        right_widget.setLayout(right_layout)  # 设置右侧布局的容器

        # 将右侧布局添加到主布局中
        main_layout.addWidget(right_widget)  # 将 right_widget 添加到主布局

        # 将主布局应用到窗口
        self.setLayout(main_layout)  # 使用主布局

        # 初始对话上下文
        self.messages = []
        self.current_ai_text = ""  # 用于保存当前AI回复的累积内容
        self.current_session_index = 0  # 当前会话索引
        self.sessions = {0: []}  # 存储所有会话，键为会话索引，值为消息列表
        self.is_processing = False  # 添加标志以跟踪是否正在处理AI响应

        # Flag to track if Shift is pressed
        self.shift_pressed = False

    def eventFilter(self, source, event):
        """
        捕获鼠标进入下拉框事件，触发刷新操作。
        """
        if event.type() == QEvent.HoverEnter:  # 使用 HoverEnter 代替 Enter
            if source == self.model_selector:
                self.safe_refresh_ai_options()
        return super().eventFilter(source, event)

    def safe_refresh_ai_options(self):
        """
        确保刷新时使用的配置项是从文件中获取的。
        """
        self.refresh_ai_options()

    def refresh_ai_options(self):
        """
        从配置文件中加载 config 项下的自定义选项，并刷新下拉框选项。
        """
        try:
            # 加载配置文件内容
            with open("config.json", "r", encoding="utf-8") as config_file:
                config_data = json.load(config_file)

            # 从 config 项下的 "自定义" 提取选项
            custom_ai_options = config_data.get("config", {}).get("自定义", {}).keys()
            custom_ai_options = list(custom_ai_options)  # 转换为列表

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"加载配置文件失败: {e}")
            custom_ai_options = []  # 加载失败时使用空列表

        # 清空下拉框并重新添加 "百度", "KIMI", "阿里", "腾讯" 和自定义选项
        self.model_selector.clear()
        self.model_selector.addItems(["百度", "KIMI", "阿里", "讯飞", "腾讯"])

        # 将自定义选项添加到下拉框
        self.model_selector.addItems(custom_ai_options)

    def keyPressEvent(self, event: QEvent):
        """捕获按键事件，处理 Shift+Enter 和 Enter 键的功能"""
        if event.key() == Qt.Key_Return:
            self.shift_pressed = True
            if self.shift_pressed:
                # Shift + Enter: 触发发送消息
                self.send_message()
                event.accept()  # 阻止默认行为（不插入换行符）
            else:
                # 只有 Enter 键时，允许输入换行
                event.ignore()  # 让 QTextEdit 处理换行符
        else:
            # 处理其他按键的事件
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QEvent):
        """捕获松开 Shift 键事件，恢复 Enter 键的换行功能"""
        if event.key() == Qt.Key_Shift:
            self.shift_pressed = False  # 松开 Shift 键时，恢复默认行为
        else:
            super().keyReleaseEvent(event)

    def adjust_input_height(self):
        """根据文本内容自动调整输入框的高度，最大高度为100像素"""
        try:
            document_height = self.user_input.document().size().height()
            new_height = min(int(document_height), 100)  # 确保高度是整数
            self.user_input.setFixedHeight(new_height)  # 设置新的高度
        except Exception as e:
            print(f"Error adjusting input height: {e}")  # 打印错误信息

    def send_message(self):
        user_text = self.user_input.toPlainText().strip()
        if not user_text:
            return  # 忽略空消息

        if self.is_processing:
            return  # 如果正在处理AI响应，则不允许发送新消息

        # 将用户消息添加到当前会话的消息记录中
        self.messages.append({"role": "user", "content": user_text})
        # 使用 HTML 格式设置用户消息的显示，保留换行符
        formatted_text = user_text.replace('\n', '<br>')
        self.chat_history.append(f"<b><span style='color:green; font-size:14pt;'>User:</span></b> {formatted_text}")
        self.user_input.clear()

        # 获取下拉栏选择的选项
        selected_option = self.model_selector.currentText()

        # 开始新的流式线程以接收AI逐步响应
        self.current_ai_text = ""  # 每次新响应前清空当前AI回复
        self.is_processing = True  # 设置为正在处理状态
        self.stream_thread = StreamThread(self.messages, selected_option)
        self.stream_thread.partial_text_signal.connect(self.update_ai_response)  # 连接信号
        self.stream_thread.finished.connect(self.reset_processing_state)  # 连接线程完成信号
        self.stream_thread.start()

    def reset_processing_state(self):
        # AI响应完成后重置处理状态
        self.is_processing = False

    def update_ai_response(self, text):
        try:
            # 清除之前的 AI 回复内容，只保留用户消息和其他 AI 回复
            history_lines = self.chat_history.toPlainText().splitlines()
            print(history_lines)

            # 检查是否存在最后一条 AI 消息
            if self.current_ai_text:
                # 找到最后一行 AI 回复的行号
                last_ai_index = -1
                for i in range(len(history_lines) - 1, -1, -1):
                    if history_lines[i].startswith("AI:"):
                        last_ai_index = i
                        break

                # 只保留用户消息和之前的 AI 消息，清除最后一次 AI 回复
                if last_ai_index != -1:
                    cleaned_history = history_lines[:last_ai_index]  # 清除最后一条 AI 回复
                else:
                    cleaned_history = history_lines  # 如果没有找到AI消息，保留全部历史

                # 使用 HTML 格式更新聊天历史
                formatted_history = []
                for line in cleaned_history:
                    # 处理以 ### 开头的行
                    if line.startswith("###"):
                        line_content = line[3:]  # 去掉前面的 ###
                        formatted_history.append(f"<b><span style='font-size:16pt;'>{line_content}</span></b>")
                    else:
                        # 处理被 ** 括起来的内容
                        parts = line.split("**")  # 分割内容
                        formatted_line = ""
                        for i, part in enumerate(parts):
                            if i % 2 == 1:  # 如果是括起来的内容
                                formatted_line += f"<b>{part}</b>"  # 加粗内容
                            else:
                                formatted_line += part  # 其他内容保持原样
                        if line.startswith("User:"):
                            formatted_history.append(
                                f"<b><span style='color:green; font-size:14pt;'>User:</span></b> {formatted_line[6:]}")
                        elif line.startswith("AI:"):
                            formatted_history.append(
                                f"<b><span style='color:red; font-size:14pt;'>AI:</span></b> {formatted_line[4:]}")
                        else:
                            formatted_history.append(formatted_line)  # 保持其他文本不变

                self.chat_history.setHtml("<br>".join(formatted_history))

            # 使用 HTML 格式设置 AI 的响应，保留换行符
            formatted_text = text.replace('\n', '<br>')  # 保留AI响应的换行符
            formatted_text_parts = formatted_text.split("**")

            # 对AI响应进行格式处理
            processed_ai_response = ""
            for i, part in enumerate(formatted_text_parts):
                if i % 2 == 1:  # 如果是被**括起来的内容
                    processed_ai_response += f"<b>{part}</b>"  # 加粗内容
                else:
                    processed_ai_response += part  # 其他内容保持原样

            self.chat_history.append(
                f"<b><span style='color:red; font-size:14pt;'>AI:</span></b> {processed_ai_response}")

            # 更新最新的AI消息内容在对话上下文中
            self.current_ai_text = text
            # 更新消息上下文
            if self.messages and self.messages[-1]["role"] == "assistant":
                self.messages[-1]["content"] = self.current_ai_text
            else:
                self.messages.append({"role": "assistant", "content": self.current_ai_text})

            # 滚动到底部以显示最新内容
            self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())

        except Exception as e:
            print(f"An error occurred: {e}")

    def load_session(self, index):
        if self.is_processing:
            return  # 如果正在处理AI响应，则不允许切换会话

        # 保存当前会话的聊天记录
        if self.current_session_index >= 0:
            self.sessions[self.current_session_index] = self.messages  # 保存当前会话的消息记录

        # 加载选定的会话
        self.current_session_index = index
        self.messages = self.sessions.get(index, [])  # 获取当前会话的消息记录
        self.chat_history.clear()  # 清空聊天历史记录

        # 重新加载会话记录并应用 HTML 样式，保留换行符
        for msg in self.messages:
            color = "green" if msg['role'] == "user" else "red"
            name = "User" if msg['role'] == "user" else "AI"
            formatted_text = msg['content'].replace('\n', '<br>')  # 保留换行符
            self.chat_history.append(
                f"<b><span style='color:{color}; font-size:14pt;'>{name}:</span></b> {formatted_text}")

        # 更新会话名称标签
        self.session_label.setText(f"当前会话: 会话 {self.current_session_index + 1}")

    def add_new_session(self):
        if self.is_processing:
            return  # 如果正在处理AI响应，则不允许新建会话

        # 新建会话
        new_index = len(self.sessions)  # 新会话的索引
        self.sessions[new_index] = []  # 为新会话创建消息列表
        self.session_list.addItem(f"会话 {new_index + 1}")  # 在会话列表中添加新会话
        self.session_list.setCurrentRow(new_index)  # 切换到新会话

        # 清空当前对话
        self.messages = []
        self.chat_history.clear()

        # 更新会话名称标签
        self.session_label.setText(f"当前会话: 会话 {new_index + 1}")


class TextPreprocessor:
    def __init__(self, parent, start_menu):
        self.parent = parent
        self.folder_path_var = start_menu.folder_path_var
        self.text_file_path_var = start_menu.text_file_path_var
        self.project_name = start_menu.project_name_combobox
        self.dialogue_done_event = threading.Event()
        print(self.text_file_path_var.get())

        # 初始化任务参数
        self.total_tasks = 0  # 总任务量
        self.current_task = 0  # 当前任务量
        self.start_time = None  # 任务开始时间
        self.progress_bar_done = True

        # 保存 StartMenu 的配置引用
        self.config = start_menu.config

        # 创建字典来保存各章节的内容
        self.chapter_contents = {}  # 原文内容
        self.chapter_marked_contents = {}  # 标记后的内容

        # 设置整体布局
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)

        # 创建左右两个 frame
        self.left_frame = tk.Frame(self.parent)
        self.left_frame.grid(row=0, column=0, sticky="nsew")
        self.right_frame = tk.Frame(self.parent, width=300)
        self.right_frame.grid(row=0, column=1, sticky="ns")
        self.right_frame.grid_propagate(False)
        self.parent.grid_columnconfigure(0, weight=1)

        # 进度条行
        self.bottom_frame = tk.Frame(self.parent)
        self.bottom_frame.grid(row=1, column=0, pady=10, columnspan=2, sticky="nsew")

        # 创建进度百分比标签
        self.progress_percentage_label = tk.Label(self.bottom_frame, text="进度: 0%")
        self.progress_percentage_label.pack(side=tk.LEFT, padx=5)

        # 创建进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.bottom_frame, variable=self.progress_var, maximum=100, length=300)
        self.progress_bar.pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)

        # 创建时间显示标签
        self.time_label = tk.Label(self.bottom_frame, text="运行时间|剩余时间: 00:00:00|00:00:00")
        self.time_label.pack(side=tk.LEFT, padx=1)

        # 一键处理
        self.one_click_process = tk.Button(self.bottom_frame, text="一键处理", command=self.run_process_all)
        self.one_click_process.pack(side=tk.LEFT, padx=10)

        # 绑定窗口大小变化事件
        # self.parent.bind("<Configure>", self.on_window_resize)

        # 在 left_frame 中创建文本框
        self.left_frame.grid_rowconfigure(0, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.text_box = scrolledtext.ScrolledText(self.left_frame, wrap="word")
        self.text_box.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # 在 right_frame 中创建选择章节下拉框和滚动画布
        self.right_frame.grid_rowconfigure(3, weight=1)

        # 标签栏
        self.Label_frame = tk.Frame(self.right_frame)
        self.Label_frame.grid(row=0, column=0, sticky="nsew")

        # 章节选择标签和下拉框
        self.chapter_label = tk.Label(self.Label_frame, text="选择章节：")
        self.chapter_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.chapter_combobox = ttk.Combobox(self.right_frame)
        self.chapter_combobox.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.chapter_combobox["values"] = ["全文", "新建章节"]  # 初始选项
        self.chapter_combobox.bind("<<ComboboxSelected>>", self.display_selected_content)

        # 设置默认选中项为“全文”
        self.chapter_combobox.set("全文")

        # 占位
        self.blank_label3 = tk.Frame(self.Label_frame, width=41)
        self.blank_label3.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # 显示标记复选框
        self.show_marked_var = tk.BooleanVar()
        self.show_marked_checkbox = tk.Checkbutton(
            self.Label_frame, text="显示已标记内容", variable=self.show_marked_var,
            command=self.display_selected_content
        )
        self.show_marked_checkbox.grid(row=0, column=2, pady=5, sticky="w")

        # 处理章节行
        self.chapter_frame = tk.Frame(self.right_frame)
        self.chapter_frame.grid(row=2, column=0, sticky="ew")

        # 章节处理选项
        self.chapter_config_label = tk.Label(self.chapter_frame, text="处理章节：")
        self.chapter_config_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        # 占位
        self.blank_label = tk.Frame(self.chapter_frame, width=15)
        self.blank_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # 删除按钮
        self.delete_chapter_button = tk.Button(self.chapter_frame, text="删除", command=self.delete_chapter)
        self.delete_chapter_button.grid(row=0, column=2, padx=5, pady=5)

        # 保存按钮
        self.save_chapter_button = tk.Button(self.chapter_frame, text="保存", command=self.save_content)
        self.save_chapter_button.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        # 刷新按钮
        self.chapter_refresh_button = tk.Button(self.chapter_frame, text="刷新", command=self.refresh_and_update)
        self.chapter_refresh_button.grid(row=0, column=4, padx=5, sticky="e")

        # 滚动画布
        self.canvas = tk.Canvas(self.right_frame, highlightthickness=0, bd=2, relief="groove")
        self.canvas.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)

        # 在 Canvas 中创建一个 frame，用于放置控件
        self.canvas_frame = tk.Frame(self.canvas, width=170)
        self.canvas_frame.bind("<Configure>", self.update_scroll_region)
        self.canvas.create_window((4, 5), window=self.canvas_frame, anchor="nw")  # 设置 x, y 坐标为 (2, 2) 以避免遮挡

        # 选择AI行
        # self.select_AI_frame = tk.Frame(self.canvas_frame)
        # self.select_AI_frame.grid(row=11, column=0, sticky="nsew")

        # 选择AI行
        self.select_AI_label = tk.Label(self.canvas_frame, text="选择AI：")
        self.select_AI_label.grid(row=9, column=0, padx=5, pady=5, sticky="w")

        self.select_AI_frame = tk.Frame(self.canvas_frame)
        self.select_AI_frame.grid(row=9, column=1, sticky="w")
        self.select_AI_var = tk.StringVar()
        self.select_AI = ttk.Combobox(self.select_AI_frame, textvariable=self.select_AI_var, width=11, state="readonly")

        # 初始化AI选择列表，默认值为 ["百度", "KIMI", "阿里", "腾讯", "更多"]
        self.default_ai_options = ["百度", "KIMI", "阿里", "讯飞", "腾讯", "更多"]
        self.refresh_ai_options()  # 初始刷新一次选项

        self.select_AI.set("百度")  # 默认选中百度
        self.select_AI.grid(row=0, column=0, padx=4, pady=5, sticky="w")
        self.select_AI.bind("<<ComboboxSelected>>", self.on_pattern_select)

        # 绑定鼠标进入事件，悬停时刷新选项
        self.select_AI.bind("<Enter>", lambda event: self.refresh_ai_options())

        # 使用 Toplevel 创建顶层提示框窗口，确保提示信息不会被遮挡
        self.tooltip = tk.Toplevel(self.canvas_frame)
        self.tooltip.overrideredirect(True)  # 去除窗口边框
        self.tooltip.withdraw()  # 初始隐藏
        self.tooltip_label = tk.Label(self.tooltip, text="", bg="white", fg="black")
        self.tooltip_label.pack()

        # 复制按钮（默认隐藏）
        self.custom_copy_button = tk.Button(self.canvas_frame, text="复制", command=self.copy_text)
        self.custom_copy_button.grid(row=10, column=0, padx=5, pady=5, sticky="w")
        self.custom_copy_button.grid_remove()

        # 更多模式文本框（默认隐藏）
        self.more_AI_entry = tk.Entry(self.canvas_frame, width=13)
        self.more_AI_entry.grid(row=10, column=1, padx=5, pady=5, sticky='w')
        self.more_AI_entry.grid_remove()

        # 绑定鼠标悬停和移动事件到 more_AI_entry
        self.more_AI_entry.bind("<Enter>", self.show_tooltip)
        self.more_AI_entry.bind("<Motion>", self.follow_mouse)
        self.more_AI_entry.bind("<Leave>", self.hide_tooltip)

        # 标注比例阈值行
        self.threshold_frame = tk.Frame(self.canvas_frame)
        self.threshold_frame.grid(row=11, column=1, padx=5, sticky="nsew")

        # 阈值输入框
        self.threshold_label = tk.Label(self.canvas_frame, text="标注比例阈值：")
        self.threshold_label.grid(row=11, column=0, pady=5, padx=5, sticky="w")
        self.threshold_entry = tk.Entry(self.threshold_frame, width=11)
        self.threshold_entry.insert(0, "95")
        self.threshold_entry.grid(row=0, column=0, pady=5, sticky="w")
        self.threshold_label_mark = tk.Label(self.threshold_frame, text="%")
        self.threshold_label_mark.grid(row=0, column=1, sticky="w")

        # 最大重试次数行
        # self.retry_frame = tk.Frame(self.canvas_frame)
        # self.retry_frame.grid(row=10, column=0, sticky="nsew")

        # 最大重试次数输入框
        self.retry_label = tk.Label(self.canvas_frame, text="最大重试次数：")
        self.retry_label.grid(row=12, column=0, padx=5, pady=5, sticky="w")
        self.retry_entry = tk.Entry(self.canvas_frame, width=13)
        self.retry_entry.insert(0, "5")  # 设置默认值为5
        self.retry_entry.grid(row=12, column=1, padx=5, pady=5, sticky="w")

        # 单次请求字数上限
        self.text_limit_label = tk.Label(self.canvas_frame, text="单轮最大字数:")
        self.text_limit_label.grid(row=13, column=0, padx=5, pady=5, sticky="w")
        self.text_limit_entry = tk.Entry(self.canvas_frame, width=13)
        self.text_limit_entry.grid(row=13, column=1, padx=5, pady=5, sticky="w")
        self.text_limit_entry.insert(0, "8500")

        # 处理按钮行
        self.process_button_frame = tk.Frame(self.canvas_frame)
        self.process_button_frame.grid(row=16, column=0, columnspan=3, sticky="nsew")

        # 创建处理按钮
        self.process_button = tk.Button(self.canvas_frame, text="标注角色对话", command=self.run_process_dialogue)
        self.process_button.grid(row=16, column=0, padx=5, pady=5, sticky="nw")

        # 补充缺失角色
        # self.fill_missing_role = tk.Checkbutton(self.canvas_frame,text="补充缺失角色")
        # self.fill_missing_role.grid(row=15, column=1, padx=5, pady=5, sticky="w")

        # 处理选项列
        self.process_frame = tk.Frame(self.canvas_frame)
        self.process_frame.grid(row=16, column=1, padx=5, pady=5, sticky="e")

        # 联系上下文
        self.contextualize_output_var = tk.BooleanVar()
        self.contextualize_output_frame = tk.Frame(self.process_frame, height=16, width=105)  # 设置Frame高度和宽度
        self.contextualize_output_frame.grid(row=0, column=0, sticky="e")
        self.contextualize_output_frame.grid_propagate(False)
        self.contextualize_output_checkbox = tk.Checkbutton(
            self.contextualize_output_frame, text="联系上下文", variable=self.contextualize_output_var
        )
        self.contextualize_output_checkbox.place(x=0, y=0, height=15, width=100)  # 设置绝对高度和宽度

        # 按章节生成
        self.process_by_chapter_var = tk.BooleanVar(value=True)
        self.process_by_chapter_frame = tk.Frame(self.process_frame, height=16, width=105)  # 设置Frame高度和宽度
        self.process_by_chapter_frame.grid(row=1, column=0, sticky="e")
        self.process_by_chapter_frame.grid_propagate(False)
        self.process_by_chapter = tk.Checkbutton(
            self.process_by_chapter_frame, text="按章节标注", variable=self.process_by_chapter_var
        )
        self.process_by_chapter.place(x=0, y=0, height=15, width=100)  # 设置绝对高度和宽度

        # 分隔符
        self.part4 = tk.Label(self.canvas_frame, text="————————————————")
        self.part4.grid(row=17, column=0, columnspan=2, sticky="w")

        # 添加滚动条
        self.scrollbar = tk.Scrollbar(self.right_frame, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=3, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # 配置 right_frame 的列，以便 canvas 和 scrollbar 并列显示
        self.right_frame.grid_columnconfigure(0, weight=1)

        # 加载文档内容
        self.load_text_file()

        self.update_chapter_list()

        # 创建 DialogueFormatter 实例
        self.dialogue_formatter = DialogueFormatter(self.text_box, self, self.config)

        # 实例化 ChangeFormat 和 ChapterSplitterApp，并在 canvas_frame 中添加其控件
        self.change_format_app = ChangeFormat(self.canvas_frame, self.text_box, self)
        # self.change_format_app.create_controls()

        self.chapter_splitter_app = ChapterSplitterApp(self.canvas_frame, self)

        # 创建 DocumentProcessorApp 并添加到 canvas_frame
        self.document_processor_app = DocumentProcessorApp(self.canvas_frame, self)

        # 绑定鼠标滚轮事件（支持 Windows 和 macOS）
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
        self.canvas.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
        self.canvas.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动
        self.canvas_frame.bind("<MouseWheel>", self._on_mouse_wheel)  # 将滚轮事件绑定到 canvas_frame
        self.canvas_frame.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
        self.canvas_frame.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动
        self.select_AI_label.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
        self.select_AI_label.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
        self.select_AI_label.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

        # 将 self.threshold_frame 和 self.retry_frame 中的所有控件绑定鼠标滚轮事件
        for widget in self.threshold_frame.winfo_children():
            widget.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
            widget.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
            widget.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

        for widget in self.process_button_frame.winfo_children():
            widget.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
            widget.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
            widget.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

        for widget in self.canvas_frame.winfo_children():
            widget.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows
            widget.bind("<Button-4>", self._on_mouse_wheel)  # macOS 向上滚动
            widget.bind("<Button-5>", self._on_mouse_wheel)  # macOS 向下滚动

        # 创建所有角色的示例列表（可以根据实际情况获取）
        self.all_characters = []

        # 创建 CharacterExtractor 实例并初始化 UI
        self.character_extractor = CharacterExtractor(self, self.all_characters)

        # 直接调用 VoiceGeneratorApp 的 load_folders 方法
        voice_generator_app.load_folders()  # 这里调用已经实例化的 voice_generator_app

    def delete_chapter(self):
        # 获取当前选中的章节名称
        selected_chapter = self.chapter_combobox.get()

        # 判断是否选择了有效的章节（排除 "全文" 和 "新建章节"）
        if selected_chapter in ["全文", "新建章节"]:
            messagebox.showwarning("删除失败", "请选择一个有效的章节进行删除！")
            return

        # 获取文件夹路径
        folder_path = self.folder_path_var.get()

        # 构造两个文件的路径
        chapter_file_path = os.path.join(folder_path, "Chapters", f"{selected_chapter}.txt")
        marked_chapter_file_path = os.path.join(folder_path, "Chapters_marked", f"{selected_chapter}_marked.txt")

        # 删除文件的函数
        def delete_file(file_path):
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"删除文件: {file_path}")
                except Exception as e:
                    messagebox.showerror("删除失败", f"删除文件 {file_path} 时发生错误: {e}")
            else:
                print(f"文件 {file_path} 不存在。")

        # 删除章节文件和标记文件
        delete_file(chapter_file_path)
        delete_file(marked_chapter_file_path)

        # 更新界面提示
        messagebox.showinfo("删除成功", f"章节 '{selected_chapter}' 的相关文件已成功删除。")

        # 重新更新章节列表（如果需要的话）
        self.refresh_and_update()

        # 自动选择“全文”
        self.chapter_combobox.set("全文")
        # time.sleep(1)
        self.display_selected_content()

    def refresh_ai_options(self):
        """
        从配置文件中加载 config 项下的自定义选项，并刷新下拉框选项。
        """
        # print("刷新")
        try:
            # 加载配置文件内容
            with open("config.json", "r", encoding="utf-8") as config_file:
                config_data = json.load(config_file)

            # 从 config 项下的 "自定义" 提取选项
            custom_ai_options = config_data.get("config", {}).get("自定义", {}).keys()
            custom_ai_options = list(custom_ai_options)  # 转换为列表

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"加载配置文件失败: {e}")
            custom_ai_options = []  # 加载失败时使用空列表

        # 在“腾讯”和“更多”之间插入自定义选项
        insert_index = self.default_ai_options.index("更多")
        updated_options = (
                self.default_ai_options[:insert_index] + custom_ai_options + self.default_ai_options[insert_index:]
        )

        # 检查当前选项是否需要重置
        current_selection = self.select_AI.get()  # 当前选中的选项
        self.select_AI['values'] = updated_options  # 更新下拉列表选项

        # 如果当前选中项仍然有效，保留选中；否则设置默认选中值
        if current_selection not in updated_options:
            self.select_AI.set("百度")  # 设置默认选项

    def copy_text(self):
        head = "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"
        content = head + self.text_box.get("1.0", "end-1c")
        print(content)
        pyperclip.copy(content)

    def show_tooltip(self, event):
        """显示提示框"""
        self.tooltip_label.config(
            text="1.点击“复制”按钮将复制的内容粘贴到任意外部AI\n2.将AI回答的内容粘贴到此文本框                         \n3.点击“标注角色对话”按钮                                     ")
        self.tooltip.deiconify()  # 显示 tooltip
        self.update_tooltip_position(event)

    def follow_mouse(self, event):
        """更新提示框位置以跟随鼠标"""
        self.update_tooltip_position(event)

    def hide_tooltip(self, event):
        """隐藏提示框"""
        self.tooltip.withdraw()  # 隐藏 tooltip

    def update_tooltip_position(self, event):
        """更新提示框位置并确保不会被遮挡"""
        # 获取鼠标在父窗口中的位置
        x = event.x_root + 10  # 鼠标右下方偏移
        y = event.y_root + 20

        # 获取屏幕宽高，避免 tooltip 超出显示范围
        screen_width = self.canvas_frame.winfo_screenwidth()
        screen_height = self.canvas_frame.winfo_screenheight()

        # 调整位置，避免超出屏幕右边或底部
        tooltip_width = self.tooltip.winfo_reqwidth()
        tooltip_height = self.tooltip.winfo_reqheight()
        if x + tooltip_width > screen_width:
            x = screen_width - tooltip_width - 10
        if y + tooltip_height > screen_height:
            y = screen_height - tooltip_height - 10

        # 移动提示框到新的位置
        self.tooltip.geometry(f"+{x}+{y}")

    def on_pattern_select(self, event):
        """处理下拉栏选项的选择"""
        selected_pattern = self.select_AI.get()
        if selected_pattern == "更多":
            self.more_AI_entry.grid()  # 显示自定义文本框
            self.custom_copy_button.grid()
        else:
            self.more_AI_entry.grid_remove()  # 隐藏自定义文本框
            self.custom_copy_button.grid_remove()

    def run_process_all(self):
        threading.Thread(target=self.process_all).start()

    def process_all(self):
        self.chapter_combobox.set("全文")
        self.display_selected_content()

        # 保存 combobox 当前状态
        original_state = self.chapter_combobox.cget("state")

        # 禁用 combobox
        self.chapter_combobox.configure(state="disabled")

        # 获取所有控件（包括嵌套的）
        controls = []
        for control in self.canvas_frame.winfo_children():
            controls.append(control)
            if control.winfo_children():  # 如果控件本身有子控件（如Frame等）
                controls.extend(control.winfo_children())  # 扩展到列表中

        # 显式将这两个控件添加到 controls 中
        controls.append(self.contextualize_output_checkbox)
        controls.append(self.process_by_chapter)
        controls.append(self.delete_chapter_button)
        controls.append(self.chapter_refresh_button)

        # 存储控件的原始状态
        original_states = {}

        for control in controls:
            # 特别处理这两个控件
            if control == self.contextualize_output_checkbox:
                original_states[control] = control.cget("state")  # 获取原始状态
                control.config(state="disabled")  # 禁用控件
            elif control == self.process_by_chapter:
                original_states[control] = control.cget("state")  # 获取原始状态
                control.config(state="disabled")  # 禁用控件
            # 处理其他控件
            elif isinstance(control, tk.Entry):
                original_states[control] = control.cget("state")  # 获取原始状态
                control.config(state="disabled")  # 禁用控件
            elif isinstance(control, tk.Button):
                original_states[control] = control.cget("state")
                control.config(state="disabled")
            elif isinstance(control, ttk.Combobox):
                original_states[control] = control["state"]
                control.config(state="disabled")
            elif isinstance(control, tk.Checkbutton):
                original_states[control] = control.cget("state")
                control.config(state="disabled")
            elif isinstance(control, tk.OptionMenu):
                original_states[control] = control.cget("state")
                control.config(state="disabled")

        # 自动更改为显示未标注章节
        self.show_marked_checkbox.deselect()
        self.display_selected_content()
        self.show_marked_checkbox.configure(state="disabled")
        # 进度条初始化
        self.progress_bar_done = False
        self.current_task = 0  # 当前任务量
        self.start_time = time.time()  # 任务开始时间初始化为当前时间
        # 重置进度条和百分比标签
        self.progress_bar['value'] = 0  # 重置进度条
        self.progress_percentage_label.config(text="进度: 0%")  # 重置进度百分比
        self.total_tasks = 5
        self.update_progress()  # 更新进度条显示

        # 格式转换
        self.change_format_app.process_text()

        # 自动分章
        self.chapter_splitter_app.split_chapters()

        # 自动标记
        self.process_dialogue(original_state, controls, original_states)

        # self.current_task += 1
        # self.progress_bar_done = True
        # self.update_progress()  # 更新进度条显示

    def update_progress(self):
        # 强制完成进度条
        if self.progress_bar_done:
            self.current_task = self.total_tasks

        # 确保当前任务量不会超过总任务量
        if self.current_task > self.total_tasks:
            return

        # 计算进度百分比
        progress_percentage = (self.current_task / self.total_tasks) * 100
        self.progress_var.set(progress_percentage)
        self.progress_percentage_label.config(text=f"进度: {int(progress_percentage)}%")

        # 计算运行时间
        elapsed_time = time.time() - self.start_time
        remaining_time = (elapsed_time / self.current_task) * (
                self.total_tasks - self.current_task) if self.current_task > 0 else 0

        # 格式化时间显示
        elapsed_time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
        remaining_time_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))

        # 更新时间标签
        self.time_label.config(text=f"运行时间|剩余时间: {elapsed_time_str}|{remaining_time_str}")

        # 如果当前任务未完成，继续每秒更新进度
        if self.current_task < self.total_tasks:
            self.parent.after(1000, self.update_progress)

    def on_window_resize(self, event):
        """
        当窗口大小变化时，调整进度条的长度以适应新的窗口宽度
        """
        # 获取窗口当前的宽度
        window_width = event.width

        # 设置进度条的长度为窗口宽度减去一定的边距（例如10px）
        new_length = window_width - 300  # 可以根据需要调整边距

        # 更新进度条的长度
        self.progress_bar.config(length=new_length)

    def save_content(self):
        """保存文本框内容到文本文档，并通过更新章节列表来保存到字典中"""
        # 获取当前选择的章节和文本框内容
        selected_chapter = self.chapter_combobox.get()
        content_to_save = self.text_box.get("1.0", tk.END).strip()

        # 如果名称为空，则不执行操作
        if not selected_chapter:
            messagebox.showwarning("警告", "请输入章节名称!")
            return

        if selected_chapter == "新建章节":
            messagebox.showwarning("警告", "请修改章节名称！")
            return

        # 判断复选框状态：保存原文或标记内容
        is_marked = self.show_marked_var.get()

        # 如果选择的是全文
        if selected_chapter == "全文":
            # 保存全文到对应的字典和文件夹
            if is_marked:
                self.chapter_marked_contents[0] = content_to_save
                folder = os.path.join(self.folder_path_var.get(), "Chapters_marked")
                file_name = f"{self.project_name.get()} 全文_marked.txt"
            else:
                self.chapter_contents[0] = content_to_save
                file_path_full = self.text_file_path_var.get()
                folder = os.path.dirname(file_path_full)
                file_name = os.path.basename(file_path_full)
        elif selected_chapter == "新建章节":
            print("无法保存至'新建章节'，请选择具体章节重命名章节名")
            return
        else:
            # 如果选中的章节名称不在章节列表中，说明是新章节
            if selected_chapter not in self.chapter_combobox["values"]:
                print(f"章节 '{selected_chapter}' 不在现有章节中，创建新章节并保存。")
                # 新章节名直接作为文件名保存
                chapter_index = len(self.chapter_combobox["values"])  # 新章节的索引在现有章节列表末尾
                chapter_options = list(self.chapter_combobox["values"])  # 现有章节列表
                chapter_options.append(selected_chapter)  # 将新章节名称加入列表
                self.chapter_combobox["values"] = chapter_options  # 更新下拉栏选项

                # 保存新章节内容
                if is_marked:
                    self.chapter_marked_contents[chapter_index] = content_to_save
                    folder = os.path.join(self.folder_path_var.get(), "Chapters_marked")
                    file_name = f"{selected_chapter}_marked.txt"
                else:
                    self.chapter_contents[chapter_index] = content_to_save
                    folder = os.path.join(self.folder_path_var.get(), "Chapters")
                    file_name = f"{selected_chapter}.txt"

            else:
                # 章节名称在下拉栏中，保存内容到相应章节
                chapter_index = list(self.chapter_combobox["values"]).index(selected_chapter)
                if is_marked:
                    self.chapter_marked_contents[chapter_index] = content_to_save
                    folder = os.path.join(self.folder_path_var.get(), "Chapters_marked")
                    file_name = f"{selected_chapter}_marked.txt"
                else:
                    self.chapter_contents[chapter_index] = content_to_save
                    folder = os.path.join(self.folder_path_var.get(), "Chapters")
                    file_name = f"{selected_chapter}.txt"

        # 创建文件夹并保存文件
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, file_name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content_to_save)

        print(f"内容已保存至：{file_path}")

        # 更新章节列表，重新加载章节字典和下拉框
        self.update_chapter_list()

    def refresh_and_update(self):
        """刷新章节列表并执行 ChangeFormat 中的 auto_set_replace_quotes 函数"""
        self.update_chapter_list()  # 更新章节列表
        self.change_format_app.auto_set_replace_quotes()  # 调用 ChangeFormat 中的函数
        # 调用 CharacterExtractor 的更新方法
        self.character_extractor.create_character_display()

    def run_process_dialogue(self):
        # 保存 combobox 当前状态
        original_state = self.chapter_combobox.cget("state")

        # 禁用 combobox
        self.chapter_combobox.configure(state="disabled")

        # 获取所有控件（包括嵌套的）
        controls = []
        for control in self.canvas_frame.winfo_children():
            controls.append(control)
            if control.winfo_children():  # 如果控件本身有子控件（如Frame等）
                controls.extend(control.winfo_children())  # 扩展到列表中

        # 显式将这两个控件添加到 controls 中
        controls.append(self.contextualize_output_checkbox)
        controls.append(self.process_by_chapter)
        controls.append(self.delete_chapter_button)
        controls.append(self.chapter_refresh_button)

        # 存储控件的原始状态
        original_states = {}

        for control in controls:
            # 特别处理这两个控件
            if control == self.contextualize_output_checkbox:
                original_states[control] = control.cget("state")  # 获取原始状态
                control.config(state="disabled")  # 禁用控件
            elif control == self.process_by_chapter:
                original_states[control] = control.cget("state")  # 获取原始状态
                control.config(state="disabled")  # 禁用控件
            # 处理其他控件
            elif isinstance(control, tk.Entry):
                original_states[control] = control.cget("state")  # 获取原始状态
                control.config(state="disabled")  # 禁用控件
            elif isinstance(control, tk.Button):
                original_states[control] = control.cget("state")
                control.config(state="disabled")
            elif isinstance(control, ttk.Combobox):
                original_states[control] = control["state"]
                control.config(state="disabled")
            elif isinstance(control, tk.Checkbutton):
                original_states[control] = control.cget("state")
                control.config(state="disabled")
            elif isinstance(control, tk.OptionMenu):
                original_states[control] = control.cget("state")
                control.config(state="disabled")

        # 自动更改为显示未标注章节
        self.show_marked_checkbox.deselect()
        self.display_selected_content()
        self.show_marked_checkbox.configure(state="disabled")
        # 进度条初始化
        self.progress_bar_done = False
        self.current_task = 0  # 当前任务量
        self.start_time = time.time()  # 任务开始时间初始化为当前时间
        # 重置进度条和百分比标签
        self.progress_bar['value'] = 0  # 重置进度条
        self.progress_percentage_label.config(text="进度: 0%")  # 重置进度百分比
        self.total_tasks = int(self.retry_entry.get())
        self.update_progress()  # 更新进度条显示

        threading.Thread(target=lambda: self.process_dialogue(original_state, controls, original_states)).start()

    def process_dialogue(self, original_state, controls, original_states):
        selected_chapter = self.chapter_combobox.get()
        # 获取最大重试次数
        try:
            max_retries = int(self.retry_entry.get())
        except ValueError:
            self.progress_bar_done = True
            messagebox.showwarning("警告", "最大重试次数应为整数")
            return

        # 根据选择章节的不同，设置 self.total_tasks
        if selected_chapter == "全文":
            # 章节数量加1，避免“全文”选项占用
            chapter_count = len(self.chapter_contents) - 1
            print(f"重试{max_retries}*章节数{chapter_count}")
            self.total_tasks = max_retries * chapter_count + 1
        else:
            self.total_tasks = max_retries + 1

        print(f"任务量：{self.total_tasks}")

        if selected_chapter == "全文" and not self.process_by_chapter_var.get():
            try:
                # 单独处理当前选择的章节
                chapter_index = list(self.chapter_combobox["values"]).index(selected_chapter)

                # 获取全文内容
                chapter_text = self.text_box.get("1.0", tk.END).strip()
                # chapter_text = self.chapter_contents.get(chapter_index, "")
                self.dialogue_done_event.clear()

                # 将全文内容发送到格式化函数处理
                actual_retries = self.dialogue_formatter.format_dialogue(chapter_text, self.dialogue_done_event,
                                                                         chapter_index)

                # 处理完成后的后续操作，与处理单章节的操作相同
                self.update_progress()
                self.dialogue_done_event.wait()
                self.show_marked_checkbox.select()  # 自动勾选复选框
                self.display_selected_content()
                self.document_processor_app.process_document(update_pg=True)
                return  # 提前结束函数，避免重复处理

            except ValueError as e:
                self.progress_bar_done = True
                messagebox.showwarning("警告", f"警告：{e}")

        if selected_chapter == "全文":
            try:
                # 批量处理每个章节
                for chapter_index, chapter_text in self.chapter_contents.items():
                    if chapter_index != 0:  # 跳过“全文”
                        self.dialogue_done_event.clear()

                        # 增加一个变量来记录实际重试次数
                        actual_retries = 0
                        actual_retries = self.dialogue_formatter.format_dialogue(chapter_text, self.dialogue_done_event,
                                                                                 chapter_index)

                        # 使用实际重试次数更新 current_task
                        retry_adjustment = max_retries - actual_retries
                        print(f"剩余任务{retry_adjustment}={max_retries}-{actual_retries}")
                        self.current_task += retry_adjustment
                        print(self.current_task)
                        self.update_progress()
                        self.dialogue_done_event.wait()

                # 全部章节标注完成后，合并内容并更新至 text_box
                combined_text = "\n".join(
                    self.chapter_marked_contents[chapter_index] for chapter_index in
                    sorted(self.chapter_contents.keys()) if
                    chapter_index != 0
                )

                # 将合并后的全文更新到字典的 "全文" 项目
                self.chapter_marked_contents[0] = combined_text

                # self.text_box.delete("1.0", tk.END)
                # self.text_box.insert(tk.END, combined_text)

                # 保存全文标注结果到 Chapters 文件夹
                project_name = self.project_name.get()  # 获取项目名称
                folder_path = os.path.join(self.folder_path_var.get(), "Chapters_marked")
                os.makedirs(folder_path, exist_ok=True)
                full_text_file_path = os.path.join(folder_path, f"{project_name} 全文_marked.txt")

                with open(full_text_file_path, "w", encoding="utf-8") as f:
                    f.write(combined_text)

                # 更新 `text_box` 显示
                self.show_marked_checkbox.select()  # 自动勾选复选框
                self.display_selected_content()

                self.document_processor_app.process_document(update_pg=True)  # 批量处理后调用

            except ValueError as e:
                self.progress_bar_done = True
                messagebox.showwarning("警告", f"警告：{e}")

        else:
            try:
                # 单独处理当前选择的章节
                chapter_index = list(self.chapter_combobox["values"]).index(selected_chapter)

                chapter_text = self.text_box.get("1.0", "end-1c")
                # chapter_text = self.chapter_contents.get(chapter_index, "")
                self.dialogue_done_event.clear()

                # 同样为单个章节调用 format_dialogue，记录实际重试次数
                actual_retries = 0
                actual_retries = self.dialogue_formatter.format_dialogue(chapter_text, self.dialogue_done_event,
                                                                         chapter_index)

                # 使用实际重试次数更新 current_task
                self.update_progress()
                self.dialogue_done_event.wait()
                self.show_marked_checkbox.select()  # 自动勾选复选框
                self.display_selected_content()
                self.document_processor_app.process_document(update_pg=True)

            except ValueError as e:
                self.progress_bar_done = True
                messagebox.showwarning("警告", f"警告：{e}")

        # 恢复 combobox 原来的状态
        self.chapter_combobox.configure(state=original_state)
        self.show_marked_checkbox.configure(state="normal")

        # 获取指定行的所有控件
        # controls = self.scroll_frame.grid_slaves(row=row_idx)

        for control in controls:
            # print("恢复")
            # 获取控件原始的state值
            original_state = original_states.get(control)

            if isinstance(control, tk.Entry):
                if original_state is not None:
                    control.config(state=original_state)  # 恢复原始状态
                else:
                    control.config(state="normal")  # 如果没有存储状态，恢复为 "normal"
            elif isinstance(control, tk.Button):
                if original_state is not None:
                    control.config(state=original_state)
                else:
                    control.config(state="normal")
            elif isinstance(control, ttk.Combobox):
                if original_state is not None:
                    control.config(state=original_state)
                else:
                    control.config(state="normal")
            elif isinstance(control, tk.Checkbutton):
                if original_state is not None:
                    control.config(state=original_state)
                else:
                    control.config(state="normal")
            elif isinstance(control, tk.OptionMenu):
                if original_state is not None:
                    control.config(state=original_state)
                else:
                    control.config(state="normal")

    def update_scroll_region(self, event=None):
        """根据 canvas_frame 的尺寸更新 canvas 的滚动区域"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_mouse_wheel(self, event):
        """处理鼠标滚轮事件以滚动画布"""
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")  # 向上滚动
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")  # 向下滚动

    def reset_chapter_selection(self):
        """还原章节选择下拉栏和文本框到默认值，并清空章节内容字典"""
        # 清空文本框
        self.text_box.delete(1.0, tk.END)

        # 设置下拉框默认值为“全文”
        self.chapter_combobox.set("全文")

        # 还原下拉框选项到默认
        self.chapter_combobox["values"] = ["全文", "新建章节"]  # 还原选项

        # 清空章节内容字典
        self.chapter_contents.clear()

        self.show_chapter_splitter_controls(True)

        self.load_text_file()

        self.update_chapter_list()

        self.change_format_app.auto_set_replace_quotes()

    def load_text_file(self):
        """加载全文内容并插入字典，显示在左侧文本框中"""
        file_path = self.text_file_path_var.get()
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.text_box.delete(1.0, tk.END)  # 清空文本框
                self.text_box.insert(tk.END, content)  # 插入内容
                self.chapter_contents[0] = content  # 将全文内容存入字典索引0
        else:
            print("文档文件不存在")

    def update_chapter_list(self):
        """分章完成后，读取 Chapters 文件夹内容并更新章节选择下拉栏"""
        chapters_folder = os.path.join(self.folder_path_var.get(), "Chapters")
        marked_chapters_folder = os.path.join(self.folder_path_var.get(), "Chapters_marked")

        # 清空并重新设置章节内容字典
        self.chapter_contents.clear()
        self.chapter_marked_contents.clear()

        # 加载未标记的“全文”内容到 chapter_contents 字典
        if hasattr(self, 'text_file_path_var') and self.text_file_path_var.get():
            text_file_path = self.text_file_path_var.get()  # 获取文件路径
            if os.path.exists(text_file_path):
                with open(text_file_path, 'r', encoding='utf-8') as f:
                    self.chapter_contents[0] = f.read()  # 从文件中读取内容并加载到字典中
            else:
                print(f"Error: The file {text_file_path} does not exist.")
        else:
            print("Error: 'text_file_path_var' is not set.")

        # 构造标记的“全文”文件路径
        project_name = self.project_name.get()
        full_text_marked_file = os.path.join(marked_chapters_folder, f"{project_name} 全文_marked.txt")

        # 检查并加载标记的“全文”内容
        if os.path.exists(full_text_marked_file):
            with open(full_text_marked_file, 'r', encoding='utf-8') as f:
                self.chapter_marked_contents[0] = f.read()

        # 检查 Chapters 文件夹中的章节文件
        if os.path.exists(chapters_folder):
            chapter_files = sorted(
                [f for f in os.listdir(chapters_folder) if f.endswith('.txt')],
                key=self.extract_chapter_number  # 使用自定义排序函数
            )

            # 创建章节选项列表，添加“全文”作为第一个选项
            chapter_options = ["全文"]

            # 先检查并加载“序章”内容
            preface_index = None  # 用于存储“序章”的索引
            for file_name in chapter_files:
                if "序章" in file_name:  # 检查文件名是否包含“序章”
                    chapter_options.append(os.path.splitext(file_name)[0])  # 将“序章”加入章节选项列表
                    preface_index = len(chapter_options) - 1  # 获取“序章”在章节列表中的索引
                    with open(os.path.join(chapters_folder, file_name), 'r', encoding='utf-8') as f:
                        self.chapter_contents[preface_index] = f.read()  # 加载“序章”内容

                    # 尝试加载标记过的“序章”内容
                    marked_preface_file_path = os.path.join(marked_chapters_folder,
                                                            f"{os.path.splitext(file_name)[0]}_marked.txt")
                    if os.path.exists(marked_preface_file_path):
                        with open(marked_preface_file_path, 'r', encoding='utf-8') as f:
                            self.chapter_marked_contents[preface_index] = f.read()
                    break  # 找到“序章”后退出循环

            # 加载除“序章”外的其他章节
            for file_name in chapter_files:
                if "序章" not in file_name:
                    chapter_index = len(chapter_options)
                    chapter_options.append(os.path.splitext(file_name)[0])

                    # 加载未标记章节内容
                    with open(os.path.join(chapters_folder, file_name), 'r', encoding='utf-8') as f:
                        self.chapter_contents[chapter_index] = f.read()

                    # 尝试加载标记过的章节内容
                    marked_file_path = os.path.join(marked_chapters_folder,
                                                    f"{os.path.splitext(file_name)[0]}_marked.txt")
                    if os.path.exists(marked_file_path):
                        with open(marked_file_path, 'r', encoding='utf-8') as f:
                            self.chapter_marked_contents[chapter_index] = f.read()

            # 添加“新建章节”选项到最后
            chapter_options.append("新建章节")

            # 更新下拉栏选项
            self.chapter_combobox["values"] = chapter_options
        else:
            os.makedirs(chapters_folder)

    def extract_chapter_number(self, chapter_name):
        """提取章节编号用于排序"""
        match = re.search(r'第(\d+)', chapter_name)
        return int(match.group(1)) if match else float('inf')  # 如果未找到则返回无穷大以放在最后

    def display_selected_content(self, event=None):
        """在左侧文本框中显示当前选择的章节内容"""
        selected_option = self.chapter_combobox.get()
        show_marked = self.show_marked_var.get()

        if selected_option == "全文":
            self.process_by_chapter.place(x=0, y=0, height=15, width=100)
            # 尝试显示标记的全文内容；如果不存在，或复选框未勾选，则显示未标记的全文内容
            if show_marked and 0 in self.chapter_marked_contents:
                content = self.chapter_marked_contents[0]  # 显示标记的全文内容
            else:
                content = self.chapter_contents.get(0, "")  # 显示未标记的全文内容
            self.show_chapter_splitter_controls(True)
            self.change_format_app.show_change_format_controls(True)
        elif selected_option == "新建章节":
            self.process_by_chapter.place_forget()
            # 显示空文本框
            content = ""
            self.show_chapter_splitter_controls(False)
            self.change_format_app.show_change_format_controls(False)
        else:
            self.process_by_chapter.place_forget()
            # 处理章节内容的显示
            chapter_index = list(self.chapter_combobox["values"]).index(selected_option)

            # 如果选择标记内容且存在标记内容，则显示，否则显示未标记内容
            if show_marked:
                content = self.chapter_marked_contents.get(chapter_index, self.chapter_contents.get(chapter_index, ""))
            else:
                content = self.chapter_contents.get(chapter_index, "")

            self.show_chapter_splitter_controls(False)
            self.change_format_app.show_change_format_controls(False)

        # 更新文本框内容
        self.text_box.delete("1.0", tk.END)
        self.text_box.insert(tk.END, content)

        self.character_extractor.create_character_display()

    def show_chapter_splitter_controls(self, show):
        """根据需要显示或隐藏分章控件"""
        self.chapter_splitter_app.show_chapter_splitter_controls(show)  # 调用 ChapterSplitterApp 中的方法


class ChapterSplitterApp:
    def __init__(self, parent, text_processor):
        self.parent = parent  # 接收父容器
        self.text_processor = text_processor  # 保存 TextPreprocessor 实例
        # print(f"{self.text_processor.project_name.get()},{self.text_processor.text_file_path_var.get()}")

        self.root = root

        self.filename = None
        self.chapter_patterns = [
            "自动选择", "第一章", "第1章", "第01章", "第001章",
            "第一话", "第1话", "第01话", "第001话", "自定义"
        ]

        # 创建一个新的 Frame 用于包含所有控件
        # self.control_frame = tk.Frame(self.parent)
        # self.control_frame.grid(row=1, column=0, columnspan=3, sticky="nsew")  # 使用 grid 来放置 Frame

        # 分割线
        self.part2 = tk.Label(self.parent, text="————————————————")
        self.part2.grid(row=3, column=0, columnspan=2, sticky="w")

        # self.config_frame = tk.Frame(self.parent)
        # self.config_frame.grid(row=4, column=0, sticky="ew")

        # 分章方法
        self.pattern_label = tk.Label(self.parent, text="选择分章方法")
        self.pattern_label.grid(row=4, column=0, padx=5, columnspan=2, sticky="w")
        self.pattern_combobox_frame = tk.Frame(self.parent)
        self.pattern_combobox_frame.grid(row=4, column=1, sticky="w")
        self.pattern_combobox = ttk.Combobox(self.pattern_combobox_frame, values=self.chapter_patterns,
                                             state="readonly", width=11)
        self.pattern_combobox.grid(row=0, column=0, padx=4, pady=5, sticky='w')
        self.pattern_combobox.current(0)  # 设置默认选中 "自动选择"
        self.pattern_combobox.bind("<<ComboboxSelected>>", self.on_pattern_select)

        # 使用 Toplevel 创建顶层提示框窗口，确保提示信息不会被遮挡
        self.tooltip = tk.Toplevel(self.parent)
        self.tooltip.overrideredirect(True)  # 去除窗口边框
        self.tooltip.withdraw()  # 初始隐藏
        self.tooltip_label = tk.Label(self.tooltip, text="", bg="white", fg="black")
        self.tooltip_label.pack()

        # 自定义模式文本框（默认隐藏）
        self.custom_entry = tk.Entry(self.parent, width=27)
        self.custom_entry.grid(row=5, column=0, columnspan=2, padx=9, pady=5, sticky='w')
        self.custom_entry.grid_remove()

        # 绑定鼠标悬停和移动事件到 custom_entry
        self.custom_entry.bind("<Enter>", self.show_tooltip)
        self.custom_entry.bind("<Motion>", self.follow_mouse)
        self.custom_entry.bind("<Leave>", self.hide_tooltip)

        # 标签
        self.label = tk.Label(self.parent, text="几章一切:")
        self.label.grid(row=6, column=0, padx=5, sticky='w')

        # 输入框
        self.entry = tk.Entry(self.parent, width=13)
        self.entry.grid(row=6, column=1, padx=5, pady=5, sticky='w')

        # 设置默认值为1
        self.entry.insert(0, "1")

        # 开始分割按钮
        self.split_button = tk.Button(self.parent, text="自动分章", command=self.run_on_split_button_click)
        self.split_button.grid(row=7, column=0, padx=5, pady=5, sticky='w')

        # 高级分章按钮
        # self.split_config_button = tk.Button(self.parent, text="分章设置")
        # self.split_config_button .grid(row=7, column=1, padx=5, pady=5, sticky='e')

        # 分割线
        self.part3 = tk.Label(self.parent, text="————————————————")
        self.part3.grid(row=8, column=0, columnspan=2, sticky="w")

        # 绑定鼠标滚轮事件以便在这个 Frame 内部也可以滚动
        # self.control_frame.bind("<MouseWheel>", self.text_processor._on_mouse_wheel)  # Windows
        # self.control_frame.bind("<Button-4>", self.text_processor._on_mouse_wheel)  # macOS 向上滚动
        # self.control_frame.bind("<Button-5>", self.text_processor._on_mouse_wheel)  # macOS 向下滚动
        # self.config_frame.bind("<MouseWheel>", self.text_processor._on_mouse_wheel)
        # self.config_frame.bind("<Button-4>", self.text_processor._on_mouse_wheel)
        # self.config_frame.bind("<Button-5>", self.text_processor._on_mouse_wheel)

        # for widget in self.control_frame.winfo_children():
        # widget.bind("<MouseWheel>", self.text_processor._on_mouse_wheel)  # Windows
        # widget.bind("<Button-4>", self.text_processor._on_mouse_wheel)  # macOS 向上滚动
        # widget.bind("<Button-5>", self.text_processor._on_mouse_wheel)  # macOS 向下滚动

        for widget in self.parent.winfo_children():
            widget.bind("<MouseWheel>", self.text_processor._on_mouse_wheel)  # Windows
            widget.bind("<Button-4>", self.text_processor._on_mouse_wheel)  # macOS 向上滚动
            widget.bind("<Button-5>", self.text_processor._on_mouse_wheel)  # macOS 向下滚动

    def show_tooltip(self, event):
        """显示提示框"""
        self.tooltip_label.config(
            text="1.在章节标签内用[汉字数字][数字][二位数字][三位数字]替换数字\n2.用*号替换多个章节标签之间的内容（内容相同可以不替换）    ")
        self.tooltip.deiconify()  # 显示 tooltip
        self.update_tooltip_position(event)

    def follow_mouse(self, event):
        """更新提示框位置以跟随鼠标"""
        self.update_tooltip_position(event)

    def hide_tooltip(self, event):
        """隐藏提示框"""
        self.tooltip.withdraw()  # 隐藏 tooltip

    def update_tooltip_position(self, event):
        """更新提示框位置并确保不会被遮挡"""
        # 获取鼠标在父窗口中的位置
        x = event.x_root + 10  # 鼠标右下方偏移
        y = event.y_root + 20

        # 获取屏幕宽高，避免 tooltip 超出显示范围
        screen_width = self.parent.winfo_screenwidth()
        screen_height = self.parent.winfo_screenheight()

        # 调整位置，避免超出屏幕右边或底部
        tooltip_width = self.tooltip.winfo_reqwidth()
        tooltip_height = self.tooltip.winfo_reqheight()
        if x + tooltip_width > screen_width:
            x = screen_width - tooltip_width - 10
        if y + tooltip_height > screen_height:
            y = screen_height - tooltip_height - 10

        # 移动提示框到新的位置
        self.tooltip.geometry(f"+{x}+{y}")

    def on_pattern_select(self, event):
        """处理下拉栏选项的选择"""
        selected_pattern = self.pattern_combobox.get()
        if selected_pattern == "自定义":
            self.custom_entry.grid()  # 显示自定义文本框
        else:
            self.custom_entry.grid_remove()  # 隐藏自定义文本框

    def run_on_split_button_click(self):
        Threed = threading.Thread(target=self.on_split_button_click)
        Threed.start()

    def on_split_button_click(self):
        print("开始")
        selected_option = self.pattern_combobox.get()  # 获取当前下拉选择框的选项
        content = self.text_processor.text_box.get("1.0", tk.END)  # 从文本框获取内容
        print("当前选项:", selected_option)

        if not content.strip():  # 检查文本框是否为空
            messagebox.showwarning("警告", "请先输入文本")
            return

        try:
            # 自动选择直接调用 split_chapters 函数
            if selected_option == "自动选择":
                self.split_chapters()  # 自动选择模式直接调用分章函数

            # 自定义模式逻辑
            elif selected_option == "自定义":
                print("自定义模式")
                custom_pattern = self.custom_entry.get().strip()  # 从自定义输入框获取内容
                if not custom_pattern:
                    messagebox.showwarning("警告", "请输入自定义分章模式")
                    return
                # 使用自定义模式处理函数
                self.process_custom_pattern(custom_pattern, content)  # 调用自定义处理方法

            # 特定章节标号模式调用指定分章方法
            elif selected_option in self.chapter_patterns:
                split_function = self.get_split_function(selected_option)  # 获取指定的分章函数
                if split_function:
                    lines = content.splitlines(keepends=True)  # 保留换行符
                    preface, chapters = split_function(lines)  # 执行分章函数
                    if chapters:
                        split_count = int(self.entry.get())
                        if split_count < 1:
                            raise ValueError("分割整数必须大于0")

                        # 调用 write_files，确保传入 split_count
                        self.write_files((preface, chapters), split_count)
                        messagebox.showinfo("成功", f"文件已使用模式 '{selected_option}' 分割并保存")
                    else:
                        raise ValueError("未找到任何章节")

        except Exception as e:
            messagebox.showerror("错误", str(e))

    def process_custom_pattern(self, custom_pattern, content):
        print(f"处理自定义模式: {custom_pattern}")

        # 初始化章节字典，第一次循环从文本框获取内容
        chapter_dict = {"001": self.text_processor.text_box.get("1.0", tk.END)}

        # 匹配所有被 [] 包裹的内容，记录每个括起来的内容的起始和结束位置
        bracketed_parts = [(m.start(), m.end()) for m in re.finditer(r'\[[^\]]+\]', custom_pattern)]

        # 按每个 [] 包裹的内容循环提取
        for i, (start, end) in enumerate(bracketed_parts):
            print(f"主循环：{i}")
            # 左侧内容：从上一个 [] 结束到当前 [] 开始
            left_text_start = bracketed_parts[i - 1][1] if i > 0 else 0
            raw_left_text = custom_pattern[left_text_start:start]

            # 从后往前查找分隔符（*，[，]）并截断
            split_pos = max(raw_left_text.rfind('*'), raw_left_text.rfind('['), raw_left_text.rfind(']'))
            if split_pos != -1:
                left_text = raw_left_text[split_pos + 1:]  # 从分隔符后截取
            else:
                left_text = raw_left_text  # 没有找到则全部保留

            # 当前 [] 包裹的内容
            bracketed_text = custom_pattern[start:end]

            # 右侧内容：从当前 [] 后的部分直到下一个分隔符（*，[]）
            right_text_start = end
            right_match = re.search(r'[\*\[\]]', custom_pattern[right_text_start:])
            if right_match:
                right_text = custom_pattern[right_text_start:right_text_start + right_match.start()]
            else:
                right_text = custom_pattern[right_text_start:]

            # 合并并输出当前结果
            output = left_text + bracketed_text + right_text
            # print(f"主循环{i}章节字典:{chapter_dict}")

            # 调用 process_output_segment 并获取分章后的章节字典
            chapter_dict = self.process_output_segment(output, chapter_dict)

        # 循环结束后，将最终章节字典发送到导出函数
        self.export_chapters(chapter_dict)

    def process_output_segment(self, segment, chapter_dict):
        """
            处理每个片段，接收章节字典，生成分章符号后按章节字典中的索引号依次分章。
            :param segment: 每次循环生成的输出内容
            :param chapter_dict: 当前的章节字典
        """
        # 匹配 [] 中的占位符
        pattern = r'\[([^\]]+)\]'
        placeholders = re.findall(pattern, segment)

        # 初始化分章符字典
        chapter_markers = {}

        for placeholder in placeholders:
            if placeholder == "二位数字":
                loop_start, loop_end = 1, 99  # 对于二位数字格式，仅循环 1 到 99
                break
        else:
            loop_start, loop_end = 1, 999  # 默认循环 1 到 999

        # 循环范围，根据占位符内容调整循环次数
        for i in range(loop_start, loop_end + 1):
            current_segment = segment  # 重置为原始模板

            # 替换每个 [] 中的内容
            for placeholder in placeholders:
                if placeholder == "汉字数字":
                    replacement = self.int_to_chinese(i)  # 使用现有的汉字转换函数
                elif placeholder == "数字":
                    replacement = str(i)  # 正常数字
                elif placeholder == "二位数字":
                    replacement = f"{i:02}"  # 两位数字，补零
                elif placeholder == "三位数字":
                    replacement = f"{i:03}"  # 三位数字，补零
                else:
                    replacement = placeholder  # 未知格式，保留原样

                # 使用正则替换第一个符合条件的 []
                current_segment = re.sub(r'\[' + re.escape(placeholder) + r'\]', replacement, current_segment, count=1)

            # 将当前生成的分章符存入字典，以 i 作为键
            chapter_markers[i] = current_segment

        # 分章处理逻辑
        split_chapters = {}
        for index, text in chapter_dict.items():
            # 将章节文本、索引号和分章符字典传入分章函数
            split_result = self.split_chapter_custom(text, index, chapter_markers)
            # 合并分章后的结果
            split_chapters.update(split_result)

        return split_chapters

    def split_chapter_custom(self, text, index, chapter_markers):
        """
            自定义分章函数，根据分章符号在文本中查找对应章节内容。
            :param text: 当前章节的文本
            :param index: 当前章节的索引号
            :param chapter_markers: 章节分章符号字典
        """
        # 将文本按行分割为列表
        lines = text.splitlines()

        # 初始化分章结果字典和序章内容
        split_result = {}
        chapter_start_idx = 0  # 用于记录章节的起始行号
        chapter_number = 0  # 序章编号设为000

        # 按照 chapter_markers 字典的索引顺序处理分章符
        for marker_index in sorted(chapter_markers.keys()):
            chapter_marker = chapter_markers[marker_index]

            # 查找分章符所在的行号
            marker_line_idx = next((i for i, line in enumerate(lines) if chapter_marker in line), None)

            if marker_line_idx is not None:
                # 如果找到了分章符，提取章节内容
                if chapter_number == 0:
                    # 序章：从文本开头到第一个分章符所在行之前
                    split_result[f"{index}.000"] = "\n".join(lines[chapter_start_idx:marker_line_idx]).strip()
                else:
                    # 后续章节：从上一个分章符的行到当前分章符的行之前
                    split_result[f"{index}.{chapter_number:03}"] = "\n".join(
                        lines[chapter_start_idx:marker_line_idx]).strip()

                # 更新下一个章节的起始行号为当前分章符所在行
                chapter_start_idx = marker_line_idx
                chapter_number += 1

        # 最后一章内容：从最后一个分章符所在行到文本结尾
        split_result[f"{index}.{chapter_number:03}"] = "\n".join(lines[chapter_start_idx:]).strip()

        # print(split_result)
        return split_result

    def export_chapters(self, chapter_dict):
        """
            导出章节字典中的文本到指定文件夹路径，将多个章节合并为一个文档。
            导出的文档后缀为所包含的章节范围，从开始章节的后缀到结束章节的后缀。
            :param chapter_dict: 包含所有章节内容的字典
        """
        # 获取导出文件夹路径和项目名称前缀
        output_folder = os.path.join(self.text_processor.folder_path_var.get(), "Chapters")
        project_name_prefix = self.text_processor.project_name.get()

        # 获取自定义命名模板
        custom_entry_template = self.custom_entry.get().strip()

        # 从文本框读取每个文档包含的章节数
        chapters_per_file = int(self.entry.get())

        # 创建输出文件夹（如果不存在）
        os.makedirs(output_folder, exist_ok=True)

        # 获取章节索引的列表并分批处理
        chapter_indices = sorted(chapter_dict.keys())
        for i in range(0, len(chapter_indices), chapters_per_file):
            # 获取本批次的章节索引
            batch_indices = chapter_indices[i:i + chapters_per_file]

            # 跳过内容为空的章节
            batch_texts = [chapter_dict[idx] for idx in batch_indices if chapter_dict[idx].strip()]
            if not batch_texts:
                continue

            # 合并章节内容
            combined_text = "\n\n".join(batch_texts)

            # 处理每个章节的索引后缀，替换 custom_entry_template 中的占位符
            processed_suffixes = []
            for chapter_index in batch_indices:
                processed_index = chapter_index.split(".", 1)[-1] if "." in chapter_index else chapter_index
                index_parts = processed_index.split(".")
                suffix = custom_entry_template
                for j, part in enumerate(index_parts):
                    suffix = re.sub(r'\[([^\]]*)\]', part, suffix, count=1)
                suffix = suffix.replace("*", " ")
                processed_suffixes.append(suffix)

            # 获取开始和结束章节的后缀
            start_suffix = processed_suffixes[0]
            end_suffix = processed_suffixes[-1] if len(processed_suffixes) > 1 else start_suffix

            # 生成文件名后缀
            file_name_suffix = f"{start_suffix} - {end_suffix}" if start_suffix != end_suffix else start_suffix

            # 生成文件名
            file_name = f"{project_name_prefix} {file_name_suffix}.txt"
            file_path = os.path.join(output_folder, file_name)

            # 将合并后的章节文本写入文件
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(combined_text)

            print(f"章节范围 {batch_indices[0]} - {batch_indices[-1]} 已导出到 {file_path}")

    def import_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if filename:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, filename)

    def run_split_chapters(self):
        thread = threading.Thread(target=self.split_chapters)
        thread.start()

    def split_chapters(self):
        content = self.text_processor.text_box.get("1.0", tk.END)  # 从文本框获取内容
        # print(content)
        if not content.strip():  # 检查文本框是否为空
            messagebox.showwarning("警告", "请先输入文本")
            return

        try:
            best_chunks = None
            best_pattern = None
            max_chapters = 0

            # 遍历所有章节标号模式
            for pattern in self.chapter_patterns:
                split_function = self.get_split_function(pattern)
                if split_function:
                    # 使用行分割，确保每行都有换行符
                    lines = content.splitlines(keepends=True)  # 保留换行符
                    preface, chapters = split_function(lines)  # 传入保留换行符的行列表
                    if len(chapters) > max_chapters:
                        max_chapters = len(chapters)
                        best_chunks = (preface, chapters)
                        best_pattern = pattern

            if best_chunks:
                split_count = int(self.entry.get())
                if split_count < 1:
                    raise ValueError("分割整数必须大于0")

                # 调用 write_files，确保传入 split_count
                self.write_files(best_chunks, split_count)
                # print(best_chunks)
                threading.Thread(target=lambda: self.show_message_box(best_pattern)).start()

            else:
                raise ValueError("未找到任何章节")

        except Exception as e:
            messagebox.showerror("错误", str(e))

    def show_message_box(self, best_pattern):
        messagebox.showinfo("成功", f"使用章节模式 '{best_pattern}'，文件已分割并保存")

    def read_file(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.readlines()
        return content

    def get_split_function(self, pattern):
        """根据检测到的章节标号模式返回对应的分割函数"""
        if pattern == "第一章":
            print("第一章")
            return self.split_by_chinese_chapter
        elif pattern == "第1章":
            print("第1章")
            return self.split_by_arabic_chapter
        elif pattern == "第01章":
            print("第01章")
            return self.split_by_two_digit_chapter
        elif pattern == "第001章":
            print("第001章")
            return self.split_by_three_digit_chapter
        elif pattern == "第一话":
            print("第一话")
            return self.split_by_chinese_episode
        elif pattern == "第1话":
            print("第1话")
            return self.split_by_arabic_episode
        elif pattern == "第01话":
            print("第01话")
            return self.split_by_two_digit_episode
        elif pattern == "第001话":
            print("第001话")
            return self.split_by_three_digit_episode
        return None

    def split_by_chinese_chapter(self, content):
        """分割中文数字章节"""
        chapter_patterns = self.generate_patterns("第XX章", 1, 999, is_chinese=True)
        return self.split_text(content, chapter_patterns)

    def split_by_arabic_chapter(self, content):
        """分割阿拉伯数字章节（第1章）"""
        chapter_patterns = self.generate_patterns("第XX章", 1, 999, is_chinese=False, fixed_width=False)
        return self.split_text(content, chapter_patterns)

    def split_by_two_digit_chapter(self, content):
        """分割两位数阿拉伯数字章节（第01章）"""
        chapter_patterns = self.generate_patterns("第XX章", 1, 99, width=2)
        return self.split_text(content, chapter_patterns)

    def split_by_three_digit_chapter(self, content):
        """分割三位数阿拉伯数字章节（第001章）"""
        chapter_patterns = self.generate_patterns("第XX章", 1, 999, width=3)
        return self.split_text(content, chapter_patterns)

    def split_by_chinese_episode(self, content):
        """分割中文数字话数"""
        episode_patterns = self.generate_patterns("第XX话", 1, 999, is_chinese=True)
        return self.split_text(content, episode_patterns)

    def split_by_arabic_episode(self, content):
        """分割阿拉伯数字话数（第1话）"""
        episode_patterns = self.generate_patterns("第XX话", 1, 999, is_chinese=False, fixed_width=False)
        return self.split_text(content, episode_patterns)

    def split_by_two_digit_episode(self, content):
        """分割两位数阿拉伯数字话数（第01话）"""
        episode_patterns = self.generate_patterns("第XX话", 1, 99, width=2)
        return self.split_text(content, episode_patterns)

    def split_by_three_digit_episode(self, content):
        """分割三位数阿拉伯数字话数（第001话）"""
        episode_patterns = self.generate_patterns("第XX话", 1, 999, width=3)
        return self.split_text(content, episode_patterns)

    def generate_patterns(self, base_pattern, start=1, end=999, is_chinese=False, fixed_width=True, width=1):
        """生成章节模式，可以处理从1到999的中文或阿拉伯数字章节模式"""
        patterns = []
        for i in range(start, end + 1):
            if is_chinese:
                num_str = self.int_to_chinese(i)
            else:
                if fixed_width:
                    num_str = f"{i:0{width}}"  # 根据指定宽度生成数字
                else:
                    num_str = str(i)  # 不固定宽度
            patterns.append(base_pattern.replace('XX', num_str))
        return patterns

    def int_to_chinese(self, num):
        """将1-999的整数转换为对应的中文数字"""
        chinese_numerals = "零一二三四五六七八九"
        units = ["", "十", "百", "千"]
        digits = []
        # print(f"导入数：{num}")

        hundreds = num // 100  # 百位
        tens = (num % 100) // 10  # 十位
        ones = num % 10  # 个位

        # 处理百位
        if hundreds > 0:
            digits.append(chinese_numerals[hundreds] + units[2])

        # 处理十位
        if tens > 0:
            if hundreds == 0 and tens == 1:
                digits.append(units[1])  # 直接添加“十”
            else:
                digits.append(chinese_numerals[tens] + units[1])  # 添加十位数和“十”
        elif tens == 0 and hundreds > 0 and ones > 0:
            digits.append("零")  # 处理如“百零X”的情况

        # 处理个位
        if ones > 0:
            digits.append(chinese_numerals[ones])

        # print(f"输出数：{digits}")

        return ''.join(digits)

    def split_text(self, content, patterns):
        """根据生成的模式分割文本并提取章节标号"""
        chapters = []
        current_chapter = []
        current_chapter_number = None
        chapter_start = None
        pattern_objects = [re.compile(p) for p in patterns]
        found_first_chapter = False
        preface = []

        for i, line in enumerate(content):
            matched = False
            for pattern in pattern_objects:
                match = pattern.search(line)
                if match:
                    matched = True
                    chapter_number = match.group()  # 提取当前行的章节标号
                    break

            if matched:
                if not found_first_chapter:
                    # 找到第一章之前的文本作为前言
                    preface = current_chapter.copy()
                    current_chapter = [line]
                    found_first_chapter = True
                    chapter_start = i
                    current_chapter_number = chapter_number
                else:
                    # 将前一个章节保存，标号和内容一一对应
                    chapters.append((chapter_start, i - 1, current_chapter, current_chapter_number))
                    # 新章节开始
                    chapter_start = i
                    current_chapter = [line]
                    current_chapter_number = chapter_number  # 更新为新的章节标号
            else:
                current_chapter.append(line)

        # 保存最后一个章节
        if chapter_start is not None:
            chapters.append((chapter_start, len(content) - 1, current_chapter, current_chapter_number))

        return preface, chapters

    def chinese_to_arabic(self, chinese_str):
        """将中文数字转换为阿拉伯数字，支持1-9999范围内的数字"""
        chinese_to_digit = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
        units = {'十': 10, '百': 100, '千': 1000}

        result = 0  # 存储最终结果
        temp_num = 0  # 存储当前累积的数字
        unit = 1  # 当前的单位，初始为个位

        # 特殊情况处理："十" -> "一十"
        if chinese_str == "十":
            return 10

        length = len(chinese_str)

        for i in range(length - 1, -1, -1):
            char = chinese_str[i]

            if char in chinese_to_digit:  # 是数字
                temp_num = chinese_to_digit[char]
                result += temp_num * unit
                temp_num = 0  # 清空暂时存储
            elif char in units:  # 是单位
                unit = units[char]
                if i == 0:  # 如果“十”是第一个字符，默认加上一
                    result += 1 * unit
            else:
                raise ValueError(f"非法字符 {char}")

        return result

    def convert_chapter_label(self, label):
        """根据章节标号自动转换中文数字为阿拉伯数字"""
        match = re.search(r'[第](.*?)[章话]', label)
        if match:
            chinese_number = match.group(1)
            if self.is_chinese_number(chinese_number):
                # 仅对中文数字进行转换
                arabic_number = self.chinese_to_arabic(chinese_number)
                return label.replace(chinese_number, str(arabic_number))
        return label

    def is_chinese_number(self, s):
        """判断是否是中文数字"""
        chinese_digits = set("零一二三四五六七八九十百千")
        return all(char in chinese_digits for char in s)

    def write_files(self, chunks, split_count):
        """根据提取的章节标号进行文件命名，并保存到指定目录"""
        preface, chapters = chunks
        # print("调用了")

        # print(chapters)

        if not chapters:
            raise ValueError("未找到任何章节")

        # 获取目标目录，使用 .get() 获取路径字符串
        output_dir = os.path.join(self.text_processor.folder_path_var.get(), "Chapters")
        os.makedirs(output_dir, exist_ok=True)  # 创建目录，如果不存在

        # 清空目标文件夹
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)  # 删除文件
            except Exception as e:
                print(f"无法删除文件 {file_path}: {e}")  # 打印错误信息

        # 获取基本文件名，从 project_name 获取
        base_filename = self.text_processor.project_name.get()  # 使用项目名称作为基本文件名

        if preface:
            self.write_file(os.path.join(output_dir, f"{base_filename} 序章.txt"), preface)

        num_chapters = len(chapters)
        num_batches = (num_chapters + split_count - 1) // split_count

        for i in range(num_batches):
            start_index = i * split_count
            end_index = min((i + 1) * split_count, num_chapters)
            batch_chunks = chapters[start_index:end_index]
            batch_content = []
            chapter_labels = []

            for chapter in batch_chunks:
                batch_content.extend(chapter[2])  # 添加章节内容
                chapter_labels.append(self.convert_chapter_label(chapter[3]))  # 收集并转换章节标号

            # 使用章节标号进行文件命名，只保留首尾章节名
            if len(chapter_labels) > 1:
                batch_name = f"{base_filename} {chapter_labels[0]} - {chapter_labels[-1]}.txt"
            else:
                batch_name = f"{base_filename} {chapter_labels[0]}.txt"

            # 将文件保存到指定的输出目录
            self.write_file(os.path.join(output_dir, batch_name), batch_content)

        # 调用 TextPreprocessor 类的更新函数
        self.text_processor.update_chapter_list()

    def write_file(self, filename, content):
        """写入文件"""
        with open(filename, 'w', encoding='utf-8') as file:
            file.writelines(content)

    def show_chapter_splitter_controls(self, show):
        """根据需要显示或隐藏分章控件"""
        # 控制标签、输入框和按钮的显隐
        self.label.grid() if show else self.label.grid_remove()
        self.entry.grid() if show else self.entry.grid_remove()
        self.split_button.grid() if show else self.split_button.grid_remove()
        self.part2.grid() if show else self.part2.grid_remove()
        self.part3.grid() if show else self.part3.grid_remove()
        self.pattern_label.grid() if show else self.pattern_label.grid_remove()
        self.pattern_combobox_frame.grid() if show else self.pattern_combobox_frame.grid_remove()
        # 仅当show为True且pattern_combobox的值为"自定义"时显示custom_entry
        if show and self.pattern_combobox.get() == "自定义":
            self.custom_entry.grid()
        else:
            self.custom_entry.grid_remove()


class ChangeFormat:
    def __init__(self, parent, text_area, text_processor):
        self.parent = parent
        self.text_area = text_area
        self.text_processor = text_processor

        # 创建 control_frame 容器
        self.control_frame = tk.Frame(self.parent)

        # 创建处理选项复选框变量
        self.var_replace_quotes = tk.BooleanVar()
        self.var_add_blank_lines = tk.BooleanVar()
        self.var_remove_empty_lines = tk.BooleanVar(value=True)
        self.var_add_blank_line_after_each_line = tk.BooleanVar(value=True)

        self.create_controls()

        # 检查文本内容并自动设置“将‘和’替换为‘「和」’”选项的状态
        self.auto_set_replace_quotes()

        # 绑定鼠标滚轮事件
        self.control_frame.bind("<MouseWheel>", self.text_processor._on_mouse_wheel)  # Windows
        self.control_frame.bind("<Button-4>", self.text_processor._on_mouse_wheel)  # macOS 向上滚动
        self.control_frame.bind("<Button-5>", self.text_processor._on_mouse_wheel)  # macOS 向下滚动

        # 绑定每个控件的滚动事件
        for widget in self.control_frame.winfo_children():
            widget.bind("<MouseWheel>", self.text_processor._on_mouse_wheel)  # Windows
            widget.bind("<Button-4>", self.text_processor._on_mouse_wheel)  # macOS 向上滚动
            widget.bind("<Button-5>", self.text_processor._on_mouse_wheel)  # macOS 向下滚动

    def auto_set_replace_quotes(self):
        """自动设置是否勾选‘将“和”替换为「和」’选项"""
        # 获取文本框内容
        text = self.text_area.get("1.0", tk.END)
        # print(self.text_area.get("1.0", tk.END))

        # 统计中文或英文引号和「」符号的数量
        quote_count = text.count('"') + text.count('"') + text.count('“') + text.count('”')
        bracket_count = text.count('「') + text.count('」')

        # 如果引号数量是符号“「”和“」”数量的10倍以上，勾选"将“和”替换为「和」"选项
        if quote_count > 10 * bracket_count:
            self.var_replace_quotes.set(True)
        else:
            self.var_replace_quotes.set(False)

    def process_text(self):
        # 获取文本框内容
        text = self.text_area.get("1.0", tk.END)
        # print(text)

        # 获取处理选项状态
        replace_quotes = self.var_replace_quotes.get()
        add_blank_lines = self.var_add_blank_lines.get()
        remove_empty_lines = self.var_remove_empty_lines.get()
        add_blank_line_after_each_line = self.var_add_blank_line_after_each_line.get()

        # 替换“和”符号
        if replace_quotes:
            text = text.replace('“', '「').replace('”', '」')

        # 在「符号前和」符号后添加空白行
        if add_blank_lines:
            text = text.replace('「', '\n\n「').replace('」', '」\n\n')

        # 删除不包含中文、英文、日文、韩文字母、数字和文字的行
        if remove_empty_lines:
            lines = text.splitlines()
            processed_lines = []

            # 正则表达式匹配中文、英文、日文、韩文字母、数字和文字，并排除符号
            pattern = re.compile(
                r'[\u4e00-\u9fff\u3400-\u4dbf'  # 中文字符
                r'\u3040-\u309f\u30a0-\u30ff'  # 日文平假名、片假名
                r'\uac00-\ud7af'  # 韩文字符
                r'a-zA-Z0-9]'  # 英文字符和数字
            )

            for line in lines:
                # 如果行中包含任何匹配的字符（且不含符号），则保留该行
                if pattern.search(line):
                    processed_lines.append(line)

            text = "\n".join(processed_lines)

        # 在每行后面添加一个空白行
        if add_blank_line_after_each_line:
            lines = text.splitlines()
            text = "\n\n".join(lines)  # 每行后添加一个空白行

        # 更新文本框内容
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, text)

    def create_controls(self):
        """创建复选框和按钮控件"""
        self.control_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")

        # tk.Label(self.control_frame, text="文档格式转换：").grid(row=0, column=0, sticky="w")

        # 创建处理选项复选框
        tk.Checkbutton(self.control_frame, text="将“和”替换为「和」", variable=self.var_replace_quotes).grid(row=1,
                                                                                                           column=0,
                                                                                                           columnspan=2,
                                                                                                           sticky="w")
        tk.Checkbutton(self.control_frame, text="在「前和」后换行", variable=self.var_add_blank_lines).grid(row=2,
                                                                                                          column=0,
                                                                                                          columnspan=2,
                                                                                                          sticky="w")
        tk.Checkbutton(self.control_frame, text="删除仅含符号的行", variable=self.var_remove_empty_lines).grid(row=3,
                                                                                                               column=0,
                                                                                                               columnspan=2,
                                                                                                               sticky="w")
        tk.Checkbutton(self.control_frame, text="段落间添加空白行",
                       variable=self.var_add_blank_line_after_each_line).grid(row=4, column=0, columnspan=2, sticky="w")
        tk.Button(self.control_frame, text="处理文本", command=self.process_text).grid(row=5, column=0, padx=5, pady=5,
                                                                                       sticky="w")
        # 检查文本内容并自动设置“将‘和’替换为‘「和」’”选项的状态
        # self.auto_set_replace_quotes()

    def show_change_format_controls(self, show):
        """控制 ChangeFormat 控件显示或隐藏"""
        if show:
            self.control_frame.grid()
        else:
            self.control_frame.grid_remove()


class DialogueFormatter:
    def __init__(self, text_box, text_processor, config):
        self.text_box = text_box  # 文本框的引用
        self.text_processor = text_processor
        self.threshold_entry = self.text_processor.threshold_entry
        self.retry_entry = self.text_processor.retry_entry
        self.results_dict = {}  # 保存标注比例和相应的标注内容
        # self.config = config  # 引用 StartMenu 的配置
        self.config = {}
        self.load_config()  # 加载配置文件并存储为字典

    def run_format_dialogue(self, chapter_text, done_event=None):
        thread = threading.Thread(target=self.format_dialogue, args=(chapter_text, done_event,))
        thread.start()

    def load_config(self):
        """加载配置文件并返回配置字典"""
        try:
            # print("获取配置")
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    if isinstance(config_data, dict):
                        self.config = config_data.get("config", {})  # Load keys from config
                    else:
                        print("配置文件格式不正确，应该为 JSON 格式的字典。")
                        self.config = {}
            else:
                print("配置文件未找到，请确保 config.json 存在于程序目录中。")
                self.config = {}
        except json.JSONDecodeError:
            print("配置文件解析失败，请确保文件格式正确。")
            self.config = {}
        except Exception as e:
            print(f"加载配置时发生异常: {e}")
            self.config = {}

    def format_dialogue(self, original_text, done_event, chapter_index):
        print("启动了一个线程")
        print(self.text_processor.select_AI.get())
        ai_choice = self.text_processor.select_AI.get()  # 获取选择的 AI 接口
        self.load_config()

        try:
            threshold = float(self.threshold_entry.get()) / 100  # 转换为小数
            max_retries = int(self.retry_entry.get())
        except ValueError:
            raise ValueError("标注比例阈值或最大重试次数取值错误")

        # original_text = self.text_box.get("1.0", "end-1c")  # 获取原文内容
        retries = 0

        while retries < max_retries:
            try:
                # 根据选择的 AI 接口获取 API 响应内容
                if ai_choice == "百度":
                    assistant_text = self.get_assistant_response_baidu(original_text)
                elif ai_choice == "KIMI":
                    assistant_text = self.get_assistant_response_KIMI(original_text)
                elif ai_choice == "阿里":
                    assistant_text = self.get_assistant_response_ali(original_text)
                elif ai_choice == "讯飞":
                    assistant_text = self.get_assistant_response_xunfei(original_text)
                elif ai_choice == "腾讯":
                    assistant_text = self.get_assistant_response_tengxun(original_text)
                elif ai_choice == "更多":
                    assistant_text = self.get_assistant_response_genduo(original_text)
                else:
                    assistant_text = self.get_assistant_response_custom(original_text)

                # 构建标注后的新文本
                constructed_text = self.construct_text(original_text, assistant_text)

                # 计算标注比例
                ratio = self.calculate_annotation_ratio(original_text, constructed_text)

                # 将结果保存到字典中
                self.results_dict[ratio] = constructed_text

                # 检查标注比例是否符合阈值
                if ratio >= threshold:
                    # actual_retries = retries  # 记录最终重试的次数
                    self.export_results(constructed_text, ratio, done_event, chapter_index)
                    print(f"已重试次数：{retries}")
                    return retries
                else:
                    retries += 1

            except Exception as e:
                raise ValueError(e)

        # 如果达到最大重试次数，则导出最佳结果
        # actual_retries = retries  # 达到最大重试时记录实际重试次数
        # print(f"实际重试次数{actual_retries}")
        best_ratio = max(self.results_dict.keys())
        self.export_results(self.results_dict[best_ratio], best_ratio, done_event, chapter_index)
        print(f"已重试次数：{retries}")
        return retries

    @acquire_lock(api_lock_baidu)
    def get_assistant_response_baidu(self, original_text):
        # 从配置字典中获取百度 API 的认证信息和模型
        baidu_config = self.config.get('百度', {})
        access_key = baidu_config.get('ACCESS_KEY')
        secret_key = baidu_config.get('SECRET_KEY')
        selected_model = baidu_config.get('MODEL')

        print(f"百度配置：\naccess_key：{access_key}\nsecret_key:{secret_key}\nselected_model:{selected_model}")

        # 设置认证信息
        os.environ["QIANFAN_ACCESS_KEY"] = access_key
        os.environ["QIANFAN_SECRET_KEY"] = secret_key

        # 初始化ERNIE对话接口
        chat_comp = qianfan.ChatCompletion()

        # 将 original_text 按 设定值 字进行分段
        def split_text_by_limit(text):
            limit = int(self.text_processor.text_limit_entry.get())
            print(limit)
            segments = []
            current_segment = []
            current_length = 0

            # 按行拆分文本并逐行累加
            for line in text.splitlines():
                line = line.encode('utf-8').decode('utf-8')  # 强制每行文本为UTF-8编码
                line_length = len(line)
                if current_length + line_length > limit:
                    # 达到限制，将当前段落存入列表
                    segments.append("\n".join(current_segment))
                    current_segment = [line]
                    current_length = line_length
                else:
                    # 累加到当前段落
                    current_segment.append(line)
                    current_length += line_length

            # 存入最后一段
            if current_segment:
                segments.append("\n".join(current_segment))

            return segments

        print(f"上下文模式:{self.text_processor.contextualize_output_var.get()}")

        is_contextualize = self.text_processor.contextualize_output_var.get()

        if is_contextualize:
            print("上下文模式")
            # 获取分段后的文本
            text_segments = split_text_by_limit(original_text)

            # 构建对话的 messages 数组，包含多轮上下文
            messages = []
            assistant_responses = []

            # 逐段调用API，每段按对话上下文进行发送
            for i, segment in enumerate(text_segments):
                # 添加不同前缀
                prefix = "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n" if i == 0 else "继续标记：\n\n"
                segment_text = prefix + segment
                segment_text = segment_text.encode('utf-8').decode('utf-8')

                # 将当前段内容作为用户的输入消息添加到上下文中
                messages.append({"role": "user", "content": segment_text})

                # 调用 API 获取响应
                print(f"实际输入：{messages}")
                response = chat_comp.do(
                    model=selected_model,
                    messages=messages,
                    temperature=0.8,
                    top_p=0.8,
                    stream=False
                )

                # 提取 API 返回内容
                assistant_text = response.get("result", "")
                assistant_text = assistant_text.encode('utf-8').decode('utf-8')  # 强制转换为UTF-8
                assistant_responses.append(assistant_text)

                # 将助手的响应加入 messages，以更新对话上下文
                messages.append({"role": "assistant", "content": assistant_text})

            # 拼接所有段落的助手响应为最终结果
            print("\n".join(assistant_responses))
            return "\n".join(assistant_responses)

        else:
            print("非上下文模式")
            # 获取分段后的文本
            text_segments = split_text_by_limit(original_text)
            text_dict = {}
            for i, segment in enumerate(text_segments):
                # 第一段带现有前缀，后续段落加“继续标记”
                prefix = "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"
                text_dict[i] = prefix + segment
                # print(text_dict[i])

            # 存储最终返回的结果
            assistant_responses = []

            # 对每一段调用API获取响应
            for i, segment_text in text_dict.items():
                segment_text = segment_text.encode('utf-8').decode('utf-8')
                print(f"实际输入：{segment_text}")
                response = chat_comp.do(
                    model=selected_model,
                    messages=[{"role": "user", "content": segment_text}],
                    temperature=0.8,
                    top_p=0.8,
                    stream=False
                )

                # 提取API返回的内容并添加到结果列表
                assistant_text = response.get("result", "")
                assistant_text = assistant_text.encode('utf-8').decode('utf-8')  # 强制转换为UTF-8
                print(assistant_text)
                assistant_responses.append(assistant_text)

            # 将所有段落的响应拼接为最终结果
            print("\n".join(assistant_responses))
            return "\n".join(assistant_responses)

    @acquire_lock(api_lock_kimi)
    def get_assistant_response_KIMI(self, original_text):
        # 从配置字典中获取百度 API 的认证信息和模型
        kimi_config = self.config.get('KIMI', {})
        access_key = kimi_config.get('ACCESS_KEY')
        api_key = kimi_config.get('SECRET_KEY')
        selected_model = kimi_config.get('MODEL')
        max_retries = 5  # 最大重试次数
        retries = 0  # 当前重试次数

        print(f"KIMI配置：\napi_key:{api_key}\nselected_model:{selected_model}")

        # 初始化KIMI API客户端
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1"
        )

        # 将 original_text 按 9000 字进行分段
        def split_text_by_limit(text):
            limit = int(self.text_processor.text_limit_entry.get())
            print(limit)
            segments = []
            current_segment = []
            current_length = 0

            # 按行拆分文本并逐行累加
            for line in text.splitlines():
                line = line.encode('utf-8').decode('utf-8')  # 强制每行文本为UTF-8编码
                line_length = len(line)
                if current_length + line_length > limit:
                    # 达到限制，将当前段落存入列表
                    segments.append("\n".join(current_segment))
                    current_segment = [line]
                    current_length = line_length
                else:
                    # 累加到当前段落
                    current_segment.append(line)
                    current_length += line_length

            # 存入最后一段
            if current_segment:
                segments.append("\n".join(current_segment))

            return segments

        print(f"上下文模式:{self.text_processor.contextualize_output_var.get()}")

        is_contextualize = self.text_processor.contextualize_output_var.get()

        if is_contextualize:
            # 获取分段后的文本
            text_segments = split_text_by_limit(original_text)
            assistant_responses = []

            history = None

            # 如果没有提供历史记录，则初始化为一个空列表
            if history is None:
                history = [
                    {"role": "system",
                     "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"}
                ]

                # 获取分段后的文本
                text_segments = split_text_by_limit(original_text)
                assistant_responses = []

                # 对每一段调用 KIMI API 获取响应
                for i, segment_text in enumerate(text_segments):
                    prefix = "请标注第一段故事：\n\n" if i == 0 else "继续标记：\n\n"
                    segment = prefix + segment_text
                    print(f"实际输入：{segment}")

                    # 在历史记录中加入新的用户输入
                    history.append({"role": "user", "content": segment})

                    while True:  # 用循环来确保在遇到速率限制时重试
                        try:
                            response = client.chat.completions.create(
                                model=selected_model,
                                messages=history,
                                temperature=0.8,
                                top_p=0.8
                            )

                            assistant_text = response.choices[0].message.content
                            print(assistant_text)
                            assistant_responses.append(assistant_text)

                            # 将助手的回答加入历史记录
                            history.append({"role": "assistant", "content": assistant_text})

                            # 成功处理后跳出 while 循环，处理下一个分段
                            time.sleep(1)
                            break

                        except RateLimitError as e:
                            # 如果速率限制错误，检查重试次数
                            if retries < max_retries:
                                retries += 1
                                print(f"遇到速率限制，等待 5 秒后重试，第 {retries} 次重试...")
                                time.sleep(5)  # 等待 5 秒后重试
                            else:
                                print("超过最大重试次数，跳过当前请求。")
                                break  # 超过最大重试次数后跳出循环

            # 将所有段落的响应拼接为最终结果
            print("\n".join(assistant_responses))
            return "\n".join(assistant_responses)

        else:
            # 获取分段后的文本
            text_segments = split_text_by_limit(original_text)
            text_dict = {}
            for i, segment in enumerate(text_segments):
                prefix = "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"
                text_dict[i] = segment

            # 存储最终返回的结果
            assistant_responses = []

            # 对每一段调用KIMI API获取响应
            for i, segment_text in text_dict.items():
                print(f"实际输入：{segment_text}")

                while True:  # 用循环来确保在遇到速率限制时重试
                    try:
                        # 调用KIMI的对话接口
                        response = client.chat.completions.create(
                            model=selected_model,
                            messages=[
                                {"role": "system",
                                 "content": "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"},
                                {"role": "user", "content": segment_text}
                            ],
                            temperature=0.8,
                            top_p=0.8
                        )

                        # 提取API返回的内容并添加到结果列表
                        assistant_text = response.choices[0].message.content
                        print(assistant_text)
                        assistant_responses.append(assistant_text)

                        # 成功处理后跳出 while 循环，处理下一个分段
                        time.sleep(1)
                        break

                    except RateLimitError as e:
                        # 如果速率限制错误，检查重试次数
                        if retries < max_retries:
                            retries += 1
                            print(f"遇到速率限制，等待 5 秒后重试，第 {retries} 次重试...")
                            time.sleep(5)  # 等待 5 秒后重试
                        else:
                            print("超过最大重试次数，跳过当前请求。")
                            break  # 超过最大重试次数后跳出循环

            # 将所有段落的响应拼接为最终结果
            print("\n".join(assistant_responses))
            return "\n".join(assistant_responses)

    @acquire_lock(api_lock_ali)
    def get_assistant_response_ali(self, original_text):
        # 从配置字典中获取百度 API 的认证信息和模型
        ali_config = self.config.get('阿里', {})
        access_key = ali_config.get('ACCESS_KEY')
        api_key = ali_config.get('SECRET_KEY')
        selected_model = ali_config.get('MODEL')
        max_retries = 5  # 最大重试次数
        retries = 0  # 当前重试次数

        print(f"阿里配置：\napi_key:{api_key}\nselected_model:{selected_model}")

        # 初始化KIMI API客户端
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        # 将 original_text 按 9000 字进行分段
        def split_text_by_limit(text):
            limit = int(self.text_processor.text_limit_entry.get())
            print(limit)
            segments = []
            current_segment = []
            current_length = 0

            # 按行拆分文本并逐行累加
            for line in text.splitlines():
                line_length = len(line)
                if current_length + line_length > limit:
                    # 达到限制，将当前段落存入列表
                    segments.append("\n".join(current_segment))
                    current_segment = [line]
                    current_length = line_length
                else:
                    # 累加到当前段落
                    current_segment.append(line)
                    current_length += line_length

            # 存入最后一段
            if current_segment:
                segments.append("\n".join(current_segment))

            return segments

        print(f"上下文模式:{self.text_processor.contextualize_output_var.get()}")

        is_contextualize = self.text_processor.contextualize_output_var.get()

        if is_contextualize:
            print("上下文模式")
            # 获取分段后的文本
            text_segments = split_text_by_limit(original_text)
            assistant_responses = []

            history = None

            # 如果没有提供历史记录，则初始化为一个空列表
            if history is None:
                history = [
                    {"role": "system",
                     "content": "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"}
                ]

                # 获取分段后的文本
                text_segments = split_text_by_limit(original_text)
                assistant_responses = []

                # 对每一段调用 KIMI API 获取响应
                for i, segment_text in enumerate(text_segments):
                    prefix = "请标注第一段故事：\n\n" if i == 0 else "继续标记：\n\n"
                    segment = prefix + segment_text
                    print(f"实际输入：{segment}")

                    # 在历史记录中加入新的用户输入
                    history.append({"role": "user", "content": segment})

                    while True:  # 用循环来确保在遇到速率限制时重试
                        try:
                            response = client.chat.completions.create(
                                model=selected_model,
                                messages=history,
                                temperature=0.8,
                                top_p=0.8
                            )

                            assistant_text = response.choices[0].message.content
                            print(assistant_text)
                            assistant_responses.append(assistant_text)

                            # 将助手的回答加入历史记录
                            history.append({"role": "assistant", "content": assistant_text})

                            # 成功处理后跳出 while 循环，处理下一个分段
                            time.sleep(1)
                            break

                        except RateLimitError as e:
                            # 如果速率限制错误，检查重试次数
                            if retries < max_retries:
                                retries += 1
                                print(f"遇到速率限制，等待 5 秒后重试，第 {retries} 次重试...")
                                time.sleep(5)  # 等待 5 秒后重试
                            else:
                                print("超过最大重试次数，跳过当前请求。")
                                break  # 超过最大重试次数后跳出循环

            # 将所有段落的响应拼接为最终结果
            print("\n".join(assistant_responses))
            return "\n".join(assistant_responses)

        else:
            print("非上下文模式")
            # 获取分段后的文本
            text_segments = split_text_by_limit(original_text)
            text_dict = {}
            for i, segment in enumerate(text_segments):
                prefix = "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"
                text_dict[i] = prefix + segment

            # 存储最终返回的结果
            assistant_responses = []

            # 对每一段调用KIMI API获取响应
            for i, segment_text in text_dict.items():
                print(f"实际输入：{segment_text}")

                while True:  # 用循环来确保在遇到速率限制时重试
                    try:
                        # 调用KIMI的对话接口
                        response = client.chat.completions.create(
                            model=selected_model,
                            messages=[
                                {"role": "user", "content": segment_text}
                            ],
                            temperature=0.8,
                            top_p=0.8
                        )

                        # 提取API返回的内容并添加到结果列表
                        assistant_text = response.choices[0].message.content
                        print(assistant_text)
                        assistant_responses.append(assistant_text)

                        # 成功处理后跳出 while 循环，处理下一个分段
                        time.sleep(1)
                        break

                    except RateLimitError as e:
                        # 如果速率限制错误，检查重试次数
                        if retries < max_retries:
                            retries += 1
                            print(f"遇到速率限制，等待 5 秒后重试，第 {retries} 次重试...")
                            time.sleep(5)  # 等待 5 秒后重试
                        else:
                            print("超过最大重试次数，跳过当前请求。")
                            break  # 超过最大重试次数后跳出循环

            # 将所有段落的响应拼接为最终结果
            print("\n".join(assistant_responses))
            return "\n".join(assistant_responses)

    def get_assistant_response_xunfei(self, original_text):
        # 从配置字典中获取讯飞 API 的认证信息和模型
        xunfei_config = self.config.get('讯飞', {})
        SPARKAI_APP_ID = xunfei_config.get('ACCESS_KEY')
        SPARKAI_API_SECRET = xunfei_config.get('SECRET_KEY')
        SPARKAI_API_KEY = xunfei_config.get('API_KEY')
        SPARKAI_DOMAIN = xunfei_config.get('MODEL')

        print(
            f"暂不支持讯飞,讯飞配置：\nAPP_ID：{SPARKAI_APP_ID}\nAPI_SECRET:{SPARKAI_API_SECRET}\nselected_model:{SPARKAI_DOMAIN}")

        # 根据不同模型选择不同的API URL
        SPARKAI_URL = "wss://spark-api.xf-yun.com/chat/pro-128k"  # 默认URL
        if SPARKAI_DOMAIN == "lite":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/v1.1/chat"
        elif SPARKAI_DOMAIN == "generalv3":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/v3.1/chat"
        elif SPARKAI_DOMAIN == "generalv3.5":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/v3.5/chat"
        elif SPARKAI_DOMAIN == "pro-128k":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/chat/pro-128k"
        elif SPARKAI_DOMAIN == "max-32k":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/chat/max-32k"
        elif SPARKAI_DOMAIN == "4.0Ultra":
            SPARKAI_URL = "wss://spark-api.xf-yun.com/v4.0/chat"

        raise ValueError("暂不支持讯飞API")

        """# 初始化 ChatSparkLLM 实例
        spark = ChatSparkLLM(
            spark_api_url=SPARKAI_URL,
            spark_app_id=SPARKAI_APP_ID,
            spark_api_key=SPARKAI_API_KEY,
            spark_api_secret=SPARKAI_API_SECRET,
            spark_llm_domain=SPARKAI_DOMAIN,
            streaming=False,
        )

        # 将 original_text 按设定值字数进行分段
        def split_text_by_limit(text):
            limit = int(self.text_processor.text_limit_entry.get())
            print(f"分段限制字数: {limit}")
            segments = []
            current_segment = []
            current_length = 0

            # 按行拆分文本并逐行累加
            for line in text.splitlines():
                line_length = len(line)
                if current_length + line_length > limit:
                    # 达到限制，将当前段落存入列表
                    segments.append("\n".join(current_segment))
                    current_segment = [line]
                    current_length = line_length
                else:
                    # 累加到当前段落
                    current_segment.append(line)
                    current_length += line_length

            # 存入最后一段
            if current_segment:
                segments.append("\n".join(current_segment))

            return segments

        # 获取分段后的文本
        print(f"上下文模式: {self.text_processor.contextualize_output_var.get()}")
        is_contextualize = self.text_processor.contextualize_output_var.get()

        if is_contextualize:
            print("启用上下文模式")
            text_segments = split_text_by_limit(original_text)
            messages = []
            assistant_responses = []

            for i, segment in enumerate(text_segments):
                # 构建用户消息
                prefix = "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话..."
                segment_text = prefix + segment

                # 使用 ChatMessage 来封装消息
                messages.append(ChatMessage(role="user", content=segment_text))

                # 发送给模型并获取响应
                response = spark.generate(messages)

                # 提取响应并加入上下文
                assistant_text = response.get("result", "")
                assistant_responses.append(assistant_text)
                messages.append(ChatMessage(role="assistant", content=assistant_text))

            # 拼接所有段落的响应
            return "\n".join(assistant_responses)

        else:
            print("不启用上下文模式")
            text_segments = split_text_by_limit(original_text)
            assistant_responses = []

            for segment in text_segments:
                #print(f"实际输入：{segment}")
                # 使用 ChatMessage 来封装消息
                messages = [ChatMessage(role="user", content=segment)]
                response = spark.generate(messages)  # 如果不需要回调
                assistant_text = response.get("result", "")
                assistant_responses.append(assistant_text)

            return "\n".join(assistant_responses)"""

    def get_assistant_response_tengxun(self, original_text):
        # 从配置字典中获取百度 API 的认证信息和模型
        tengxun_config = self.config.get('腾讯', {})
        access_key = tengxun_config.get('ACCESS_KEY')
        secret_key = tengxun_config.get('SECRET_KEY')
        selected_model = tengxun_config.get('MODEL')

        print(
            f"暂不支持腾讯,腾讯配置：\naccess_key：{access_key}\nsecret_key:{secret_key}\nselected_model:{selected_model}")
        print("暂不支持腾讯")

        raise ValueError("暂不支持腾讯API")

    def get_assistant_response_genduo(self, original_text):
        assistant_text = self.text_processor.more_AI_entry.get()
        print(assistant_text)
        return assistant_text

    def get_assistant_response_custom(self, original_text):
        """根据用户选择的AI选项，从自定义配置中获取相关配置信息"""
        select_option = self.text_processor.select_AI_var.get()
        max_retries = 5  # 最大重试次数
        retries = 0  # 当前重试次数

        # 从配置文件读取
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)

            # 获取自定义项中的所有配置
            custom_configs = config_data.get('config', {}).get('自定义', {})

            # 检查当前选择的选项是否在自定义配置中
            if select_option in custom_configs:
                selected_config = custom_configs[select_option]
                base_url = selected_config.get('ACCESS_KEY', '')
                api_key = selected_config.get('SECRET_KEY', '')
                selected_model = selected_config.get('MODEL', '')
            else:
                # 如果选项不存在，提供默认值或抛出异常
                print(f"警告: 选项 '{select_option}' 不在自定义配置中！")
                base_url, api_key, selected_model = '', '', ''
        else:
            print("错误: 找不到配置文件 'config.json'")
            base_url, api_key, selected_model = '', '', ''

        # 打印调试信息
        print(f"选择的配置 ({select_option})：\nbase_url: {base_url}\napi_key: {api_key}\nMODEL: {selected_model}")

        # 初始化KIMI API客户端
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

        # 将 original_text 按 9000 字进行分段
        def split_text_by_limit(text):
            limit = int(self.text_processor.text_limit_entry.get())
            print(limit)
            segments = []
            current_segment = []
            current_length = 0

            # 按行拆分文本并逐行累加
            for line in text.splitlines():
                line_length = len(line)
                if current_length + line_length > limit:
                    # 达到限制，将当前段落存入列表
                    segments.append("\n".join(current_segment))
                    current_segment = [line]
                    current_length = line_length
                else:
                    # 累加到当前段落
                    current_segment.append(line)
                    current_length += line_length

            # 存入最后一段
            if current_segment:
                segments.append("\n".join(current_segment))

            return segments

        print(f"上下文模式:{self.text_processor.contextualize_output_var.get()}")

        is_contextualize = self.text_processor.contextualize_output_var.get()

        if is_contextualize:
            print("上下文模式")
            # 获取分段后的文本
            text_segments = split_text_by_limit(original_text)
            assistant_responses = []

            history = None

            # 如果没有提供历史记录，则初始化为一个空列表
            if history is None:
                history = [
                    {"role": "system",
                     "content": "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"}
                ]

                # 获取分段后的文本
                text_segments = split_text_by_limit(original_text)
                assistant_responses = []

                # 对每一段调用 KIMI API 获取响应
                for i, segment_text in enumerate(text_segments):
                    prefix = "请标注第一段故事：\n\n" if i == 0 else "继续标记：\n\n"
                    segment = prefix + segment_text
                    print(f"实际输入：{segment}")

                    # 在历史记录中加入新的用户输入
                    history.append({"role": "user", "content": segment})

                    while True:  # 用循环来确保在遇到速率限制时重试
                        try:
                            response = client.chat.completions.create(
                                model=selected_model,
                                messages=history,
                                temperature=0.8,
                                top_p=0.8
                            )

                            assistant_text = response.choices[0].message.content
                            print(assistant_text)
                            assistant_responses.append(assistant_text)

                            # 将助手的回答加入历史记录
                            history.append({"role": "assistant", "content": assistant_text})

                            # 成功处理后跳出 while 循环，处理下一个分段
                            time.sleep(1)
                            break

                        except RateLimitError as e:
                            # 如果速率限制错误，检查重试次数
                            if retries < max_retries:
                                retries += 1
                                print(f"遇到速率限制，等待 5 秒后重试，第 {retries} 次重试...")
                                time.sleep(5)  # 等待 5 秒后重试
                            else:
                                print("超过最大重试次数，跳过当前请求。")
                                break  # 超过最大重试次数后跳出循环

            # 将所有段落的响应拼接为最终结果
            print("\n".join(assistant_responses))
            return "\n".join(assistant_responses)

        else:
            print("非上下文模式")
            # 获取分段后的文本
            text_segments = split_text_by_limit(original_text)
            text_dict = {}
            for i, segment in enumerate(text_segments):
                prefix = "以下故事中使用「」符号表示角色说的话，对以下故事按如下标准进行标注：判断用「」符号括起来的行是哪个角色说的话并在行前以\n“角色名@：「对话内容」”\n的格式标注他的名称或代称，不要落下“我”说的话（在“我”说的话前面把“我”作为角色名），没有名字的角色标注职业或其他角色对其的称呼或路人等名称并用相同的格式在行前标注。不要落下任何被「」符号括起来的内容。删除没被「」符号括起来的内容。\n\n"
                text_dict[i] = prefix + segment

            # 存储最终返回的结果
            assistant_responses = []

            # 对每一段调用KIMI API获取响应
            for i, segment_text in text_dict.items():
                print(f"实际输入：{segment_text}")

                while True:
                    try:
                        # 调用KIMI的对话接口
                        response = client.chat.completions.create(
                            model=selected_model,
                            messages=[
                                {"role": "user", "content": segment_text}
                            ]
                        )

                        # 提取API返回的内容并添加到结果列表
                        assistant_text = response.choices[0].message.content
                        print(assistant_text)
                        assistant_responses.append(assistant_text)

                        # 成功处理后跳出 while 循环，处理下一个分段
                        time.sleep(1)
                        break

                    except RateLimitError as e:
                        # 如果速率限制错误，检查重试次数
                        if retries < max_retries:
                            retries += 1
                            print(f"遇到速率限制，等待 5 秒后重试，第 {retries} 次重试...")
                            time.sleep(5)  # 等待 5 秒后重试
                        else:
                            print("超过最大重试次数，跳过当前请求。")
                            break  # 超过最大重试次数后跳出循环

            # 将所有段落的响应拼接为最终结果
            print("\n".join(assistant_responses))
            return "\n".join(assistant_responses)

    def construct_text(self, original_text, assistant_text):
        """构建新的文本，基于 assistant_text 中的信息对原始文本标注"""
        original_lines = original_text.splitlines()
        assistant_lines = assistant_text.splitlines()

        # 创建一个字典以便快速查找API返回的行
        assistant_dict = {}
        for line in assistant_lines:
            match = re.search(r'^(.*?)@：[「」](.*?)[「」](.*)$', line)
            if match:
                prefix = match.group(1).strip()
                dialogue = match.group(2).strip()
                assistant_dict[dialogue] = prefix  # 记录前缀

        # 构建新的文本
        new_lines = []
        for line in original_lines:
            dialogues = re.findall(r'「(.*?)」', line)
            for dialogue in dialogues:
                if dialogue in assistant_dict:
                    prefix = assistant_dict[dialogue]
                    line = line.replace(f'「{dialogue}」', f'{prefix}@：「{dialogue}」')
            new_lines.append(line)

        # 更新进度
        self.text_processor.current_task += 1  # 先加1
        print(self.text_processor.current_task)
        self.text_processor.update_progress()

        return "\n".join(new_lines)

    def calculate_annotation_ratio(self, original_text, constructed_text):
        """计算原文被「」括起来的对话行和构造文本中的标注行之间的比例"""
        original_dialogues = re.findall(r'「(.*?)」', original_text)
        annotated_dialogues = re.findall(r'@：「(.*?)」', constructed_text)

        ratio = len(annotated_dialogues) / len(original_dialogues) if original_dialogues else 0
        return ratio

    def export_results(self, best_text, best_ratio, done_event, chapter_index):
        """导出标注结果到文件，并根据条件更新相关内容"""
        # 预处理 best_text 中的特殊字符
        # 将 @ 替换为 @，：替换为：，「替换为「，」替换为」
        best_text = best_text.replace('@', '@').replace('：', '：').replace('「', '「').replace('」', '」')

        # 创建用于保存标注结果的文件夹路径
        folder_path = os.path.join(self.text_processor.folder_path_var.get(), "Chapters_marked")
        os.makedirs(folder_path, exist_ok=True)

        # 使用 chapter_combobox 的选项列表获取章节全名
        chapter_full_name = self.text_processor.chapter_combobox["values"][chapter_index]

        # 确定文件名：根据是否选择“全文”设置不同的文件名
        if self.text_processor.chapter_combobox.get() == "全文":
            # 章节名来自 `process_dialogue` 函数传递的参数
            file_name = f"{chapter_full_name}_marked.txt"
        else:
            file_name = f"{self.text_processor.chapter_combobox.get()}_marked.txt"
        file_path = os.path.join(folder_path, file_name)

        # 将结果保存到文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(best_text)

        # 更新 TextPreprocessor 的 chapter_marked_contents 字典
        self.text_processor.chapter_marked_contents[chapter_index] = best_text

        # 清空 `results_dict` 以便下一次标注循环
        self.results_dict.clear()

        print(f"文件已保存，标注比例：{best_ratio * 100:.2f}%")

        # 标注完成，设置完成事件
        if done_event:
            done_event.set()
            print("线程完成")


class DocumentProcessorApp:
    def __init__(self, frame, text_preprocessor):
        self.text_preprocessor = text_preprocessor
        self.parent = frame
        self.button_frame = self.text_preprocessor.process_button_frame

        # 移除 input_path 相关标签和控件
        # self.input_label.grid_remove()
        # self.input_path.grid_remove()

        # 获取 TextPreprocessor 的 text_box 内容作为输入
        self.input_content = self.text_preprocessor.text_box.get("1.0", tk.END)

        # 初始化 output_dir
        self.output_dir = ""  # 也可以设置为 os.path.join(...) 的默认路径

        # 将分句符号及其他控件添加到 TextPreprocessor 的滚动画布
        self.add_controls_to_canvas()

    def add_controls_to_canvas(self):

        # 分段符行：
        # self.symbol_frame = tk.Frame(self.parent)
        # self.symbol_frame.grid(row=12, column=0, sticky="nsew")

        self.symbol_label = tk.Label(self.parent, text="分句符：")
        self.symbol_label.grid(row=14, column=0, padx=5, pady=5, sticky="w")

        self.symbol_entry = tk.Entry(self.parent, width=13)
        self.symbol_entry.insert(0, '|')  # 设置默认值为 "|"
        self.symbol_entry.grid(row=14, column=1, padx=5, pady=5, sticky="w")

        self.custom_logic_var = tk.BooleanVar(value=True)  # 默认勾选
        self.custom_logic_checkbox = tk.Checkbutton(
            self.parent, text="不在同一段内添加分句符", variable=self.custom_logic_var
        )
        self.custom_logic_checkbox.grid(row=15, column=0, columnspan=3, padx=5, sticky="w")

        self.blank_frame2 = tk.Frame(self.button_frame, width=15)
        self.blank_frame2.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.process_button = tk.Button(
            self.parent, text="重新分配对话", command=lambda: self.process_document(update_pg=False)
        )
        self.process_button.grid(row=18, column=1, padx=5, sticky="e")

    def process_document(self, update_pg):
        # 直接使用 TextPreprocessor 提供的 input_content 和 output_dir 进行处理
        input_content = self.text_preprocessor.text_box.get("1.0", tk.END)
        output_dir = self.output_dir
        custom_symbol = self.symbol_entry.get().strip()

        # 每次调用时获取当前章节的名称，并构造 output_dir
        chapter_name = self.text_preprocessor.chapter_combobox.get()
        print(chapter_name)
        output_dir = os.path.join(
            self.text_preprocessor.folder_path_var.get(), "Chapters_tts", chapter_name
        )
        os.makedirs(output_dir, exist_ok=True)  # 确保目录存在

        # print(custom_symbol, input_content)

        if not input_content or not output_dir:
            messagebox.showerror("Error", "Please specify both input file and output directory.")
            return

        try:
            # 检查并删除现有的 .txt 文件
            txt_files = glob.glob(os.path.join(output_dir, "*.txt"))
            for txt_file in txt_files:
                try:
                    os.remove(txt_file)
                except OSError as e:
                    messagebox.showerror("Error", f"无法删除文件 {txt_file}: {str(e)}")
                    return

            content = input_content

            blocks = content.split('\n\n')
            tags = {}
            order_table_lines = []
            categorized_files = []

            # Add a counter for "旁白"
            narration_counter = 1
            last_tag = None  # 用于记录上一个角色
            last_order_tag = None  # 用于记录顺序表上一个角色

            # Dictionary to store the last paragraph for each character (for custom logic)
            last_paragraph = {}

            # 根据复选框决定是否启用自定义逻辑
            use_custom_logic = custom_symbol

            # First create the order table
            for i, block in enumerate(blocks):
                block = block.strip()
                if '@：「' in block:
                    tag = block.split('@：「')[0].strip()
                    if tag not in tags:
                        tags[tag] = 0
                    if not use_custom_logic or last_order_tag != tag:  # 避免重复写入同一角色
                        tags[tag] += 1
                        sequence = tags[tag]
                        order_table_lines.append(f"{tag} {sequence}")
                        last_order_tag = tag  # 更新上一个角色
                else:
                    if not use_custom_logic or last_order_tag != "旁白":  # 避免重复写入旁白
                        order_table_lines.append(f"旁白 {narration_counter}")
                        narration_counter += 1
                        last_order_tag = "旁白"  # 更新上一个角色

            # Save the order table to a file
            order_table_path = os.path.join(output_dir, "顺序表.txt")
            with open(order_table_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(order_table_lines))

            # Create categorized files
            for block in blocks:
                block = block.strip()
                if '@：「' in block:
                    tag = block.split('@：「')[0].strip()
                    cleaned_lines = [line.split('@：「')[1].strip() for line in block.split('\n') if '@：「' in line]
                    new_paragraph = '\n'.join(cleaned_lines) + custom_symbol

                    categorized_file_path = os.path.join(output_dir, f"{tag}.txt")

                    if use_custom_logic:
                        # Check if last paragraph exists for the current tag
                        if last_tag == tag:
                            # Remove the custom symbol from the previous paragraph
                            with open(categorized_file_path, 'r+', encoding='utf-8') as f:
                                content = f.read()
                                f.seek(0)
                                f.write(content.rstrip(custom_symbol + '\n\n') + '\n\n')

                    # Append the new paragraph
                    with open(categorized_file_path, 'a', encoding='utf-8') as f:
                        f.write(new_paragraph + '\n\n')
                    last_paragraph[tag] = new_paragraph  # Update last paragraph
                    last_tag = tag  # Update last tag

                    if categorized_file_path not in categorized_files:
                        categorized_files.append(categorized_file_path)
                else:
                    categorized_file_path = os.path.join(output_dir, "旁白.txt")
                    new_paragraph = f"{block}{custom_symbol}"

                    if use_custom_logic:
                        # Check if last paragraph exists for narration
                        if last_tag == "旁白":
                            with open(categorized_file_path, 'r+', encoding='utf-8') as f:
                                content = f.read()
                                f.seek(0)
                                f.write(content.rstrip(custom_symbol + '\n\n') + '\n\n')

                    # Append the new paragraph
                    with open(categorized_file_path, 'a', encoding='utf-8') as f:
                        f.write(new_paragraph + '\n\n')
                    last_paragraph["旁白"] = new_paragraph
                    last_tag = "旁白"

                    if categorized_file_path not in categorized_files:
                        categorized_files.append(categorized_file_path)

            # 更新进度
            if update_pg:
                # self.text_preprocessor.current_task += 1  # 先加1
                print(self.text_preprocessor.current_task)
                self.text_preprocessor.progress_bar_done = True
                self.text_preprocessor.update_progress()

            # Display success message with list of created files
            messagebox.showinfo("Success",
                                f"Order table saved to {order_table_path}\nCategorized files created:\n" + "\n".join(
                                    categorized_files))

        except Exception as e:
            messagebox.showerror("Error", str(e))


class CharacterExtractor:
    def __init__(self, text_preprocessor, all_characters):
        self.text_preprocessor = text_preprocessor
        self.all_characters = all_characters
        self.character_lines = []

        # 创建替换按钮
        self.replace_button = tk.Button(
            self.text_preprocessor.canvas_frame,
            text="替换角色",
            command=self.replace_characters
        )
        self.replace_button.grid(row=18, column=0, sticky="w", padx=5, pady=5)
        self.replace_button.bind("<MouseWheel>", self.text_preprocessor._on_mouse_wheel)  # Windows
        self.replace_button.bind("<Button-4>", self.text_preprocessor._on_mouse_wheel)
        self.replace_button.bind("<Button-5>", self.text_preprocessor._on_mouse_wheel)

        # 创建角色显示区域
        self.character_frame = tk.Frame(self.text_preprocessor.canvas_frame)
        self.character_frame.grid(row=19, column=0, columnspan=2, sticky="w")

        # 创建一个容纳角色的主 Frame
        self.roles_container = tk.Frame(self.character_frame)
        self.roles_container.pack(pady=5)  # 添加一些间距

        self.combos = []  # 存储所有下拉框的引用

    def extract_characters(self):
        # 获取文本框内容
        text_content = self.text_preprocessor.text_box.get("1.0", tk.END)
        lines = text_content.splitlines()
        self.character_lines.clear()  # 清空之前的角色名称

        for line in lines:
            if '@：「' in line:
                character_name = line.split('@：「')[0].strip()
                if character_name and character_name not in self.character_lines:
                    self.character_lines.append(character_name)

    def create_character_display(self):
        self.extract_characters()  # 提取角色名称

        # 清空角色容器中的控件
        for widget in self.roles_container.winfo_children():
            widget.destroy()

        # 在角色容器中显示所有角色
        self.combos.clear()  # 清空之前存储的下拉框引用
        for idx, character in enumerate(self.character_lines):
            label = tk.Label(self.roles_container, text=f"[{character}]", anchor="w", width=9)
            label.grid(row=idx, column=0, sticky="w")

            label2 = tk.Label(self.roles_container, text="替换为")
            label2.grid(row=idx, column=1, sticky="w")

            # 创建下拉框
            combo_frame = tk.Frame(self.roles_container)
            combo_frame.grid(row=idx, column=2, columnspan=2, sticky="w")
            combo = ttk.Combobox(combo_frame, values=self.character_lines, width=10)
            combo.set(character)  # 设置默认选中为当前角色
            combo.grid(row=idx, column=2, sticky="w", padx=5, pady=1)
            self.combos.append(combo)  # 将下拉框存储到列表中

        self.roles_container.bind("<MouseWheel>", self.text_preprocessor._on_mouse_wheel)  # Windows
        self.roles_container.bind("<Button-4>", self.text_preprocessor._on_mouse_wheel)  # macOS 向上滚动
        self.roles_container.bind("<Button-5>", self.text_preprocessor._on_mouse_wheel)  # macOS 向下滚动

        for widget in self.roles_container.winfo_children():
            widget.bind("<MouseWheel>", self.text_preprocessor._on_mouse_wheel)  # Windows
            widget.bind("<Button-4>", self.text_preprocessor._on_mouse_wheel)  # macOS 向上滚动
            widget.bind("<Button-5>", self.text_preprocessor._on_mouse_wheel)  # macOS 向下滚动

    def replace_characters(self):
        # 获取文本框内容
        text_content = self.text_preprocessor.text_box.get("1.0", tk.END)
        new_content = text_content

        # 替换角色名
        for idx, character in enumerate(self.character_lines):
            # 获取当前下拉框选定的角色名
            selected_character = self.combos[idx].get()
            # 构建要替换的字符串
            original_string = f"{character}@：「"
            new_string = f"{selected_character}@：「"
            new_content = new_content.replace(original_string, new_string)

        # 更新文本框内容
        self.text_preprocessor.text_box.delete("1.0", tk.END)  # 清空文本框
        self.text_preprocessor.text_box.insert("1.0", new_content)  # 插入替换后的内容

        self.create_character_display()


class VoiceGeneratorApp:
    def __init__(self, root, folder_path_var, start_menu):
        # 初始化Gradio客户端
        self.client = None

        self.root = root
        self.folder_path_config = folder_path_var
        self.start_menu = start_menu  # 保存 StartMenu 实例

        self.sovits_model_list = []  # 存储SoVITS模型列表
        self.gpt_model_list = []  # 存储GPT模型列表
        self.row_variables = {}
        self.voice_threads = []  # 用于存储生成语音的线程
        self.character_folder_path = {}  # 用于存储从配置文件加载的character_folder字典

        # 在初始化时调用 populate_folder_dropdown_gen 方法
        self.populate_folder_dropdown_gen()

        # 顶部路径框和浏览按钮容器
        self.path_frame = tk.Frame(self.root)
        self.path_frame.pack(pady=10, fill="x")

        # 新增 "导入配置" 按钮
        self.import_button = tk.Button(self.path_frame, text="导入配置", command=self.import_all_configs)
        self.import_button.pack(side=tk.LEFT, padx=5)

        # 新增 "导出配置" 按钮
        self.export_button = tk.Button(self.path_frame, text="导出配置", command=self.export_all_configs)
        self.export_button.pack(side=tk.LEFT, padx=5)

        self.path_label = tk.Label(self.path_frame, text="选择文件夹:")
        self.path_label.pack(side=tk.LEFT)

        # 文件夹路径下拉框
        self.folder_path_var = tk.StringVar()
        self.folder_combobox = ttk.Combobox(self.path_frame, textvariable=self.folder_path_var, width=50)
        self.folder_combobox.pack(side=tk.LEFT, padx=5, fill="x", expand=True)

        # 浏览按钮
        self.browse_button = tk.Button(self.path_frame, text="浏览...", command=self.browse_main_folder)
        self.browse_button.pack(side=tk.LEFT, padx=5)

        # 刷新列表按钮
        self.refresh_list_button = tk.Button(self.path_frame, text="刷新列表", command=self.refresh_folder_list)
        self.refresh_list_button.pack(side=tk.LEFT, padx=5)

        self.refresh_model_button = tk.Button(self.path_frame, text="刷新模型", command=self.refresh_model_list)
        self.refresh_model_button.pack(side=tk.LEFT, padx=5)

        # 创建顶层框架用于放置头部和滚动区域
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        # 创建表头画布
        self.header_canvas = tk.Canvas(self.main_frame, height=30, highlightthickness=0)
        self.header_frame = tk.Frame(self.header_canvas)

        # 创建列表画布
        self.list_canvas = tk.Canvas(self.main_frame, highlightthickness=0)
        self.scroll_frame = tk.Frame(self.list_canvas)

        # 创建滚动条
        self.horizontal_scrollbar = tk.Scrollbar(self.main_frame, orient="horizontal",
                                                 command=self.sync_scroll_horizontal)
        self.vertical_scrollbar = tk.Scrollbar(self.main_frame, orient="vertical", command=self.list_canvas.yview)

        # 绑定配置变化
        self.scroll_frame.bind("<Configure>",
                               lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.header_frame.bind("<Configure>",
                               lambda e: self.header_canvas.configure(scrollregion=self.header_canvas.bbox("all")))

        # 将滚动区域添加到画布中
        self.header_window = self.header_canvas.create_window((0, 0), window=self.header_frame, anchor="nw")
        self.list_window = self.list_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        # 布局
        self.header_canvas.grid(row=0, column=0, sticky="ew")
        self.list_canvas.grid(row=1, column=0, sticky="nsew")
        self.horizontal_scrollbar.grid(row=2, column=0, sticky="ew")
        self.vertical_scrollbar.grid(row=1, column=1, sticky="ns")

        # 配置滚动条
        self.list_canvas.configure(xscrollcommand=self.horizontal_scrollbar.set,
                                   yscrollcommand=self.vertical_scrollbar.set)

        # 创建表头和内容
        self.create_header(self.header_frame)

        # 设置主框架的权重以支持动态调整
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

        # 在最底部添加frame和"生成完整语音"按钮
        self.bottom_frame = tk.Frame(self.root)
        self.bottom_frame.pack(fill=tk.X, pady=10)

        self.merge_button = tk.Button(self.bottom_frame, text="合并语音", command=self.run_merge_audio_files)
        self.merge_button.pack(side=tk.LEFT, padx=10)

        # 创建进度百分比标签
        self.progress_percentage_label = tk.Label(self.bottom_frame, text="进度: 0%")
        self.progress_percentage_label.pack(side=tk.LEFT, padx=5)

        # 创建进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.bottom_frame, variable=self.progress_var, maximum=100, length=300)
        self.progress_bar.pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)

        # 创建时间显示标签
        self.time_label = tk.Label(self.bottom_frame, text="运行时间|剩余时间: 00:00:00|00:00:00")
        self.time_label.pack(side=tk.LEFT, padx=1)

        self.generate_button = tk.Button(self.bottom_frame, text="生成语音", command=self.start_generate_all_voices)
        self.generate_button.pack(side=tk.LEFT, padx=10)

        # 初始化任务参数
        self.total_tasks = 0  # 总任务量
        self.current_task = 0  # 当前任务量
        self.start_time = None  # 任务开始时间
        self.progress_bar_done = True

        # 加载工作目录的子文件夹并设置默认选项
        self.load_folders()

        # 在下拉框值发生变化时调用 display_txt_files 方法
        self.folder_combobox.bind("<<ComboboxSelected>>", self.on_folder_selected)

        self.list_canvas.bind("<MouseWheel>", self.scroll_canvas)
        self.list_canvas.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
        self.list_canvas.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

        # 如果在启动时 folder_path_var 有有效路径，传递该路径
        initial_folder = self.folder_path_var.get()
        if initial_folder:
            self.display_txt_files(initial_folder)

    def populate_folder_dropdown_gen(self, event=None):
        """从config.json加载character_folder并存储到self.character_folder_path字典"""
        # print("populate_folder_dropdown_gen")
        config_file = "config.json"
        if os.path.exists(config_file):
            # 读取配置文件
            with open(config_file, 'r', encoding='utf-8') as file:
                config_data = json.load(file)

            # 获取character_folder并更新到字典
            character_folders = config_data.get('config', {}).get('character_folder', [])
            if character_folders:
                # 更新到self.character_folder_path字典
                self.character_folder_path = {i: folder for i, folder in enumerate(character_folders)}
            else:
                print(f"配置文件中未找到 'character_folder' 项！")
        else:
            print(f"配置文件 {config_file} 不存在!")

    def on_folder_selected(self, event):
        """下拉框选择新路径时调用的函数"""
        selected_folder = self.folder_combobox.get()
        if selected_folder:
            self.clear_current_display()
            self.display_txt_files(selected_folder)  # 传入新的文件夹路径
            #self.refresh_model_list()

    def set_client(self, client):
        self.client = client
        # print(f"Client set in VoiceGeneratorApp.{self.client}")
        self.refresh_model_list()

    def load_folders(self):
        """加载 Chapters_tts 文件夹下的子文件夹路径作为下拉框选项"""
        # print("刷新了3")

        # 获取 StartMenu 中的工作文件夹路径
        base_folder = self.start_menu.folder_path_var.get()  # 从 start_menu 获取工作文件夹路径

        if not base_folder:  # 如果没有设置文件夹路径，给出警告或提示
            print("未设置工作文件夹路径，请先设置")
            return

        # 目标文件夹路径：Chapters_tts
        chapters_folder = os.path.join(base_folder, "Chapters_tts")

        # 如果 Chapters_tts 文件夹不存在，则创建
        if not os.path.exists(chapters_folder):
            os.makedirs(chapters_folder)

        # 获取所有子文件夹
        subfolders = [f.path for f in os.scandir(chapters_folder) if f.is_dir()]

        # 默认选择末尾为“全文”的文件夹
        default_folder = None
        for folder in subfolders:
            if folder.endswith("全文"):
                default_folder = folder
                break

        # 获取当前已选择的文件夹（如果有）
        current_selection = self.folder_combobox.get()

        # 更新下拉框的选项
        self.folder_combobox['values'] = subfolders

        # 如果 subfolders 列表非空
        if subfolders:
            # 如果当前选中的文件夹不在更新后的选项中，或者它是“全文”文件夹
            if current_selection not in subfolders:
                # 如果存在文件夹，则选择默认的“全文”文件夹（如果有）
                self.folder_combobox.set(default_folder or subfolders[0])
            else:
                # 如果当前选中的文件夹存在于更新后的选项中，则不做更改
                self.folder_combobox.set(current_selection)
        else:
            # 如果没有子文件夹，清空下拉框
            self.folder_combobox.set('')

        # 检查 self.scroll_frame 是否有控件，如果没有则调用 display_txt_files
        if not self.scroll_frame.winfo_children():  # 如果 scroll_frame 中没有控件
            #print("刷新角色")
            folder_path = self.folder_path_var.get()  # 获取当前文件夹路径
            if folder_path and os.path.exists(folder_path) and os.path.isdir(folder_path):  # 检查是否为有效的文件夹路径
                self.display_txt_files(folder_path)  # 调用 display_txt_files 函数并传递路径
            else:
                print(f"无效的路径: {folder_path}")  # 输出无效路径的提示信息

    def update_progress(self):
        # 强制完成进度条
        if self.progress_bar_done:
            self.current_task = self.total_tasks

        # 确保当前任务量不会超过总任务量
        if self.current_task > self.total_tasks:
            return

        # 计算进度百分比
        progress_percentage = (self.current_task / self.total_tasks) * 100
        self.progress_var.set(progress_percentage)
        self.progress_percentage_label.config(text=f"进度: {int(progress_percentage)}%")

        # 计算运行时间
        elapsed_time = time.time() - self.start_time
        remaining_time = (elapsed_time / self.current_task) * (
                self.total_tasks - self.current_task) if self.current_task > 0 else 0

        # 格式化时间显示
        elapsed_time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
        remaining_time_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))

        # 更新时间标签
        self.time_label.config(text=f"运行时间|剩余时间: {elapsed_time_str}|{remaining_time_str}")

        # 如果当前任务未完成，继续每秒更新进度
        if self.current_task < self.total_tasks:
            self.root.after(1000, self.update_progress)

    def import_all_configs(self):
        """导入所有配置文件并更新到对应行"""
        folder_path = self.folder_path_var.get()

        if not folder_path:
            messagebox.showerror("错误", "请选择一个有效的文件夹路径")
            return

        try:
            # 遍历文件夹中的所有 .json 文件
            for file_name in os.listdir(folder_path):
                if file_name.endswith(".json"):
                    # 获取行名称（去除文件扩展名）
                    row_name = os.path.splitext(file_name)[0]

                    # 打开并加载配置文件
                    with open(os.path.join(folder_path, file_name), 'r', encoding='utf-8') as f:
                        config_data = json.load(f)

                    # 找到与文件名匹配的行，并更新行变量
                    for idx, row_vars in self.row_variables.items():
                        if self.row_variables[idx]['label_name'].cget("text") == row_name:
                            self.update_row_variables(idx, config_data)
                            break

            messagebox.showinfo("成功", "所有配置已成功导入")
        except Exception as e:
            messagebox.showerror("错误", f"导入配置文件时出错: {str(e)}")

    def update_row_variables(self, idx, config_data):
        """根据导入的配置更新指定行的变量，忽略缺失值"""
        row_vars = self.row_variables[idx]

        # 检查每个键是否存在于config_data中，如果存在则更新对应的变量
        if 'top_k' in config_data:
            row_vars['top_k'].set(config_data['top_k'])
        if 'top_p' in config_data:
            row_vars['top_p'].set(config_data['top_p'])
        if 'temperature' in config_data:
            row_vars['temperature'].set(config_data['temperature'])
        if 'speed' in config_data:
            row_vars['speed'].set(config_data['speed'])
        if 'ref_free' in config_data:
            row_vars['ref_free'].set(config_data['ref_free'])
        if 'if_freeze' in config_data:
            row_vars['if_freeze'].set(config_data['if_freeze'])
        if 'sovits' in config_data:
            row_vars['sovits'].set(config_data['sovits'])
        if 'gpt' in config_data:
            row_vars['gpt'].set(config_data['gpt'])
        if 'ref_wav_path' in config_data:
            row_vars['ref_wav_path'].set(config_data['ref_wav_path'])
        if 'prompt' in config_data:
            row_vars['prompt'].set(config_data['prompt'])
        if 'ref_language' in config_data:
            row_vars['ref_language'].set(config_data['ref_language'])
        if 'text_language' in config_data:
            row_vars['text_language'].set(config_data['text_language'])
        if 'cut_method' in config_data:
            row_vars['cut_method'].set(config_data['cut_method'])
        if 'delimiter' in config_data:
            row_vars['delimiter'].set(config_data['delimiter'])

    def export_all_configs(self):
        """导出所有行的配置到 .json 文件"""
        exported_files = []  # 用于记录导出的文件路径
        for idx, row_vars in self.row_variables.items():
            if idx == 0:
                # 跳过第0行，因为第0行是默认行
                continue

            try:
                # 调用 export_all_character_config 方法导出当前行的配置
                config_path = self.export_all_character_config(
                    folder_path="当前角色",  # 使用 UI 中选择的路径
                    selected_option=self.row_variables[idx]['label_name'].cget("text"),  # 使用行的名称作为导出的配置文件名
                    top_k=row_vars['top_k'],
                    top_p=row_vars['top_p'],
                    temperature=row_vars['temperature'],
                    speed=row_vars['speed'],
                    ref_free=row_vars['ref_free'],
                    if_freeze=row_vars['if_freeze'],
                    sovits=row_vars['sovits'],
                    gpt=row_vars['gpt'],
                    ref_wav_path=row_vars['ref_wav_path'],
                    prompt=row_vars['prompt'],
                    ref_language=row_vars['ref_language'],
                    text_language=row_vars['text_language'],
                    cut_method=row_vars['cut_method'],
                    delimiter=row_vars['delimiter'],
                    show_message=False  # 批量导出时不显示每个导出的消息框
                )
                exported_files.append(config_path)  # 保存成功导出的文件路径
            except Exception as e:
                messagebox.showerror("错误", f"导出配置文件时出错: {str(e)}")

        # 导出完成后，显示一次性消息框，列出所有导出的文件
        if exported_files:
            messagebox.showinfo(
                "导出完成",
                f"全部角色配置已导出到:\n{', '.join(exported_files)}"
            )

    def start_generate_all_voices(self):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        """在新线程中调用生成语音的函数"""
        voice_thread = threading.Thread(target=self.generate_all_voices)
        voice_thread.start()
        self.voice_threads.append(voice_thread)

    @check_using_api
    def generate_all_voices(self):
        # 保存控件状态
        original_states_menu = {}
        controls_to_disable = [
            self.import_button, self.refresh_list_button,
            self.browse_button, self.generate_button, self.merge_button
        ]

        # 保存当前状态并禁用控件
        for control in controls_to_disable:
            original_states_menu[control] = control.cget("state")
            control.config(state="disabled")

        # 禁用文件夹路径下拉框
        original_states_menu[self.folder_combobox] = self.folder_combobox.cget("state")
        self.folder_combobox.config(state="disabled")

        # 初始化进度条参数
        self.progress_bar_done = False
        self.current_task = 0  # 当前任务量
        self.start_time = time.time()  # 任务开始时间初始化为当前时间

        # 读取“顺序表.txt”文件并设置总任务量
        order_file_path = os.path.join(self.folder_path_var.get(), "顺序表.txt")
        if os.path.exists(order_file_path):
            with open(order_file_path, 'r', encoding='utf-8') as file:
                self.total_tasks = sum(1 for line in file) + 1  # 行数加1作为总任务量
                print(self.total_tasks)
        else:
            self.total_tasks = 0  # 如果文件不存在，则设置为0

        self.progress_bar['value'] = 0  # 重置进度条
        self.progress_percentage_label.config(text="进度: 0%")  # 重置进度百分比
        self.update_progress()  # 更新进度条显示

        """生成所有非默认行的语音（排除第0行）"""
        failed_rows = []  # 用于记录出错的行名

        for idx in range(1, len(self.row_variables)):  # 从第1行开始，排除第0行
            row_vars = self.row_variables[idx]
            try:
                # 获取指定行的所有控件
                row_controls = self.scroll_frame.grid_slaves(row=idx)

                # 存储控件的原始状态
                original_states = {}

                for control in row_controls:
                    if isinstance(control, tk.Entry):
                        original_states[control] = control.cget("state")  # 获取原始状态
                        control.config(state="disabled")  # 禁用控件
                    elif isinstance(control, tk.Button):
                        original_states[control] = control.cget("state")
                        control.config(state="disabled")
                    elif isinstance(control, ttk.Combobox):
                        original_states[control] = control["state"]
                        control.config(state="disabled")
                    elif isinstance(control, tk.Checkbutton):
                        original_states[control] = control.cget("state")
                        control.config(state="disabled")
                    elif isinstance(control, tk.OptionMenu):
                        original_states[control] = control.cget("state")
                        control.config(state="disabled")

                # 创建线程并运行 generate_character_voice，传入对应的变量
                thread = threading.Thread(target=self.generate_character_voice,
                                          args=(row_vars['sovits'], row_vars['gpt'], row_vars['ref_wav_path'],
                                                row_vars['prompt'], row_vars['ref_language'], row_vars['text_language'],
                                                row_vars['cut_method'], row_vars['top_k'], row_vars['top_p'],
                                                row_vars['temperature'], row_vars['speed'], row_vars['ref_free'],
                                                row_vars['if_freeze'], row_vars['delimiter'], idx, failed_rows,
                                                original_states, row_controls))
                thread.start()  # 启动线程
                thread.join()  # 等待当前线程完成，确保按顺序执行
                self.voice_threads.append(thread)  # 将线程保存到列表

            except Exception as e:
                print(f"生成第 {idx} 行语音时出错: {e}")

        # 合并音频，传入出错的行名
        self.merge_audio_files(failed_rows)

        # 恢复控件状态
        for control, state in original_states_menu.items():
            control.config(state=state)  # 恢复控件原状态

    def run_merge_audio_files(self):
        failed_rows = []
        # 初始化进度条参数
        self.progress_bar_done = False
        self.current_task = 0  # 当前任务量
        self.start_time = time.time()  # 任务开始时间初始化为当前时间
        self.total_tasks = 1
        threading.Thread(target=self.merge_audio_files(failed_rows))

    def merge_audio_files(self, failed_rows):
        folder_path = self.folder_path_var.get()
        order_file_path = os.path.join(folder_path, "顺序表.txt")
        input_folder = os.path.join(folder_path, "AudioCache")
        output_folder = folder_path
        print("合并")

        if not os.path.isfile(order_file_path):
            messagebox.showerror("错误", f"顺序表文件不存在: {order_file_path}")
            return

        with open(order_file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        audio_segments = []
        for line in lines:
            file_name = line.strip() + '.wav'
            file_path3 = os.path.join(input_folder, file_name)
            if os.path.isfile(file_path3):
                audio = AudioSegment.from_wav(file_path3)
                audio_segments.append(audio)

        if audio_segments:
            combined = sum(audio_segments)
            output_file = os.path.join(output_folder, 'merged_output.wav')
            combined.export(output_file, format='wav')

            self.current_task += 1
            self.progress_bar_done = True
            self.update_progress()  # 更新进度条显示

            # 如果有出错的行，显示警告信息
            if failed_rows:
                failed_str = "、".join(failed_rows)
                messagebox.showwarning("合成未完全成功",
                                       f"合成未完全成功，以下角色的语言合成失败: {failed_str}。请检查这些角色的参数并单独合成语音，全部合成完后点击合并语言按钮。")
            else:
                messagebox.showinfo("成功", f"合成完成: {output_file}")

        else:
            messagebox.showerror("错误:没有找到匹配的音频文件")

    def refresh_folder_list(self):
        """ 刷新文件夹内容 """
        folder_path = self.folder_path_var.get()
        if folder_path:  # 确保路径不为空
            self.clear_current_display()
            self.refresh_model_list()
            self.display_txt_files(folder_path)  # 修改为 display_txt_files

        else:
            messagebox.showwarning("警告", "请先选择一个有效的文件夹。")

    def refresh_model_list(self):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        try:
            # 从 API 获取最新的模型列表
            result = self.client.predict(api_name="/change_choices")
            self.sovits_model_list = [choice[0] for choice in result[0]['choices']]
            self.gpt_model_list = [choice[0] for choice in result[1]['choices']]

            # 模型列表刷新成功后，自动点击每一行的刷新按钮
            for widget in self.scroll_frame.winfo_children():
                if isinstance(widget, tk.Button) and widget.cget("text") == "刷新单项模型":
                    widget.invoke()  # 调用按钮的命令

        except Exception as e:
            messagebox.showerror("错误", f"刷新模型列表失败: {str(e)}")

    def browse_main_folder(self):
        """ 让用户选择主文件夹并显示其中的 .txt 文件内容 """
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.folder_path_var.set(folder_selected)
            self.clear_current_display()  # 清空当前显示的内容
            self.display_txt_files(folder_selected)  # 修改为 display_txt_files

    def get_txt_files(self, main_folder):
        # 获取主文件夹中的所有 .txt 文件，并排除名为 "顺序表.txt" 的文件，返回它们的文件名（不包含扩展名）
        return [os.path.splitext(f)[0] for f in os.listdir(main_folder)
                if f.endswith('.txt') and f != '顺序表.txt']

    def clear_current_display(self):
        """ 清空当前显示的内容 """
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()  # 销毁 scroll_frame 中的所有小部件

    def export_all_character_config(self, folder_path, selected_option, top_k, top_p, temperature, speed, ref_free,
                                    if_freeze, sovits, gpt, ref_wav_path, prompt, ref_language, text_language,
                                    cut_method,
                                    delimiter, show_message=True):
        # 主文件夹
        full_folder_path = self.folder_path_var.get()

        # 检查路径是否存在
        if not full_folder_path:
            messagebox.showerror("错误", "请选择一个有效的文件夹路径")
            return

        # 创建配置数据
        config_data = {
            "top_k": top_k.get(),
            "top_p": top_p.get(),
            "temperature": temperature.get(),
            "speed": speed.get(),
            "ref_free": ref_free.get(),
            "if_freeze": if_freeze.get(),
            "sovits": sovits.get(),
            "gpt": gpt.get(),
            "ref_wav_path": ref_wav_path.get(),
            "prompt": prompt.get(),
            "ref_language": ref_language.get(),
            "text_language": text_language.get(),
            "cut_method": cut_method.get(),
            "delimiter": delimiter.get()
        }

        # 使用下拉框选项命名配置文件
        config_path = os.path.join(full_folder_path, f"{selected_option}.json")

        # 写入配置到指定路径
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            if show_message:
                messagebox.showinfo("成功", f"角色配置已导出到: {config_path}")
            return config_path  # 返回导出的文件路径
        except Exception as e:
            messagebox.showerror("错误", f"导出配置文件时出错: {str(e)}")
            return None

    def export_character_config(self, folder_path, selected_option, top_k, top_p, temperature, speed, ref_free,
                                if_freeze, sovits, gpt, ref_wav_path, prompt, ref_language, text_language, cut_method,
                                delimiter, main_folder_path, show_message=True):

        # 获取主文件夹路径
        # main_folder_path = self.folder_path_config.get()

        # 如果 folder_path 是 "当前角色"，使用 self.folder_path_var 路径
        if folder_path == "当前角色":
            full_folder_path = self.folder_path_var.get()
        else:
            full_folder_path = os.path.join(main_folder_path, folder_path)

        # 检查路径是否存在
        if not full_folder_path:
            messagebox.showerror("错误", "请选择一个有效的文件夹路径")
            return

        # 创建配置数据
        config_data = {
            "top_k": top_k.get(),
            "top_p": top_p.get(),
            "temperature": temperature.get(),
            "speed": speed.get(),
            "ref_free": ref_free.get(),
            "if_freeze": if_freeze.get(),
            "sovits": sovits.get(),
            "gpt": gpt.get(),
            "ref_wav_path": ref_wav_path.get(),
            "prompt": prompt.get(),
            "ref_language": ref_language.get(),
            "text_language": text_language.get(),
            "cut_method": cut_method.get(),
            "delimiter": delimiter.get()
        }

        # 使用下拉框选项命名配置文件
        config_path = os.path.join(full_folder_path, f"{selected_option}.json")

        # 写入配置到指定路径
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            if show_message:
                messagebox.showinfo("成功", f"角色配置已导出到: {config_path}")
            return config_path  # 返回导出的文件路径
        except Exception as e:
            messagebox.showerror("错误", f"导出配置文件时出错: {str(e)}")
            return None

    def sync_scroll_horizontal(self, *args):
        """同步横向滚动"""
        self.header_canvas.xview(*args)
        self.list_canvas.xview(*args)

    def create_header(self, header_frame):
        headers = [
            ("角色名", 17), ("角色列表", 17), ("配置角色", 17), ("选择配置", 40), ("SoVITS模型", 21), ("GPT模型", 38),
            ("参考音频路径", 52), ("提示文本", 29), ("参考语言", 20), ("生成语言", 15), ("top_k", 5), ("top_p", 5),
            ("温度", 4),
            ("语速", 3), ("无参考模式", 8), ("冻结设置", 11), ("分句内切割方式", 16), ("分句符", 5)
        ]

        for col, (header, width) in enumerate(headers):
            tk.Label(header_frame, text=header, anchor='w', width=width).grid(row=0, column=col, padx=5, pady=5,
                                                                              sticky="w")

    def get_subfolders(self, main_folder):
        return [f for f in os.listdir(main_folder) if os.path.isdir(os.path.join(main_folder, f))]

    def get_audio_files(self, folder):
        return glob.glob(os.path.join(folder, "**/*.wav"), recursive=True)

    def display_txt_files(self, main_folder):
        txt_files = self.get_txt_files(main_folder)

        # 添加“默认”项
        txt_files.insert(0, "默认")

        entry_width = 5
        check_width = 2
        option_width = 15
        long_entry_width = 40
        start_col = 1  # 起始列
        row_padding = 10  # 行间距
        column_padding = 5  # 列间距

        # 存储每一行的变量
        self.row_variables = {}

        for idx, folder in enumerate(txt_files):
            # txt_files[idx] 即为去掉扩展名的文件名
            if folder == "默认":
                label_name = "默认"
                file_path = ""  # 默认行不对应任何文件路径
            else:
                file_path = os.path.join(main_folder, folder + ".txt")
                label_name = folder

            # 显示文件名（不包含扩展名）
            label_name = tk.Label(self.scroll_frame, text=txt_files[idx], font=("微软雅黑", 10), width=10, anchor="w")
            label_name.grid(row=idx, column=start_col - 1, padx=column_padding, pady=row_padding, sticky="w")
            label_name.bind("<MouseWheel>", self.scroll_canvas)  # 绑定滚动事件
            label_name.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            label_name.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 角色列表路径下拉栏
            combo_box_path_var = tk.StringVar()
            combo_box_path = ttk.Combobox(self.scroll_frame, textvariable=combo_box_path_var, width=option_width)

            # 从 self.character_folder_path 提取路径列表作为选项
            path_options = list(self.character_folder_path.values())
            combo_box_path['values'] = path_options  # 设置选项

            # 默认选择第一个选项（如果有路径）
            if path_options:
                combo_box_path_var.set(path_options[0])  # 设置默认值为第一个路径
            combo_box_path.grid(row=idx, column=start_col, padx=column_padding, pady=row_padding,
                                sticky="w")

            # 绑定鼠标进入事件
            combo_box_path.bind("<Enter>", self.populate_folder_dropdown_gen)

            # 创建角色下拉框 combo_box_charactor
            charactor_var = tk.StringVar(value="当前角色")
            combo_box_charactor = ttk.Combobox(self.scroll_frame, textvariable=charactor_var, width=option_width)
            combo_box_charactor.grid(row=idx, column=start_col + 1, padx=column_padding, pady=row_padding,
                                     sticky="w")

            # 加载文件夹选项
            self.update_charactor_options(combo_box_charactor, combo_box_path_var)
            combo_box_path.bind("<<ComboboxSelected>>",
                                lambda e, cbc=combo_box_charactor,
                                       cbpv=combo_box_path_var: self.update_charactor_options(cbc, cbpv))

            # 添加下拉框 combo_box_config
            # 默认包含当前行的 label_name 以及“新建配置”
            config_file_var = tk.StringVar(value=txt_files[idx])  # 自动填充为 label_name
            combo_box_config = ttk.Combobox(self.scroll_frame, textvariable=config_file_var, width=option_width)

            # 添加下拉框中的选项
            combo_box_config['values'] = [txt_files[idx], "新建配置"]
            combo_box_config.grid(row=idx, column=start_col + 2, padx=column_padding, pady=row_padding, sticky="w")

            # 绑定选择事件
            combo_box_config.bind("<<ComboboxSelected>>",
                                  lambda e, char_var=charactor_var, cfg_var=config_file_var, index=idx:
                                  self.on_json_file_selected(char_var.get(), cfg_var.get(), index))

            # 创建音频文件下拉菜单
            audio_files = self.get_audio_files(file_path)
            ref_wav_path_entry = tk.StringVar()
            prompt_var = tk.StringVar()

            # 添加按钮以应用默认值
            if folder == "默认":
                apply_default_button = tk.Button(self.scroll_frame, text=" 应用默认值  ",
                                                 command=self.apply_default_values)
                apply_default_button.grid(row=idx, column=start_col + 4, padx=column_padding, pady=row_padding)
                apply_default_button.bind("<MouseWheel>", self.scroll_canvas)
                apply_default_button.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
                apply_default_button.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            else:
                # 当 folder 不是 "默认" 时，添加“生成角色语言”按钮
                generate_language_button = tk.Button(self.scroll_frame, text="生成角色语音",
                                                     command=lambda index=idx: self.run_generate_character_voice(index))
                generate_language_button.grid(row=idx, column=start_col + 4, padx=column_padding, pady=row_padding)
                generate_language_button.bind("<MouseWheel>", self.scroll_canvas)
                generate_language_button.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
                generate_language_button.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 单独创建并绑定 Entry 和 Checkbutton 控件
            top_k_var = tk.StringVar(value="15")
            top_k_entry = tk.Entry(self.scroll_frame, textvariable=top_k_var, width=entry_width)
            top_k_entry.grid(row=idx, column=start_col + 13, padx=column_padding, pady=row_padding, sticky="w")
            top_k_entry.bind("<MouseWheel>", self.scroll_canvas)
            top_k_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            top_k_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            top_p_var = tk.StringVar(value="1")
            top_p_entry = tk.Entry(self.scroll_frame, textvariable=top_p_var, width=entry_width)
            top_p_entry.grid(row=idx, column=start_col + 14, padx=column_padding, pady=row_padding, sticky="w")
            top_p_entry.bind("<MouseWheel>", self.scroll_canvas)
            top_p_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            top_p_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            temperature_var = tk.StringVar(value="1")
            temperature_entry = tk.Entry(self.scroll_frame, textvariable=temperature_var, width=entry_width)
            temperature_entry.grid(row=idx, column=start_col + 15, padx=column_padding, pady=row_padding, sticky="w")
            temperature_entry.bind("<MouseWheel>", self.scroll_canvas)
            temperature_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            temperature_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            speed_var = tk.StringVar(value="1")
            speed_entry = tk.Entry(self.scroll_frame, textvariable=speed_var, width=entry_width)
            speed_entry.grid(row=idx, column=start_col + 16, padx=column_padding, pady=row_padding, sticky="w")
            speed_entry.bind("<MouseWheel>", self.scroll_canvas)
            speed_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            speed_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            ref_free_var = tk.BooleanVar()
            ref_free_check = tk.Checkbutton(self.scroll_frame, variable=ref_free_var, width=check_width)
            ref_free_check.grid(row=idx, column=start_col + 17, padx=column_padding, pady=row_padding, sticky="w")
            ref_free_check.bind("<MouseWheel>", self.scroll_canvas)
            ref_free_check.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            ref_free_check.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            if_freeze_var = tk.BooleanVar()
            if_freeze_check = tk.Checkbutton(self.scroll_frame, variable=if_freeze_var, width=check_width)
            if_freeze_check.grid(row=idx, column=start_col + 18, padx=column_padding + 15, pady=row_padding, sticky="w")
            if_freeze_check.bind("<MouseWheel>", self.scroll_canvas)
            if_freeze_check.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            if_freeze_check.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            sovits_var = tk.StringVar(value="请选择")
            sovits_menu = tk.OptionMenu(self.scroll_frame, sovits_var, "请先刷新模型")
            sovits_menu.config(width=option_width)
            sovits_menu.grid(row=idx, column=start_col + 5, padx=column_padding, pady=row_padding, sticky="w")
            sovits_menu.bind("<MouseWheel>", self.scroll_canvas)
            sovits_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            sovits_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            gpt_var = tk.StringVar(value="请选择")
            gpt_menu = tk.OptionMenu(self.scroll_frame, gpt_var, "请先刷新模型")
            gpt_menu.config(width=option_width)
            gpt_menu.grid(row=idx, column=start_col + 6, padx=column_padding, pady=row_padding, sticky="w")
            gpt_menu.bind("<MouseWheel>", self.scroll_canvas)
            gpt_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            gpt_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 刷新模型
            refresh_button = tk.Button(self.scroll_frame, text="刷新单项模型",
                                       command=lambda sm=sovits_menu, gm=gpt_menu, sv=sovits_var,
                                                      gv=gpt_var: self.run_update_model_choices(sm, gm, sv, gv))
            # refresh_button.grid(row=idx, column=start_col + 11, padx=column_padding, pady=row_padding, sticky="w")

            ref_language_var = tk.StringVar(value="请选择")
            ref_language_menu = tk.OptionMenu(self.scroll_frame, ref_language_var, "请先确认模型")
            ref_language_menu.config(width=option_width)
            ref_language_menu.grid(row=idx, column=start_col + 11, padx=column_padding, pady=row_padding, sticky="w")
            ref_language_menu.bind("<MouseWheel>", self.scroll_canvas)
            ref_language_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            ref_language_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            text_language_var = tk.StringVar(value="请选择")
            text_language_menu = tk.OptionMenu(self.scroll_frame, text_language_var, "请先确认模型")
            text_language_menu.config(width=option_width)
            text_language_menu.grid(row=idx, column=start_col + 12, padx=column_padding, pady=row_padding, sticky="w")
            text_language_menu.bind("<MouseWheel>", self.scroll_canvas)
            text_language_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            text_language_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            confirm_button = tk.Button(self.scroll_frame, text="确认模型",
                                       command=lambda sv=sovits_var, gv=gpt_var, rlv=ref_language_var,
                                                      tlv=text_language_var, frm=self.scroll_frame,
                                                      sc=start_col, lin=idx: self.run_confirm_gpt_model(sv, gv, rlv,
                                                                                                        tlv, frm,
                                                                                                        sc, lin))
            confirm_button.grid(row=idx, column=start_col + 7, padx=column_padding, pady=row_padding, sticky="w")
            confirm_button.bind("<MouseWheel>", self.scroll_canvas)
            confirm_button.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            confirm_button.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            cut_method_var = tk.StringVar(value="凑四句一切")
            cut_method_menu = tk.OptionMenu(self.scroll_frame, cut_method_var, "不切", "凑四句一切", "凑50字一切",
                                            "按中文句号。切",
                                            "按英文句号.切", "按标点符号切")
            cut_method_menu.config(width=option_width)
            cut_method_menu.grid(row=idx, column=start_col + 19, padx=column_padding, pady=row_padding, sticky="w")
            cut_method_menu.bind("<MouseWheel>", self.scroll_canvas)
            cut_method_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            cut_method_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 分隔符 Entry (绑定滚动事件)
            delimiter_entry = tk.StringVar(value="|")
            delimiter_entry_field = tk.Entry(self.scroll_frame, textvariable=delimiter_entry, width=entry_width)
            delimiter_entry_field.grid(row=idx, column=start_col + 20, padx=column_padding, pady=row_padding,
                                       sticky="w")
            delimiter_entry_field.bind("<MouseWheel>", self.scroll_canvas)
            delimiter_entry_field.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            delimiter_entry_field.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 选择参考音频
            combo_box = ttk.Combobox(self.scroll_frame, textvariable=ref_wav_path_entry, width=long_entry_width)
            combo_box['values'] = audio_files
            combo_box.grid(row=idx, column=start_col + 8, padx=column_padding, pady=row_padding, sticky="w")

            # 添加“浏览...”按钮
            browse_button = tk.Button(self.scroll_frame, text="浏览...",
                                      command=lambda var=ref_wav_path_entry, combo=combo_box: self.browse_wav_file(var,
                                                                                                                   combo,
                                                                                                                   idx))
            browse_button.grid(row=idx, column=start_col + 9, padx=column_padding, pady=row_padding, sticky="w")
            browse_button.bind("<MouseWheel>", self.scroll_canvas)
            browse_button.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            browse_button.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 禁止在下拉框上使用滚轮
            # combo_box.bind("<MouseWheel>", lambda e: "break")

            result_entry = tk.Entry(self.scroll_frame, textvariable=prompt_var, width=long_entry_width)
            result_entry.grid(row=idx, column=start_col + 10, padx=column_padding, pady=row_padding, sticky="w")
            result_entry.bind("<MouseWheel>", self.scroll_canvas)
            result_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            result_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            combo_box.bind("<<ComboboxSelected>>",
                           lambda e, var=ref_wav_path_entry, result=prompt_var,
                                  ref_lang1=ref_language_var, ref_lang2=text_language_var: self.update_text(
                               var.get(), result, ref_lang1, ref_lang2))

            # 绑定选择事件到新函数
            combo_box_charactor.bind("<<ComboboxSelected>>",
                                     lambda e, index=idx, char_var=charactor_var,
                                            sc=start_col, rwpe_var=ref_wav_path_entry, result=prompt_var,
                                            ref_lang1=ref_language_var, ref_lang2=text_language_var,
                                            cbp=combo_box_path_var: self.on_charactor_selected(index,
                                                                                               char_var, sc, rwpe_var,
                                                                                               result, ref_lang1,
                                                                                               ref_lang2, cbp))

            # if audio_files:

            # else:
            # label_no_audio = tk.Label(self.scroll_frame, text="No .wav files", fg="gray")
            # label_no_audio.grid(row=idx, column=start_col + 12, padx=column_padding, pady=row_padding, sticky="w")

            # 导出角色配置按钮，并传递当前行的所有变量到 lambda 中，确保每个按钮绑定当前行的配置
            export_button = tk.Button(self.scroll_frame, text="导出配置",
                                      command=lambda char_var=charactor_var,
                                                     so=config_file_var,  # 确保此时获取值
                                                     top_k=top_k_var,
                                                     top_p=top_p_var,
                                                     temperature=temperature_var,
                                                     speed=speed_var,
                                                     ref_free=ref_free_var,
                                                     if_freeze=if_freeze_var,
                                                     sovits=sovits_var,
                                                     gpt=gpt_var,
                                                     ref_wav_path=ref_wav_path_entry,
                                                     prompt=prompt_var,
                                                     ref_language=ref_language_var,
                                                     text_language=text_language_var,
                                                     cut_method=cut_method_var,
                                                     delimiter=delimiter_entry,
                                                     main_folder_path=combo_box_path_var:
                                      self.export_character_config(char_var.get(), so.get(), top_k, top_p, temperature,
                                                                   speed,
                                                                   ref_free, if_freeze, sovits, gpt,
                                                                   ref_wav_path, prompt, ref_language, text_language,
                                                                   cut_method, delimiter, main_folder_path.get()))

            export_button.grid(row=idx, column=start_col + 3, padx=5, pady=5, sticky="w")
            export_button.bind("<MouseWheel>", self.scroll_canvas)
            export_button.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            export_button.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 将当前行的变量存储到字典中
            self.row_variables[idx] = {
                'top_k': top_k_var,
                'top_p': top_p_var,
                'temperature': temperature_var,
                'speed': speed_var,
                'ref_free': ref_free_var,
                'if_freeze': if_freeze_var,
                'sovits': sovits_var,
                'gpt': gpt_var,
                'ref_wav_path': ref_wav_path_entry,
                'combo_box_ref_wav_path': combo_box,
                'prompt': prompt_var,
                'ref_language': ref_language_var,
                'text_language': text_language_var,
                'cut_method': cut_method_var,
                'delimiter': delimiter_entry,
                'charactor_var': charactor_var,
                'config_file_var': config_file_var,
                'config_file': combo_box_config,
                'label_name': label_name,
                'character_list_path': combo_box_path_var.get()
            }

        # 添加滚动功能
        self.scroll_frame.bind("<MouseWheel>", lambda e: self.scroll_canvas(e))
        self.scroll_frame.bind("<Button-4>", lambda e: self.scroll_canvas(e))  # macOS 向上滚动
        self.scroll_frame.bind("<Button-5>", lambda e: self.scroll_canvas(e))  # macOS 向下滚动

    def apply_default_values(self):
        # 找到“默认”行的变量
        default_row_idx = 0  # 默认行的索引为 0
        default_values = self.row_variables[default_row_idx]

        # 添加调试信息，查看default_values的内容
        # print(f"Default values: {default_values}")

        # 检查并提取“默认”行各控件的值
        try:
            default_top_k = default_values["top_k"].get()
            default_top_p = default_values["top_p"].get()
            default_temperature = default_values["temperature"].get()
            default_speed = default_values["speed"].get()
            default_ref_free = default_values["ref_free"].get()
            default_if_freeze = default_values["if_freeze"].get()
            default_sovits_model = default_values["sovits"].get()
            default_gpt_model = default_values["gpt"].get()
            default_ref_wav_path = default_values["ref_wav_path"].get()
            default_prompt = default_values["prompt"].get()
            default_ref_language = default_values["ref_language"].get()
            default_text_language = default_values["text_language"].get()
            default_cut_method = default_values["cut_method"].get()
            default_delimiter = default_values["delimiter"].get()
        except KeyError as e:
            # print(f"KeyError: {e} - 检查行 {default_row_idx} 中是否包含所有需要的控件")
            return  # 如果出现KeyError，终止函数

        # 遍历所有行并设置它们的控件值
        for idx in range(1, len(self.row_variables)):  # 从 1 开始，跳过“默认”行
            row_vars = self.row_variables[idx]

            # 设置各控件的值
            row_vars["top_k"].set(default_top_k)
            row_vars["top_p"].set(default_top_p)
            row_vars["temperature"].set(default_temperature)
            row_vars["speed"].set(default_speed)
            row_vars["ref_free"].set(default_ref_free)
            row_vars["if_freeze"].set(default_if_freeze)
            row_vars["sovits"].set(default_sovits_model)
            row_vars["gpt"].set(default_gpt_model)
            row_vars["ref_wav_path"].set(default_ref_wav_path)
            row_vars["prompt"].set(default_prompt)
            row_vars["ref_language"].set(default_ref_language)
            row_vars["text_language"].set(default_text_language)
            row_vars["cut_method"].set(default_cut_method)
            row_vars["delimiter"].set(default_delimiter)

        # print("已应用默认值到其他所有行")

    def on_charactor_selected(self, idx, char_var, start_col, audio_file_var, prompt_var, ref_language_var,
                              text_language_var, combo_box_path_var):
        """处理角色选择事件，更新配置文件和音频文件"""
        selected_charactor = char_var.get()
        self.update_json_options(idx, selected_charactor)  # 更新 json 配置文件下拉框
        self.update_audio_files(idx, selected_charactor, combo_box_path_var)  # 更新音频文件下拉框
        self.auto_choice_model(idx, selected_charactor, start_col)
        audio_file = audio_file_var.get()
        self.update_text(audio_file, prompt_var, ref_language_var, text_language_var)

    def auto_choice_model(self, idx, selected_charactor, start_col):
        """根据selected_charactor值更新下拉框选择项"""
        # 获取当前行的下拉菜单变量
        sovits_menu = self.scroll_frame.grid_slaves(row=idx, column=start_col + 5)[0]  # SoVITS下拉菜单
        gpt_menu = self.scroll_frame.grid_slaves(row=idx, column=start_col + 6)[0]  # GPT下拉菜单

        # 提取文件名并匹配selected_charactor
        sovits_model_paths = [
            path for path in self.sovits_model_list if selected_charactor in os.path.basename(path)
        ]
        gpt_model_paths = [
            path for path in self.gpt_model_list if selected_charactor in os.path.basename(path)
        ]

        # 设置默认选择项（如果没有匹配的模型，则选择第一个选项，或显示"无匹配模型"）
        selected_sovits = sovits_model_paths[0] if sovits_model_paths else "请选择"
        selected_gpt = gpt_model_paths[0] if gpt_model_paths else "请选择"

        # 更新SoVITS菜单的当前选择
        sovits_menu.setvar(sovits_menu.cget("textvariable"), selected_sovits)

        # 更新GPT菜单的当前选择
        gpt_menu.setvar(gpt_menu.cget("textvariable"), selected_gpt)

    def update_charactor_options(self, combo_box_charactor, combo_box_path_var):
        """更新角色下拉框选项"""
        # print(f"更新{combo_box_path_var.get()}")
        folder_path = combo_box_path_var.get()
        # print(folder_path)
        if os.path.exists(folder_path):
            folders = [name for name in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, name))]
            combo_box_charactor['values'] = folders + ["当前角色"]
        else:
            combo_box_charactor['values'] = ["当前角色"]

    def update_json_options(self, idx, selected_folder):
        """更新 JSON 文件下拉框选项"""
        if selected_folder != "当前角色":
            # 处理非“当前角色”的情况
            folder_path = self.row_variables[idx]['character_list_path']
            json_folder_path = os.path.join(folder_path, selected_folder)

            if os.path.exists(json_folder_path):
                json_files = [name[:-5] for name in os.listdir(json_folder_path) if name.endswith('.json')]
                # 更新对应行的 combo_box_config 的值
                combo_box_config = self.row_variables[idx]['config_file']  # 获取 ttk.Combobox 对象
                combo_box_config['values'] = json_files + ["新建配置"]  # 更新下拉选项
            else:
                combo_box_config = self.row_variables[idx]['config_file']
                combo_box_config['values'] = ["新建配置"]  # 没有可用的 JSON 文件，仅提供“新建配置”
        else:
            # 如果选择了“当前角色”
            label_name = self.row_variables[idx]['label_name']  # 从 row_variables 中获取 label_name
            combo_box_config = self.row_variables[idx]['config_file']  # 获取 ttk.Combobox 对象

            # 为 combo_box_config 添加 label_name 和 “新建配置” 两个选项
            combo_box_config['values'] = [label_name['text'], "新建配置"]

            # 自动填充 combo_box_config 的文本框内容为 label_name
            combo_box_config.set(label_name['text'])

    def update_audio_files(self, idx, selected_folder, combo_box_path_var):
        """更新参考音频下拉框选项，并自动选择路径最短且文件名最长的 .wav 文件"""
        # 获取文件夹路径
        folder_path = os.path.join(combo_box_path_var.get(), selected_folder)
        # print(folder_path)

        # 获取所有 .wav 文件路径列表
        audio_files = self.get_audio_files(folder_path)
        # print(audio_files)

        if not audio_files:
            # 如果没有 .wav 文件，清空下拉框并退出
            combo_box = self.row_variables[idx]['combo_box_ref_wav_path']
            combo_box['values'] = []
            return

        # 找到路径最短且在路径相同时文件名最长的文件
        def get_file_priority(file_path):
            dir_path, file_name = os.path.split(file_path)
            return (len(dir_path), -len(file_name))  # 按路径长度升序，文件名长度降序排序

        selected_file = min(audio_files, key=get_file_priority)

        # 更新下拉框
        combo_box = self.row_variables[idx]['combo_box_ref_wav_path']
        combo_box['values'] = audio_files  # 更新下拉框的值
        combo_box.set(selected_file)  # 自动选择最优文件

    def get_json_files(self, folder):
        """获取文件夹中的所有 JSON 文件"""
        json_files = glob.glob(os.path.join(folder, "*.json"))
        # 仅返回文件名（去掉路径和扩展名）
        return [os.path.splitext(os.path.basename(f))[0] for f in json_files]

    def on_json_file_selected(self, folder_path, selected_file, idx):
        """选择 JSON 文件后应用配置"""
        # 检查是否选择了“新建配置”
        if selected_file == "新建配置":
            return

        # label_name = self.row_variables[idx]['label_name'].cget("text")

        # print(label_name)

        # 检查是否选择了当前行的 label_name
        if selected_file == self.row_variables[idx]['label_name'].cget("text"):
            # print(selected_file)
            main_folder_path = self.folder_path_var.get()
            # print(main_folder_path)
            config_file_path = os.path.join(main_folder_path, f"{selected_file}.json")
            # print(config_file_path)

            # 尝试加载与 label_name 同名的配置文件
            if not os.path.exists(config_file_path):
                return  # 文件不存在时，什么也不做

            try:
                with open(config_file_path, 'r', encoding='utf-8') as file:
                    config_data = json.load(file)

                # 检查是否存在 row_variables
                if idx not in self.row_variables:
                    raise ValueError(f"Row {idx} does not exist.")

                # 获取当前行的变量
                row_vars = self.row_variables[idx]

                # 更新对应的变量
                row_vars['top_k'].set(config_data.get('top_k', '15'))  # 默认值为 15
                row_vars['top_p'].set(config_data.get('top_p', '1'))  # 默认值为 1
                row_vars['temperature'].set(config_data.get('temperature', '1'))  # 默认值为 1
                row_vars['speed'].set(config_data.get('speed', '1'))  # 默认值为 1
                row_vars['ref_free'].set(config_data.get('ref_free', False))  # 默认值为 False
                row_vars['if_freeze'].set(config_data.get('if_freeze', False))  # 默认值为 False
                row_vars['sovits'].set(config_data.get('sovits', '请选择'))  # 默认值为 '请选择'
                row_vars['gpt'].set(config_data.get('gpt', '请选择'))  # 默认值为 '请选择'
                row_vars['ref_wav_path'].set(config_data.get('ref_wav_path', ''))  # 默认值为 ''
                row_vars['prompt'].set(config_data.get('prompt', ''))  # 默认值为 ''
                row_vars['ref_language'].set(config_data.get('ref_language', '请选择'))  # 默认值为 '请选择'
                row_vars['text_language'].set(config_data.get('text_language', '请选择'))  # 默认值为 '请选择'
                row_vars['cut_method'].set(config_data.get('cut_method', '凑四句一切'))  # 默认值为 '凑四句一切'
                row_vars['delimiter'].set(config_data.get('delimiter', '|'))  # 默认值为 '|'

            except Exception as e:
                messagebox.showerror("错误", f"导入配置时发生错误：{str(e)}")
            return  # 处理完后返回，避免继续执行

        # 继续处理其他选项
        main_folder_path = self.row_variables[idx]['character_list_path']
        config_file_path = os.path.join(main_folder_path, folder_path, f"{selected_file}.json")

        try:
            with open(config_file_path, 'r', encoding='utf-8') as file:
                config_data = json.load(file)

            # 检查是否存在 row_variables
            if idx not in self.row_variables:
                raise ValueError(f"Row {idx} does not exist.")

            # 获取当前行的变量
            row_vars = self.row_variables[idx]

            # 更新对应的变量
            row_vars['top_k'].set(config_data.get('top_k', '15'))  # 默认值为 15
            row_vars['top_p'].set(config_data.get('top_p', '1'))  # 默认值为 1
            row_vars['temperature'].set(config_data.get('temperature', '1'))  # 默认值为 1
            row_vars['speed'].set(config_data.get('speed', '1'))  # 默认值为 1
            row_vars['ref_free'].set(config_data.get('ref_free', False))  # 默认值为 False
            row_vars['if_freeze'].set(config_data.get('if_freeze', False))  # 默认值为 False
            row_vars['sovits'].set(config_data.get('sovits', '请选择'))  # 默认值为 '请选择'
            row_vars['gpt'].set(config_data.get('gpt', '请选择'))  # 默认值为 '请选择'
            row_vars['ref_wav_path'].set(config_data.get('ref_wav_path', ''))  # 默认值为 ''
            row_vars['prompt'].set(config_data.get('prompt', ''))  # 默认值为 ''
            row_vars['ref_language'].set(config_data.get('ref_language', '请选择'))  # 默认值为 '请选择'
            row_vars['text_language'].set(config_data.get('text_language', '请选择'))  # 默认值为 '请选择'
            row_vars['cut_method'].set(config_data.get('cut_method', '凑四句一切'))  # 默认值为 '凑四句一切'
            row_vars['delimiter'].set(config_data.get('delimiter', '|'))  # 默认值为 '|'

        except FileNotFoundError:
            messagebox.showerror("错误", f"找不到配置文件：{config_file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导入配置时发生错误：{str(e)}")

    def update_row_with_config(self, row_index, config):
        pass

    def run_update_model_choices(self, sovits_menu, gpt_menu, sovits_var, gpt_var):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        # 创建线程并运行 update_model_choices
        thread = threading.Thread(target=self.update_model_choices,
                                  args=(sovits_menu, gpt_menu, sovits_var, gpt_var))

        thread.start()

    @check_using_api
    def run_confirm_gpt_model(self, sovits_var, gpt_var, ref_language_var, text_language_var, frame, start_col, row):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        # 创建线程并运行 confirm_gpt_model
        thread = threading.Thread(target=self.confirm_gpt_model,
                                  args=(
                                      sovits_var, gpt_var, ref_language_var, text_language_var, frame, start_col, row))
        thread.start()

    @check_using_api
    def run_generate_character_voice(self, idx):
        thread = threading.Thread(target=self.pre_generate_character_voice, args=(idx,))
        self.voice_threads.append(thread)  # 将线程保存到列表
        thread.start()

    def pre_generate_character_voice(self, idx):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        failed_rows = []

        # 保存控件状态
        original_states_menu = {}
        controls_to_disable = [
            self.import_button, self.refresh_list_button,
            self.browse_button, self.generate_button, self.merge_button
        ]

        # 保存当前状态并禁用控件
        for control in controls_to_disable:
            original_states_menu[control] = control.cget("state")
            control.config(state="disabled")

        # 禁用文件夹路径下拉框
        original_states_menu[self.folder_combobox] = self.folder_combobox.cget("state")
        self.folder_combobox.config(state="disabled")

        # 获取指定行的所有控件
        row_controls = self.scroll_frame.grid_slaves(row=idx)

        # 存储控件的原始状态
        original_states = {}

        for control in row_controls:
            if isinstance(control, tk.Entry):
                original_states[control] = control.cget("state")  # 获取原始状态
                control.config(state="disabled")  # 禁用控件
            elif isinstance(control, tk.Button):
                original_states[control] = control.cget("state")
                control.config(state="disabled")
            elif isinstance(control, ttk.Combobox):
                original_states[control] = control["state"]
                control.config(state="disabled")
            elif isinstance(control, tk.Checkbutton):
                original_states[control] = control.cget("state")
                control.config(state="disabled")
            elif isinstance(control, tk.OptionMenu):
                original_states[control] = control.cget("state")
                control.config(state="disabled")

        """根据指定行的参数生成角色语音，并初始化进度条参数"""
        # 获取按钮所在行的所有参数
        row_vars = self.row_variables[idx]

        # 读取对应的 .txt 文件
        file_name = row_vars['label_name'].cget("text")  # 获取文件名
        file_path = os.path.join(self.folder_path_var.get(), f"{file_name}.txt")  # 拼接完整路径

        # 初始化进度条参数
        self.progress_bar_done = False
        self.current_task = 0  # 当前任务量
        self.start_time = time.time()  # 任务开始时间初始化为当前时间

        # 读取文件内容并分块
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()  # 读取文件内容
                # 根据分隔符分块
                chunks = content.split(row_vars['delimiter'].get())  # 使用指定分隔符分块
                self.total_tasks = max(0, len(chunks) - 1)  # 将分块数量减去1设定为总任务量，确保不为负数
        else:
            self.total_tasks = 0  # 如果文件不存在，则设置为0

        # 重置进度条和百分比标签
        self.progress_bar['value'] = 0  # 重置进度条
        self.progress_percentage_label.config(text="进度: 0%")  # 重置进度百分比
        self.update_progress()  # 更新进度条显示

        """# 创建线程并运行 generate_character_voice，传入对应的变量
        thread = threading.Thread(target=self.generate_character_voice,
                                  args=(row_vars['sovits'], row_vars['gpt'], row_vars['ref_wav_path'],
                                        row_vars['prompt'], row_vars['ref_language'], row_vars['text_language'],
                                        row_vars['cut_method'], row_vars['top_k'], row_vars['top_p'],
                                        row_vars['temperature'], row_vars['speed'], row_vars['ref_free'],
                                        row_vars['if_freeze'], row_vars['delimiter'], idx, failed_rows, original_states, row_controls))
        self.voice_threads.append(thread)  # 将线程保存到列表
        thread.start()"""

        self.generate_character_voice(row_vars['sovits'], row_vars['gpt'], row_vars['ref_wav_path'],
                                      row_vars['prompt'], row_vars['ref_language'], row_vars['text_language'],
                                      row_vars['cut_method'], row_vars['top_k'], row_vars['top_p'],
                                      row_vars['temperature'], row_vars['speed'], row_vars['ref_free'],
                                      row_vars['if_freeze'], row_vars['delimiter'], idx, failed_rows, original_states,
                                      row_controls)

        self.progress_bar_done = True
        self.update_progress()  # 更新进度条显示

        # 恢复控件状态
        for control, state in original_states_menu.items():
            control.config(state=state)  # 恢复控件原状态

    def update_model_choices(self, sovits_menu, gpt_menu, sovits_var, gpt_var):
        if not self.sovits_model_list or not self.gpt_model_list:
            tk.messagebox.showerror("Error", "模型列表为空，请先刷新模型。")
            return

        sovits_menu['menu'].delete(0, 'end')
        for choice in self.sovits_model_list:
            sovits_menu['menu'].add_command(label=choice, command=lambda val=choice: sovits_var.set(val))

        gpt_menu['menu'].delete(0, 'end')
        for choice in self.gpt_model_list:
            gpt_menu['menu'].add_command(label=choice, command=lambda val=choice: gpt_var.set(val))

    def confirm_gpt_model(self, sovits_var, gpt_var, ref_language_var, text_language_var, frame, start_col, row):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return
        sovits_model = sovits_var.get()
        gpt_model = gpt_var.get()

        if sovits_model == "请选择" or gpt_model == "请选择":
            messagebox.showwarning("警告", "请选择有效的SoVITS模型和GPT模型")
            return

        try:
            # 提交选中的SoVITS模型到API
            sovits_result = self.client.predict(
                sovits_path=sovits_model,
                api_name="/change_sovits_weights"
            )

            # 提交选中的GPT模型到API
            gpt_result = self.client.predict(
                gpt_path=gpt_model,
                api_name="/change_gpt_weights"
            )

            # 从SoVITS模型的API返回中提取参考语言和生成语言选项
            ref_language_choices = [choice[0] for choice in sovits_result[0]['choices']]
            gen_language_choices = [choice[0] for choice in sovits_result[1]['choices']]

            # 获取点击的按钮所在行的下拉菜单
            ref_language_menu = frame.grid_slaves(row=row, column=start_col + 11)[0]
            text_language_menu = frame.grid_slaves(row=row, column=start_col + 12)[0]

            # 更新参考语言下拉菜单的选项
            ref_language_menu['menu'].delete(0, 'end')
            for choice in ref_language_choices:
                ref_language_menu['menu'].add_command(label=choice, command=tk._setit(ref_language_var, choice))

            # 更新生成语言下拉菜单的选项
            text_language_menu['menu'].delete(0, 'end')
            for choice in gen_language_choices:
                text_language_menu['menu'].add_command(label=choice, command=tk._setit(text_language_var, choice))

        except Exception as e:
            messagebox.showerror("错误", str(e))

    def generate_character_voice(self, sovits_var, gpt_var, ref_wav_path_var, prompt_var, ref_language_var,
                                 text_language_var, cut_method_var, top_k_var, top_p_var, temperature_var,
                                 speed_var, ref_free_var, if_freeze_var, delimiter_var, idx, failed_rows,
                                 original_states, row_controls):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        try:
            # 获取当前行的所有参数
            sovits_model = sovits_var.get()
            gpt_model = gpt_var.get()
            ref_wav_path = handle_file(ref_wav_path_var.get().strip())  # 参考音频路径
            prompt_text = prompt_var.get().strip()  # 提示文本
            ref_language = ref_language_var.get().strip()  # 参考音频语言
            text_language = text_language_var.get().strip()  # 合成文本语言
            cut_method = cut_method_var.get().strip()  # 切割方式
            top_k = int(top_k_var.get().strip())  # top_k 参数
            top_p = float(top_p_var.get().strip())  # top_p 参数
            temperature = float(temperature_var.get().strip())  # 温度
            speed = float(speed_var.get().strip())  # 语速
            ref_free = ref_free_var.get()  # 是否使用自由音频
            if_freeze = if_freeze_var.get()  # 是否冻结
            delimiter = delimiter_var.get().strip()  # 分隔符
            row_name = self.row_variables[idx]['label_name'].cget("text")  # 获取行的名称
            row_idx = idx

            print(
                f"获取的参数：{sovits_model}, {gpt_model}, {ref_wav_path}, {prompt_text}, {ref_language}, {text_language}, "
                f"{top_k}, {top_p}, {temperature}, {speed}, {ref_free}, {if_freeze}, {cut_method}, {delimiter}, {row_name}")

            # 确认模型是否有效
            if sovits_model != "请选择" and gpt_model != "请选择":
                try:
                    # 提交 SoVITS 和 GPT 模型到 API
                    self.client.predict(sovits_path=sovits_model, api_name="/change_sovits_weights")
                    self.client.predict(gpt_path=gpt_model, api_name="/change_gpt_weights")
                    print(f"执行的模型 {sovits_model}, {gpt_model}")

                except Exception as e:
                    messagebox.showerror("错误", str(e))
                    failed_rows.append(row_name)  # 记录出错的行名
                    return

            # 选择保存路径
            save_path = self.folder_path_var.get()
            audio_cache_path = os.path.join(save_path, "AudioCache")
            os.makedirs(audio_cache_path, exist_ok=True)
            output_dir = audio_cache_path

            # 读取文本文件内容
            text_file_path = os.path.join(save_path, f"{row_name}.txt")
            if not os.path.isfile(text_file_path):
                messagebox.showerror("错误", f"未找到文本文件: {text_file_path}")
                failed_rows.append(row_name)  # 记录出错的行名
                return

            with open(text_file_path, 'r', encoding='utf-8') as file:
                text_content = file.read()

            # 使用自定义分隔符分割文本
            sentences = self.split_text(text_content, delimiter)

            temp_files = []  # 临时文件路径

            # 逐句生成音频
            for idx, sentence in enumerate(sentences):
                if not all(
                        [ref_wav_path, prompt_text, ref_language, text_language, cut_method, top_k, top_p, temperature,
                         speed, sentence]):
                    continue  # 如果有空值，跳过处理

                try:
                    result = self.client.predict(
                        ref_wav_path=ref_wav_path,
                        prompt_text=prompt_text,
                        prompt_language=ref_language,
                        text_language=text_language,
                        how_to_cut=cut_method,
                        top_k=top_k,
                        top_p=top_p,
                        temperature=temperature,
                        speed=speed,
                        ref_free=ref_free,
                        if_freeze=if_freeze,
                        text=sentence,
                        inp_refs=[],
                        api_name="/get_tts_wav"
                    )

                    print(
                        f"实际执行的参数：{sovits_model}, {gpt_model}, {ref_wav_path}, {prompt_text}, {ref_language}, {text_language}, "
                        f"{top_k}, {top_p}, {temperature}, {speed}, {ref_free}, {if_freeze}, {cut_method}, {delimiter}, {row_name}, {sentence}")

                    # 获取音频文件路径
                    audio_file_path = result[0] if isinstance(result, tuple) and len(result) > 0 else result
                    if os.path.exists(audio_file_path):
                        dest_path = os.path.join(output_dir, f"{row_name} {idx + 1}.wav")
                        shutil.move(audio_file_path, dest_path)

                        # 更新进度条
                        # self.update_progress()

                    temp_files.append(audio_file_path)

                    self.current_task += 1
                    print(self.current_task)
                    self.update_progress()  # 更新进度条显示

                except Exception as e:
                    messagebox.showerror("错误", f"音频生成失败: {str(e)}")
                    failed_rows.append(row_name)  # 记录出错的行名

            # 调用清理函数清理临时文件
            # self.cleanup_temp_files(temp_files)

            # 获取指定行的所有控件
            row_controls = self.scroll_frame.grid_slaves(row=row_idx)

            for control in row_controls:
                # print("恢复")
                # 获取控件原始的state值
                original_state = original_states.get(control)

                if isinstance(control, tk.Entry):
                    if original_state is not None:
                        control.config(state=original_state)  # 恢复原始状态
                    else:
                        control.config(state="normal")  # 如果没有存储状态，恢复为 "normal"
                elif isinstance(control, tk.Button):
                    if original_state is not None:
                        control.config(state=original_state)
                    else:
                        control.config(state="normal")
                elif isinstance(control, ttk.Combobox):
                    if original_state is not None:
                        control.config(state=original_state)
                    else:
                        control.config(state="normal")
                elif isinstance(control, tk.Checkbutton):
                    if original_state is not None:
                        control.config(state=original_state)
                    else:
                        control.config(state="normal")
                elif isinstance(control, tk.OptionMenu):
                    if original_state is not None:
                        control.config(state=original_state)
                    else:
                        control.config(state="normal")

        except Exception as e:
            # 捕获异常并将出错的行记录到 failed_rows 中
            row_name = self.row_variables[idx]['label_name'].cget("text")
            failed_rows.append(row_name)
            print(f"生成第 {idx} 行语音时出错: {e}")

    def escape_regex_chars(self, pattern):
        """转义正则表达式中的特殊字符"""
        return re.escape(pattern)

    def split_text(self, text, delimiter):
        """根据给定的分隔符分割文本"""
        if delimiter:
            # 转义自定义分隔符
            escaped_delimiter = self.escape_regex_chars(delimiter)
            # 使用转义后的分隔符进行分割
            sentences = re.split(escaped_delimiter, text)
        else:
            sentences = [text]
        return [s.strip() for s in sentences if s.strip()]

    def scroll_canvas(self, event):
        """处理鼠标滚轮事件"""
        if event.num == 4 or event.delta > 0:
            self.list_canvas.yview_scroll(-1, "units")  # 向上滚动
        elif event.num == 5 or event.delta < 0:
            self.list_canvas.yview_scroll(1, "units")  # 向下滚动

    def display_avatar(self, folder, row, column=0):
        pass

    def crop_to_square(self, img):
        pass

    def update_text(self, audio_file, prompt_var, ref_language_var, text_language_var):
        filename = os.path.basename(audio_file)

        if "#" in filename:
            # 分割文件名，获取最后一个 '#' 后的部分
            parts = filename.split("#")
            if len(parts) >= 2:  # 确保有足够的 '#' 来获取最后两个 '#'
                # 使用原有方法判断
                text_between_hash = parts[-2]

                # 根据文本判断语言并设置 ref_language_var
                if text_between_hash in ["zh", "中文"]:
                    ref_language_var.set("中文")
                    text_language_var.set("中文")
                elif text_between_hash in ["en", "英文"]:
                    ref_language_var.set("英文")
                    text_language_var.set("英文")
                elif text_between_hash in ["ja", "日文"]:
                    ref_language_var.set("日文")
                    text_language_var.set("日文")

                # 处理最后一个 '#' 后面的文本
                text_after_hash = parts[-1]
                # 找到最后一个 '.' 的索引
                last_dot_index = text_after_hash.rfind('.')
                # 如果找到了 '.'，则提取其前面的文本
                if last_dot_index != -1:
                    text_after_hash = text_after_hash[:last_dot_index]
                prompt_var.set(text_after_hash)
            else:
                prompt_var.set("")  # 如果没有足够的 '#'，则清空 prompt_var
        else:
            # 删除末尾的 .wav 扩展名
            cleaned_text = filename.rstrip('.wav').strip()

            # 删除句子前【】符号内的内容
            cleaned_text = re.sub(r'【.*?】', '', cleaned_text).strip()

            # 判断语言
            def contains_chinese(text):
                return bool(re.search(r'[\u4e00-\u9fff]', text))

            def contains_japanese(text):
                # 只匹配不包含中文的日文字符
                return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF\u32D0-\u32FF]', text))

            def contains_english(text):
                return bool(re.search(r'[a-zA-Z]', text))

            # 语言检测
            has_chinese = contains_chinese(cleaned_text)
            has_japanese = contains_japanese(cleaned_text)
            has_english = contains_english(cleaned_text)

            # 语言组合逻辑：日文优先
            if has_japanese and has_english:
                ref_language_var.set("日英混合")
                text_language_var.set("日英混合")
            elif has_japanese:
                ref_language_var.set("日文")
                text_language_var.set("日文")
            elif has_chinese and has_english:
                ref_language_var.set("中英混合")
                text_language_var.set("中英混合")
            elif has_chinese:
                ref_language_var.set("中文")
                text_language_var.set("中文")
            elif has_english:
                ref_language_var.set("英文")
                text_language_var.set("英文")
            else:
                ref_language_var.set("未知")
                text_language_var.set("未知")

            # 设置提示文本
            prompt_var.set(cleaned_text)

    def browse_wav_file(self, ref_wav_path_entry, combo_box, idx):
        file_path = filedialog.askopenfilename(filetypes=[("WAV files", "*.wav")])
        if file_path:
            ref_wav_path_entry.set(file_path)  # 设置选中的文件路径到 Entry 变量中
            combo_box.set(file_path)  # 将文件路径填充到下拉框中

            # 手动触发 <<ComboboxSelected>> 事件
            combo_box.event_generate("<<ComboboxSelected>>")


class FolderAudioViewer:
    def __init__(self, root):
        # 初始化Gradio客户端
        self.client = None

        self.root = root

        self.sovits_model_list = []  # 存储SoVITS模型列表
        self.gpt_model_list = []  # 存储GPT模型列表
        self.row_variables = {}

        # 读取配置文件
        self.config = self.load_config()

        # 顶部路径框和浏览按钮容器
        self.path_frame = tk.Frame(self.root)
        self.path_frame.pack(pady=10, fill="x")

        self.blank_space = tk.Frame(self.path_frame, width=168)
        self.blank_space.pack(side=tk.LEFT)

        self.path_label = tk.Label(self.path_frame, text="选择文件夹:")
        self.path_label.pack(side=tk.LEFT)

        # 文件夹路径输入框
        self.folder_path_var = tk.StringVar()
        self.folder_entry = ttk.Combobox(self.path_frame, textvariable=self.folder_path_var, width=50)
        self.folder_entry.pack(side=tk.LEFT, padx=5, fill="x", expand=True)

        # 加载配置文件中的 character_folder 字典并填充下拉框
        self.populate_folder_dropdown()

        # 浏览按钮
        self.browse_button = tk.Button(self.path_frame, text="浏览...", command=self.browse_main_folder)
        self.browse_button.pack(side=tk.LEFT, padx=5)

        # 在下拉框值发生变化时调用 display_txt_files 方法
        self.folder_entry.bind("<<ComboboxSelected>>", self.on_folder_selected)

        # 刷新列表按钮
        self.refresh_list_button = tk.Button(self.path_frame, text="刷新列表", command=self.refresh_folder_list)
        self.refresh_list_button.pack(side=tk.LEFT, padx=5)

        self.refresh_model_button = tk.Button(self.path_frame, text="刷新模型", command=self.refresh_model_list)
        self.refresh_model_button.pack(side=tk.LEFT, padx=5)

        # 创建顶层框架用于放置头部和滚动区域
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        # 创建表头画布
        self.header_canvas = tk.Canvas(self.main_frame, height=30, highlightthickness=0)
        self.header_frame = tk.Frame(self.header_canvas)

        # 创建列表画布
        self.list_canvas = tk.Canvas(self.main_frame, highlightthickness=0)
        self.scroll_frame = tk.Frame(self.list_canvas)

        # 创建滚动条
        self.horizontal_scrollbar = tk.Scrollbar(self.main_frame, orient="horizontal",
                                                 command=self.sync_scroll_horizontal)
        self.vertical_scrollbar = tk.Scrollbar(self.main_frame, orient="vertical", command=self.list_canvas.yview)

        # 绑定配置变化
        self.scroll_frame.bind("<Configure>",
                               lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.header_frame.bind("<Configure>",
                               lambda e: self.header_canvas.configure(scrollregion=self.header_canvas.bbox("all")))

        # 将滚动区域添加到画布中
        self.header_window = self.header_canvas.create_window((0, 0), window=self.header_frame, anchor="nw")
        self.list_window = self.list_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        # 布局
        self.header_canvas.grid(row=0, column=0, sticky="ew")
        self.list_canvas.grid(row=1, column=0, sticky="nsew")
        self.horizontal_scrollbar.grid(row=2, column=0, sticky="ew")
        self.vertical_scrollbar.grid(row=1, column=1, sticky="ns")

        # 配置滚动条
        self.list_canvas.configure(xscrollcommand=self.horizontal_scrollbar.set,
                                   yscrollcommand=self.vertical_scrollbar.set)

        # 创建表头和内容
        self.create_header(self.header_frame)

        # 设置主框架的权重以支持动态调整
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

        self.list_canvas.bind("<MouseWheel>", self.scroll_canvas)
        self.list_canvas.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
        self.list_canvas.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

    def start_display_folders(self):
        initial_folder = self.folder_path_var.get()
        if initial_folder:
            if self.client is not None:
                self.refresh_model_list()

            self.display_folders(initial_folder)

    def on_folder_selected(self, event):
        """下拉框选择新路径时调用的函数"""
        selected_folder = self.folder_path_var.get()
        if selected_folder:
            self.clear_current_display()
            self.display_folders(selected_folder)  # 传入新的文件夹路径
            #self.refresh_model_list()

    def load_config(self):
        """加载配置文件并返回"""
        config_file = "config.json"
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as file:
                return json.load(file)
        else:
            print(f"配置文件 {config_file} 不存在!")
            return {}

    def populate_folder_dropdown(self):
        """将config.json中的character_folder加载到下拉框中"""
        # print("刷新了4")
        config_file = "config.json"
        if os.path.exists(config_file):
            # 读取配置文件
            with open(config_file, 'r', encoding='utf-8') as file:
                config_data = json.load(file)

            # 获取character_folder并更新下拉框
            character_folders = config_data.get('config', {}).get('character_folder', [])
            if character_folders:
                # 将folder paths加入到下拉框
                self.folder_entry['values'] = character_folders

                # 获取当前folder_path_var的值
                current_folder = self.folder_path_var.get()

                # 如果当前folder_path_var的值不在下拉框选项中，设置默认选项为第一个文件夹
                if current_folder not in character_folders:
                    self.folder_path_var.set(character_folders[0])  # 默认选择第一个文件夹
                else:
                    # 如果当前选中的文件夹在下拉框选项中，则不做任何修改
                    self.folder_path_var.set(current_folder)
            else:
                print(f"配置文件中未找到 'character_folder' 项！")
        else:
            print(f"配置文件 {config_file} 不存在!")

    def set_client(self, client):
        self.client = client
        # print("Client set in FolderAudioViewer.")
        self.refresh_model_list()

    def refresh_folder_list(self):
        """ 刷新文件夹内容 """
        folder_path = self.folder_path_var.get()
        if folder_path:  # 确保路径不为空
            self.clear_current_display()
            self.refresh_model_list()
            self.display_folders(folder_path)

        else:
            messagebox.showwarning("警告", "请先选择一个有效的文件夹。")

    def refresh_model_list(self):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        try:
            # 从 API 获取最新的模型列表
            result = self.client.predict(api_name="/change_choices")
            self.sovits_model_list = [choice[0] for choice in result[0]['choices']]
            self.gpt_model_list = [choice[0] for choice in result[1]['choices']]

            # 模型列表刷新成功后，自动点击每一行的刷新按钮
            for widget in self.scroll_frame.winfo_children():
                if isinstance(widget, tk.Button) and widget.cget("text") == "刷新单项模型":
                    widget.invoke()  # 调用按钮的命令

        except Exception as e:
            messagebox.showerror("错误", f"刷新模型列表失败: {str(e)}")

    def browse_main_folder(self):
        """ 让用户选择主文件夹并显示其中的子文件夹内容 """
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.folder_path_var.set(folder_selected)
            self.clear_current_display()  # 清空当前显示的内容
            self.display_folders(folder_selected)

    def clear_current_display(self):
        """ 清空当前显示的内容 """
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()  # 销毁 scroll_frame 中的所有小部件

    def export_character_config(self, folder_path, selected_option, top_k, top_p, temperature, speed, ref_free,
                                if_freeze,
                                sovits, gpt, ref_wav_path, prompt, ref_language, text_language, cut_method, delimiter):
        # 检查文件夹路径是否存在
        if not folder_path:
            messagebox.showerror("错误", "请选择一个有效的文件夹路径")
            return

        # 导出配置逻辑，例如写入文件等f
        config_data = {
            # 移除file_name字段
            "top_k": top_k.get(),
            "top_p": top_p.get(),
            "temperature": temperature.get(),
            "speed": speed.get(),
            "ref_free": ref_free.get(),
            "if_freeze": if_freeze.get(),
            "sovits": sovits.get(),
            "gpt": gpt.get(),
            "ref_wav_path": ref_wav_path.get(),
            "prompt": prompt.get(),
            "ref_language": ref_language.get(),
            "text_language": text_language.get(),
            "cut_method": cut_method.get(),
            "delimiter": delimiter.get()
        }

        # 使用选中的下拉框选项命名文件
        config_path = os.path.join(folder_path, f"{selected_option}.json")
        print(config_path, f"和", selected_option, f"B")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)

        messagebox.showinfo("成功", f"角色配置已导出到: {config_path}")

    def sync_scroll_horizontal(self, *args):
        """同步横向滚动"""
        self.header_canvas.xview(*args)
        self.list_canvas.xview(*args)

    def create_header(self, header_frame):
        headers = [
            ("    头像", 12), ("角色名", 13), ("配置名称", 27), ("SoVITS模型", 21), ("GPT模型", 38),
            ("参考音频路径", 52), ("提示文本", 29),
            ("参考语言", 20), ("生成语言", 15), ("top_k", 5), ("top_p", 5), ("温度", 4), ("语速", 3), ("无参考模式", 8),
            ("冻结设置", 11),
            ("分句内切割方式", 16), ("分句符", 6)
        ]

        for col, (header, width) in enumerate(headers):
            tk.Label(header_frame, text=header, anchor='w', width=width).grid(row=0, column=col, padx=5, pady=5,
                                                                              sticky="w")

    def get_subfolders(self, main_folder):
        if not os.path.exists(main_folder):  # 检查路径是否存在
            return []  # 返回空列表
        return [f for f in os.listdir(main_folder) if os.path.isdir(os.path.join(main_folder, f))]

    def get_audio_files(self, folder):
        return glob.glob(os.path.join(folder, "**/*.wav"), recursive=True)

    def display_folders(self, main_folder):
        subfolders = self.get_subfolders(main_folder)

        entry_width = 5
        check_width = 2
        option_width = 15
        long_entry_width = 40
        start_col = 1  # 起始列
        row_padding = 10  # 行间距
        column_padding = 5  # 列间距

        # 存储每一行的变量
        self.row_variables = {}

        for idx, folder in enumerate(subfolders):
            folder_path = os.path.join(main_folder, folder)

            # 显示头像
            self.display_avatar(folder_path, idx)

            # 显示文件夹名称
            label_name = tk.Label(self.scroll_frame, text=folder, font=("微软雅黑", 10), width=10, anchor="w")
            label_name.grid(row=idx, column=start_col, padx=column_padding, pady=row_padding, sticky="w")
            label_name.bind("<MouseWheel>", self.scroll_canvas)  # 绑定滚动事件
            label_name.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            label_name.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 创建选择配置文件的下拉菜单 combo_box_config
            config_files = self.get_json_files(folder_path)
            config_file_var = tk.StringVar(value="新建配置")

            # 添加下拉框中的选项
            combo_box_config = ttk.Combobox(self.scroll_frame, textvariable=config_file_var, width=option_width)
            combo_box_config['values'] = config_files + ["新建配置"]
            combo_box_config.grid(row=idx, column=start_col + 1, padx=column_padding, pady=row_padding, sticky="w")

            # 绑定选择事件
            combo_box_config.bind("<<ComboboxSelected>>",
                                  lambda e, fp=folder_path, cfg_var=config_file_var, index=idx:
                                  self.on_json_file_selected(fp, cfg_var.get(), index))

            # 创建音频文件下拉菜单
            audio_files = self.get_audio_files(folder_path)
            ref_wav_path_entry = tk.StringVar()
            prompt_var = tk.StringVar()

            # 单独创建并绑定 Entry 和 Checkbutton 控件
            top_k_var = tk.StringVar(value="15")
            top_k_entry = tk.Entry(self.scroll_frame, textvariable=top_k_var, width=entry_width)
            top_k_entry.grid(row=idx, column=start_col + 11, padx=column_padding, pady=row_padding, sticky="w")
            top_k_entry.bind("<MouseWheel>", self.scroll_canvas)
            top_k_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            top_k_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            top_p_var = tk.StringVar(value="1")
            top_p_entry = tk.Entry(self.scroll_frame, textvariable=top_p_var, width=entry_width)
            top_p_entry.grid(row=idx, column=start_col + 12, padx=column_padding, pady=row_padding, sticky="w")
            top_p_entry.bind("<MouseWheel>", self.scroll_canvas)
            top_p_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            top_p_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            temperature_var = tk.StringVar(value="1")
            temperature_entry = tk.Entry(self.scroll_frame, textvariable=temperature_var, width=entry_width)
            temperature_entry.grid(row=idx, column=start_col + 13, padx=column_padding, pady=row_padding, sticky="w")
            temperature_entry.bind("<MouseWheel>", self.scroll_canvas)
            temperature_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            temperature_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            speed_var = tk.StringVar(value="1")
            speed_entry = tk.Entry(self.scroll_frame, textvariable=speed_var, width=entry_width)
            speed_entry.grid(row=idx, column=start_col + 14, padx=column_padding, pady=row_padding, sticky="w")
            speed_entry.bind("<MouseWheel>", self.scroll_canvas)
            speed_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            speed_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            ref_free_var = tk.BooleanVar()
            ref_free_check = tk.Checkbutton(self.scroll_frame, variable=ref_free_var, width=check_width)
            ref_free_check.grid(row=idx, column=start_col + 15, padx=column_padding, pady=row_padding, sticky="w")
            ref_free_check.bind("<MouseWheel>", self.scroll_canvas)
            ref_free_check.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            ref_free_check.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            if_freeze_var = tk.BooleanVar()
            if_freeze_check = tk.Checkbutton(self.scroll_frame, variable=if_freeze_var, width=check_width)
            if_freeze_check.grid(row=idx, column=start_col + 16, padx=column_padding + 15, pady=row_padding, sticky="w")
            if_freeze_check.bind("<MouseWheel>", self.scroll_canvas)
            if_freeze_check.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            if_freeze_check.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            sovits_var = tk.StringVar(value="请选择")
            sovits_menu = tk.OptionMenu(self.scroll_frame, sovits_var, "请先刷新模型")
            sovits_menu.config(width=option_width)
            sovits_menu.grid(row=idx, column=start_col + 3, padx=column_padding, pady=row_padding, sticky="w")
            sovits_menu.bind("<MouseWheel>", self.scroll_canvas)
            sovits_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            sovits_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            gpt_var = tk.StringVar(value="请选择")
            gpt_menu = tk.OptionMenu(self.scroll_frame, gpt_var, "请先刷新模型")
            gpt_menu.config(width=option_width)
            gpt_menu.grid(row=idx, column=start_col + 4, padx=column_padding, pady=row_padding, sticky="w")
            gpt_menu.bind("<MouseWheel>", self.scroll_canvas)
            gpt_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            gpt_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 刷新模型
            refresh_button = tk.Button(self.scroll_frame, text="刷新单项模型",
                                       command=lambda sm=sovits_menu, gm=gpt_menu, sv=sovits_var,
                                                      gv=gpt_var: self.run_update_model_choices(sm, gm, sv, gv))
            # refresh_button.grid(row=idx, column=start_col + 11, padx=column_padding, pady=row_padding, sticky="w")

            ref_language_var = tk.StringVar(value="请选择")
            ref_language_menu = tk.OptionMenu(self.scroll_frame, ref_language_var, "请先确认模型")
            ref_language_menu.config(width=option_width)
            ref_language_menu.grid(row=idx, column=start_col + 9, padx=column_padding, pady=row_padding, sticky="w")
            ref_language_menu.bind("<MouseWheel>", self.scroll_canvas)
            ref_language_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            ref_language_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            text_language_var = tk.StringVar(value="请选择")
            text_language_menu = tk.OptionMenu(self.scroll_frame, text_language_var, "请先确认模型")
            text_language_menu.config(width=option_width)
            text_language_menu.grid(row=idx, column=start_col + 10, padx=column_padding, pady=row_padding, sticky="w")
            text_language_menu.bind("<MouseWheel>", self.scroll_canvas)
            text_language_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            text_language_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            confirm_button = tk.Button(self.scroll_frame, text="确认模型",
                                       command=lambda sv=sovits_var, gv=gpt_var, rlv=ref_language_var,
                                                      tlv=text_language_var, frm=self.scroll_frame,
                                                      sc=start_col, lin=idx: self.run_confirm_gpt_model(sv, gv, rlv,
                                                                                                        tlv, frm,
                                                                                                        sc, lin))
            confirm_button.grid(row=idx, column=start_col + 5, padx=column_padding, pady=row_padding, sticky="w")
            confirm_button.bind("<MouseWheel>", self.scroll_canvas)
            confirm_button.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            confirm_button.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            cut_method_var = tk.StringVar(value="凑四句一切")
            cut_method_menu = tk.OptionMenu(self.scroll_frame, cut_method_var, "不切", "凑四句一切", "凑50字一切",
                                            "按中文句号。切",
                                            "按英文句号.切", "按标点符号切")
            cut_method_menu.config(width=option_width)
            cut_method_menu.grid(row=idx, column=start_col + 17, padx=column_padding, pady=row_padding, sticky="w")
            cut_method_menu.bind("<MouseWheel>", self.scroll_canvas)
            cut_method_menu.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            cut_method_menu.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 分隔符 Entry (绑定滚动事件)
            delimiter_entry = tk.StringVar(value="|")
            delimiter_entry_field = tk.Entry(self.scroll_frame, textvariable=delimiter_entry, width=entry_width)
            delimiter_entry_field.grid(row=idx, column=start_col + 18, padx=column_padding, pady=row_padding,
                                       sticky="w")
            delimiter_entry_field.bind("<MouseWheel>", self.scroll_canvas)
            delimiter_entry_field.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            delimiter_entry_field.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            combo_box = ttk.Combobox(self.scroll_frame, textvariable=ref_wav_path_entry, width=long_entry_width)
            combo_box['values'] = audio_files
            combo_box.grid(row=idx, column=start_col + 6, padx=column_padding, pady=row_padding, sticky="w")

            # 添加“浏览...”按钮
            browse_button = tk.Button(self.scroll_frame, text="浏览...",
                                      command=lambda var=ref_wav_path_entry, combo=combo_box: self.browse_wav_file(var,
                                                                                                                   combo,
                                                                                                                   idx))
            browse_button.grid(row=idx, column=start_col + 7, padx=column_padding, pady=row_padding, sticky="w")
            browse_button.bind("<MouseWheel>", self.scroll_canvas)
            browse_button.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            browse_button.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 禁止在下拉框上使用滚轮
            # combo_box.bind("<MouseWheel>", lambda e: "break")

            result_entry = tk.Entry(self.scroll_frame, textvariable=prompt_var, width=long_entry_width)
            result_entry.grid(row=idx, column=start_col + 8, padx=column_padding, pady=row_padding, sticky="w")
            result_entry.bind("<MouseWheel>", self.scroll_canvas)
            result_entry.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            result_entry.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            combo_box.bind("<<ComboboxSelected>>",
                           lambda e, var=ref_wav_path_entry, result=prompt_var,
                                  ref_lang1=ref_language_var, ref_lang2=text_language_var: self.update_text(
                               var.get(), result, ref_lang1, ref_lang2))

            self.auto_choice_model(idx, folder, start_col)

            # if audio_files:

            # else:
            # label_no_audio = tk.Label(self.scroll_frame, text="No .wav files", fg="gray")
            # label_no_audio.grid(row=idx, column=start_col + 12, padx=column_padding, pady=row_padding, sticky="w")

            # 导出角色配置按钮，并传递当前行的所有变量到 lambda 中，确保每个按钮绑定当前行的配置
            export_button = tk.Button(self.scroll_frame, text="导出配置",
                                      command=lambda fp=folder_path,
                                                     so=config_file_var,  # 确保此时获取值
                                                     top_k=top_k_var,
                                                     top_p=top_p_var,
                                                     temperature=temperature_var,
                                                     speed=speed_var,
                                                     ref_free=ref_free_var,
                                                     if_freeze=if_freeze_var,
                                                     sovits=sovits_var,
                                                     gpt=gpt_var,
                                                     ref_wav_path=ref_wav_path_entry,
                                                     prompt=prompt_var,
                                                     ref_language=ref_language_var,
                                                     text_language=text_language_var,
                                                     cut_method=cut_method_var,
                                                     delimiter=delimiter_entry:
                                      self.export_character_config(fp, so.get(), top_k, top_p, temperature,
                                                                   speed,
                                                                   ref_free, if_freeze, sovits, gpt,
                                                                   ref_wav_path, prompt, ref_language, text_language,
                                                                   cut_method, delimiter))

            export_button.grid(row=idx, column=start_col + 2, padx=5, pady=5, sticky="w")
            export_button.bind("<MouseWheel>", self.scroll_canvas)
            export_button.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            export_button.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

            # 将当前行的变量存储到字典中
            self.row_variables[idx] = {
                'top_k': top_k_var,
                'top_p': top_p_var,
                'temperature': temperature_var,
                'speed': speed_var,
                'ref_free': ref_free_var,
                'if_freeze': if_freeze_var,
                'sovits': sovits_var,
                'gpt': gpt_var,
                'ref_wav_path': ref_wav_path_entry,
                'combo_box_ref_wav_path': combo_box,
                'prompt': prompt_var,
                'ref_language': ref_language_var,
                'text_language': text_language_var,
                'cut_method': cut_method_var,
                'delimiter': delimiter_entry
            }

            self.auto_choice_audio(idx, audio_files)
            self.update_text(ref_wav_path_entry.get(), prompt_var, ref_language_var, text_language_var)

        # 添加滚动功能
        self.scroll_frame.bind("<MouseWheel>", lambda e: self.scroll_canvas(e))
        self.scroll_frame.bind("<Button-4>", lambda e: self.scroll_canvas(e))  # macOS 向上滚动
        self.scroll_frame.bind("<Button-5>", lambda e: self.scroll_canvas(e))  # macOS 向下滚动

    def auto_choice_model(self, idx, selected_charactor, start_col):
        """根据selected_charactor值更新下拉框选择项"""
        #print(f"匹配{selected_charactor}")
        # 获取当前行的下拉菜单变量
        sovits_menu = self.scroll_frame.grid_slaves(row=idx, column=start_col + 3)[0]  # SoVITS下拉菜单
        gpt_menu = self.scroll_frame.grid_slaves(row=idx, column=start_col + 4)[0]  # GPT下拉菜单

        # 提取文件名并匹配selected_charactor
        sovits_model_paths = [
            path for path in self.sovits_model_list if selected_charactor in os.path.basename(path)
        ]
        gpt_model_paths = [
            path for path in self.gpt_model_list if selected_charactor in os.path.basename(path)
        ]

        # 设置默认选择项（如果没有匹配的模型，则选择第一个选项，或显示"无匹配模型"）
        selected_sovits = sovits_model_paths[0] if sovits_model_paths else "请选择"
        selected_gpt = gpt_model_paths[0] if gpt_model_paths else "请选择"

        # 更新SoVITS菜单的当前选择
        sovits_menu.setvar(sovits_menu.cget("textvariable"), selected_sovits)

        # 更新GPT菜单的当前选择
        gpt_menu.setvar(gpt_menu.cget("textvariable"), selected_gpt)

    def auto_choice_audio(self, idx, audio_files):
        """更新参考音频下拉框选项，并自动选择路径最短且文件名最长的 .wav 文件"""
        if not audio_files:
            # 如果没有 .wav 文件，清空下拉框并退出
            combo_box = self.row_variables[idx]['combo_box_ref_wav_path']
            combo_box['values'] = []
            return

        # 找到路径最短且在路径相同时文件名最长的文件
        def get_file_priority(file_path):
            dir_path, file_name = os.path.split(file_path)
            return (len(dir_path), -len(file_name))  # 按路径长度升序，文件名长度降序排序

        selected_file = min(audio_files, key=get_file_priority)

        # 更新下拉框
        combo_box = self.row_variables[idx]['combo_box_ref_wav_path']
        combo_box['values'] = audio_files  # 更新下拉框的值
        combo_box.set(selected_file)  # 自动选择最优文件

    def get_json_files(self, folder):
        """获取文件夹中的所有 JSON 文件"""
        json_files = glob.glob(os.path.join(folder, "*.json"))
        # 仅返回文件名（去掉路径和扩展名）
        return [os.path.splitext(os.path.basename(f))[0] for f in json_files]

    def on_json_file_selected(self, folder_path, selected_file, idx):
        """选择 JSON 文件后应用配置"""
        if selected_file == "新建配置":
            # 如果选择“新建配置”，则不执行任何操作
            return

        config_file_path = os.path.join(folder_path, f"{selected_file}.json")
        try:
            with open(config_file_path, 'r', encoding='utf-8') as file:
                config_data = json.load(file)

            # 检查是否存在 row_variables
            if idx not in self.row_variables:
                raise ValueError(f"Row {idx} does not exist.")

            # 获取当前行的变量
            row_vars = self.row_variables[idx]

            # 更新对应的变量
            row_vars['top_k'].set(config_data.get('top_k', '15'))  # 默认值为 15
            row_vars['top_p'].set(config_data.get('top_p', '1'))  # 默认值为 1
            row_vars['temperature'].set(config_data.get('temperature', '1'))  # 默认值为 1
            row_vars['speed'].set(config_data.get('speed', '1'))  # 默认值为 1
            row_vars['ref_free'].set(config_data.get('ref_free', False))  # 默认值为 False
            row_vars['if_freeze'].set(config_data.get('if_freeze', False))  # 默认值为 False
            row_vars['sovits'].set(config_data.get('sovits', '请选择'))  # 默认值为 '请选择'
            row_vars['gpt'].set(config_data.get('gpt', '请选择'))  # 默认值为 '请选择'
            row_vars['ref_wav_path'].set(config_data.get('ref_wav_path', ''))  # 默认值为 ''
            row_vars['prompt'].set(config_data.get('prompt', ''))  # 默认值为 ''
            row_vars['ref_language'].set(config_data.get('ref_language', '请选择'))  # 默认值为 '请选择'
            row_vars['text_language'].set(config_data.get('text_language', '请选择'))  # 默认值为 '请选择'
            row_vars['cut_method'].set(config_data.get('cut_method', '凑四句一切'))  # 默认值为 '凑四句一切'
            row_vars['delimiter'].set(config_data.get('delimiter', '|'))  # 默认值为 '|'

        except Exception as e:
            messagebox.showerror("错误", f"导入配置时发生错误：{str(e)}")

    def update_row_with_config(self, row_index, config):
        # 确保 row_index 存在于 row_variables 中
        if row_index in self.row_variables:
            row_vars = self.row_variables[row_index]

            # 使用配置文件中的值更新各个变量
            row_vars["top_k_var"].set(config.get("top_k", "15"))
            row_vars["top_p_var"].set(config.get("top_p", "1"))
            row_vars["temperature_var"].set(config.get("temperature", "1"))
            row_vars["speed_var"].set(config.get("speed", "1"))
            row_vars["ref_free_var"].set(config.get("ref_free", False))
            row_vars["if_freeze_var"].set(config.get("if_freeze", False))
            row_vars["sovits_var"].set(config.get("sovits", "请选择"))
            row_vars["gpt_var"].set(config.get("gpt", "请选择"))
            row_vars["ref_wav_path_entry"].set(config.get("ref_wav_path", ""))
            row_vars["prompt_var"].set(config.get("prompt", ""))
            row_vars["ref_language_var"].set(config.get("ref_language", "请选择"))
            row_vars["text_language_var"].set(config.get("text_language", "请选择"))
            row_vars["cut_method_var"].set(config.get("cut_method", "凑四句一切"))
            row_vars["delimiter_entry"].set(config.get("delimiter", "|"))
        else:
            print(f"Row {row_index} does not exist.")

    def run_update_model_choices(self, sovits_menu, gpt_menu, sovits_var, gpt_var):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        # 创建线程并运行 update_model_choices
        thread = threading.Thread(target=self.update_model_choices,
                                  args=(sovits_menu, gpt_menu, sovits_var, gpt_var))

        thread.start()

    @check_using_api
    def run_confirm_gpt_model(self, sovits_var, gpt_var, ref_language_var, text_language_var, frame, start_col, row):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

        # 创建线程并运行 confirm_gpt_model
        thread = threading.Thread(target=self.confirm_gpt_model,
                                  args=(
                                      sovits_var, gpt_var, ref_language_var, text_language_var, frame, start_col, row))
        thread.start()

    def update_model_choices(self, sovits_menu, gpt_menu, sovits_var, gpt_var):
        if not self.sovits_model_list or not self.gpt_model_list:
            tk.messagebox.showerror("Error", "模型列表为空，请先刷新模型。")
            return

        sovits_menu['menu'].delete(0, 'end')
        for choice in self.sovits_model_list:
            sovits_menu['menu'].add_command(label=choice, command=lambda val=choice: sovits_var.set(val))

        gpt_menu['menu'].delete(0, 'end')
        for choice in self.gpt_model_list:
            gpt_menu['menu'].add_command(label=choice, command=lambda val=choice: gpt_var.set(val))

    def confirm_gpt_model(self, sovits_var, gpt_var, ref_language_var, text_language_var, frame, start_col, row):
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return
        sovits_model = sovits_var.get()
        gpt_model = gpt_var.get()

        if sovits_model == "请选择" or gpt_model == "请选择":
            messagebox.showwarning("警告", "请选择有效的SoVITS模型和GPT模型")
            return

        try:
            # 提交选中的SoVITS模型到API
            sovits_result = self.client.predict(
                sovits_path=sovits_model,
                api_name="/change_sovits_weights"
            )

            # 提交选中的GPT模型到API
            gpt_result = self.client.predict(
                gpt_path=gpt_model,
                api_name="/change_gpt_weights"
            )

            # 从SoVITS模型的API返回中提取参考语言和生成语言选项
            ref_language_choices = [choice[0] for choice in sovits_result[0]['choices']]
            gen_language_choices = [choice[0] for choice in sovits_result[1]['choices']]

            # 获取点击的按钮所在行的下拉菜单
            ref_language_menu = frame.grid_slaves(row=row, column=start_col + 9)[0]
            text_language_menu = frame.grid_slaves(row=row, column=start_col + 10)[0]

            # 更新参考语言下拉菜单的选项
            ref_language_menu['menu'].delete(0, 'end')
            for choice in ref_language_choices:
                ref_language_menu['menu'].add_command(label=choice, command=tk._setit(ref_language_var, choice))

            # 更新生成语言下拉菜单的选项
            text_language_menu['menu'].delete(0, 'end')
            for choice in gen_language_choices:
                text_language_menu['menu'].add_command(label=choice, command=tk._setit(text_language_var, choice))

        except Exception as e:
            messagebox.showerror("错误", str(e))

    def scroll_canvas(self, event):
        """处理鼠标滚轮事件"""
        if event.num == 4 or event.delta > 0:
            self.list_canvas.yview_scroll(-1, "units")  # 向上滚动
        elif event.num == 5 or event.delta < 0:
            self.list_canvas.yview_scroll(1, "units")  # 向下滚动

    def display_avatar(self, folder, row, column=0):
        # 尝试显示 avatar.png 图像
        avatar_path = os.path.join(folder, "avatar.png")
        if os.path.exists(avatar_path):
            img = Image.open(avatar_path)
            img = self.crop_to_square(img)  # 剪切为 1:1 比例
            img = img.resize((50, 50), Image.LANCZOS)  # 使用 LANCZOS 算法调整图像大小
            img_tk = ImageTk.PhotoImage(img)
            label_img = tk.Label(self.scroll_frame, image=img_tk)
            label_img.image = img_tk  # 保持引用防止垃圾回收
            label_img.grid(row=row, column=column, padx=10, pady=5, sticky="w")
            label_img.bind("<MouseWheel>", self.scroll_canvas)
            label_img.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            label_img.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动
            return

        # 如果 avatar.png 不存在，查找名为 avatar 的文件
        avatar_image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.ico')
        avatar_images = []

        for ext in avatar_image_extensions:
            avatar_file = os.path.join(folder, f"avatar{ext}")
            if os.path.exists(avatar_file):
                avatar_images.append(avatar_file)

        if avatar_images:
            # 如果找到多个 avatar 文件，选择比例最接近 1:1 的文件
            best_image = None
            best_ratio_diff = float('inf')

            for avatar_file in avatar_images:
                try:
                    img = Image.open(avatar_file)
                    img = self.crop_to_square(img)  # 剪切为 1:1 比例
                    width, height = img.size
                    ratio = width / height

                    # 查找比例最接近 1:1 的图像
                    ratio_diff = abs(ratio - 1)
                    if ratio_diff < best_ratio_diff:
                        best_ratio_diff = ratio_diff
                        best_image = img

                except Exception as e:
                    print(f"无法打开图像 {avatar_file}: {e}")

            # 显示找到的最佳 avatar 图像
            if best_image is not None:
                best_image = best_image.resize((50, 50), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(best_image)
                label_img = tk.Label(self.scroll_frame, image=img_tk)
                label_img.image = img_tk  # 保持引用防止垃圾回收
                label_img.grid(row=row, column=column, padx=10, pady=5, sticky="w")
                label_img.bind("<MouseWheel>", self.scroll_canvas)
                label_img.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
                label_img.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动
                return

        # 如果没有 avatar.png，也没有名为 avatar 的图像，查找其他图像格式
        image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.ico')
        best_image = None
        best_ratio_diff = float('inf')

        for filename in os.listdir(folder):
            if filename.lower().endswith(image_extensions):
                image_path = os.path.join(folder, filename)
                try:
                    img = Image.open(image_path)
                    img = self.crop_to_square(img)  # 剪切为 1:1 比例
                    width, height = img.size
                    ratio = width / height

                    # 查找比例最接近 1:1 的图像
                    ratio_diff = abs(ratio - 1)
                    if ratio_diff < best_ratio_diff:
                        best_ratio_diff = ratio_diff
                        best_image = img

                except Exception as e:
                    print(f"无法打开图像 {filename}: {e}")

        # 显示找到的最佳图像，或者占位符
        if best_image is not None:
            best_image = best_image.resize((50, 50), Image.LANCZOS)
            img_tk = ImageTk.PhotoImage(best_image)
            label_img = tk.Label(self.scroll_frame, image=img_tk)
            label_img.image = img_tk  # 保持引用防止垃圾回收
            label_img.grid(row=row, column=column, padx=10, pady=5, sticky="w")
            label_img.bind("<MouseWheel>", self.scroll_canvas)
            label_img.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            label_img.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动
        else:
            # 没有任何图像时显示占位符
            label_img = tk.Label(self.scroll_frame, text="[无头像]", width=7, height=3)
            label_img.grid(row=row, column=column, padx=10, pady=5, sticky="w")
            label_img.bind("<MouseWheel>", self.scroll_canvas)
            label_img.bind("<Button-4>", self.scroll_canvas)  # macOS 向上滚动
            label_img.bind("<Button-5>", self.scroll_canvas)  # macOS 向下滚动

    def crop_to_square(self, img):
        """将图像裁剪为 1:1 比例"""
        width, height = img.size
        if width > height:
            # 裁剪左右
            new_width = height
            left = (width - new_width) / 2
            right = left + new_width
            img = img.crop((left, 0, right, height))
        elif height > width:
            # 裁剪上下
            new_height = width
            top = (height - new_height) / 2
            bottom = top + new_height
            img = img.crop((0, top, width, bottom))
        # 如果宽高相等，什么也不做
        return img

    def update_text(self, audio_file, prompt_var, ref_language_var, text_language_var):
        filename = os.path.basename(audio_file)

        if "#" in filename:
            # 分割文件名，获取最后一个 '#' 后的部分
            parts = filename.split("#")
            if len(parts) >= 2:  # 确保有足够的 '#' 来获取最后两个 '#'
                # 使用原有方法判断
                text_between_hash = parts[-2]

                # 根据文本判断语言并设置 ref_language_var
                if text_between_hash in ["zh", "中文"]:
                    ref_language_var.set("中文")
                    text_language_var.set("中文")
                elif text_between_hash in ["en", "英文"]:
                    ref_language_var.set("英文")
                    text_language_var.set("英文")
                elif text_between_hash in ["ja", "日文"]:
                    ref_language_var.set("日文")
                    text_language_var.set("日文")

                # 处理最后一个 '#' 后面的文本
                text_after_hash = parts[-1]
                # 找到最后一个 '.' 的索引
                last_dot_index = text_after_hash.rfind('.')
                # 如果找到了 '.'，则提取其前面的文本
                if last_dot_index != -1:
                    text_after_hash = text_after_hash[:last_dot_index]
                prompt_var.set(text_after_hash)
            else:
                prompt_var.set("")  # 如果没有足够的 '#'，则清空 prompt_var
        else:
            # 删除末尾的 .wav 扩展名
            cleaned_text = filename.rstrip('.wav').strip()

            # 删除句子前【】符号内的内容
            cleaned_text = re.sub(r'【.*?】', '', cleaned_text).strip()

            # 判断语言
            def contains_chinese(text):
                return bool(re.search(r'[\u4e00-\u9fff]', text))

            def contains_japanese(text):
                # 只匹配不包含中文的日文字符
                return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF\u32D0-\u32FF]', text))

            def contains_english(text):
                return bool(re.search(r'[a-zA-Z]', text))

            # 语言检测
            has_chinese = contains_chinese(cleaned_text)
            has_japanese = contains_japanese(cleaned_text)
            has_english = contains_english(cleaned_text)

            # 语言组合逻辑：日文优先
            if has_japanese and has_english:
                ref_language_var.set("日英混合")
                text_language_var.set("日英混合")
            elif has_japanese:
                ref_language_var.set("日文")
                text_language_var.set("日文")
            elif has_chinese and has_english:
                ref_language_var.set("中英混合")
                text_language_var.set("中英混合")
            elif has_chinese:
                ref_language_var.set("中文")
                text_language_var.set("中文")
            elif has_english:
                ref_language_var.set("英文")
                text_language_var.set("英文")
            else:
                ref_language_var.set("未知")
                text_language_var.set("未知")

            # 设置提示文本
            prompt_var.set(cleaned_text)

    def browse_wav_file(self, ref_wav_path_entry, combo_box, idx):
        file_path = filedialog.askopenfilename(filetypes=[("WAV files", "*.wav")])
        if file_path:
            ref_wav_path_entry.set(file_path)  # 设置选中的文件路径到 Entry 变量中
            combo_box.set(file_path)  # 将文件路径填充到下拉框中

            # 手动触发 <<ComboboxSelected>> 事件
            combo_box.event_generate("<<ComboboxSelected>>")


class Console(tk.Tk):
    def __init__(self):
        super().__init__()
        # self.title("Python Console")
        # self.geometry("800x600")

        # 创建滚动文本框作为控制台输出
        self.console_output = ScrolledText(self, state='disabled', wrap='word', font=('微软雅黑', 12))
        self.console_output.pack(expand=True, fill=tk.BOTH)

        # 创建输入框和按钮
        self.input_frame = tk.Frame(self)
        # self.input_frame.pack(fill=tk.X)

        self.command_entry = tk.Entry(self.input_frame, font=('微软雅黑', 12))
        # self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.command_entry.bind("<Return>", self.execute_command)

        self.run_button = tk.Button(self.input_frame, text="Run", command=self.execute_command)
        # self.run_button.pack(side=tk.RIGHT, padx=5, pady=5)

        # 重定向标准输出和错误输出
        sys.stdout = self
        sys.stderr = self

    def write(self, message):
        self.console_output.config(state='normal')
        self.console_output.insert(tk.END, message)
        self.console_output.see(tk.END)
        self.console_output.config(state='disabled')

    def flush(self):
        pass

    def execute_command(self, event=None):
        # 获取用户输入的命令
        command = self.command_entry.get()
        self.command_entry.delete(0, tk.END)

        # 打印用户输入的命令到控制台
        self.write(f">>> {command}\n")

        try:
            # 执行用户输入的代码
            exec(command, globals())
        except Exception as e:
            self.write(f"{e}\n")


def main():
    global root
    # 创建GUI窗口
    root = tk.Tk()
    root.title("多角色有声书生成器")

    # 设置窗口最小尺寸
    root.minsize(1000, 600)
    root.geometry("1000x600")

    global folder_audio_viewer
    global voice_generator_app
    global notebook_main
    global main_tab2

    # 创建选项卡容器
    notebook_main = Notebook(root)
    notebook_main.grid(row=0, column=0, padx=5, pady=5, columnspan=3, sticky="nsew")

    # 配置 root，使其自动调整大小
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    # 创建选项卡1和选项卡2
    main_tab1 = tk.Frame(notebook_main)
    main_tab2 = tk.Frame(notebook_main)
    main_tab3 = tk.Frame(notebook_main)
    main_tab4 = tk.Frame(notebook_main)
    main_tab5 = tk.Frame(notebook_main)

    # 将选项卡添加到Notebook中
    notebook_main.add(main_tab1, text="项目管理器")
    notebook_main.add(main_tab2, text="文本预处理")
    notebook_main.add(main_tab3, text="分角色朗读")
    notebook_main.add(main_tab4, text="角色管理器")
    notebook_main.add(main_tab5, text="内置控制台")
    notebook_main.pack(expand=1, fill="both")

    def add_console_to_tab(tab):
        """
        将控制台 UI 添加到指定的选项卡中。
        """
        # 创建滚动文本框作为控制台输出
        console_output = scrolledtext.ScrolledText(tab, state='disabled', wrap='word', font=('微软雅黑', 12))
        console_output.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

        # 创建输入框和按钮
        input_frame = tk.Frame(tab)
        # input_frame.pack(fill=tk.X, padx=5, pady=5)

        command_entry = tk.Entry(input_frame, font=('微软雅黑', 12))
        # command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        run_button = tk.Button(input_frame, text="Run", font=('Consolas', 12))

        # run_button.pack(side=tk.RIGHT, padx=5)

        # 重定向 sys.stdout 和 sys.stderr 到控制台
        class ConsoleRedirector:
            def __init__(self, widget):
                self.widget = widget

            def write(self, message):
                self.widget.config(state='normal')
                self.widget.insert(tk.END, message)
                self.widget.see(tk.END)
                self.widget.config(state='disabled')

            def flush(self):
                pass

        sys.stdout = ConsoleRedirector(console_output)
        sys.stderr = ConsoleRedirector(console_output)

        def execute_command(event=None):
            """执行用户输入的命令"""
            command = command_entry.get()
            command_entry.delete(0, tk.END)
            print(f">>> {command}")  # 打印用户输入的命令

            try:
                exec(command, globals())
            except Exception as e:
                print(e)

        # 绑定回车键和按钮点击事件
        command_entry.bind("<Return>", execute_command)
        run_button.config(command=execute_command)

    # 在 main() 中调用该函数
    add_console_to_tab(main_tab5)

    # 先创建 StartMenu 实例
    start_menu = StartMenu(main_tab1, None)

    # 实例化 FolderAudioViewer 实例
    folder_audio_viewer = FolderAudioViewer(main_tab4)

    # 然后实例化 VoiceGeneratorApp
    voice_generator_app = VoiceGeneratorApp(main_tab3, folder_audio_viewer.folder_path_var, start_menu)

    # 再实例化 TextPreprocessor，并传递给 StartMenu
    text_preprocessor = TextPreprocessor(main_tab2, start_menu)

    # 在 TextPreprocessor 内部访问已实例化的 voice_generator_app
    voice_generator_app.load_folders()  # 此时可以正确调用

    # 赋值 text_preprocessor 到 StartMenu
    start_menu.text_preprocessor = text_preprocessor  # 更新 StartMenu 中的 text_preprocessor 引用

    # 初始化时连接服务
    start_menu.run_connect_to_gradio_start()

    #folder_audio_viewer.start_display_folders()

    def set_initial_focus():
        # 假设希望在 tab1 的文本框中输入
        start_menu.folder_path_entry.focus_set()
        start_menu.folder_path_entry.focus_force()

    # 初始化时设置焦点
    set_initial_focus()

    def on_tab_switch(event):
        selected_tab = notebook_main.index("current")

        if selected_tab == 2:  # "分角色朗读"选项卡
            voice_generator_app.load_folders()
        elif selected_tab == 3:  # "角色管理器"选项卡
            folder_audio_viewer.load_config()
            folder_audio_viewer.populate_folder_dropdown()

    # 绑定选项卡切换事件
    notebook_main.bind("<<NotebookTabChanged>>", on_tab_switch)

    def on_close():
        """处理关闭 Tkinter 主窗口时的操作"""
        chat_window = ChatGUI()
        if chat_window:
            chat_window.close()  # 关闭 ChatGUI 窗口
        root.quit()  # 退出 Tkinter 事件循环
        sys.exit(0)  # 退出程序

    # 绑定窗口关闭事件，确保关闭 Tkinter 窗口时，关闭 ChatGUI 窗口
    root.protocol("WM_DELETE_WINDOW", on_close)

    # 启动主循环
    root.mainloop()


if __name__ == "__main__":
    Chat_app = QApplication(sys.argv)  # 创建 QApplication 实例
    main()  # 启动 Tkinter 主窗口
    sys.exit(Chat_app.exec_())  # 启动 PyQt5 事件循环

# 程序打包指令1(先执行)：Pyinstaller -F -w -i sd.ico tts4.2.3.py
# 程序打包指令2(后执行)：Pyinstaller -F -w -i sd.ico tts4.2.3.py --collect-data=gradio_client --collect-data=gradio