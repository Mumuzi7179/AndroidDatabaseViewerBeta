from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QProgressBar, QPushButton, QTextEdit, QGroupBox,
                               QTreeWidget, QTreeWidgetItem, QMessageBox, QApplication,
                               QCheckBox)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont
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
        self.resize(800, 600)
        
        self.setup_ui()
        
    def setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        
        # 说明文本
        info_label = QLabel("此功能将扫描所有数据库，自动识别并导出大于150字节的二进制文件。\n"
                           "导出的文件将按类型分类保存到 ./output/ 目录中。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(info_label)
        
        # 导出选项组
        options_group = QGroupBox("导出选项")
        options_layout = QVBoxLayout(options_group)
        
        # 按包导出选项
        self.export_by_package_checkbox = QCheckBox("按照文件夹导出")
        self.export_by_package_checkbox.setToolTip("勾选后将按包名创建文件夹，文件命名为：数据库名_序号.扩展名")
        options_layout.addWidget(self.export_by_package_checkbox)
        
        layout.addWidget(options_group)
        
        # 进度组
        progress_group = QGroupBox("导出进度")
        progress_layout = QVBoxLayout(progress_group)
        
        self.status_label = QLabel("准备开始...")
        progress_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        layout.addWidget(progress_group)
        
        # 结果组
        result_group = QGroupBox("导出结果")
        result_layout = QVBoxLayout(result_group)
        
        # 统计信息
        self.stats_label = QLabel("等待开始导出...")
        self.stats_label.setFont(QFont("", 10, QFont.Weight.Bold))
        result_layout.addWidget(self.stats_label)
        
        # 文件列表
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["文件类型", "大小", "详细信息"])
        self.result_tree.setVisible(False)
        result_layout.addWidget(self.result_tree)
        
        # 详细日志
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setVisible(False)
        result_layout.addWidget(self.log_text)
        
        layout.addWidget(result_group)
        
        # 按钮组
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("开始导出")
        self.start_button.clicked.connect(self.start_export)
        button_layout.addWidget(self.start_button)
        
        self.open_folder_button = QPushButton("打开输出文件夹")
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.open_folder_button.setEnabled(False)
        button_layout.addWidget(self.open_folder_button)
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
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
                    file_item.setText(2, f"{file_info['database']}/{file_info['table']}/{file_info['column']}")
        else:
            # 按文件类型分组显示
            for file_type, count in files_by_type.items():
                type_item = QTreeWidgetItem(self.result_tree)
                type_item.setText(0, f"{file_type} 文件")
                type_item.setText(1, f"{count} 个文件")
                type_item.setText(2, f"保存在 ./output/{file_type[1:]}/ 目录")
                
                # 添加该类型的文件详情 - 显示所有文件
                type_files = [f for f in result['exported_files'] if f['file_type'] == file_type]
                for file_info in type_files:  # 显示所有文件
                    file_item = QTreeWidgetItem(type_item)
                    file_item.setText(0, os.path.basename(file_info['file_path']))
                    file_item.setText(1, f"{file_info['file_size']} 字节")
                    file_item.setText(2, f"{file_info['package']}/{file_info['database']}/{file_info['table']}/{file_info['column']}")
        
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