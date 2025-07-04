# -*- coding: utf-8 -*-
"""
搜索对话框组件
提供全局搜索功能，并自动保存搜索结果到日志
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QCheckBox,
    QProgressBar, QMessageBox, QTextEdit, QSplitter,
    QGroupBox, QSpinBox, QComboBox, QTabWidget, QWidget, QMenu,
    QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QAction
import json
from datetime import datetime


def safe_json_serialize(obj):
    """
    安全的JSON序列化函数，处理bytes类型
    """
    def convert_value(value):
        if isinstance(value, bytes):
            try:
                # 尝试解码为UTF-8字符串
                return value.decode('utf-8', errors='replace')
            except:
                # 如果解码失败，转换为十六进制字符串
                return f"<bytes:{value.hex()}>"
        elif isinstance(value, dict):
            return {k: convert_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [convert_value(item) for item in value]
        else:
            return value
    
    return convert_value(obj)


class CellDetailDialog(QDialog):
    """单元格详细内容查看对话框"""
    
    def __init__(self, content, parent=None):
        super().__init__(parent)
        self.init_ui(content)
    
    def init_ui(self, content):
        """初始化界面"""
        self.setWindowTitle("单元格内容详情")
        self.setModal(True)
        
        # 设置对话框尺寸
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        

        
        # 内容显示区域
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(str(content) if content is not None else "")
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        layout.addWidget(self.text_edit)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        copy_btn = QPushButton("复制内容")
        copy_btn.clicked.connect(self.copy_content)
        button_layout.addWidget(copy_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def copy_content(self):
        """复制内容到剪贴板"""
        content = self.text_edit.toPlainText()
        QApplication.clipboard().setText(content)
        QMessageBox.information(self, "复制成功", "内容已复制到剪贴板")
    



class CustomSearchTableWidget(QTableWidget):
    """支持双击查看详情的搜索结果表格"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_dialog = parent
        
    def mouseDoubleClickEvent(self, event):
        """处理双击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if item and self.search_dialog:
                # 调用搜索对话框的详情显示方法
                self.search_dialog.show_row_details(item)
                return
        
        super().mouseDoubleClickEvent(event)


class SearchThread(QThread):
    """搜索线程"""
    search_completed = Signal(list)  # 搜索结果
    search_progress = Signal(str)   # 搜索进度信息
    search_error = Signal(str)      # 搜索错误
    
    def __init__(self, database_manager, search_term, case_sensitive=False, use_regex=False, search_bytes=False):
        super().__init__()
        self.database_manager = database_manager
        self.search_term = search_term
        self.case_sensitive = case_sensitive
        self.use_regex = use_regex
        self.search_bytes = search_bytes
    
    def run(self):
        try:
            self.search_progress.emit("正在搜索数据库...")
            results = self.database_manager.global_search(
                self.search_term, self.case_sensitive, self.use_regex, self.search_bytes
            )
            self.search_completed.emit(results)
        except Exception as e:
            self.search_error.emit(str(e))


class SearchDialog(QDialog):
    """搜索对话框"""
    
    # 添加跳转信号
    jump_to_database = Signal(str, str, str, str)  # package_name, parent_dir, db_name, table_name
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.database_manager = None
        self.log_manager = None
        self.search_thread = None
        self.last_results = []
        
        # 分页相关变量
        self.current_page = 1
        self.page_size = 10
        self.total_pages = 1
        self.all_results = []  # 存储所有搜索结果
        self.current_page_results = []  # 当前页显示的结果
        
        self.setWindowTitle("全局搜索")
        self.setMinimumSize(900, 600)
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 搜索输入区域
        search_group = QGroupBox("搜索条件")
        search_layout = QVBoxLayout(search_group)
        
        # 搜索词输入
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("搜索内容:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入要搜索的内容... (正则示例: \\d{11} 匹配11位数字)")
        self.search_input.returnPressed.connect(self.start_search)
        input_layout.addWidget(self.search_input)
        search_layout.addLayout(input_layout)
        
        # 搜索选项
        options_layout = QHBoxLayout()
        self.case_sensitive_cb = QCheckBox("区分大小写")
        options_layout.addWidget(self.case_sensitive_cb)
        
        self.regex_cb = QCheckBox("正则表达式")
        self.regex_cb.setToolTip("启用正则表达式搜索模式")
        options_layout.addWidget(self.regex_cb)
        
        # 新增：搜索字节选项
        self.search_bytes_cb = QCheckBox("搜索字节")
        self.search_bytes_cb.setToolTip("示例：504b0304")
        self.search_bytes_cb.stateChanged.connect(self.on_search_bytes_changed)
        options_layout.addWidget(self.search_bytes_cb)
        
        self.auto_save_cb = QCheckBox("自动保存结果")
        self.auto_save_cb.setChecked(True)
        options_layout.addWidget(self.auto_save_cb)
        
        options_layout.addStretch()
        
        # 搜索按钮
        self.search_btn = QPushButton("开始搜索")
        self.search_btn.clicked.connect(self.start_search)
        options_layout.addWidget(self.search_btn)
        
        # 清除按钮
        clear_btn = QPushButton("清除结果")
        clear_btn.clicked.connect(self.clear_results)
        options_layout.addWidget(clear_btn)
        
        # 正则帮助按钮
        regex_help_btn = QPushButton("正则帮助")
        regex_help_btn.clicked.connect(self.show_regex_help)
        options_layout.addWidget(regex_help_btn)
        
        search_layout.addLayout(options_layout)
        layout.addWidget(search_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 添加分页控制组
        pagination_group = QGroupBox("分页设置")
        pagination_layout = QHBoxLayout(pagination_group)
        
        # 每页显示数量选择
        pagination_layout.addWidget(QLabel("每页显示:"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["10", "20", "50", "100"])
        self.page_size_combo.setCurrentText("10")  # 默认10条
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)
        pagination_layout.addWidget(self.page_size_combo)
        
        pagination_layout.addStretch()
        
        # 分页控制按钮
        self.prev_page_btn = QPushButton("上一页")
        self.prev_page_btn.clicked.connect(self.prev_page)
        self.prev_page_btn.setEnabled(False)
        pagination_layout.addWidget(self.prev_page_btn)
        
        self.page_label = QLabel("第 1 页 / 共 1 页")
        pagination_layout.addWidget(self.page_label)
        
        self.next_page_btn = QPushButton("下一页")
        self.next_page_btn.clicked.connect(self.next_page)
        self.next_page_btn.setEnabled(False)
        pagination_layout.addWidget(self.next_page_btn)
        
        # 跳转页面  
        pagination_layout.addWidget(QLabel("跳转至:"))
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("页码")
        self.page_input.setMaximumWidth(60)
        self.page_input.returnPressed.connect(self.jump_to_page)
        pagination_layout.addWidget(self.page_input)
        
        jump_btn = QPushButton("GO")
        jump_btn.clicked.connect(self.jump_to_page)
        pagination_layout.addWidget(jump_btn)
        
        layout.addWidget(pagination_group)
        
        # 状态标签
        self.status_label = QLabel("准备搜索")
        layout.addWidget(self.status_label)
        
        # 主要内容区 - 使用标签页
        self.content_tabs = QTabWidget()
        
        # 搜索结果标签页
        self.results_tab = QWidget()
        self.setup_results_tab()
        self.content_tabs.addTab(self.results_tab, "搜索结果")
        
        # 搜索统计标签页
        self.stats_tab = QWidget()
        self.setup_stats_tab()
        self.content_tabs.addTab(self.stats_tab, "搜索统计")
        
        layout.addWidget(self.content_tabs)
        
        # 底部按钮
        button_layout = QHBoxLayout()
        
        # 导出按钮
        export_btn = QPushButton("导出结果")
        export_btn.clicked.connect(self.export_results)
        button_layout.addWidget(export_btn)
        
        # 保存日志按钮
        save_log_btn = QPushButton("手动保存日志")
        save_log_btn.clicked.connect(self.save_search_log)
        button_layout.addWidget(save_log_btn)
        
        button_layout.addStretch()
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        

    
    def setup_results_tab(self):
        """设置搜索结果标签页"""
        layout = QVBoxLayout(self.results_tab)
        
        # 结果计数
        self.result_count_label = QLabel("搜索结果: 0 条")
        self.result_count_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.result_count_label)
        
        # 结果表格
        self.results_table = CustomSearchTableWidget(self)
        self.results_table.setColumnCount(4)  # 减少到4列
        self.results_table.setHorizontalHeaderLabels([
            "包名", "数据库", "匹配内容", "行数据预览"
        ])
        self.results_table.setSortingEnabled(True)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # 双击查看详细信息
        self.results_table.itemDoubleClicked.connect(self.show_row_details)
        
        # 设置右键菜单
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_results_context_menu)
        
        layout.addWidget(self.results_table)
    
    def show_results_context_menu(self, position):
        """显示搜索结果表格的右键菜单"""
        # 获取当前单元格
        item = self.results_table.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        
        # 复制单元格内容
        copy_cell_action = QAction("复制单元格", self)
        copy_cell_action.triggered.connect(lambda: self.copy_cell_content(item))
        menu.addAction(copy_cell_action)
        
        # 复制整行
        copy_row_action = QAction("复制整行", self)
        copy_row_action.triggered.connect(lambda: self.copy_row_content(item.row()))
        menu.addAction(copy_row_action)
        
        # 复制列内容
        copy_column_action = QAction("复制列名", self)
        copy_column_action.triggered.connect(lambda: self.copy_column_header(item.column()))
        menu.addAction(copy_column_action)
        
        menu.addSeparator()
        
        # 跳转到数据库 - 新增功能
        jump_action = QAction("🔍 跳转到数据库", self)
        jump_action.triggered.connect(lambda: self.jump_to_database_location(item.row()))
        menu.addAction(jump_action)
        
        menu.addSeparator()
        
        # 查看行详情
        detail_action = QAction("查看详情", self)
        detail_action.triggered.connect(lambda: self.show_row_details(item))
        menu.addAction(detail_action)
        
        # 复制数据库路径
        copy_path_action = QAction("复制数据库信息", self)
        copy_path_action.triggered.connect(lambda: self.copy_db_info(item.row()))
        menu.addAction(copy_path_action)
        
        menu.exec(self.results_table.mapToGlobal(position))
    
    def copy_cell_content(self, item):
        """复制单元格内容"""
        if item:
            clipboard = QApplication.clipboard()
            clipboard.setText(item.text())
            self.status_label.setText("已复制单元格内容到剪贴板")
    
    def copy_row_content(self, row):
        """复制整行内容"""
        if row >= 0 and row < self.results_table.rowCount():
            row_data = []
            for col in range(self.results_table.columnCount()):
                item = self.results_table.item(row, col)
                row_data.append(item.text() if item else "")
            
            # 制表符分隔的格式
            row_text = "\t".join(row_data)
            
            clipboard = QApplication.clipboard()
            clipboard.setText(row_text)
            self.status_label.setText("已复制整行内容到剪贴板")
    
    def copy_column_header(self, column):
        """复制列标题"""
        if column >= 0 and column < self.results_table.columnCount():
            header_item = self.results_table.horizontalHeaderItem(column)
            if header_item:
                clipboard = QApplication.clipboard()
                clipboard.setText(header_item.text())
                self.status_label.setText("已复制列名到剪贴板")
    
    def copy_db_info(self, row):
        """复制数据库信息"""
        if row >= 0 and row < len(self.last_results):
            result = self.last_results[row]
            db_info = f"{result.package_name}/{result.parent_dir}/{result.database_name}"
            
            clipboard = QApplication.clipboard()
            clipboard.setText(db_info)
            self.status_label.setText("已复制数据库信息到剪贴板")
    
    def setup_stats_tab(self):
        """设置搜索统计标签页"""
        layout = QVBoxLayout(self.stats_tab)
        
        # 统计信息显示
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        layout.addWidget(self.stats_text)
        
        # 刷新统计按钮
        refresh_stats_btn = QPushButton("刷新统计")
        refresh_stats_btn.clicked.connect(self.update_statistics)
        layout.addWidget(refresh_stats_btn)
    
    def set_database_manager(self, database_manager):
        """设置数据库管理器"""
        self.database_manager = database_manager
    
    def set_log_manager(self, log_manager):
        """设置日志管理器"""
        self.log_manager = log_manager
    
    def on_search_bytes_changed(self):
        """处理搜索字节选项变化"""
        if self.search_bytes_cb.isChecked():
            # 勾选搜索字节时，禁用其他选项
            self.case_sensitive_cb.setEnabled(False)
            self.regex_cb.setEnabled(False)
            self.case_sensitive_cb.setChecked(False)
            self.regex_cb.setChecked(False)
            # 更新搜索框提示
            self.search_input.setPlaceholderText("输入十六进制字节串 (示例: 504b0304)")
        else:
            # 取消勾选时，恢复其他选项
            self.case_sensitive_cb.setEnabled(True)
            self.regex_cb.setEnabled(True)
            # 恢复搜索框提示
            self.search_input.setPlaceholderText("输入要搜索的内容... (正则示例: \\d{11} 匹配11位数字)")
    
    def start_search(self):
        """开始搜索"""
        search_term = self.search_input.text().strip()
        if not search_term:
            QMessageBox.warning(self, "警告", "请输入搜索内容")
            return
        
        if not self.database_manager:
            QMessageBox.warning(self, "警告", "数据库管理器未初始化")
            return
        
        # 如果是字节搜索，验证输入格式
        if self.search_bytes_cb.isChecked():
            # 验证十六进制格式
            import re
            if not re.match(r'^[0-9a-fA-F]+$', search_term):
                QMessageBox.warning(self, "警告", "请输入有效的十六进制字符串 (例如: 504b0304)")
                return
            # 确保是偶数长度（每个字节需要2个十六进制字符）
            if len(search_term) % 2 != 0:
                QMessageBox.warning(self, "警告", "十六进制字符串长度必须是偶数")
                return
        
        # 禁用搜索按钮
        self.search_btn.setEnabled(False)
        
        # 显示进度条
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度
        
        # 清空之前的结果
        self.results_table.setRowCount(0)
        
        # 启动搜索线程
        case_sensitive = self.case_sensitive_cb.isChecked()
        use_regex = self.regex_cb.isChecked()
        search_bytes = self.search_bytes_cb.isChecked()
        
        self.search_thread = SearchThread(
            self.database_manager, search_term, case_sensitive, use_regex, search_bytes
        )
        self.search_thread.search_completed.connect(self.on_search_completed)
        self.search_thread.search_progress.connect(self.on_search_progress)
        self.search_thread.search_error.connect(self.on_search_error)
        self.search_thread.finished.connect(self.on_search_finished)
        self.search_thread.start()
    
    def on_search_completed(self, results):
        """搜索完成"""
        self.last_results = results
        self.all_results = results  # 存储所有结果用于分页
        
        # 更新结果计数
        self.result_count_label.setText(f"搜索结果: {len(results)} 条")
        
        if not results:
            # 没有结果时清空分页
            self.all_results = []
            self.current_page = 1
            self.update_pagination()
        else:
            # 重置到第一页并更新分页显示
            self.current_page = 1
            self.update_pagination()
        
        # 自动保存搜索结果
        if self.auto_save_cb.isChecked() and self.log_manager:
            try:
                log_file = self.log_manager.save_search_results(
                    self.search_input.text(),
                    results,
                    self.case_sensitive_cb.isChecked(),
                    self.regex_cb.isChecked(),
                    self.search_bytes_cb.isChecked()
                )
                self.status_label.setText(f"搜索完成，已保存到: {log_file}")
            except Exception as e:
                self.status_label.setText(f"搜索完成，但保存失败: {str(e)}")
        else:
            self.status_label.setText("搜索完成")
        
        # 更新统计信息
        self.update_statistics()
    
    def on_search_progress(self, message):
        """搜索进度更新"""
        self.status_label.setText(message)
    
    def on_search_error(self, error_message):
        """搜索出错"""
        QMessageBox.critical(self, "搜索错误", f"搜索失败:\n{error_message}")
        self.status_label.setText("搜索失败")
    
    def on_search_finished(self):
        """搜索线程结束"""
        self.progress_bar.setVisible(False)
        self.search_btn.setEnabled(True)
        self.search_thread = None
    
    def show_row_details(self, item):
        """显示行详细信息"""
        row = item.row() if hasattr(item, 'row') else item
        if row < len(self.current_page_results):
            result = self.current_page_results[row]
            
            # 创建详细信息对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("行数据详情")
            dialog.setMinimumSize(600, 400)
            
            layout = QVBoxLayout(dialog)
            
            # 基本信息
            info_text = f"""
包名: {result.package_name}
目录: {result.parent_dir}
数据库: {result.database_name}
表名: {result.table_name}
列名: {result.column_name}
匹配值: {result.match_value}
            """.strip()
            
            info_label = QLabel(info_text)
            info_label.setStyleSheet("font-family: monospace; background-color: #f0f0f0; padding: 10px;")
            layout.addWidget(info_label)
            
            # 完整行数据
            layout.addWidget(QLabel("完整行数据:"))
            data_text = QTextEdit()
            safe_data = safe_json_serialize(result.row_data)
            data_text.setPlainText(json.dumps(safe_data, ensure_ascii=False, indent=2))
            data_text.setReadOnly(True)
            layout.addWidget(data_text)
            
            # 按钮布局
            btn_layout = QHBoxLayout()
            
            # 复制按钮
            copy_btn = QPushButton("复制数据")
            copy_btn.clicked.connect(lambda: self.copy_result_data(result))
            btn_layout.addWidget(copy_btn)
            
            # 关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.close)
            btn_layout.addWidget(close_btn)
            
            layout.addLayout(btn_layout)
            
            dialog.exec()
    
    def copy_result_data(self, result):
        """复制搜索结果数据"""
        safe_data = safe_json_serialize(result.row_data)
        data_text = json.dumps(safe_data, ensure_ascii=False, indent=2)
        
        clipboard = QApplication.clipboard()
        clipboard.setText(data_text)
        self.status_label.setText("已复制行数据到剪贴板")
    
    def clear_results(self):
        """清除搜索结果"""
        self.results_table.setRowCount(0)
        self.last_results = []
        self.result_count_label.setText("搜索结果: 0 条")
        self.status_label.setText("已清除搜索结果")
        self.stats_text.clear()
    
    def export_results(self):
        """导出搜索结果"""
        if not self.last_results:
            QMessageBox.information(self, "提示", "没有搜索结果可导出")
            return
        
        from PySide6.QtWidgets import QFileDialog
        
        # 生成默认文件名
        search_term = self.search_input.text()[:20]  # 限制长度
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"search_{search_term}_{timestamp}.csv"
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出搜索结果", default_filename, "CSV文件 (*.csv)"
        )
        
        if filename:
            try:
                import csv
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    
                    # 写入表头
                    headers = ["包名", "数据库", "匹配内容", "完整行数据"]
                    writer.writerow(headers)
                    
                    # 写入数据
                    for result in self.last_results:
                        safe_data = safe_json_serialize(result.row_data)
                        row = [
                            result.package_name,
                            result.database_name,
                            result.match_value,
                            json.dumps(safe_data, ensure_ascii=False)
                        ]
                        writer.writerow(row)
                
                QMessageBox.information(self, "成功", f"搜索结果已导出到:\n{filename}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")
    
    def save_search_log(self):
        """手动保存搜索日志"""
        if not self.last_results:
            QMessageBox.information(self, "提示", "没有搜索结果可保存")
            return
        
        if not self.log_manager:
            QMessageBox.warning(self, "警告", "日志管理器未初始化")
            return
        
        try:
            log_file = self.log_manager.save_search_results(
                self.search_input.text(),
                self.last_results,
                self.case_sensitive_cb.isChecked(),
                self.regex_cb.isChecked(),
                self.search_bytes_cb.isChecked()
            )
            QMessageBox.information(self, "成功", f"搜索结果已保存到:\n{log_file}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败:\n{str(e)}")
    
    def update_statistics(self):
        """更新搜索统计信息"""
        if not self.last_results:
            self.stats_text.setPlainText("暂无搜索结果")
            return
        
        # 统计各种信息
        package_count = len(set(r.package_name for r in self.last_results))
        db_count = len(set((r.package_name, r.parent_dir, r.database_name) for r in self.last_results))
        table_count = len(set((r.package_name, r.parent_dir, r.database_name, r.table_name) for r in self.last_results))
        
        # 按包名统计
        package_stats = {}
        for result in self.last_results:
            if result.package_name not in package_stats:
                package_stats[result.package_name] = 0
            package_stats[result.package_name] += 1
        
        # 按数据库统计
        db_stats = {}
        for result in self.last_results:
            db_key = f"{result.package_name}/{result.parent_dir}/{result.database_name}"
            if db_key not in db_stats:
                db_stats[db_key] = 0
            db_stats[db_key] += 1
        
        # 生成统计报告
        stats_text = f"""搜索统计报告
================

搜索词: {self.search_input.text()}
区分大小写: {'是' if self.case_sensitive_cb.isChecked() else '否'}
正则表达式: {'是' if self.regex_cb.isChecked() else '否'}
搜索时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

总体统计:
- 匹配结果: {len(self.last_results)} 条
- 涉及包: {package_count} 个
- 涉及数据库: {db_count} 个
- 涉及表: {table_count} 个

按包名统计 (前10):
"""
        
        # 按包名统计的前10
        sorted_packages = sorted(package_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        for pkg, count in sorted_packages:
            stats_text += f"- {pkg}: {count} 条\n"
        
        stats_text += "\n按数据库统计 (前10):\n"
        
        # 按数据库统计的前10
        sorted_dbs = sorted(db_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        for db, count in sorted_dbs:
            stats_text += f"- {db}: {count} 条\n"
        
        self.stats_text.setPlainText(stats_text)
    
    def show_regex_help(self):
        """显示正则表达式帮助"""
        help_text = """
正则表达式搜索帮助

常用正则表达式模式：

基本匹配：
• .          匹配任意单个字符（除换行符）
• \\d         匹配数字 (0-9)
• \\w         匹配字母、数字、下划线
• \\s         匹配空白字符（空格、制表符等）

量词：
• *          匹配0次或多次
• +          匹配1次或多次
• ?          匹配0次或1次
• {n}        匹配恰好n次
• {n,m}      匹配n到m次

实用示例：
• \\d{11}     匹配11位数字（手机号）
• \\d{15,18}  匹配15-18位数字（身份证）
• \\w+@\\w+   匹配邮箱格式
• ^\\d+$      匹配纯数字字符串
• .*keyword.* 匹配包含keyword的字符串

字符类：
• [abc]      匹配a、b或c中的任意一个
• [a-z]      匹配小写字母
• [A-Z]      匹配大写字母
• [0-9]      匹配数字（等同于\\d）
• [^abc]     匹配除a、b、c之外的字符

锚点：
• ^          匹配字符串开头
• $          匹配字符串结尾

注意：
• 使用正则表达式搜索会比普通搜索慢一些
• 错误的正则表达式会导致搜索失败
• 可以配合"区分大小写"选项使用
        """
        
        dialog = QDialog(self)
        dialog.setWindowTitle("正则表达式帮助")
        dialog.setMinimumSize(500, 600)
        
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setPlainText(help_text.strip())
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Consolas", 10))
        layout.addWidget(text_edit)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def jump_to_database_location(self, row):
        """跳转到主窗口中对应的数据库位置"""
        try:
            print(f"尝试跳转，行索引: {row}, 当前页结果数: {len(self.current_page_results)}")
            
            if row >= 0 and row < len(self.current_page_results):
                result = self.current_page_results[row]
                print(f"跳转目标: {result.package_name}/{result.parent_dir}/{result.database_name}/{result.table_name}")
                
                # 发射跳转信号
                self.jump_to_database.emit(
                    result.package_name,
                    result.parent_dir,
                    result.database_name,
                    result.table_name
                )
                
                print("跳转信号已发射")
                
                # 关闭搜索对话框
                self.accept()
                
                print("搜索对话框已关闭")
            else:
                print(f"无效的行索引: {row}")
                QMessageBox.warning(self, "跳转错误", "搜索结果索引无效")
                
        except Exception as e:
            print(f"跳转过程中发生异常: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "跳转错误", f"跳转功能发生错误:\n{str(e)}")
    
    def on_page_size_changed(self):
        """页面大小改变处理"""
        try:
            new_page_size = int(self.page_size_combo.currentText())
            if new_page_size != self.page_size:
                self.page_size = new_page_size
                self.current_page = 1  # 重置到第一页
                self.update_pagination()
        except ValueError:
            pass
    
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self.update_pagination()
    
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_pagination()
    
    def jump_to_page(self):
        """跳转到指定页面"""
        try:
            page_num = int(self.page_input.text())
            if 1 <= page_num <= self.total_pages:
                self.current_page = page_num
                self.update_pagination()
                self.page_input.clear()
            else:
                QMessageBox.warning(self, "页码错误", f"页码必须在 1 到 {self.total_pages} 之间")
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的页码数字")
    
    def update_pagination(self):
        """更新分页显示"""
        if not self.all_results:
            self.current_page = 1
            self.total_pages = 1
            self.current_page_results = []
        else:
            # 计算总页数
            self.total_pages = max(1, (len(self.all_results) + self.page_size - 1) // self.page_size)
            
            # 确保当前页在有效范围内
            self.current_page = max(1, min(self.current_page, self.total_pages))
            
            # 计算当前页的数据范围
            start_index = (self.current_page - 1) * self.page_size
            end_index = min(start_index + self.page_size, len(self.all_results))
            self.current_page_results = self.all_results[start_index:end_index]
        
        # 更新UI显示
        self.display_current_page_results()
        self.update_pagination_controls()
    
    def display_current_page_results(self):
        """显示当前页的搜索结果"""
        self.results_table.setRowCount(0)
        
        if not self.current_page_results:
            if not self.all_results:
                # 显示无结果
                self.results_table.setRowCount(1)
                self.results_table.setItem(0, 0, QTableWidgetItem("未找到匹配结果"))
                for i in range(1, 4):
                    self.results_table.setItem(0, i, QTableWidgetItem(""))
            return
        
        # 设置表格行数
        self.results_table.setRowCount(len(self.current_page_results))
        
        # 填充表格数据
        for i, result in enumerate(self.current_page_results):
            # 包名
            self.results_table.setItem(i, 0, QTableWidgetItem(result.package_name))
            
            # 数据库
            self.results_table.setItem(i, 1, QTableWidgetItem(result.database_name))
            
            # 匹配内容
            match_text = str(result.match_value)[:100]  # 限制长度
            if len(str(result.match_value)) > 100:
                match_text += "..."
            match_item = QTableWidgetItem(match_text)
            match_item.setToolTip(str(result.match_value))  # 完整内容作为提示
            self.results_table.setItem(i, 2, match_item)
            
            # 行数据预览
            safe_row_data = safe_json_serialize(result.row_data)
            row_preview = str(safe_row_data)[:100]
            if len(str(safe_row_data)) > 100:
                row_preview += "..."
            preview_item = QTableWidgetItem(row_preview)
            preview_item.setToolTip(json.dumps(safe_row_data, ensure_ascii=False, indent=2))
            self.results_table.setItem(i, 3, preview_item)
        
        # 调整列宽
        self.results_table.resizeColumnsToContents()
    
    def update_pagination_controls(self):
        """更新分页控件状态"""
        self.page_label.setText(f"第 {self.current_page} 页 / 共 {self.total_pages} 页 (总计 {len(self.all_results)} 条)")
        
        # 更新按钮状态
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < self.total_pages)
        
        # 如果没有结果，禁用分页控件
        has_results = len(self.all_results) > 0
        self.page_size_combo.setEnabled(has_results)
        self.page_input.setEnabled(has_results)
 