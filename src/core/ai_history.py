import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import asdict
from ..core.ai_analyzer import AnalysisResult


class AIHistoryManager:
    """AI历史数据管理器"""
    
    def __init__(self, history_file: str = "ai_history.json"):
        self.history_file = history_file
        self.history_data = {
            "chat_history": [],
            "analysis_results": [],
            "last_updated": None
        }
        self.load_history()
    
    def load_history(self) -> bool:
        """加载历史数据"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.history_data = data
                    print(f"✓ AI历史数据加载成功: {self.history_file}")
                    return True
            else:
                print(f"ℹ️ AI历史文件不存在，将创建新文件: {self.history_file}")
                return False
        except Exception as e:
            print(f"❌ AI历史数据加载失败: {str(e)}")
            return False
    
    def save_history(self) -> bool:
        """保存历史数据"""
        try:
            self.history_data["last_updated"] = datetime.now().isoformat()
            
            # 确保目录存在
            os.makedirs(os.path.dirname(self.history_file) if os.path.dirname(self.history_file) else ".", exist_ok=True)
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
            
            print(f"✓ AI历史数据保存成功: {self.history_file}")
            return True
        except Exception as e:
            print(f"❌ AI历史数据保存失败: {str(e)}")
            return False
    
    def add_chat_message(self, message_type: str, content: str, timestamp: Optional[str] = None):
        """添加聊天消息"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        chat_entry = {
            "type": message_type,  # "user" 或 "ai"
            "content": content,
            "timestamp": timestamp
        }
        
        self.history_data["chat_history"].append(chat_entry)
        
        # 保持聊天记录在合理范围内（最多1000条）
        if len(self.history_data["chat_history"]) > 1000:
            self.history_data["chat_history"] = self.history_data["chat_history"][-1000:]
    
    def get_chat_history(self) -> List[Dict[str, str]]:
        """获取聊天历史"""
        return self.history_data.get("chat_history", [])
    
    def clear_chat_history(self):
        """清空聊天历史"""
        self.history_data["chat_history"] = []
        print("🗑️ 聊天历史已清空")
    
    def save_analysis_results(self, results: List[AnalysisResult], timestamp: Optional[str] = None):
        """保存分析结果"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        # 转换AnalysisResult为字典
        results_data = []
        for result in results:
            result_dict = asdict(result)
            results_data.append(result_dict)
        
        analysis_entry = {
            "timestamp": timestamp,
            "results": results_data,
            "count": len(results)
        }
        
        self.history_data["analysis_results"].append(analysis_entry)
        
        # 保持分析结果在合理范围内（最多50次分析）
        if len(self.history_data["analysis_results"]) > 50:
            self.history_data["analysis_results"] = self.history_data["analysis_results"][-50:]
        
        print(f"💾 分析结果已保存: {len(results)} 个应用")
    
    def get_latest_analysis_results(self) -> Optional[List[AnalysisResult]]:
        """获取最新的分析结果"""
        if not self.history_data["analysis_results"]:
            return None
        
        latest_entry = self.history_data["analysis_results"][-1]
        results = []
        
        try:
            for result_dict in latest_entry["results"]:
                result = AnalysisResult(**result_dict)
                results.append(result)
            
            print(f"📋 加载最新分析结果: {len(results)} 个应用")
            return results
        except Exception as e:
            print(f"❌ 分析结果解析失败: {str(e)}")
            return None
    
    def get_all_analysis_sessions(self) -> List[Dict[str, Any]]:
        """获取所有分析会话信息"""
        sessions = []
        for entry in self.history_data["analysis_results"]:
            session_info = {
                "timestamp": entry["timestamp"],
                "count": entry["count"],
                "formatted_time": self._format_timestamp(entry["timestamp"])
            }
            sessions.append(session_info)
        return sessions
    
    def get_analysis_results_by_index(self, index: int) -> Optional[List[AnalysisResult]]:
        """根据索引获取分析结果"""
        if 0 <= index < len(self.history_data["analysis_results"]):
            entry = self.history_data["analysis_results"][index]
            results = []
            
            try:
                for result_dict in entry["results"]:
                    result = AnalysisResult(**result_dict)
                    results.append(result)
                return results
            except Exception as e:
                print(f"❌ 分析结果解析失败: {str(e)}")
                return None
        return None
    
    def clear_analysis_results(self):
        """清空分析结果"""
        self.history_data["analysis_results"] = []
        print("🗑️ 分析结果已清空")
    
    def _format_timestamp(self, timestamp: str) -> str:
        """格式化时间戳"""
        try:
            dt = datetime.fromisoformat(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return timestamp
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_chat_messages": len(self.history_data["chat_history"]),
            "total_analysis_sessions": len(self.history_data["analysis_results"]),
            "last_updated": self.history_data.get("last_updated"),
            "history_file_size": os.path.getsize(self.history_file) if os.path.exists(self.history_file) else 0
        } 