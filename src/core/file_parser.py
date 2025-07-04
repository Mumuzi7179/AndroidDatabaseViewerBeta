# -*- coding: utf-8 -*-
"""
文件解析模块
负责解析Android文件结构，生成文件树，查找包名文件夹
"""

import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass


@dataclass
class DatabaseFileInfo:
    """数据库文件信息"""
    file_name: str
    file_path: str
    parent_dir: str  # databases, cache, 等
    
    
@dataclass
class PackageInfo:
    """包信息数据类"""
    package_name: str
    path: str
    has_databases: bool = False
    has_shared_prefs: bool = False
    has_files: bool = False
    is_system_app: bool = True  # 默认为系统应用，如果检测到是非系统应用则设为False
    database_files: Optional[Dict[str, List[DatabaseFileInfo]]] = None  # {目录名: [数据库文件列表]}
    
    def __post_init__(self):
        if self.database_files is None:
            self.database_files = {}


class AndroidFileParser:
    """Android文件解析器"""
    
    # 常见的Android数据存储目录
    COMMON_DATA_PATHS = [
        "data",
        "data/data",
        "data/user/0",
        "data/user_de/0",
        "data/misc_de/0",
        "sdcard/Android/data",
        "storage/emulated/0/Android/data",
    ]
    
    # 包名标识文件夹（包括小米结构）
    PACKAGE_INDICATORS = ["databases", "shared_prefs", "files", "cache", "db", "sp", "f"]
    
    # 小米结构映射
    XIAOMI_DIR_MAPPING = {
        "db": "databases",
        "sp": "shared_prefs", 
        "f": "files"
    }
    
    # 可能包含数据库的目录名
    DATABASE_DIRS = ["databases", "cache", "files", "app_webview", "no_backup", "db"]
    
    def __init__(self, root_path: str):
        """
        初始化文件解析器
        
        Args:
            root_path: Android数据包根目录
        """
        self.root_path = Path(root_path)
        self.file_tree = {}
        self.packages = []
        self.non_system_packages = set()  # 存储非系统应用包名
        
        # 在初始化时检测非系统应用
        self._detect_non_system_apps()
        
    def _detect_non_system_apps(self):
        """检测非系统应用"""
        print("正在检测非系统应用...")
        
        # 首先检查是否存在常见的Android数据路径
        has_common_paths = False
        for common_path in self.COMMON_DATA_PATHS:
            full_path = self.root_path / common_path
            if full_path.exists() and full_path.is_dir():
                has_common_paths = True
                break
        
        # 如果存在常见路径，优先从这些路径检测，避免全局扫描
        if has_common_paths:
            print("  发现常见Android路径，跳过全局扫描以提高速度")
            # 方法2: 从packages.xml文件解析
            self._detect_from_packages_xml()
        else:
            # 只有在没有常见路径时才进行全目录扫描
            # 方法1: 从/data/app和/app目录读取包名
            self._detect_from_app_directories()
            
            # 方法2: 从packages.xml文件解析
            self._detect_from_packages_xml()
        
        if self.non_system_packages:
            print(f"检测到 {len(self.non_system_packages)} 个非系统应用")
        else:
            print("未检测到非系统应用信息")
    
    def _detect_from_app_directories(self):
        """从/data/app和/app目录检测非系统应用"""
        app_paths = [
            self.root_path / "data" / "app",
            self.root_path / "app"
        ]
        
        for app_path in app_paths:
            if app_path.exists() and app_path.is_dir():
                print(f"  扫描app目录: {app_path}")
                try:
                    for item in app_path.iterdir():
                        if item.is_dir():
                            # 提取包名（处理类似 com.example.app-xxx 的目录名）
                            package_name = self._extract_package_name_from_app_dir(item.name)
                            if package_name:
                                self.non_system_packages.add(package_name)
                                print(f"    发现非系统应用: {package_name}")
                except (PermissionError, OSError) as e:
                    print(f"  无法访问目录 {app_path}: {e}")
    
    def _extract_package_name_from_app_dir(self, dir_name: str) -> Optional[str]:
        """从app目录名提取包名"""
        # 处理类似 com.example.app-xxx 的目录名
        if "-" in dir_name:
            # 分割并取第一部分作为包名
            parts = dir_name.split("-")
            package_name = parts[0]
            # 验证是否看起来像包名（包含点号）
            if "." in package_name and not package_name.startswith("."):
                return package_name
        else:
            # 直接是包名
            if "." in dir_name and not dir_name.startswith("."):
                return dir_name
        return None
    
    def _detect_from_packages_xml(self):
        """从packages.xml文件检测非系统应用"""
        # 可能的packages.xml位置
        xml_paths = [
            self.root_path / "system" / "packages.xml",
            self.root_path / "packages.xml",
            # 其他可能的位置
            self.root_path / "data" / "system" / "packages.xml",
        ]
        
        for xml_path in xml_paths:
            if xml_path.exists():
                print(f"  解析packages.xml: {xml_path}")
                try:
                    self._parse_packages_xml(xml_path)
                    break  # 找到一个有效的packages.xml就停止
                except Exception as e:
                    print(f"  解析packages.xml失败: {e}")
                    continue
    
    def _parse_packages_xml(self, xml_path: Path):
        """解析packages.xml文件"""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            for package_elem in root.findall('package'):
                package_name = package_elem.get('name')
                code_path = package_elem.get('codePath')
                
                if package_name and code_path:
                    # 检查codePath是否以/data/app开头
                    if code_path.startswith('/data/app'):
                        self.non_system_packages.add(package_name)
                        print(f"    发现非系统应用: {package_name} (codePath: {code_path})")
                        
        except ET.ParseError as e:
            print(f"    XML解析错误: {e}")
        except Exception as e:
            print(f"    解析packages.xml时出错: {e}")
    
    def parse_directory_structure(self) -> Dict:
        """
        解析目录结构
        
        Returns:
            文件树字典
        """
        print(f"开始解析目录: {self.root_path}")
        self.file_tree = self._build_file_tree(self.root_path)
        return self.file_tree
    
    def _build_file_tree(self, path: Path, max_depth: int = 10, current_depth: int = 0) -> Dict:
        """
        递归构建文件树
        
        Args:
            path: 当前路径
            max_depth: 最大递归深度
            current_depth: 当前递归深度
            
        Returns:
            文件树字典
        """
        if current_depth > max_depth:
            return {"type": "directory", "children": {}, "truncated": True}
        
        tree = {"type": "directory", "children": {}}
        
        try:
            if not path.exists() or not path.is_dir():
                return tree
                
            for item in path.iterdir():
                try:
                    if item.is_dir():
                        tree["children"][item.name] = self._build_file_tree(
                            item, max_depth, current_depth + 1
                        )
                    else:
                        tree["children"][item.name] = {
                            "type": "file",
                            "size": item.stat().st_size if item.exists() else 0
                        }
                except (PermissionError, OSError) as e:
                    # 跳过无法访问的文件/目录
                    continue
                    
        except (PermissionError, OSError) as e:
            print(f"无法访问目录 {path}: {e}")
            
        return tree
    
    def find_packages(self) -> List[PackageInfo]:
        """
        查找所有包名文件夹
        
        Returns:
            包信息列表
        """
        print("开始查找包名文件夹...")
        self.packages = []
        
        # 首先在常见路径中查找
        for common_path in self.COMMON_DATA_PATHS:
            full_path = self.root_path / common_path
            if full_path.exists():
                self._scan_for_packages(full_path)
        
        # 如果常见路径没找到，则全局搜索
        if not self.packages:
            print("常见路径未找到包，进行全局搜索...")
            self._global_scan_for_packages(self.root_path)
        
        print(f"找到 {len(self.packages)} 个包")
        return self.packages
    
    def _scan_for_packages(self, data_path: Path):
        """
        在指定数据路径中扫描包
        
        Args:
            data_path: 数据路径
        """
        try:
            if not data_path.exists() or not data_path.is_dir():
                return
                
            for item in data_path.iterdir():
                if item.is_dir() and self._is_package_directory(item):
                    package_info = self._analyze_package(item)
                    if package_info:
                        self.packages.append(package_info)
                        
        except (PermissionError, OSError) as e:
            print(f"无法扫描目录 {data_path}: {e}")
    
    def _global_scan_for_packages(self, path: Path, max_depth: int = 8, current_depth: int = 0):
        """
        全局扫描包文件夹
        
        Args:
            path: 当前路径
            max_depth: 最大扫描深度
            current_depth: 当前深度
        """
        if current_depth > max_depth:
            return
            
        try:
            if not path.exists() or not path.is_dir():
                return
                
            for item in path.iterdir():
                if item.is_dir():
                    # 检查是否为包目录
                    if self._is_package_directory(item):
                        package_info = self._analyze_package(item)
                        if package_info:
                            self.packages.append(package_info)
                    else:
                        # 继续递归搜索
                        self._global_scan_for_packages(item, max_depth, current_depth + 1)
                        
        except (PermissionError, OSError) as e:
            pass  # 忽略权限错误
    
    def _is_package_directory(self, path: Path) -> bool:
        """
        判断是否为包目录（支持小米结构）
        
        Args:
            path: 目录路径
            
        Returns:
            是否为包目录
        """
        try:
            # 检查是否包含包名特征（包含点号的目录名，如com.example.app）
            if "." not in path.name:
                return False
            
            # 检查是否包含标识文件夹（包括小米结构）
            for indicator in self.PACKAGE_INDICATORS:
                if (path / indicator).exists():
                    return True
                    
            return False
            
        except (PermissionError, OSError):
            return False
    
    def _analyze_package(self, package_path: Path) -> Optional[PackageInfo]:
        """
        分析包目录（支持小米结构）
        
        Args:
            package_path: 包目录路径
            
        Returns:
            包信息
        """
        try:
            package_info = PackageInfo(
                package_name=package_path.name,
                path=str(package_path)
            )
            
            # 判断是否为系统应用
            package_info.is_system_app = package_path.name not in self.non_system_packages
            
            # 检查各种目录（支持小米结构）
            databases_paths = [package_path / "databases", package_path / "db"]
            shared_prefs_paths = [package_path / "shared_prefs", package_path / "sp"]
            files_paths = [package_path / "files", package_path / "f"]
            
            # 检查是否存在相应目录
            package_info.has_databases = any(p.exists() and p.is_dir() for p in databases_paths)
            package_info.has_shared_prefs = any(p.exists() and p.is_dir() for p in shared_prefs_paths)
            package_info.has_files = any(p.exists() and p.is_dir() for p in files_paths)
            
            # 在包目录下查找所有可能包含数据库的目录
            package_info.database_files = self._find_all_databases_in_package(package_path)
            
            # 只返回包含数据的包
            if (package_info.has_databases or package_info.has_shared_prefs or 
                package_info.has_files or package_info.database_files):
                return package_info
                
            return None
            
        except (PermissionError, OSError) as e:
            print(f"分析包目录失败 {package_path}: {e}")
            return None
    
    def _find_all_databases_in_package(self, package_path: Path) -> Dict[str, List[DatabaseFileInfo]]:
        """
        在包目录下查找所有数据库文件（支持小米结构）
        
        Args:
            package_path: 包目录路径
            
        Returns:
            数据库文件字典 {目录名: [数据库文件列表]}
        """
        database_files = {}
        
        try:
            # 检查包目录下的所有子目录
            for item in package_path.iterdir():
                if item.is_dir():
                    # 在每个子目录中查找数据库文件
                    db_files_in_dir = self._find_databases_in_directory(item)
                    if db_files_in_dir:
                        # 转换小米结构目录名
                        display_name = self.XIAOMI_DIR_MAPPING.get(item.name, item.name)
                        database_files[display_name] = db_files_in_dir
                        
        except (PermissionError, OSError) as e:
            print(f"扫描包目录失败 {package_path}: {e}")
            
        return database_files
    
    def _find_databases_in_directory(self, directory_path: Path, root_dir_name: Optional[str] = None, max_depth: int = 5, current_depth: int = 0) -> List[DatabaseFileInfo]:
        """
        在指定目录中递归查找数据库文件
        
        Args:
            directory_path: 目录路径
            root_dir_name: 根目录名称（如databases）
            max_depth: 最大递归深度
            current_depth: 当前递归深度
            
        Returns:
            数据库文件列表
        """
        databases = []
        
        # 防止递归过深
        if current_depth > max_depth:
            return databases
        
        # 如果是第一次调用，设置根目录名称
        if root_dir_name is None:
            root_dir_name = directory_path.name
        
        try:
            for item in directory_path.iterdir():
                if item.is_file():
                    # 检查是否为SQLite数据库文件
                    if self._is_sqlite_file(item):
                        # 构建显示路径：如果在子目录中，显示 "databases/子目录名"
                        if current_depth > 0:
                            parent_path = f"{root_dir_name}/{directory_path.name}"
                        else:
                            parent_path = root_dir_name
                            
                        db_info = DatabaseFileInfo(
                            file_name=item.name,
                            file_path=str(item),
                            parent_dir=parent_path
                        )
                        databases.append(db_info)
                elif item.is_dir():
                    # 递归查找子目录中的数据库文件
                    sub_databases = self._find_databases_in_directory(item, root_dir_name, max_depth, current_depth + 1)
                    databases.extend(sub_databases)
                        
        except (PermissionError, OSError) as e:
            print(f"扫描数据库目录失败 {directory_path}: {e}")
            
        return databases
    
    def _is_sqlite_file(self, file_path: Path) -> bool:
        """
        检查文件是否为SQLite数据库文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否为SQLite文件
        """
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
    
    def save_structure_to_json(self, output_path: str):
        """
        保存文件结构到JSON文件
        
        Args:
            output_path: 输出文件路径
        """
        data = {
            "root_path": str(self.root_path),
            "file_tree": self.file_tree,
            "packages": []
        }
        
        for pkg in self.packages:
            pkg_data = {
                "package_name": pkg.package_name,
                "path": pkg.path,
                "has_databases": pkg.has_databases,
                "has_shared_prefs": pkg.has_shared_prefs,
                "has_files": pkg.has_files,
                "is_system_app": pkg.is_system_app,
                "database_files": {}
            }
            
            for dir_name, db_files in (pkg.database_files or {}).items():
                pkg_data["database_files"][dir_name] = [
                    {
                        "file_name": db.file_name,
                        "file_path": db.file_path,
                        "parent_dir": db.parent_dir
                    }
                    for db in db_files
                ]
            
            data["packages"].append(pkg_data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"文件结构已保存到: {output_path}")
    
    def load_structure_from_json(self, json_path: str) -> bool:
        """
        从JSON文件加载文件结构
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            是否加载成功
        """
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.root_path = Path(data["root_path"])
            self.file_tree = data["file_tree"]
            
            self.packages = []
            for pkg_data in data["packages"]:
                # 重建数据库文件信息
                database_files = {}
                for dir_name, db_files_data in pkg_data.get("database_files", {}).items():
                    database_files[dir_name] = [
                        DatabaseFileInfo(
                            file_name=db["file_name"],
                            file_path=db["file_path"],
                            parent_dir=db["parent_dir"]
                        )
                        for db in db_files_data
                    ]
                
                package_info = PackageInfo(
                    package_name=pkg_data["package_name"],
                    path=pkg_data["path"],
                    has_databases=pkg_data["has_databases"],
                    has_shared_prefs=pkg_data["has_shared_prefs"],
                    has_files=pkg_data["has_files"],
                    is_system_app=pkg_data.get("is_system_app", True),  # 兼容旧版本，默认为系统应用
                    database_files=database_files
                )
                self.packages.append(package_info)
            
            print(f"从JSON文件加载了 {len(self.packages)} 个包")
            return True
            
        except (IOError, json.JSONDecodeError) as e:
            print(f"加载JSON文件失败: {e}")
            return False 