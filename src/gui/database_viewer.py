# -*- coding: utf-8 -*-
"""
数据库查看器组件
显示数据库表内容，支持表切换
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QTabWidget,
    QPushButton, QLineEdit, QComboBox, QSpinBox,
    QMessageBox, QProgressBar, QCheckBox, QMenu,
    QDialog, QTextEdit, QScrollArea, QApplication,
    QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtGui import QFont, QAction, QWheelEvent, QColor

from ..core.database_manager import format_field_value, detect_file_type


class CellDetailDialog(QDialog):
    """单元格详细内容查看对话框"""
    
    def __init__(self, content, parent=None):
        super().__init__(parent)
        self.content = content
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("单元格内容详情")
        self.setModal(True)
        
        # 设置对话框尺寸
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        
        # 内容显示区域
        self.text_edit = QTextEdit()
        
        # 根据内容类型设置显示
        if isinstance(self.content, bytes):
            # 检测是否为文件
            file_type = detect_file_type(self.content)
            if file_type:
                self.text_edit.setPlainText(f"检测到文件类型: {file_type}\n文件大小: {len(self.content)} 字节\n\n点击'打开文件'按钮查看文件内容")
            else:
                # 尝试解码显示
                try:
                    decoded = self.content.decode('utf-8', errors='replace')
                    self.text_edit.setPlainText(decoded)
                except:
                    self.text_edit.setPlainText(f"二进制数据 ({len(self.content)} 字节):\n{self.content.hex()}")
        else:
            self.text_edit.setPlainText(str(self.content) if self.content is not None else "")
        
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        layout.addWidget(self.text_edit)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        # 如果是文件，添加打开文件按钮
        if isinstance(self.content, bytes):
            file_type = detect_file_type(self.content)
            if file_type:
                open_file_btn = QPushButton("打开文件")
                open_file_btn.clicked.connect(self.open_file)
                button_layout.addWidget(open_file_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    

    
    def open_file(self):
        """打开文件"""
        if not isinstance(self.content, bytes):
            return
        
        file_type = detect_file_type(self.content)
        if not file_type:
            QMessageBox.warning(self, "警告", "无法识别文件类型")
            return
        
        try:
            # 创建临时文件
            temp_dir = tempfile.gettempdir()
            temp_filename = f"db_extract_{hash(self.content) % 1000000}{file_type}"
            temp_path = os.path.join(temp_dir, temp_filename)
            
            # 写入文件
            with open(temp_path, 'wb') as f:
                f.write(self.content)
            
            # 使用系统默认程序打开
            if sys.platform.startswith('win'):
                os.startfile(temp_path)
            elif sys.platform.startswith('darwin'):  # macOS
                subprocess.run(['open', temp_path])
            else:  # Linux
                subprocess.run(['xdg-open', temp_path])
            
            QMessageBox.information(self, "成功", f"文件已保存到临时目录并打开:\n{temp_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开文件失败: {str(e)}")


class DataLoadThread(QThread):
    """数据加载线程"""
    data_loaded = Signal(list, list)  # columns, rows
    error_occurred = Signal(str)
    progress_updated = Signal(int)  # 进度百分比
    
    def __init__(self, database_manager, package_name, parent_dir, db_name, table_name, limit, offset):
        super().__init__()
        self.database_manager = database_manager
        self.package_name = package_name
        self.parent_dir = parent_dir
        self.db_name = db_name
        self.table_name = table_name
        self.limit = limit
        self.offset = offset
    
    def run(self):
        try:
            # 发送进度更新
            self.progress_updated.emit(10)  # 开始加载
            
            print(f"[线程] 开始加载数据: {self.package_name}/{self.parent_dir}/{self.db_name}/{self.table_name}")
            
            # 获取表结构信息
            self.progress_updated.emit(30)  # 获取表结构
            
            # 获取数据
            self.progress_updated.emit(50)  # 开始获取数据
            
            # 添加超时保护
            import signal
            def timeout_handler(signum, frame):
                raise TimeoutError("数据加载超时")
            
            # 在Windows上不支持SIGALRM，所以使用其他方法
            try:
                columns, rows = self.database_manager.get_table_data(
                    self.package_name, self.parent_dir, self.db_name, 
                    self.table_name, self.limit, self.offset
                )
            except Exception as e:
                print(f"[线程] 数据获取失败: {e}")
                self.error_occurred.emit(f"数据获取失败: {str(e)}")
                return
            
            self.progress_updated.emit(80)  # 数据获取完成
            
            print(f"[线程] 数据获取成功: {len(columns)} 列, {len(rows)} 行")
            
            # 处理数据
            self.progress_updated.emit(90)  # 处理数据
            
            self.progress_updated.emit(100)  # 完成
            self.data_loaded.emit(columns, rows)
            
        except Exception as e:
            print(f"[线程] 加载过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"加载数据时发生错误: {str(e)}")


class TableComboBox(QComboBox):
    """支持滚轮切换的表选择下拉框"""
    
    def __init__(self):
        super().__init__()
        # 设置样式修复悬停颜色问题
        self.setStyleSheet("""
            QComboBox {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
                min-height: 20px;
                color: #333;
            }
            QComboBox:hover {
                border-color: #4a90e2;
                background-color: #f8f9fa;
            }
            QComboBox:focus {
                border-color: #4a90e2;
                outline: none;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #666;
                width: 0;
                height: 0;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                border: 1px solid #ccc;
                selection-background-color: #4a90e2;
                selection-color: white;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px;
                border: none;
                color: #333;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #e8f4fd;
                color: #333;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #4a90e2;
                color: white;
            }
        """)
    
    def wheelEvent(self, event: QWheelEvent):
        """处理滚轮事件"""
        if self.count() == 0:
            return
        
        current_index = self.currentIndex()
        delta = event.angleDelta().y()
        
        if delta > 0:  # 向上滚动
            new_index = max(0, current_index - 1)
        else:  # 向下滚动
            new_index = min(self.count() - 1, current_index + 1)
        
        if new_index != current_index:
            self.setCurrentIndex(new_index)
        
        event.accept()


class CustomTableWidget(QTableWidget):
    """自定义表格组件，支持双击查看详情"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.database_viewer = parent
        self.original_data = {}  # 存储原始数据 {(row, col): original_value}
        
    def wheelEvent(self, event: QWheelEvent):
        """处理滚轮事件，支持Ctrl+滚轮缩放"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+滚轮：调整字体大小
            current_font = self.font()
            current_size = current_font.pointSize()
            
            if event.angleDelta().y() > 0:  # 向上滚动，放大
                new_size = min(current_size + 1, 20)
            else:  # 向下滚动，缩小
                new_size = max(current_size - 1, 8)
            
            if new_size != current_size:
                current_font.setPointSize(new_size)
                self.setFont(current_font)
            
            event.accept()
        else:
            # 普通滚轮：滚动表格
            super().wheelEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """处理双击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if item and self.database_viewer:
                row = item.row()
                col = item.column()
                
                # 获取原始数据
                original_value = self.original_data.get((row, col))
                if original_value is not None:
                    # 检查是否为文件类型
                    if isinstance(original_value, bytes):
                        file_type = detect_file_type(original_value)
                        if file_type:
                            # 是文件类型，直接打开文件
                            self._open_file_directly(original_value, file_type)
                            return
                    
                    # 不是文件类型，显示详细内容对话框
                    dialog = CellDetailDialog(original_value, self)
                    dialog.exec()
                    return
        
        super().mouseDoubleClickEvent(event)
    
    def _open_file_directly(self, file_data: bytes, file_type: str):
        """直接打开文件"""
        try:
            import tempfile
            import subprocess
            import sys
            import os
            
            # 创建临时文件
            temp_dir = tempfile.gettempdir()
            temp_filename = f"db_extract_{hash(file_data) % 1000000}{file_type}"
            temp_path = os.path.join(temp_dir, temp_filename)
            
            # 写入文件
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            # 使用系统默认程序打开
            if sys.platform.startswith('win'):
                os.startfile(temp_path)
            elif sys.platform.startswith('darwin'):  # macOS
                subprocess.run(['open', temp_path])
            else:  # Linux
                subprocess.run(['xdg-open', temp_path])
            
            print(f"文件已打开: {temp_path}")
            
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开文件失败: {str(e)}")
    
    def set_original_data(self, row: int, col: int, value):
        """设置原始数据"""
        self.original_data[(row, col)] = value
    
    def clear_original_data(self):
        """清空原始数据"""
        self.original_data.clear()


class DatabaseViewerWidget(QWidget):
    """数据库查看器组件"""
    
    def __init__(self):
        super().__init__()
        self.database_manager = None
        self.current_package = ""
        self.current_parent_dir = ""
        self.current_db = ""
        self.current_table = ""
        self.current_columns = []
        self.current_page = 1
        self.page_size = 50  # 默认50条一页
        self.total_rows = 0
        self.total_pages = 1
        self.load_thread = None
        self.load_timeout_timer = None
        
        self.init_ui()
    
    def __del__(self):
        """析构函数，确保线程清理"""
        try:
            self.cleanup_thread()
        except RuntimeError:
            # C++对象已被删除，忽略这个错误
            pass
        except Exception as e:
            print(f"[清理] 析构函数出错: {e}")
    
    def cleanup_thread(self):
        """清理线程"""
        try:
            if hasattr(self, 'load_thread') and self.load_thread and self.load_thread.isRunning():
                print("[清理] 等待数据加载线程结束...")
                self.load_thread.terminate()
                if not self.load_thread.wait(1000):  # 减少等待时间到1秒
                    print("[清理] 线程未能正常结束")
                self.load_thread = None
            
            if hasattr(self, 'load_timeout_timer') and self.load_timeout_timer:
                self.load_timeout_timer.stop()
                self.load_timeout_timer = None
        except RuntimeError:
            # C++对象已被删除，忽略这个错误
            print("[清理] C++对象已删除，跳过清理")
        except Exception as e:
            print(f"[清理] 清理线程时出错: {e}")
    


    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 顶部控制面板
        top_control_panel = QWidget()
        top_control_layout = QHBoxLayout(top_control_panel)
        
        # 表选择
        top_control_layout.addWidget(QLabel("选择表:"))
        self.table_combo = TableComboBox()
        self.table_combo.currentTextChanged.connect(self.on_table_changed)
        top_control_layout.addWidget(self.table_combo)
        
        top_control_layout.addStretch()
        
        # 搜索框
        top_control_layout.addWidget(QLabel("筛选:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词筛选...")
        self.search_input.textChanged.connect(self.filter_table_data)
        top_control_layout.addWidget(self.search_input)
        
        clear_search_btn = QPushButton("清除")
        clear_search_btn.clicked.connect(self.clear_search)
        top_control_layout.addWidget(clear_search_btn)
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_data)
        top_control_layout.addWidget(refresh_btn)
        
        # 导出按钮
        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self.export_current_data)
        top_control_layout.addWidget(export_btn)
        
        layout.addWidget(top_control_panel)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 数据表格
        self.table_widget = CustomTableWidget(self)
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        # 设置表格样式
        self.table_widget.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ccc;
                gridline-color: #e0e0e0;
                selection-background-color: #4a90e2;
                selection-color: white;
            }
            QTableWidget::item {
                padding: 4px;
                border: none;
                color: #333;
            }
            QTableWidget::item:hover {
                background-color: #e8f4fd;
                color: #333;
            }
            QTableWidget::item:selected {
                background-color: #4a90e2;
                color: white;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
                padding: 6px;
                font-weight: bold;
                color: #333;
            }
            QHeaderView::section:hover {
                background-color: #e8f4fd;
            }
        """)
        
        # 设置表格滚动模式为像素级滚动，而不是按项目滚动
        self.table_widget.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        
        # 设置水平滚动条为像素级平滑滚动
        horizontal_scroll = self.table_widget.horizontalScrollBar()
        horizontal_scroll.setSingleStep(3)  # 设置单步滚动为3像素（更平滑）
        horizontal_scroll.setPageStep(50)   # 设置页面滚动步长
        
        # 设置垂直滚动条也为平滑滚动
        vertical_scroll = self.table_widget.verticalScrollBar()
        vertical_scroll.setSingleStep(3)    # 设置单步滚动为3像素
        vertical_scroll.setPageStep(50)     # 设置页面滚动步长
        
        layout.addWidget(self.table_widget)
        
        # 底部分页控制面板
        bottom_control_panel = QWidget()
        bottom_control_layout = QHBoxLayout(bottom_control_panel)
        
        # 分页控制
        bottom_control_layout.addWidget(QLabel("每页:"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["10", "20", "50", "100", "200"])
        self.page_size_combo.setCurrentText("50")
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)
        bottom_control_layout.addWidget(self.page_size_combo)
        
        bottom_control_layout.addSpacing(20)
        
        # 页码控制
        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        bottom_control_layout.addWidget(self.prev_btn)
        
        self.page_label = QLabel("第 1 页 / 共 1 页")
        bottom_control_layout.addWidget(self.page_label)
        
        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self.next_page)
        bottom_control_layout.addWidget(self.next_btn)
        
        bottom_control_layout.addSpacing(20)
        
        # 跳转页面
        bottom_control_layout.addWidget(QLabel("跳转:"))
        self.jump_page_input = QLineEdit()
        self.jump_page_input.setMaximumWidth(60)
        self.jump_page_input.setPlaceholderText("页码")
        self.jump_page_input.returnPressed.connect(self.jump_to_page)
        bottom_control_layout.addWidget(self.jump_page_input)
        
        jump_btn = QPushButton("跳转")
        jump_btn.clicked.connect(self.jump_to_page)
        bottom_control_layout.addWidget(jump_btn)
        
        bottom_control_layout.addStretch()
        
        # 状态显示
        self.status_label = QLabel("未选择数据库")
        bottom_control_layout.addWidget(self.status_label)
        
        layout.addWidget(bottom_control_panel)
    
    def show_context_menu(self, position):
        """显示右键菜单"""
        # 获取当前单元格
        item = self.table_widget.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        
        # 获取原始数据以判断是否为二进制
        row = item.row()
        col = item.column()
        original_value = self.table_widget.original_data.get((row, col))
        
        # 复制单元格内容
        copy_cell_action = QAction("复制单元格", self)
        copy_cell_action.triggered.connect(lambda: self.copy_cell_content(item))
        menu.addAction(copy_cell_action)
        
        # 如果是二进制数据，添加复制十六进制内容选项
        if isinstance(original_value, bytes):
            copy_hex_action = QAction("复制十六进制内容", self)
            copy_hex_action.triggered.connect(lambda: self.copy_hex_content(original_value))
            menu.addAction(copy_hex_action)
        
        # 复制整行
        copy_row_action = QAction("复制整行", self)
        copy_row_action.triggered.connect(lambda: self.copy_row_content(item.row()))
        menu.addAction(copy_row_action)
        
        # 复制列内容
        copy_column_action = QAction("复制列名", self)
        copy_column_action.triggered.connect(lambda: self.copy_column_header(item.column()))
        menu.addAction(copy_column_action)
        
        menu.addSeparator()
        
        # 显示单元格详情
        detail_action = QAction("查看详情", self)
        detail_action.triggered.connect(lambda: self.show_cell_detail(item))
        menu.addAction(detail_action)
        
        menu.exec(self.table_widget.mapToGlobal(position))
    
    def copy_cell_content(self, item):
        """复制单元格内容"""
        if item:
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(item.text())
            self.status_label.setText("已复制单元格内容到剪贴板")
    
    def copy_hex_content(self, data):
        """复制二进制数据的十六进制表示"""
        if isinstance(data, bytes):
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            hex_string = data.hex().upper()
            # 格式化为更易读的格式，每两个字符加一个空格
            formatted_hex = ' '.join(hex_string[i:i+2] for i in range(0, len(hex_string), 2))
            clipboard.setText(formatted_hex)
            self.status_label.setText("已复制十六进制内容到剪贴板")
    
    def copy_row_content(self, row):
        """复制整行内容"""
        if row >= 0 and row < self.table_widget.rowCount():
            row_data = []
            for col in range(self.table_widget.columnCount()):
                item = self.table_widget.item(row, col)
                row_data.append(item.text() if item else "")
            
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText("\t".join(row_data))
            self.status_label.setText("已复制整行内容到剪贴板")
    
    def copy_column_header(self, column):
        """复制列标题"""
        if column >= 0 and column < self.table_widget.columnCount():
            header = self.table_widget.horizontalHeaderItem(column)
            if header:
                from PySide6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(header.text())
                self.status_label.setText("已复制列名到剪贴板")
    
    def show_cell_detail(self, item):
        """显示单元格详细信息"""
        if not item:
            return
        
        row = item.row()
        col = item.column()
        value = item.text()
        column_name = self.table_widget.horizontalHeaderItem(col).text() if self.table_widget.horizontalHeaderItem(col) else f"列{col}"
        
        # 创建详情对话框
        detail_text = f"""
表: {self.current_table}
行: {row + 1}
列: {column_name}
值: {value}
数据类型: {type(value).__name__}
字符长度: {len(str(value))}
        """.strip()
        
        QMessageBox.information(self, "单元格详情", detail_text)
    
    def set_database_manager(self, database_manager):
        """设置数据库管理器"""
        self.database_manager = database_manager
    
    def show_database_tables(self, package_name: str, parent_dir: str, db_name: str):
        """显示数据库的表列表"""
        self.current_package = package_name
        self.current_parent_dir = parent_dir
        self.current_db = db_name
        self.current_table = ""
        self.current_columns = []
        self.current_page = 1
        self.page_size = 50  # 默认50条一页
        self.total_rows = 0
        self.total_pages = 1
        
        # 更新信息标签
        self.status_label.setText(f"数据库: {package_name}/{parent_dir}/{db_name}")
        
        # 获取表列表
        try:
            if (self.database_manager and 
                package_name in self.database_manager.databases and
                parent_dir in self.database_manager.databases[package_name] and
                db_name in self.database_manager.databases[package_name][parent_dir]):
                
                db_info = self.database_manager.databases[package_name][parent_dir][db_name]
                self.current_table = db_info.tables[0] if db_info.tables else ""
                self.current_columns = []  # 移除错误的columns属性访问
                
                # 更新表选择下拉框
                self.table_combo.clear()
                if db_info.tables:
                    self.table_combo.addItems(db_info.tables)
                    # 自动选择第一个表
                    if len(db_info.tables) > 0:
                        self.table_combo.setCurrentIndex(0)
                else:
                    self.table_combo.addItem("(无表)")
                    self.clear_table_display()
            else:
                self.current_table = ""
                self.current_columns = []
                self.table_combo.clear()
                self.table_combo.addItem("(无表)")
                self.clear_table_display()
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"获取表列表失败: {str(e)}")
            self.current_table = ""
            self.current_columns = []
            self.clear_table_display()
    
    def on_table_changed(self, table_name):
        """表选择改变时的处理"""
        if (table_name and table_name != "(无表)" and 
            self.database_manager and self.current_package and 
            self.current_package in self.database_manager.databases and
            self.current_parent_dir in self.database_manager.databases[self.current_package] and
            self.current_db in self.database_manager.databases[self.current_package][self.current_parent_dir]):
            
            db_info = self.database_manager.databases[self.current_package][self.current_parent_dir][self.current_db]
            if table_name in db_info.tables:
                self.current_table = table_name
                self.current_page = 1
                self.load_data()
            else:
                self.clear_table_display()
        else:
            self.clear_table_display()
    
    def clear_table_display(self):
        """清空表显示"""
        self.table_widget.clear()
        self.table_widget.setRowCount(0)
        self.table_widget.setColumnCount(0)
        self.status_label.setText("无数据")
        self.update_pagination_buttons()
    
    def load_data(self):
        """加载表格数据"""
        if not self.current_table or not self.database_manager:
            return
        
        print(f"[线程] 开始加载数据: {self.current_package}/{self.current_parent_dir}/{self.current_db}/{self.current_table}")
        
        # 显示加载状态
        self.status_label.setText(f"正在加载 {self.current_table}...")
        self.progress_bar.setVisible(True)
        
        # 创建新的数据加载线程
        self.load_thread = DataLoadThread(
            self.database_manager,
            self.current_package,
            self.current_parent_dir,
            self.current_db,
            self.current_table,
            self.page_size,
            (self.current_page - 1) * self.page_size
        )
        
        # 连接信号
        self.load_thread.data_loaded.connect(self.on_data_loaded)
        self.load_thread.error_occurred.connect(self.on_error_occurred)
        self.load_thread.finished.connect(self.on_thread_finished)
        self.load_thread.progress_updated.connect(self.on_progress_updated)
        
        # 启动线程
        self.load_thread.start()
    
    def on_data_loaded(self, columns, rows):
        """数据加载完成"""
        try:
            # 清空原始数据
            self.table_widget.clear_original_data()
            
            # 设置表格
            self.table_widget.setRowCount(len(rows))
            self.table_widget.setColumnCount(len(columns))
            self.table_widget.setHorizontalHeaderLabels(columns)
            
            # 填充数据
            for row_idx, row_data in enumerate(rows):
                for col_idx, cell_data in enumerate(row_data):
                    # 存储原始数据
                    self.table_widget.set_original_data(row_idx, col_idx, cell_data)
                    
                    # 格式化显示值
                    display_text, is_large_field, file_type = format_field_value(cell_data)
                    
                    # 创建表格项
                    item = QTableWidgetItem(display_text)
                    
                    # 为大字段或文件设置特殊样式
                    if is_large_field:
                        if file_type:
                            # 文件类型，设置蓝色背景
                            item.setBackground(QColor(230, 240, 255))  # 浅蓝色
                        else:
                            # 大字段，设置黄色背景
                            item.setBackground(QColor(255, 255, 230))  # 浅黄色
                    
                    self.table_widget.setItem(row_idx, col_idx, item)
            
            # 调整列宽
            self.table_widget.resizeColumnsToContents()
            
            # 获取表的总行数（用于分页计算）
            if self.database_manager and self.current_package and self.current_table:
                try:
                    table_info = self.database_manager.get_table_info(
                        self.current_package, self.current_parent_dir, 
                        self.current_db, self.current_table
                    )
                    if table_info:
                        self.total_rows = table_info.row_count
                    else:
                        self.total_rows = len(rows)
                except:
                    self.total_rows = len(rows)
            else:
                self.total_rows = len(rows)
            
            # 计算总页数
            self.total_pages = max(1, (self.total_rows + self.page_size - 1) // self.page_size)
            self.page_label.setText(f"第 {self.current_page} 页 / 共 {self.total_pages} 页")
            self.status_label.setText(f"当前页显示 {len(rows)} 行，总计 {self.total_rows} 行数据")
            
            # 更新分页按钮
            self.update_pagination_buttons()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"显示数据时出错: {str(e)}")
    
    def on_error_occurred(self, error_message):
        """处理错误"""
        QMessageBox.critical(self, "加载数据失败", error_message)
        self.status_label.setText("加载数据失败")
    
    def on_thread_finished(self):
        """线程完成后的清理"""
        print("数据加载线程已完成")
        
        # 隐藏进度条
        self.progress_bar.setVisible(False)
    
    def on_progress_updated(self, percent):
        """处理进度更新"""
        self.progress_bar.setValue(percent)
    
    def on_page_size_changed(self, new_size):
        """页面大小改变"""
        try:
            self.page_size = int(new_size)
            self.current_page = 1
            self.load_data()
        except ValueError:
            pass
    
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page = max(1, self.current_page - 1)
            self.load_data()
    
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages:
            self.current_page = min(self.total_pages, self.current_page + 1)
            self.load_data()
    
    def jump_to_page(self):
        """跳转到指定页面"""
        try:
            new_page = int(self.jump_page_input.text())
            if 1 <= new_page <= self.total_pages:
                self.current_page = new_page
                self.load_data()
            else:
                QMessageBox.warning(self, "警告", "页码超出范围")
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的页码")
    
    def update_pagination_buttons(self):
        """更新分页按钮状态"""
        # 上一页按钮
        self.prev_btn.setEnabled(self.current_page > 1)
        
        # 下一页按钮
        self.next_btn.setEnabled(self.current_page < self.total_pages)
    
    def refresh_data(self):
        """刷新当前数据"""
        if self.current_table:
            self.load_data()
    
    def filter_table_data(self):
        """过滤表格数据"""
        search_text = self.search_input.text().strip()
        
        if not search_text:
            # 显示所有行
            for row in range(self.table_widget.rowCount()):
                self.table_widget.setRowHidden(row, False)
            return
        
        # 根据搜索文本过滤行
        for row in range(self.table_widget.rowCount()):
            row_visible = False
            
            # 检查每一列
            for col in range(self.table_widget.columnCount()):
                item = self.table_widget.item(row, col)
                if item:
                    cell_text = item.text()
                    if search_text.lower() in cell_text.lower():
                        row_visible = True
                        break
            
            self.table_widget.setRowHidden(row, not row_visible)
    
    def clear_search(self):
        """清除搜索"""
        self.search_input.clear()
        # 显示所有行
        for row in range(self.table_widget.rowCount()):
            self.table_widget.setRowHidden(row, False)
    
    def get_current_table_info(self):
        """获取当前表信息"""
        return {
            'package': self.current_package,
            'parent_dir': self.current_parent_dir,
            'database': self.current_db,
            'table': self.current_table
        }
    
    def export_current_data(self):
        """导出当前表数据"""
        if not self.current_table or self.table_widget.rowCount() == 0:
            QMessageBox.information(self, "提示", "当前没有数据可导出")
            return
        
        from PySide6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出数据", f"{self.current_table}.csv", "CSV文件 (*.csv)"
        )
        
        if filename:
            try:
                import csv
                with open(filename, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    
                    # 写入表头
                    headers = []
                    for col in range(self.table_widget.columnCount()):
                        headers.append(self.table_widget.horizontalHeaderItem(col).text())
                    writer.writerow(headers)
                    
                    # 写入数据行
                    for row in range(self.table_widget.rowCount()):
                        if not self.table_widget.isRowHidden(row):  # 只导出可见行
                            row_data = []
                            for col in range(self.table_widget.columnCount()):
                                item = self.table_widget.item(row, col)
                                row_data.append(item.text() if item else "")
                            writer.writerow(row_data)
                
                QMessageBox.information(self, "成功", f"数据已导出到:\n{filename}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")
    
    def select_and_show_table(self, table_name):
        """选择并显示指定的表"""
        try:
            if (self.database_manager and self.current_package and 
                self.current_package in self.database_manager.databases and
                self.current_parent_dir in self.database_manager.databases[self.current_package] and
                self.current_db in self.database_manager.databases[self.current_package][self.current_parent_dir]):
                
                db_info = self.database_manager.databases[self.current_package][self.current_parent_dir][self.current_db]
                if table_name in db_info.tables:
                    # 在下拉框中选择对应的表
                    self.table_combo.setCurrentText(table_name)
                    
                    print(f"已选择表: {table_name}")
                    return True
                else:
                    print(f"表 {table_name} 不在可用表列表中")
                    return False
            else:
                print("数据库信息不完整")
                return False
                
        except Exception as e:
            print(f"选择表时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def stop_loading(self):
        """停止加载数据"""
        try:
            if hasattr(self, 'load_thread') and self.load_thread and self.load_thread.isRunning():
                print("正在停止数据加载线程...")
                try:
                    # 请求线程中断
                    self.load_thread.requestInterruption()
                    
                    # 强制终止线程
                    self.load_thread.terminate()
                    
                    # 不等待线程结束，直接清理
                    print("数据加载线程已终止")
                    
                except Exception as e:
                    print(f"停止线程时出错: {e}")
            
            # 立即更新UI状态
            if hasattr(self, 'progress_bar') and self.progress_bar:
                self.progress_bar.setVisible(False)
            if hasattr(self, 'status_label') and self.status_label:
                self.status_label.setText("已停止加载")
            
            # 停止超时定时器
            if hasattr(self, 'load_timeout_timer') and self.load_timeout_timer:
                self.load_timeout_timer.stop()
                
        except RuntimeError:
            # C++对象已被删除，忽略这个错误
            print("[停止加载] C++对象已删除，跳过清理")
        except Exception as e:
            print(f"[停止加载] 停止加载时出错: {e}")
    
    def on_load_timeout(self):
        """加载超时处理"""
        print("数据加载超时，强制停止...")
        try:
            if hasattr(self, 'load_thread') and self.load_thread and self.load_thread.isRunning():
                self.load_thread.terminate()
                if not self.load_thread.wait(1000):  # 减少等待时间到1秒
                    print("超时线程未能正常结束")
            
            if hasattr(self, 'progress_bar') and self.progress_bar:
                self.progress_bar.setVisible(False)
            if hasattr(self, 'status_label') and self.status_label:
                self.status_label.setText("加载超时，已停止")
            
            QMessageBox.warning(self, "加载超时", 
                               "数据加载时间过长，已自动停止。\n"
                               "这可能是由于数据库文件被锁定或查询复杂度过高。\n"
                               "请尝试刷新或选择其他表。")
        except RuntimeError:
            # C++对象已被删除，忽略这个错误
            print("[超时处理] C++对象已删除，跳过处理")
        except Exception as e:
            print(f"[超时处理] 处理超时时出错: {e}") 