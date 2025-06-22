# -*- coding: utf-8 -*-
"""
数据库管理模块
负责SQLite数据库的读取、查询和全局搜索功能
"""

import sqlite3
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass


@dataclass
class DatabaseInfo:
    """数据库信息"""
    package_name: str
    database_name: str
    database_path: str
    parent_dir: str  # 父目录名称（databases, cache等）
    tables: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.tables is None:
            self.tables = []


@dataclass
class TableInfo:
    """表信息"""
    table_name: str
    columns: List[str]
    row_count: int


@dataclass
class SearchResult:
    """搜索结果"""
    package_name: str
    database_name: str
    table_name: str
    column_name: str
    row_data: Dict[str, Any]
    match_value: str
    parent_dir: str  # 数据库所在目录


@dataclass 
class CachedTableData:
    """缓存的表数据"""
    columns: List[str]
    rows: List[Tuple]
    total_rows: int


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        """初始化数据库管理器"""
        self.databases = {}  # {package_name: {parent_dir: {db_name: DatabaseInfo}}}
        self.connections = {}  # 数据库连接缓存
        self.cached_data = {}  # 数据缓存 {package_name: {parent_dir: {db_name: {table_name: CachedTableData}}}}
        self.search_index = {}  # 搜索索引
    
    def load_databases(self, packages):
        """
        加载所有包的数据库信息并预加载表信息
        
        Args:
            packages: 包信息列表
        """
        print("开始加载数据库信息...")
        self.databases = {}
        self.cached_data = {}
        
        total_databases = 0
        total_tables = 0
        
        for package in packages:
            if package.database_files:
                package_dbs = {}
                package_cache = {}
                
                for parent_dir, db_files in package.database_files.items():
                    dir_dbs = {}
                    dir_cache = {}
                    
                    for db_file in db_files:
                        if os.path.exists(db_file.file_path):
                            db_info = DatabaseInfo(
                                package_name=package.package_name,
                                database_name=db_file.file_name,
                                database_path=db_file.file_path,
                                parent_dir=parent_dir
                            )
                            
                            # 预加载表信息
                            print(f"  预加载: {package.package_name}/{parent_dir}/{db_file.file_name}")
                            db_info.tables = self._get_table_names(db_file.file_path)
                            total_tables += len(db_info.tables)
                            
                            # 预加载小表的数据（行数小于1000的表）
                            table_cache = {}
                            for table_name in db_info.tables:
                                try:
                                    row_count = self._get_table_row_count(db_file.file_path, table_name)
                                    if row_count <= 1000:  # 小表直接缓存
                                        columns, rows = self._load_table_data(db_file.file_path, table_name)
                                        table_cache[table_name] = CachedTableData(
                                            columns=columns,
                                            rows=rows,
                                            total_rows=row_count
                                        )
                                        print(f"    缓存表: {table_name} ({row_count} 行)")
                                except Exception as e:
                                    print(f"    跳过表 {table_name}: {e}")
                                    continue
                            
                            dir_dbs[db_file.file_name] = db_info
                            dir_cache[db_file.file_name] = table_cache
                            total_databases += 1
                    
                    if dir_dbs:
                        package_dbs[parent_dir] = dir_dbs
                        package_cache[parent_dir] = dir_cache
                
                if package_dbs:
                    self.databases[package.package_name] = package_dbs
                    self.cached_data[package.package_name] = package_cache
        
        print(f"加载完成: {len(self.databases)} 个包, {total_databases} 个数据库, {total_tables} 个表")
        
        # 构建搜索索引
        print("构建搜索索引...")
        self._build_search_index()
        print("搜索索引构建完成")
    
    def _build_search_index(self):
        """构建搜索索引以加速搜索"""
        self.search_index = {}
        
        for package_name, package_dbs in self.databases.items():
            for parent_dir, dir_dbs in package_dbs.items():
                for db_name, db_info in dir_dbs.items():
                    # 为每个数据库的每个表建立索引
                    for table_name in db_info.tables:
                        try:
                            # 获取表的列信息
                            columns = self._get_table_columns(db_info.database_path, table_name)
                            
                            # 如果表数据已缓存，直接从缓存建立索引
                            cached_table = self.cached_data.get(package_name, {}).get(parent_dir, {}).get(db_name, {}).get(table_name)
                            if cached_table:
                                for row in cached_table.rows:
                                    row_data = dict(zip(cached_table.columns, row))
                                    self._add_to_search_index(package_name, parent_dir, db_name, table_name, columns, row_data)
                            
                        except Exception as e:
                            continue
    
    def _add_to_search_index(self, package_name, parent_dir, db_name, table_name, columns, row_data):
        """将行数据添加到搜索索引"""
        for column_name, value in row_data.items():
            if value is not None:
                value_str = str(value).lower()
                # 分词索引（简单的按空格和标点分词）
                words = value_str.replace(',', ' ').replace('.', ' ').replace(':', ' ').split()
                for word in words:
                    if len(word) > 1:  # 忽略单字符
                        if word not in self.search_index:
                            self.search_index[word] = []
                        
                        self.search_index[word].append({
                            'package_name': package_name,
                            'parent_dir': parent_dir,
                            'database_name': db_name,
                            'table_name': table_name,
                            'column_name': column_name,
                            'row_data': row_data,
                            'match_value': str(value)
                        })
    
    def _get_table_row_count(self, db_path: str, table_name: str) -> int:
        """获取表的行数"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            result = cursor.fetchone()
            count = int(result[0]) if result and result[0] is not None else 0
            conn.close()
            return count
        except:
            return 0
    
    def _load_table_data(self, db_path: str, table_name: str, limit: Optional[int] = None) -> Tuple[List[str], List[Tuple]]:
        """加载表数据"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 获取列名
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            
            # 获取数据
            if limit:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            else:
                cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            conn.close()
            return columns, rows
            
        except Exception as e:
            print(f"加载表数据失败 {db_path}/{table_name}: {e}")
            return [], []
    
    def _get_table_columns(self, db_path: str, table_name: str) -> List[str]:
        """获取表的列名"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            conn.close()
            return columns
        except:
            return []
    
    def _get_table_names(self, db_path: str) -> List[str]:
        """
        获取数据库中的表名
        
        Args:
            db_path: 数据库路径
            
        Returns:
            表名列表
        """
        tables = []
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            
            tables = [row[0] for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            print(f"获取表名失败 {db_path}: {e}")
        finally:
            if 'conn' in locals():
                conn.close()
        
        return tables
    
    def get_table_info(self, package_name: str, parent_dir: str, db_name: str, table_name: str) -> Optional[TableInfo]:
        """
        获取表信息
        
        Args:
            package_name: 包名
            parent_dir: 父目录名
            db_name: 数据库名
            table_name: 表名
            
        Returns:
            表信息
        """
        if (package_name not in self.databases or 
            parent_dir not in self.databases[package_name] or
            db_name not in self.databases[package_name][parent_dir]):
            return None
        
        db_info = self.databases[package_name][parent_dir][db_name]
        
        try:
            conn = sqlite3.connect(db_info.database_path)
            cursor = conn.cursor()
            
            # 获取列信息
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            
            # 获取行数
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            
            return TableInfo(
                table_name=table_name,
                columns=columns,
                row_count=row_count
            )
            
        except sqlite3.Error as e:
            print(f"获取表信息失败: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_table_data(self, package_name: str, parent_dir: str, db_name: str, table_name: str, 
                      limit: int = 1000, offset: int = 0) -> Tuple[List[str], List[Tuple]]:
        """
        获取表数据（优先从缓存获取）
        
        Args:
            package_name: 包名
            parent_dir: 父目录名
            db_name: 数据库名
            table_name: 表名
            limit: 限制行数
            offset: 偏移量
            
        Returns:
            (列名列表, 数据行列表)
        """
        # 首先检查缓存
        cached_table = self.cached_data.get(package_name, {}).get(parent_dir, {}).get(db_name, {}).get(table_name)
        if cached_table:
            # 从缓存返回数据
            start_idx = offset
            end_idx = offset + limit
            return cached_table.columns, cached_table.rows[start_idx:end_idx]
        
        # 缓存中没有，从数据库读取
        if (package_name not in self.databases or 
            parent_dir not in self.databases[package_name] or
            db_name not in self.databases[package_name][parent_dir]):
            return [], []
        
        db_info = self.databases[package_name][parent_dir][db_name]
        
        conn = None
        try:
            # 使用更安全的连接方式，设置超时
            conn = sqlite3.connect(db_info.database_path, timeout=10.0)
            conn.execute("PRAGMA busy_timeout = 10000")  # 10秒忙等待
            cursor = conn.cursor()
            
            # 安全地获取列名（使用参数化查询的思想）
            cursor.execute(f"PRAGMA table_info([{table_name}])")
            columns = [row[1] for row in cursor.fetchall()]
            
            if not columns:
                print(f"警告: 表 {table_name} 没有列信息")
                return [], []
            
            # 安全地获取数据
            cursor.execute(f"SELECT * FROM [{table_name}] LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            
            print(f"成功获取表数据: {package_name}/{parent_dir}/{db_name}/{table_name} - {len(rows)} 行")
            return columns, rows
            
        except sqlite3.OperationalError as e:
            print(f"数据库操作错误: {e}")
            if "database is locked" in str(e).lower():
                print("数据库被锁定，尝试重新连接...")
                # 稍等一下再试
                import time
                time.sleep(0.5)
                return self._retry_get_table_data(db_info.database_path, table_name, limit, offset)
            return [], []
        except sqlite3.Error as e:
            print(f"获取表数据失败: {e}")
            return [], []
        except Exception as e:
            print(f"未知错误: {e}")
            import traceback
            traceback.print_exc()
            return [], []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def _retry_get_table_data(self, db_path: str, table_name: str, limit: int, offset: int) -> Tuple[List[str], List[Tuple]]:
        """重试获取表数据"""
        conn = None
        try:
            conn = sqlite3.connect(db_path, timeout=5.0)
            conn.execute("PRAGMA busy_timeout = 5000")
            cursor = conn.cursor()
            
            cursor.execute(f"PRAGMA table_info([{table_name}])")
            columns = [row[1] for row in cursor.fetchall()]
            
            cursor.execute(f"SELECT * FROM [{table_name}] LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            
            return columns, rows
            
        except Exception as e:
            print(f"重试获取表数据也失败: {e}")
            return [], []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def global_search(self, search_term: str, case_sensitive: bool = False, use_regex: bool = False) -> List[SearchResult]:
        """
        全局搜索所有数据库（使用索引加速）
        
        Args:
            search_term: 搜索词
            case_sensitive: 是否区分大小写
            use_regex: 是否使用正则表达式
            
        Returns:
            搜索结果列表
        """
        results = []
        
        print(f"开始全局搜索: '{search_term}' (正则: {use_regex}, 大小写: {case_sensitive})")
        
        # 如果使用正则表达式，直接使用传统搜索（索引不支持正则）
        if use_regex:
            results = self._traditional_search(search_term, case_sensitive, use_regex)
        else:
            search_pattern = search_term if case_sensitive else search_term.lower()
            
            # 使用搜索索引进行快速搜索
            if not case_sensitive:
                search_words = search_pattern.split()
                for word in search_words:
                    if word in self.search_index:
                        for result_data in self.search_index[word]:
                            if search_pattern in result_data['match_value'].lower():
                                result = SearchResult(
                                    package_name=result_data['package_name'],
                                    database_name=result_data['database_name'],
                                    table_name=result_data['table_name'],
                                    column_name=result_data['column_name'],
                                    row_data=result_data['row_data'],
                                    match_value=result_data['match_value'],
                                    parent_dir=result_data['parent_dir']
                                )
                                results.append(result)
            
            # 如果索引搜索结果不够，回退到传统搜索
            if len(results) < 100:
                traditional_results = self._traditional_search(search_pattern, case_sensitive, use_regex)
                # 合并结果并去重
                existing_keys = set()
                for r in results:
                    key = (r.package_name, r.database_name, r.table_name, r.column_name, r.match_value)
                    existing_keys.add(key)
                
                for r in traditional_results:
                    key = (r.package_name, r.database_name, r.table_name, r.column_name, r.match_value)
                    if key not in existing_keys:
                        results.append(r)
        
        print(f"搜索完成，找到 {len(results)} 条结果")
        return results
    
    def _traditional_search(self, search_pattern: str, case_sensitive: bool, use_regex: bool = False) -> List[SearchResult]:
        """传统的数据库搜索方法"""
        results = []
        
        for package_name, package_dbs in self.databases.items():
            for parent_dir, dir_dbs in package_dbs.items():
                for db_name, db_info in dir_dbs.items():
                    results.extend(self._search_database(
                        db_info, search_pattern, case_sensitive, use_regex
                    ))
        
        return results
    
    def _search_database(self, db_info: DatabaseInfo, search_pattern: str, 
                        case_sensitive: bool, use_regex: bool = False) -> List[SearchResult]:
        """
        搜索单个数据库
        
        Args:
            db_info: 数据库信息
            search_pattern: 搜索模式
            case_sensitive: 是否区分大小写
            use_regex: 是否使用正则表达式
            
        Returns:
            搜索结果列表
        """
        results = []
        
        try:
            conn = sqlite3.connect(db_info.database_path)
            cursor = conn.cursor()
            
            for table_name in (db_info.tables or []):
                # 获取表结构
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [row[1] for row in cursor.fetchall()]
                
                # 在每个文本列中搜索
                for column in columns:
                    try:
                        if use_regex:
                            # 正则表达式搜索：获取所有数据然后在Python中过滤
                            query = f"SELECT * FROM {table_name} LIMIT 10000"
                            cursor.execute(query)
                            rows = cursor.fetchall()
                            
                            import re
                            # 编译正则表达式
                            flags = 0 if case_sensitive else re.IGNORECASE
                            try:
                                regex_pattern = re.compile(search_pattern, flags)
                            except re.error as e:
                                print(f"正则表达式错误: {e}")
                                continue
                            
                            for row in rows:
                                # 创建行数据字典
                                row_data = dict(zip(columns, row))
                                
                                # 获取列值并转换为字符串
                                column_value = str(row_data.get(column, ""))
                                
                                # 使用正则表达式匹配
                                if regex_pattern.search(column_value):
                                    result = SearchResult(
                                        package_name=db_info.package_name,
                                        database_name=db_info.database_name,
                                        table_name=table_name,
                                        column_name=column,
                                        row_data=row_data,
                                        match_value=column_value,
                                        parent_dir=db_info.parent_dir
                                    )
                                    results.append(result)
                        else:
                            # 普通字符串搜索
                            if case_sensitive:
                                query = f"""
                                    SELECT * FROM {table_name} 
                                    WHERE {column} LIKE '%{search_pattern}%'
                                    LIMIT 100
                                """
                            else:
                                query = f"""
                                    SELECT * FROM {table_name} 
                                    WHERE LOWER({column}) LIKE '%{search_pattern}%'
                                    LIMIT 100
                                """
                            
                            cursor.execute(query)
                            rows = cursor.fetchall()
                            
                            for row in rows:
                                # 创建行数据字典
                                row_data = dict(zip(columns, row))
                                
                                # 获取匹配的值
                                match_value = str(row_data.get(column, ""))
                                
                                result = SearchResult(
                                    package_name=db_info.package_name,
                                    database_name=db_info.database_name,
                                    table_name=table_name,
                                    column_name=column,
                                    row_data=row_data,
                                    match_value=match_value,
                                    parent_dir=db_info.parent_dir
                                )
                                results.append(result)
                    
                    except sqlite3.Error:
                        # 忽略列类型不兼容等错误
                        continue
        
        except sqlite3.Error as e:
            print(f"搜索数据库失败 {db_info.database_path}: {e}")
        
        finally:
            if 'conn' in locals():
                conn.close()
        
        return results
    
    def get_database_statistics(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "total_packages": len(self.databases),
            "total_databases": 0,
            "total_tables": 0,
            "package_details": {}
        }
        
        for package_name, package_dbs in self.databases.items():
            package_stats = {
                "directories": len(package_dbs),
                "databases": 0,
                "tables": 0,
                "directory_details": {}
            }
            
            for parent_dir, dir_dbs in package_dbs.items():
                dir_stats = {
                    "databases": len(dir_dbs),
                    "tables": 0,
                    "database_details": {}
                }
                
                for db_name, db_info in dir_dbs.items():
                    table_count = len(db_info.tables or [])
                    dir_stats["tables"] += table_count
                    dir_stats["database_details"][db_name] = {
                        "tables": table_count,
                        "table_names": db_info.tables or []
                    }
                
                package_stats["databases"] += dir_stats["databases"]
                package_stats["tables"] += dir_stats["tables"]
                package_stats["directory_details"][parent_dir] = dir_stats
            
            stats["total_databases"] += package_stats["databases"]
            stats["total_tables"] += package_stats["tables"]
            stats["package_details"][package_name] = package_stats
        
        return stats
    
    def close_all_connections(self):
        """关闭所有数据库连接"""
        for conn in self.connections.values():
            try:
                conn.close()
            except:
                pass
        self.connections.clear() 