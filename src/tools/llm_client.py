"""
LLMClient - 内部 AI 服务封装

调用内部 AI 服务进行错误分析辅助
"""

import os
import requests
from typing import Dict, Optional


class LLMClient:
    """
    内部 AI 服务客户端

    用于辅助 Skill 分析复杂错误模式
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
        self.api_url = api_url or os.environ.get("LLM_API_URL", "https://aiapi-test.huan.tv/anthropic")
        self.api_token = api_token or os.environ.get("LLM_API_TOKEN", "")
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "glm-5")

    def analyze(
        self,
        log_excerpt: str,
        task_type: str,
        skill_result: Dict
    ) -> Dict:
        """
        分析错误

        Args:
            log_excerpt: 错误日志片段（最多 2000 字符）
            task_type: 任务类型
            skill_result: Skill 初步分析结果

        Returns:
            {
                "error_category": str,
                "error_description": str,
                "suggested_actions": list,
                "confidence": float
            }
        """
        try:
            prompt = self._build_prompt(log_excerpt, task_type, skill_result)

            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_token,
            }

            payload = {
                "model": self.model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}]
            }

            response = requests.post(
                f"{self.api_url}/v1/messages",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                return {"error_category": "UNKNOWN", "confidence": 0.0}

            data = response.json()
            content = data.get("content", [])
            if content:
                text = content[0].get("text", "")
                return self._parse_response(text)

            return {"error_category": "UNKNOWN", "confidence": 0.0}

        except requests.RequestException:
            return {"error_category": "UNKNOWN", "confidence": 0.0}

    def _build_prompt(self, log_excerpt: str, task_type: str, skill_result: Dict) -> str:
        """构建分析提示词"""
        return f"""分析以下错误日志并给出修复建议。

任务类型: {task_type}
Skill 初步分析: {skill_result.get('error_type', 'unknown')} (置信度: {skill_result.get('confidence', 0)})

错误日志:
{log_excerpt[:2000]}

请返回以下格式:
Error category: [RESOURCE|NETWORK|DATA|CONFIG|EXECUTION]
Error description: [简短描述]
Suggested actions: [动作列表]
Confidence: [0-1]
"""

    def _parse_response(self, text: str) -> Dict:
        """解析 LLM 响应"""
        result = {
            "error_category": "UNKNOWN",
            "error_description": "",
            "suggested_actions": [],
            "confidence": 0.5
        }

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
            elif line.startswith("Confidence:"):
                try:
                    result["confidence"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

        return result


__all__ = ["LLMClient"]