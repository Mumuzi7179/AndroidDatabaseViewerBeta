# -*- coding: utf-8 -*-
"""
包树形视图组件
显示包名-目录-数据库的三级结构
"""

from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, 
    QWidget, QLabel, QHBoxLayout, QPushButton,
    QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon, QColor, QBrush


class PackageTreeWidget(QWidget):
    """包树形视图组件"""
    
    # 自定义信号
    database_selected = Signal(str, str, str)  # package_name, parent_dir, db_name
    
    def __init__(self):
        super().__init__()
        self.packages = []
        self.database_manager = None
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 标题
        title_layout = QHBoxLayout()
        title_label = QLabel("包和数据库列表")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_tree)
        title_layout.addWidget(refresh_btn)
        
        layout.addLayout(title_layout)
        
        # 树形控件
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("包名 / 目录 / 数据库")
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
        # 设置样式，修复悬停颜色问题
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: white;
                border: 1px solid #ccc;
                alternate-background-color: #f9f9f9;
            }
            QTreeWidget::item {
                height: 24px;
                padding: 2px;
                border: none;
                color: #333;
            }
            QTreeWidget::item:hover {
                background-color: #e8f4fd;
                color: #333;
            }
            QTreeWidget::item:selected {
                background-color: #4a90e2;
                color: white;
            }
            QTreeWidget::item:selected:hover {
                background-color: #357abd;
                color: white;
            }
        """)
        
        layout.addWidget(self.tree)
    
    def set_database_manager(self, database_manager):
        """设置数据库管理器"""
        self.database_manager = database_manager
    
    def load_packages(self, packages):
        """加载包数据"""
        self.packages = packages
        self.refresh_tree()
    
    def refresh_tree(self):
        """刷新树形视图"""
        self.tree.clear()
        
        if not self.packages:
            return
        
        # 分类包：有数据库的和无数据库的
        packages_with_db = []
        packages_without_db = []
        
        # 统计系统应用和非系统应用数量
        system_apps_with_db = 0
        non_system_apps_with_db = 0
        
        for package in self.packages:
            if package.database_files:
                packages_with_db.append(package)
                if package.is_system_app:
                    system_apps_with_db += 1
                else:
                    non_system_apps_with_db += 1
            else:
                packages_without_db.append(package)
        
        # 添加有数据库的包
        if packages_with_db:
            # 构建标题，显示系统应用和非系统应用的数量
            title_parts = []
            if system_apps_with_db > 0:
                title_parts.append(f"系统应用: {system_apps_with_db}")
            if non_system_apps_with_db > 0:
                title_parts.append(f"📱非系统应用: {non_system_apps_with_db}")
            
            if title_parts:
                db_root_title = f"包含数据库的应用 ({', '.join(title_parts)})"
            else:
                db_root_title = "包含数据库的应用"
                
            db_root = QTreeWidgetItem(self.tree, [db_root_title])
            db_root.setExpanded(True)
            
            for package in sorted(packages_with_db, key=lambda x: x.package_name):
                # 根据是否为系统应用设置不同的显示文本和颜色
                display_text = package.package_name
                if not package.is_system_app:
                    display_text = f"📱 {package.package_name}"  # 为非系统应用添加手机图标
                
                package_item = QTreeWidgetItem(db_root, [display_text])
                package_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'package',
                    'package_name': package.package_name,
                    'package_path': package.path,
                    'is_system_app': package.is_system_app
                })
                
                # 为非系统应用设置不同的颜色
                if not package.is_system_app:
                    # 设置为橙色字体，表示非系统应用
                    package_item.setForeground(0, QBrush(QColor(255, 140, 0)))  # 橙色
                
                # 为每个包添加目录级别
                for parent_dir, db_files in package.database_files.items():
                    dir_item = QTreeWidgetItem(package_item, [parent_dir])
                    dir_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'directory',
                        'package_name': package.package_name,
                        'parent_dir': parent_dir
                    })
                    
                    # 添加数据库（三级结构到此为止）
                    for db_file in sorted(db_files, key=lambda x: x.file_name):
                        db_item = QTreeWidgetItem(dir_item, [db_file.file_name])
                        db_item.setData(0, Qt.ItemDataRole.UserRole, {
                            'type': 'database',
                            'package_name': package.package_name,
                            'parent_dir': parent_dir,
                            'db_name': db_file.file_name
                        })
        
        # 添加无数据库的包（可选显示）
        if packages_without_db:
            other_root = QTreeWidgetItem(self.tree, [f"其他应用 ({len(packages_without_db)})"])
            
            for package in sorted(packages_without_db, key=lambda x: x.package_name):
                # 根据是否为系统应用设置不同的显示文本和颜色
                display_text = package.package_name
                if not package.is_system_app:
                    display_text = f"📱 {package.package_name}"  # 为非系统应用添加手机图标
                
                package_item = QTreeWidgetItem(other_root, [display_text])
                package_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'package_no_db',
                    'package_name': package.package_name,
                    'package_path': package.path,
                    'is_system_app': package.is_system_app
                })
                
                # 为非系统应用设置不同的颜色
                if not package.is_system_app:
                    # 设置为橙色字体，表示非系统应用
                    package_item.setForeground(0, QBrush(QColor(255, 140, 0)))  # 橙色
        
        # 展开第一层
        self.tree.expandToDepth(0)
    
    def on_item_clicked(self, item, column):
        """处理项目点击事件"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        
        if not data:
            return
        
        item_type = data.get('type')
        
        if item_type == 'database':
            # 选择了数据库，发送信号
            package_name = data['package_name']
            parent_dir = data['parent_dir']
            db_name = data['db_name']
            self.database_selected.emit(package_name, parent_dir, db_name)
    
    def show_context_menu(self, position):
        """显示右键菜单"""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        menu = QMenu(self)
        item_type = data.get('type')
        
        if item_type == 'package':
            # 包的右键菜单
            open_folder_action = QAction("打开文件夹", self)
            open_folder_action.triggered.connect(
                lambda: self.open_package_folder(data['package_path'])
            )
            menu.addAction(open_folder_action)
        
        elif item_type == 'database':
            # 数据库的右键菜单
            copy_path_action = QAction("复制数据库路径", self)
            copy_path_action.triggered.connect(
                lambda: self.copy_db_path(
                    data['package_name'], 
                    data['parent_dir'], 
                    data['db_name']
                )
            )
            menu.addAction(copy_path_action)
        
        if menu.actions():
            menu.exec(self.tree.mapToGlobal(position))
    
    def copy_db_path(self, package_name, parent_dir, db_name):
        """复制数据库路径"""
        if self.database_manager:
            db_path = self.database_manager.get_database_path(package_name, parent_dir, db_name)
            if db_path:
                self.copy_to_clipboard(db_path)
                QMessageBox.information(self, "复制成功", f"数据库路径已复制到剪贴板:\n{db_path}")
    
    def open_package_folder(self, folder_path):
        """打开包文件夹"""
        import os
        import subprocess
        import platform
        
        if os.path.exists(folder_path):
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", folder_path])
            else:  # Linux
                subprocess.run(["xdg-open", folder_path])
        else:
            QMessageBox.warning(self, "警告", f"文件夹不存在: {folder_path}")
    
    def copy_to_clipboard(self, text):
        """复制文本到剪贴板"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
    
    def get_selected_item_info(self):
        """获取当前选中项的信息"""
        current_item = self.tree.currentItem()
        if current_item:
            return current_item.data(0, Qt.ItemDataRole.UserRole)
        return None
    
    def select_database_item(self, package_name, parent_dir, db_name):
        """选中指定的数据库项"""
        try:
            # 检查当前选中的项是否已经是目标项
            current_item = self.tree.currentItem()
            if current_item:
                current_data = current_item.data(0, Qt.ItemDataRole.UserRole)
                if (current_data and current_data.get('type') == 'database' and
                    current_data.get('package_name') == package_name and
                    current_data.get('parent_dir') == parent_dir and
                    current_data.get('db_name') == db_name):
                    print(f"数据库项已经选中，无需重复操作: {package_name}/{parent_dir}/{db_name}")
                    return True
            
            # 遍历树中的所有项来查找匹配的数据库
            root = self.tree.invisibleRootItem()
            for i in range(root.childCount()):
                category_item = root.child(i)  # "包含数据库的应用" 或 "其他应用"
                
                # 遍历包
                for j in range(category_item.childCount()):
                    package_item = category_item.child(j)
                    package_data = package_item.data(0, Qt.ItemDataRole.UserRole)
                    
                    if package_data and package_data.get('package_name') == package_name:
                        # 找到了匹配的包，现在查找目录
                        for k in range(package_item.childCount()):
                            dir_item = package_item.child(k)
                            dir_data = dir_item.data(0, Qt.ItemDataRole.UserRole)
                            
                            if dir_data and dir_data.get('parent_dir') == parent_dir:
                                # 找到了匹配的目录，现在查找数据库
                                for l in range(dir_item.childCount()):
                                    db_item = dir_item.child(l)
                                    db_data = db_item.data(0, Qt.ItemDataRole.UserRole)
                                    
                                    if db_data and db_data.get('db_name') == db_name:
                                        # 找到了匹配的数据库项
                                        # 展开父级项
                                        category_item.setExpanded(True)
                                        package_item.setExpanded(True)
                                        dir_item.setExpanded(True)
                                        
                                        # 选中数据库项
                                        self.tree.setCurrentItem(db_item)
                                        
                                        # 确保项目可见
                                        self.tree.scrollToItem(db_item)
                                        
                                        # 只有当不是当前项时才触发点击事件
                                        if current_item != db_item:
                                            print(f"触发数据库项点击: {package_name}/{parent_dir}/{db_name}")
                                            self.on_item_clicked(db_item, 0)
                                        else:
                                            print(f"数据库项已选中，跳过点击事件")
                                        
                                        return True
            
            return False
            
        except Exception as e:
            print(f"选择数据库项时出错: {e}")
            return False 