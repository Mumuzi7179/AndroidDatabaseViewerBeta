# -*- coding: utf-8 -*-
"""
AI分析对话框
提供AI分析功能，包括配置、一键分析和正常提问
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox, QSplitter,
    QMessageBox, QProgressBar, QScrollArea, QFrame, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPalette
import json
from datetime import datetime
from typing import Dict, Any, List
from functools import partial

from ..core.ai_config import AIConfig, AIConfigManager
from ..core.ai_analyzer import AIAnalyzer, AnalysisResult
from ..core.ai_history import AIHistoryManager


class ChatThread(QThread):
    """AI对话线程"""
    chat_completed = Signal(str)  # 对话结果
    chat_error = Signal(str)     # 对话错误
    
    def __init__(self, analyzer: AIAnalyzer, message: str):
        super().__init__()
        self.analyzer = analyzer
        self.message = message
    
    def run(self):
        try:
            response = self.analyzer.chat(self.message)
            self.chat_completed.emit(response)
        except Exception as e:
            self.chat_error.emit(str(e))


class ConnectionTestThread(QThread):
    """连接测试线程"""
    test_completed = Signal(bool, str)  # 成功标志, 消息
    
    def __init__(self, analyzer: AIAnalyzer):
        super().__init__()
        self.analyzer = analyzer
    
    def run(self):
        try:
            success, message = self.analyzer.test_connection()
            self.test_completed.emit(success, message)
        except Exception as e:
            self.test_completed.emit(False, f"测试异常: {str(e)}")


class AnalysisThread(QThread):
    """一键分析线程"""
    analysis_progress = Signal(str, int)  # 消息, 进度百分比
    analysis_completed = Signal(list)  # 分析结果列表
    analysis_error = Signal(str)
    
    def __init__(self, analyzer: AIAnalyzer, database_manager, packages, simple_mode=False):
        super().__init__()
        self.analyzer = analyzer
        self.database_manager = database_manager
        self.packages = packages
        self.simple_mode = simple_mode  # 是否为简单模式（只解析结构）
        self.is_cancelled = False
    
    def cancel(self):
        """取消分析"""
        self.is_cancelled = True
    
    def run(self):
        """执行一键分析"""
        try:
            # 筛选出非系统应用
            non_system_apps = [pkg for pkg in self.packages if not pkg.is_system_app and pkg.database_files]
            
            if not non_system_apps:
                self.analysis_error.emit("未找到非系统应用")
                return
            
            self.analysis_progress.emit(f"开始分析 {len(non_system_apps)} 个非系统应用...", 0)
            
            results = []
            total_apps = len(non_system_apps)
            
            for i, package in enumerate(non_system_apps):
                if self.is_cancelled:
                    break
                
                progress = int((i / total_apps) * 100)
                self.analysis_progress.emit(f"正在分析: {package.package_name}", progress)
                
                try:
                    # 获取应用的数据库数据
                    database_data = self._extract_database_data(package)
                    
                    # 调用AI分析
                    result = self.analyzer.analyze_single_app(package.package_name, database_data)
                    results.append(result)
                    
                except Exception as e:
                    # 即使单个应用分析失败，也要记录并继续
                    error_result = AnalysisResult(
                        package_name=package.package_name,
                        app_type="分析失败",
                        data_summary=f"分析时发生错误: {str(e)}",
                        forensic_value="无法评估",
                        key_findings=[f"错误: {str(e)}"],
                        risk_level="未知"
                    )
                    results.append(error_result)
            
            if not self.is_cancelled:
                self.analysis_progress.emit("分析完成", 100)
                self.analysis_completed.emit(results)
                
        except Exception as e:
            self.analysis_error.emit(f"分析过程中发生错误: {str(e)}")
    
    def _extract_database_data(self, package) -> Dict[str, Any]:
        """提取包的数据库数据"""
        database_data = {}
        
        for parent_dir, db_files in package.database_files.items():
            for db_file in db_files:
                db_name = db_file.file_name
                db_key = f"{parent_dir}/{db_name}"
                
                # 获取数据库表信息
                database_data[db_key] = {"tables": {}}
                
                try:
                    # 从数据库管理器获取表信息
                    if package.package_name in self.database_manager.databases:
                        package_dbs = self.database_manager.databases[package.package_name]
                        if parent_dir in package_dbs and db_name in package_dbs[parent_dir]:
                            db_info = package_dbs[parent_dir][db_name]
                            
                            for table_name in db_info.tables:
                                try:
                                    # 获取表结构
                                    table_info = self.database_manager.get_table_info(
                                        package.package_name, parent_dir, db_name, table_name
                                    )
                                    
                                    if table_info:
                                        # 只获取第一行数据用于结构分析
                                        row_count = table_info.row_count
                                        
                                        if self.simple_mode:
                                            # 简单模式：只获取结构，不获取数据
                                            columns, sample_rows = self.database_manager.get_table_data(
                                                package.package_name, parent_dir, db_name, table_name, 
                                                limit=0, offset=0
                                            )
                                        else:
                                            # 完整模式：获取第一行数据
                                            if row_count > 0:
                                                # 有数据的表，获取第一行
                                                columns, sample_rows = self.database_manager.get_table_data(
                                                    package.package_name, parent_dir, db_name, table_name, 
                                                    limit=1, offset=0
                                                )
                                            else:
                                                # 空表，只获取结构
                                                columns, sample_rows = self.database_manager.get_table_data(
                                                    package.package_name, parent_dir, db_name, table_name, 
                                                    limit=0, offset=0
                                                )
                                        
                                        database_data[db_key]["tables"][table_name] = {
                                            "columns": columns,
                                            "sample_data": sample_rows,
                                            "row_count": table_info.row_count
                                        }
                                except Exception as e:
                                    print(f"获取表 {table_name} 数据失败: {e}")
                                    continue
                except Exception as e:
                    print(f"获取数据库 {db_name} 信息失败: {e}")
                    continue
        
        return database_data


class AIConfigDialog(QDialog):
    """AI配置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_manager = AIConfigManager()
        self.config = self.config_manager.load_config()
        self.init_ui()
        self.load_config_to_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("AI配置")
        self.setMinimumSize(500, 600)
        
        layout = QVBoxLayout(self)
        
        # AI类型选择
        type_group = QGroupBox("AI类型")
        type_layout = QVBoxLayout(type_group)
        
        self.ai_type_combo = QComboBox()
        self.ai_type_combo.addItems(["remote", "local"])
        self.ai_type_combo.currentTextChanged.connect(self.on_ai_type_changed)
        type_layout.addWidget(QLabel("AI类型:"))
        type_layout.addWidget(self.ai_type_combo)
        
        layout.addWidget(type_group)
        
        # 远程AI配置
        self.remote_group = QGroupBox("远程AI配置 (如 OpenAI, Claude)")
        remote_layout = QVBoxLayout(self.remote_group)
        
        self.remote_api_key = QLineEdit()
        self.remote_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        remote_layout.addWidget(QLabel("API Key:"))
        remote_layout.addWidget(self.remote_api_key)
        
        self.remote_api_url = QLineEdit()
        remote_layout.addWidget(QLabel("API URL:"))
        remote_layout.addWidget(self.remote_api_url)
        
        self.remote_model = QLineEdit()
        remote_layout.addWidget(QLabel("模型名称:"))
        remote_layout.addWidget(self.remote_model)
        
        self.remote_timeout = QSpinBox()
        self.remote_timeout.setRange(10, 300)
        self.remote_timeout.setSuffix(" 秒")
        remote_layout.addWidget(QLabel("超时时间:"))
        remote_layout.addWidget(self.remote_timeout)
        
        layout.addWidget(self.remote_group)
        
        # 本地AI配置
        self.local_group = QGroupBox("本地AI配置 (如 LM Studio)")
        local_layout = QVBoxLayout(self.local_group)
        
        self.local_api_url = QLineEdit()
        local_layout.addWidget(QLabel("API URL:"))
        local_layout.addWidget(self.local_api_url)
        
        self.local_model = QLineEdit()
        self.local_model.setPlaceholderText("留空即可，LM Studio会自动使用已加载的模型")
        local_layout.addWidget(QLabel("模型名称 (可选):"))
        local_layout.addWidget(self.local_model)
        
        self.local_timeout = QSpinBox()
        self.local_timeout.setRange(10, 600)
        self.local_timeout.setSuffix(" 秒")
        local_layout.addWidget(QLabel("超时时间:"))
        local_layout.addWidget(self.local_timeout)
        
        layout.addWidget(self.local_group)
        
        # 分析配置
        analysis_group = QGroupBox("分析配置")
        analysis_layout = QVBoxLayout(analysis_group)
        
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(100, 8000)
        analysis_layout.addWidget(QLabel("最大Token数:"))
        analysis_layout.addWidget(self.max_tokens)
        
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setDecimals(1)
        analysis_layout.addWidget(QLabel("Temperature:"))
        analysis_layout.addWidget(self.temperature)
        
        layout.addWidget(analysis_group)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self.test_connection)
        button_layout.addWidget(self.test_btn)
        
        button_layout.addStretch()
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_config)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # 初始显示状态
        self.on_ai_type_changed()
    
    def on_ai_type_changed(self):
        """AI类型改变时的处理"""
        ai_type = self.ai_type_combo.currentText()
        self.remote_group.setVisible(ai_type == "remote")
        self.local_group.setVisible(ai_type == "local")
    
    def load_config_to_ui(self):
        """加载配置到界面"""
        # AI类型
        index = self.ai_type_combo.findText(self.config.ai_type)
        if index >= 0:
            self.ai_type_combo.setCurrentIndex(index)
        
        # 远程AI配置
        self.remote_api_key.setText(self.config.remote_api_key)
        self.remote_api_url.setText(self.config.remote_api_url)
        self.remote_model.setText(self.config.remote_model)
        self.remote_timeout.setValue(self.config.remote_timeout)
        
        # 本地AI配置
        self.local_api_url.setText(self.config.local_api_url)
        self.local_model.setText(self.config.local_model)
        self.local_timeout.setValue(self.config.local_timeout)
        
        # 分析配置
        self.max_tokens.setValue(self.config.max_tokens)
        self.temperature.setValue(self.config.temperature)
    
    def save_config(self):
        """保存配置"""
        # 构建新配置
        new_config = AIConfig(
            ai_type=self.ai_type_combo.currentText(),
            remote_api_key=self.remote_api_key.text(),
            remote_api_url=self.remote_api_url.text(),
            remote_model=self.remote_model.text(),
            remote_timeout=self.remote_timeout.value(),
            local_api_url=self.local_api_url.text(),
            local_model=self.local_model.text(),
            local_timeout=self.local_timeout.value(),
            max_tokens=self.max_tokens.value(),
            temperature=self.temperature.value()
        )
        
        # 保存配置
        if self.config_manager.save_config(new_config):
            QMessageBox.information(self, "成功", "配置保存成功")
            self.config = new_config
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "配置保存失败")
    
    def test_connection(self):
        """测试连接"""
        # 临时创建配置进行测试
        test_config = AIConfig(
            ai_type=self.ai_type_combo.currentText(),
            remote_api_key=self.remote_api_key.text(),
            remote_api_url=self.remote_api_url.text(),
            remote_model=self.remote_model.text(),
            remote_timeout=self.remote_timeout.value(),
            local_api_url=self.local_api_url.text(),
            local_model=self.local_model.text(),
            local_timeout=self.local_timeout.value(),
            max_tokens=self.max_tokens.value(),
            temperature=self.temperature.value()
        )
        
        # 创建分析器进行测试
        analyzer = AIAnalyzer()
        analyzer.update_config(test_config)
        
        # 显示进度提示
        self.test_btn = self.sender()
        self.test_btn.setText("测试中...")
        self.test_btn.setEnabled(False)
        
        # 使用线程进行测试
        self.test_thread = ConnectionTestThread(analyzer)
        self.test_thread.test_completed.connect(self.on_test_completed)
        self.test_thread.finished.connect(self.on_test_finished)
        self.test_thread.start()
    
    def on_test_completed(self, success: bool, message: str):
        """测试完成"""
        if success:
            QMessageBox.information(self, "连接测试", f"✓ {message}")
        else:
            QMessageBox.warning(self, "连接测试", f"✗ {message}")
    
    def on_test_finished(self):
        """测试线程结束"""
        self.test_btn.setText("测试连接")
        self.test_btn.setEnabled(True)


class AIAnalysisDialog(QDialog):
    """AI分析主对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.database_manager = None
        self.packages = []
        self.analyzer = AIAnalyzer()
        self.analysis_thread = None
        
        # 初始化历史数据管理器
        self.history_manager = AIHistoryManager("ai_history.json")
        
        self.setWindowTitle("AI分析助手")
        self.setMinimumSize(1000, 700)
        self.init_ui()
        
        # 加载历史数据
        self.load_history_data()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 顶部工具栏
        toolbar_layout = QHBoxLayout()
        
        self.settings_btn = QPushButton("⚙️ 设置")
        self.settings_btn.clicked.connect(self.show_settings)
        toolbar_layout.addWidget(self.settings_btn)
        
        # 分析选项
        self.simple_analysis_cb = QCheckBox("仅解析库、列、表名 (不解析字段内容)")
        self.simple_analysis_cb.setToolTip("勾选此项将只分析数据库结构，不读取具体的数据内容，分析速度更快")
        toolbar_layout.addWidget(self.simple_analysis_cb)
        
        toolbar_layout.addStretch()
        
        self.one_click_btn = QPushButton("🔍 一键分析")
        self.one_click_btn.clicked.connect(self.start_one_click_analysis)
        toolbar_layout.addWidget(self.one_click_btn)        
        
        self.stop_analysis_btn = QPushButton("⏹️ 停止分析")
        self.stop_analysis_btn.clicked.connect(self.stop_one_click_analysis)
        self.stop_analysis_btn.setEnabled(False)
        self.stop_analysis_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        toolbar_layout.addWidget(self.stop_analysis_btn)
        
        toolbar_layout.addStretch()
        
        # 状态标签
        self.status_label = QLabel("请先配置AI设置")
        self.status_label.setStyleSheet("color: #666;")
        toolbar_layout.addWidget(self.status_label)
        
        layout.addLayout(toolbar_layout)
        
        # 主要内容区域
        self.tab_widget = QTabWidget()
        
        # 一键分析结果标签页
        self.analysis_tab = QWidget()
        self.init_analysis_tab()
        self.tab_widget.addTab(self.analysis_tab, "📊 分析结果")
        
        # 对话标签页
        self.chat_tab = QWidget()
        self.init_chat_tab()
        self.tab_widget.addTab(self.chat_tab, "💬 AI对话")
        
        layout.addWidget(self.tab_widget)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 检查配置状态
        self.check_config_status()
    
    def init_analysis_tab(self):
        """初始化分析结果标签页"""
        layout = QVBoxLayout(self.analysis_tab)
        
        # 工具栏
        toolbar_layout = QHBoxLayout()
        
        self.export_btn = QPushButton("📤 导出结果")
        self.export_btn.clicked.connect(self.export_analysis_results)
        self.export_btn.setEnabled(False)
        toolbar_layout.addWidget(self.export_btn)
        
        self.clear_btn = QPushButton("🗑️ 清空结果")
        self.clear_btn.clicked.connect(self.clear_analysis_results)
        self.clear_btn.setEnabled(False)
        toolbar_layout.addWidget(self.clear_btn)
        
        toolbar_layout.addStretch()
        
        layout.addLayout(toolbar_layout)
        
        # 分析结果显示区域
        self.analysis_scroll = QScrollArea()
        self.analysis_content = QWidget()
        self.analysis_layout = QVBoxLayout(self.analysis_content)
        self.analysis_scroll.setWidget(self.analysis_content)
        self.analysis_scroll.setWidgetResizable(True)
        
        layout.addWidget(self.analysis_scroll)
        
        # 初始提示
        self.show_analysis_hint()
    
    def init_chat_tab(self):
        """初始化对话标签页"""
        layout = QVBoxLayout(self.chat_tab)
        
        # 对话历史
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.chat_history)
        
        # 输入区域
        input_layout = QHBoxLayout()
        
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入您的问题...")
        self.chat_input.returnPressed.connect(self.send_chat_message)
        input_layout.addWidget(self.chat_input)
        
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_chat_message)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(input_layout)
        
        # 预设问题
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("快速问题:"))
        
        preset_questions = [
            "分析一下这些应用的风险等级",
            "哪些应用可能包含敏感信息",
            "从取证角度看哪些数据最重要"
        ]
        
        for question in preset_questions:
            btn = QPushButton(question)
            # 使用partial避免闭包问题
            from functools import partial
            btn.clicked.connect(partial(self.ask_preset_question, question))
            preset_layout.addWidget(btn)
        
        layout.addLayout(preset_layout)
        
        # 初始化对话
        self.chat_history.append(f"<div style='color: #666; font-style: italic;'>[{datetime.now().strftime('%H:%M:%S')}] AI助手已准备就绪，您可以询问任何关于Android数据分析的问题。</div>")
    
    def show_analysis_hint(self):
        """显示分析提示"""
        hint_widget = QWidget()
        hint_layout = QVBoxLayout(hint_widget)
        
        hint_label = QLabel("🤖 AI分析助手")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2; margin: 20px;")
        hint_layout.addWidget(hint_label)
        
        desc_label = QLabel("点击「一键分析」按钮，AI将自动分析所有非系统应用的数据库内容，\n从取证角度评估每个应用的价值和风险等级。")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("font-size: 14px; color: #666; margin: 10px;")
        hint_layout.addWidget(desc_label)
        
        hint_layout.addStretch()
        
        self.analysis_layout.addWidget(hint_widget)
    
    def set_database_manager(self, database_manager):
        """设置数据库管理器"""
        self.database_manager = database_manager
    
    def set_packages(self, packages):
        """设置包列表"""
        self.packages = packages
        
        # 更新状态
        non_system_count = len([pkg for pkg in packages if not pkg.is_system_app and pkg.database_files])
        if non_system_count > 0:
            self.status_label.setText(f"检测到 {non_system_count} 个非系统应用可供分析")
        else:
            self.status_label.setText("未检测到非系统应用")
    
    def check_config_status(self):
        """检查配置状态"""
        if self.analyzer.config_manager.is_configured():
            self.status_label.setText("✓ AI已配置")
            self.one_click_btn.setEnabled(True)
            self.send_btn.setEnabled(True)
        else:
            self.status_label.setText("⚠️ 请先配置AI设置")
            self.one_click_btn.setEnabled(False)
            self.send_btn.setEnabled(False)
    
    def show_settings(self):
        """显示设置对话框"""
        dialog = AIConfigDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 更新分析器配置
            self.analyzer.update_config(dialog.config)
            self.check_config_status()
    
    def start_one_click_analysis(self):
        """开始一键分析"""
        if not self.database_manager or not self.packages:
            QMessageBox.warning(self, "警告", "请先加载数据包")
            return
        
        # 检查是否有非系统应用
        non_system_apps = [pkg for pkg in self.packages if not pkg.is_system_app and pkg.database_files]
        if not non_system_apps:
            QMessageBox.information(self, "提示", "未找到非系统应用")
            return
        
        # 确认开始分析
        reply = QMessageBox.question(
            self, "确认分析", 
            f"将分析 {len(non_system_apps)} 个非系统应用，这可能需要几分钟时间。\n\n确定开始分析吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 清空之前的结果
        self.clear_analysis_results()
        
        # 检查是否为简单模式
        simple_mode = self.simple_analysis_cb.isChecked()
        
        # 开始分析
        self.analysis_thread = AnalysisThread(self.analyzer, self.database_manager, self.packages, simple_mode)
        self.analysis_thread.analysis_progress.connect(self.on_analysis_progress)
        self.analysis_thread.analysis_completed.connect(self.on_analysis_completed)
        self.analysis_thread.analysis_error.connect(self.on_analysis_error)
        self.analysis_thread.finished.connect(self.on_analysis_finished)
        
        self.analysis_thread.start()
        
        # 更新界面状态
        self.progress_bar.setVisible(True)
        self.one_click_btn.setEnabled(False)
        self.stop_analysis_btn.setEnabled(True)
        self.tab_widget.setCurrentIndex(0)  # 切换到分析结果标签页
    
    def on_analysis_progress(self, message: str, progress: int):
        """分析进度更新"""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
    
    def on_analysis_completed(self, results: List[AnalysisResult]):
        """分析完成"""
        self.display_analysis_results(results)
        self.export_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        
        # 保存分析结果到历史
        self.history_manager.save_analysis_results(results)
        self.history_manager.save_history()
    
    def on_analysis_error(self, error_message: str):
        """分析错误"""
        QMessageBox.critical(self, "分析错误", error_message)
    
    def on_analysis_finished(self):
        """分析线程结束"""
        self.progress_bar.setVisible(False)
        self.one_click_btn.setEnabled(True)
        self.stop_analysis_btn.setEnabled(False)
        self.status_label.setText("分析完成")
    
    def stop_one_click_analysis(self):
        """停止一键分析"""
        if hasattr(self, 'analysis_thread') and self.analysis_thread.isRunning():
            self.analysis_thread.cancel()
            self.analysis_thread.quit()
            self.analysis_thread.wait()  # 等待线程结束
            
            # 更新界面状态
            self.progress_bar.setVisible(False)
            self.one_click_btn.setEnabled(True)
            self.stop_analysis_btn.setEnabled(False)
            self.status_label.setText("分析已停止")
    
    def display_analysis_results(self, results: List[AnalysisResult]):
        """显示分析结果"""
        # 安全地清空之前的内容
        for i in reversed(range(self.analysis_layout.count())):
            item = self.analysis_layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                else:
                    # 处理布局或spacer等非widget项目
                    self.analysis_layout.removeItem(item)
        
        # 添加结果标题
        title_label = QLabel(f"📊 分析结果 ({len(results)} 个应用)")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; margin: 10px;")
        self.analysis_layout.addWidget(title_label)
        
        # 按风险等级分组显示
        risk_order = {"高": 0, "中": 1, "低": 2, "未知": 3}
        sorted_results = sorted(results, key=lambda r: risk_order.get(r.risk_level, 3))
        
        for result in sorted_results:
            result_widget = self.create_result_widget(result)
            self.analysis_layout.addWidget(result_widget)
        
        self.analysis_layout.addStretch()
    
    def create_result_widget(self, result: AnalysisResult) -> QWidget:
        """创建单个结果显示组件"""
        widget = QFrame()
        widget.setFrameStyle(QFrame.Shape.Box)
        widget.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                margin: 5px;
                padding: 10px;
            }
        """)
        
        layout = QVBoxLayout(widget)
        
        # 标题行
        title_layout = QHBoxLayout()
        
        # 应用名称
        app_name_label = QLabel(f"📱 {result.package_name}")
        app_name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")
        title_layout.addWidget(app_name_label)
        
        title_layout.addStretch()
        
        # 应用类型
        type_label = QLabel(f"类型: {result.app_type}")
        type_label.setStyleSheet("font-size: 12px; color: #6c757d; background-color: #e9ecef; padding: 2px 8px; border-radius: 4px;")
        title_layout.addWidget(type_label)
        
        # 风险等级
        risk_color = {"高": "#dc3545", "中": "#fd7e14", "低": "#28a745", "未知": "#6c757d"}
        risk_label = QLabel(f"风险: {result.risk_level}")
        risk_label.setStyleSheet(f"font-size: 12px; color: white; background-color: {risk_color.get(result.risk_level, '#6c757d')}; padding: 2px 8px; border-radius: 4px;")
        title_layout.addWidget(risk_label)
        
        layout.addLayout(title_layout)
        
        # 数据摘要
        summary_label = QLabel(f"📋 数据摘要: {result.data_summary}")
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet("font-size: 12px; color: #495057; margin: 5px 0;")
        layout.addWidget(summary_label)
        
        # 取证价值
        forensic_label = QLabel(f"🔍 取证价值: {result.forensic_value}")
        forensic_label.setWordWrap(True)
        forensic_label.setStyleSheet("font-size: 12px; color: #495057; margin: 5px 0;")
        layout.addWidget(forensic_label)
        
        # 关键发现
        if result.key_findings:
            findings_label = QLabel("🔑 关键发现:")
            findings_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #495057; margin: 5px 0;")
            layout.addWidget(findings_label)
            
            for finding in result.key_findings:
                finding_label = QLabel(f"  • {finding}")
                finding_label.setWordWrap(True)
                finding_label.setStyleSheet("font-size: 11px; color: #6c757d; margin-left: 10px;")
                layout.addWidget(finding_label)
        
        return widget
    
    def clear_analysis_results(self):
        """清空分析结果"""
        # 安全地清理布局中的所有项目
        for i in reversed(range(self.analysis_layout.count())):
            item = self.analysis_layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                else:
                    # 处理布局或spacer等非widget项目
                    self.analysis_layout.removeItem(item)
        
        self.show_analysis_hint()
        self.export_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
    
    def export_analysis_results(self):
        """导出分析结果"""
        # TODO: 实现导出功能
        QMessageBox.information(self, "导出", "导出功能将在后续版本中实现")
    
    def send_chat_message(self):
        """发送聊天消息"""
        message = self.chat_input.text().strip()
        if not message:
            return
        
        # 显示用户消息
        self.chat_history.append(f"<div style='color: #2c3e50; margin: 10px 0;'><strong>您:</strong> {message}</div>")
        
        # 保存用户消息到历史
        self.history_manager.add_chat_message("user", message)
        
        # 清空输入框
        self.chat_input.clear()
        
        # 禁用输入和发送按钮
        self.send_btn.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.send_btn.setText("AI思考中...")
        
        # 显示正在思考
        self.chat_history.append(f"<div id='thinking' style='color: #6c757d; font-style: italic; margin: 5px 0;'>🤔 AI正在思考，请稍候...</div>")
        
        # 启动对话线程
        self.chat_thread = ChatThread(self.analyzer, message)
        self.chat_thread.chat_completed.connect(self.on_chat_completed)
        self.chat_thread.chat_error.connect(self.on_chat_error)
        self.chat_thread.finished.connect(self.on_chat_finished)
        self.chat_thread.start()
    
    def on_chat_completed(self, response: str):
        """AI对话完成"""
        # 移除"正在思考"消息
        self.remove_thinking_message()
        
        # 显示AI回复
        self.chat_history.append(f"<div style='color: #4a90e2; margin: 10px 0;'><strong>AI:</strong> {response}</div>")
        
        # 保存对话到历史
        self.history_manager.add_chat_message("ai", response)
        self.history_manager.save_history()
    
    def on_chat_error(self, error_message: str):
        """AI对话错误"""
        # 移除"正在思考"消息
        self.remove_thinking_message()
        
        # 显示错误信息
        self.chat_history.append(f"<div style='color: #dc3545; margin: 10px 0;'><strong>错误:</strong> {error_message}</div>")
    
    def on_chat_finished(self):
        """对话线程结束"""
        self.send_btn.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.send_btn.setText("发送")
        self.chat_input.setFocus()
    
    def remove_thinking_message(self):
        """移除思考提示消息"""
        # 获取当前HTML内容
        current_html = self.chat_history.toHtml()
        # 移除思考消息（简单的字符串替换）
        updated_html = current_html.replace("🤔 AI正在思考，请稍候...", "")
        self.chat_history.setHtml(updated_html)
    
    def ask_preset_question(self, question: str):
        """询问预设问题"""
        self.chat_input.setText(question)
        self.send_chat_message()
    
    def load_history_data(self):
        """加载历史数据"""
        try:
            # 加载聊天历史
            chat_history = self.history_manager.get_chat_history()
            if chat_history:
                self.chat_history.clear()
                self.chat_history.append(f"<div style='color: #666; font-style: italic;'>[{datetime.now().strftime('%H:%M:%S')}] 加载历史对话记录...</div>")
                
                for msg in chat_history:
                    if msg["type"] == "user":
                        self.chat_history.append(f"<div style='color: #2c3e50; margin: 10px 0;'><strong>您:</strong> {msg['content']}</div>")
                    elif msg["type"] == "ai":
                        self.chat_history.append(f"<div style='color: #4a90e2; margin: 10px 0;'><strong>AI:</strong> {msg['content']}</div>")
                
                self.chat_history.append("<div style='color: #666; font-style: italic; border-top: 1px solid #eee; margin: 10px 0; padding-top: 10px;'>--- 本次会话开始 ---</div>")
                print(f"📋 加载聊天历史: {len(chat_history)} 条消息")
            
            # 加载最新分析结果
            latest_results = self.history_manager.get_latest_analysis_results()
            if latest_results:
                try:
                    self.display_analysis_results(latest_results)
                    self.export_btn.setEnabled(True)
                    self.clear_btn.setEnabled(True)
                    print(f"📊 加载最新分析结果: {len(latest_results)} 个应用")
                except Exception as display_error:
                    print(f"❌ 显示分析结果失败: {str(display_error)}")
                    # 如果显示失败，至少显示提示
                    self.show_analysis_hint()
            
        except Exception as e:
            print(f"❌ 加载历史数据失败: {str(e)}")
            # 确保界面处于正常状态
            try:
                self.show_analysis_hint()
            except:
                pass
    
    def closeEvent(self, event):
        """关闭事件"""
        # 保存历史数据
        try:
            self.history_manager.save_history()
            print("💾 AI历史数据已保存")
        except Exception as e:
            print(f"❌ 保存历史数据失败: {str(e)}")
        
        # 检查是否有分析线程在运行
        if hasattr(self, 'analysis_thread') and self.analysis_thread and self.analysis_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认关闭", 
                "分析正在进行中，确定要关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.analysis_thread.cancel()
                self.analysis_thread.wait(3000)  # 等待3秒
                event.accept()
            else:
                event.ignore()
        else:
            event.accept() 