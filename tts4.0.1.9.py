import os
import shutil
import time
import glob
import threading
import re
import queue
import json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, Scrollbar, VERTICAL, HORIZONTAL, ttk
from tkinter.ttk import Progressbar, Notebook
from PIL import Image, ImageTk
from gradio_client import Client, handle_file
from pydub import AudioSegment

# 初始化Gradio客户端
#client = Client("http://localhost:9872/")
client = None

# 定义全局标志变量来控制运行时间更新
update_time_running = True

# 创建全局锁
api_lock = threading.Lock()

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

def connect_to_gradio():
    global client  # 确保在函数中修改全局变量
    url = url_entry.get()  # 获取文本框中的 URL
    try:
        client = Client(url)  # 初始化 Gradio 客户端
        folder_audio_viewer.set_client(client)  # 将 client 赋值给 FolderAudioViewer 实例
        voice_generator_app.set_client(client)  # 将 client 赋值给 VoiceGeneratorApp 实例
        print(f"Connected to {url}")
        tk.messagebox.showinfo("Connection", f"Connected to {url}")
    except Exception as e:
        print(f"Failed to connect to {url}: {e}")
        tk.messagebox.showerror("Connection Error", f"Failed to connect to {url}: 请启动WebUI并开启TTS推理，在推理UI启动后连接到WebUI地址{e}")

def run_update_model_choices():
    thread = threading.Thread(target=update_model_choices)
    thread.start()

@check_using_api
def run_submit():
    thread = threading.Thread(target=submit)
    thread.start()
    print("Submitted")

def update_model_choices():
    if client is None:
        tk.messagebox.showerror("Error", "Not connected to Gradio server.")
        return
    # Request model choices from the API
    result = client.predict(api_name="/change_choices")

    # Extract SoVITS and GPT model choices from the result
    sovits_choices = [choice[0] for choice in result[0]['choices']]
    gpt_choices = [choice[0] for choice in result[1]['choices']]

    # Update the options in the dropdown menus
    sovits_menu['menu'].delete(0, 'end')
    gpt_menu['menu'].delete(0, 'end')

    for choice in sovits_choices:
        sovits_menu['menu'].add_command(label=choice, command=tk._setit(sovits_var, choice))

    for choice in gpt_choices:
        gpt_menu['menu'].add_command(label=choice, command=tk._setit(gpt_var, choice))


def submit():
    if client is None:
        tk.messagebox.showerror("Error", "Not connected to Gradio server.")
        return
    sovits_model = sovits_var.get()
    gpt_model = gpt_var.get()

    # Submit the selected SoVITS model to the API
    sovits_result = client.predict(
        sovits_path=sovits_model,
        api_name="/change_sovits_weights"
    )

    # Submit the selected GPT model to the API
    gpt_result = client.predict(
        gpt_path=gpt_model,
        api_name="/change_gpt_weights"
    )

    # 提取参考语言和生成语言的选项
    ref_language_choices = [choice[0] for choice in sovits_result[0]['choices']]
    gen_language_choices = [choice[0] for choice in sovits_result[1]['choices']]

    # 更新参考语言下拉菜单的选项
    prompt_language_menu['menu'].delete(0, 'end')
    for choice in ref_language_choices:
        prompt_language_menu['menu'].add_command(label=choice, command=tk._setit(prompt_language_var, choice))

    # 更新生成语言下拉菜单的选项
    text_language_menu['menu'].delete(0, 'end')
    for choice in gen_language_choices:
        text_language_menu['menu'].add_command(label=choice, command=tk._setit(text_language_var, choice))

def update_language_options():
    if client is None:
        tk.messagebox.showerror("Error", "Not connected to Gradio server.")
        return
    # 请求参考语言和生成语言的选项从API
    result = client.predict(api_name="/change_sovits_weights")

    # 提取参考语言和生成语言的选项
    ref_language_choices = [choice[0] for choice in result[0]['choices']]
    gen_language_choices = [choice[0] for choice in result[1]['choices']]


    # 更新参考语言下拉菜单的选项
    prompt_language_menu['menu'].delete(0, 'end')
    for choice in ref_language_choices:
        prompt_language_menu['menu'].add_command(label=choice, command=tk._setit(prompt_language_var, choice))

    # 更新生成语言下拉菜单的选项
    text_language_menu['menu'].delete(0, 'end')
    for choice in gen_language_choices:
        text_language_menu['menu'].add_command(label=choice, command=tk._setit(text_language_var, choice))

def escape_regex_chars(pattern):
    """转义正则表达式中的特殊字符"""
    return re.escape(pattern)

def split_text(text, delimiter):
    """根据给定的分隔符分割文本"""
    if delimiter:
        # 转义自定义分隔符
        escaped_delimiter = escape_regex_chars(delimiter)
        # 使用转义后的分隔符进行分割
        sentences = re.split(escaped_delimiter, text)
    else:
        sentences = [text]
    return [s.strip() for s in sentences if s.strip()]


def update_progress_bar(index, total, start_time):
    """更新进度条和显示标签"""
    progress_bar["value"] = index + 1
    percentage = (index + 1) / total * 100
    percentage_label.config(text=f"进度: {int(percentage)}%")

    # 计算预估剩余时间
    elapsed_time = time.time() - start_time
    if index + 1 > 0:
        estimated_total_time = elapsed_time / (index + 1) * total
        remaining_time = estimated_total_time - elapsed_time
        remaining_time_str = time.strftime('%H:%M:%S', time.gmtime(remaining_time))
    else:
        remaining_time_str = "00:00:00"

    # 更新时间标签
    time_label.config(
        text=f"运行时间|剩余时间: {time.strftime('%H:%M:%S', time.gmtime(elapsed_time))}|{remaining_time_str}")

def update_runtime(start_time):
    """定期更新运行时间显示"""
    if update_time_running:
        elapsed_time = time.time() - start_time
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed_time))
        # 这里我们只更新运行时间，剩余时间保持不变
        current_text = time_label.cget("text")
        remaining_time_str = current_text.split("|")[2].strip()  # 获取剩余时间部分
        time_label.config(text=f"运行时间|剩余时间: {elapsed_str}|{remaining_time_str}")
        root.after(1000, update_runtime, start_time)  # 每秒更新一次

def cleanup_temp_files(temp_files):
    """清理临时文件"""
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                messagebox.showerror("错误", f"Error deleting temporary file {temp_file}: {e}")

@check_using_api
def generate_audio_files(sentences, output_dir):
    if client is None:
        tk.messagebox.showerror("Error", "Not connected to Gradio server.")
        return
    print("Generating audio files...")

    # 重置进度条和百分比标签
    progress_bar["value"] = 0
    percentage_label.config(text="进度: 0%")
    time_label.config(text="运行时间|剩余时间: 00:00:00|00:00:00")

    global update_time_running

    # 清理并确保路径格式正确
    output_dir = str(output_dir).strip()

    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except Exception as e:
            messagebox.showerror("错误", f"创建目录失败: {e}")
            return

    filename_prefix = str(filename_prefix_entry.get()).strip()  # 获取文件名前缀

    # 更新进度条的最大值
    progress_bar["maximum"] = len(sentences)
    progress_bar["value"] = 0
    root.update_idletasks()

    start_time = time.time()

    update_time_running = True  # 开始计时
    update_runtime(start_time)  # 启动定时更新运行时间

    temp_files = []  # 存储临时文件路径

    try:
        sovits_model = sovits_var.get()
        gpt_model = gpt_var.get()

        # Submit the selected SoVITS model to the API
        sovits_result = client.predict(
            sovits_path=sovits_model,
            api_name="/change_sovits_weights"
        )

        # Submit the selected GPT model to the API
        gpt_result = client.predict(
            gpt_path=gpt_model,
            api_name="/change_gpt_weights"
        )

        print(f"执行的模型 {sovits_model}, {gpt_model}")

    except Exception as e:
        # 停止更新运行时间
        update_time_running = False
        messagebox.showerror("错误", f"请选择有效模型{str(e)}")
        return

    for idx, sentence in enumerate(sentences):

        try:
            # 调用Gradio API生成音频
            result = client.predict(
                ref_wav_path=handle_file(str(ref_wav_path_entry.get()).strip()),  # 参考音频路径
                prompt_text=str(prompt_text_entry.get()).strip(),  # 提示文本
                prompt_language=str(prompt_language_var.get()).strip(),  # 参考音频语言
                text=sentence,  # 要合成的文本
                text_language=str(text_language_var.get()).strip(),  # 合成文本语言
                how_to_cut=str(cut_method_var.get()).strip(),  # 切割方式
                top_k=int(top_k_var.get().strip()),  # top_k 参数（确保是整数）
                top_p=float(top_p_var.get().strip()),  # top_p 参数
                temperature=float(temperature_var.get().strip()),  # 温度参数
                ref_free=ref_free_var.get(),  # 是否开启无参考模式
                speed=float(speed_var.get().strip()),  # 语速
                if_freeze=if_freeze_var.get(),  # 是否冻结设置
                inp_refs=[],  # 参考音频文件（此处可留空或添加更多参考音频）
                api_name="/get_tts_wav"
            )

            # 处理返回的结果
            audio_file_path = result[0] if isinstance(result, tuple) and len(result) > 0 else result

            if os.path.exists(audio_file_path):
                dest_path = os.path.join(output_dir, f"{filename_prefix} {idx + 1}.wav")
                try:
                    shutil.move(audio_file_path, dest_path)
                except Exception as e:
                    # 停止更新运行时间
                    update_time_running = False
                    messagebox.showerror("错误", f"Error copying file {audio_file_path} to {dest_path}: {e}")
            else:
                # 停止更新运行时间
                update_time_running = False
                messagebox.showerror("错误", f"Invalid file path: {audio_file_path}")

            # 添加临时文件到列表中
            temp_files.append(audio_file_path)

            # 更新进度条和标签
            update_progress_bar(idx, len(sentences), start_time)

        except Exception as e:
            # 停止更新运行时间
            update_time_running = False
            messagebox.showerror("错误", f"生成音频时出错: {e}")
            return

    # 停止更新运行时间
    update_time_running = False

    # 显示运行时间的弹窗
    elapsed_time = time.time() - start_time
    elapsed_time_str = time.strftime('%H:%M:%S', time.gmtime(elapsed_time))
    messagebox.showinfo("完成", f"所有音频文件已生成并保存。\n运行时间: {elapsed_time_str}")

    # 清零运行时间显示
    #elapsed_label.config(text="运行时间: 00:00:00")

    # 清理临时文件
    cleanup_temp_files(temp_files)

# 浏览文件函数
def browse_file(entry):
    file_path = filedialog.askopenfilename(filetypes=[("WAV files", "*.wav")])
    if file_path:
        entry.delete(0, tk.END)
        entry.insert(0, file_path)
        # 调用 update_text 函数，传入选定的文件路径
        update_text(file_path, prompt_text_entry, prompt_language_var, text_language_var)

def update_text(audio_file, prompt_text_entry, prompt_language_var, text_language_var):
    filename = os.path.basename(audio_file)

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
            prompt_language_var.set("日英混合")
            text_language_var.set("日英混合")
        elif has_japanese:
            prompt_language_var.set("日文")
            text_language_var.set("日文")
        elif has_chinese and has_english:
            prompt_language_var.set("中英混合")
            text_language_var.set("中英混合")
        elif has_chinese:
            prompt_language_var.set("中文")
            text_language_var.set("中文")
        elif has_english:
            prompt_language_var.set("英文")
            text_language_var.set("英文")
        else:
            prompt_language_var.set("未知")
            text_language_var.set("未知")

        # 设置提示文本
        prompt_text_entry.delete(0, tk.END)  # 清空输入框
        prompt_text_entry.insert(0, cleaned_text)  # 填充提示文本


def browse_directory(entry_widget):
    """浏览目录并设置路径"""
    directory = filedialog.askdirectory()
    if directory:  # 仅在用户选择了目录后更新路径框
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, directory)

def on_generate_button_click():
    """处理生成音频按钮点击事件"""
    sentences = split_text(str(text_entry.get("1.0", tk.END)).strip(), str(delimiter_entry.get()).strip())
    output_dir = str(output_dir_entry.get()).strip()

    # 创建新线程来生成音频文件
    threading.Thread(target=generate_audio_files, args=(sentences, output_dir)).start()


class ChapterSplitterApp:
    def __init__(self, root):
        self.root = root

        self.filename = None
        self.chapter_patterns = [
            r'第一章', r'第1章', r'第01章', r'第001章',
            r'第一话', r'第1话', r'第01话', r'第001话'
        ]

        # 路径框
        self.path_label = tk.Label(right_frame2, text="要分章的文档:")
        self.path_label.grid(row=0, column=0, padx=5, pady=1, sticky='w')

        self.path_entry = tk.Entry(right_frame2, width=50)
        self.path_entry.grid(row=1, column=0, padx=5, pady=1)

        # 浏览按钮
        self.browse_button = tk.Button(right_frame2, text="浏览...", command=self.import_file)
        self.browse_button.grid(row=1, column=1, padx=5, pady=1)

        # 标签
        self.label = tk.Label(right_frame2, text="几章一切:")
        self.label.grid(row=2, column=0, padx=5, pady=1, sticky='w')

        # 输入框
        self.entry = tk.Entry(right_frame2, width=50)
        self.entry.grid(row=3, column=0, padx=5, pady=5)

        # 开始分割按钮
        self.split_button = tk.Button(right_frame2, text="自动分章", command=self.run_split_chapters)
        self.split_button.grid(row=4, column=0, padx=5, pady=1, sticky='w')

    def import_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if filename:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, filename)

    def run_split_chapters(self):
        thread = threading.Thread(target=self.split_chapters)
        thread.start()

    def split_chapters(self):
        filepath = self.path_entry.get()
        if not filepath:
            messagebox.showwarning("警告", "请先导入文件")
            return

        try:
            content = self.read_file(filepath)

            best_chunks = None
            best_pattern = None
            max_chapters = 0

            # 遍历所有章节标号模式
            for pattern in self.chapter_patterns:
                split_function = self.get_split_function(pattern)
                if split_function:
                    preface, chapters = split_function(content)
                    if len(chapters) > max_chapters:
                        max_chapters = len(chapters)
                        best_chunks = (preface, chapters)
                        best_pattern = pattern

            if best_chunks:
                split_count = int(self.entry.get())
                if split_count < 1:
                    raise ValueError("分割整数必须大于0")

                self.write_files(filepath, best_chunks, split_count)
                messagebox.showinfo("成功", f"使用章节模式 '{best_pattern}'，文件已分割并保存")
            else:
                raise ValueError("未找到任何章节")

        except Exception as e:
            messagebox.showerror("错误", str(e))


    def read_file(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.readlines()
        return content

    def get_split_function(self, pattern):
        """根据检测到的章节标号模式返回对应的分割函数"""
        if pattern == r'第一章':
            return self.split_by_chinese_chapter
        elif pattern == r'第1章':
            return self.split_by_arabic_chapter
        elif pattern == r'第01章':
            return self.split_by_two_digit_chapter
        elif pattern == r'第001章':
            return self.split_by_three_digit_chapter
        elif pattern == r'第一话':
            return self.split_by_chinese_episode
        elif pattern == r'第1话':
            return self.split_by_arabic_episode
        elif pattern == r'第01话':
            return self.split_by_two_digit_episode
        elif pattern == r'第001话':
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

        hundreds = num // 100        # 百位
        tens = (num % 100) // 10     # 十位
        ones = num % 10              # 个位

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

    def write_files(self, filepath, chunks, split_count):
        """根据提取的章节标号进行文件命名"""
        preface, chapters = chunks

        if not chapters:
            raise ValueError("未找到任何章节")

        base_filename = filepath.rsplit('.', 1)[0]

        if preface:
            self.write_file(f"{base_filename} 序章.txt", preface)

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
                batch_name = f"{base_filename} {chapter_labels[0]}至{chapter_labels[-1]}.txt"
            else:
                batch_name = f"{base_filename} {chapter_labels[0]}.txt"

            self.write_file(batch_name, batch_content)

    def write_file(self, filename, content):
        """写入文件"""
        with open(filename, 'w', encoding='utf-8') as file:
            file.writelines(content)


class AnnotationApp:
    def __init__(self, root):
        self.root = root

        # 创建界面元素
        self.create_widgets()

    def create_widgets(self):
        # 分割符
        self.part1 = tk.Label(right_frame2, text="————————————————————————————————")
        self.part1.grid(row=5, column=0, padx=1, columnspan=2)

        # 未标注文本路径
        tk.Label(right_frame2, text="未标注角色名文本路径:").grid(row=6, column=0, padx=5, pady=1, sticky='w')
        self.uncategorized_path_entry = tk.Entry(right_frame2, width=50)
        self.uncategorized_path_entry.grid(row=7, column=0, padx=5, pady=1)
        tk.Button(right_frame2, text="浏览...", command=self.load_uncategorized_file).grid(row=7, column=1, padx=5,)

        # 对话文本路径
        tk.Label(right_frame2, text="对话标注角色名文本路径:").grid(row=8, column=0, padx=5, pady=1, sticky='w')
        self.dialog_path_entry = tk.Entry(right_frame2, width=50)
        self.dialog_path_entry.grid(row=9, column=0, padx=5, pady=1)
        tk.Button(right_frame2, text="浏览...", command=self.load_dialog_file).grid(row=9, column=1, padx=10, pady=1)

        # 开始标注按钮
        tk.Button(right_frame2, text="开始标注", command=self.annotate_texts).grid(row=10, column=0, padx=5, sticky='w')

    def load_dialog_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file_path:
            self.dialog_path_entry.delete(0, tk.END)
            self.dialog_path_entry.insert(0, file_path)

    def load_uncategorized_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file_path:
            self.uncategorized_path_entry.delete(0, tk.END)
            self.uncategorized_path_entry.insert(0, file_path)

    def annotate_texts(self):
        dialog_file = self.dialog_path_entry.get()
        uncategorized_file = self.uncategorized_path_entry.get()

        if not dialog_file or not uncategorized_file:
            messagebox.showerror("错误", "请确保选择了对话文本和未标注文本文件。")
            return

        try:
            # 读取对话文本内容
            with open(dialog_file, 'r', encoding='utf-8') as f:
                dialog_lines = f.readlines()

            # 提取对话文本中的标注内容和前缀
            annotations = {}
            for line in dialog_lines:
                match = re.search(r'^(.*?)「(.*?)」', line)
                if match:
                    prefix, annotation = match.groups()
                    annotations[annotation.strip()] = prefix.strip()

            # 读取未标注文本内容
            with open(uncategorized_file, 'r', encoding='utf-8') as f:
                uncategorized_lines = f.readlines()

            # 处理未标注文本
            new_lines = []
            added_annotations = set()  # 跟踪已添加的注释

            for line in uncategorized_lines:
                line = line.rstrip()  # 去除每行末尾的空白字符
                new_line = ''
                pos = 0

                # 查找未标注文本中的「」符号括起来的内容
                for match in re.finditer(r'(.*?)「(.*?)」', line):
                    before, content = match.groups()
                    new_line += line[pos:match.start()]  # 添加之前的内容
                    if content in annotations and content not in added_annotations:
                        new_line += f"{annotations[content]}「{content}」"
                        added_annotations.add(content)  # 标记为已添加
                    else:
                        new_line += f"「{content}」"
                    pos = match.end()

                # 添加最后一部分内容
                new_line += line[pos:]
                new_lines.append(new_line)

            # 构建新文件名
            base, ext = os.path.splitext(uncategorized_file)
            new_file = f"{base} marked{ext}"

            # 保存新的未标注文本内容
            with open(new_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(new_lines))

            messagebox.showinfo("成功", f"标注完成，已保存到新文件: {new_file}")

        except Exception as e:
            messagebox.showerror("错误", f"处理文件时发生错误: {e}")


class FileMergerApp:
    def __init__(self, root):
        self.root = root
        self.create_widgets()

    def create_widgets(self):
        self.part2 = tk.Label(right_frame2, text="————————————————————————————————")
        self.part2.grid(row=11, column=0, padx=1, columnspan=2)
        tk.Label(right_frame2, text="要合并的章节所在文件夹:").grid(row=12, column=0, padx=5, pady=1, sticky="w")
        self.folder_path_entry = tk.Entry(right_frame2, width=50)
        self.folder_path_entry.grid(row=13, column=0, padx=5, pady=1, sticky="w")
        tk.Button(right_frame2, text="浏览...", command=self.load_folder).grid(row=13, column=1, padx=5, pady=1)
        tk.Button(right_frame2, text="合并文档", command=self.merge_files).grid(row=14, column=0, padx=5, sticky="w")

    def load_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.folder_path_entry.delete(0, tk.END)
            self.folder_path_entry.insert(0, folder_path)

    def merge_files(self):
        folder_path = self.folder_path_entry.get()
        if not folder_path:
            messagebox.showerror("错误", "请确保选择了文件夹。")
            return

        try:
            # 获取文件夹内所有.txt文件
            txt_files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]

            # 提取数字并排序文件名
            def extract_number(file_name):
                match = re.search(r'第(\d+)(章|话)', file_name)
                return int(match.group(1)) if match else float('inf')  # 返回一个较大的数以便排在最后

            txt_files.sort(key=extract_number)

            if not txt_files:
                messagebox.showinfo("信息", "该文件夹中没有.txt文件。")
                return

            # 合成文件路径
            merged_file_path = os.path.join(folder_path, 'merged_file.txt')
            with open(merged_file_path, 'w', encoding='utf-8') as merged_file:
                for file_name in txt_files:
                    file_path = os.path.join(folder_path, file_name)
                    with open(file_path, 'r', encoding='utf-8') as file:
                        merged_file.write(file.read())
                        merged_file.write("\n")  # 添加换行符分隔不同文件

            messagebox.showinfo("成功", f"文件已成功合成，保存到: {merged_file_path}")

        except Exception as e:
            messagebox.showerror("错误", f"处理文件时发生错误: {e}")


class DocumentProcessorApp:
    def __init__(self, root):
        self.root = root
        if isinstance(self.root, tk.Tk):
            self.root.title("Document Processor")

        self.part3 = tk.Label(right_frame2, text="————————————————————————————————")
        self.part3.grid(row=15, column=0, padx=1, columnspan=2)
        self.input_label = tk.Label(right_frame2, text="导入完成AI标记的文档:")
        self.input_label.grid(row=16, column=0, padx=5, pady=1, sticky="w")
        self.input_path = tk.Entry(right_frame2, width=50)
        self.input_path.grid(row=17, column=0, padx=5, pady=1, sticky="w")
        self.input_button = tk.Button(right_frame2, text="浏览...", command=self.select_input_file)
        self.input_button.grid(row=17, column=1, padx=5, pady=1)

        self.output_label = tk.Label(right_frame2, text="输出各角色文本及顺序表:")
        self.output_label.grid(row=18, column=0, padx=5, pady=1, sticky="w")
        self.output_path = tk.Entry(right_frame2, width=50)
        self.output_path.grid(row=19, column=0, padx=5, pady=1, sticky="w")
        self.output_button = tk.Button(right_frame2, text="浏览...", command=self.select_output_directory)
        self.output_button.grid(row=19, column=1, padx=5, pady=1)

        self.symbol_label = tk.Label(right_frame2, text="分句符号(确保文本中不存在该符号):")
        self.symbol_label.grid(row=20, column=0, padx=5, pady=1, sticky="w")
        self.symbol_entry = tk.Entry(right_frame2, width=50)
        self.symbol_entry.grid(row=21, column=0, padx=5, pady=1, sticky="w")

        # 添加复选框来切换处理逻辑
        self.use_custom_logic = tk.BooleanVar(value=True)
        self.custom_logic_checkbox = tk.Checkbutton(right_frame2, text="不在同一段内添加分句符(生成更快)", variable=self.use_custom_logic)
        self.custom_logic_checkbox.grid(row=22, column=0, padx=5, sticky="w")

        self.process_button = tk.Button(right_frame2, text="生成各角色文本和顺序表", command=self.process_document)
        self.process_button.grid(row=23, column=0, padx=5, sticky="w")

    def select_input_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if file_path:
            self.input_path.delete(0, tk.END)
            self.input_path.insert(0, file_path)

    def select_output_directory(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_path.delete(0, tk.END)
            self.output_path.insert(0, dir_path)

    def process_document(self):
        input_file = self.input_path.get()
        output_dir = self.output_path.get()
        custom_symbol = self.symbol_entry.get().strip()

        if not input_file or not output_dir:
            messagebox.showerror("Error", "Please specify both input file and output directory.")
            return

        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()

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
            use_custom_logic = self.use_custom_logic.get()

            # First create the order table
            for i, block in enumerate(blocks):
                block = block.strip()
                if '@:「' in block:
                    tag = block.split('@:「')[0].strip()
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
                if '@:「' in block:
                    tag = block.split('@:「')[0].strip()
                    cleaned_lines = [line.split('@:「')[1].strip() for line in block.split('\n') if '@:「' in line]
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

            # Display success message with list of created files
            messagebox.showinfo("Success",
                                f"Order table saved to {order_table_path}\nCategorized files created:\n" + "\n".join(
                                    categorized_files))

        except Exception as e:
            messagebox.showerror("Error", str(e))



class VoiceGeneratorApp:
    def __init__(self, root, folder_path_var):
        # 初始化Gradio客户端
        self.client = None

        self.root = root
        self.folder_path_config = folder_path_var

        self.sovits_model_list = []  # 存储SoVITS模型列表
        self.gpt_model_list = []  # 存储GPT模型列表
        self.row_variables = {}
        self.voice_threads = []  # 用于存储生成语音的线程

        # 顶部路径框和浏览按钮容器
        self.path_frame = tk.Frame(self.root)
        self.path_frame.pack(pady=10)

        # 新增 "导入配置" 按钮
        self.import_button = tk.Button(self.path_frame, text="导入配置", command=self.import_all_configs)
        self.import_button.pack(side=tk.LEFT, padx=5)

        # 新增 "导出配置" 按钮
        self.export_button = tk.Button(self.path_frame, text="导出配置", command=self.export_all_configs)
        self.export_button.pack(side=tk.LEFT, padx=5)

        self.path_label = tk.Label(self.path_frame, text="选择文件夹:")
        self.path_label.pack(side=tk.LEFT)

        # 文件夹路径输入框
        self.folder_path_var = tk.StringVar()
        self.folder_entry = tk.Entry(self.path_frame, textvariable=self.folder_path_var, width=50)
        self.folder_entry.pack(side=tk.LEFT, padx=5)

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
        self.header_canvas = tk.Canvas(self.main_frame, bg="white", height=30, highlightthickness=0)
        self.header_frame = tk.Frame(self.header_canvas)

        # 创建列表画布
        self.list_canvas = tk.Canvas(self.main_frame, bg="white", highlightthickness=0)
        self.scroll_frame = tk.Frame(self.list_canvas)

        # 创建滚动条
        self.horizontal_scrollbar = tk.Scrollbar(self.main_frame, orient="horizontal",
                                                  command=self.sync_scroll_horizontal)
        self.vertical_scrollbar = tk.Scrollbar(self.main_frame, orient="vertical", command=self.list_canvas.yview)

        # 绑定配置变化
        self.scroll_frame.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.header_frame.bind("<Configure>", lambda e: self.header_canvas.configure(scrollregion=self.header_canvas.bbox("all")))

        # 将滚动区域添加到画布中
        self.header_window = self.header_canvas.create_window((0, 0), window=self.header_frame, anchor="nw")
        self.list_window = self.list_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        # 布局
        self.header_canvas.grid(row=0, column=0, sticky="ew")
        self.list_canvas.grid(row=1, column=0, sticky="nsew")
        self.horizontal_scrollbar.grid(row=2, column=0, sticky="ew")
        self.vertical_scrollbar.grid(row=1, column=1, sticky="ns")

        # 配置滚动条
        self.list_canvas.configure(xscrollcommand=self.horizontal_scrollbar.set, yscrollcommand=self.vertical_scrollbar.set)

        # 创建表头和内容
        self.create_header(self.header_frame)

        # 设置主框架的权重以支持动态调整
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

        # 在最底部添加frame和"生成完整语音"按钮
        self.bottom_frame = tk.Frame(self.root)
        self.bottom_frame.pack(fill=tk.X, pady=10)

        self.merge_button = tk.Button(self.bottom_frame, text="合并语音", command=self.merge_audio_files)
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

    def set_client(self, client):
        self.client = client
        #print("Client set in VoiceGeneratorApp.")

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
                # 调用 export_character_config 方法导出当前行的配置
                config_path = self.export_character_config(
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
                # 创建线程并运行 generate_character_voice，传入对应的变量
                thread = threading.Thread(target=self.generate_character_voice,
                                          args=(row_vars['sovits'], row_vars['gpt'], row_vars['ref_wav_path'],
                                                row_vars['prompt'], row_vars['ref_language'], row_vars['text_language'],
                                                row_vars['cut_method'], row_vars['top_k'], row_vars['top_p'],
                                                row_vars['temperature'], row_vars['speed'], row_vars['ref_free'],
                                                row_vars['if_freeze'], row_vars['delimiter'], idx, failed_rows))
                thread.start()  # 启动线程
                thread.join()  # 等待当前线程完成，确保按顺序执行
                self.voice_threads.append(thread)  # 将线程保存到列表

            except Exception as e:
                print(f"生成第 {idx} 行语音时出错: {e}")

        # 合并音频，传入出错的行名
        self.merge_audio_files(failed_rows)

    def merge_audio_files(self, failed_rows):
        folder_path = self.folder_path_var.get()
        order_file_path = os.path.join(folder_path, "顺序表.txt")
        input_folder = os.path.join(folder_path, "AudioCache")
        output_folder = folder_path

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

    def export_character_config(self, folder_path, selected_option, top_k, top_p, temperature, speed, ref_free,
                                if_freeze, sovits, gpt, ref_wav_path, prompt, ref_language, text_language, cut_method,
                                delimiter, show_message=True):

        # 获取主文件夹路径
        main_folder_path = self.folder_path_config.get()

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
            ("角色名", 18), ("配置角色", 17), ("选择配置", 41), ("SoVITS模型", 21),("GPT模型", 39),
            ("参考音频路径", 52), ("提示文本", 30), ("参考语言", 20),("生成语言", 16), ("top_k", 5), ("top_p", 5), ("温度", 4),
            ("语速", 3), ("无参考模式", 8), ("冻结设置", 12),("分句内切割方式", 16), ("分句符", 6)
        ]

        for col, (header, width) in enumerate(headers):
            tk.Label(header_frame, text=header, anchor='w', width=width).grid(row=0, column=col, padx=5, pady=5, sticky="w")

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

            # 创建角色下拉框 combo_box_charactor
            charactor_var = tk.StringVar(value="当前角色")
            combo_box_charactor = ttk.Combobox(self.scroll_frame, textvariable=charactor_var, width=option_width)
            combo_box_charactor.grid(row=idx, column=start_col, padx=column_padding, pady=row_padding,
                                     sticky="w")

            # 绑定选择事件到新函数
            combo_box_charactor.bind("<<ComboboxSelected>>",
                                     lambda e, index=idx, char_var=charactor_var: self.on_charactor_selected(index,
                                                                                                             char_var))

            # 加载文件夹选项
            self.update_charactor_options(combo_box_charactor)

            # 添加下拉框 combo_box_config
            # 默认包含当前行的 label_name 以及“新建配置”
            config_file_var = tk.StringVar(value=txt_files[idx])  # 自动填充为 label_name
            combo_box_config = ttk.Combobox(self.scroll_frame, textvariable=config_file_var, width=option_width)

            # 添加下拉框中的选项
            combo_box_config['values'] = [txt_files[idx], "新建配置"]
            combo_box_config.grid(row=idx, column=start_col + 1, padx=column_padding, pady=row_padding, sticky="w")

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
                apply_default_button.grid(row=idx, column=start_col + 3, padx=column_padding, pady=row_padding)
                apply_default_button.bind("<MouseWheel>", self.scroll_canvas)

            else:
                # 当 folder 不是 "默认" 时，添加“生成角色语言”按钮
                generate_language_button = tk.Button(self.scroll_frame, text="生成角色语音",
                                                     command=lambda index=idx: self.run_generate_character_voice(index))
                generate_language_button.grid(row=idx, column=start_col + 3, padx=column_padding, pady=row_padding)
                generate_language_button.bind("<MouseWheel>", self.scroll_canvas)

            # 单独创建并绑定 Entry 和 Checkbutton 控件
            top_k_var = tk.StringVar(value="15")
            top_k_entry = tk.Entry(self.scroll_frame, textvariable=top_k_var, width=entry_width)
            top_k_entry.grid(row=idx, column=start_col + 12, padx=column_padding, pady=row_padding, sticky="w")
            top_k_entry.bind("<MouseWheel>", self.scroll_canvas)

            top_p_var = tk.StringVar(value="1")
            top_p_entry = tk.Entry(self.scroll_frame, textvariable=top_p_var, width=entry_width)
            top_p_entry.grid(row=idx, column=start_col + 13, padx=column_padding, pady=row_padding, sticky="w")
            top_p_entry.bind("<MouseWheel>", self.scroll_canvas)

            temperature_var = tk.StringVar(value="1")
            temperature_entry = tk.Entry(self.scroll_frame, textvariable=temperature_var, width=entry_width)
            temperature_entry.grid(row=idx, column=start_col + 14, padx=column_padding, pady=row_padding, sticky="w")
            temperature_entry.bind("<MouseWheel>", self.scroll_canvas)

            speed_var = tk.StringVar(value="1")
            speed_entry = tk.Entry(self.scroll_frame, textvariable=speed_var, width=entry_width)
            speed_entry.grid(row=idx, column=start_col + 15, padx=column_padding, pady=row_padding, sticky="w")
            speed_entry.bind("<MouseWheel>", self.scroll_canvas)

            ref_free_var = tk.BooleanVar()
            ref_free_check = tk.Checkbutton(self.scroll_frame, variable=ref_free_var, width=check_width)
            ref_free_check.grid(row=idx, column=start_col + 16, padx=column_padding, pady=row_padding, sticky="w")
            ref_free_check.bind("<MouseWheel>", self.scroll_canvas)

            if_freeze_var = tk.BooleanVar()
            if_freeze_check = tk.Checkbutton(self.scroll_frame, variable=if_freeze_var, width=check_width)
            if_freeze_check.grid(row=idx, column=start_col + 17, padx=column_padding + 15, pady=row_padding, sticky="w")
            if_freeze_check.bind("<MouseWheel>", self.scroll_canvas)

            sovits_var = tk.StringVar(value="请选择")
            sovits_menu = tk.OptionMenu(self.scroll_frame, sovits_var, "请先刷新模型")
            sovits_menu.config(width=option_width)
            sovits_menu.grid(row=idx, column=start_col + 4, padx=column_padding, pady=row_padding, sticky="w")
            sovits_menu.bind("<MouseWheel>", self.scroll_canvas)

            gpt_var = tk.StringVar(value="请选择")
            gpt_menu = tk.OptionMenu(self.scroll_frame, gpt_var, "请先刷新模型")
            gpt_menu.config(width=option_width)
            gpt_menu.grid(row=idx, column=start_col + 5, padx=column_padding, pady=row_padding, sticky="w")
            gpt_menu.bind("<MouseWheel>", self.scroll_canvas)

            # 刷新模型
            refresh_button = tk.Button(self.scroll_frame, text="刷新单项模型",
                                       command=lambda sm=sovits_menu, gm=gpt_menu, sv=sovits_var,
                                                      gv=gpt_var: self.run_update_model_choices(sm, gm, sv, gv))
            #refresh_button.grid(row=idx, column=start_col + 11, padx=column_padding, pady=row_padding, sticky="w")

            ref_language_var = tk.StringVar(value="请选择")
            ref_language_menu = tk.OptionMenu(self.scroll_frame, ref_language_var, "请先确认模型")
            ref_language_menu.config(width=option_width)
            ref_language_menu.grid(row=idx, column=start_col + 10, padx=column_padding, pady=row_padding, sticky="w")
            ref_language_menu.bind("<MouseWheel>", self.scroll_canvas)

            text_language_var = tk.StringVar(value="请选择")
            text_language_menu = tk.OptionMenu(self.scroll_frame, text_language_var, "请先确认模型")
            text_language_menu.config(width=option_width)
            text_language_menu.grid(row=idx, column=start_col + 11, padx=column_padding, pady=row_padding, sticky="w")
            text_language_menu.bind("<MouseWheel>", self.scroll_canvas)

            confirm_button = tk.Button(self.scroll_frame, text="确认模型",
                                       command=lambda sv=sovits_var, gv=gpt_var, rlv=ref_language_var,
                                                      tlv=text_language_var, frm=self.scroll_frame,
                                                      sc=start_col, lin=idx: self.run_confirm_gpt_model(sv, gv, rlv,
                                                                                                        tlv, frm,
                                                                                                        sc, lin))
            confirm_button.grid(row=idx, column=start_col + 6, padx=column_padding, pady=row_padding, sticky="w")
            confirm_button.bind("<MouseWheel>", self.scroll_canvas)

            cut_method_var = tk.StringVar(value="凑四句一切")
            cut_method_menu = tk.OptionMenu(self.scroll_frame, cut_method_var, "不切", "凑四句一切", "凑50字一切",
                                            "按中文句号。切",
                                            "按英文句号.切", "按标点符号切")
            cut_method_menu.config(width=option_width)
            cut_method_menu.grid(row=idx, column=start_col + 18, padx=column_padding, pady=row_padding, sticky="w")
            cut_method_menu.bind("<MouseWheel>", self.scroll_canvas)

            # 分隔符 Entry (绑定滚动事件)
            delimiter_entry = tk.StringVar(value="|")
            delimiter_entry_field = tk.Entry(self.scroll_frame, textvariable=delimiter_entry, width=entry_width)
            delimiter_entry_field.grid(row=idx, column=start_col + 19, padx=column_padding, pady=row_padding,
                                       sticky="w")
            delimiter_entry_field.bind("<MouseWheel>", self.scroll_canvas)

            # 选择参考音频
            combo_box = ttk.Combobox(self.scroll_frame, textvariable=ref_wav_path_entry, width=long_entry_width)
            combo_box['values'] = audio_files
            combo_box.grid(row=idx, column=start_col + 7, padx=column_padding, pady=row_padding, sticky="w")

            # 添加“浏览...”按钮
            browse_button = tk.Button(self.scroll_frame, text="浏览...",
                                      command=lambda var=ref_wav_path_entry, combo=combo_box: self.browse_wav_file(var,
                                                                                                                   combo,
                                                                                                                   idx))
            browse_button.grid(row=idx, column=start_col + 8, padx=column_padding, pady=row_padding, sticky="w")
            browse_button.bind("<MouseWheel>", self.scroll_canvas)

            # 禁止在下拉框上使用滚轮
            # combo_box.bind("<MouseWheel>", lambda e: "break")

            result_entry = tk.Entry(self.scroll_frame, textvariable=prompt_var, width=long_entry_width)
            result_entry.grid(row=idx, column=start_col + 9, padx=column_padding, pady=row_padding, sticky="w")
            result_entry.bind("<MouseWheel>", self.scroll_canvas)

            combo_box.bind("<<ComboboxSelected>>",
                           lambda e, var=ref_wav_path_entry, result=prompt_var,
                                  ref_lang1=ref_language_var, ref_lang2=text_language_var: self.update_text(
                               var.get(), result, ref_lang1, ref_lang2))

            #if audio_files:

            #else:
                #label_no_audio = tk.Label(self.scroll_frame, text="No .wav files", fg="gray")
                #label_no_audio.grid(row=idx, column=start_col + 12, padx=column_padding, pady=row_padding, sticky="w")

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
                                                     delimiter=delimiter_entry:
                                      self.export_character_config(char_var.get(), so.get(), top_k, top_p, temperature,
                                                                   speed,
                                                                   ref_free, if_freeze, sovits, gpt,
                                                                   ref_wav_path, prompt, ref_language, text_language,
                                                                   cut_method, delimiter))

            export_button.grid(row=idx, column=start_col + 2, padx=5, pady=5, sticky="w")
            export_button.bind("<MouseWheel>", self.scroll_canvas)

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
            }

        # 添加滚动功能
        self.scroll_frame.bind("<MouseWheel>", lambda e: self.scroll_canvas(e))

    def apply_default_values(self):
        # 找到“默认”行的变量
        default_row_idx = 0  # 默认行的索引为 0
        default_values = self.row_variables[default_row_idx]

        # 添加调试信息，查看default_values的内容
        #print(f"Default values: {default_values}")

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
            #print(f"KeyError: {e} - 检查行 {default_row_idx} 中是否包含所有需要的控件")
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

        #print("已应用默认值到其他所有行")

    def on_charactor_selected(self, idx, char_var):
        """处理角色选择事件，更新配置文件和音频文件"""
        selected_charactor = char_var.get()
        self.update_json_options(idx, selected_charactor)  # 更新 json 配置文件下拉框
        self.update_audio_files(idx, selected_charactor)  # 更新音频文件下拉框

    def update_charactor_options(self, combo_box_charactor):
        """更新角色下拉框选项"""
        folder_path = self.folder_path_config.get()
        #print(folder_path)
        if os.path.exists(folder_path):
            folders = [name for name in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, name))]
            combo_box_charactor['values'] = folders + ["当前角色"]
        else:
            combo_box_charactor['values'] = ["当前角色"]

    def update_json_options(self, idx, selected_folder):
        """更新 JSON 文件下拉框选项"""
        if selected_folder != "当前角色":
            # 处理非“当前角色”的情况
            folder_path = self.folder_path_config.get()
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

    def update_audio_files(self, idx, selected_folder):
        """更新参考音频下拉框选项"""
        folder_path = os.path.join(self.folder_path_config.get(), selected_folder)  # 获取文件夹路径
        audio_files = self.get_audio_files(folder_path)  # 获取 .wav 文件列表

        combo_box = self.row_variables[idx]['combo_box_ref_wav_path']  # 获取对应行的 combo_box
        combo_box['values'] = audio_files  # 更新下拉框的值

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

        #label_name = self.row_variables[idx]['label_name'].cget("text")

        #print(label_name)

        # 检查是否选择了当前行的 label_name
        if selected_file == self.row_variables[idx]['label_name'].cget("text"):
            #print(selected_file)
            main_folder_path = self.folder_path_var.get()
            #print(main_folder_path)
            config_file_path = os.path.join(main_folder_path, f"{selected_file}.json")
            #print(config_file_path)

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
        main_folder_path = self.folder_path_config.get()
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
        if self.client is None:
            tk.messagebox.showerror("Error", "Not connected to Gradio server.")
            return

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

        # 创建线程并运行 generate_character_voice，传入对应的变量
        thread = threading.Thread(target=self.generate_character_voice,
                                  args=(row_vars['sovits'], row_vars['gpt'], row_vars['ref_wav_path'],
                                        row_vars['prompt'], row_vars['ref_language'], row_vars['text_language'],
                                        row_vars['cut_method'], row_vars['top_k'], row_vars['top_p'],
                                        row_vars['temperature'], row_vars['speed'], row_vars['ref_free'],
                                        row_vars['if_freeze'], row_vars['delimiter'], idx))
        self.voice_threads.append(thread)  # 将线程保存到列表
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
            ref_language_menu = frame.grid_slaves(row=row, column=start_col + 10)[0]
            text_language_menu = frame.grid_slaves(row=row, column=start_col + 11)[0]

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
                                 speed_var, ref_free_var, if_freeze_var, delimiter_var, idx, failed_rows):
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
        if event.delta > 0:
            self.list_canvas.yview_scroll(-1, "units")  # 向上滚动
        else:
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

        # 顶部路径框和浏览按钮容器
        self.path_frame = tk.Frame(self.root)
        self.path_frame.pack(pady=10)

        self.blank_space = tk.Frame(self.path_frame, width=138)
        self.blank_space.pack(side=tk.LEFT)

        self.path_label = tk.Label(self.path_frame, text="选择文件夹:")
        self.path_label.pack(side=tk.LEFT)

        # 文件夹路径输入框
        self.folder_path_var = tk.StringVar()
        self.folder_entry = tk.Entry(self.path_frame, textvariable=self.folder_path_var, width=50)
        self.folder_entry.pack(side=tk.LEFT, padx=5)

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
        self.header_canvas = tk.Canvas(self.main_frame, bg="white", height=30, highlightthickness=0)
        self.header_frame = tk.Frame(self.header_canvas)

        # 创建列表画布
        self.list_canvas = tk.Canvas(self.main_frame, bg="white", highlightthickness=0)
        self.scroll_frame = tk.Frame(self.list_canvas)

        # 创建滚动条
        self.horizontal_scrollbar = tk.Scrollbar(self.main_frame, orient="horizontal",
                                                  command=self.sync_scroll_horizontal)
        self.vertical_scrollbar = tk.Scrollbar(self.main_frame, orient="vertical", command=self.list_canvas.yview)

        # 绑定配置变化
        self.scroll_frame.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.header_frame.bind("<Configure>", lambda e: self.header_canvas.configure(scrollregion=self.header_canvas.bbox("all")))

        # 将滚动区域添加到画布中
        self.header_window = self.header_canvas.create_window((0, 0), window=self.header_frame, anchor="nw")
        self.list_window = self.list_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        # 布局
        self.header_canvas.grid(row=0, column=0, sticky="ew")
        self.list_canvas.grid(row=1, column=0, sticky="nsew")
        self.horizontal_scrollbar.grid(row=2, column=0, sticky="ew")
        self.vertical_scrollbar.grid(row=1, column=1, sticky="ns")

        # 配置滚动条
        self.list_canvas.configure(xscrollcommand=self.horizontal_scrollbar.set, yscrollcommand=self.vertical_scrollbar.set)

        # 创建表头和内容
        self.create_header(self.header_frame)

        # 设置主框架的权重以支持动态调整
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

    def set_client(self, client):
        self.client = client
        #print("Client set in FolderAudioViewer.")

    def refresh_folder_list(self):
        """ 刷新文件夹内容 """
        folder_path = self.folder_path_var.get()
        if folder_path:  # 确保路径不为空
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
        print(config_path,f"和",selected_option,f"B")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)

        messagebox.showinfo("成功", f"角色配置已导出到: {config_path}")

    def sync_scroll_horizontal(self, *args):
        """同步横向滚动"""
        self.header_canvas.xview(*args)
        self.list_canvas.xview(*args)

    def create_header(self, header_frame):
        headers = [
            ("    头像",12), ("角色名", 13), ("配置名称", 27), ("SoVITS模型", 21), ("GPT模型", 39), ("参考音频路径", 52), ("提示文本", 30),
            ("参考语言", 20), ("生成语言", 16),("top_k", 5), ("top_p", 5), ("温度", 4), ("语速", 3), ("无参考模式", 8), ("冻结设置", 12),
            ("分句内切割方式", 16), ("分句符", 6)
        ]

        for col, (header, width) in enumerate(headers):
            tk.Label(header_frame, text=header, anchor='w', width=width).grid(row=0, column=col, padx=5, pady=5, sticky="w")

    def get_subfolders(self, main_folder):
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

            top_p_var = tk.StringVar(value="1")
            top_p_entry = tk.Entry(self.scroll_frame, textvariable=top_p_var, width=entry_width)
            top_p_entry.grid(row=idx, column=start_col + 12, padx=column_padding, pady=row_padding, sticky="w")
            top_p_entry.bind("<MouseWheel>", self.scroll_canvas)

            temperature_var = tk.StringVar(value="1")
            temperature_entry = tk.Entry(self.scroll_frame, textvariable=temperature_var, width=entry_width)
            temperature_entry.grid(row=idx, column=start_col + 13, padx=column_padding, pady=row_padding, sticky="w")
            temperature_entry.bind("<MouseWheel>", self.scroll_canvas)

            speed_var = tk.StringVar(value="1")
            speed_entry = tk.Entry(self.scroll_frame, textvariable=speed_var, width=entry_width)
            speed_entry.grid(row=idx, column=start_col + 14, padx=column_padding, pady=row_padding, sticky="w")
            speed_entry.bind("<MouseWheel>", self.scroll_canvas)

            ref_free_var = tk.BooleanVar()
            ref_free_check = tk.Checkbutton(self.scroll_frame, variable=ref_free_var, width=check_width)
            ref_free_check.grid(row=idx, column=start_col + 15, padx=column_padding, pady=row_padding, sticky="w")
            ref_free_check.bind("<MouseWheel>", self.scroll_canvas)

            if_freeze_var = tk.BooleanVar()
            if_freeze_check = tk.Checkbutton(self.scroll_frame, variable=if_freeze_var, width=check_width)
            if_freeze_check.grid(row=idx, column=start_col + 16, padx=column_padding + 15, pady=row_padding, sticky="w")
            if_freeze_check.bind("<MouseWheel>", self.scroll_canvas)

            sovits_var = tk.StringVar(value="请选择")
            sovits_menu = tk.OptionMenu(self.scroll_frame, sovits_var, "请先刷新模型")
            sovits_menu.config(width=option_width)
            sovits_menu.grid(row=idx, column=start_col + 3, padx=column_padding, pady=row_padding, sticky="w")
            sovits_menu.bind("<MouseWheel>", self.scroll_canvas)

            gpt_var = tk.StringVar(value="请选择")
            gpt_menu = tk.OptionMenu(self.scroll_frame, gpt_var, "请先刷新模型")
            gpt_menu.config(width=option_width)
            gpt_menu.grid(row=idx, column=start_col + 4, padx=column_padding, pady=row_padding, sticky="w")
            gpt_menu.bind("<MouseWheel>", self.scroll_canvas)

            # 刷新模型
            refresh_button = tk.Button(self.scroll_frame, text="刷新单项模型",
                                       command=lambda sm=sovits_menu, gm=gpt_menu, sv=sovits_var,
                                                      gv=gpt_var: self.run_update_model_choices(sm, gm, sv, gv))
            #refresh_button.grid(row=idx, column=start_col + 11, padx=column_padding, pady=row_padding, sticky="w")

            ref_language_var = tk.StringVar(value="请选择")
            ref_language_menu = tk.OptionMenu(self.scroll_frame, ref_language_var, "请先确认模型")
            ref_language_menu.config(width=option_width)
            ref_language_menu.grid(row=idx, column=start_col + 9, padx=column_padding, pady=row_padding, sticky="w")
            ref_language_menu.bind("<MouseWheel>", self.scroll_canvas)

            text_language_var = tk.StringVar(value="请选择")
            text_language_menu = tk.OptionMenu(self.scroll_frame, text_language_var, "请先确认模型")
            text_language_menu.config(width=option_width)
            text_language_menu.grid(row=idx, column=start_col + 10, padx=column_padding, pady=row_padding, sticky="w")
            text_language_menu.bind("<MouseWheel>", self.scroll_canvas)

            confirm_button = tk.Button(self.scroll_frame, text="确认模型",
                                       command=lambda sv=sovits_var, gv=gpt_var, rlv=ref_language_var,
                                                      tlv=text_language_var, frm=self.scroll_frame,
                                                      sc=start_col, lin=idx: self.run_confirm_gpt_model(sv, gv, rlv,
                                                                                                        tlv, frm,
                                                                                                        sc, lin))
            confirm_button.grid(row=idx, column=start_col + 5, padx=column_padding, pady=row_padding, sticky="w")
            confirm_button.bind("<MouseWheel>", self.scroll_canvas)

            cut_method_var = tk.StringVar(value="凑四句一切")
            cut_method_menu = tk.OptionMenu(self.scroll_frame, cut_method_var, "不切", "凑四句一切", "凑50字一切",
                                            "按中文句号。切",
                                            "按英文句号.切", "按标点符号切")
            cut_method_menu.config(width=option_width)
            cut_method_menu.grid(row=idx, column=start_col + 17, padx=column_padding, pady=row_padding, sticky="w")
            cut_method_menu.bind("<MouseWheel>", self.scroll_canvas)

            # 分隔符 Entry (绑定滚动事件)
            delimiter_entry = tk.StringVar(value="|")
            delimiter_entry_field = tk.Entry(self.scroll_frame, textvariable=delimiter_entry, width=entry_width)
            delimiter_entry_field.grid(row=idx, column=start_col + 18, padx=column_padding, pady=row_padding,
                                       sticky="w")
            delimiter_entry_field.bind("<MouseWheel>", self.scroll_canvas)

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

            # 禁止在下拉框上使用滚轮
            # combo_box.bind("<MouseWheel>", lambda e: "break")

            result_entry = tk.Entry(self.scroll_frame, textvariable=prompt_var, width=long_entry_width)
            result_entry.grid(row=idx, column=start_col + 8, padx=column_padding, pady=row_padding, sticky="w")
            result_entry.bind("<MouseWheel>", self.scroll_canvas)

            combo_box.bind("<<ComboboxSelected>>",
                           lambda e, var=ref_wav_path_entry, result=prompt_var,
                                  ref_lang1=ref_language_var, ref_lang2=text_language_var: self.update_text(
                               var.get(), result, ref_lang1, ref_lang2))

            #if audio_files:

            #else:
                #label_no_audio = tk.Label(self.scroll_frame, text="No .wav files", fg="gray")
                #label_no_audio.grid(row=idx, column=start_col + 12, padx=column_padding, pady=row_padding, sticky="w")

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
                'prompt': prompt_var,
                'ref_language': ref_language_var,
                'text_language': text_language_var,
                'cut_method': cut_method_var,
                'delimiter': delimiter_entry
            }

        # 添加滚动功能
        self.scroll_frame.bind("<MouseWheel>", lambda e: self.scroll_canvas(e))

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
        if event.delta > 0:
            self.list_canvas.yview_scroll(-1, "units")  # 向上滚动
        else:
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
        else:
            # 没有任何图像时显示占位符
            label_img = tk.Label(self.scroll_frame, text="[无头像]", width=7, height=3)
            label_img.grid(row=row, column=column, padx=10, pady=5, sticky="w")

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


def process_text():
    # 获取文本框内容
    text = text_area.get("1.0", tk.END)

    # 获取处理选项状态
    replace_quotes = var_replace_quotes.get()
    add_blank_lines = var_add_blank_lines.get()
    remove_empty_lines = var_remove_empty_lines.get()
    add_blank_line_after_each_line = var_add_blank_line_after_each_line.get()

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

        # 正则表达式匹配中文、英文、日文、韩文的字母、数字和文字，并排除符号
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
    text_area.delete("1.0", tk.END)
    text_area.insert(tk.END, text)


# 创建GUI窗口
root = tk.Tk()
root.title("文本转语音生成器")

# 设置窗口最小尺寸
root.minsize(900, 600)
root.geometry("900x600")

# 创建选项卡容器
notebook = Notebook(root)
notebook.grid(row=0, column=0, padx=5, pady=5, columnspan=3, sticky="nsew")

# 配置 root，使其自动调整大小
root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=1)

# 创建选项卡1和选项卡2
tab1 = tk.Frame(notebook)
tab2 = tk.Frame(notebook)
tab3 = tk.Frame(notebook)
tab4 = tk.Frame(notebook)

# 将选项卡添加到Notebook中
notebook.add(tab1, text="文本转语音")
notebook.add(tab2, text="文本预处理")
notebook.add(tab3, text="分角色朗读")
notebook.add(tab4, text="角色管理器")
notebook.pack(expand=1, fill="both")

# 设置 Canvas 的宽度为 n 像素
canvas_width = 425

# 创建一个 Canvas 以支持滚动
right_frame_canvas = tk.Canvas(tab2, width=canvas_width, highlightthickness=0)  # 去掉黑框
right_frame_canvas.grid(row=0, column=2, rowspan=7, padx=5, pady=5, sticky="nsew")

# 创建一个垂直滚动条，并将其与 Canvas 绑定
scrollbar = tk.Scrollbar(tab2, orient="vertical", command=right_frame_canvas.yview)
scrollbar.grid(row=0, column=3, rowspan=7, sticky="ns")

# 将滚动条和Canvas进行绑定
right_frame_canvas.configure(yscrollcommand=scrollbar.set)

# 让选项卡内的控件可以随窗口大小变化
tab1.grid_rowconfigure(1, weight=1)  # 第1行的文本框可以扩展
tab1.grid_columnconfigure(0, weight=1)  # 第0列的文本框可以扩展

tab2.grid_rowconfigure(1, weight=1)
tab2.grid_columnconfigure(0, weight=1)

# 将现有元素布局到选项卡1中
tk.Label(tab1, text="要合成的文本:").grid(row=0, column=0, sticky="w")
text_entry = scrolledtext.ScrolledText(tab1, height=15, width=50)
text_entry.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

# top_k
tk.Label(tab1, text="top_k:").grid(row=2, column=0, sticky="w", pady=2)
top_k_var = tk.StringVar(value="15")
tk.Entry(tab1, textvariable=top_k_var).grid(row=2, column=1, padx=5, pady=2, sticky="w")

# top_p
tk.Label(tab1, text="top_p:").grid(row=3, column=0, sticky="w", pady=2)
top_p_var = tk.StringVar(value="1")
tk.Entry(tab1, textvariable=top_p_var).grid(row=3, column=1, padx=5, pady=2, sticky="w")

# temperature
tk.Label(tab1, text="温度:").grid(row=4, column=0, sticky="w", pady=2)
temperature_var = tk.StringVar(value="1")
tk.Entry(tab1, textvariable=temperature_var).grid(row=4, column=1, padx=5, pady=2, sticky="w")

# 语速
tk.Label(tab1, text="语速:").grid(row=5, column=0, sticky="w", pady=2)
speed_var = tk.StringVar(value="1")
tk.Entry(tab1, textvariable=speed_var).grid(row=5, column=1, padx=5, pady=2, sticky="w")

# 无参考模式
tk.Label(tab1, text="无参考模式:").grid(row=6, column=0, sticky="w", pady=2)
ref_free_var = tk.BooleanVar()
tk.Checkbutton(tab1, variable=ref_free_var).grid(row=6, column=1, padx=5, pady=2, sticky="w")

# 冻结设置
tk.Label(tab1, text="冻结设置:").grid(row=7, column=0, sticky="w", pady=2)
if_freeze_var = tk.BooleanVar()
tk.Checkbutton(tab1, variable=if_freeze_var).grid(row=7, column=1, padx=5, pady=2, sticky="w")

# 右侧区域
right_frame = tk.Frame(tab1)
right_frame.grid(row=0, column=2, rowspan=8, padx=5, pady=5, sticky="n")

# 创建一个 Label 和文本框，用于输入 URL
label = tk.Label(right_frame, text="Gradio URL:")
label.grid(row=0, column=0, sticky="w", pady=1, columnspan=2)

url_entry = tk.Entry(right_frame, width=50)
url_entry.grid(row=1, column=0, pady=1, sticky="w")
url_entry.insert(0, "http://localhost:9872/")  # 设置默认值

# 创建一个按钮，按下后初始化 Gradio 客户端
connect_button = tk.Button(right_frame, text=" 连接 ", command=connect_to_gradio)
connect_button.grid(row=1, column=2, padx=9, pady=1, sticky="w")

# 右侧区域内
in_right_frame = tk.Frame(right_frame)
in_right_frame.grid(row=6, column=0, rowspan=5, sticky="wn")

# 添加实例下拉栏1
tk.Label(in_right_frame, text="SoVITS模型:").grid(row=0, column=1, sticky="w", pady=1, padx=5)
sovits_var = tk.StringVar(value="请选择")
sovits_menu = tk.OptionMenu(in_right_frame, sovits_var, [])
sovits_menu.grid(row=0, column=2, padx=5, pady=1, sticky="w", columnspan=2)
sovits_menu.config(width=23)

# 添加实例下拉栏2
tk.Label(in_right_frame, text="GPT模型:").grid(row=1, column=1, sticky="w", pady=1, padx=5)
gpt_var = tk.StringVar(value="请选择")
gpt_menu = tk.OptionMenu(in_right_frame, gpt_var, [])
gpt_menu.grid(row=1, column=2, padx=5, pady=1, sticky="w", columnspan=2)
gpt_menu.config(width=23)

# 添加按钮1
tk.Button(in_right_frame, text="刷新模型", command=run_update_model_choices).grid(row=0, column=0, pady=5, sticky="w")

# 添加按钮2
tk.Button(in_right_frame, text="确认模型", command=run_submit).grid(row=1, column=0,  pady=5, sticky="w")

# 参考音频路径
tk.Label(right_frame, text="参考音频路径:").grid(row=2, column=0, sticky="w", pady=1)
ref_wav_path_entry = tk.Entry(right_frame, width=50)
ref_wav_path_entry.grid(row=3, column=0, pady=1, sticky="w", columnspan=2)
tk.Button(right_frame, text="浏览...", command=lambda: browse_file(ref_wav_path_entry)).grid(row=3, column=2, padx=9, pady=1, sticky="w")

# 提示文本
tk.Label(right_frame, text="提示文本:").grid(row=4, column=0, sticky="w", pady=1)
prompt_text_entry = tk.Entry(right_frame, width=50)
prompt_text_entry.grid(row=5, column=0, pady=1, sticky="w", columnspan=2)

# 参考语言
tk.Label(in_right_frame, text="参考语言:").grid(row=3, column=0, columnspan=2, sticky="w", pady=1)
prompt_language_var = tk.StringVar(value="请选择")
prompt_language_menu = tk.OptionMenu(in_right_frame, prompt_language_var, "请先确认模型")
prompt_language_menu.grid(row=3, column=2, padx=5, pady=1, sticky="w")

# 生成语言
tk.Label(in_right_frame, text="生成语言:").grid(row=4, column=0, columnspan=2, sticky="w", pady=1)
text_language_var = tk.StringVar(value="请选择")
text_language_menu = tk.OptionMenu(in_right_frame, text_language_var, "请先确认模型")
text_language_menu.grid(row=4, column=2, padx=5, pady=1, sticky="w")

# 分句内切割方式
tk.Label(in_right_frame, text="分句内切割方式:").grid(row=5, column=0, columnspan=2, sticky="w", pady=1)
cut_method_var = tk.StringVar(value="不切")
tk.OptionMenu(in_right_frame, cut_method_var, "不切", "凑四句一切", "凑50字一切", "按中文句号。切", "按英文句号.切", "按标点符号切").grid(row=5, column=2, padx=5, pady=1, sticky="w")

# 自定义分句符号
tk.Label(right_frame, text="分句符号(留空为不分句,输出一个完整音频):").grid(row=11, column=0, sticky="w", pady=1)
delimiter_entry = tk.Entry(right_frame, width=50)
delimiter_entry.grid(row=12, column=0, pady=1, sticky="w", columnspan=2)

# 选择输出目录
tk.Label(right_frame, text="选择输出目录:").grid(row=13, column=0, sticky="w", pady=1)
output_dir_entry = tk.Entry(right_frame, width=50)
output_dir_entry.grid(row=14, column=0, pady=1, sticky="w", columnspan=2)
tk.Button(right_frame, text="浏览...", command=lambda: browse_directory(output_dir_entry)).grid(row=14, column=2, padx=9, pady=1, sticky="w")

# 文件名前缀
tk.Label(right_frame, text="文件名前缀:").grid(row=15, column=0, sticky="w", pady=1)
filename_prefix_entry = tk.Entry(right_frame, width=50)
filename_prefix_entry.grid(row=16, column=0, pady=1, sticky="w", columnspan=2)

# 创建进度条和时间信息的Frame
progress_frame = tk.Frame(tab1)
progress_frame.grid(row=17, column=0, columnspan=3, pady=5, sticky="ew")

# 配置 progress_frame 的列使其自动扩展
progress_frame.grid_columnconfigure(1, weight=1)

# 进度百分比
percentage_label = tk.Label(progress_frame, text="进度: 0%")
percentage_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

# 进度条
progress_bar = Progressbar(progress_frame, orient="horizontal", mode="determinate")
progress_bar.grid(row=0, column=1, padx=1, sticky="ew")

# 运行时间和剩余时间
time_label = tk.Label(progress_frame, text="运行时间|剩余时间: 00:00:00|00:00:00")
time_label.grid(row=0, column=2, padx=1, pady=5, sticky="e")

# 提交按钮
tk.Button(progress_frame, text="生成语音", command=on_generate_button_click).grid(row=0, column=3, pady=5, padx=10)

# 创建 right_frame2 并将其放置在 Canvas 上
right_frame2 = tk.Frame(right_frame_canvas)
right_frame_canvas.create_window((0, 0), window=right_frame2, anchor="nw")

# 更新 Canvas 的滚动区域
def on_frame_configure(event):
    right_frame_canvas.configure(scrollregion=right_frame_canvas.bbox("all"))

right_frame2.bind("<Configure>", on_frame_configure)

# 绑定鼠标滚轮事件
def on_mousewheel(event):
    right_frame_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

# 将鼠标滚轮绑定到 right_frame2
right_frame2.bind("<MouseWheel>", on_mousewheel)  # Windows 和 macOS
right_frame2.bind("<Button-4>", on_mousewheel)  # Linux 向上滚动
right_frame2.bind("<Button-5>", on_mousewheel)  # Linux 向下滚动

# 左侧列元素
tk.Label(tab2, text="文章排版转换:").grid(row=0, column=0, sticky="w")
text_area = scrolledtext.ScrolledText(tab2, wrap=tk.WORD)
text_area.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

# 创建处理选项复选框
var_replace_quotes = tk.BooleanVar()
var_add_blank_lines = tk.BooleanVar()
var_remove_empty_lines = tk.BooleanVar()
var_add_blank_line_after_each_line = tk.BooleanVar()

tk.Checkbutton(tab2, text="将“和”替换为「和」", variable=var_replace_quotes).grid(row=2, column=0, sticky="w")

tk.Checkbutton(tab2, text="在「前和」后换行", variable=var_add_blank_lines).grid(row=3, column=0, sticky="w")

tk.Checkbutton(tab2, text="删除仅含符号的行", variable=var_remove_empty_lines).grid(row=4, column=0, sticky="w")

tk.Checkbutton(tab2, text="段落间添加空白行", variable=var_add_blank_line_after_each_line).grid(row=5, column=0, sticky="w")

tk.Button(tab2, text="处理文本", command=process_text).grid(row=6, column=0, pady=10, sticky="w")

# 让窗口的大小变化事件动态调整布局
def on_resize(event):
    root.update_idletasks()

root.bind("<Configure>", on_resize)

# 将原有元素布局到选项卡中
app = AnnotationApp(right_frame2)

app = ChapterSplitterApp(right_frame2)

app = FileMergerApp(right_frame2)

app = DocumentProcessorApp(right_frame2)

# 创建 FolderAudioViewer 实例
folder_audio_viewer = FolderAudioViewer(tab4)

# 创建 VoiceGeneratorApp 实例，并传入 folder_path_var
voice_generator_app = VoiceGeneratorApp(tab3, folder_audio_viewer.folder_path_var)

# 为所有控件绑定鼠标滚轮事件
def bind_scroll(event):
    on_mousewheel(event)

def bind_all_widgets(parent):
    for widget in parent.winfo_children():
        widget.bind("<MouseWheel>", bind_scroll)  # Windows 和 macOS
        widget.bind("<Button-4>", bind_scroll)    # Linux 向上滚动
        widget.bind("<Button-5>", bind_scroll)    # Linux 向下滚动
        if widget.winfo_children():
            bind_all_widgets(widget)  # 递归绑定子控件

bind_all_widgets(right_frame2)

#初始化时连接服务
connect_to_gradio()

# 初始化时更新模型选择
update_model_choices()

#程序打包指令1(先执行)：Pyinstaller -F -w -i sd.ico tts4.0.1.9.py
#程序打包指令2(后执行)：Pyinstaller -F -w -i sd.ico tts4.0.1.9.py --collect-data=gradio_client --collect-data=gradio

# 启动主循环
root.mainloop()