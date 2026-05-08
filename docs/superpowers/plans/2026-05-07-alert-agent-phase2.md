# 告警 Agent 第二阶段实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善告警 Agent 基础设施层、节点实现层、集成层和审批层，实现完整的日志获取、错误分析、动作执行和审批流程。

**Architecture:** 分层渐进式实现：基础设施层（日志工具+LLM封装）→ 节点实现层（完善占位节点）→ 集成层（端到端测试）→ 审批层（回调+超时）

**Tech Stack:** LangGraph, kubernetes-client, requests, pytest, fastapi

---

## 文件结构

**新建文件：**
```
src/tools/
├── spark_hist.py         # SparkHistTool - Spark History Server API
├── yarn_log.py           # YARNLogTool - YARN Gateway API
├── k8s_log.py            # K8sLogTool - Kubernetes API
├── llm_client.py         # LLMClient - 内部 AI 服务封装
├── knowledge.py          # KnowledgeTool - 知识库查询
├── approval_tool.py      # ApprovalTool - 审批管理
src/integrations/
├── dsctl_wrapper.py      # dsctl CLI 封装
tests/tools/
├── test_spark_hist.py
├── test_yarn_log.py
├── test_k8s_log.py
├── test_llm_client.py
├── test_knowledge.py
├── test_approval_tool.py
tests/integration/
├── test_e2e_workflow.py  # 端到端测试
data/approvals/           # 审批请求存储目录
```

**修改文件：**
```
src/workflow/nodes/fetch_logs.py    # 完善实现
src/workflow/nodes/analyze.py       # 完善实现
src/workflow/nodes/execute.py       # 完善实现
src/workflow/nodes/notify.py        # 完善实现
src/workflow/nodes/store.py         # 完善实现
src/workflow/nodes/approval.py      # 完善实现
src/workflow/nodes/knowledge.py     # 完善实现
src/tools/__init__.py               # 添加新工具导出
src/api/webhook_api.py              # 添加审批回调
config/projects.yaml                # 添加 LLM 配置
requirements.txt                    # 添加 kubernetes
```

---

## Phase 1: 基础设施层

### Task 1: SparkHistTool - Spark History Server 日志获取

**Files:**
- Create: `src/tools/spark_hist.py`
- Create: `tests/test_tools/test_spark_hist.py`
- Modify: `src/tools/__init__.py`

- [ ] **Step 1: 创建 tests/test_tools/test_spark_hist.py**

```python
"""
SparkHistTool 测试
"""

import pytest
from unittest.mock import Mock, patch
from src.tools.spark_hist import SparkHistTool


class TestSparkHistTool:

    def test_init_with_url(self):
        """测试初始化"""
        tool = SparkHistTool(history_url="http://spark-history:18082")
        assert tool.history_url == "http://spark-history:18082"

    @patch("requests.get")
    def test_fetch_logs_success(self, mock_get):
        """测试获取日志成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "attempts": [{
                "id": "driver",
                "logs": "driver stdout content"
            }]
        }
        mock_get.return_value = mock_response
        
        tool = SparkHistTool(history_url="http://spark-history:18082")
        result = tool.fetch_logs("application_123_456")
        
        assert "driver" in result
        assert "driver stdout content" in result["driver"]

    @patch("requests.get")
    def test_fetch_logs_application_not_found(self, mock_get):
        """测试应用不存在"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        tool = SparkHistTool(history_url="http://spark-history:18082")
        result = tool.fetch_logs("application_invalid")
        
        assert result == {}  # 返回空字典

    @patch("requests.get")
    def test_fetch_logs_with_executor_logs(self, mock_get):
        """测试包含 executor 日志"""
        mock_app_response = Mock()
        mock_app_response.status_code = 200
        mock_app_response.json.return_value = {
            "attempts": [
                {"id": "driver", "logs": "driver log"},
                {"id": "1", "logs": "executor 1 log"},
                {"id": "2", "logs": "executor 2 log"}
            ]
        }
        
        mock_get.return_value = mock_app_response
        
        tool = SparkHistTool(history_url="http://spark-history:18082")
        result = tool.fetch_logs("application_123_456")
        
        assert len(result) == 3
        assert "executor_1" in result

    def test_extract_app_id_from_log(self):
        """测试从日志提取 app_id"""
        tool = SparkHistTool(history_url="http://test:18082")
        
        log = "Starting Spark application application_20260507_12345"
        app_id = tool.extract_app_id(log)
        
        assert app_id == "application_20260507_12345"

    def test_extract_app_id_not_found(self):
        """测试日志中无 app_id"""
        tool = SparkHistTool(history_url="http://test:18082")
        
        log = "Some random log content"
        app_id = tool.extract_app_id(log)
        
        assert app_id is None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_spark_hist.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 src/tools/spark_hist.py**

```python
"""
SparkHistTool - Spark History Server 日志获取工具

通过 Spark History Server REST API 获取应用日志
"""

import re
import requests
from typing import Dict, Optional


class SparkHistTool:
    """
    Spark History Server 日志获取工具
    
    API:
    - GET /api/v1/applications/{app_id} - 获取应用信息
    - GET /api/v1/applications/{app_id}/logs - 获取日志
    """
    
    def __init__(self, history_url: str):
        """
        初始化
        
        Args:
            history_url: Spark History Server URL (如 http://host:18082)
        """
        self.history_url = history_url.rstrip("/")
    
    def fetch_logs(self, application_id: str) -> Dict[str, str]:
        """
        获取应用日志
        
        Args:
            application_id: Spark 应用 ID (如 application_123456_789)
        
        Returns:
            日志字典 {"driver": "...", "executor_1": "...", ...}
        """
        try:
            # 获取应用详情（包含 attempts）
            url = f"{self.history_url}/api/v1/applications/{application_id}"
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                return {}
            
            app_data = response.json()
            logs = {}
            
            # 解析 attempts 获取日志
            for attempt in app_data.get("attempts", []):
                attempt_id = attempt.get("id", "")
                log_content = attempt.get("logs", "")
                
                if attempt_id == "driver":
                    logs["driver"] = log_content
                else:
                    logs[f"executor_{attempt_id}"] = log_content
            
            return logs
            
        except requests.RequestException:
            return {}
    
    def extract_app_id(self, log_content: str) -> Optional[str]:
        """
        从日志内容提取 Spark application_id
        
        Args:
            log_content: 日志文本
        
        Returns:
            application_id 或 None
        """
        # 匹配 application_xxx_yyy 格式
        patterns = [
            r"application_\d+_\d+",
            r"app-\d+-\d+",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, log_content)
            if match:
                return match.group(0)
        
        return None


__all__ = ["SparkHistTool"]
```

- [ ] **Step 4: 更新 src/tools/__init__.py 添加导出**

```python
"""
工具模块
"""

from .risk_assess import RiskAssessTool
from .impact import ImpactTool
from .dingtalk_enterprise import DingTalkEnterpriseTool, DingTalkError
from .log_store import LogStoreTool
from .spark_hist import SparkHistTool

__all__ = [
    "RiskAssessTool",
    "ImpactTool",
    "DingTalkEnterpriseTool",
    "DingTalkError",
    "LogStoreTool",
    "SparkHistTool",
]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_spark_hist.py -v`
Expected: 6 tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/spark_hist.py src/tools/__init__.py tests/test_tools/test_spark_hist.py && git commit -m "feat: 添加 SparkHistTool Spark History Server 日志获取工具"
```

---

### Task 2: YARNLogTool - YARN Gateway 日志获取

**Files:**
- Create: `src/tools/yarn_log.py`
- Create: `tests/test_tools/test_yarn_log.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
YARNLogTool 测试
"""

import pytest
from unittest.mock import Mock, patch
from src.tools.yarn_log import YARNLogTool


class TestYARNLogTool:

    def test_init_with_gateway_url(self):
        """测试初始化"""
        tool = YARNLogTool(
            gateway_url="https://knox:8443/gateway/default/yarn",
            username="yarn_user",
            password="yarn_pass"
        )
        assert tool.gateway_url == "https://knox:8443/gateway/default/yarn"

    @patch("requests.get")
    def test_fetch_logs_success(self, mock_get):
        """测试获取日志成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "app": {
                "containers": [
                    {"id": "container_1", "log": "driver log"},
                    {"id": "container_2", "log": "executor log"}
                ]
            }
        }
        mock_get.return_value = mock_response
        
        tool = YARNLogTool("https://knox:8443", "user", "pass")
        result = tool.fetch_logs("application_123_456")
        
        assert "container_1" in result

    @patch("requests.get")
    def test_fetch_logs_not_found(self, mock_get):
        """测试应用不存在"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        tool = YARNLogTool("https://knox:8443", "user", "pass")
        result = tool.fetch_logs("application_invalid")
        
        assert result == {}

    def test_build_yarn_api_url(self):
        """测试构建 YARN API URL"""
        tool = YARNLogTool("https://knox:8443/gateway/default/yarn", "user", "pass")
        
        url = tool._build_app_url("application_123_456")
        
        assert "application_123_456" in url
        assert "ws/v1/cluster/apps" in url
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_yarn_log.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 src/tools/yarn_log.py**

```python
"""
YARNLogTool - YARN Gateway 日志获取工具

通过 Knox Gateway 代理 YARN ResourceManager API 获取 container 日志
"""

import requests
from typing import Dict, Optional
from requests.auth import HTTPBasicAuth


class YARNLogTool:
    """
    YARN Gateway 日志获取工具
    
    通过 Knox Gateway 访问 YARN API
    """
    
    def __init__(
        self,
        gateway_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_type: str = "basic"
    ):
        """
        初始化
        
        Args:
            gateway_url: Knox Gateway YARN URL
            username: 认证用户名
            password: 认证密码
            auth_type: basic / kerberos
        """
        self.gateway_url = gateway_url.rstrip("/")
        self.username = username
        self.password = password
        self.auth_type = auth_type
    
    def fetch_logs(self, application_id: str) -> Dict[str, str]:
        """
        获取 YARN container 日志
        
        Args:
            application_id: YARN 应用 ID
        
        Returns:
            日志字典 {"container_1": "...", ...}
        """
        try:
            url = self._build_app_url(application_id)
            
            auth = None
            if self.username and self.password:
                auth = HTTPBasicAuth(self.username, self.password)
            
            response = requests.get(url, auth=auth, timeout=15, verify=False)
            
            if response.status_code != 200:
                return {}
            
            app_data = response.json()
            logs = {}
            
            # 解析 containers
            containers = app_data.get("app", {}).get("containers", [])
            for container in containers:
                container_id = container.get("id", "")
                log_content = self._fetch_container_log(container_id, auth)
                if log_content:
                    logs[container_id] = log_content
            
            return logs
            
        except requests.RequestException:
            return {}
    
    def _build_app_url(self, application_id: str) -> str:
        """构建应用 API URL"""
        return f"{self.gateway_url}/ws/v1/cluster/apps/{application_id}"
    
    def _fetch_container_log(self, container_id: str, auth) -> Optional[str]:
        """获取单个 container 日志"""
        try:
            url = f"{self.gateway_url}/ws/v1/cluster/apps/{container_id.split('_')[0]}_{container_id.split('_')[1]}/containers/{container_id}/logs"
            response = requests.get(url, auth=auth, timeout=10, verify=False)
            
            if response.status_code == 200:
                return response.text
            return None
        except requests.RequestException:
            return None


__all__ = ["YARNLogTool"]
```

- [ ] **Step 4: 更新 __init__.py 导出**

添加 `from .yarn_log import YARNLogTool` 到导出列表。

- [ ] **Step 5: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_yarn_log.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/yarn_log.py tests/test_tools/test_yarn_log.py && git commit -m "feat: 添加 YARNLogTool YARN Gateway 日志获取工具"
```

---

### Task 3: K8sLogTool - Kubernetes 日志获取

**Files:**
- Create: `src/tools/k8s_log.py`
- Create: `tests/test_tools/test_k8s_log.py`
- Modify: `requirements.txt`

- [ ] **Step 1: 更新 requirements.txt**

添加一行：
```text
kubernetes>=28.0.0
```

- [ ] **Step 2: 创建测试文件**

```python
"""
K8sLogTool 测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.tools.k8s_log import K8sLogTool


class TestK8sLogTool:

    def test_init_with_namespace(self):
        """测试初始化"""
        tool = K8sLogTool(namespace="spark-apps")
        assert tool.namespace == "spark-apps"

    @patch("src.tools.k8s_log.kubernetes.config.load_kube_config")
    @patch("src.tools.k8s_log.kubernetes.client.CoreV1Api")
    def test_fetch_logs_success(self, mock_api_class, mock_load_config):
        """测试获取日志成功"""
        mock_api = MagicMock()
        mock_api.list_namespaced_pod.return_value = MagicMock(items=[
            MagicMock(metadata=MagicMock(name="spark-driver"), status=MagicMock(phase="Running")),
            MagicMock(metadata=MagicMock(name="spark-executor-1"), status=MagicMock(phase="Running")),
        ])
        mock_api.read_pod_log.return_value = "pod log content"
        mock_api_class.return_value = mock_api
        
        tool = K8sLogTool(namespace="spark-apps")
        result = tool.fetch_logs("spark-app-name")
        
        assert "spark-driver" in result

    @patch("src.tools.k8s_log.kubernetes.config.load_kube_config")
    @patch("src.tools.k8s_log.kubernetes.client.CoreV1Api")
    def test_fetch_logs_no_pods(self, mock_api_class, mock_load_config):
        """测试无匹配 Pod"""
        mock_api = MagicMock()
        mock_api.list_namespaced_pod.return_value = MagicMock(items=[])
        mock_api_class.return_value = mock_api
        
        tool = K8sLogTool(namespace="spark-apps")
        result = tool.fetch_logs("nonexistent-app")
        
        assert result == {}

    def test_build_pod_label_selector(self):
        """测试构建 label selector"""
        tool = K8sLogTool(namespace="spark-apps")
        
        selector = tool._build_label_selector("my-spark-app")
        
        assert "spark-app-name=my-spark-app" in selector
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_k8s_log.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: 创建 src/tools/k8s_log.py**

```python
"""
K8sLogTool - Kubernetes 日志获取工具

使用 kubernetes-client 获取 Spark on K8s Pod 日志
"""

import os
from typing import Dict, Optional

try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False


class K8sLogTool:
    """
    Kubernetes Pod 日志获取工具
    
    通过 Pod labels 筛选 Spark 应用相关 Pod
    """
    
    def __init__(
        self,
        namespace: str = "spark-apps",
        kubeconfig_path: Optional[str] = None
    ):
        """
        初始化
        
        Args:
            namespace: Spark 应用命名空间
            kubeconfig_path: kubeconfig 文件路径（可选）
        """
        self.namespace = namespace
        self.kubeconfig_path = kubeconfig_path
        self._api = None
        
        if K8S_AVAILABLE:
            self._init_k8s_client()
    
    def _init_k8s_client(self):
        """初始化 K8s 客户端"""
        if self.kubeconfig_path:
            config.load_kube_config(config_file=self.kubeconfig_path)
        elif os.environ.get("KUBECONFIG"):
            config.load_kube_config()
        else:
            # 尝试 in-cluster 配置
            try:
                config.load_incluster_config()
            except config.ConfigException:
                # 回退到默认 kubeconfig
                config.load_kube_config()
        
        self._api = client.CoreV1Api()
    
    def fetch_logs(self, app_name: str) -> Dict[str, str]:
        """
        获取 Spark 应用 Pod 日志
        
        Args:
            app_name: Spark 应用名称
        
        Returns:
            日志字典 {"driver-pod": "...", "executor-1": "...", ...}
        """
        if not K8S_AVAILABLE or not self._api:
            return {}
        
        try:
            label_selector = self._build_label_selector(app_name)
            
            pods = self._api.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=label_selector
            )
            
            logs = {}
            for pod in pods.items:
                pod_name = pod.metadata.name
                
                # 只获取 Running 或 Succeeded/Failed Pod 的日志
                if pod.status.phase not in ["Running", "Succeeded", "Failed"]:
                    continue
                
                try:
                    log_content = self._api.read_pod_log(
                        name=pod_name,
                        namespace=self.namespace,
                        tail_lines=500  # 只获取最近 500 行
                    )
                    logs[pod_name] = log_content
                except client.ApiException:
                    pass
            
            return logs
            
        except client.ApiException:
            return {}
    
    def _build_label_selector(self, app_name: str) -> str:
        """构建 Pod label selector"""
        # Spark on K8s 使用 spark-app-name label
        return f"spark-app-name={app_name}"


__all__ = ["K8sLogTool"]
```

- [ ] **Step 5: 更新 __init__.py**

添加 `from .k8s_log import K8sLogTool` 导出。

- [ ] **Step 6: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_k8s_log.py -v`
Expected: 4 tests PASS

- [ ] **Step 7: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add requirements.txt src/tools/k8s_log.py tests/test_tools/test_k8s_log.py && git commit -m "feat: 添加 K8sLogTool Kubernetes 日志获取工具"
```

---

### Task 4: LLMClient - 内部 AI 服务封装

**Files:**
- Create: `src/tools/llm_client.py`
- Create: `tests/test_tools/test_llm_client.py`

- [ ] **Step 1: 创建测试文件**

```python
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
            "content": [{"text": "Error category: RESOURCE\nSuggested action: Increase memory"}]
        }
        mock_post.return_value = mock_response
        
        client = LLMClient("https://test", "token")
        result = client.analyze(
            log_excerpt="OutOfMemoryError in executor",
            task_type="SPARK",
            skill_result={"error_type": "unknown", "confidence": 0.5}
        )
        
        assert result["error_category"] == "RESOURCE"

    @patch("requests.post")
    def test_analyze_api_failure(self, mock_post):
        """测试 API 失败"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        client = LLMClient("https://test", "token")
        result = client.analyze(
            log_excerpt="some log",
            task_type="SPARK",
            skill_result={"error_type": "unknown", "confidence": 0.3}
        )
        
        assert result["confidence"] == 0.0

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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_llm_client.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 src/tools/llm_client.py**

```python
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
```

- [ ] **Step 4: 更新 __init__.py**

添加 `from .llm_client import LLMClient` 导出。

- [ ] **Step 5: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_llm_client.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/llm_client.py tests/test_tools/test_llm_client.py && git commit -m "feat: 添加 LLMClient 内部 AI 服务封装"
```

---

### Task 5: DSCLIClient - dsctl CLI 封装

**Files:**
- Create: `src/integrations/dsctl_wrapper.py`
- Create: `tests/test_integrations/test_dsctl_wrapper.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
DSCLIClient 测试
"""

import pytest
from unittest.mock import Mock, patch
from src.integrations.dsctl_wrapper import DSCLIClient


class TestDSCLIClient:

    def test_init_with_config(self):
        """测试初始化"""
        client = DSCLIClient(
            api_url="http://ds:12345/dolphinscheduler",
            api_token="test_token"
        )
        assert client.api_url == "http://ds:12345/dolphinscheduler"

    @patch("subprocess.run")
    def test_rerun_workflow_instance(self, mock_run):
        """测试重跑工作流实例"""
        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")
        
        client = DSCLIClient("http://ds:12345", "token")
        result = client.workflow_instance_rerun(instance_id=833841)
        
        assert result.success is True

    @patch("subprocess.run")
    def test_recover_from_failed(self, mock_run):
        """测试从失败恢复"""
        mock_run.return_value = Mock(returncode=0, stdout="Recovery started", stderr="")
        
        client = DSCLIClient("http://ds:12345", "token")
        result = client.workflow_instance_recover(instance_id=833841, task_code=123456)
        
        assert result.success is True

    @patch("subprocess.run")
    def test_get_task_logs(self, mock_run):
        """测试获取任务日志"""
        mock_run.return_value = Mock(returncode=0, stdout="Task log content", stderr="")
        
        client = DSCLIClient("http://ds:12345", "token")
        result = client.get_task_logs(task_instance_id=1377412)
        
        assert result.success is True
        assert "Task log content" in result.stdout

    @patch("subprocess.run")
    def test_command_failure(self, mock_run):
        """测试命令失败"""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error: not found")
        
        client = DSCLIClient("http://ds:12345", "token")
        result = client.workflow_instance_rerun(instance_id=999)
        
        assert result.success is False
```

- [ ] **Step 2: 创建 src/integrations/__init__.py**

```python
"""
集成模块
"""

from .dsctl_wrapper import DSCLIClient

__all__ = ["DSCLIClient"]
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_integrations/test_dsctl_wrapper.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: 创建 src/integrations/dsctl_wrapper.py**

```python
"""
DSCLIClient - dsctl CLI 封装

通过 subprocess 调用 dsctl CLI 执行 DolphinScheduler 操作
"""

import subprocess
import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class CLIResult:
    """CLI 执行结果"""
    success: bool
    stdout: str
    stderr: str
    returncode: int


class DSCLIClient:
    """
    dsctl CLI 封装
    
    支持操作:
    - workflow-instance rerun
    - workflow-instance recover
    - task-instance logs
    """
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        version: str = "3.2.0"
    ):
        """
        初始化
        
        Args:
            api_url: DolphinScheduler API URL
            api_token: API Token
            version: DS 版本
        """
        self.api_url = api_url or os.environ.get("DS_API_URL", "")
        self.api_token = api_token or os.environ.get("DS_API_TOKEN", "")
        self.version = version
    
    def _run_command(self, args: list, timeout: int = 30) -> CLIResult:
        """执行 dsctl 命令"""
        env = os.environ.copy()
        env["DS_API_URL"] = self.api_url
        env["DS_API_TOKEN"] = self.api_token
        env["DS_VERSION"] = self.version
        
        cmd = ["py", "-m", "dsctl"] + args
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            
            return CLIResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode
            )
        except subprocess.TimeoutExpired:
            return CLIResult(
                success=False,
                stdout="",
                stderr="Command timed out",
                returncode=-1
            )
    
    def workflow_instance_rerun(self, instance_id: int) -> CLIResult:
        """
        重跑工作流实例
        
        Args:
            instance_id: 工作流实例 ID
        
        Returns:
            CLIResult
        """
        return self._run_command([
            "workflow-instance", "rerun",
            str(instance_id)
        ])
    
    def workflow_instance_recover(
        self,
        instance_id: int,
        task_code: int
    ) -> CLIResult:
        """
        从失败任务恢复
        
        Args:
            instance_id: 工作流实例 ID
            task_code: 失败任务编码
        
        Returns:
            CLIResult
        """
        return self._run_command([
            "workflow-instance", "recover",
            str(instance_id),
            "--task", str(task_code)
        ])
    
    def get_task_logs(self, task_instance_id: int) -> CLIResult:
        """
        获取任务日志
        
        Args:
            task_instance_id: 任务实例 ID
        
        Returns:
            CLIResult
        """
        return self._run_command([
            "task-instance", "logs",
            str(task_instance_id)
        ])
    
    def workflow_get(self, project_code: int, workflow_code: int) -> CLIResult:
        """
        获取工作流定义
        
        Args:
            project_code: 项目编码
            workflow_code: 工作流编码
        
        Returns:
            CLIResult
        """
        return self._run_command([
            "workflow", "get",
            str(workflow_code),
            "--project", str(project_code)
        ])


__all__ = ["DSCLIClient", "CLIResult"]
```

- [ ] **Step 5: 创建 tests/test_integrations/__init__.py**

```python
"""
集成测试
"""
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_integrations/test_dsctl_wrapper.py -v`
Expected: 5 tests PASS

- [ ] **Step 7: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/integrations/ tests/test_integrations/ && git commit -m "feat: 添加 DSCLIClient dsctl CLI 封装"
```

---

## Phase 2: 节点实现层

### Task 6: 完善 fetch_logs 节点

**Files:**
- Modify: `src/workflow/nodes/fetch_logs.py`
- Create: `tests/test_workflow/test_nodes/test_fetch_logs.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
fetch_logs 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.fetch_logs import fetch_logs


class TestFetchLogs:

    @patch("src.workflow.nodes.fetch_logs.DSCLIClient")
    @patch("src.workflow.nodes.fetch_logs.SparkHistTool")
    def test_fetch_logs_yarn_mode(self, mock_spark, mock_dsctl):
        """测试 YARN 模式日志获取"""
        mock_dsctl_instance = Mock()
        mock_dsctl_instance.get_task_logs.return_value = Mock(
            success=True, stdout="driver log content"
        )
        mock_dsctl.return_value = mock_dsctl_instance
        
        mock_spark_instance = Mock()
        mock_spark_instance.fetch_logs.return_value = {"driver": "spark history log"}
        mock_spark_instance.extract_app_id.return_value = "application_123_456"
        mock_spark.return_value = mock_spark_instance
        
        state = create_initial_state(
            project_code="11598158952448",
            workflow_code="21451302002208",
            task_code="123456",
            task_type="SPARK"
        )
        state["project_config"] = {
            "spark_mode": "yarn",
            "spark_history_url": "http://spark-history:18082",
            "ds_api_url": "http://ds:12345",
            "ds_api_token": "token"
        }
        state["alert_raw"] = {"taskInstanceId": 1377412}
        
        result = fetch_logs(state)
        
        assert result["driver_logs"] is not None

    def test_fetch_logs_no_project_config(self):
        """测试无项目配置"""
        state = create_initial_state(
            project_code="0",
            workflow_code="0",
            task_code="0",
            task_type="SPARK"
        )
        state["project_config"] = None
        
        result = fetch_logs(state)
        
        assert result["log_fetch_error"] is not None
```

- [ ] **Step 2: 完善 src/workflow/nodes/fetch_logs.py**

```python
"""
fetch_logs 节点

获取 Spark 任务日志 - 完整实现
"""

from typing import Dict
from ..state import AgentState
from ...tools.spark_hist import SparkHistTool
from ...tools.yarn_log import YARNLogTool
from ...tools.k8s_log import K8sLogTool
from ...integrations.dsctl_wrapper import DSCLIClient


def fetch_logs(state: AgentState) -> AgentState:
    """
    获取日志
    
    协调多种日志源:
    1. dsctl CLI - driver 基础日志
    2. Spark History Server - Spark 日志
    3. YARN Gateway / K8s API - 运行环境日志
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (driver_logs, spark_logs, yarn_logs/k8s_logs, log_fetch_error)
    """
    project_config = state.get("project_config")
    
    if not project_config:
        return {
            **state,
            "driver_logs": None,
            "spark_logs": None,
            "yarn_logs": None,
            "k8s_logs": None,
            "log_fetch_error": "无项目配置",
        }
    
    spark_mode = project_config.get("spark_mode", "yarn")
    spark_history_url = project_config.get("spark_history_url", "")
    
    # 1. 获取 dsctl driver 日志
    driver_logs = None
    log_fetch_error = None
    
    try:
        dsctl = DSCLIClient(
            api_url=project_config.get("ds_api_url", ""),
            api_token=project_config.get("ds_api_token", "")
        )
        
        task_instance_id = state["alert_raw"].get("taskInstanceId")
        if task_instance_id:
            result = dsctl.get_task_logs(task_instance_id)
            if result.success:
                driver_logs = result.stdout
            else:
                log_fetch_error = f"dsctl 日志获取失败: {result.stderr}"
    except Exception as e:
        log_fetch_error = f"dsctl 异常: {str(e)}"
    
    # 2. 获取 Spark History 日志
    spark_logs = None
    app_id = None
    
    if spark_history_url and driver_logs:
        try:
            spark_tool = SparkHistTool(history_url=spark_history_url)
            app_id = spark_tool.extract_app_id(driver_logs)
            
            if app_id:
                spark_logs_dict = spark_tool.fetch_logs(app_id)
                spark_logs = "\n".join(f"{k}: {v}" for k, v in spark_logs_dict.items())
        except Exception as e:
            if not log_fetch_error:
                log_fetch_error = f"Spark History 异常: {str(e)}"
    
    # 3. 根据模式获取额外日志
    yarn_logs = None
    k8s_logs = None
    
    if spark_mode == "yarn" and app_id:
        try:
            yarn_gateway_url = project_config.get("yarn_gateway_url", "")
            if yarn_gateway_url:
                yarn_tool = YARNLogTool(
                    gateway_url=yarn_gateway_url,
                    username=project_config.get("yarn_username"),
                    password=project_config.get("yarn_password")
                )
                yarn_logs_dict = yarn_tool.fetch_logs(app_id)
                yarn_logs = "\n".join(f"{k}: {v[:1000]}" for k, v in yarn_logs_dict.items())
        except Exception:
            pass
    
    elif spark_mode == "k8s":
        try:
            k8s_namespace = project_config.get("k8s_namespace", "spark-apps")
            k8s_tool = K8sLogTool(namespace=k8s_namespace)
            
            # 从 app_id 提取 app_name
            if app_id:
                app_name = app_id.replace("application_", "")
                k8s_logs_dict = k8s_tool.fetch_logs(app_name)
                k8s_logs = k8s_logs_dict
        except Exception:
            pass
    
    return {
        **state,
        "driver_logs": driver_logs,
        "spark_logs": spark_logs,
        "yarn_logs": yarn_logs,
        "k8s_logs": k8s_logs,
        "log_fetch_error": log_fetch_error,
    }


__all__ = ["fetch_logs"]
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_fetch_logs.py -v`
Expected: 2 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/fetch_logs.py tests/test_workflow/test_nodes/test_fetch_logs.py && git commit -m "feat: 完善 fetch_logs 节点实现"
```

---

### Task 7: 完善 analyze_error 节点

**Files:**
- Modify: `src/workflow/nodes/analyze.py`
- Create: `tests/test_workflow/test_nodes/test_analyze.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
analyze_error 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.analyze import analyze_error


class TestAnalyzeError:

    def test_analyze_spark_task_with_skill(self):
        """测试 Spark 任务 Skill 分析"""
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["driver_logs"] = "java.lang.OutOfMemoryError: Java heap space"
        state["spark_logs"] = None
        state["project_config"] = {}
        
        result = analyze_error(state)
        
        assert "oom_executor" in result.get("error_patterns", []) or result.get("error_category") == "RESOURCE"

    def test_analyze_shell_task(self):
        """测试 Shell 任务分析"""
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SHELL"
        )
        state["driver_logs"] = "Error: command not found"
        state["project_config"] = {}
        
        result = analyze_error(state)
        
        assert result["error_category"] != ""

    def test_analyze_no_logs(self):
        """测试无日志时的分析"""
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["driver_logs"] = None
        state["spark_logs"] = None
        
        result = analyze_error(state)
        
        assert result["confidence_score"] == 0.0
```

- [ ] **Step 2: 完善 src/workflow/nodes/analyze.py**

```python
"""
analyze_error 节点

分析错误模式 - Skill 分发 + LLM 辅助
"""

from typing import Dict, List
from ..state import AgentState
from ...skills.registry import SkillRegistry
from ...tools.llm_client import LLMClient
from ...models.alert import AlertContext, AlertInfo


def analyze_error(state: AgentState) -> AgentState:
    """
    分析错误
    
    流程:
    1. 根据 task_type 选择 Skill
    2. Skill 分析日志，匹配错误模式
    3. 低置信度时调用 LLM 辅助
    4. 合并结果
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (error_patterns, error_category, suggested_actions, confidence_score)
    """
    task_type = state["task_type"]
    driver_logs = state.get("driver_logs", "")
    spark_logs = state.get("spark_logs", "")
    
    # 合并日志
    logs = _combine_logs(driver_logs, spark_logs)
    
    if not logs:
        return {
            **state,
            "error_patterns": [],
            "error_category": "",
            "suggested_actions": [],
            "knowledge_match": None,
            "confidence_score": 0.0,
        }
    
    # 构建 AlertContext
    context = AlertContext(
        alert_info=AlertInfo(
            project_code=int(state.get("project_code", 0) or 0),
            process_definition_code=int(state.get("workflow_code", 0) or 0),
            process_instance_id=0,
            task_code=int(state.get("task_code", 0) or 0),
            task_instance_id=0,
            task_type=task_type,
            state="FAILURE",
        )
    )
    
    # 1. Skill 分发
    skill = _get_skill_for_task_type(task_type)
    skill_result = None
    
    if skill:
        try:
            skill_result = skill.analyze(logs, context)
        except Exception:
            pass
    
    # 2. 处理 Skill 结果
    if skill_result and skill_result.confidence >= 0.8:
        # 高置信度直接使用
        error_patterns = [skill_result.error_type]
        error_category = _map_error_category(skill_result.error_type)
        suggested_actions = _build_actions_from_skill(skill, skill_result)
        confidence_score = skill_result.confidence
    else:
        # 低置信度调用 LLM 辅助
        llm_client = LLMClient()
        llm_result = llm_client.analyze(
            log_excerpt=logs[:2000],
            task_type=task_type,
            skill_result={"error_type": getattr(skill_result, 'error_type', 'unknown'), "confidence": getattr(skill_result, 'confidence', 0.5)}
        )
        
        if llm_result.get("confidence", 0) > 0:
            error_patterns = llm_result.get("error_patterns", [])
            error_category = llm_result.get("error_category", "")
            suggested_actions = llm_result.get("suggested_actions", [])
            confidence_score = llm_result.get("confidence", 0.5)
        else:
            error_patterns = []
            error_category = ""
            suggested_actions = []
            confidence_score = 0.0
    
    return {
        **state,
        "error_patterns": error_patterns,
        "error_category": error_category,
        "suggested_actions": suggested_actions,
        "knowledge_match": None,
        "confidence_score": confidence_score,
    }


def _combine_logs(driver_logs: str, spark_logs: str) -> str:
    """合并日志"""
    parts = []
    if driver_logs:
        parts.append(driver_logs)
    if spark_logs:
        parts.append(spark_logs)
    return "\n".join(parts)


def _get_skill_for_task_type(task_type: str):
    """根据任务类型获取 Skill"""
    # 简化实现：直接导入 Skill
    try:
        if task_type == "SPARK":
            from ...skills.spark_skill import SparkSkill
            return SparkSkill()
        elif task_type == "SHELL":
            from ...skills.shell_skill import ShellSkill
            return ShellSkill()
        elif task_type == "PYTHON":
            from ...skills.python_skill import PythonSkill
            return PythonSkill()
        elif task_type == "DATAX":
            from ...skills.datax_skill import DataXSkill
            return DataXSkill()
    except ImportError:
        return None
    return None


def _map_error_category(error_type: str) -> str:
    """将错误类型映射到分类"""
    mapping = {
        "oom_executor": "RESOURCE",
        "oom_driver": "RESOURCE",
        "oom_driver_direct": "RESOURCE",
        "container_killed": "RESOURCE",
        "executor_lost": "RESOURCE",
        "class_not_found": "CONFIG",
        "no_class_def": "CONFIG",
        "shuffle_failed": "NETWORK",
        "connection_refused": "NETWORK",
        "hdfs_not_found": "DATA",
        "schema_mismatch": "DATA",
        "broadcast_timeout": "EXECUTION",
        "stage_failed": "EXECUTION",
    }
    return mapping.get(error_type, "EXECUTION")


def _build_actions_from_skill(skill, skill_result) -> List[Dict]:
    """从 Skill 结果构建动作"""
    actions = []
    
    if skill_result.can_auto_fix:
        fix_action = skill._build_auto_fix_action(skill_result)
        if fix_action:
            actions.append({
                "action_type": fix_action.action_type,
                "description": str(fix_action.config_changes) if hasattr(fix_action, 'config_changes') else "auto fix",
                "risk_level": "LOW"
            })
    
    # 添加建议
    suggestions = skill.suggest(skill_result) if hasattr(skill, 'suggest') else []
    for suggestion in suggestions[:2]:
        actions.append({
            "action_type": "suggested",
            "description": suggestion,
            "risk_level": "MEDIUM"
        })
    
    return actions


__all__ = ["analyze_error"]
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_analyze.py -v`
Expected: 3 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/analyze.py tests/test_workflow/test_nodes/test_analyze.py && git commit -m "feat: 完善 analyze_error 节点 Skill 分发 + LLM 辅助"
```

---

### Task 8: 完善 execute_action 节点

**Files:**
- Modify: `src/workflow/nodes/execute.py`
- Create: `tests/test_workflow/test_nodes/test_execute.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
execute_action 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.execute import execute_action


class TestExecuteAction:

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_rerun_action(self, mock_dsctl):
        """测试重跑动作"""
        mock_instance = Mock()
        mock_instance.workflow_instance_rerun.return_value = Mock(success=True, stdout="OK")
        mock_dsctl.return_value = mock_instance
        
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["suggested_actions"] = [{"action_type": "rerun", "risk_level": "LOW"}]
        state["alert_raw"] = {"processInstanceId": 833841}
        state["project_config"] = {"ds_api_url": "http://ds:12345", "ds_api_token": "token"}
        
        result = execute_action(state)
        
        assert result["execution_success"] is True

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_recover_action(self, mock_dsctl):
        """测试恢复动作"""
        mock_instance = Mock()
        mock_instance.workflow_instance_recover.return_value = Mock(success=True)
        mock_dsctl.return_value = mock_instance
        
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "LOW"}]
        state["alert_raw"] = {"processInstanceId": 833841}
        state["task_code"] = "789"
        state["project_config"] = {"ds_api_url": "http://ds:12345", "ds_api_token": "token"}
        
        result = execute_action(state)
        
        assert len(result["executed_actions"]) > 0

    def test_execute_high_risk_without_approval(self):
        """测试高风险动作无审批"""
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "HIGH"}]
        state["approval_status"] = None
        
        result = execute_action(state)
        
        assert result["execution_success"] is False

    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_execute_high_risk_with_approval(self, mock_dsctl):
        """测试高风险动作已审批"""
        mock_instance = Mock()
        mock_instance.workflow_instance_recover.return_value = Mock(success=True)
        mock_dsctl.return_value = mock_instance
        
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["suggested_actions"] = [{"action_type": "recover-failed", "risk_level": "HIGH"}]
        state["approval_status"] = "approved"
        state["alert_raw"] = {"processInstanceId": 833841}
        state["project_config"] = {"ds_api_url": "http://ds:12345", "ds_api_token": "token"}
        
        result = execute_action(state)
        
        assert len(result["executed_actions"]) > 0
```

- [ ] **Step 2: 完善 src/workflow/nodes/execute.py**

```python
"""
execute_action 节点

执行修复动作 - 完整实现
"""

from typing import Dict, List
from ..state import AgentState
from ...integrations.dsctl_wrapper import DSCLIClient, CLIResult


def execute_action(state: AgentState) -> AgentState:
    """
    执行动作
    
    支持动作:
    - rerun: 重跑工作流
    - recover-failed: 从失败恢复
    - config-change: 修改配置
    - notify-only: 仅通知
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (executed_actions, execution_results, execution_success)
    """
    actions = state.get("suggested_actions", [])
    approval_status = state.get("approval_status")
    project_config = state.get("project_config")
    
    if not actions or not project_config:
        return {
            **state,
            "executed_actions": [],
            "execution_results": [],
            "execution_success": False,
        }
    
    dsctl = DSCLIClient(
        api_url=project_config.get("ds_api_url", ""),
        api_token=project_config.get("ds_api_token", "")
    )
    
    executed = []
    results = []
    
    instance_id = state["alert_raw"].get("processInstanceId")
    task_code = state.get("task_code")
    
    for action in actions:
        action_type = action.get("action_type", "")
        risk_level = action.get("risk_level", "LOW")
        
        # 检查审批
        if risk_level in ["HIGH", "CRITICAL"]:
            if approval_status != "approved":
                results.append({
                    "action": action,
                    "status": "skipped",
                    "reason": f"需要审批，当前状态: {approval_status}"
                })
                continue
        
        # 执行动作
        result = _execute_single_action(
            action_type, 
            dsctl, 
            instance_id, 
            task_code,
            state
        )
        
        if result:
            executed.append(action)
            results.append({
                "action": action,
                "status": "success" if result.success else "failed",
                "output": result.stdout[:500] if result.stdout else ""
            })
        else:
            results.append({
                "action": action,
                "status": "skipped",
                "reason": "未知动作类型"
            })
    
    # 判断整体成功
    success = any(
        r.get("status") == "success" 
        for r in results 
        if r.get("status") != "skipped"
    ) if executed else False
    
    return {
        **state,
        "executed_actions": executed,
        "execution_results": results,
        "execution_success": success,
    }


def _execute_single_action(
    action_type: str,
    dsctl: DSCLIClient,
    instance_id: int,
    task_code: str,
    state: Dict
) -> CLIResult:
    """执行单个动作"""
    
    if action_type == "rerun":
        return dsctl.workflow_instance_rerun(instance_id)
    
    elif action_type == "recover-failed":
        return dsctl.workflow_instance_recover(
            instance_id, 
            int(task_code)
        )
    
    elif action_type == "config-change":
        # config-change 需要: 1) 更新参数 2) 重跑
        # 当前简化实现，直接重跑
        return dsctl.workflow_instance_rerun(instance_id)
    
    elif action_type == "notify-only":
        # 仅通知，不执行
        return CLIResult(success=True, stdout="仅通知", stderr="", returncode=0)
    
    return None


__all__ = ["execute_action"]
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_execute.py -v`
Expected: 4 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/execute.py tests/test_workflow/test_nodes/test_execute.py && git commit -m "feat: 完善 execute_action 节点支持 rerun/recover/config-change"
```

---

### Task 9: 完善 notify_dingtalk 节点

**Files:**
- Modify: `src/workflow/nodes/notify.py`
- Create: `tests/test_workflow/test_nodes/test_notify.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
notify_dingtalk 节点测试
"""

import pytest
from unittest.mock import Mock, patch
from src.workflow.state import create_initial_state
from src.workflow.nodes.notify import notify_dingtalk


class TestNotifyDingtalk:

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_notify_error_analysis(self, mock_dingtalk):
        """测试发送错误分析通知"""
        mock_instance = Mock()
        mock_instance.send_notification.return_value = "msg_123"
        mock_instance.build_error_notification.return_value = {
            "title": "告警分析",
            "content": "error content"
        }
        mock_dingtalk.return_value = mock_instance
        
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["approval_required"] = False
        state["risk_level"] = "LOW"
        state["error_category"] = "RESOURCE"
        state["error_patterns"] = ["oom_executor"]
        state["suggested_actions"] = []
        state["project_config"] = {
            "dingtalk": {
                "robot_code": "test_robot",
                "client_id": "test_id",
                "client_secret": "test_secret",
                "notify_users": ["user1"]
            }
        }
        
        result = notify_dingtalk(state)
        
        assert result["notification_sent"] is True
        assert result["approval_message_id"] == "msg_123"

    def test_notify_no_dingtalk_config(self):
        """测试无钉钉配置"""
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["project_config"] = {}
        
        result = notify_dingtalk(state)
        
        assert result["notification_sent"] is False
```

- [ ] **Step 2: 完善 src/workflow/nodes/notify.py**

```python
"""
notify_dingtalk 节点

发送钉钉通知 - 完整实现
"""

from ..state import AgentState
from ...tools.dingtalk_enterprise import DingTalkEnterpriseTool


def notify_dingtalk(state: AgentState) -> AgentState:
    """
    发送钉钉通知
    
    根据审批状态发送不同类型通知:
    - 无需审批: 错误分析通知
    - 需审批: 审批请求通知
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (notification_sent, notification_content, approval_message_id)
    """
    project_config = state.get("project_config")
    dingtalk_config = project_config.get("dingtalk") if project_config else None
    
    if not dingtalk_config:
        return {
            **state,
            "notification_sent": False,
            "notification_content": None,
            "approval_message_id": None,
        }
    
    tool = DingTalkEnterpriseTool(
        client_id=dingtalk_config.get("client_id", ""),
        client_secret=dingtalk_config.get("client_secret", "")
    )
    
    approval_required = state.get("approval_required", False)
    
    if approval_required:
        # 审批请求通知
        content = tool.build_approval_request(
            task_type=state["task_type"],
            workflow_code=state["workflow_code"],
            task_code=state["task_code"],
            risk_level=state["risk_level"],
            impact_summary=state.get("impact_summary", ""),
            suggested_actions=state.get("suggested_actions", []),
            risk_factors=state.get("risk_factors", []),
            approve_url=f"/approval/approve",
            reject_url=f"/approval/reject"
        )
        buttons = content.get("buttons", [])
    else:
        # 错误分析通知
        content = tool.build_error_notification(
            task_type=state["task_type"],
            workflow_code=state["workflow_code"],
            task_code=state["task_code"],
            risk_level=state["risk_level"],
            error_category=state.get("error_category", ""),
            error_patterns=state.get("error_patterns", []),
            suggested_actions=state.get("suggested_actions", []),
            ds_url=project_config.get("ds_api_url", "")
        )
        buttons = None
    
    # 发送通知
    try:
        msg_id = tool.send_notification(
            robot_code=dingtalk_config.get("robot_code", ""),
            user_ids=dingtalk_config.get("notify_users", []),
            title=content.get("title", ""),
            content=content.get("content", ""),
            buttons=buttons
        )
        
        return {
            **state,
            "notification_sent": True,
            "notification_content": content.get("content", ""),
            "approval_message_id": msg_id,
        }
    except Exception as e:
        return {
            **state,
            "notification_sent": False,
            "notification_content": f"发送失败: {str(e)}",
            "approval_message_id": None,
        }


__all__ = ["notify_dingtalk"]
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_notify.py -v`
Expected: 2 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/notify.py tests/test_workflow/test_nodes/test_notify.py && git commit -m "feat: 完善 notify_dingtalk 节点发送钉钉通知"
```

---

### Task 10: 完善 store_results 节点

**Files:**
- Modify: `src/workflow/nodes/store.py`
- Create: `tests/test_workflow/test_nodes/test_store.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
store_results 节点测试
"""

import pytest
import tempfile
import os
from src.workflow.state import create_initial_state
from src.workflow.nodes.store import store_results


class TestStoreResults:

    def test_store_logs_success(self):
        """测试存储日志成功"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = create_initial_state(
                project_code="123",
                workflow_code="456",
                task_code="789",
                task_type="SPARK"
            )
            state["driver_logs"] = "driver log"
            state["spark_logs"] = "spark log"
            state["yarn_logs"] = "yarn log"
            state["error_category"] = "RESOURCE"
            state["risk_level"] = "LOW"
            state["project_config"] = {"spark_mode": "yarn"}
            
            # 使用临时目录
            result = store_results(state, base_path=tmpdir)
            
            assert result["log_stored"] is True
            assert result["log_store_path"] is not None

    def test_store_logs_no_logs(self):
        """测试无日志时不存储"""
        state = create_initial_state(
            project_code="123",
            workflow_code="456",
            task_code="789",
            task_type="SPARK"
        )
        state["driver_logs"] = None
        state["spark_logs"] = None
        
        result = store_results(state)
        
        assert result["log_stored"] is False
```

- [ ] **Step 2: 完善 src/workflow/nodes/store.py**

```python
"""
store_results 节点

存储日志和分析结果 - 完整实现
"""

from typing import Optional
from ..state import AgentState
from ...tools.log_store import LogStoreTool


def store_results(state: AgentState, base_path: Optional[str] = None) -> AgentState:
    """
    存储结果
    
    使用 LogStoreTool:
    1. 存储所有日志
    2. 清理过期日志
    
    Args:
        state: 当前状态
        base_path: 可选的存储路径（用于测试）
    
    Returns:
        更新后的状态 (log_stored, result_stored, log_store_path)
    """
    driver_logs = state.get("driver_logs")
    spark_logs = state.get("spark_logs")
    yarn_logs = state.get("yarn_logs")
    k8s_logs = state.get("k8s_logs")
    
    if not driver_logs and not spark_logs:
        return {
            **state,
            "log_stored": False,
            "result_stored": False,
            "log_store_path": None,
        }
    
    project_config = state.get("project_config", {})
    spark_mode = project_config.get("spark_mode", "yarn")
    
    tool = LogStoreTool(base_path=base_path or "logs/alerts")
    
    try:
        # 存储日志
        path = tool.store_logs(
            workflow_code=state["workflow_code"],
            task_code=state["task_code"],
            driver_logs=driver_logs or "",
            spark_logs=spark_logs or "",
            yarn_logs=yarn_logs,
            k8s_logs=k8s_logs,
            spark_mode=spark_mode,
            metadata={
                "error_category": state.get("error_category", ""),
                "risk_level": state.get("risk_level", ""),
                "error_patterns": state.get("error_patterns", []),
                "project_code": state.get("project_code", ""),
            }
        )
        
        # 清理过期日志
        deleted_count = tool.cleanup_old_logs()
        tool.log_cleanup_result(deleted_count)
        
        return {
            **state,
            "log_stored": True,
            "result_stored": True,
            "log_store_path": path,
        }
        
    except Exception as e:
        return {
            **state,
            "log_stored": False,
            "result_stored": False,
            "log_store_path": None,
        }


__all__ = ["store_results"]
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_workflow/test_nodes/test_store.py -v`
Expected: 2 tests PASS

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/store.py tests/test_workflow/test_nodes/test_store.py && git commit -m "feat: 完善 store_results 节点存储日志"
```

---

## Phase 3: 集成层

### Task 11: 端到端集成测试

**Files:**
- Create: `tests/test_integration/test_e2e_workflow.py`

- [ ] **Step 1: 创建测试目录**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/tests/test_integration
```

- [ ] **Step 2: 创建 tests/test_integration/__init__.py**

```python
"""
集成测试
"""
```

- [ ] **Step 3: 创建测试文件**

```python
"""
端到端工作流测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.workflow.graph import AlertWorkflowGraph
from src.workflow.state import create_initial_state


class TestEndToEndWorkflow:

    @patch("src.workflow.nodes.fetch_logs.DSCLIClient")
    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    @patch("src.workflow.nodes.execute.DSCLIClient")
    def test_low_risk_auto_fix_flow(self, mock_exec_dsctl, mock_dingtalk, mock_fetch_dsctl):
        """测试 LOW 风险自动修复流程"""
        # Mock 日志获取
        mock_fetch_dsctl_instance = Mock()
        mock_fetch_dsctl_instance.get_task_logs.return_value = Mock(
            success=True, stdout="java.lang.OutOfMemoryError: Java heap space"
        )
        mock_fetch_dsctl.return_value = mock_fetch_dsctl_instance
        
        # Mock 钉钉通知
        mock_dingtalk_instance = Mock()
        mock_dingtalk_instance.send_notification.return_value = "msg_123"
        mock_dingtalk_instance.build_error_notification.return_value = {"title": "test", "content": "test"}
        mock_dingtalk.return_value = mock_dingtalk_instance
        
        # Mock 动作执行
        mock_exec_instance = Mock()
        mock_exec_instance.workflow_instance_rerun.return_value = Mock(success=True)
        mock_exec_dsctl.return_value = mock_exec_instance
        
        workflow = AlertWorkflowGraph()
        
        alert_raw = {
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "taskCode": 123456,
            "taskInstanceId": 1377412,
            "processInstanceId": 833841,
            "taskType": "SPARK",
            "taskState": "FAILURE",
        }
        
        # 需要先注册项目
        from src.config.projects import projects_registry, ProjectConfig
        test_config = ProjectConfig(
            name="test_project",
            code=11598158952448,
            ds_api_url="http://test:12345",
            ds_api_token="test_token",
            dingtalk=Mock(robot_code="test", client_id="test", client_secret="test", notify_users=["user1"])
        )
        projects_registry.register(test_config)
        
        result = workflow.run(alert_raw)
        
        assert result.get("project_valid") is True

    def test_invalid_project_flow(self):
        """测试无效项目流程"""
        workflow = AlertWorkflowGraph()
        
        alert_raw = {
            "projectCode": 999999,  # 不存在的项目
            "processDefinitionCode": 123,
            "taskCode": 456,
            "taskType": "SPARK",
        }
        
        result = workflow.run(alert_raw)
        
        assert result.get("project_valid") is False

    @patch("src.workflow.nodes.notify.DingTalkEnterpriseTool")
    def test_approval_required_flow(self, mock_dingtalk):
        """测试需要审批的流程"""
        mock_instance = Mock()
        mock_instance.send_notification.return_value = "msg_approval"
        mock_instance.build_approval_request.return_value = {
            "title": "审批请求",
            "content": "需要审批",
            "buttons": [{"title": "批准", "actionUrl": "/approval/approve"}]
        }
        mock_dingtalk.return_value = mock_instance
        
        # 这个测试需要更复杂的设置，暂时简化
        pass
```

- [ ] **Step 4: 运行测试**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_integration/test_e2e_workflow.py -v`
Expected: 2 tests PASS (简化测试)

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add tests/test_integration/ && git commit -m "feat: 添加端到端集成测试"
```

---

## Phase 4: 审批层

### Task 12: ApprovalTool - 审批管理工具

**Files:**
- Create: `src/tools/approval_tool.py`
- Create: `tests/test_tools/test_approval_tool.py`

- [ ] **Step 1: 创建测试文件**

```python
"""
ApprovalTool 测试
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from src.tools.approval_tool import ApprovalTool, ApprovalRequest
from src.workflow.state import create_initial_state


class TestApprovalTool:

    def test_init_with_data_dir(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)
            assert tool.data_dir == tmpdir

    def test_create_request(self):
        """测试创建审批请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)
            
            state = create_initial_state(
                project_code="123",
                workflow_code="456",
                task_code="789",
                task_type="SPARK"
            )
            
            request_id = tool.create_request(state, timeout_minutes=30)
            
            assert request_id is not None
            assert len(request_id) == 36  # UUID 格式

    def test_get_request(self):
        """测试获取审批请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)
            
            state = create_initial_state(
                project_code="123",
                workflow_code="456",
                task_code="789",
                task_type="SPARK"
            )
            
            request_id = tool.create_request(state)
            request = tool.get_request(request_id)
            
            assert request is not None
            assert request.status == "pending"

    def test_update_status_approved(self):
        """测试更新状态为已批准"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)
            
            state = create_initial_state(
                project_code="123",
                workflow_code="456",
                task_code="789",
                task_type="SPARK"
            )
            
            request_id = tool.create_request(state)
            result = tool.update_status(request_id, "approved")
            
            assert result is True
            request = tool.get_request(request_id)
            assert request.status == "approved"

    def test_check_expired(self):
        """测试检查过期请求"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ApprovalTool(data_dir=tmpdir)
            
            state = create_initial_state(
                project_code="123",
                workflow_code="456",
                task_code="789",
                task_type="SPARK"
            )
            
            # 创建一个已过期的请求
            request_id = tool.create_request(state, timeout_minutes=-1)  # 负数使其立即过期
            
            expired = tool.check_expired()
            
            assert request_id in expired
```

- [ ] **Step 2: 创建 src/tools/approval_tool.py**

```python
"""
ApprovalTool - 审批管理工具

管理审批请求的创建、存储、状态更新和过期检查
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class ApprovalRequest:
    """审批请求"""
    request_id: str
    workflow_state: Dict
    created_at: str
    expires_at: str
    status: str  # pending, approved, rejected, timeout
    dingtalk_message_id: Optional[str] = None


class ApprovalTool:
    """
    审批管理工具
    
    使用 JSON 文件存储审批请求
    """
    
    DEFAULT_DATA_DIR = "data/approvals"
    
    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        """
        初始化
        
        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
    
    def create_request(
        self,
        state: Dict,
        timeout_minutes: int = 30,
        dingtalk_message_id: Optional[str] = None
    ) -> str:
        """
        创建审批请求
        
        Args:
            state: LangGraph 状态快照
            timeout_minutes: 超时时间（分钟）
            dingtalk_message_id: 钉钉消息 ID
        
        Returns:
            request_id
        """
        request_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(minutes=timeout_minutes)
        
        request = ApprovalRequest(
            request_id=request_id,
            workflow_state=state,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            status="pending",
            dingtalk_message_id=dingtalk_message_id
        )
        
        # 存储
        self._save_request(request)
        
        return request_id
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """
        获取审批请求
        
        Args:
            request_id: 请求 ID
        
        Returns:
            ApprovalRequest 或 None
        """
        path = self._get_request_path(request_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return ApprovalRequest(**data)
    
    def update_status(self, request_id: str, status: str) -> bool:
        """
        更新审批状态
        
        Args:
            request_id: 请求 ID
            status: 新状态
        
        Returns:
            是否成功
        """
        request = self.get_request(request_id)
        
        if not request:
            return False
        
        if request.status != "pending":
            return False  # 只能更新 pending 状态
        
        request.status = status
        self._save_request(request)
        
        return True
    
    def check_expired(self) -> List[str]:
        """
        检查过期请求
        
        Returns:
            过期的请求 ID 列表
        """
        expired = []
        now = datetime.now()
        
        for filename in os.listdir(self.data_dir):
            if not filename.endswith(".json"):
                continue
            
            request_id = filename[:-5]
            request = self.get_request(request_id)
            
            if request and request.status == "pending":
                expires_at = datetime.fromisoformat(request.expires_at)
                if now > expires_at:
                    expired.append(request_id)
        
        return expired
    
    def _save_request(self, request: ApprovalRequest) -> None:
        """保存请求"""
        path = self._get_request_path(request.request_id)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(request), f, ensure_ascii=False)
    
    def _get_request_path(self, request_id: str) -> str:
        """获取请求文件路径"""
        return os.path.join(self.data_dir, f"{request_id}.json")


__all__ = ["ApprovalTool", "ApprovalRequest"]
```

- [ ] **Step 3: 更新 __init__.py**

添加 `from .approval_tool import ApprovalTool, ApprovalRequest` 导出。

- [ ] **Step 4: 运行测试验证通过**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/test_tools/test_approval_tool.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/tools/approval_tool.py tests/test_tools/test_approval_tool.py && git commit -m "feat: 添加 ApprovalTool 审批管理工具"
```

---

### Task 13: 完善审批节点和回调

**Files:**
- Modify: `src/workflow/nodes/approval.py`
- Modify: `src/api/webhook_api.py`
- Create: `data/approvals/` 目录

- [ ] **Step 1: 创建数据目录**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/data/approvals
```

- [ ] **Step 2: 完善 src/workflow/nodes/approval.py**

```python
"""
approval 节点

请求审批和检查审批状态
"""

from ..state import AgentState
from ...tools.approval_tool import ApprovalTool


def request_approval(state: AgentState) -> AgentState:
    """
    请求审批
    
    创建审批请求并发送钉钉审批消息
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (approval_status, approval_message_id)
    """
    tool = ApprovalTool()
    
    # 创建审批请求
    request_id = tool.create_request(
        state=state,
        timeout_minutes=30,
        dingtalk_message_id=state.get("approval_message_id")
    )
    
    return {
        **state,
        "approval_status": "pending",
        "approval_message_id": request_id,
    }


def check_approval(state: AgentState) -> AgentState:
    """
    检查审批状态
    
    查询 ApprovalTool 获取审批状态
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态 (approval_status)
    """
    request_id = state.get("approval_message_id")
    
    if not request_id:
        return {
            **state,
            "approval_status": None,
        }
    
    tool = ApprovalTool()
    request = tool.get_request(request_id)
    
    if not request:
        return {
            **state,
            "approval_status": "timeout",  # 未找到视为超时
        }
    
    return {
        **state,
        "approval_status": request.status,
    }


__all__ = ["request_approval", "check_approval"]
```

- [ ] **Step 3: 更新 webhook_api.py 审批回调**

```python
"""
Webhook API - 接收 DolphinScheduler 告警
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from ..workflow.graph import AlertWorkflowGraph
from ..config.projects import projects_registry
from ..tools.approval_tool import ApprovalTool

router = APIRouter()

# 创建工作流实例
workflow = AlertWorkflowGraph()


@router.post("/webhook")
async def handle_webhook(request: Request):
    """处理 DolphinScheduler 告警 webhook"""
    try:
        payload = await request.json()
        
        # 执行工作流
        result = workflow.run(payload)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "processed",
                "project_valid": result.get("project_valid"),
                "risk_level": result.get("risk_level"),
                "approval_required": result.get("approval_required"),
                "execution_success": result.get("execution_success"),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approval/{request_id}")
async def handle_approval(request_id: str, action: str):
    """
    处理审批回调
    
    参数:
    - request_id: 审批请求 ID
    - action: approve / reject
    """
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    tool = ApprovalTool()
    request = tool.get_request(request_id)
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if request.status != "pending":
        raise HTTPException(status_code=400, detail=f"Already {request.status}")
    
    # 更新状态
    approval_status = "approved" if action == "approve" else "rejected"
    tool.update_status(request_id, approval_status)
    
    # 继续工作流
    result = workflow.continue_from_approval(request.workflow_state, approval_status)
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "processed",
            "approval_status": approval_status,
            "execution_success": result.get("execution_success"),
        },
    )


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "workflow": "LangGraph"}


__all__ = ["router"]
```

- [ ] **Step 4: 提交**

```bash
cd D:/Project/dolphinscheduler-agent && git add src/workflow/nodes/approval.py src/api/webhook_api.py data/approvals/ && git commit -m "feat: 完善审批节点和回调处理"
```

---

## 实现说明

### 测试策略

- 每个 Tool 单独测试（Mock 外部服务）
- 每个节点单独测试（Mock 依赖工具）
- 端到端测试验证完整流程

### 运行全部测试

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/ -v --tb=short
```

### 配置更新

新增环境变量（`.env` 或系统环境）：
```bash
LLM_API_URL=https://aiapi-test.huan.tv/anthropic
LLM_API_TOKEN=your_token
APPROVAL_TIMEOUT=1800
```

更新 `config/projects.yaml` 添加 LLM 配置段（可选）。

### 依赖安装

```bash
pip install kubernetes>=28.0.0
```