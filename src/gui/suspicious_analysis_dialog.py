# -*- coding: utf-8 -*-
"""
可疑信息分析对话框
用于快速搜索和分析可能包含敏感信息的数据
"""

import json
import time
from pathlib import Path
# 在导入部分添加
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QSplitter, QPushButton, QProgressBar, QLabel,
    QMessageBox, QFileDialog, QHeaderView, QApplication, QWidget, QScrollBar
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor


class SuspiciousSearchThread(QThread):
    """可疑信息搜索线程"""
    progress_updated = Signal(str)
    progress_percent = Signal(int)
    result_found = Signal(str, str, list)  # 分类名, 颜色, 结果列表
    search_finished = Signal()
    
    def __init__(self, database_manager):
        super().__init__()
        self.database_manager = database_manager
        
        # 定义搜索关键词分类
        self.categories = {
            "密码相关": {
                "keywords": ["密码", "秘密", "secret", "password", "hidden", "隐藏"],
                "regex": [],
                "color": "#FF5722"
            },
            "钱包相关": {
                "keywords": ["钱包", "wallet", "钱", "支付", "微信", "购买", "欠"],
                "regex": [],
                "color": "#4CAF50"
            },
            "服务器相关": {
                "keywords": ["地址", "服务器", "host", "ip地址", "端口","ip:",":port"],
                "regex": [r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"],  # IP地址
                "color": "#2196F3"
            },
            "加密容器相关": {
                "keywords": ["VC:", "veracrypt", "tc:", "truecrypt", "bt", "bitlocker", "秘钥", "key", "加密"],
                "regex": [],
                "color": "#9C27B0"
            },
            "其他相关": {
                "keywords": ["骗", "转账", "诈骗"],
                "regex": [r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"],  # 邮箱
                "color": "#FF9800"
            }
        }
    
    def run(self):
        """执行搜索 - 内存优化版本"""
        try:
            self.progress_updated.emit("开始可疑信息批量搜索...")
            self.progress_percent.emit(0)
            
            def progress_callback(percent, message):
                self.progress_percent.emit(percent)
                self.progress_updated.emit(message)
                # 强制处理事件，保持界面响应
                QApplication.processEvents()
            
            category_results = self.database_manager.bulk_suspicious_search(self.categories, progress_callback)
            
            self.progress_percent.emit(95)
            self.progress_updated.emit("整理搜索结果...")
            
            # 优化结果发送：分批发送避免界面卡顿
            for category, results in category_results.items():
                if results:
                    color = self.categories[category]["color"]
                    
                    # 分批发送结果，每批最多100个
                    batch_size = 100
                    for i in range(0, len(results), batch_size):
                        batch_results = results[i:i+batch_size]
                        formatted_results = []
                        
                        for result in batch_results:
                            formatted_results.append({
                                'package_name': result.package_name,
                                'database_name': result.database_name,
                                'table_name': result.table_name,
                                'column_name': result.column_name,
                                'match_value': result.match_value,
                                'parent_dir': result.parent_dir,
                                'row_data': result.row_data
                            })
                        
                        self.result_found.emit(category, color, formatted_results)
                        QApplication.processEvents()  # 保持界面响应
            
            self.progress_percent.emit(100)
            self.progress_updated.emit("搜索完成")
            
        except Exception as e:
            self.progress_updated.emit(f"搜索出错: {str(e)}")
            print(f"搜索线程错误: {e}")
        finally:
            self.search_finished.emit()


class SuspiciousAnalysisDialog(QDialog):
    """可疑信息分析对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("可疑信息分析")
        self.setMinimumSize(1000, 700)
        
        # 存储所有结果
        self.all_results = {}
        self.cached_results = {}
        self.cache_timestamp = 0
        
        # 分页显示相关
        self.current_category = None
        self.displayed_count = {}  # 每个分类已显示的数量
        self.page_size = 100  # 每页显示数量
        
        self.database_manager = None
        self.search_thread = None
        
        self.init_ui()
    
    def init_ui(self):
        """初始化用户界面 - 紧凑布局版本"""
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                font-family: 'Microsoft YaHei', Arial, sans-serif;
            }
            QPushButton {
                background-color: #f8f9fa;
                color: #495057;
                border: 1px solid #dee2e6;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 13px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
                border-color: #adb5bd;
            }
            QPushButton:pressed {
                background-color: #dee2e6;
            }
            QPushButton#start_btn {
                background-color: #007bff;
                color: white;
                border-color: #007bff;
            }
            QPushButton#start_btn:hover {
                background-color: #0056b3;
                border-color: #0056b3;
            }
            QProgressBar {
                border: 1px solid #dee2e6;
                border-radius: 3px;
                text-align: center;
                background-color: #f8f9fa;
                height: 16px;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #007bff;
                border-radius: 2px;
            }
            QLabel#status {
                color: #6c757d;
                font-size: 11px;
                padding: 2px 4px;
            }
            QTreeWidget {
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                selection-background-color: #e3f2fd;
                font-size: 13px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px;
                border-bottom: 1px solid #f1f3f4;
            }
            QTreeWidget::item:selected {
                background-color: #e3f2fd;
            }
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                selection-background-color: #e3f2fd;
            }
            QSplitter::handle {
                background-color: #dee2e6;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 顶部控制区域 - 紧凑布局
        top_layout = QHBoxLayout()
        top_layout.setSpacing(6)
        
        # 按钮组
        self.start_analysis_btn = QPushButton("开始分析")
        self.start_analysis_btn.setObjectName("start_btn")
        self.start_analysis_btn.clicked.connect(self.start_analysis)
        top_layout.addWidget(self.start_analysis_btn)
        
        self.clear_cache_btn = QPushButton("清除缓存")
        self.clear_cache_btn.clicked.connect(self.clear_cache)
        top_layout.addWidget(self.clear_cache_btn)
        
        self.export_btn = QPushButton("导出结果")
        self.export_btn.clicked.connect(self.export_results)
        top_layout.addWidget(self.export_btn)
        
        # 状态信息 - 放在同一行右侧
        top_layout.addStretch()
        
        # 状态标签 - 小字体
        self.status_label = QLabel("准备就绪")
        self.status_label.setObjectName("status")
        top_layout.addWidget(self.status_label)
        
        layout.addLayout(top_layout)
        
        # 进度条 - 很小的高度
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(16)  # 限制最大高度
        layout.addWidget(self.progress_bar)
        
        # 主要内容区域 - 占据绝大部分空间
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：分类树
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderLabels(["分类", "数量"])
        self.category_tree.itemClicked.connect(self.on_category_selected)
        self.category_tree.setFixedWidth(240)
        
        header = self.category_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        
        splitter.addWidget(self.category_tree)
        
        # 右侧：详细内容
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFont(QFont("Consolas", 10))
        
        # 连接滚动条信号以实现自动加载
        def on_scroll_changed(self, value):
            """滚动条变化时检查是否需要加载更多结果"""
            scroll_bar = self.detail_text.verticalScrollBar()
            
            # 检查是否滚动到底部（留一点缓冲区域）
            if value >= scroll_bar.maximum() - 10:
                self.load_more_results()
        
        splitter.addWidget(self.detail_text)
        
        # 设置分割器比例 - 右侧占绝大部分
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 800])  # 右侧更大
        
        layout.addWidget(splitter)
        
        # 确保主内容区域占据绝大部分空间
        layout.setStretchFactor(splitter, 1)  # 让splitter可以拉伸
    
    def set_database_manager(self, database_manager):
        """设置数据库管理器"""
        self.database_manager = database_manager
        # 检查是否有缓存
        self.check_and_load_cache()
    
    def start_analysis(self):
        """开始分析"""
        if not self.database_manager:
            QMessageBox.warning(self, "警告", "数据库管理器未设置")
            return
        
        # 清空之前的结果
        self.category_tree.clear()
        self.detail_text.clear()
        self.all_results = {}
        
        # 显示进度条
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 禁用按钮
        self.start_analysis_btn.setEnabled(False)
        
        # 创建并启动搜索线程
        self.search_thread = SuspiciousSearchThread(self.database_manager)
        self.search_thread.progress_updated.connect(self.update_progress)
        self.search_thread.progress_percent.connect(self.progress_bar.setValue)
        self.search_thread.result_found.connect(self.add_category_result)
        self.search_thread.search_finished.connect(self.on_search_finished)
        self.search_thread.start()
    
    def update_progress(self, message):
        """更新进度信息"""
        self.status_label.setText(message)
    
    def add_category_result(self, category, color, results):
        """添加分类结果"""
        if not results:
            return
        
        # 保存结果
        if category not in self.all_results:
            self.all_results[category] = []
        self.all_results[category].extend(results)
        
        # 更新树形控件
        self.update_category_tree()
    
    def update_category_tree(self):
        """更新分类树 - 支持二级目录"""
        self.category_tree.clear()
        
        # 获取搜索分类定义
        search_thread = SuspiciousSearchThread(None)
        
        for category, results in self.all_results.items():
            if results:
                # 创建主分类项
                main_item = QTreeWidgetItem([category, str(len(results))])
                main_item.setData(0, Qt.ItemDataRole.UserRole, category)
                
                # 设置颜色
                color = search_thread.categories.get(category, {}).get("color", "#000000")
                main_item.setForeground(0, QColor(color))
                
                # 添加关键词子项
                category_info = search_thread.categories.get(category, {})
                keywords = category_info.get("keywords", [])
                regex_patterns = category_info.get("regex", [])
                
                # 统计每个关键词的匹配数量
                keyword_counts = {}
                for keyword in keywords:
                    count = sum(1 for result in results if keyword.lower() in str(result.get('match_value', '')).lower())
                    if count > 0:
                        keyword_counts[keyword] = count
                
                # 统计正则表达式匹配数量
                import re
                for pattern in regex_patterns:
                    try:
                        regex_obj = re.compile(pattern, re.IGNORECASE)
                        count = sum(1 for result in results if regex_obj.search(str(result.get('match_value', ''))))
                        if count > 0:
                            keyword_counts[f"正则:{pattern}"] = count
                    except:
                        pass
                
                # 添加关键词子项
                for keyword, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True):
                    keyword_item = QTreeWidgetItem([keyword, str(count)])
                    keyword_item.setData(0, Qt.ItemDataRole.UserRole, f"{category}:{keyword}")
                    keyword_item.setForeground(0, QColor("#666666"))
                    main_item.addChild(keyword_item)
                
                self.category_tree.addTopLevelItem(main_item)
                
                # 默认展开主分类
                main_item.setExpanded(True)
        
        # 调整列宽
        self.category_tree.resizeColumnToContents(0)
        self.category_tree.resizeColumnToContents(1)
    
    def on_category_selected(self, item):
        """选择分类时显示详细内容 - 支持关键词筛选"""
        user_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not user_data:
            return
        
        if ':' in user_data:  # 选择了关键词子项
            category, keyword = user_data.split(':', 1)
            if category not in self.all_results:
                return
            
            # 筛选包含该关键词的结果
            all_results = self.all_results[category]
            if keyword.startswith('正则:'):
                pattern = keyword[3:]
                import re
                try:
                    regex_obj = re.compile(pattern, re.IGNORECASE)
                    filtered_results = [r for r in all_results if regex_obj.search(str(r.get('match_value', '')))]
                except:
                    filtered_results = []
            else:
                filtered_results = [r for r in all_results if keyword.lower() in str(r.get('match_value', '')).lower()]
            
            self.current_category = category
            self.current_keyword = keyword
            self.displayed_count[f"{category}:{keyword}"] = 0
            
            # 临时替换结果进行显示
            original_results = self.all_results[category]
            self.all_results[category] = filtered_results
            self.display_results_page(category, reset=True)
            self.all_results[category] = original_results  # 恢复原始结果
            
        else:  # 选择了主分类
            category = user_data
            if category not in self.all_results:
                return
            
            self.current_category = category
            self.current_keyword = None
            self.displayed_count[category] = 0
            
            # 显示第一页
            self.display_results_page(category, reset=True)
    
    def display_results_page(self, category, reset=False):
        """显示结果页面"""
        if category not in self.all_results:
            return
            
        results = self.all_results[category]
        
        if reset:
            self.detail_text.clear()
            self.displayed_count[category] = 0
        
        start_idx = self.displayed_count[category]
        end_idx = min(start_idx + self.page_size, len(results))
        
        if start_idx >= len(results):
            return  # 没有更多结果
        
        # 构建内容
        if reset:
            content = f"=== {category} ({len(results)} 条结果) ===\n\n"
        else:
            content = "\n"  # 追加模式
        
        # 使用富文本格式
        cursor = self.detail_text.textCursor()
        if not reset:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # 设置格式
        normal_format = QTextCharFormat()
        normal_format.setForeground(QColor("#000000"))
        
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#FF0000"))  # 红色序号
        number_format.setFontWeight(QFont.Weight.Bold)
        
        match_format = QTextCharFormat()
        match_format.setForeground(QColor("#0066CC"))  # 蓝色匹配词
        match_format.setFontWeight(QFont.Weight.Bold)
        
        for i in range(start_idx, end_idx):
            result = results[i]
            
            # 插入红色序号
            cursor.setCharFormat(number_format)
            cursor.insertText(f"[{i+1}] ")
            
            # 插入正常文本
            cursor.setCharFormat(normal_format)
            cursor.insertText(f"{result['package_name']} > {result['database_name']} > {result['table_name']} > {result['column_name']}\n")
            
            # 处理匹配值，根据是否为关键词筛选决定高亮方式
            match_value = str(result['match_value'])
            cursor.insertText("    匹配值: ")
            
            # 判断是否为二级目录（关键词筛选）
            is_keyword_filter = hasattr(self, 'current_keyword') and self.current_keyword is not None
            
            if is_keyword_filter:
                # 二级目录：移除"[匹配:xxx]"标记，直接高亮关键词内容
                if '[匹配:' in match_value:
                    # 移除所有"[匹配:xxx]"标记
                    import re
                    clean_value = re.sub(r'\[匹配:[^\]]+\]', '', match_value)
                    
                    # 高亮当前关键词
                    keyword = self.current_keyword
                    if keyword.startswith('正则:'):
                        # 正则表达式高亮
                        pattern = keyword[3:]
                        try:
                            regex_obj = re.compile(pattern, re.IGNORECASE)
                            parts = regex_obj.split(clean_value)
                            matches = regex_obj.findall(clean_value)
                            
                            for i, part in enumerate(parts):
                                cursor.setCharFormat(normal_format)
                                cursor.insertText(part)
                                if i < len(matches):
                                    cursor.setCharFormat(match_format)
                                    cursor.insertText(matches[i])
                        except:
                            cursor.setCharFormat(normal_format)
                            cursor.insertText(clean_value)
                    else:
                        # 普通关键词高亮
                        parts = clean_value.lower().split(keyword.lower())
                        original_parts = []
                        start = 0
                        for part in parts[:-1]:
                            end = start + len(part)
                            original_parts.append(clean_value[start:end])
                            start = end + len(keyword)
                        original_parts.append(clean_value[start:])
                        
                        for i, part in enumerate(original_parts):
                            cursor.setCharFormat(normal_format)
                            cursor.insertText(part)
                            if i < len(original_parts) - 1:
                                cursor.setCharFormat(match_format)
                                cursor.insertText(clean_value[len(''.join(original_parts[:i+1])):len(''.join(original_parts[:i+1]))+len(keyword)])
                else:
                    cursor.setCharFormat(normal_format)
                    cursor.insertText(match_value)
            else:
                # 一级目录：保持"[匹配:xxx]"标记的蓝色高亮，同时高亮匹配值中的关键词
                if '[匹配:' in match_value:
                    parts = match_value.split('[匹配:')
                    cursor.setCharFormat(normal_format)
                    cursor.insertText(parts[0])
                    
                    for part in parts[1:]:
                        if ']' in part:
                            match_word, rest = part.split(']', 1)
                            cursor.setCharFormat(match_format)
                            cursor.insertText(f"[匹配:{match_word}]")
                            cursor.setCharFormat(normal_format)
                            cursor.insertText(rest)
                        else:
                            cursor.insertText(f"[匹配:{part}")
                else:
                    cursor.setCharFormat(normal_format)
                    cursor.insertText(match_value)
            
            cursor.insertText("\n")
            cursor.insertText(f"    目录: {result['parent_dir']}\n\n")
        
        # 更新显示计数
        self.displayed_count[category] = end_idx
        
        # 如果还有更多结果，显示提示
        if end_idx < len(results):
            cursor.setCharFormat(normal_format)
            cursor.insertText(f"... 还有 {len(results) - end_idx} 条结果，滚动到底部加载更多\n")
    
    def load_more_results(self):
        """加载更多结果"""
        if not self.current_category:
            return
            
        category = self.current_category
        if category not in self.all_results:
            return
            
        results = self.all_results[category]
        displayed = self.displayed_count.get(category, 0)
        
        if displayed >= len(results):
            return  # 已经显示完所有结果
        
        # 移除"还有..."提示文本
        cursor = self.detail_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        
        # 显示下一页
        self.display_results_page(category, reset=False)
    
    def on_search_finished(self):
        """搜索完成"""
        self.progress_bar.setVisible(False)
        
        total_results = sum(len(results) for results in self.all_results.values())
        
        # 保存结果到缓存
        self.cached_results = self.all_results.copy()
        self.cache_timestamp = time.time()
        
        # 重新启用按钮
        self.start_analysis_btn.setEnabled(True)
        
        if total_results > 0:
            self.status_label.setText(f"分析完成，共找到 {total_results} 条可疑信息")
        else:
            self.status_label.setText("分析完成，未找到可疑信息")
    
    def check_and_load_cache(self):
        """检查并加载缓存数据"""
        if self.cached_results:
            # 有缓存数据，显示提示并加载
            total_cached = sum(len(results) for results in self.cached_results.values())
            cache_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.cache_timestamp))
            
            reply = QMessageBox.question(
                self, "发现缓存数据", 
                f"发现 {cache_time} 的缓存数据，共 {total_cached} 条结果。\n是否加载缓存数据？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.all_results = self.cached_results.copy()
                self.update_category_tree()
                self.status_label.setText(f"已加载缓存数据，共 {total_cached} 条结果")
    
    def clear_cache(self):
        """清除缓存"""
        reply = QMessageBox.question(
            self, "确认清除", 
            "确定要清除缓存的分析结果吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cached_results = {}
            self.cache_timestamp = None
            self.all_results = {}
            self.category_tree.clear()
            self.detail_text.clear()
            self.status_label.setText("缓存已清除")
    
    def export_results(self):
        """导出结果"""
        if not self.all_results:
            QMessageBox.information(self, "提示", "没有可导出的结果")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出可疑信息分析结果", 
            f"suspicious_analysis_{int(time.time())}.json",
            "JSON文件 (*.json)"
        )
        
        if file_path:
            try:
                # 转换数据，确保所有值都是JSON可序列化的
                serializable_results = {}
                for category, results in self.all_results.items():
                    serializable_results[category] = []
                    for result in results:
                        # 确保所有字段都是字符串
                        clean_result = {
                            'package_name': str(result.get('package_name', '')),
                            'database_name': str(result.get('database_name', '')),
                            'table_name': str(result.get('table_name', '')),
                            'column_name': str(result.get('column_name', '')),
                            'match_value': str(result.get('match_value', '')).replace('\x00', ''),  # 移除null字符
                            'parent_dir': str(result.get('parent_dir', '')),
                            'row_data': str(result.get('row_data', ''))
                        }
                        serializable_results[category].append(clean_result)
                    
                export_data = {
                    "timestamp": time.time(),
                    "total_results": sum(len(results) for results in serializable_results.values()),
                    "categories": serializable_results
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                
                QMessageBox.information(self, "成功", f"结果已导出到：{file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败：{str(e)}")