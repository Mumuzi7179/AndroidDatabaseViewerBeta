# -*- coding: utf-8 -*-
"""
AI配置管理模块
负责AI相关配置的保存和加载
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class AIConfig:
    """AI配置数据类"""
    # 通用配置
    ai_type: str = "remote"  # remote 或 local
    
    # 远程AI配置 (如 OpenAI, Claude 等)
    remote_api_key: str = ""
    remote_api_url: str = "https://api.openai.com/v1/chat/completions"
    remote_model: str = "gpt-3.5-turbo"
    remote_timeout: int = 60
    
    # 本地AI配置 (如 LM Studio)
    local_api_url: str = "http://localhost:1234/v1/chat/completions"
    local_model: str = ""  # LM Studio通常不需要指定模型名称
    local_timeout: int = 120
    
    # 分析配置
    max_tokens: int = 4000
    temperature: float = 0.7
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AIConfig':
        """从字典创建实例"""
        return cls(**data)


class AIConfigManager:
    """AI配置管理器"""
    
    def __init__(self):
        self.config_file = Path("config") / "ai_config.json"
        self.config = AIConfig()
        self._ensure_config_dir()
    
    def _ensure_config_dir(self):
        """确保配置目录存在"""
        self.config_file.parent.mkdir(exist_ok=True)
    
    def load_config(self) -> AIConfig:
        """加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = AIConfig.from_dict(data)
                    print(f"AI配置加载成功: {self.config_file}")
            except Exception as e:
                print(f"加载AI配置失败: {e}")
                self.config = AIConfig()
        else:
            print("AI配置文件不存在，使用默认配置")
        
        return self.config
    
    def save_config(self, config: AIConfig):
        """保存配置"""
        try:
            self.config = config
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
            print(f"AI配置保存成功: {self.config_file}")
            return True
        except Exception as e:
            print(f"保存AI配置失败: {e}")
            return False
    
    def get_config(self) -> AIConfig:
        """获取当前配置"""
        return self.config
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        if self.config.ai_type == "remote":
            return bool(self.config.remote_api_key and self.config.remote_api_url)
        elif self.config.ai_type == "local":
            return bool(self.config.local_api_url)  # 本地模式只需要URL即可
        return False 