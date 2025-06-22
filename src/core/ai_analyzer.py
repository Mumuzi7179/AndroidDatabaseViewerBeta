# -*- coding: utf-8 -*-
"""
AI分析模块
负责调用AI API进行数据分析
"""

import json
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .ai_config import AIConfig, AIConfigManager


@dataclass
class AnalysisResult:
    """分析结果数据类"""
    package_name: str
    app_type: str
    data_summary: str
    forensic_value: str
    key_findings: List[str]
    risk_level: str  # 高、中、低
    

class AIAnalyzer:
    """AI分析器"""
    
    def __init__(self):
        self.config_manager = AIConfigManager()
        self.config = self.config_manager.load_config()
    
    def update_config(self, config: AIConfig):
        """更新配置"""
        self.config = config
    
    def test_connection(self) -> tuple[bool, str]:
        """测试AI连接"""
        try:
            # 对于思考模型，不限制token数量，让AI充分思考完成
            response = self._make_api_call("这是一个连接测试。请思考后直接回复：连接成功")
            if response and response != "AI响应内容为空":
                if "连接成功" in response:
                    return True, "连接测试成功"
                else:
                    return True, f"连接成功，AI回复: {response[:150]}..."
            else:
                return False, "AI无响应或响应为空"
        except Exception as e:
            return False, f"连接测试失败: {str(e)}"
    
    def _make_api_call(self, prompt: str, max_tokens: Optional[int] = None, max_retries: int = 5) -> Optional[str]:
        """调用AI API（带重试机制）"""
        if not self.config:
            raise Exception("AI配置未设置")
        
        # 准备请求参数
        if self.config.ai_type == "remote":
            url = self.config.remote_api_url
            headers = {
                "Authorization": f"Bearer {self.config.remote_api_key}",
                "Content-Type": "application/json"
            }
            model = self.config.remote_model
            timeout = self.config.remote_timeout
        else:  # local
            url = self.config.local_api_url
            headers = {"Content-Type": "application/json"}
            model = self.config.local_model
            timeout = self.config.local_timeout
        
        # 清理提示词，避免特殊字符导致的400错误
        cleaned_prompt = self._clean_prompt(prompt)
        
        # 构建请求体
        data = {
            "messages": [
                {"role": "user", "content": cleaned_prompt}
            ],
            "temperature": self.config.temperature
        }
        
        # 只有当指定了max_tokens时才添加此字段
        if max_tokens is not None:
            data["max_tokens"] = max_tokens
        elif self.config.max_tokens > 0:
            data["max_tokens"] = self.config.max_tokens
        
        # 只有当模型名称不为空时才添加model字段
        if model and model.strip():
            data["model"] = model
        
        # 重试机制
        last_error = None
        for attempt in range(max_retries):
            try:
                print(f"AI API调用尝试 {attempt + 1}/{max_retries}")
                
                # 调试信息：记录请求大小
                import json as json_module
                request_size = len(json_module.dumps(data).encode('utf-8'))
                print(f"请求数据大小: {request_size} 字节")
                
                if request_size > 10000:  # 10KB
                    print(f"⚠️ 请求数据较大，可能导致400错误")
                
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                
                # 记录响应状态
                print(f"响应状态: {response.status_code}")
                
                if response.status_code == 400:
                    print(f"400错误详情: {response.text[:500]}")
                
                response.raise_for_status()
                
                result = response.json()
                
                # 检查是否有错误信息
                if "error" in result:
                    raise Exception(f"API返回错误: {result['error']}")
                
                # 解析响应
                if "choices" in result and len(result["choices"]) > 0:
                    message = result["choices"][0]["message"]
                    
                    # 优先获取content字段（最终答案）
                    content = message.get("content", "").strip()
                    
                    # 如果content为空，尝试reasoning_content（可能AI还在思考中）
                    if not content and "reasoning_content" in message:
                        content = message["reasoning_content"].strip()
                    
                    # 如果还是为空，尝试其他可能的字段
                    if not content:
                        for field in ["text", "response", "output"]:
                            if field in message and message[field]:
                                content = str(message[field]).strip()
                                break
                    
                    if content:
                        print(f"AI API调用成功，响应长度: {len(content)}")
                        return content
                    else:
                        raise Exception("AI响应内容为空")
                else:
                    raise Exception(f"AI API响应格式异常: {result}")
                    
            except requests.exceptions.Timeout as e:
                last_error = f"请求超时 (尝试 {attempt + 1})"
                print(f"AI API超时: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)  # 等待2秒后重试
                    continue
                    
            except requests.exceptions.RequestException as e:
                last_error = f"网络请求失败: {str(e)} (尝试 {attempt + 1})"
                print(f"AI API网络错误: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)  # 等待1秒后重试
                    continue
                    
            except Exception as e:
                last_error = f"API调用异常: {str(e)} (尝试 {attempt + 1})"
                print(f"AI API异常: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)  # 等待1秒后重试
                    continue
        
        # 所有重试都失败了
        raise Exception(f"AI API调用失败 ({max_retries}次重试): {last_error}")
    
    def analyze_single_app(self, package_name: str, database_data: Dict[str, Any]) -> AnalysisResult:
        """分析单个应用"""
        print(f"🔍 开始分析应用: {package_name}")
        
        # 对于已知problematic的包，使用简化分析
        problematic_packages = [
            "com.sweetpotato.biquge", "com.xmonster.letsgo", 
            # 可以根据观察到的失败包名添加更多
        ]
        
        if package_name in problematic_packages:
            print(f"⚠️ {package_name} 已知存在分析问题，使用简化分析")
            return self._simple_analysis(package_name, database_data)
        
        # 构建分析提示词
        prompt = self._build_analysis_prompt(package_name, database_data)
        
        # 统计数据库结构信息
        total_tables = 0
        tables_with_data = 0
        for db_name, db_info in database_data.items():
            if "tables" in db_info:
                for table_name, table_data in db_info["tables"].items():
                    total_tables += 1
                    if table_data.get("row_count", 0) > 0:
                        tables_with_data += 1
        
        # 记录请求大小和数据概况
        prompt_size = len(prompt.encode('utf-8'))
        print(f"📊 {package_name} - 请求大小: {prompt_size} 字节, {total_tables} 个表({tables_with_data} 个有数据)")
        
        try:
            # 调用AI分析（更多重试次数）
            response = self._make_api_call(prompt, max_retries=5)  # 增加重试次数
            
            if not response:
                print(f"❌ {package_name} - AI返回空响应，尝试简化分析")
                return self._simple_analysis(package_name, database_data)
            
            # 解析AI回复
            result = self._parse_analysis_response(package_name, response)
            print(f"✅ {package_name} - 分析完成，风险等级: {result.risk_level}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ {package_name} - 分析失败: {error_msg}")
            
            # 根据错误类型提供更友好的信息
            friendly_error = "分析异常"
            if "prediction-error" in error_msg.lower():
                friendly_error = "LM Studio预测错误，可能是模型负载过高"
            elif "timeout" in error_msg.lower() or "超时" in error_msg:
                friendly_error = "请求超时，建议增加超时时间"
            elif "connection" in error_msg.lower() or "连接" in error_msg:
                friendly_error = "连接失败，请检查LM Studio状态"
            elif "json" in error_msg.lower():
                friendly_error = "响应格式错误，模型输出异常"
            elif "400" in error_msg:
                friendly_error = "请求数据过大或格式错误"
            
            return AnalysisResult(
                package_name=package_name,
                app_type="分析失败",
                data_summary=f"{friendly_error}: {error_msg[:100]}",
                forensic_value="建议手动检查或重试",
                key_findings=[f"自动分析失败: {friendly_error}"],
                risk_level="未知"
            )
    
    def _simple_analysis(self, package_name: str, database_data: Dict[str, Any]) -> AnalysisResult:
        """简化分析，基于包名和数据库结构进行基本判断"""
        print(f"🔍 对 {package_name} 进行简化分析")
        
        # 基于包名判断应用类型
        app_type = "未知应用"
        if "chat" in package_name.lower() or "message" in package_name.lower():
            app_type = "社交通讯"
        elif "game" in package_name.lower() or "play" in package_name.lower():
            app_type = "游戏"
        elif "shop" in package_name.lower() or "pay" in package_name.lower():
            app_type = "购物支付"
        elif "music" in package_name.lower() or "video" in package_name.lower():
            app_type = "影音娱乐"
        elif "tool" in package_name.lower() or "util" in package_name.lower():
            app_type = "工具效率"
        elif "book" in package_name.lower() or "read" in package_name.lower():
            app_type = "阅读应用"
        
        # 统计数据库信息
        total_tables = 0
        total_rows = 0
        important_tables = []
        
        for db_name, db_info in database_data.items():
            if "tables" in db_info:
                for table_name, table_data in db_info["tables"].items():
                    total_tables += 1
                    row_count = table_data.get("row_count", 0)
                    total_rows += row_count
                    
                    # 检查是否是重要表
                    if row_count > 0:
                        table_lower = table_name.lower()
                        if any(keyword in table_lower for keyword in [
                            'message', 'chat', 'contact', 'user', 'account',
                            'history', 'record', 'data', 'content'
                        ]):
                            important_tables.append(f"{table_name}({row_count}行)")
        
        # 生成数据摘要
        data_summary = f"包含{total_tables}个数据表，总计{total_rows}行数据"
        if important_tables:
            data_summary += f"，重要表：{', '.join(important_tables[:3])}"
        
        # 取证价值评估
        forensic_value = "数据量较少，需要手动检查具体内容"
        if total_rows > 100:
            forensic_value = "包含较多数据记录，建议深入分析具体内容寻找证据"
        if important_tables:
            forensic_value = f"发现重要数据表：{', '.join(important_tables[:3])}，可能包含聊天记录、联系人、交易记录等证据信息"
        
        # 关键证据点
        key_findings = [
            f"数据规模: {total_tables}个表，共{total_rows}行记录",
            f"应用类型: {app_type}类应用"
        ]
        
        if important_tables:
            key_findings.append(f"发现{len(important_tables)}个重要数据表，可能包含用户隐私数据")
        
        # 根据表名推测可能的证据类型
        evidence_hints = []
        for table_name in [t.split('(')[0] for t in important_tables]:
            table_lower = table_name.lower()
            if 'message' in table_lower or 'chat' in table_lower:
                evidence_hints.append("可能包含聊天记录")
            elif 'contact' in table_lower:
                evidence_hints.append("可能包含联系人信息")
            elif 'user' in table_lower or 'account' in table_lower:
                evidence_hints.append("可能包含账户信息")
            elif 'history' in table_lower:
                evidence_hints.append("可能包含历史记录")
        
        if evidence_hints:
            key_findings.extend(evidence_hints[:2])
        
        # 风险等级
        risk_level = "低"
        if total_rows > 1000:
            risk_level = "中"
        if any("user" in t.lower() or "account" in t.lower() for t in important_tables):
            risk_level = "高"
        
        return AnalysisResult(
            package_name=package_name,
            app_type=app_type,
            data_summary=data_summary,
            forensic_value=forensic_value,
            key_findings=key_findings,
            risk_level=risk_level
        )
    
    def _build_analysis_prompt(self, package_name: str, database_data: Dict[str, Any]) -> str:
        """构建分析提示词（限制2万token）"""
        prompt = f"""请你作为一名数字取证专家，分析以下Android应用的数据库结构和内容：

应用包名: {package_name}

数据库信息:
"""
        
        total_tables = 0
        current_length = len(prompt)
        max_length = 20000  # 2万字符限制
        
        # 精简的数据库结构信息
        for db_name, db_info in database_data.items():
            if current_length > max_length:
                prompt += "\n[数据库信息过多，已截断...]"
                break
                
            db_summary = f"\n📁 数据库: {db_name}\n"
            
            if "tables" in db_info:
                table_summaries = []
                for table_name, table_data in db_info["tables"].items():
                    total_tables += 1
                    
                    # 基本表信息
                    row_count = table_data.get("row_count", 0)
                    table_summary = f"  📋 表: {table_name} ({row_count}行)"
                    
                    # 列信息
                    if "columns" in table_data and table_data['columns']:
                        cols = table_data['columns']
                        table_summary += f"\n    🔧 字段: {', '.join(cols)}"
                    
                    # 第一行数据示例（如果有数据）
                    if ("sample_data" in table_data and table_data["sample_data"] and row_count > 0):
                        try:
                            first_row = table_data["sample_data"][0]
                            sample_str = str(first_row)
                            # 限制单行数据长度
                            if len(sample_str) > 200:
                                sample_str = sample_str[:200] + "..."
                            table_summary += f"\n    💾 示例数据: {sample_str}"
                        except:
                            pass
                    
                    # 检查长度，避免超出限制
                    if current_length + len(table_summary) > max_length:
                        table_summaries.append(f"  [还有{len(db_info['tables']) - len(table_summaries)}个表未显示]")
                        break
                    
                    table_summaries.append(table_summary)
                
                db_summary += "\n".join(table_summaries)
            
            # 检查总长度
            if current_length + len(db_summary) > max_length:
                prompt += "\n[数据库信息过多，已截断...]"
                break
            
            prompt += db_summary
            current_length += len(db_summary)
        
        prompt += f"""

🔍 数字取证分析要求：
基于上述数据库结构和示例数据，请重点关注：
• 聊天记录、联系人、通话记录
• 交易记录、账单、支付信息  
• 密码、秘钥、Token等敏感信息
• 虚拟币钱包地址、交易记录
• 记事本、备忘录内容
• 浏览历史、搜索记录
• 位置信息、时间戳
• 文件路径、账号信息

请按格式分析(用中文)：

1. 应用类型: [社交通讯|购物支付|影音娱乐|工具效率|游戏|记账理财|浏览器|系统应用|其他]

2. 证据摘要: [发现了哪些类型的重要数据]

3. 具体证据内容: [从示例数据中提取的具体信息，包括人名、金额、地址、时间等细节]

4. 关键证据点: [3-5个最重要的具体发现，用||分隔]

5. 取证价值: [高|中|低] - [价值说明]

⚠️ 重点：要从示例数据中提取具体内容，不要只说"包含XX记录"，要说具体发现了什么。
"""
        
        return prompt
    
    def _parse_analysis_response(self, package_name: str, response: str) -> AnalysisResult:
        """解析AI分析回复"""
        try:
            # 解析结构化回复
            app_type = self._extract_field(response, "应用类型", "未知应用")
            data_summary = self._extract_field(response, "证据摘要", "无证据摘要")
            evidence_content = self._extract_field(response, "具体证据内容", "")
            key_findings_str = self._extract_field(response, "关键证据点", "")
            forensic_value_str = self._extract_field(response, "取证价值", "低")
            
            # 解析取证价值（格式：等级 - 原因）
            if " - " in forensic_value_str:
                risk_level, forensic_reason = forensic_value_str.split(" - ", 1)
                forensic_value = f"{risk_level.strip()}：{forensic_reason.strip()}"
                risk_level = risk_level.strip()
            else:
                risk_level = forensic_value_str.strip()
                forensic_value = f"取证价值：{risk_level}"
            
            # 合并证据内容和具体证据内容
            if evidence_content:
                if data_summary == "无证据摘要":
                    data_summary = evidence_content[:100] + ("..." if len(evidence_content) > 100 else "")
                forensic_value = evidence_content
            
            # 处理关键证据点
            key_findings = []
            if key_findings_str:
                key_findings = [f.strip() for f in key_findings_str.split("||") if f.strip()]
            
            if not key_findings:
                key_findings = ["暂无具体证据发现"]
            
            return AnalysisResult(
                package_name=package_name,
                app_type=app_type,
                data_summary=data_summary,
                forensic_value=forensic_value,
                key_findings=key_findings,
                risk_level=risk_level
            )
            
        except Exception as e:
            # 如果解析失败，返回原始回复
            return AnalysisResult(
                package_name=package_name,
                app_type="解析异常",
                data_summary=response[:200] + "..." if len(response) > 200 else response,
                forensic_value="解析失败",
                key_findings=[f"回复解析异常: {str(e)}"],
                risk_level="未知"
            )
    
    def _extract_field(self, text: str, field_name: str, default: str = "") -> str:
        """从文本中提取指定字段"""
        try:
            # 查找字段标识
            start_marker = f"{field_name}:"
            start_pos = text.find(start_marker)
            
            if start_pos == -1:
                return default
            
            # 找到内容开始位置
            content_start = start_pos + len(start_marker)
            
            # 找到下一个数字编号位置（如"2. "、"3. "等）
            import re
            next_section = re.search(r'\n\s*\d+\.\s+', text[content_start:])
            
            if next_section:
                content_end = content_start + next_section.start()
                content = text[content_start:content_end].strip()
            else:
                # 如果没找到下一个section，取到文本结尾
                content = text[content_start:].strip()
            
            # 清理内容
            content = content.replace("[", "").replace("]", "").strip()
            
            return content if content else default
            
        except Exception:
            return default
    
    def _clean_prompt(self, prompt: str) -> str:
        """清理提示词，移除可能导致API错误的字符"""
        try:
            # 移除控制字符
            import re
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', prompt)
            
            # 移除过长的行
            lines = cleaned.split('\n')
            cleaned_lines = []
            for line in lines:
                if len(line) > 500:  # 限制单行长度
                    line = line[:500] + "..."
                cleaned_lines.append(line)
            
            cleaned = '\n'.join(cleaned_lines)
            
            # 总长度限制
            if len(cleaned) > 8000:
                cleaned = cleaned[:8000] + "\n\n[内容过长，已截断...]"
            
            return cleaned
        except Exception as e:
            print(f"清理提示词失败: {e}")
            return prompt[:5000]  # 发生错误时至少截断长度
    
    def chat(self, message: str) -> str:
        """普通对话"""
        try:
            print(f"💬 开始AI对话...")
            response = self._make_api_call(message, max_retries=3)
            
            if response:
                print(f"💬 对话完成，响应长度: {len(response)}")
                return response
            else:
                print(f"💬 对话失败：AI无响应")
                return "AI无响应，请检查连接状态或重试"
                
        except Exception as e:
            error_msg = str(e)
            print(f"💬 对话异常: {error_msg}")
            
            # 提供更友好的错误信息
            if "prediction-error" in error_msg.lower():
                return "LM Studio预测错误，模型可能负载过高，请稍后重试"
            elif "timeout" in error_msg.lower() or "超时" in error_msg:
                return "请求超时，请检查网络连接或增加超时时间"
            elif "connection" in error_msg.lower() or "连接" in error_msg:
                return "连接失败，请确认LM Studio正在运行且API可用"
            else:
                return f"对话异常: {error_msg}" 