# -*- coding: utf-8 -*-
"""
可疑信息分析对话框
用于快速搜索和分析可能包含敏感信息的数据
"""

import json
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QSplitter, QPushButton, QProgressBar, QLabel,
    QMessageBox, QFileDialog, QHeaderView, QApplication, QWidget
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor


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
                "keywords": ["钱包", "wallet", "钱", "支付宝", "微信", "购买", "欠"],
                "regex": [r"(?=.*[a-zA-Z])(?=.*\d)^[a-zA-Z\d]{12,64}$"],  # 同时包含字母和数字的12-64位纯字母数字字符串
                "color": "#4CAF50"
            },
            "服务器相关": {
                "keywords": ["地址", "服务器", "server", "host", "ip", "port"],
                "regex": [r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"],  # IP地址
                "color": "#2196F3"
            },
            "加密容器相关": {
                "keywords": ["VC", "veracrypt", "tc", "truecrypt", "bt", "bitlocker", "秘钥", "key"],
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
        """执行搜索"""
        try:
            self.progress_updated.emit("开始搜索可疑信息...")
            self.progress_percent.emit(0)
            
            # 为每个分类收集结果
            category_results = {cat: [] for cat in self.categories.keys()}
            
            total_categories = len(self.categories)
            processed_categories = 0
            
            for category, config in self.categories.items():
                self.progress_updated.emit(f"搜索 {category}...")
                
                unique_results = set()  # 用于去重
                
                # 搜索关键词
                for keyword in config["keywords"]:
                    try:
                        search_results = self.database_manager.global_search(keyword, case_sensitive=False, use_regex=False)
                        
                        for result in search_results:
                            # 创建唯一键用于去重
                            unique_key = f"{result.package_name}|{result.parent_dir}|{result.database_name}|{result.table_name}|{result.column_name}|{str(result.match_value)[:100]}"
                            if unique_key not in unique_results:
                                unique_results.add(unique_key)
                                category_results[category].append({
                                    'package_name': result.package_name,
                                    'parent_dir': result.parent_dir,
                                    'db_name': result.database_name,
                                    'table_name': result.table_name,
                                    'column_name': result.column_name,
                                    'value': str(result.match_value),
                                    'keyword': keyword
                                })
                    except Exception as e:
                        print(f"搜索关键词 '{keyword}' 时出错: {e}")
                
                # 搜索正则表达式
                for pattern in config["regex"]:
                    try:
                        search_results = self.database_manager.global_search(pattern, case_sensitive=False, use_regex=True)
                        
                        for result in search_results:
                            # 创建唯一键用于去重
                            unique_key = f"{result.package_name}|{result.parent_dir}|{result.database_name}|{result.table_name}|{result.column_name}|{str(result.match_value)[:100]}"
                            if unique_key not in unique_results:
                                unique_results.add(unique_key)
                                category_results[category].append({
                                    'package_name': result.package_name,
                                    'parent_dir': result.parent_dir,
                                    'db_name': result.database_name,
                                    'table_name': result.table_name,
                                    'column_name': result.column_name,
                                    'value': str(result.match_value),
                                    'keyword': f"正则:{pattern}"
                                })
                    except Exception as e:
                        print(f"搜索正则表达式 '{pattern}' 时出错: {e}")
                
                processed_categories += 1
                progress = int((processed_categories / total_categories) * 100)
                self.progress_percent.emit(progress)
            
            # 发送结果
            for category, results in category_results.items():
                if results:
                    color = self.categories[category]["color"]
                    self.result_found.emit(category, color, results)
            
            self.progress_updated.emit("搜索完成")
            self.search_finished.emit()
            
        except Exception as e:
            self.progress_updated.emit(f"搜索出错: {str(e)}")
            self.search_finished.emit()
    
    def _search_in_database(self, db_info, package_name, parent_dir, db_name, keywords, regex_patterns):
        """在数据库中搜索指定关键词和正则表达式 - 已弃用，使用global_search代替"""
        # 这个方法已经不再使用，保留以防需要
        pass


class SuspiciousAnalysisDialog(QDialog):
    """可疑信息分析对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.database_manager = None
        self.search_thread = None
        self.all_results = {}
        
        self.setWindowTitle("可疑信息分析")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)
        
        self.init_ui()
    
    def init_ui(self):
        """初始化用户界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(5)  # 减少组件间距
        layout.setContentsMargins(8, 8, 8, 8)  # 减少边距
        
        # 状态栏 - 紧凑布局
        status_layout = QHBoxLayout()
        status_layout.setSpacing(10)
        
        self.status_label = QLabel("准备开始分析...")
        self.status_label.setMaximumHeight(25)  # 限制状态标签高度
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(20)  # 限制进度条高度
        self.progress_bar.setMaximumWidth(200)  # 限制进度条宽度
        
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()  # 添加弹性空间
        status_layout.addWidget(self.progress_bar)
        
        # 创建状态栏容器并设置固定高度
        status_widget = QWidget()
        status_widget.setLayout(status_layout)
        status_widget.setMaximumHeight(35)  # 限制状态栏总高度
        layout.addWidget(status_widget)
        
        # 主要内容区域 - 分割视图
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：分类树
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderLabel("可疑信息分类")
        self.category_tree.setMaximumWidth(280)  # 稍微增加宽度
        self.category_tree.setMinimumWidth(200)  # 设置最小宽度
        self.category_tree.itemClicked.connect(self.on_category_selected)
        
        # 右侧：详细内容
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFont(QFont("Consolas", 10))
        
        splitter.addWidget(self.category_tree)
        splitter.addWidget(self.detail_text)
        splitter.setSizes([280, 720])  # 调整比例
        
        # 让分割器占据主要空间
        layout.addWidget(splitter, 1)  # stretch factor = 1，占据剩余空间
        
        # 底部按钮 - 紧凑布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.setContentsMargins(0, 5, 0, 0)  # 减少上边距
        
        self.export_txt_btn = QPushButton("导出TXT")
        self.export_txt_btn.clicked.connect(self.export_to_txt)
        self.export_txt_btn.setEnabled(False)
        self.export_txt_btn.setMaximumHeight(30)  # 限制按钮高度
        self.export_txt_btn.setMinimumWidth(80)
        
        self.export_csv_btn = QPushButton("导出CSV")
        self.export_csv_btn.clicked.connect(self.export_to_csv)
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.setMaximumHeight(30)  # 限制按钮高度
        self.export_csv_btn.setMinimumWidth(80)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setMaximumHeight(30)  # 限制按钮高度
        self.close_btn.setMinimumWidth(60)
        
        button_layout.addWidget(self.export_txt_btn)
        button_layout.addWidget(self.export_csv_btn)
        button_layout.addStretch()  # 弹性空间
        button_layout.addWidget(self.close_btn)
        
        # 创建按钮容器并设置固定高度
        button_widget = QWidget()
        button_widget.setLayout(button_layout)
        button_widget.setMaximumHeight(40)  # 限制按钮区域总高度
        layout.addWidget(button_widget)
    
    def set_database_manager(self, database_manager):
        """设置数据库管理器"""
        self.database_manager = database_manager
    
    def start_analysis(self):
        """开始分析"""
        if not self.database_manager:
            QMessageBox.warning(self, "警告", "数据库管理器未设置")
            return
        
        # 清空之前的结果
        self.category_tree.clear()
        self.detail_text.clear()
        self.all_results.clear()
        
        # 显示进度条
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.export_txt_btn.setEnabled(False)
        self.export_csv_btn.setEnabled(False)
        
        # 创建并启动搜索线程
        self.search_thread = SuspiciousSearchThread(self.database_manager)
        self.search_thread.progress_updated.connect(self.update_progress)
        self.search_thread.progress_percent.connect(self.update_progress_percent)
        self.search_thread.result_found.connect(self.add_category_result)
        self.search_thread.search_finished.connect(self.on_search_finished)
        
        self.search_thread.start()
    
    def update_progress(self, message):
        """更新进度信息"""
        self.status_label.setText(message)
    
    def update_progress_percent(self, percent):
        """更新进度百分比"""
        self.progress_bar.setValue(percent)
    
    def add_category_result(self, category, color, results):
        """添加分类结果"""
        if not results:
            return
        
        # 保存结果
        self.all_results[category] = results
        
        # 创建分类项
        category_item = QTreeWidgetItem(self.category_tree)
        category_item.setText(0, f"{category} ({len(results)})")
        category_item.setData(0, Qt.ItemDataRole.UserRole, category)
        
        # 设置颜色
        category_item.setForeground(0, QColor(color))
        
        # 设置字体加粗
        font = category_item.font(0)
        font.setBold(True)
        category_item.setFont(0, font)
        
        # 展开项目
        category_item.setExpanded(True)
    
    def on_category_selected(self, item):
        """选择分类时显示详细内容"""
        category = item.data(0, Qt.ItemDataRole.UserRole)
        if not category or category not in self.all_results:
            return
        
        results = self.all_results[category]
        
        # 构建显示内容
        content = f"=== {category} ===\n"
        content += f"共找到 {len(results)} 条相关信息\n\n"
        
        for i, result in enumerate(results, 1):
            content += f"{i}. 位置: {result['package_name']}/{result['parent_dir']}/{result['db_name']}\n"
            content += f"   表: {result['table_name']}\n"
            content += f"   字段: {result['column_name']}\n"
            content += f"   内容: {result['value'][:200]}{'...' if len(result['value']) > 200 else ''}\n"
            content += f"   匹配: {result['keyword']}\n"
            content += "-" * 80 + "\n"
        
        self.detail_text.setPlainText(content)
    
    def on_search_finished(self):
        """搜索完成"""
        self.progress_bar.setVisible(False)
        
        total_results = sum(len(results) for results in self.all_results.values())
        
        if total_results > 0:
            self.status_label.setText(f"分析完成，共找到 {total_results} 条可疑信息")
            self.export_txt_btn.setEnabled(True)
            self.export_csv_btn.setEnabled(True)
            
            # 自动选择第一个分类
            if self.category_tree.topLevelItemCount() > 0:
                first_item = self.category_tree.topLevelItem(0)
                self.category_tree.setCurrentItem(first_item)
                self.on_category_selected(first_item)
        else:
            self.status_label.setText("分析完成，未找到可疑信息")
            self.detail_text.setPlainText("未找到包含可疑关键词的数据。")
    
    def export_to_txt(self):
        """导出为TXT文件"""
        if not self.all_results:
            QMessageBox.information(self, "提示", "没有结果可导出")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存TXT文件", "suspicious_analysis.txt", "文本文件 (*.txt)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("可疑信息分析报告\n")
                    f.write("=" * 50 + "\n\n")
                    
                    for category, results in self.all_results.items():
                        f.write(f"【{category}】\n")
                        f.write(f"共 {len(results)} 条记录\n\n")
                        
                        for i, result in enumerate(results, 1):
                            f.write(f"{i}. 位置: {result['package_name']}/{result['parent_dir']}/{result['db_name']}\n")
                            f.write(f"   表: {result['table_name']}\n")
                            f.write(f"   字段: {result['column_name']}\n")
                            f.write(f"   内容: {result['value']}\n")
                            f.write(f"   匹配: {result['keyword']}\n")
                            f.write("-" * 80 + "\n")
                        
                        f.write("\n")
                
                QMessageBox.information(self, "成功", f"结果已导出到:\n{filename}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")
    
    def export_to_csv(self):
        """导出为CSV文件"""
        if not self.all_results:
            QMessageBox.information(self, "提示", "没有结果可导出")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存CSV文件", "suspicious_analysis.csv", "CSV文件 (*.csv)"
        )
        
        if filename:
            try:
                import csv
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['分类', '包名', '目录', '数据库', '表名', '字段名', '内容', '匹配关键词'])
                    
                    for category, results in self.all_results.items():
                        for result in results:
                            writer.writerow([
                                category,
                                result['package_name'],
                                result['parent_dir'],
                                result['db_name'],
                                result['table_name'],
                                result['column_name'],
                                result['value'],
                                result['keyword']
                            ])
                
                QMessageBox.information(self, "成功", f"结果已导出到:\n{filename}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.terminate()
            self.search_thread.wait()
        event.accept() 