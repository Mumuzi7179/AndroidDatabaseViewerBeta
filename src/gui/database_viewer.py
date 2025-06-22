# -*- coding: utf-8 -*-
"""
数据库查看器组件
显示数据库表内容，支持表切换
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QTabWidget,
    QPushButton, QLineEdit, QComboBox, QSpinBox,
    QMessageBox, QProgressBar, QCheckBox, QMenu,
    QDialog, QTextEdit, QScrollArea, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal, QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtGui import QFont, QAction, QWheelEvent


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
    """支持横向滚轮滚动和双击查看详情的表格控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def wheelEvent(self, event: QWheelEvent):
        """处理滚轮事件 - 支持横向滚动"""
        modifiers = event.modifiers()
        delta = event.angleDelta()
        
        # Ctrl+滚轮 或者 Shift+滚轮 进行横向滚动
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            # 横向滚动
            horizontal_scroll = self.horizontalScrollBar()
            if horizontal_scroll:
                # 获取当前滚动位置
                current_value = horizontal_scroll.value()
                # 计算滚动步长（平滑滚动）
                scroll_step = delta.y() // 8  # 减小步长让滚动更平滑
                new_value = current_value - scroll_step
                
                # 创建平滑滚动动画
                if not hasattr(self, '_scroll_animation'):
                    self._scroll_animation = QPropertyAnimation(horizontal_scroll, b"value")
                    self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
                
                self._scroll_animation.stop()
                self._scroll_animation.setDuration(200)  # 动画持续时间
                self._scroll_animation.setStartValue(current_value)
                self._scroll_animation.setEndValue(max(0, min(horizontal_scroll.maximum(), new_value)))
                self._scroll_animation.start()
                
            event.accept()
        else:
            # 默认纵向滚动
            super().wheelEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """处理双击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if item:
                # 显示单元格详细内容
                content = item.text()
                dialog = CellDetailDialog(content, self.parent())
                dialog.exec()
                return
        
        super().mouseDoubleClickEvent(event)


class DatabaseViewerWidget(QWidget):
    """数据库查看器组件"""
    
    def __init__(self):
        super().__init__()
        self.database_manager = None
        self.current_package = ""
        self.current_parent_dir = ""
        self.current_db = ""
        self.current_table = ""
        self.current_offset = 0
        self.page_size = 1000
        self.data_thread = None
        self.available_tables = []
        
        # 添加超时定时器
        self.load_timeout_timer = QTimer()
        self.load_timeout_timer.setSingleShot(True)
        self.load_timeout_timer.timeout.connect(self.on_load_timeout)
        
        self.init_ui()
    
    def __del__(self):
        """析构方法，确保线程被正确清理"""
        self.cleanup_thread()
    
    def cleanup_thread(self):
        """清理数据加载线程"""
        if self.data_thread:
            self.force_cleanup_thread()
        
        # 重置UI状态
        self.progress_bar.setVisible(False)
        if hasattr(self, 'status_label'):
            self.status_label.setText("准备就绪")
    
    def force_cleanup_thread(self):
        """强制清理数据加载线程"""
        if self.data_thread:
            print("强制清理数据加载线程...")
            # 断开所有信号连接
            try:
                self.data_thread.blockSignals(True)  # 阻止信号发送
                self.data_thread.data_loaded.disconnect()
            except (TypeError, AttributeError):
                pass
            try:
                self.data_thread.error_occurred.disconnect()
            except (TypeError, AttributeError):
                pass
            try:
                self.data_thread.progress_updated.disconnect()
            except (TypeError, AttributeError):
                pass
            try:
                self.data_thread.finished.disconnect()
            except (TypeError, AttributeError):
                pass
            
            # 强制终止线程，但不等待
            if self.data_thread.isRunning():
                self.data_thread.terminate()
                # 短时间等待，避免卡死
                if not self.data_thread.wait(500):  # 只等待0.5秒
                    print("线程无法正常结束，但继续执行")
            
            # 清理线程对象
            try:
                self.data_thread.deleteLater()
            except (TypeError, AttributeError):
                pass
            self.data_thread = None
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 信息栏
        info_layout = QHBoxLayout()
        self.info_label = QLabel("请选择数据库")
        self.info_label.setStyleSheet("font-weight: bold; color: #333;")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # 表选择栏
        table_layout = QHBoxLayout()
        table_label = QLabel("选择表:")
        table_layout.addWidget(table_label)
        
        self.table_combo = TableComboBox()
        self.table_combo.currentTextChanged.connect(self.on_table_changed)
        table_layout.addWidget(self.table_combo)
        
        table_layout.addStretch()
        layout.addLayout(table_layout)
        
        # 控制栏
        control_layout = QHBoxLayout()
        
        # 分页控制
        page_label = QLabel("每页显示:")
        control_layout.addWidget(page_label)
        
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["100", "500", "1000", "2000", "5000"])
        self.page_size_combo.setCurrentText("1000")
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)
        control_layout.addWidget(self.page_size_combo)
        
        control_layout.addSpacing(20)
        
        # 页码控制
        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        control_layout.addWidget(self.prev_btn)
        
        self.page_label = QLabel("第 1 页")
        control_layout.addWidget(self.page_label)
        
        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        control_layout.addWidget(self.next_btn)
        
        control_layout.addSpacing(20)
        
        # 停止加载按钮
        self.stop_loading_btn = QPushButton("停止加载")
        self.stop_loading_btn.clicked.connect(self.stop_loading)
        self.stop_loading_btn.setVisible(False)  # 默认隐藏
        self.stop_loading_btn.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c9302c;
            }
        """)
        control_layout.addWidget(self.stop_loading_btn)
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_data)
        control_layout.addWidget(refresh_btn)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # 内置搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("表内搜索:")
        search_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("在当前表中搜索...")
        self.search_input.textChanged.connect(self.filter_table_data)
        search_layout.addWidget(self.search_input)
        
        self.case_sensitive_cb = QCheckBox("区分大小写")
        search_layout.addWidget(self.case_sensitive_cb)
        
        clear_search_btn = QPushButton("清除")
        clear_search_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(clear_search_btn)
        
        layout.addLayout(search_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 表格
        self.table = CustomTableWidget()
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        
        # 设置右键菜单
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.table)
        
        # 状态栏
        status_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)
    
    def show_context_menu(self, position):
        """显示右键菜单"""
        # 获取当前单元格
        item = self.table.itemAt(position)
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
        
        # 显示单元格详情
        detail_action = QAction("查看详情", self)
        detail_action.triggered.connect(lambda: self.show_cell_detail(item))
        menu.addAction(detail_action)
        
        menu.exec(self.table.mapToGlobal(position))
    
    def copy_cell_content(self, item):
        """复制单元格内容"""
        if item:
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(item.text())
            self.status_label.setText("已复制单元格内容到剪贴板")
    
    def copy_row_content(self, row):
        """复制整行内容"""
        if row >= 0 and row < self.table.rowCount():
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText("\t".join(row_data))
            self.status_label.setText("已复制整行内容到剪贴板")
    
    def copy_column_header(self, column):
        """复制列标题"""
        if column >= 0 and column < self.table.columnCount():
            header = self.table.horizontalHeaderItem(column)
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
        column_name = self.table.horizontalHeaderItem(col).text() if self.table.horizontalHeaderItem(col) else f"列{col}"
        
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
        self.current_offset = 0
        
        # 更新信息标签
        self.info_label.setText(f"数据库: {package_name}/{parent_dir}/{db_name}")
        
        # 获取表列表
        try:
            if (self.database_manager and 
                package_name in self.database_manager.databases and
                parent_dir in self.database_manager.databases[package_name] and
                db_name in self.database_manager.databases[package_name][parent_dir]):
                
                db_info = self.database_manager.databases[package_name][parent_dir][db_name]
                self.available_tables = sorted(db_info.tables or [])
                
                # 更新表选择下拉框
                self.table_combo.clear()
                if self.available_tables:
                    self.table_combo.addItems(self.available_tables)
                    # 自动选择第一个表
                    if len(self.available_tables) > 0:
                        self.table_combo.setCurrentIndex(0)
                else:
                    self.table_combo.addItem("(无表)")
                    self.clear_table_display()
            else:
                self.available_tables = []
                self.table_combo.clear()
                self.table_combo.addItem("(无表)")
                self.clear_table_display()
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"获取表列表失败: {str(e)}")
            self.available_tables = []
            self.clear_table_display()
    
    def on_table_changed(self, table_name):
        """表选择改变时的处理"""
        if table_name and table_name != "(无表)" and table_name in self.available_tables:
            self.current_table = table_name
            self.current_offset = 0
            self.load_data()
        else:
            self.clear_table_display()
    
    def clear_table_display(self):
        """清空表显示"""
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
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
        self.stop_loading_btn.setVisible(True)
        
        # 启动超时定时器
        self.load_timeout_timer.start(30000)  # 30秒超时
        
        # 创建新的数据加载线程
        self.data_thread = DataLoadThread(
            self.database_manager,
            self.current_package,
            self.current_parent_dir,
            self.current_db,
            self.current_table,
            self.page_size,
            self.current_offset
        )
        
        # 连接信号
        self.data_thread.data_loaded.connect(self.on_data_loaded)
        self.data_thread.error_occurred.connect(self.on_error_occurred)
        self.data_thread.finished.connect(self.on_thread_finished)
        self.data_thread.progress_updated.connect(self.on_progress_updated)
        
        # 启动线程
        self.data_thread.start()
    
    def on_data_loaded(self, columns, rows):
        """数据加载完成"""
        try:
            # 设置表格
            self.table.setRowCount(len(rows))
            self.table.setColumnCount(len(columns))
            self.table.setHorizontalHeaderLabels(columns)
            
            # 填充数据
            for row_idx, row_data in enumerate(rows):
                for col_idx, cell_data in enumerate(row_data):
                    item = QTableWidgetItem(str(cell_data) if cell_data is not None else "")
                    self.table.setItem(row_idx, col_idx, item)
            
            # 调整列宽
            self.table.resizeColumnsToContents()
            
            # 更新状态
            total_rows = len(rows)
            current_page = self.current_offset // self.page_size + 1
            self.page_label.setText(f"第 {current_page} 页")
            self.status_label.setText(f"显示 {total_rows} 行数据")
            
            # 更新分页按钮
            self.update_pagination_buttons()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"显示数据时出错: {str(e)}")
    
    def on_error_occurred(self, error_message):
        """处理错误"""
        QMessageBox.critical(self, "加载数据失败", error_message)
        self.status_label.setText("加载数据失败")
        self.stop_loading_btn.setVisible(False)  # 隐藏停止按钮
    
    def on_thread_finished(self):
        """线程完成后的清理"""
        print("数据加载线程已完成")
        
        # 停止超时定时器
        if hasattr(self, 'load_timeout_timer'):
            self.load_timeout_timer.stop()
        
        # 隐藏进度条和停止按钮
        self.progress_bar.setVisible(False)
        self.stop_loading_btn.setVisible(False)
        
        # 简单清理线程对象
        if self.data_thread:
            try:
                # 断开所有信号连接
                self.data_thread.blockSignals(True)
                
                # 删除线程对象
                self.data_thread.deleteLater()
                self.data_thread = None
                print("线程对象已清理")
                
            except Exception as e:
                print(f"清理线程时出错: {e}")
                self.data_thread = None
    
    def on_progress_updated(self, percent):
        """处理进度更新"""
        self.progress_bar.setValue(percent)
    
    def on_page_size_changed(self, new_size):
        """页面大小改变"""
        try:
            self.page_size = int(new_size)
            self.current_offset = 0
            self.load_data()
        except ValueError:
            pass
    
    def prev_page(self):
        """上一页"""
        if self.current_offset > 0:
            self.current_offset = max(0, self.current_offset - self.page_size)
            self.load_data()
    
    def next_page(self):
        """下一页"""
        self.current_offset += self.page_size
        self.load_data()
    
    def update_pagination_buttons(self):
        """更新分页按钮状态"""
        # 上一页按钮
        self.prev_btn.setEnabled(self.current_offset > 0)
        
        # 下一页按钮 - 简单启用，实际数据不足时会自动禁用
        has_data = self.table.rowCount() > 0
        is_full_page = self.table.rowCount() == self.page_size
        self.next_btn.setEnabled(has_data and is_full_page)
    
    def refresh_data(self):
        """刷新当前数据"""
        if self.current_table:
            self.load_data()
    
    def filter_table_data(self):
        """过滤表格数据"""
        search_text = self.search_input.text().strip()
        case_sensitive = self.case_sensitive_cb.isChecked()
        
        if not search_text:
            # 显示所有行
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, False)
            return
        
        # 根据搜索文本过滤行
        for row in range(self.table.rowCount()):
            row_visible = False
            
            # 检查每一列
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    cell_text = item.text()
                    if case_sensitive:
                        if search_text in cell_text:
                            row_visible = True
                            break
                    else:
                        if search_text.lower() in cell_text.lower():
                            row_visible = True
                            break
            
            self.table.setRowHidden(row, not row_visible)
    
    def clear_search(self):
        """清除搜索"""
        self.search_input.clear()
        # 显示所有行
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
    
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
        if not self.current_table or self.table.rowCount() == 0:
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
                    for col in range(self.table.columnCount()):
                        headers.append(self.table.horizontalHeaderItem(col).text())
                    writer.writerow(headers)
                    
                    # 写入数据行
                    for row in range(self.table.rowCount()):
                        if not self.table.isRowHidden(row):  # 只导出可见行
                            row_data = []
                            for col in range(self.table.columnCount()):
                                item = self.table.item(row, col)
                                row_data.append(item.text() if item else "")
                            writer.writerow(row_data)
                
                QMessageBox.information(self, "成功", f"数据已导出到:\n{filename}")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")
    
    def select_and_show_table(self, table_name):
        """选择并显示指定的表"""
        try:
            if table_name in self.available_tables:
                # 在下拉框中选择对应的表
                table_index = self.available_tables.index(table_name)
                self.table_combo.setCurrentIndex(table_index)
                
                print(f"已选择表: {table_name}")
                return True
            else:
                print(f"表 {table_name} 不在可用表列表中")
                return False
                
        except Exception as e:
            print(f"选择表时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def stop_loading(self):
        """停止加载数据"""
        if self.data_thread and self.data_thread.isRunning():
            print("正在停止数据加载线程...")
            try:
                # 阻止信号发送，避免UI更新冲突
                self.data_thread.blockSignals(True)
                
                # 请求线程中断
                self.data_thread.requestInterruption()
                
                # 强制终止线程
                self.data_thread.terminate()
                
                # 不等待线程结束，直接清理
                print("数据加载线程已终止")
                
                # 清理线程对象
                self.data_thread.deleteLater()
                self.data_thread = None
                
            except Exception as e:
                print(f"停止线程时出错: {e}")
                # 即使出错也要清理线程引用
                self.data_thread = None
        
        # 立即更新UI状态
        self.stop_loading_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("已停止加载")
        
        # 停止超时定时器
        if hasattr(self, 'load_timeout_timer'):
            self.load_timeout_timer.stop()
    
    def on_load_timeout(self):
        """加载超时处理"""
        print("数据加载超时，强制停止...")
        if self.data_thread and self.data_thread.isRunning():
            self.data_thread.terminate()
            self.data_thread.wait(3000)  # 等待3秒
        
        self.progress_bar.setVisible(False)
        self.stop_loading_btn.setVisible(False)
        self.status_label.setText("加载超时，已停止")
        
        QMessageBox.warning(self, "加载超时", 
                           "数据加载时间过长，已自动停止。\n"
                           "这可能是由于数据库文件被锁定或查询复杂度过高。\n"
                           "请尝试刷新或选择其他表。") 