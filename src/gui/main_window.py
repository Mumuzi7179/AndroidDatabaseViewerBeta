# -*- coding: utf-8 -*-
"""
主窗口模块
应用程序的主界面
"""

import os
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QSplitter, QPushButton, QLabel, QFileDialog,
    QMessageBox, QProgressBar, QStatusBar, QMenuBar,
    QMenu, QToolBar, QApplication, QProgressDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QAction, QIcon, QDesktopServices
import time

from ..core.file_parser import AndroidFileParser
from ..core.database_manager import DatabaseManager
from ..core.log_manager import LogManager
from ..core.project_manager import ProjectManager
from .package_tree import PackageTreeWidget
from .database_viewer import DatabaseViewerWidget
from .search_dialog import SearchDialog
from .ai_analysis_dialog import AIAnalysisDialog
from .suspicious_analysis_dialog import SuspiciousAnalysisDialog
from .export_attachments_dialog import ExportAttachmentsDialog


class LoadDataThread(QThread):
    """数据加载线程"""
    progress_updated = Signal(str)
    progress_percent = Signal(int)  # 进度百分比
    data_loaded = Signal(object)  # 包数据
    error_occurred = Signal(str)
    
    def __init__(self, file_parser, database_manager, data_path):
        super().__init__()
        self.file_parser = file_parser
        self.database_manager = database_manager
        self.data_path = data_path
    
    def run(self):
        try:
            # 解析文件结构
            self.progress_updated.emit("正在解析文件结构...")
            self.progress_percent.emit(10)
            self.file_parser.parse_directory_structure()
            
            # 查找包
            self.progress_updated.emit("正在查找应用包...")
            self.progress_percent.emit(30)
            packages = self.file_parser.find_packages()
            
            # 加载数据库
            self.progress_updated.emit("正在加载数据库信息...")
            self.progress_percent.emit(60)
            
            # 分步加载数据库，提供更详细的进度
            total_packages = len(packages)
            loaded_packages = 0
            
            for i, package in enumerate(packages):
                if package.database_files:
                    # 计算当前进度
                    current_progress = 60 + int((i / total_packages) * 30)
                    self.progress_percent.emit(current_progress)
                    self.progress_updated.emit(f"正在加载 {package.package_name} 的数据库...")
                    
                loaded_packages += 1
            
            self.progress_percent.emit(90)
            self.database_manager.load_databases(packages)
            
            self.progress_percent.emit(100)
            self.progress_updated.emit("加载完成")
            self.data_loaded.emit(packages)
            
        except Exception as e:
            self.error_occurred.emit(str(e))


class MainWindow(QMainWindow):
    """主窗口类"""
    
    def __init__(self):
        super().__init__()
        self.file_parser = None
        self.database_manager = DatabaseManager()
        self.log_manager = LogManager()
        self.project_manager = ProjectManager()
        self.packages = []
        self.current_data_path = ""
        self.load_thread = None
        self.has_unsaved_changes = False  # 追踪是否有未保存的更改
        
        # 启用拖拽功能
        self.setAcceptDrops(True)
        
        self.init_ui()
        self.init_status_bar()
        self.init_menu_bar()
        self.init_tool_bar()
        self.apply_theme()
        
        # 设置定时器清理旧日志
        self.log_cleanup_timer = QTimer()
        self.log_cleanup_timer.setSingleShot(True)
        self.log_cleanup_timer.timeout.connect(self.cleanup_old_logs)
        self.log_cleanup_timer.start(60000)  # 1分钟后清理
    
    def dragEnterEvent(self, event):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                file_path = urls[0].toLocalFile()
                if os.path.isdir(file_path):
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dropEvent(self, event):
        """拖拽放下事件"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                folder_path = urls[0].toLocalFile()
                if os.path.isdir(folder_path):
                    self.current_data_path = folder_path
                    self.path_label.setText(f"数据包: {folder_path}")
                    self.load_data(folder_path)
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("Android 数据库分析工具 v0.4.1")
        self.setGeometry(100, 100, 1200, 800)
        # 设置最小窗口大小，确保所有按钮都能显示
        self.setMinimumSize(1000, 600)
        
        # 设置窗口图标
        icon_path = Path(__file__).parent.parent / "assets" / "icon.jpg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 工具栏区域
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)  # 设置按钮间距
        
        # 选择文件夹按钮 - 修改名称
        self.select_folder_btn = QPushButton("选择文件夹")
        self.select_folder_btn.clicked.connect(self.select_data_folder)
        self.select_folder_btn.setMinimumWidth(100)
        toolbar_layout.addWidget(self.select_folder_btn)
        
        # 解析所有数据库按钮 - 修改名称
        self.parse_all_db_btn = QPushButton("解析所有数据库")
        self.parse_all_db_btn.setToolTip("直接解析文件夹下的所有数据库文件，无需Android包结构")
        self.parse_all_db_btn.clicked.connect(self.select_and_parse_all_databases)
        self.parse_all_db_btn.setVisible(True)
        self.parse_all_db_btn.setMinimumWidth(120)
        toolbar_layout.addWidget(self.parse_all_db_btn)
        
        # 载入工程文件按钮 - 新增
        self.load_project_btn = QPushButton("载入工程文件")
        self.load_project_btn.setToolTip("载入之前保存的.madb工程文件")
        self.load_project_btn.clicked.connect(self.load_project_file)
        self.load_project_btn.setMinimumWidth(100)
        toolbar_layout.addWidget(self.load_project_btn)
        
        # 当前路径显示
        self.path_label = QLabel("未选择数据包 (可拖拽文件夹到此窗口)")
        self.path_label.setStyleSheet("color: #666; font-style: italic;")
        toolbar_layout.addWidget(self.path_label)
        
        toolbar_layout.addStretch()
        
        # 全局搜索按钮
        self.search_btn = QPushButton("全局搜索")
        self.search_btn.clicked.connect(self.show_search_dialog)
        self.search_btn.setEnabled(False)
        self.search_btn.setMinimumWidth(80)
        toolbar_layout.addWidget(self.search_btn)
        
        # AI分析按钮
        self.ai_analysis_btn = QPushButton("🤖 AI分析")
        self.ai_analysis_btn.clicked.connect(self.show_ai_analysis_dialog)
        self.ai_analysis_btn.setEnabled(False)
        self.ai_analysis_btn.setMinimumWidth(80)
        toolbar_layout.addWidget(self.ai_analysis_btn)
        
        # 可疑信息分析按钮
        self.suspicious_analysis_btn = QPushButton("🕵️ 可疑信息分析")
        self.suspicious_analysis_btn.setToolTip("快速搜索可能包含密码、钱包、加密等可疑信息的数据")
        self.suspicious_analysis_btn.clicked.connect(self.show_suspicious_analysis_dialog)
        self.suspicious_analysis_btn.setEnabled(False)
        self.suspicious_analysis_btn.setMinimumWidth(120)
        toolbar_layout.addWidget(self.suspicious_analysis_btn)
        
        # 一键导出所有附件按钮
        self.export_attachments_btn = QPushButton("📎 一键导出所有附件")
        self.export_attachments_btn.setToolTip("自动识别并导出所有数据库中的附件文件（图片、文档、压缩包等）")
        self.export_attachments_btn.clicked.connect(self.show_export_attachments_dialog)
        self.export_attachments_btn.setEnabled(False)
        self.export_attachments_btn.setMinimumWidth(140)
        toolbar_layout.addWidget(self.export_attachments_btn)
        
        main_layout.addLayout(toolbar_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # 主要内容区域
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 先创建组件
        self.package_tree = PackageTreeWidget()
        self.database_viewer = DatabaseViewerWidget()
        
        # 连接信号
        self.package_tree.database_selected.connect(self.database_viewer.show_database_tables)
        
        # 添加到分割器
        splitter.addWidget(self.package_tree)
        splitter.addWidget(self.database_viewer)
        
        # 设置分割器比例 - 调整到合适的中间值
        splitter.setSizes([340, 860])
        main_layout.addWidget(splitter)
        
        # 设置数据库管理器
        self.package_tree.set_database_manager(self.database_manager)
        self.database_viewer.set_database_manager(self.database_manager)
    
    def apply_theme(self):
        """应用主题样式"""
        # 现代化的深蓝色主题
        theme_style = """
        QMainWindow {
            background-color: #f5f5f5;
        }
        
        QPushButton {
            background-color: #4a90e2;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        
        QPushButton:hover {
            background-color: #357abd;
        }
        
        QPushButton:pressed {
            background-color: #2968a3;
        }
        
        QPushButton:disabled {
            background-color: #cccccc;
            color: #666666;
        }
        
        QTreeWidget {
            background-color: white;
            border: 1px solid #ddd;
            border-radius: 4px;
            selection-background-color: #4a90e2;
        }
        
        QTreeWidget::item {
            padding: 4px;
        }
        
        QTreeWidget::item:hover {
            background-color: #e3f2fd;
        }
        
        QTreeWidget::item:selected {
            background-color: #4a90e2;
            color: white;
        }
        
        QTableWidget {
            background-color: white;
            border: 1px solid #ddd;
            border-radius: 4px;
            gridline-color: #e0e0e0;
        }
        
        QTableWidget::item {
            padding: 6px;
        }
        
        QTableWidget::item:selected {
            background-color: #4a90e2;
            color: white;
        }
        
        QHeaderView::section {
            background-color: #f0f0f0;
            border: 1px solid #ddd;
            padding: 6px;
            font-weight: bold;
        }
        
        QLineEdit {
            background-color: white;
            border: 2px solid #ddd;
            border-radius: 4px;
            padding: 6px;
        }
        
        QLineEdit:focus {
            border-color: #4a90e2;
        }
        
        QProgressBar {
            border: 1px solid #ddd;
            border-radius: 4px;
            text-align: center;
        }
        
        QProgressBar::chunk {
            background-color: #4a90e2;
            border-radius: 3px;
        }
        
        QStatusBar {
            background-color: #f0f0f0;
            border-top: 1px solid #ddd;
        }
        
        QMenuBar {
            background-color: #f8f8f8;
            border-bottom: 1px solid #ddd;
        }
        
        QMenuBar::item {
            padding: 6px 12px;
        }
        
        QMenuBar::item:selected {
            background-color: #4a90e2;
            color: white;
        }
        
        QToolBar {
            background-color: #f8f8f8;
            border-bottom: 1px solid #ddd;
            spacing: 3px;
        }
        
        QSplitter::handle {
            background-color: #ddd;
        }
        
        QSplitter::handle:horizontal {
            width: 2px;
        }
        
        QSplitter::handle:vertical {
            height: 2px;
        }
        
        QCheckBox {
            spacing: 5px;
        }
        
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
        
        QCheckBox::indicator:unchecked {
            border: 2px solid #ddd;
            background-color: white;
            border-radius: 2px;
        }
        
        QCheckBox::indicator:checked {
            border: 2px solid #4a90e2;
            background-color: #4a90e2;
            border-radius: 2px;
        }
        
        QComboBox {
            background-color: white;
            border: 2px solid #ddd;
            border-radius: 4px;
            padding: 6px;
            min-width: 80px;
        }
        
        QComboBox:focus {
            border-color: #4a90e2;
        }
        
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left: 1px solid #ddd;
        }
        
        QTabWidget::pane {
            border: 1px solid #ddd;
            background-color: white;
        }
        
        QTabBar::tab {
            background-color: #f0f0f0;
            border: 1px solid #ddd;
            padding: 8px 16px;
            margin-right: 2px;
        }
        
        QTabBar::tab:selected {
            background-color: #4a90e2;
            color: white;
        }
        
        QTabBar::tab:hover {
            background-color: #e3f2fd;
        }
        """
        
        self.setStyleSheet(theme_style)
    
    def init_status_bar(self):
        """初始化状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)
        
        # 统计信息标签
        self.stats_label = QLabel("")
        self.status_bar.addPermanentWidget(self.stats_label)
    
    def init_menu_bar(self):
        """初始化菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        # 打开数据包
        open_action = QAction("打开数据包", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.select_data_folder)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        # 导出结构
        export_action = QAction("导出文件结构", self)
        export_action.triggered.connect(self.export_structure)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        # 退出
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        
        # 全局搜索
        search_action = QAction("全局搜索", self)
        search_action.setShortcut("Ctrl+F")
        search_action.triggered.connect(self.show_search_dialog)
        tools_menu.addAction(search_action)
        
        # 数据库统计
        stats_action = QAction("数据库统计", self)
        stats_action.triggered.connect(self.show_database_stats)
        tools_menu.addAction(stats_action)
        
        tools_menu.addSeparator()
        
        # 一键导出所有附件
        export_attachments_action = QAction("一键导出所有附件", self)
        export_attachments_action.setShortcut("Ctrl+E")
        export_attachments_action.triggered.connect(self.show_export_attachments_dialog)
        tools_menu.addAction(export_attachments_action)
        
        tools_menu.addSeparator()
        
        # 清理日志
        cleanup_action = QAction("清理旧日志", self)
        cleanup_action.triggered.connect(self.cleanup_old_logs)
        tools_menu.addAction(cleanup_action)
        
        # 视图菜单
        view_menu = menubar.addMenu("视图")
        
        # 主题选择
        theme_menu = view_menu.addMenu("主题")
        
        # 默认主题
        default_theme_action = QAction("现代蓝色", self)
        default_theme_action.triggered.connect(lambda: self.apply_theme())
        theme_menu.addAction(default_theme_action)
        

        
        # 绿色主题
        green_theme_action = QAction("清新绿色", self)
        green_theme_action.triggered.connect(self.apply_green_theme)
        theme_menu.addAction(green_theme_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    

    
    def apply_green_theme(self):
        """应用绿色主题"""
        green_style = """
        QMainWindow {
            background-color: #f8fffe;
        }
        
        QPushButton {
            background-color: #2e7d32;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        
        QPushButton:hover {
            background-color: #1b5e20;
        }
        
        QPushButton:pressed {
            background-color: #0d3d0f;
        }
        
        QPushButton:disabled {
            background-color: #cccccc;
            color: #666666;
        }
        
        QTreeWidget {
            background-color: white;
            border: 1px solid #c8e6c9;
            selection-background-color: #2e7d32;
        }
        
        QTreeWidget::item:hover {
            background-color: #e8f5e8;
        }
        
        QTableWidget {
            background-color: white;
            border: 1px solid #c8e6c9;
            gridline-color: #e0e0e0;
        }
        
        QTableWidget::item:selected {
            background-color: #2e7d32;
            color: white;
        }
        
        QHeaderView::section {
            background-color: #e8f5e8;
            border: 1px solid #c8e6c9;
            padding: 6px;
            font-weight: bold;
        }
        
        QLineEdit {
            background-color: white;
            border: 2px solid #c8e6c9;
            border-radius: 4px;
            padding: 6px;
        }
        
        QLineEdit:focus {
            border-color: #2e7d32;
        }
        
        QProgressBar {
            border: 1px solid #c8e6c9;
            border-radius: 4px;
            text-align: center;
        }
        
        QProgressBar::chunk {
            background-color: #2e7d32;
            border-radius: 3px;
        }
        
        QStatusBar {
            background-color: #e8f5e8;
            border-top: 1px solid #c8e6c9;
        }
        
        QMenuBar {
            background-color: #f1f8e9;
            border-bottom: 1px solid #c8e6c9;
        }
        
        QMenuBar::item:selected {
            background-color: #2e7d32;
            color: white;
        }
        
        QCheckBox::indicator:checked {
            border: 2px solid #2e7d32;
            background-color: #2e7d32;
        }
        
        QComboBox:focus {
            border-color: #2e7d32;
        }
        
        QTabBar::tab:selected {
            background-color: #2e7d32;
            color: white;
        }
        """
        
        self.setStyleSheet(green_style)
    
    def init_tool_bar(self):
        """初始化工具栏"""
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        # 添加工具栏按钮
        toolbar.addAction("打开", self.select_data_folder)
        toolbar.addSeparator()
        toolbar.addAction("搜索", self.show_search_dialog)
        toolbar.addAction("统计", self.show_database_stats)
    
    def select_data_folder(self):
        """选择数据文件夹"""
        folder_path = QFileDialog.getExistingDirectory(
            self, "选择Android数据包文件夹"
        )
        
        if folder_path:
            self.current_data_path = folder_path
            self.path_label.setText(f"数据包: {folder_path}")
            self.load_data(folder_path)
    
    def load_data(self, data_path):
        """加载数据"""
        # 创建文件解析器
        self.file_parser = AndroidFileParser(data_path)
        
        # 显示进度条
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)  # 设置真实进度范围
        self.progress_bar.setValue(0)
        self.status_label.setText("正在加载数据...")
        
        # 禁用相关按钮
        self.select_folder_btn.setEnabled(False)
        self.search_btn.setEnabled(False)
        
        # 启动加载线程
        self.load_thread = LoadDataThread(
            self.file_parser, self.database_manager, data_path
        )
        self.load_thread.progress_updated.connect(self.update_progress)
        self.load_thread.progress_percent.connect(self.update_progress_percent)
        self.load_thread.data_loaded.connect(self.on_data_loaded)
        self.load_thread.error_occurred.connect(self.on_load_error)
        self.load_thread.finished.connect(self.on_load_finished)
        self.load_thread.start()
    
    def update_progress(self, message):
        """更新进度信息"""
        self.status_label.setText(message)
    
    def update_progress_percent(self, percent):
        """更新进度百分比"""
        self.progress_bar.setValue(percent)
    
    def on_data_loaded(self, packages):
        """数据加载完成"""
        self.packages = packages
        self.has_unsaved_changes = True  # 标记有未保存的更改
        
        # 更新包树形视图
        self.package_tree.load_packages(packages)
        
        # 更新统计信息
        self.update_statistics()
        
        self.status_label.setText("数据加载完成")
        
        # 更新界面
        self.package_tree.load_packages(packages)
        self.search_btn.setEnabled(True)
        self.ai_analysis_btn.setEnabled(True)
        self.suspicious_analysis_btn.setEnabled(True)
        self.export_attachments_btn.setEnabled(True)
    
    def on_load_error(self, error_message):
        """数据加载错误"""
        QMessageBox.critical(self, "加载错误", f"数据加载失败:\n{error_message}")
        self.status_label.setText("数据加载失败")
    
    def on_load_finished(self):
        """加载线程完成"""
        self.progress_bar.setVisible(False)
        self.select_folder_btn.setEnabled(True)
        self.search_btn.setEnabled(bool(self.packages))
        self.ai_analysis_btn.setEnabled(bool(self.packages))
        self.suspicious_analysis_btn.setEnabled(bool(self.packages))
        self.export_attachments_btn.setEnabled(bool(self.packages))
        self.load_thread = None
    
    def show_search_dialog(self):
        """显示搜索对话框"""
        if not self.database_manager or not self.packages:
            QMessageBox.warning(self, "警告", "请先加载数据包")
            return
        
        dialog = SearchDialog(self)
        dialog.set_database_manager(self.database_manager)
        dialog.set_log_manager(self.log_manager)
        
        # 连接跳转信号
        dialog.jump_to_database.connect(self.handle_database_jump)
        
        dialog.exec()
    
    def show_ai_analysis_dialog(self):
        """显示AI分析对话框"""
        if not self.database_manager or not self.packages:
            QMessageBox.warning(self, "警告", "请先加载数据包")
            return
        
        # 创建AI分析对话框
        ai_dialog = AIAnalysisDialog(self)
        ai_dialog.set_database_manager(self.database_manager)
        ai_dialog.set_packages(self.packages)
        
        # 显示对话框
        ai_dialog.exec()
    
    def show_suspicious_analysis_dialog(self):
        """显示可疑信息分析对话框"""
        if not self.database_manager or not self.packages:
            QMessageBox.warning(self, "警告", "请先加载数据包")
            return
        
        # 显示分析对话框，让用户手动点击分析
        dialog = SuspiciousAnalysisDialog(self)
        dialog.set_database_manager(self.database_manager)
        dialog.exec()
    
    def show_export_attachments_dialog(self):
        """显示导出所有附件对话框"""
        if not self.database_manager or not self.packages:
            QMessageBox.warning(self, "警告", "请先加载数据包")
            return
        
        # 创建导出附件对话框
        dialog = ExportAttachmentsDialog(self.database_manager, self)
        dialog.exec()
    
    def handle_database_jump(self, package_name, parent_dir, db_name, table_name):
        """处理从搜索结果跳转到数据库的请求"""
        try:
            print(f"开始跳转: {package_name}/{parent_dir}/{db_name}/{table_name}")
            
            # 1. 在包树中选中对应的数据库项 - 就像用户点击一样
            success = self.package_tree.select_database_item(package_name, parent_dir, db_name)
            
            if success:
                # 2. 如果指定了表名，在数据库查看器中选择该表
                if table_name:
                    # 等待一下让数据库表列表加载完成
                    QApplication.processEvents()
                    
                    # 选择指定的表
                    self.database_viewer.select_and_show_table(table_name)
                
                # 3. 更新状态栏
                self.status_label.setText(f"已跳转到: {package_name}/{parent_dir}/{db_name}/{table_name}")
                
                # 4. 将主窗口置于前台
                self.raise_()
                self.activateWindow()
                
                print(f"跳转完成")
            else:
                QMessageBox.warning(self, "跳转失败", "无法找到指定的数据库项")
                
        except Exception as e:
            print(f"跳转出错: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "跳转错误", f"跳转过程中发生错误:\n{str(e)}")
    
    def update_statistics(self):
        """更新统计信息"""
        if not self.packages:
            self.stats_label.setText("")
            return
        
        # 统计系统应用和非系统应用数量
        system_apps = sum(1 for pkg in self.packages if pkg.is_system_app)
        non_system_apps = sum(1 for pkg in self.packages if not pkg.is_system_app)
        
        stats = self.database_manager.get_database_statistics()
        self.stats_label.setText(
            f"包: {stats['total_packages']} (系统: {system_apps}, 📱非系统: {non_system_apps}) | "
            f"数据库: {stats['total_databases']} | "
            f"表: {stats['total_tables']}"
        )
    
    def show_database_stats(self):
        """显示数据库统计信息"""
        if not self.database_manager or not self.packages:
            QMessageBox.information(self, "提示", "请先加载数据包")
            return
        
        stats = self.database_manager.get_database_statistics()
        
        # 创建统计信息对话框
        from PySide6.QtWidgets import QDialog, QTextEdit, QVBoxLayout
        
        dialog = QDialog(self)
        dialog.setWindowTitle("数据库统计信息")
        dialog.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        
        # 生成统计报告
        report = f"""数据库统计报告
================

总体统计:
- 总包数: {stats['total_packages']}
- 总数据库数: {stats['total_databases']}
- 总表数: {stats['total_tables']}

详细统计:
"""
        
        for package_name, package_stats in stats['package_details'].items():
            report += f"\n包名: {package_name}\n"
            report += f"  目录数: {package_stats['directories']}\n"
            report += f"  数据库数: {package_stats['databases']}\n"
            report += f"  表数: {package_stats['tables']}\n"
            
            for dir_name, dir_stats in package_stats['directory_details'].items():
                report += f"  目录: {dir_name}\n"
                report += f"    数据库数: {dir_stats['databases']}\n"
                report += f"    表数: {dir_stats['tables']}\n"
                
                for db_name, db_stats in dir_stats['database_details'].items():
                    report += f"    数据库: {db_name} ({db_stats['tables']} 表)\n"
        
        text_edit.setPlainText(report)
        layout.addWidget(text_edit)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def export_structure(self):
        """导出文件结构"""
        if not self.file_parser:
            QMessageBox.information(self, "提示", "请先加载数据包")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存文件结构", "android_structure.json", "JSON文件 (*.json)"
        )
        
        if filename:
            try:
                self.file_parser.save_structure_to_json(filename)
                QMessageBox.information(self, "成功", f"文件结构已导出到:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")
    
    def cleanup_old_logs(self):
        """清理旧日志文件"""
        try:
            self.log_manager.clean_old_logs(days=30)
            self.status_label.setText("旧日志文件已清理")
        except Exception as e:
            print(f"清理日志失败: {e}")
    
    def show_about(self):
        """显示关于对话框"""
        # 创建自定义关于对话框
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser
        
        dialog = QDialog(self)
        dialog.setWindowTitle("关于")
        dialog.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # 使用 QTextBrowser 支持 HTML 和链接
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)  # 允许打开外部链接
        
        about_html = """
        <div style="text-align: center; padding: 20px;">
            <h2>Android 数据库分析工具</h2>
            <p><strong>版本:</strong> 0.4.1</p>
            <p><strong>作者:</strong> mumuzi</p>
            <p><strong>GitHub:</strong> <a href="https://github.com/Mumuzi7179">https://github.com/Mumuzi7179</a></p>
            
            <h3>功能特点:</h3>
            <ul style="text-align: left; max-width: 300px; margin: 0 auto;">
                <li>智能识别Android数据包结构</li>
                <li>预加载数据库和表信息</li>
                <li>全局搜索和结果导出</li>
                <li>搜索结果自动保存日志</li>
                <li>支持无扩展名数据库文件</li>
                <li>支持拖拽文件夹加载</li>
                <li>右键复制单元格内容</li>
                <li>双击打开特殊格式文件</li>
            </ul>
        </div>
        """
        
        text_browser.setHtml(about_html)
        layout.addWidget(text_browser)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def closeEvent(self, event):
        """程序关闭时的清理工作"""
        try:
            print("正在关闭程序...")
            
            # 如果有未保存的更改，询问用户是否保存
            if self.has_unsaved_changes and self.packages:
                reply = QMessageBox.question(
                    self, "保存提醒", 
                    "是否保存为工程文件？",
                    QMessageBox.StandardButton.Yes | 
                    QMessageBox.StandardButton.No | 
                    QMessageBox.StandardButton.Cancel
                )
                
                if reply == QMessageBox.StandardButton.Cancel:
                    # 用户取消，不退出程序
                    event.ignore()
                    return
                elif reply == QMessageBox.StandardButton.Yes:
                    # 用户选择保存
                    success = self.save_current_project()
                    if not success:
                        # 保存失败，询问是否强制退出
                        force_exit = QMessageBox.question(
                            self, "保存失败",
                            "工程文件保存失败，是否强制退出？",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        )
                        if force_exit == QMessageBox.StandardButton.No:
                            event.ignore()
                            return
                # 用户选择不保存，直接继续退出流程
            
            # 停止数据库查看器中的线程
            if hasattr(self, 'database_viewer') and self.database_viewer:
                self.database_viewer.stop_loading()
            
            # 清理加载线程
            if hasattr(self, 'load_thread') and self.load_thread:
                if self.load_thread and self.load_thread.isRunning():
                    print("停止主加载线程...")
                    self.load_thread.requestInterruption()
                    self.load_thread.terminate()
                    if not self.load_thread.wait(2000):  # 最多等待2秒
                        print("主加载线程未能正常结束")
                    self.load_thread.deleteLater()
                    self.load_thread = None
            
            # 关闭数据库连接
            if hasattr(self, 'database_manager') and self.database_manager:
                self.database_manager.close_all_connections()
            
            # 清理工程管理器的临时文件
            if hasattr(self, 'project_manager') and self.project_manager:
                self.project_manager.cleanup_temp_files()
            
            print("程序关闭清理完成")
            event.accept()
            
        except Exception as e:
            print(f"关闭程序时出错: {e}")
            # 即使出错也要接受关闭事件
            event.accept()
    
    def save_current_project(self):
        """保存当前工程"""
        try:
            # 创建进度对话框
            progress_dialog = QProgressDialog("", "取消", 0, 100, self)
            progress_dialog.setWindowTitle("保存工程")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.show()
            
            def update_progress(message, percent):
                progress_dialog.setValue(percent)
                QApplication.processEvents()
                if progress_dialog.wasCanceled():
                    return False
                return True
            
            # 保存工程文件
            success = self.project_manager.save_project(
                self.packages, 
                self.current_data_path, 
                progress_callback=update_progress
            )
            
            progress_dialog.close()
            
            if success:
                self.has_unsaved_changes = False
                QMessageBox.information(self, "保存成功", "工程文件已成功保存！")
                return True
            else:
                QMessageBox.warning(self, "保存失败", "工程文件保存失败！")
                return False
            
        except Exception as e:
            QMessageBox.critical(self, "保存错误", f"保存工程文件时发生错误:\n{str(e)}")
            return False
    
    def clear_all_data(self):
        """清空所有解析的数据"""
        try:
            print("正在清空解析数据...")
            
            # 清空包数据
            self.packages = []
            self.current_data_path = ""
            self.has_unsaved_changes = False
            
            # 重置界面
            self.package_tree.tree.clear()  # 使用正确的方法清空树形视图
            self.database_viewer.clear_table_display()  # 使用正确的方法清空数据库视图
            
            # 禁用相关按钮
            self.search_btn.setEnabled(False)
            self.ai_analysis_btn.setEnabled(False)
            self.suspicious_analysis_btn.setEnabled(False)
            self.export_attachments_btn.setEnabled(False)
            
            # 重置标签
            self.path_label.setText("未选择数据包 (可拖拽文件夹到此窗口)")
            self.status_label.setText("已清空解析数据")
            self.stats_label.setText("")
            
            # 关闭数据库连接
            if self.database_manager:
                self.database_manager.close_all_connections()
            
            print("解析数据清空完成")
            
        except Exception as e:
            print(f"清空数据时出错: {e}")
    
    def load_project_file(self):
        """载入工程文件"""
        try:
            # 如果当前有未保存的更改，先询问用户
            if self.has_unsaved_changes and self.packages:
                reply = QMessageBox.question(
                    self, "确认载入",
                    "当前有未保存的解析记录，载入工程文件将清除当前数据。\n是否继续？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            
            # 选择工程文件
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择工程文件", "", "Android数据库工程文件 (*.madb)"
            )
            
            if not file_path:
                return
            
            # 创建进度对话框
            progress_dialog = QProgressDialog("", "取消", 0, 100, self)
            progress_dialog.setWindowTitle("载入工程")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.show()
            
            def update_progress(message, percent):
                progress_dialog.setValue(percent)
                QApplication.processEvents()
                if progress_dialog.wasCanceled():
                    return False
                return True
            
            # 先清空当前数据
            self.clear_all_data()
            
            # 载入工程文件
            project_data = self.project_manager.load_project(
                file_path, 
                progress_callback=update_progress
            )
            
            if project_data:
                # 恢复数据
                self.packages = project_data.packages
                self.current_data_path = project_data.current_data_path
                self.has_unsaved_changes = False  # 刚载入的工程文件不算未保存更改
                
                # 显示数据库加载进度
                update_progress("", 85)
                
                # 重新加载数据库管理器
                def db_progress_callback(current, total):
                    # 将数据库加载进度映射到85-95区间
                    if total > 0:
                        db_progress = 85 + int((current / total) * 10)
                        update_progress("", db_progress)
                        QApplication.processEvents()
                
                self.database_manager.load_databases(self.packages, progress_callback=db_progress_callback)
                
                # 更新界面
                self.package_tree.load_packages(self.packages)
                self.search_btn.setEnabled(True)
                self.ai_analysis_btn.setEnabled(True)
                self.suspicious_analysis_btn.setEnabled(True)
                self.export_attachments_btn.setEnabled(True)
                
                # 更新标签
                self.path_label.setText(f"工程文件: {file_path}")
                self.status_label.setText("工程文件载入完成")
                
                # 更新统计信息
                self.update_statistics()
                
                # 完成进度
                update_progress("", 100)
            
            progress_dialog.close()
            
            if project_data:
                QMessageBox.information(
                    self, "载入成功", 
                    f"工程文件载入成功！\n"
                    f"包含 {len(self.packages)} 个包\n"
                    f"包含 {len(project_data.database_files)} 个数据库文件"
                )
            else:
                QMessageBox.warning(self, "载入失败", "工程文件载入失败！")
                
        except Exception as e:
            QMessageBox.critical(self, "载入错误", f"载入工程文件时发生错误:\n{str(e)}")
            import traceback
            traceback.print_exc()
    
    def select_and_parse_all_databases(self):
        """选择文件夹并解析其中所有数据库文件"""
        from PySide6.QtWidgets import QFileDialog
        
        folder_path = QFileDialog.getExistingDirectory(
            self, "选择包含数据库文件的文件夹", ""
        )
        
        if folder_path:
            self.current_data_path = folder_path
            self.path_label.setText(f"数据库文件夹: {folder_path}")
            self.parse_all_databases_in_folder(folder_path)
    
    def parse_all_databases_in_folder(self, folder_path):
        """解析文件夹中的所有数据库文件"""
        try:
            # 显示进度条
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.status_label.setText("正在扫描数据库文件...")
            
            # 创建一个特殊的文件解析器，用于扫描所有数据库
            from pathlib import Path
            from ..core.file_parser import DatabaseFileInfo, PackageInfo
            
            # 递归查找所有数据库文件
            all_db_files = []
            folder_path_obj = Path(folder_path)
            
            def scan_databases(directory, depth=0, max_depth=10):
                """递归扫描数据库文件"""
                if depth > max_depth:
                    return
                
                try:
                    for item in directory.iterdir():
                        if item.is_file():
                            if self._is_database_file(item):
                                all_db_files.append(item)
                        elif item.is_dir():
                            scan_databases(item, depth + 1, max_depth)
                except (PermissionError, OSError) as e:
                    print(f"扫描目录失败 {directory}: {e}")
            
            # 开始扫描
            scan_databases(folder_path_obj)
            
            self.progress_bar.setValue(30)
            self.status_label.setText(f"发现 {len(all_db_files)} 个数据库文件，正在组织结构...")
            
            # 将数据库文件组织成虚拟包结构
            packages = []
            
            # 按目录分组数据库文件
            db_by_dir = {}
            for db_file in all_db_files:
                parent_dir = db_file.parent.name
                if parent_dir not in db_by_dir:
                    db_by_dir[parent_dir] = []
                db_by_dir[parent_dir].append(db_file)
            
            self.progress_bar.setValue(60)
            
            # 为每个目录创建一个虚拟包
            for dir_name, files in db_by_dir.items():
                database_files = {"databases": []}
                
                for db_file in files:
                    db_info = DatabaseFileInfo(
                        file_name=db_file.name,
                        file_path=str(db_file),
                        parent_dir="databases"
                    )
                    database_files["databases"].append(db_info)
                
                # 创建虚拟包信息
                package_info = PackageInfo(
                    package_name=f"db_folder.{dir_name}",
                    path=str(db_file.parent),
                    has_databases=True,
                    has_shared_prefs=False,
                    has_files=False,
                    is_system_app=False,  # 标记为非系统应用以便AI分析
                    database_files=database_files
                )
                packages.append(package_info)
            
            # 如果没有按目录分组，创建一个总的包
            if not packages and all_db_files:
                database_files = {"databases": []}
                
                for db_file in all_db_files:
                    db_info = DatabaseFileInfo(
                        file_name=db_file.name,
                        file_path=str(db_file),
                        parent_dir="databases"
                    )
                    database_files["databases"].append(db_info)
                
                package_info = PackageInfo(
                    package_name="db_folder.all_databases",
                    path=folder_path,
                    has_databases=True,
                    has_shared_prefs=False,
                    has_files=False,
                    is_system_app=False,
                    database_files=database_files
                )
                packages.append(package_info)
            
            self.progress_bar.setValue(90)
            self.status_label.setText("正在加载数据库内容...")
            
            # 加载数据库
            self.database_manager.load_databases(packages)
            self.packages = packages
            self.has_unsaved_changes = True  # 标记有未保存的更改
            
            # 更新界面
            self.package_tree.load_packages(packages)
            self.search_btn.setEnabled(True)
            self.ai_analysis_btn.setEnabled(True)
            self.suspicious_analysis_btn.setEnabled(True)
            self.export_attachments_btn.setEnabled(True)
            
            self.progress_bar.setValue(100)
            self.status_label.setText(f"成功加载 {len(packages)} 个虚拟包，共 {len(all_db_files)} 个数据库文件")
            
            # 更新统计信息
            self.update_statistics()
            
            # 隐藏进度条
            self.progress_bar.setVisible(False)
            
            QMessageBox.information(
                self, "加载完成", 
                f"成功加载 {len(all_db_files)} 个数据库文件\n"
                f"已组织为 {len(packages)} 个虚拟包\n"
                f"现在可以使用搜索和AI分析功能了"
            )
            
        except Exception as e:
            self.progress_bar.setVisible(False)
            self.status_label.setText("加载失败")
            QMessageBox.critical(self, "错误", f"解析数据库文件时发生错误:\n{str(e)}")
            import traceback
            traceback.print_exc()
    
    def _is_database_file(self, file_path):
        """检查文件是否为数据库文件"""
        try:
            # 首先检查文件大小，太小的文件可能不是数据库
            if file_path.stat().st_size < 100:
                return False
                
            # 读取文件头部检查SQLite签名
            with open(file_path, 'rb') as f:
                header = f.read(16)
                # SQLite文件头签名
                if header.startswith(b'SQLite format 3\x00'):
                    return True
                    
            # 如果文件头不匹配，但文件名符合数据库特征，也尝试作为数据库处理
            file_name = file_path.name.lower()
            db_keywords = ['db', 'database', 'sqlite', 'data', 'cache', 'message', 'contact', 'log']
            
            # 检查文件扩展名
            if file_path.suffix.lower() in ['.db', '.sqlite', '.sqlite3']:
                return True
                
            # 检查无扩展名文件是否包含数据库关键词
            if not file_path.suffix:
                for keyword in db_keywords:
                    if keyword in file_name:
                        # 尝试打开看是否为有效的SQLite文件
                        try:
                            import sqlite3
                            conn = sqlite3.connect(str(file_path))
                            cursor = conn.cursor()
                            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                            conn.close()
                            return True
                        except:
                            pass
                            
            return False
            
        except (IOError, OSError):
            return False

# ... rest of the file remains unchanged ... 