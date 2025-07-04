# -*- coding: utf-8 -*-
"""
工程文件管理模块
负责保存和载入完整的项目数据，包括数据库内容
"""

import os
import pickle
import zipfile
import zlib
import tempfile
import shutil
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class ProjectData:
    """工程数据结构"""
    packages: List[Any]  # PackageInfo列表
    database_files: Dict[str, bytes]  # 数据库文件内容 {文件路径: 二进制内容}
    project_info: Dict[str, Any]  # 工程信息
    current_data_path: str  # 当前数据路径


class ProjectManager:
    """工程文件管理器"""
    
    def __init__(self):
        self.temp_dir = None
    
    def save_project(self, packages: List[Any], current_data_path: str, 
                    progress_callback=None) -> bool:
        """
        保存工程为.madb文件
        
        Args:
            packages: 包列表
            current_data_path: 当前数据路径
            progress_callback: 进度回调函数
            
        Returns:
            是否保存成功
        """
        try:
            from PySide6.QtWidgets import QFileDialog
            
            # 选择保存位置
            save_path, _ = QFileDialog.getSaveFileName(
                None, "保存工程文件", "", "Android数据库工程文件 (*.madb)"
            )
            
            if not save_path:
                return False
            
            if not save_path.endswith('.madb'):
                save_path += '.madb'
            
            if progress_callback:
                progress_callback("正在收集数据库文件...", 10)
            
            # 收集所有数据库文件内容
            database_files = {}
            total_files = 0
            processed_files = 0
            
            # 统计总文件数
            for package in packages:
                if hasattr(package, 'database_files') and package.database_files:
                    for dir_name, db_files in package.database_files.items():
                        total_files += len(db_files)
            
            # 读取数据库文件内容
            for package in packages:
                if hasattr(package, 'database_files') and package.database_files:
                    for dir_name, db_files in package.database_files.items():
                        for db_file in db_files:
                            try:
                                with open(db_file.file_path, 'rb') as f:
                                    content = f.read()
                                    database_files[db_file.file_path] = content
                                
                                processed_files += 1
                                if progress_callback:
                                    progress = 10 + int((processed_files / total_files) * 30)
                                    progress_callback(f"读取数据库文件 {processed_files}/{total_files}", progress)
                            
                            except Exception as e:
                                print(f"读取数据库文件失败 {db_file.file_path}: {e}")
            
            if progress_callback:
                progress_callback("正在序列化数据...", 50)
            
            # 创建工程数据对象
            project_data = ProjectData(
                packages=packages,
                database_files=database_files,
                project_info={
                    "version": "1.0",
                    "creation_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_packages": len(packages),
                    "total_databases": len(database_files)
                },
                current_data_path=current_data_path
            )
            
            if progress_callback:
                progress_callback("正在压缩数据...", 60)
            
            # 序列化数据
            serialized_data = pickle.dumps(project_data)
            
            if progress_callback:
                progress_callback("正在进行ZIP压缩...", 70)
            
            # 创建临时文件进行ZIP压缩
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_zip_path = temp_file.name + '.zip'
            
            try:
                with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
                    zipf.writestr('project_data.pkl', serialized_data)
                
                if progress_callback:
                    progress_callback("正在进行哈夫曼压缩...", 80)
                
                # 读取ZIP文件并进行二次压缩（使用zlib的哈夫曼编码）
                with open(temp_zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                # 使用zlib进行二次压缩（内部使用哈夫曼编码）
                compressed_data = zlib.compress(zip_data, level=9)
                
                if progress_callback:
                    progress_callback("正在保存文件...", 90)
                
                # 保存最终文件
                with open(save_path, 'wb') as final_file:
                    # 写入文件头标识
                    final_file.write(b'MADB')  # 文件标识
                    final_file.write((1).to_bytes(4, 'little'))  # 版本号
                    final_file.write(len(compressed_data).to_bytes(8, 'little'))  # 数据长度
                    final_file.write(compressed_data)
                
                if progress_callback:
                    progress_callback("保存完成", 100)
                
                # 计算压缩比
                original_size = len(serialized_data) / (1024 * 1024)
                final_size = os.path.getsize(save_path) / (1024 * 1024)
                compression_ratio = (1 - final_size / original_size) * 100 if original_size > 0 else 0
                
                print(f"工程文件已保存: {save_path}")
                print(f"原始数据: {original_size:.2f}MB")
                print(f"压缩后: {final_size:.2f}MB")
                print(f"压缩率: {compression_ratio:.1f}%")
                
                return True
                
            finally:
                # 清理临时文件
                if os.path.exists(temp_zip_path):
                    os.unlink(temp_zip_path)
            
        except Exception as e:
            print(f"保存工程文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_project(self, file_path: str, progress_callback=None) -> Optional[ProjectData]:
        """
        载入工程文件
        
        Args:
            file_path: 工程文件路径
            progress_callback: 进度回调函数
            
        Returns:
            工程数据或None
        """
        try:
            if progress_callback:
                progress_callback("正在读取工程文件...", 10)
            
            # 读取文件
            with open(file_path, 'rb') as f:
                # 验证文件头
                magic = f.read(4)
                if magic != b'MADB':
                    raise ValueError("不是有效的MADB工程文件")
                
                version = int.from_bytes(f.read(4), 'little')
                if version != 1:
                    raise ValueError(f"不支持的文件版本: {version}")
                
                data_length = int.from_bytes(f.read(8), 'little')
                compressed_data = f.read(data_length)
            
            if progress_callback:
                progress_callback("正在解压缩数据...", 30)
            
            # 解压缩数据
            zip_data = zlib.decompress(compressed_data)
            
            if progress_callback:
                progress_callback("正在解析ZIP数据...", 50)
            
            # 创建临时文件保存ZIP数据
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
                temp_zip_path = temp_file.name
                temp_file.write(zip_data)
            
            try:
                # 解压ZIP文件
                with zipfile.ZipFile(temp_zip_path, 'r') as zipf:
                    serialized_data = zipf.read('project_data.pkl')
                
                if progress_callback:
                    progress_callback("正在反序列化数据...", 70)
                
                # 反序列化数据
                project_data = pickle.loads(serialized_data)
                
                if progress_callback:
                    progress_callback("正在恢复数据库文件...", 80)
                
                # 创建临时目录存放数据库文件
                self.temp_dir = tempfile.mkdtemp(prefix='madb_project_')
                
                # 恢复数据库文件到临时目录
                for i, (original_path, file_content) in enumerate(project_data.database_files.items()):
                    # 在临时目录中创建对应的文件结构
                    original_filename = os.path.basename(original_path)
                    # 为了避免文件名冲突，添加索引
                    temp_filename = f"{i:04d}_{original_filename}"
                    temp_file_path = os.path.join(self.temp_dir, temp_filename)
                    
                    # 确保目录存在
                    os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
                    
                    # 写入文件内容
                    with open(temp_file_path, 'wb') as f:
                        f.write(file_content)
                    
                    # 更新包中的文件路径指向临时文件
                    for package in project_data.packages:
                        if hasattr(package, 'database_files') and package.database_files:
                            for dir_name, db_files in package.database_files.items():
                                for db_file in db_files:
                                    if db_file.file_path == original_path:
                                        db_file.file_path = temp_file_path
                
                if progress_callback:
                    progress_callback("载入完成", 100)
                
                print(f"工程文件载入成功: {file_path}")
                print(f"包含 {len(project_data.packages)} 个包")
                print(f"包含 {len(project_data.database_files)} 个数据库文件")
                
                return project_data
                
            finally:
                # 清理临时ZIP文件
                if os.path.exists(temp_zip_path):
                    os.unlink(temp_zip_path)
            
        except Exception as e:
            print(f"载入工程文件失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def cleanup_temp_files(self):
        """清理临时文件"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
                print("临时文件清理完成")
            except Exception as e:
                print(f"清理临时文件失败: {e}") 