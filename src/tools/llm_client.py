"""
LLMClient - 内部 AI 服务封装

LLM 是深度分析师：
- 对 KNOWN_NEEDS_LLM 进行具体定位和原因分析
- 对 UNKNOWN 进行完全分析
- 返回 JSON 格式的分析结果，包含 script_changes 或 config_changes
"""

import os
import requests
from typing import Dict, Optional


class LLMClient:
    """
    内部 AI 服务客户端

    用于深度分析 Skill 无法自动修复的错误
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化

        Args:
            api_url: AI 服务 URL（默认从环境变量）
            api_token: 认证令牌（默认从环境变量）
            model: 模型名称
        """
        self.api_url = api_url or os.environ.get("LLM_API_URL", "https://coding.dashscope.aliyuncs.com/apps/anthropic")
        self.api_token = api_token or os.environ.get("LLM_API_KEY") or os.environ.get("LLM_API_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL") or os.environ.get("ANTHROPIC_MODEL", "glm-5")

    def analyze(
        self,
        log_excerpt: str,
        task_type: str,
        skill_result: Dict
    ) -> Dict:
        """
        深度分析错误

        Args:
            log_excerpt: 错误日志片段（最多 2000 字符）
            task_type: 任务类型
            skill_result: Skill 预判结果（包含 error_type, llm_hint）

        Returns:
            {
                "error_category": str,
                "error_description": str,
                "suggested_actions": list,
                "can_auto_fix": bool,
                "confidence": float,
                "script_changes": dict,  # 如果可以自动修复脚本
                "config_changes": dict,  # 如果可以自动修复配置
            }
        """
        try:
            prompt = self._build_prompt(log_excerpt, task_type, skill_result)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_token}",
                "x-api-key": self.api_token,  # 兼容Anthropic格式
            }

            payload = {
                "model": self.model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}]
            }

            print(f"[LLM] Calling API: {self.api_url}/v1/messages")
            print(f"[LLM] Model: {self.model}")

            response = requests.post(
                f"{self.api_url}/v1/messages",
                headers=headers,
                json=payload,
                timeout=90
            )

            print(f"[LLM] Status: {response.status_code}")
            if response.status_code != 200:
                print(f"[LLM] Error: {response.text[:200]}")
                return {"error_category": "UNKNOWN", "confidence": 0.0}

            data = response.json()
            print(f"[LLM] Response keys: {data.keys()}")
            content = data.get("content", [])
            if content:
                # Find the text element (DashScope returns thinking + text)
                text = ""
                for item in content:
                    if item.get("type") == "text":
                        text = item.get("text", "")
                        break
                print(f"[LLM] Text length: {len(text)}")
                return self._parse_response(text)

            return {"error_category": "UNKNOWN", "confidence": 0.0}

        except requests.RequestException as e:
            print(f"[LLM] Request error: {e}")
            return {"error_category": "UNKNOWN", "confidence": 0.0}

    def _build_prompt(self, log_excerpt: str, task_type: str, skill_result: Dict) -> str:
        """构建分析提示词"""
        error_type = skill_result.get("error_type", "unknown")
        llm_hint = skill_result.get("llm_hint", "")

        # 如果有 llm_hint，强调这是已知错误类型的深度分析
        if llm_hint:
            return f"""分析以下错误日志，找出具体错误原因并提供修复建议。

## 任务类型
{task_type}

## Skill 预判
错误类型: {error_type}
分析提示: {llm_hint}

## 错误日志
{log_excerpt[:2000]}

## 分析要求
1. 从日志中定位具体错误位置和原因
2. 如果是脚本拼写错误，找出拼写错误的命令和正确命令
3. 如果是语法错误（如引号不闭合），指出缺少的符号和位置
4. 如果能自动修复，给出具体的修复内容

## 输出格式（JSON）
返回一个 JSON 对象，包含以下字段：
- error_category: 错误类别（RESOURCE/NETWORK/DATA/CONFIG/EXECUTION）
- error_description: 具体错误原因描述
- suggested_actions: 修复动作列表
  - action_type: 动作类型（modify_script/modify_config/rerun/suggested）
  - description: 动作描述
  - script_changes: 脚本修改内容（字典格式，key 是日志中实际出现的错误内容，value 是正确替换内容）
    例如：脚本中有 "ech hello"，则 script_changes 为 {"ech hello": "echo hello"} 或 {"ech": "echo"}
  - config_changes: 配置修改内容（字典格式）
- can_auto_fix: 是否可以自动修复（true/false）
- confidence: 分析置信度（0.0-1.0）

注意：script_changes 的 key 必须是日志中实际出现的错误内容片段，value 是修正后的内容。不要使用占位符如 "wrong" 或 "correct"。
"""
        else:
            # UNKNOWN 类型，完全分析
            return f"""分析以下错误日志，识别错误原因并给出修复建议。

## 任务类型
{task_type}

## 错误日志
{log_excerpt[:2000]}

## 分析要求
1. 分析日志中的错误信息，识别错误类型
2. 找出错误的具体位置和原因
3. 如果能自动修复，给出具体的修复内容

## 输出格式（JSON）
返回一个 JSON 对象，包含以下字段：
- error_category: 错误类别（RESOURCE/NETWORK/DATA/CONFIG/EXECUTION）
- error_description: 具体错误原因描述
- suggested_actions: 修复动作列表
  - action_type: 动作类型（modify_script/modify_config/rerun/suggested）
  - description: 动作描述
  - script_changes: 脚本修改内容（字典格式，key 是日志中实际出现的错误内容，value 是正确替换内容）
  - config_changes: 配置修改内容（字典格式）
- can_auto_fix: 是否可以自动修复（true/false）
- confidence: 分析置信度（0.0-1.0）

注意：script_changes 的 key 必须是日志中实际出现的错误内容片段，value 是修正后的内容。不要使用占位符。
"""

    def _parse_response(self, text: str) -> Dict:
        """解析 LLM 响应"""
        import json
        result = {
            "error_category": "UNKNOWN",
            "error_description": "",
            "suggested_actions": [],
            "can_auto_fix": False,
            "confidence": 0.5,
        }

        # 尝试解析 JSON
        try:
            # 提取 JSON 内容（可能包含在其他文本中）
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = text[json_start:json_end]
                parsed = json.loads(json_str)

                # 验证并提取字段
                if "error_category" in parsed:
                    result["error_category"] = parsed["error_category"]
                if "error_description" in parsed:
                    result["error_description"] = parsed["error_description"]
                if "suggested_actions" in parsed and isinstance(parsed["suggested_actions"], list):
                    result["suggested_actions"] = parsed["suggested_actions"]
                if "can_auto_fix" in parsed:
                    result["can_auto_fix"] = parsed["can_auto_fix"]
                if "confidence" in parsed:
                    result["confidence"] = float(parsed["confidence"])

                return result
        except (json.JSONDecodeError, ValueError):
            pass

        # 回退到逐行解析
        lines = text.strip().split("\n")
        for line in lines:
            if line.startswith("Error category:"):
                category = line.split(":", 1)[1].strip()
                if category in ["RESOURCE", "NETWORK", "DATA", "CONFIG", "EXECUTION"]:
                    result["error_category"] = category
            elif line.startswith("Error description:"):
                result["error_description"] = line.split(":", 1)[1].strip()
            elif line.startswith("Suggested actions:"):
                actions_str = line.split(":", 1)[1].strip()
                result["suggested_actions"] = [{"action_type": "suggested", "description": actions_str}]
            elif line.startswith("Can auto fix:"):
                result["can_auto_fix"] = line.split(":", 1)[1].strip().lower() == "true"
            elif line.startswith("Confidence:"):
                try:
                    result["confidence"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

        return result


__all__ = ["LLMClient"]