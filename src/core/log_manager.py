# -*- coding: utf-8 -*-
"""
日志管理模块
负责保存搜索结果和操作日志
"""

import os
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


def safe_json_serialize(obj):
    """
    安全的JSON序列化函数，处理bytes类型
    """
    def convert_value(value):
        if isinstance(value, bytes):
            try:
                # 尝试解码为UTF-8字符串
                return value.decode('utf-8', errors='replace')
            except:
                # 如果解码失败，转换为十六进制字符串
                return f"<bytes:{value.hex()}>"
        elif isinstance(value, dict):
            return {k: convert_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [convert_value(item) for item in value]
        else:
            return value
    
    return convert_value(obj)


class LogManager:
    """日志管理器"""
    
    def __init__(self, base_dir: str = "./log"):
        """
        初始化日志管理器
        
        Args:
            base_dir: 日志基础目录
        """
        self.base_dir = Path(base_dir)
        self.ensure_log_directory()
    
    def ensure_log_directory(self):
        """确保日志目录存在"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def get_log_filename(self, prefix: str = "search", extension: str = "json") -> str:
        """
        生成日志文件名
        
        Args:
            prefix: 文件名前缀
            extension: 文件扩展名
            
        Returns:
            完整的日志文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.{extension}"
        return str(self.base_dir / filename)
    
    def save_search_results(self, search_term: str, results: List, case_sensitive: bool = False, use_regex: bool = False) -> str:
        """
        保存搜索结果
        
        Args:
            search_term: 搜索词
            results: 搜索结果列表
            case_sensitive: 是否区分大小写
            use_regex: 是否使用正则表达式
            
        Returns:
            保存的文件路径
        """
        # 生成文件名
        json_file = self.get_log_filename("search", "json")
        csv_file = self.get_log_filename("search", "csv")
        
        # 准备数据
        search_data = {
            "search_info": {
                "search_term": search_term,
                "case_sensitive": case_sensitive,
                "use_regex": use_regex,
                "timestamp": datetime.now().isoformat(),
                "result_count": len(results)
            },
            "results": []
        }
        
        csv_data = []
        csv_headers = ["包名", "目录", "数据库", "表名", "列名", "匹配内容", "完整行数据"]
        
        for result in results:
            # 安全序列化行数据
            safe_row_data = safe_json_serialize(result.row_data)
            
            # JSON格式数据
            result_data = {
                "package_name": result.package_name,
                "parent_dir": result.parent_dir,
                "database_name": result.database_name,
                "table_name": result.table_name,
                "column_name": result.column_name,
                "match_value": result.match_value,
                "row_data": safe_row_data
            }
            search_data["results"].append(result_data)
            
            # CSV格式数据
            csv_row = [
                result.package_name,
                result.parent_dir,
                result.database_name,
                result.table_name,
                result.column_name,
                result.match_value,
                json.dumps(safe_row_data, ensure_ascii=False)
            ]
            csv_data.append(csv_row)
        
        # 保存JSON文件
        try:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(search_data, f, ensure_ascii=False, indent=2)
            print(f"搜索结果已保存到JSON: {json_file}")
        except Exception as e:
            print(f"保存JSON文件失败: {e}")
        
        # 保存CSV文件
        try:
            with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(csv_headers)
                writer.writerows(csv_data)
            print(f"搜索结果已保存到CSV: {csv_file}")
        except Exception as e:
            print(f"保存CSV文件失败: {e}")
        
        return json_file
    
    def save_operation_log(self, operation: str, details: Dict[str, Any]) -> str:
        """
        保存操作日志
        
        Args:
            operation: 操作类型
            details: 操作详情
            
        Returns:
            保存的文件路径
        """
        log_file = self.get_log_filename("operation", "json")
        
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "details": details
        }
        
        try:
            # 如果文件已存在，追加到现有日志
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    existing_logs = json.load(f)
                if not isinstance(existing_logs, list):
                    existing_logs = [existing_logs]
            else:
                existing_logs = []
            
            existing_logs.append(log_data)
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(existing_logs, f, ensure_ascii=False, indent=2)
            
            print(f"操作日志已保存: {log_file}")
            return log_file
            
        except Exception as e:
            print(f"保存操作日志失败: {e}")
            return ""
    
    def get_recent_logs(self, count: int = 10) -> List[str]:
        """
        获取最近的日志文件
        
        Args:
            count: 获取数量
            
        Returns:
            日志文件路径列表
        """
        try:
            log_files = []
            for file_path in self.base_dir.iterdir():
                if file_path.is_file() and file_path.suffix in ['.json', '.csv']:
                    log_files.append(file_path)
            
            # 按修改时间排序
            log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            return [str(f) for f in log_files[:count]]
            
        except Exception as e:
            print(f"获取日志文件失败: {e}")
            return []
    
    def clean_old_logs(self, days: int = 30):
        """
        清理旧日志文件
        
        Args:
            days: 保留天数
        """
        try:
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(days=days)
            
            for file_path in self.base_dir.iterdir():
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        file_path.unlink()
                        print(f"删除旧日志文件: {file_path}")
                        
        except Exception as e:
            print(f"清理日志文件失败: {e}")
    
    def export_search_summary(self, search_results_files: List[str]) -> str:
        """
        导出搜索结果汇总
        
        Args:
            search_results_files: 搜索结果文件列表
            
        Returns:
            汇总文件路径
        """
        summary_file = self.get_log_filename("search_summary", "json")
        
        summary_data = {
            "export_time": datetime.now().isoformat(),
            "total_searches": len(search_results_files),
            "searches": []
        }
        
        try:
            for file_path in search_results_files:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        search_data = json.load(f)
                        
                    summary_data["searches"].append({
                        "file": file_path,
                        "search_term": search_data.get("search_info", {}).get("search_term", ""),
                        "timestamp": search_data.get("search_info", {}).get("timestamp", ""),
                        "result_count": search_data.get("search_info", {}).get("result_count", 0)
                    })
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)
            
            print(f"搜索汇总已保存: {summary_file}")
            return summary_file
            
        except Exception as e:
            print(f"导出搜索汇总失败: {e}")
            return "" 