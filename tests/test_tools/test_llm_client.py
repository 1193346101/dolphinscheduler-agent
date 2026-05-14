"""
LLMClient 测试
"""

import pytest
from unittest.mock import Mock, patch
from src.tools.llm_client import LLMClient


class TestLLMClient:

    def test_init_with_url(self):
        """测试初始化"""
        client = LLMClient(api_url="https://aiapi-test.huan.tv/anthropic", api_token="test_token")
        assert client.api_url == "https://aiapi-test.huan.tv/anthropic"

    @patch("requests.post")
    def test_analyze_success(self, mock_post):
        """测试分析成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Error category: RESOURCE\nSuggested action: Increase memory"}],
            "usage": {"input_tokens": 100, "output_tokens": 50}
        }
        mock_post.return_value = mock_response

        client = LLMClient("https://test", "token")
        result = client.analyze(
            log_excerpt="OutOfMemoryError in executor",
            task_type="SPARK",
            skill_result={"error_type": "unknown", "confidence": 0.5}
        )

        assert result["error_category"] == "RESOURCE"
        assert result["token_usage"]["input_tokens"] == 100
        assert result["token_usage"]["output_tokens"] == 50

    @patch("requests.post")
    def test_analyze_api_failure(self, mock_post):
        """测试 API 失败"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        client = LLMClient("https://test", "token")
        result = client.analyze(
            log_excerpt="some log",
            task_type="SPARK",
            skill_result={"error_type": "unknown", "confidence": 0.3}
        )

        assert result["confidence"] == 0.0
        # Token 消耗估算（只有 input）
        assert result["token_usage"]["total_tokens"] > 0

    def test_build_prompt(self):
        """测试构建提示词"""
        client = LLMClient("https://test", "token")

        prompt = client._build_prompt(
            log_excerpt="OutOfMemoryError",
            task_type="SPARK",
            skill_result={"error_type": "oom_executor", "confidence": 0.6}
        )

        assert "OutOfMemoryError" in prompt
        assert "SPARK" in prompt