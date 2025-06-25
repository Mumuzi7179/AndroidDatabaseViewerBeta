from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QProgressBar, QPushButton, QTextEdit, QGroupBox,
                               QTreeWidget, QTreeWidgetItem, QMessageBox, QApplication,
                               QCheckBox, QMenu, QSplitter)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont, QAction
import os
import subprocess
import platform


class ExportThread(QThread):
    """导出线程"""
    progress = Signal(int)
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, database_manager, export_by_package=False):
        super().__init__()
        self.database_manager = database_manager
        self.export_by_package = export_by_package
        
    def run(self):
        try:
            def progress_callback(processed):
                self.progress.emit(processed)
            
            result = self.database_manager.export_all_attachments(progress_callback, self.export_by_package)
            if result:
                self.finished.emit(result)
            else:
                self.error.emit("导出过程中发生错误")
        except Exception as e:
            self.error.emit(f"导出失败: {str(e)}")


class ExportAttachmentsDialog(QDialog):
    """导出所有附件对话框"""
    
    def __init__(self, database_manager, parent=None):
        super().__init__(parent)
        self.database_manager = database_manager
        self.export_thread = None
        self.export_result = None
        
        self.setWindowTitle("一键导出所有附件")
        self.setModal(True)
        self.resize(1000, 700)  # 增大窗口尺寸
        
        self.setup_ui()
        
    def setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)  # 减小组件间距
        
        # 说明文本 - 减小高度
        info_label = QLabel("此功能将扫描所有数据库，自动识别并导出大于150字节的二进制文件，按类型分类保存到 ./output/ 目录中。")
        info_label.setWordWrap(True)
        info_label.setMaximumHeight(40)  # 限制高度
        info_label.setStyleSheet("color: #666; padding: 8px; background-color: #f8f8f8; border-radius: 4px; font-size: 12px;")
        layout.addWidget(info_label)
        
        # 导出选项组 - 压缩高度
        options_group = QGroupBox("导出选项(不勾选则默认按文件类型导出)")
        options_group.setMaximumHeight(80)  # 限制高度
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(10, 5, 10, 5)  # 减小边距
        
        # 按包导出选项
        self.export_by_package_checkbox = QCheckBox("按照应用包名分文件夹导出")
        self.export_by_package_checkbox.setToolTip("勾选后将按包名创建文件夹，文件命名为：数据库名_序号.扩展名")
        options_layout.addWidget(self.export_by_package_checkbox)
        
        layout.addWidget(options_group)
        
        # 进度组 - 压缩高度
        progress_group = QGroupBox("导出进度")
        progress_group.setMaximumHeight(90)  # 限制高度
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setContentsMargins(10, 5, 10, 5)  # 减小边距
        
        self.status_label = QLabel("点击「开始导出」按钮开始...")
        progress_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        layout.addWidget(progress_group)
        
        # 使用分割器来更好地分配空间
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 结果组 - 这是主要内容区域，给予更多空间
        result_group = QGroupBox("导出结果")
        result_layout = QVBoxLayout(result_group)
        result_layout.setContentsMargins(10, 10, 10, 10)
        
        # 统计信息 - 减小高度
        self.stats_label = QLabel("等待开始导出...")
        self.stats_label.setFont(QFont("", 10, QFont.Weight.Bold))
        self.stats_label.setMaximumHeight(30)  # 限制高度
        result_layout.addWidget(self.stats_label)
        
        # 文件列表 - 这是主要展示区域
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["文件名/类型", "大小", "详细路径"])
        self.result_tree.setVisible(False)
        self.result_tree.setMinimumHeight(300)  # 设置最小高度
        # 设置列宽比例
        self.result_tree.setColumnWidth(0, 250)
        self.result_tree.setColumnWidth(1, 100)
        self.result_tree.setColumnWidth(2, 400)
        
        # 添加右键菜单
        self.result_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_tree.customContextMenuRequested.connect(self.show_context_menu)
        
        result_layout.addWidget(self.result_tree)
        
        splitter.addWidget(result_group)
        
        # 详细日志 - 压缩到较小区域
        log_group = QGroupBox("详细日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(10, 5, 10, 5)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(120)  # 限制日志区域高度
        self.log_text.setVisible(False)
        self.log_text.setStyleSheet("font-family: Consolas, Monaco, monospace; font-size: 11px;")
        log_layout.addWidget(self.log_text)
        
        splitter.addWidget(log_group)
        
        # 设置分割器比例 - 结果区域占大部分空间
        splitter.setStretchFactor(0, 3)  # 结果区域占3/4
        splitter.setStretchFactor(1, 1)  # 日志区域占1/4
        
        layout.addWidget(splitter)
        
        # 按钮组 - 压缩高度
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 5, 0, 0)
        
        self.start_button = QPushButton("🚀 开始导出")
        self.start_button.clicked.connect(self.start_export)
        self.start_button.setMinimumHeight(35)  # 设置按钮高度
        button_layout.addWidget(self.start_button)
        
        self.open_folder_button = QPushButton("📁 打开输出文件夹")
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.setMinimumHeight(35)  # 设置按钮高度
        button_layout.addWidget(self.open_folder_button)
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.close)
        self.close_button.setMinimumHeight(35)  # 设置按钮高度
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
    def show_context_menu(self, position):
        """显示右键菜单"""
        item = self.result_tree.itemAt(position)
        if not item:
            return
        
        # 只有文件项才显示右键菜单（不是文件夹项）
        if not item.parent():  # 如果是顶级项（文件夹），不显示菜单
            return
            
        # 获取文件路径
        file_path = self.get_file_path_from_item(item)
        if not file_path or not os.path.exists(file_path):
            return
        
        menu = QMenu(self)
        
        # 打开文件
        open_action = QAction("🔍 打开文件", self)
        open_action.triggered.connect(lambda: self.open_file(file_path))
        menu.addAction(open_action)
        
        # 在文件管理器中显示
        show_action = QAction("📁 在文件管理器中显示", self)
        show_action.triggered.connect(lambda: self.show_in_explorer(file_path))
        menu.addAction(show_action)
        
        # 复制文件路径
        copy_action = QAction("📋 复制文件路径", self)
        copy_action.triggered.connect(lambda: self.copy_file_path(file_path))
        menu.addAction(copy_action)
        
        menu.exec(self.result_tree.mapToGlobal(position))
    
    def get_file_path_from_item(self, item):
        """从树项获取文件路径"""
        if not item.parent():
            return None
        
        # 首先尝试从存储的数据中获取文件路径
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path and os.path.exists(file_path):
            return file_path
        
        # 如果没有存储的路径，尝试从界面文本解析
        file_name = item.text(0)
        parent_item = item.parent()
        parent_text = parent_item.text(2)  # 详细信息列
        
        if "保存在" in parent_text:
            # 解析路径，例如 "保存在 ./output/images/ 目录"
            import re
            match = re.search(r'保存在\s+(.+)\s+目录', parent_text)
            if match:
                dir_path = match.group(1)
                return os.path.join(dir_path, file_name)
        
        return None
    
    def open_file(self, file_path):
        """打开文件"""
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", file_path])
            else:  # Linux
                subprocess.run(["xdg-open", file_path])
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法打开文件: {e}")
    
    def show_in_explorer(self, file_path):
        """在文件管理器中显示文件"""
        try:
            # 转换为绝对路径
            abs_path = os.path.abspath(file_path)
            
            if platform.system() == "Windows":
                # Windows下使用explorer命令选中文件
                subprocess.run(f'explorer /select,"{abs_path}"', shell=True)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", "-R", abs_path])
            else:  # Linux
                subprocess.run(["xdg-open", os.path.dirname(abs_path)])
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法在文件管理器中显示文件: {e}")
    
    def copy_file_path(self, file_path):
        """复制文件路径到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(file_path)
        self.status_label.setText(f"已复制文件路径: {os.path.basename(file_path)}")

    def start_export(self):
        """开始导出"""
        self.start_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.result_tree.setVisible(False)
        self.log_text.setVisible(False)
        
        self.status_label.setText("正在扫描数据库...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度
        
        # 获取导出选项
        export_by_package = self.export_by_package_checkbox.isChecked()
        
        # 启动导出线程
        self.export_thread = ExportThread(self.database_manager, export_by_package)
        self.export_thread.progress.connect(self.update_progress)
        self.export_thread.finished.connect(self.export_finished)
        self.export_thread.error.connect(self.export_error)
        self.export_thread.start()
        
    def update_progress(self, processed):
        """更新进度"""
        self.status_label.setText(f"正在处理... 已处理 {processed} 行数据")
        
    def export_finished(self, result):
        """导出完成"""
        self.export_result = result
        self.start_button.setEnabled(True)
        self.open_folder_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        total_files = result['total_files']
        files_by_type = result.get('files_by_type', {})
        export_mode = result.get('export_mode', 'by_type')
        
        if total_files == 0:
            self.status_label.setText("导出完成 - 未发现任何附件文件")
            self.stats_label.setText("没有找到符合条件的附件文件")
            return
        
        self.status_label.setText(f"导出完成！共导出 {total_files} 个文件")
        
        if export_mode == 'by_package':
            packages_count = len(result.get('files_by_package', {}))
            self.stats_label.setText(f"成功导出 {total_files} 个附件文件，按 {packages_count} 个包分类")
        else:
            self.stats_label.setText(f"成功导出 {total_files} 个附件文件，按 {len(files_by_type)} 种类型分类")
        
        # 显示结果树
        self.result_tree.setVisible(True)
        self.result_tree.clear()
        
        if export_mode == 'by_package':
            # 按包分组显示
            files_by_package = result.get('files_by_package', {})
            for package_name, package_files in files_by_package.items():
                package_item = QTreeWidgetItem(self.result_tree)
                package_item.setText(0, f"📦 {package_name}")
                package_item.setText(1, f"{len(package_files)} 个文件")
                package_item.setText(2, f"保存在 ./output/{package_name}/ 目录")
                
                # 添加该包的文件详情
                for file_info in package_files:
                    file_item = QTreeWidgetItem(package_item)
                    file_item.setText(0, os.path.basename(file_info['file_path']))
                    file_item.setText(1, f"{file_info['file_size']} 字节")
                    file_item.setText(2, f"来源: {file_info['database']}/{file_info['table']}/{file_info['column']}")
                    # 存储完整文件路径用于右键菜单
                    file_item.setData(0, Qt.ItemDataRole.UserRole, file_info['file_path'])
        else:
            # 按文件类型分组显示
            for file_type, count in files_by_type.items():
                type_item = QTreeWidgetItem(self.result_tree)
                type_item.setText(0, f"📁 {file_type} 文件")
                type_item.setText(1, f"{count} 个文件")
                type_item.setText(2, f"保存在 ./output/{file_type[1:]}/ 目录")
                
                # 添加该类型的文件详情 - 显示所有文件
                type_files = [f for f in result['exported_files'] if f['file_type'] == file_type]
                for file_info in type_files:  # 显示所有文件
                    file_item = QTreeWidgetItem(type_item)
                    file_item.setText(0, os.path.basename(file_info['file_path']))
                    file_item.setText(1, f"{file_info['file_size']} 字节")
                    file_item.setText(2, f"来源: {file_info['package']}/{file_info['database']}/{file_info['table']}/{file_info['column']}")
                    # 存储完整文件路径用于右键菜单
                    file_item.setData(0, Qt.ItemDataRole.UserRole, file_info['file_path'])
        
        self.result_tree.expandAll()
        
        # 显示详细日志
        self.log_text.setVisible(True)
        log_content = f"导出统计:\n"
        log_content += f"总文件数: {total_files}\n"
        log_content += f"输出目录: {result['output_directory']}\n"
        log_content += f"导出模式: {'按包分类' if export_mode == 'by_package' else '按类型分类'}\n\n"
        
        if export_mode == 'by_package':
            log_content += "包分布:\n"
            files_by_package = result.get('files_by_package', {})
            for package_name, package_files in files_by_package.items():
                log_content += f"  {package_name}: {len(package_files)} 个文件\n"
        else:
            log_content += "文件类型分布:\n"
            for file_type, count in files_by_type.items():
                log_content += f"  {file_type}: {count} 个文件\n"
        
        self.log_text.setText(log_content)
        
        # 显示成功消息
        mode_text = "按包分类" if export_mode == 'by_package' else "按类型分类"
        QMessageBox.information(self, "导出成功", 
                               f"成功导出 {total_files} 个附件文件！\n"
                               f"文件已保存到 ./output/ 目录中，{mode_text}存放。")
        
    def export_error(self, error_msg):
        """导出出错"""
        self.start_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"导出失败: {error_msg}")
        
        QMessageBox.critical(self, "导出失败", f"导出过程中发生错误:\n{error_msg}")
        
    def open_output_folder(self):
        """打开输出文件夹"""
        output_dir = os.path.abspath("./output")
        if not os.path.exists(output_dir):
            QMessageBox.warning(self, "警告", "输出目录不存在！")
            return
        
        try:
            if platform.system() == "Windows":
                os.startfile(output_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", output_dir])
            else:  # Linux
                subprocess.run(["xdg-open", output_dir])
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法打开文件夹: {e}")
            
    def closeEvent(self, event):
        """关闭事件"""
        if self.export_thread and self.export_thread.isRunning():
            reply = QMessageBox.question(self, "确认", "导出正在进行中，确定要关闭吗？",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.export_thread.terminate()
                if not self.export_thread.wait(3000):  # 最多等待3秒
                    print("导出线程未能正常结束")
                event.accept()
            else:
                event.ignore()
        else:
            event.accept() 