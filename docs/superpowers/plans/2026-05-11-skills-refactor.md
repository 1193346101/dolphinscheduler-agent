# Skills 重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构现有 skills 模块为 anthropics/skills 规范格式，添加日志预处理、超时分析、安全检查等增强功能

**Architecture:** 参考 pdf skill 结构，每个 error-analyzer 为独立目录（SKILL.md + patterns.md + scripts/）。保留现有 Python 类作为运行时加载器，但核心逻辑移至 SKILL.md 定义的脚本。

**Tech Stack:** Python 3.x, Markdown, JSON, dsctl CLI, YARN API

---

## 文件结构

本次重构创建/修改的文件：

```
skills/                              # 新目录（anthropics/skills 格式）
├── common/
│   ├── preprocess_log.py           # 日志降噪（Task 1）
│   ├── extract_context.py          # IP/服务提取（Task 2）
│   ├── cluster_lookup.py           # 集群配置关联（Task 3）
│   └── safety_check.py             # 安全检查（Task 4）
│
├── spark-error-analyzer/
│   ├── SKILL.md                    # 核心提示词（Task 5）
│   ├── spark_patterns.md           # 错误模式表（Task 6）
│   └── scripts/
│       ├── match_error.py          # 模式匹配（Task 7）
│       ├── analyze_traceback.py    # 堆栈解析（Task 8）
│       └── build_fix.py            # 修复方案（Task 9）
│       └── calculate_resource.py   # 资源建议（Task 10）
│
├── shell-error-analyzer/
│   ├── SKILL.md                    # Task 11
│   ├── shell_patterns.md           # Task 12
│   └── scripts/
│       ├── match_error.py          # Task 13
│       └── analyze_traceback.py    # Task 14
│
├── python-error-analyzer/
│   ├── SKILL.md                    # Task 15
│   ├── python_patterns.md          # Task 16
│   └── scripts/
│       ├── match_error.py          # Task 17
│       └── analyze_traceback.py    # Task 18
│
├── datax-error-analyzer/
│   ├── SKILL.md                    # Task 19
│   ├── datax_patterns.md           # Task 20
│   └── scripts/
│       └── match_error.py          # Task 21
│
├── timeout-analyzer/
│   ├── SKILL.md                    # Task 22
│   └── scripts/
│       ├── analyze_timeout.py      # Task 23
│       └── check_cluster.py        # Task 24
│
└── registry.py                     # 统一注册表（Task 25）

config/
└── cluster_info.md                 # 集群配置（Task 26）

data/
├── metrics/                        # 每日指标（已存在）
├── knowledge_base/
│   └── projects/                   # 项目历史（Task 27）
└── changes/                        # 变更记录（Task 28）

scripts/
└── collect_metrics.py              # 每日采集（Task 29）

src/skills/                         # 修改现有模块
├── base.py                         # 保持不变
├── registry.py                     # 修改：加载 SKILL.md（Task 30）
├── spark_skill.py                  # 修改：调用脚本（Task 31）
├── shell_skill.py                  # 修改：移除拼写映射（Task 32）
├── python_skill.py                 # 修改：调用脚本（Task 33）
└── datax_skill.py                  # 修改：调用脚本（Task 34）

tests/skills/                       # 新增测试
├── test_preprocess_log.py          # Task 35
├── test_match_error.py             # Task 36
├── test_timeout_analyzer.py        # Task 37
└── test_safety_check.py            # Task 38
```

---

## Task 1: 日志降噪公共模块

**Files:**
- Create: `skills/common/preprocess_log.py`
- Test: `tests/skills/test_preprocess_log.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/skills/test_preprocess_log.py
import pytest
from skills.common.preprocess_log import preprocess_log, validate_extraction

def test_preprocess_log_extract_config_lines():
    """测试提取 Spark 配置行"""
    log = """
    spark.executor.memory 2g
    spark.driver.memory 1g
    hadoop.fs.defaultFS hdfs://localhost:9000
    ERROR: OutOfMemoryError
    """
    result = preprocess_log(log, "SPARK")
    assert len(result['config_lines']) == 3
    assert 'spark.executor.memory' in result['config_lines'][0]

def test_preprocess_log_extract_error_blocks():
    """测试提取完整错误块"""
    log = """
    ERROR: Java heap space
    at org.apache.spark.executor.Executor.run(Executor.scala:123)
    at java.lang.Thread.run(Thread.java:748)
    Caused by: java.lang.OutOfMemoryError
    """
    result = preprocess_log(log, "SPARK")
    assert len(result['error_blocks']) >= 1
    assert 'OutOfMemoryError' in result['error_blocks'][0]

def test_preprocess_log_extract_app_id():
    """测试提取 Application ID"""
    log = "application_1234567890_0001 running"
    result = preprocess_log(log, "SPARK")
    assert result['app_info']['app_id'] == 'application_1234567890_0001'

def test_validate_extraction():
    """验证提取完整性"""
    log = "ERROR: test\nFATAL: test2\nException: test3"
    result = {'error_blocks': ['ERROR: test', 'FATAL: test2', 'Exception: test3']}
    assert validate_extraction(log, result) == True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_preprocess_log.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# skills/common/preprocess_log.py
"""
日志降噪 - 智能提取关键信息

替代固定前200后300行，提取：
- config_lines: Spark/Hadoop 配置
- error_blocks: 完整错误堆栈
- data_metrics: 数据量指标
- app_info: Application ID 等
"""

import re
import json
from typing import Dict, List

def preprocess_log(log_content: str, task_type: str) -> Dict:
    """智能提取日志关键信息"""
    result = {
        'config_lines': [],
        'error_blocks': [],
        'resource_stats': [],
        'data_metrics': {},
        'app_info': {}
    }

    lines = log_content.split('\n')

    # 1. 提取配置行
    config_prefixes = ['spark.', 'hadoop.', 'yarn.', 'dfs.']
    for line in lines:
        stripped = line.strip()
        for prefix in config_prefixes:
            if prefix in stripped.lower():
                result['config_lines'].append(stripped)
                break

    # 2. 提取完整错误块（ERROR/FATAL/Exception + 后续堆栈）
    i = 0
    while i < len(lines):
        line = lines[i]
        error_keywords = ['ERROR', 'FATAL', 'Exception', 'Caused by', 'Traceback']
        if any(kw in line for kw in error_keywords):
            block = [line]
            j = i + 1
            # 继续提取堆栈行（空格/tab开头或包含 'at ')
            while j < len(lines):
                next_line = lines[j]
                if next_line.startswith(' ') or next_line.startswith('\t') or 'at ' in next_line or 'Caused by' in next_line:
                    block.append(next_line)
                    j += 1
                else:
                    break
            result['error_blocks'].append('\n'.join(block))
            i = j
        else:
            i += 1

    # 3. 提取 Application ID
    app_patterns = [
        r'application_\d+_\d+',
        r'app-\d+-\d+',
        r'application_\d+'
    ]
    for pattern in app_patterns:
        match = re.search(pattern, log_content)
        if match:
            result['app_info']['app_id'] = match.group(0)
            break

    # 4. 提取数据量指标（从 Spark Event Log JSON）
    if task_type == "SPARK":
        result['data_metrics'] = _extract_spark_metrics(log_content)

    return result

def _extract_spark_metrics(log_content: str) -> Dict:
    """从 Spark Event Log 提取数据量指标"""
    metrics = {
        'input_bytes': 0,
        'shuffle_read_bytes': 0,
        'shuffle_write_bytes': 0,
        'memory_spilled': 0
    }

    for line in log_content.split('\n'):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if event.get('Event') == 'SparkListenerTaskEnd':
                task_metrics = event.get('Task Metrics', {})
                input_m = task_metrics.get('Input Metrics', {})
                metrics['input_bytes'] += input_m.get('Bytes Read', 0)

                shuffle_read = task_metrics.get('Shuffle Read Metrics', {})
                metrics['shuffle_read_bytes'] += shuffle_read.get('Total Bytes Read', 0)

                shuffle_write = task_metrics.get('Shuffle Write Metrics', {})
                metrics['shuffle_write_bytes'] += shuffle_write.get('Bytes Written', 0)

                metrics['memory_spilled'] += task_metrics.get('Memory Bytes Spilled', 0)
        except json.JSONDecodeError:
            continue

    return metrics

def validate_extraction(original: str, extracted: Dict) -> bool:
    """验证提取完整性"""
    original_errors = len(re.findall(r'(ERROR|FATAL|Exception)', original))
    extracted_errors = len([b for b in extracted['error_blocks'] if re.search(r'(ERROR|FATAL|Exception)', b)])
    return original_errors == extracted_errors
```

- [ ] **Step 4: Create skills directory structure**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/skills/common
mkdir -p D:/Project/dolphinscheduler-agent/tests/skills
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_preprocess_log.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add skills/common/preprocess_log.py tests/skills/test_preprocess_log.py
git commit -m "feat(skills): add log preprocessing module for noise reduction"
```

---

## Task 2: IP/服务提取模块

**Files:**
- Create: `skills/common/extract_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/skills/test_extract_context.py
import pytest
from skills.common.extract_context import extract_targets

def test_extract_ip_port():
    """测试提取 IP 和端口"""
    log = "Connection refused: 192.168.1.100:3306"
    targets = extract_targets(log)
    assert len(targets) >= 1
    assert targets[0]['ip'] == '192.168.1.100'
    assert targets[0]['port'] == 3306

def test_extract_hostname():
    """测试提取主机名"""
    log = "Failed to connect to spark-history-server:18082"
    targets = extract_targets(log)
    assert len(targets) >= 1
    assert 'spark-history-server' in targets[0]['hostname']

def test_extract_hdfs_path():
    """测试提取 HDFS 路径"""
    log = "hdfs://nameservice1/user/data/input.csv not found"
    targets = extract_targets(log)
    assert len(targets) >= 1
    assert 'hdfs://nameservice1' in targets[0]['hdfs_path']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_extract_context.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# skills/common/extract_context.py
"""
提取日志中的上下文信息：IP、端口、主机名、HDFS路径
"""

import re
from typing import Dict, List

def extract_targets(log_content: str) -> List[Dict]:
    """提取日志中的目标信息"""
    targets = []

    # 1. 提取 IP:端口
    ip_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)'
    for match in re.finditer(ip_pattern, log_content):
        targets.append({
            'type': 'ip_port',
            'ip': match.group(1),
            'port': int(match.group(2))
        })

    # 2. 提取主机名:端口
    hostname_pattern = r'([a-zA-Z][a-zA-Z0-9\-]*[a-zA-Z0-9]):(\d+)'
    for match in re.finditer(hostname_pattern, log_content):
        targets.append({
            'type': 'hostname_port',
            'hostname': match.group(1),
            'port': int(match.group(2))
        })

    # 3. 提取 HDFS 路径
    hdfs_pattern = r'hdfs://([a-zA-Z0-9\-\.]+(/[a-zA-Z0-9\-\.\/]*)?)'
    for match in re.finditer(hdfs_pattern, log_content):
        targets.append({
            'type': 'hdfs',
            'hdfs_path': 'hdfs://' + match.group(1)
        })

    return targets
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_extract_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/common/extract_context.py tests/skills/test_extract_context.py
git commit -m "feat(skills): add context extraction module for IP/service lookup"
```

---

## Task 3: 集群配置关联模块

**Files:**
- Create: `skills/common/cluster_lookup.py`
- Create: `config/cluster_info.md` (template)

- [ ] **Step 1: Write the failing test**

```python
# tests/skills/test_cluster_lookup.py
import pytest
from skills.common.cluster_lookup import lookup_service, parse_hosts_table

def test_parse_hosts_table():
    """测试解析集群配置表"""
    cluster_file = "config/cluster_info.md"
    hosts = parse_hosts_table(cluster_file)
    assert isinstance(hosts, list)

def test_lookup_service_by_ip():
    """测试通过 IP 查找服务"""
    cluster_file = "config/cluster_info.md"
    result = lookup_service("192.168.1.100", 12345, cluster_file)
    # 如果配置中有该 IP，应返回服务名
    if result:
        assert 'service' in result or 'hostname' in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_cluster_lookup.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# skills/common/cluster_lookup.py
"""
集群配置关联 - 通过 IP/端口查找服务信息
"""

import re
from typing import Dict, List, Optional

def parse_hosts_table(cluster_file: str) -> List[Dict]:
    """解析 cluster_info.md 中的 hosts 表"""
    hosts = []
    try:
        with open(cluster_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 Markdown 表格: | IP | Hostname | Services |
        table_pattern = r'\| (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}) \| ([^|]+) \| ([^|]+) \|'
        for match in re.finditer(table_pattern, content):
            ip = match.group(1)
            hostname = match.group(2).strip()
            services_str = match.group(3).strip()

            # 解析服务列表: Service:Port, Service:Port
            services = []
            for svc in services_str.split(','):
                svc = svc.strip()
                svc_match = re.match(r'([^:]+):(\d+)', svc)
                if svc_match:
                    services.append({
                        'name': svc_match.group(1).strip(),
                        'port': int(svc_match.group(2))
                    })

            hosts.append({
                'ip': ip,
                'hostname': hostname,
                'services': services
            })
    except FileNotFoundError:
        pass

    return hosts

def lookup_service(ip: str, port: int, cluster_file: str) -> Optional[Dict]:
    """通过 IP 和端口查找服务"""
    hosts = parse_hosts_table(cluster_file)
    for host in hosts:
        if host['ip'] == ip:
            for service in host['services']:
                if service['port'] == port:
                    return {
                        'service': service['name'],
                        'hostname': host['hostname'],
                        'ip': ip,
                        'port': port
                    }
    return None
```

- [ ] **Step 4: Create cluster_info.md template**

```markdown
# config/cluster_info.md

## Cluster: default

### Hosts

| IP | Hostname | Services |
|----|----------|----------|
| 192.168.1.100 | dolphin-master-01 | DolphinScheduler:12345, YARN RM:8032 |
| 192.168.1.101 | spark-worker-01 | Spark History:18082, HDFS NN:9000 |

### Service Dependencies

| Service | Depends On | Impact If Down |
|---------|------------|----------------|
| Spark SQL | Hive Metastore | Cannot query tables |
| DataX MySQL | MySQL Server | Cannot sync data |

### Resource Limits

| Max Executor Mem | Max Driver Mem |
|------------------|----------------|
| 16g | 8g |
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_cluster_lookup.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add skills/common/cluster_lookup.py config/cluster_info.md tests/skills/test_cluster_lookup.py
git commit -m "feat(skills): add cluster configuration lookup module"
```

---

## Task 4: 安全检查模块

**Files:**
- Create: `skills/common/safety_check.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/skills/test_safety_check.py
import pytest
from skills.common.safety_check import check_cluster_safety, check_downstream_impact

def test_check_cluster_safety_safe():
    """测试安全状态"""
    # 模拟 YARN metrics
    metrics = {
        'usedMB': 50000,
        'totalMB': 100000,
        'availableMB': 50000,
        'appsPending': 3
    }
    result = check_cluster_safety(metrics)
    assert result['safe'] == True
    assert result['utilization'] == 0.5

def test_check_cluster_safety_high_utilization():
    """测试高利用率告警"""
    metrics = {
        'usedMB': 90000,
        'totalMB': 100000,
        'availableMB': 10000,
        'appsPending': 5
    }
    result = check_cluster_safety(metrics)
    assert result['safe'] == False
    assert any(i['type'] == 'high_utilization' for i in result['issues'])

def test_check_cluster_safety_queue_overload():
    """测试队列过载告警"""
    metrics = {
        'usedMB': 50000,
        'totalMB': 100000,
        'availableMB': 50000,
        'appsPending': 15
    }
    result = check_cluster_safety(metrics)
    assert result['safe'] == False
    assert any(i['type'] == 'queue_overload' for i in result['issues'])

def test_check_downstream_impact_safe():
    """测试下游影响安全"""
    downstream_count = 3
    result = check_downstream_impact(downstream_count)
    assert result['safe'] == True
    assert result['requires_approval'] == False

def test_check_downstream_impact_needs_approval():
    """测试下游影响需审批"""
    downstream_count = 8
    result = check_downstream_impact(downstream_count)
    assert result['safe'] == False
    assert result['requires_approval'] == True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_safety_check.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# skills/common/safety_check.py
"""
安全检查模块 - 执行操作前的安全验证

检查项：
- 集群利用率 < 80%
- 排队任务数 < 10
- 下游依赖数 < 5
"""

from typing import Dict, List

def check_cluster_safety(yarn_metrics: Dict) -> Dict:
    """检查集群资源安全性"""
    used_mb = yarn_metrics.get('usedMB', 0)
    total_mb = yarn_metrics.get('totalMB', 1)
    available_mb = yarn_metrics.get('availableMB', 0)
    pending_apps = yarn_metrics.get('appsPending', 0)

    utilization = used_mb / total_mb if total_mb > 0 else 0

    issues = []

    if utilization > 0.8:
        issues.append({
            'type': 'high_utilization',
            'value': utilization,
            'threshold': 0.8,
            'message': '集群利用率超过 80%，禁止增加资源'
        })

    if pending_apps > 10:
        issues.append({
            'type': 'queue_overload',
            'value': pending_apps,
            'threshold': 10,
            'message': '排队任务超过 10 个，建议等待队列释放'
        })

    return {
        'safe': len(issues) == 0,
        'utilization': utilization,
        'pending_apps': pending_apps,
        'available_mb': available_mb,
        'issues': issues
    }

def check_downstream_impact(downstream_count: int) -> Dict:
    """检查下游影响"""
    return {
        'safe': downstream_count < 5,
        'downstream_count': downstream_count,
        'requires_approval': downstream_count >= 5,
        'message': f'下游依赖 {downstream_count} 个工作流' + ('，需审批' if downstream_count >= 5 else '')
    }

def validate_operation_prerequisites(safety_result: Dict, downstream_result: Dict) -> Dict:
    """验证操作前置条件"""
    checklist = {
        'cluster_utilization_ok': safety_result['utilization'] < 0.8,
        'queue_ok': safety_result['pending_apps'] < 10,
        'downstream_ok': downstream_result['downstream_count'] < 5,
        'all_passed': False
    }
    checklist['all_passed'] = all([
        checklist['cluster_utilization_ok'],
        checklist['queue_ok'],
        checklist['downstream_ok']
    ])
    return checklist
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_safety_check.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/common/safety_check.py tests/skills/test_safety_check.py
git commit -m "feat(skills): add safety check module for operation validation"
```

---

## Task 5: Spark SKILL.md 核心提示词

**Files:**
- Create: `skills/spark-error-analyzer/SKILL.md`

- [ ] **Step 1: Create SKILL.md**

```markdown
# skills/spark-error-analyzer/SKILL.md
---
name: spark-error-analyzer
description: 分析 Spark/Spark Streaming 任务执行错误并给出修复建议。当 SPARK 或 SPARK_STREAMING 任务失败时触发，适用于 OOM、ClassNotFoundException、ShuffleError、ConnectionError、ContainerKilled 等错误。不要用于 SHELL、PYTHON 等其他任务类型。
---

# Spark 错误分析器

## 概述

通过日志预处理 + 模式匹配 + 上下文增强分析 Spark 任务错误。

## 处理流程

### 步骤 1：日志预处理（必须首先执行）

先调用 `skills/common/preprocess_log.py` 提取关键信息：

```bash
python skills/common/preprocess_log.py --log "<日志内容>" --task-type SPARK
```

输出内容：
- `config_lines`: Spark/Hadoop 配置参数
- `error_blocks`: 完整的错误堆栈信息
- `data_metrics`: 数据量指标（输入、Shuffle、Spill）
- `app_info`: Application ID

**不要直接使用原始日志**，必须先预处理。

---

### 步骤 2：匹配错误模式

使用预处理后的 error_blocks 调用匹配脚本：

```bash
python scripts/match_error.py --patterns spark_patterns.md --log "<error_blocks>"
```

输出类别：
- `AUTO_FIXABLE`: 可自动修复（OOM → 增加内存）
- `KNOWN_NEEDS_LLM`: 已知错误类型，需深入分析
- `UNKNOWN`: 未匹配，需完整 LLM 分析

---

### 步骤 3：增强上下文（连接/服务错误时）

如果错误涉及 IP/端口/域名，调用 `skills/common/extract_context.py`：

```bash
python skills/common/extract_context.py --log "<error_blocks>" --cluster config/cluster_info.md
```

输出：`targets` 数组，包含服务名称、主机名、集群信息。

---

### 步骤 4：构建修复方案（AUTO_FIXABLE 时）

对于可自动修复的错误，调用 `scripts/build_fix.py`：

```bash
python scripts/build_fix.py --error-type "<错误类型>" --current-config "<config_lines>" --historical "data/knowledge_base/projects/{workflow_code}/spark_errors.md"
```

**资源建议规则：**
- 最高翻倍：当前配置 × 2
- 检查集群上限：不能超过 cluster_info.md 中的 max_executor_mem
- 优先历史成功配置

---

### 步骤 5：分析数据量指标（OOM/性能问题时）

分析预处理输出的 `data_metrics`：

关键指标：
- `memory_spilled > 0`：内存不足，必须增加内存
- `shuffle_read_bytes > input_bytes × 10`：可能数据倾斜
- `shuffle_fetch_wait_time` 较大：网络瓶颈

---

### 步骤 6：匹配知识库

优先搜索项目历史：

```bash
grep "<错误类型>" data/knowledge_base/projects/{workflow_code}/spark_errors.md
```

---

### 步骤 7：安全检查（执行操作前必须）

调用 `skills/common/safety_check.py` 检查：
- 集群利用率 < 80%
- 排队任务数 < 10
- 下游依赖数 < 5

---

## 输出格式

始终返回 JSON：

```json
{
  "error_type": "oom_executor",
  "category": "AUTO_FIXABLE",
  "error_message": "OutOfMemoryError: Java heap space...",
  "targets": [{"ip": "192.168.1.101", "service": "Spark History Server"}],
  "data_metrics": {"input_bytes": 1073741824, "memory_spilled": 536870912},
  "fix": {
    "config_changes": {"spark.executor.memory": "4g"},
    "reason": "当前 2g × 2 = 4g",
    "confidence": 0.95
  },
  "llm_hint": "Executor OOM，内存 Spill 512MB，建议增加到 4g"
}
```

---

## 快速参考表

| 错误类型 | 匹配模式 | 类别 | 修复建议 |
|---------|---------|------|---------|
| oom_executor | `OutOfMemoryError: Java heap space` | AUTO_FIXABLE | executor.memory × 2 |
| oom_driver | `OutOfMemoryError: unable to create` | AUTO_FIXABLE | driver.memory × 2 |
| container_killed_memory | `Container killed due to memory` | AUTO_FIXABLE | executor.memory × 2 |
| class_not_found | `ClassNotFoundException` | KNOWN_NEEDS_LLM | 检查 jar 包/依赖 |
| shuffle_failed | `FetchFailedException` | KNOWN_NEEDS_LLM | 检查 Shuffle Service |
| connection_refused | `Connection refused` | KNOWN_NEEDS_LLM | 检查服务状态 |

---

## 重要规则

1. 必须先预处理日志 - 原始日志噪音大
2. 资源建议最高翻倍 - 当前 2g 时建议 4g
3. 检查集群上限 - 不能超过集群 max_executor_mem
4. 历史配置优先 - 项目历史有成功记录时直接使用
5. Spill 表明内存不足 - memory_spilled > 0 时必须增加内存
6. **执行操作前必须安全检查** - 确保不影响集群和调度
```

- [ ] **Step 2: Create directory**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/skills/spark-error-analyzer/scripts
```

- [ ] **Step 3: Commit**

```bash
git add skills/spark-error-analyzer/SKILL.md
git commit -m "feat(skills): add spark-error-analyzer SKILL.md"
```

---

## Task 6: Spark 错误模式表

**Files:**
- Create: `skills/spark-error-analyzer/spark_patterns.md`

- [ ] **Step 1: Write patterns.md**

```markdown
# skills/spark-error-analyzer/spark_patterns.md

# Spark 错误模式表

## AUTO_FIXABLE（可自动修复）

| error_type | pattern | fix_action |
|------------|---------|------------|
| oom_executor | `OutOfMemoryError: Java heap space` | executor.memory × 2 |
| oom_driver | `OutOfMemoryError: unable to create new native thread` | driver.memory × 2 |
| oom_driver_direct | `OutOfMemoryError: Container memory exceeded` | driver.maxResultSize × 2 |
| container_killed_memory | `Container killed due to memory` | executor.memory × 2 |
| gc_overhead | `GC overhead limit exceeded` | executor.memory × 2 |
| broadcast_timeout | `BroadcastHashJoin.*timeout` | autoBroadcastJoinThreshold=-1 |
| shuffle_timeout | `shuffle.*timeout` | shuffle.io.timeout=120s |
| network_timeout | `spark.network.timeout` | network.timeout=300s |

## KNOWN_NEEDS_LLM（需 LLM 分析）

| error_type | pattern | llm_hint |
|------------|---------|----------|
| class_not_found | `ClassNotFoundException` | 检查依赖包是否已上传 |
| no_class_def | `NoClassDefFoundError` | 检查类定义和依赖加载 |
| jar_not_found | `jar not found` | 检查 Jar 包路径 |
| main_class_not_found | `Main class not found` | 检查 Main Class 名称 |
| shuffle_failed | `FetchFailedException` | 检查 Shuffle Service 状态 |
| shuffle_connection | `shuffle.*connection failed` | 检查 Shuffle Service |
| connection_refused | `Connection refused` | 检查目标服务是否运行 |
| connection_timeout | `Connection timed out` | 检查网络状态 |
| hdfs_not_found | `does not exist|FileNotFound` | 检查输入路径 |
| hdfs_permission | `Permission denied.*hdfs` | 检查文件权限 |
| schema_mismatch | `Schema mismatch|cannot resolve` | 检查数据结构 |
| container_killed | `Container killed by YARN` | 分析资源使用 |
| executor_lost | `Executor lost` | 分析 Executor 状态 |
| job_aborted | `SparkException: Job aborted` | 分析中止原因 |
| stage_failed | `Stage \\d+ failed` | 分析失败 Stage |
| sql_syntax | `SQL syntax error` | 分析 SQL 语法 |
| sql_column_not_found | `Column.*not found` | 检查列名 |
| sql_table_not_found | `Table.*not found` | 检查表名 |
```

- [ ] **Step 2: Commit**

```bash
git add skills/spark-error-analyzer/spark_patterns.md
git commit -m "feat(skills): add spark error patterns table"
```

---

## Task 7: Spark 模式匹配脚本

**Files:**
- Create: `skills/spark-error-analyzer/scripts/match_error.py`
- Test: `tests/skills/test_match_error.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/skills/test_match_error.py
import pytest
import sys
sys.path.insert(0, 'D:/Project/dolphinscheduler-agent')

from skills.spark_error_analyzer.scripts.match_error import match_error, load_patterns

def test_load_patterns():
    """测试加载模式表"""
    patterns = load_patterns('skills/spark-error-analyzer/spark_patterns.md')
    assert len(patterns) > 0
    assert 'oom_executor' in patterns

def test_match_oom_error():
    """测试匹配 OOM 错误"""
    log = "java.lang.OutOfMemoryError: Java heap space\nat Executor.run"
    result = match_error(log, 'skills/spark-error-analyzer/spark_patterns.md')
    assert result['error_type'] == 'oom_executor'
    assert result['category'] == 'AUTO_FIXABLE'

def test_match_class_not_found():
    """测试匹配 ClassNotFoundException"""
    log = "java.lang.ClassNotFoundException: com.example.MyClass"
    result = match_error(log, 'skills/spark-error-analyzer/spark_patterns.md')
    assert result['error_type'] == 'class_not_found'
    assert result['category'] == 'KNOWN_NEEDS_LLM'

def test_match_unknown():
    """测试未匹配的错误"""
    log = "Some unknown error message"
    result = match_error(log, 'skills/spark-error-analyzer/spark_patterns.md')
    assert result['error_type'] == 'unknown'
    assert result['category'] == 'UNKNOWN'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_match_error.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# skills/spark-error-analyzer/scripts/match_error.py
"""
Spark 错误模式匹配脚本

读取 spark_patterns.md，匹配日志中的错误模式
输出：error_type, category, matched_pattern
"""

import re
import json
from typing import Dict, List, Optional
from pathlib import Path

def load_patterns(patterns_file: str) -> Dict:
    """加载模式表（从 Markdown 表格）"""
    patterns = {}
    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 Markdown 表格行
        # 格式: | error_type | pattern | fix_action/llm_hint |
        for line in content.split('\n'):
            if line.startswith('|') and not line.startswith('| error_type') and not line.startswith('|--'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    error_type = parts[1]
                    pattern = parts[2]
                    extra = parts[3]

                    # 判断类别：AUTO_FIXABLE 表中的是 AUTO_FIXABLE
                    category = 'KNOWN_NEEDS_LLM'
                    if 'AUTO_FIXABLE' in content[:content.find(line)]:
                        category = 'AUTO_FIXABLE'

                    patterns[error_type] = {
                        'pattern': pattern,
                        'category': category,
                        'extra': extra
                    }
    except FileNotFoundError:
        pass

    return patterns

def match_error(log_content: str, patterns_file: str) -> Dict:
    """匹配错误模式"""
    patterns = load_patterns(patterns_file)

    for error_type, info in patterns.items():
        pattern = info['pattern']
        try:
            if re.search(pattern, log_content, re.IGNORECASE | re.DOTALL):
                return {
                    'error_type': error_type,
                    'category': info['category'],
                    'matched_pattern': pattern,
                    'extra': info['extra'],
                    'error_message': _extract_error_context(log_content, pattern)
                }
        except re.error:
            continue

    # 未匹配
    return {
        'error_type': 'unknown',
        'category': 'UNKNOWN',
        'matched_pattern': None,
        'error_message': log_content[:500]
    }

def _extract_error_context(log_content: str, pattern: str) -> str:
    """提取错误上下文"""
    match = re.search(pattern, log_content, re.IGNORECASE | re.DOTALL)
    if match:
        start = max(0, match.start() - 200)
        end = min(len(log_content), match.end() + 300)
        return log_content[start:end]
    return log_content[:500]

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--patterns', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()

    result = match_error(args.log, args.patterns)
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/test_match_error.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/spark-error-analyzer/scripts/match_error.py tests/skills/test_match_error.py
git commit -m "feat(skills): add spark error pattern matching script"
```

---

## Task 8: Spark 堆栈解析脚本

**Files:**
- Create: `skills/spark-error-analyzer/scripts/analyze_traceback.py`

- [ ] **Step 1: Write implementation**

```python
# skills/spark-error-analyzer/scripts/analyze_traceback.py
"""
Spark 异常堆栈深度解析

提取：
- 最外层异常类型和消息
- Caused by（根因异常）
- 调用链
"""

import re
import json
from typing import Dict, List, Optional

def parse_spark_exception(log: str) -> Dict:
    """解析 Spark 异常"""
    result = {
        'error_type': None,
        'error_message': None,
        'root_cause': None,
        'call_chain': []
    }

    # 1. 提取最外层异常
    outer_pattern = r'org\.apache\.spark\.(\w+Exception|Error): (.+)'
    outer_match = re.search(outer_pattern, log)
    if outer_match:
        result['error_type'] = outer_match.group(1)
        result['error_message'] = outer_match.group(2)

    # 2. 提取 Caused by（根因）
    caused_pattern = r'Caused by: ([\w.]+(?:Exception|Error)): (.+)'
    caused_match = re.search(caused_pattern, log)
    if caused_match:
        result['root_cause'] = {
            'type': caused_match.group(1),
            'message': caused_match.group(2)
        }

    # 3. 提取调用链（at org.apache.spark...）
    call_pattern = r'at ([\w.]+)\.(\w+)\(([^\)]+):(\d+)\)'
    for match in re.finditer(call_pattern, log):
        result['call_chain'].append({
            'class': match.group(1),
            'method': match.group(2),
            'file': match.group(3),
            'line': int(match.group(4))
        })

    return result

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True)
    args = parser.parse_args()

    result = parse_spark_exception(args.log)
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 2: Commit**

```bash
git add skills/spark-error-analyzer/scripts/analyze_traceback.py
git commit -m "feat(skills): add spark exception traceback parser"
```

---

## Task 9: Spark 修复方案构建脚本

**Files:**
- Create: `skills/spark-error-analyzer/scripts/build_fix.py`

- [ ] **Step 1: Write implementation**

```python
# skills/spark-error-analyzer/scripts/build_fix.py
"""
构建 Spark 修复方案

规则：
1. 优先历史成功配置
2. 默认翻倍（最高 2 倍）
3. 检查集群上限
"""

import re
import json
from typing import Dict, Optional

def parse_memory(mem_str: str) -> int:
    """解析内存字符串为 MB"""
    if not mem_str:
        return 1024  # 默认 1g

    mem_str = mem_str.lower().strip()
    match = re.match(r'(\d+)(g|m|k)?', mem_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2) or 'm'
        if unit == 'g':
            return value * 1024
        elif unit == 'k':
            return value // 1024
        return value
    return 1024

def format_memory(mb: int) -> str:
    """格式化 MB 为内存字符串"""
    if mb >= 1024:
        return f"{mb // 1024}g"
    return f"{mb}m"

def build_fix(
    error_type: str,
    current_config: Dict,
    cluster_limit: Dict,
    historical_file: Optional[str] = None
) -> Dict:
    """构建修复方案"""
    # 1. 检查历史成功配置
    if historical_file:
        historical_fix = _find_historical_fix(error_type, historical_file)
        if historical_fix:
            return {
                'config_changes': historical_fix,
                'reason': '历史验证',
                'confidence': 0.95,
                'source': 'historical'
            }

    # 2. 默认修复方案
    default_fixes = {
        'oom_executor': {
            'spark.executor.memory': lambda c: format_memory(parse_memory(c.get('spark.executor.memory', '2g')) * 2),
            'spark.executor.memoryOverhead': lambda c: format_memory(parse_memory(c.get('spark.executor.memoryOverhead', '512m')) * 2),
        },
        'oom_driver': {
            'spark.driver.memory': lambda c: format_memory(parse_memory(c.get('spark.driver.memory', '1g')) * 2),
            'spark.driver.maxResultSize': lambda c: format_memory(parse_memory(c.get('spark.driver.maxResultSize', '1g')) * 2),
        },
        'container_killed_memory': {
            'spark.executor.memory': lambda c: format_memory(parse_memory(c.get('spark.executor.memory', '2g')) * 2),
            'spark.executor.memoryOverhead': lambda c: format_memory(parse_memory(c.get('spark.executor.memoryOverhead', '512m')) * 2),
        },
        'gc_overhead': {
            'spark.executor.memory': lambda c: format_memory(parse_memory(c.get('spark.executor.memory', '2g')) * 2),
            'spark.executor.memoryOverhead': lambda c: format_memory(parse_memory(c.get('spark.executor.memoryOverhead', '512m')) * 2),
        },
        'broadcast_timeout': {
            'spark.sql.autoBroadcastJoinThreshold': lambda c: '-1',
        },
        'shuffle_timeout': {
            'spark.shuffle.io.timeout': lambda c: '120s',
        },
        'network_timeout': {
            'spark.network.timeout': lambda c: '300s',
        },
    }

    if error_type not in default_fixes:
        return {'config_changes': {}, 'reason': '无自动修复方案', 'confidence': 0.3}

    # 3. 计算新配置
    config_changes = {}
    max_executor_mem = parse_memory(cluster_limit.get('max_executor_mem', '16g'))
    max_driver_mem = parse_memory(cluster_limit.get('max_driver_mem', '8g'))

    for key, calc_fn in default_fixes[error_type].items():
        new_value = calc_fn(current_config)
        new_mem = parse_memory(new_value)

        # 检查上限
        if 'executor' in key and new_mem > max_executor_mem:
            new_value = format_memory(max_executor_mem)
        elif 'driver' in key and new_mem > max_driver_mem:
            new_value = format_memory(max_driver_mem)

        config_changes[key] = new_value

    return {
        'config_changes': config_changes,
        'reason': '当前配置翻倍',
        'confidence': 0.85,
        'source': 'default'
    }

def _find_historical_fix(error_type: str, historical_file: str) -> Optional[Dict]:
    """从历史记录中查找成功配置"""
    try:
        with open(historical_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析历史表格: | 错误类型 | ... | 修复配置 | 结果 |
        for line in content.split('\n'):
            if line.startswith('|') and error_type in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 5 and 'SUCCESS' in parts[-1]:
                    # 提取修复配置（JSON 格式）
                    fix_str = parts[4] if len(parts) > 4 else ''
                    if fix_str:
                        try:
                            return json.loads(fix_str)
                        except json.JSONDecodeError:
                            pass
    except FileNotFoundError:
        pass
    return None

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--error-type', required=True)
    parser.add_argument('--current-config', required=True)
    parser.add_argument('--cluster-limit', default='{}')
    parser.add_argument('--historical', default=None)
    args = parser.parse_args()

    current_config = json.loads(args.current_config)
    cluster_limit = json.loads(args.cluster_limit)

    result = build_fix(args.error_type, current_config, cluster_limit, args.historical)
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 2: Commit**

```bash
git add skills/spark-error-analyzer/scripts/build_fix.py
git commit -m "feat(skills): add spark fix builder with resource limits"
```

---

## Task 10: Spark 资源建议计算脚本

**Files:**
- Create: `skills/spark-error-analyzer/scripts/calculate_resource.py`

- [ ] **Step 1: Write implementation**

```python
# skills/spark-error-analyzer/scripts/calculate_resource.py
"""
资源建议计算

规则：
1. 最高翻倍
2. 检查集群上限
3. 优先历史成功配置
"""

import json
from typing import Dict

def calculate_resource_suggestion(
    error_type: str,
    data_metrics: Dict,
    current_config: Dict,
    cluster_limit: Dict
) -> Dict:
    """计算资源建议"""
    from build_fix import parse_memory, format_memory

    current_mem = parse_memory(current_config.get('spark.executor.memory', '1g'))
    max_limit = parse_memory(cluster_limit.get('max_executor_mem', '16g'))

    # 1. 根据 data_metrics 判断
    memory_spilled = data_metrics.get('memory_spilled', 0)

    suggestion = {}

    # Spill 表明内存不足
    if memory_spilled > 0:
        spill_mb = memory_spilled // (1024 * 1024)
        suggested_mem = current_mem + spill_mb

        # 上限检查
        if suggested_mem > max_limit:
            suggested_mem = max_limit
            suggestion['warning'] = '已达集群上限'

        suggestion['suggested_memory'] = format_memory(suggested_mem)
        suggestion['reason'] = f'内存 Spill {spill_mb}MB，建议增加'
        suggestion['spill_bytes'] = memory_spilled

    # 2. 默认翻倍
    else:
        suggested_mem = current_mem * 2
        if suggested_mem > max_limit:
            suggested_mem = max_limit
            suggestion['warning'] = '已达集群上限'

        suggestion['suggested_memory'] = format_memory(suggested_mem)
        suggestion['reason'] = '当前配置翻倍'

    suggestion['current_memory'] = format_memory(current_mem)
    suggestion['max_limit'] = format_memory(max_limit)

    return suggestion

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--error-type', required=True)
    parser.add_argument('--data-metrics', required=True)
    parser.add_argument('--current-config', required=True)
    parser.add_argument('--cluster-limit', default='{}')
    args = parser.parse_args()

    result = calculate_resource_suggestion(
        args.error_type,
        json.loads(args.data_metrics),
        json.loads(args.current_config),
        json.loads(args.cluster_limit)
    )
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 2: Commit**

```bash
git add skills/spark-error-analyzer/scripts/calculate_resource.py
git commit -m "feat(skills): add spark resource suggestion calculator"
```

---

## Task 11: Shell SKILL.md 核心提示词

**Files:**
- Create: `skills/shell-error-analyzer/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
# skills/shell-error-analyzer/SKILL.md
---
name: shell-error-analyzer
description: 分析 SHELL 任务执行错误并给出修复建议。当 SHELL 任务失败时触发，适用于语法错误、权限不足、文件不存在、连接被拒绝等。不要用于 SPARK、PYTHON 等其他任务类型。
---

# Shell 错误分析器

## 概述

通过日志预处理 + 模式匹配分析 Shell 脚本错误。

## 处理流程

### 步骤 1：日志预处理

```bash
python skills/common/preprocess_log.py --log "<日志内容>" --task-type SHELL
```

### 步骤 2：匹配错误模式

```bash
python scripts/match_error.py --patterns shell_patterns.md --log "<error_blocks>"
```

### 步骤 3：增强上下文（连接/文件错误时）

```bash
python skills/common/extract_context.py --log "<error_blocks>" --cluster config/cluster_info.md
```

---

## 快速参考表

| 错误类型 | 匹配模式 | 分析提示 |
|---------|---------|---------|
| syntax_error | `syntax error` | Shell 语法错误，分析具体位置 |
| unexpected_eof | `unexpected EOF` | Shell 文件意外结束，引号不闭合 |
| permission_denied | `Permission denied` | Shell 权限不足，检查文件权限 |
| no_such_file | `No such file or directory` | Shell 文件不存在，检查路径 |
| connection_refused | `Connection refused` | Shell 连接被拒绝，检查目标服务 |
| connection_timeout | `Connection timed out` | Shell 连接超时，检查网络 |

---

## 重要规则

1. 必须预处理日志
2. 增强服务上下文 - 连接错误时识别具体服务
3. 验证文件路径 - 文件错误时确认路径是否存在
4. 大多数错误需 LLM - Shell 很少可自动修复
```

- [ ] **Step 2: Create directory**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/skills/shell-error-analyzer/scripts
```

- [ ] **Step 3: Commit**

```bash
git add skills/shell-error-analyzer/SKILL.md
git commit -m "feat(skills): add shell-error-analyzer SKILL.md"
```

---

## Task 12: Shell 错误模式表

**Files:**
- Create: `skills/shell-error-analyzer/shell_patterns.md`

- [ ] **Step 1: Write patterns.md**

```markdown
# skills/shell-error-analyzer/shell_patterns.md

# Shell 错误模式表

## KNOWN_NEEDS_LLM（需 LLM 分析）

| error_type | pattern | llm_hint |
|------------|---------|----------|
| syntax_error | `syntax error` | Shell 语法错误，分析具体位置和原因 |
| unexpected_eof | `unexpected EOF` | Shell 文件意外结束，通常是引号不闭合 |
| unexpected_eof_quote | `unexpected EOF while looking for matching` | Shell 引号或括号不闭合 |
| unexpected_token | `unexpected token` | Shell 出现意外符号 |
| variable_unset | `parameter null or not set` | Shell 变量为空或未定义 |
| bad_substitution | `bad substitution` | Shell 变量替换语法错误 |
| no_such_file | `No such file or directory` | Shell 文件不存在，检查路径 |
| permission_denied | `Permission denied` | Shell 权限不足 |
| connection_refused | `Connection refused` | Shell 网络连接被拒绝 |
| connection_timeout | `Connection timed out` | Shell 网络连接超时 |
| host_unreachable | `Host unreachable` | Shell 主机不可达 |
| dns_error | `unknown host` | Shell DNS 解析失败 |
| disk_full | `no space left` | Shell 磁盘空间不足 |
| memory_error | `cannot allocate` | Shell 内存分配失败 |
| broken_pipe | `Broken pipe` | Shell 管道断开 |
| segfault | `Segmentation fault` | Shell 程序段错误 |
| killed | `Killed` | Shell 进程被终止 |
```

- [ ] **Step 2: Commit**

```bash
git add skills/shell-error-analyzer/shell_patterns.md
git commit -m "feat(skills): add shell error patterns table"
```

---

## Task 13: Shell 模式匹配脚本

**Files:**
- Create: `skills/shell-error-analyzer/scripts/match_error.py`

- [ ] **Step 1: Write implementation**

```python
# skills/shell-error-analyzer/scripts/match_error.py
"""
Shell 错误模式匹配脚本
"""

import re
import json
from typing import Dict

def load_patterns(patterns_file: str) -> Dict:
    """加载模式表"""
    patterns = {}
    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            content = f.read()

        for line in content.split('\n'):
            if line.startswith('|') and not line.startswith('| error_type') and not line.startswith('|--'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3:
                    error_type = parts[1]
                    pattern = parts[2]
                    llm_hint = parts[3] if len(parts) > 3 else ''
                    patterns[error_type] = {
                        'pattern': pattern,
                        'category': 'KNOWN_NEEDS_LLM',
                        'llm_hint': llm_hint
                    }
    except FileNotFoundError:
        pass

    return patterns

def match_error(log_content: str, patterns_file: str) -> Dict:
    """匹配错误模式"""
    patterns = load_patterns(patterns_file)

    for error_type, info in patterns.items():
        pattern = info['pattern']
        try:
            if re.search(pattern, log_content, re.IGNORECASE):
                return {
                    'error_type': error_type,
                    'category': 'KNOWN_NEEDS_LLM',
                    'matched_pattern': pattern,
                    'llm_hint': info['llm_hint'],
                    'error_message': log_content[:500]
                }
        except re.error:
            continue

    return {
        'error_type': 'unknown',
        'category': 'UNKNOWN',
        'error_message': log_content[:500]
    }

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--patterns', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()

    result = match_error(args.log, args.patterns)
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 2: Commit**

```bash
git add skills/shell-error-analyzer/scripts/match_error.py
git commit -m "feat(skills): add shell error pattern matching script"
```

---

## Task 14: Shell 堆栈解析脚本

**Files:**
- Create: `skills/shell-error-analyzer/scripts/analyze_traceback.py`

- [ ] **Step 1: Write implementation**

```python
# skills/shell-error-analyzer/scripts/analyze_traceback.py
"""
Shell 错误位置解析

提取：
- 错误行号
- 错误位置（文件:行）
"""

import re
import json
from typing import Dict, Optional

def parse_shell_error(log: str) -> Dict:
    """解析 Shell 错误位置"""
    result = {
        'error_type': None,
        'line_number': None,
        'file': None,
        'error_message': None
    }

    # 提取行号
    line_pattern = r'line (\d+):'
    line_match = re.search(line_pattern, log)
    if line_match:
        result['line_number'] = int(line_match.group(1))

    # 提取错误类型
    error_types = ['syntax error', 'unexpected EOF', 'Permission denied', 'command not found']
    for et in error_types:
        if et.lower() in log.lower():
            result['error_type'] = et
            break

    # 提取错误消息
    result['error_message'] = log[:200]

    return result

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True)
    args = parser.parse_args()

    result = parse_shell_error(args.log)
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 2: Commit**

```bash
git add skills/shell-error-analyzer/scripts/analyze_traceback.py
git commit -m "feat(skills): add shell error location parser"
```

---

## Task 15-18: Python 错误分析器

**Files:**
- Create: `skills/python-error-analyzer/SKILL.md`
- Create: `skills/python-error-analyzer/python_patterns.md`
- Create: `skills/python-error-analyzer/scripts/match_error.py`
- Create: `skills/python-error-analyzer/scripts/analyze_traceback.py`

- [ ] **Step 1: Create directory**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/skills/python-error-analyzer/scripts
```

- [ ] **Step 2: Write SKILL.md**

```markdown
# skills/python-error-analyzer/SKILL.md
---
name: python-error-analyzer
description: 分析 PYTHON 任务执行错误并给出修复建议。当 PYTHON 任务失败时触发，适用于语法错误、模块导入失败、运行时异常等。不要用于 SPARK、SHELL 等其他任务类型。
---

# Python 错误分析器

## 概述

通过日志预处理 + 堆栈深度解析分析 Python 任务错误。

## 处理流程

### 步骤 1：日志预处理

```bash
python skills/common/preprocess_log.py --log "<日志内容>" --task-type PYTHON
```

### 步骤 2：堆栈深度解析

```bash
python scripts/analyze_traceback.py --log "<error_blocks>" --type python
```

输出：
- `error_type`: 异常类型
- `call_chain`: 调用链
- `root_cause`: 根因位置

### 步骤 3：匹配错误模式

```bash
python scripts/match_error.py --patterns python_patterns.md --log "<error_blocks>"
```

---

## 快速参考表

| 错误类型 | 匹配模式 | 分析提示 |
|---------|---------|---------|
| import_error | `ImportError: No module named` | 检查依赖是否安装 |
| module_not_found | `ModuleNotFoundError` | Python 3.6+，检查依赖 |
| syntax_error | `SyntaxError: invalid syntax` | 分析行号，检查语法 |
| type_error | `TypeError` | 类型不匹配 |
| value_error | `ValueError` | 值无效 |
| key_error | `KeyError` | 键不存在 |
| connection_error | `ConnectionError` | 网络问题 |
```

- [ ] **Step 3: Write patterns.md**

```markdown
# skills/python-error-analyzer/python_patterns.md

# Python 错误模式表

## KNOWN_NEEDS_LLM

| error_type | pattern | llm_hint |
|------------|---------|----------|
| import_error | `ImportError` | 检查依赖是否安装 |
| module_not_found | `ModuleNotFoundError` | Python 3.6+，检查依赖 |
| syntax_error | `SyntaxError` | 分析行号，检查语法 |
| indentation_error | `IndentationError` | 检查缩进一致性 |
| type_error | `TypeError` | 类型不匹配 |
| value_error | `ValueError` | 值无效 |
| key_error | `KeyError` | 键不存在 |
| attribute_error | `AttributeError` | 属性不存在 |
| connection_error | `ConnectionError` | 网络问题 |
| timeout_error | `TimeoutError` | 操作超时 |
```

- [ ] **Step 4: Write match_error.py**

```python
# skills/python-error-analyzer/scripts/match_error.py
"""Python 错误模式匹配"""

import re
import json
from typing import Dict

def load_patterns(patterns_file: str) -> Dict:
    patterns = {}
    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            for line in f.read().split('\n'):
                if line.startswith('|') and len(line.split('|')) >= 4:
                    parts = [p.strip() for p in line.split('|')]
                    if parts[1] and parts[1] != 'error_type':
                        patterns[parts[1]] = {
                            'pattern': parts[2],
                            'category': 'KNOWN_NEEDS_LLM',
                            'llm_hint': parts[3]
                        }
    except FileNotFoundError:
        pass
    return patterns

def match_error(log_content: str, patterns_file: str) -> Dict:
    patterns = load_patterns(patterns_file)
    for error_type, info in patterns.items():
        if re.search(info['pattern'], log_content, re.IGNORECASE):
            return {
                'error_type': error_type,
                'category': 'KNOWN_NEEDS_LLM',
                'llm_hint': info['llm_hint'],
                'error_message': log_content[:500]
            }
    return {'error_type': 'unknown', 'category': 'UNKNOWN', 'error_message': log_content[:500]}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--patterns', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()
    print(json.dumps(match_error(args.log, args.patterns), ensure_ascii=False))
```

- [ ] **Step 5: Write analyze_traceback.py**

```python
# skills/python-error-analyzer/scripts/analyze_traceback.py
"""Python traceback 深度解析"""

import re
import json
from typing import Dict, List

def parse_python_traceback(log: str) -> Dict:
    result = {
        'error_type': None,
        'error_message': None,
        'call_chain': [],
        'root_cause': None
    }

    # 提取 Traceback
    traceback_pattern = r'Traceback \(most recent call last\):\n(.*?)(\n(\w+Error|Exception): (.+))?'
    match = re.search(traceback_pattern, log, re.DOTALL)
    if match:
        stack_text = match.group(1)
        result['error_type'] = match.group(3) if match.group(3) else None
        result['error_message'] = match.group(4) if match.group(4) else None

        # 解析调用链
        file_pattern = r'File "([^"]+)", line (\d+), in (\w+)'
        for fm in re.finditer(file_pattern, stack_text):
            result['call_chain'].append({
                'file': fm.group(1),
                'line': int(fm.group(2)),
                'function': fm.group(3)
            })

        # 根因是最后一个调用
        if result['call_chain']:
            result['root_cause'] = result['call_chain'][-1]

    return result

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True)
    args = parser.parse_args()
    print(json.dumps(parse_python_traceback(args.log), ensure_ascii=False))
```

- [ ] **Step 6: Commit**

```bash
git add skills/python-error-analyzer/
git commit -m "feat(skills): add python-error-analyzer complete"
```

---

## Task 19-21: DataX 错误分析器

**Files:**
- Create: `skills/datax-error-analyzer/SKILL.md`
- Create: `skills/datax-error-analyzer/datax_patterns.md`
- Create: `skills/datax-error-analyzer/scripts/match_error.py`

- [ ] **Step 1: Create directory**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/skills/datax-error-analyzer/scripts
```

- [ ] **Step 2: Write SKILL.md**

```markdown
# skills/datax-error-analyzer/SKILL.md
---
name: datax-error-analyzer
description: 分析 DataX 任务执行错误并给出修复建议。当 DataX 任务失败时触发，适用于连接失败、权限不足、字段不匹配等。不要用于 SPARK、SHELL 等其他任务类型。
---

# DataX 错误分析器

## 概述

通过日志预处理 + 模式匹配分析 DataX 数据同步错误。

## 处理流程

### 步骤 1：日志预处理

```bash
python skills/common/preprocess_log.py --log "<日志内容>" --task-type DATAX
```

### 步骤 2：匹配错误模式

```bash
python scripts/match_error.py --patterns datax_patterns.md --log "<error_blocks>"
```

### 步骤 3：增强上下文（连接错误时）

```bash
python skills/common/extract_context.py --log "<error_blocks>" --cluster config/cluster_info.md
```

---

## 快速参考表

| 错误类型 | 匹配模式 | 分析提示 |
|---------|---------|---------|
| connection_refused | `Communications link failure` | MySQL/Oracle 连接失败 |
| auth_failed | `Access denied for user` | 权限不足 |
| table_not_found | `Table 'xxx' doesn't exist` | 目标表不存在 |
| column_mismatch | `Unknown column 'xxx'` | 字段不匹配 |
```

- [ ] **Step 3: Write patterns.md**

```markdown
# skills/datax-error-analyzer/datax_patterns.md

# DataX 错误模式表

| error_type | pattern | llm_hint |
|------------|---------|----------|
| connection_refused | `Communications link failure` | MySQL/Oracle 连接失败 |
| auth_failed | `Access denied for user` | 权限不足，检查账号密码 |
| table_not_found | `Table.*doesn't exist` | 目标表不存在 |
| column_mismatch | `Unknown column` | 字段不匹配 |
| type_conversion | `Data truncation` | 类型转换失败 |
| primary_key_dup | `Duplicate entry` | 主键重复 |
| timeout | `connect timed out` | 连接超时 |
```

- [ ] **Step 4: Write match_error.py**

```python
# skills/datax-error-analyzer/scripts/match_error.py
"""DataX 错误模式匹配"""

import re
import json
from typing import Dict

def match_error(log_content: str, patterns_file: str) -> Dict:
    patterns = {}
    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            for line in f.read().split('\n'):
                if line.startswith('|') and len(line.split('|')) >= 4:
                    parts = [p.strip() for p in line.split('|')]
                    if parts[1] and parts[1] != 'error_type':
                        patterns[parts[1]] = {'pattern': parts[2], 'llm_hint': parts[3]}
    except FileNotFoundError:
        pass

    for error_type, info in patterns.items():
        if re.search(info['pattern'], log_content, re.IGNORECASE):
            return {
                'error_type': error_type,
                'category': 'KNOWN_NEEDS_LLM',
                'llm_hint': info['llm_hint'],
                'error_message': log_content[:500]
            }
    return {'error_type': 'unknown', 'category': 'UNKNOWN', 'error_message': log_content[:500]}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--patterns', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()
    print(json.dumps(match_error(args.log, args.patterns), ensure_ascii=False))
```

- [ ] **Step 5: Commit**

```bash
git add skills/datax-error-analyzer/
git commit -m "feat(skills): add datax-error-analyzer complete"
```

---

## Task 22-24: 超时分析器

**Files:**
- Create: `skills/timeout-analyzer/SKILL.md`
- Create: `skills/timeout-analyzer/scripts/analyze_timeout.py`
- Create: `skills/timeout-analyzer/scripts/check_cluster.py`

- [ ] **Step 1: Create directory**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/skills/timeout-analyzer/scripts
```

- [ ] **Step 2: Write SKILL.md**

```markdown
# skills/timeout-analyzer/SKILL.md
---
name: timeout-analyzer
description: 分析工作流超时告警并定位根因。当工作流执行超过配置的超时阈值时触发。不要用于任务错误分析。
---

# 超时分析器

## 概述

定位超时根因：任务报错重试 或 资源等待。

## 超时原因（仅 2 种）

| 原因 | 判断条件 | 分析方式 |
|-----|---------|---------|
| 任务报错重试 | `retry_count > 0` | 哪个任务 + 错误类型 |
| 资源等待 | `queue_wait_time > 历史 × 2` | 集群资源竞争 |

**其他原因无关** - 重试策略和超时阈值都是默认配置。

---

## 处理流程

### 步骤 1：获取当前工作流任务列表

```bash
dsctl workflow instance tasks --instance-id "<workflow_instance_id>"
```

### 步骤 2：获取历史数据（7 天）

```bash
cat data/metrics/2026-05-{04..10}.json | grep "<workflow_code>"
```

### 步骤 3：分析每个任务

检查原因 1：任务报错重试
- 如果 `retry_count > 0` → 获取任务日志 → 匹配错误类型

检查原因 2：资源等待
- 如果 `queue_wait_time > avg × 2` → 检查集群资源状态

### 步骤 4：定位根因

按 `total_duration` 排序，取最长的异常任务作为根因。

---

## 输出格式

场景 1：任务报错重试

```json
{
  "root_cause": {
    "type": "task_error_retry",
    "task_name": "spark_transform",
    "error_type": "connection_refused",
    "retry_count": 2
  },
  "llm_hint": "spark_transform 报错 connection_refused，重试 2 次"
}
```

场景 2：资源等待

```json
{
  "root_cause": {
    "type": "resource_waiting",
    "task_name": "spark_aggregate",
    "queue_wait": 300,
    "avg_queue_wait": 50
  },
  "cluster_status": {
    "utilization": 0.85,
    "running_apps": 15
  },
  "llm_hint": "spark_aggregate 等待资源 300s（历史平均 50s）"
}
```
```

- [ ] **Step 3: Write analyze_timeout.py**

```python
# skills/timeout-analyzer/scripts/analyze_timeout.py
"""
超时根因分析

仅分析 2 种原因：
1. 任务报错重试 (retry_count > 0)
2. 资源等待 (queue_wait_time > 历史 × 2)
"""

import json
from typing import Dict, List, Optional
from pathlib import Path

def analyze_timeout_alert(
    tasks: List[Dict],
    historical_metrics: List[Dict]
) -> Dict:
    """分析超时告警"""
    analysis = []

    for task in tasks:
        task_analysis = {
            'task_name': task.get('task_name'),
            'retry_count': task.get('retry_count', 0),
            'queue_wait_time': task.get('queue_wait_time', 0),
            'timeout_reason': None,
            'is_timeout_cause': False
        }

        # 原因 1: 任务报错重试
        if task['retry_count'] > 0:
            task_analysis['timeout_reason'] = 'task_error_retry'
            task_analysis['is_timeout_cause'] = True
            task_analysis['llm_hint'] = f"重试 {task['retry_count']} 次"

        # 原因 2: 资源等待
        else:
            # 计算历史平均等待时间
            historical = [h for h in historical_metrics if h.get('task_code') == task.get('task_code')]
            if historical:
                avg_wait = sum(h.get('queue_wait_time', 0) for h in historical) / len(historical)
                if task['queue_wait_time'] > avg_wait * 2:
                    task_analysis['timeout_reason'] = 'resource_waiting'
                    task_analysis['avg_queue_wait'] = avg_wait
                    task_analysis['is_timeout_cause'] = True
                    task_analysis['llm_hint'] = f"等待 {task['queue_wait_time']}s（历史平均 {avg_wait}s）"

        analysis.append(task_analysis)

    # 定位根因
    timeout_tasks = [a for a in analysis if a['is_timeout_cause']]
    if not timeout_tasks:
        return {'cause': 'unknown', 'analysis': analysis}

    root_task = max(timeout_tasks, key=lambda t: t.get('queue_wait_time', 0))

    return {
        'root_cause': {
            'type': root_task['timeout_reason'],
            'task_name': root_task['task_name'],
            'retry_count': root_task.get('retry_count'),
            'queue_wait_time': root_task.get('queue_wait_time')
        },
        'analysis': analysis,
        'llm_hint': root_task.get('llm_hint', '')
    }

def load_historical_metrics(workflow_code: str, days: int = 7) -> List[Dict]:
    """加载历史指标"""
    metrics = []
    metrics_dir = Path('data/metrics')

    for f in metrics_dir.glob('*.json'):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
                for item in data:
                    if item.get('workflow_code') == workflow_code:
                        metrics.append(item)
        except (json.JSONDecodeError, FileNotFoundError):
            continue

    return metrics[-days:] if len(metrics) > days else metrics

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--tasks', required=True)
    parser.add_argument('--workflow-code', required=True)
    args = parser.parse_args()

    tasks = json.loads(args.tasks)
    historical = load_historical_metrics(args.workflow_code)

    result = analyze_timeout_alert(tasks, historical)
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 4: Write check_cluster.py**

```python
# skills/timeout-analyzer/scripts/check_cluster.py
"""
检查集群资源状态
"""

import json
from typing import Dict

def get_cluster_resource_status(yarn_metrics: Dict) -> Dict:
    """获取集群资源状态"""
    used_mb = yarn_metrics.get('usedMB', 0)
    total_mb = yarn_metrics.get('totalMB', 1)
    running_apps = yarn_metrics.get('appsRunning', 0)
    pending_apps = yarn_metrics.get('appsPending', 0)

    utilization = used_mb / total_mb if total_mb > 0 else 0

    return {
        'utilization': utilization,
        'used_mb': used_mb,
        'total_mb': total_mb,
        'running_apps': running_apps,
        'pending_apps': pending_apps,
        'is_overloaded': utilization > 0.8 or pending_apps > 10
    }

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--yarn-metrics', required=True)
    args = parser.parse_args()

    result = get_cluster_resource_status(json.loads(args.yarn_metrics))
    print(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 5: Commit**

```bash
git add skills/timeout-analyzer/
git commit -m "feat(skills): add timeout-analyzer complete"
```

---

## Task 25: Skills 统一注册表

**Files:**
- Create: `skills/registry.py`

- [ ] **Step 1: Write registry.py**

```python
# skills/registry.py
"""
Skills 统一注册表

加载 SKILL.md 并提供统一的调用接口
"""

import json
from pathlib import Path
from typing import Dict, Optional

class SkillRegistry:
    """Skills 注册表"""

    def __init__(self, skills_dir: str = 'skills'):
        self.skills_dir = Path(skills_dir)
        self._skills = {}
        self._load_all_skills()

    def _load_all_skills(self):
        """加载所有 SKILL.md"""
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir() and skill_dir.name != 'common':
                skill_md = skill_dir / 'SKILL.md'
                if skill_md.exists():
                    self._skills[skill_dir.name] = self._parse_skill_md(skill_md)

    def _parse_skill_md(self, skill_md: Path) -> Dict:
        """解析 SKILL.md 的 YAML frontmatter"""
        with open(skill_md, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 YAML frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                import yaml
                try:
                    frontmatter = yaml.safe_load(parts[1])
                    return {
                        'name': frontmatter.get('name'),
                        'description': frontmatter.get('description'),
                        'path': str(skill_md.parent)
                    }
                except yaml.YAMLError:
                    pass

        return {'path': str(skill_md.parent)}

    def get_skill(self, skill_name: str) -> Optional[Dict]:
        """获取 Skill"""
        return self._skills.get(skill_name)

    def list_skills(self) -> Dict:
        """列出所有 Skills"""
        return self._skills

    def match_skill_for_task_type(self, task_type: str) -> Optional[str]:
        """根据任务类型匹配 Skill"""
        task_skill_map = {
            'SPARK': 'spark-error-analyzer',
            'SPARK_STREAMING': 'spark-error-analyzer',
            'SHELL': 'shell-error-analyzer',
            'PYTHON': 'python-error-analyzer',
            'DATAX': 'datax-error-analyzer'
        }
        return task_skill_map.get(task_type.upper())

# 全局注册表
skill_registry = SkillRegistry()

__all__ = ['SkillRegistry', 'skill_registry']
```

- [ ] **Step 2: Commit**

```bash
git add skills/registry.py
git commit -m "feat(skills): add unified skill registry"
```

---

## Task 26: 更新 cluster_info.md 配置

**Files:**
- Modify: `config/cluster_info.md`

- [ ] **Step 1: Update cluster_info.md**

添加完整的集群配置表，确保包含：
- Hosts 表（IP、Hostname、Services）
- Service Dependencies 表
- Resource Limits 表

参考 Task 3 中的模板格式。

- [ ] **Step 2: Commit**

```bash
git add config/cluster_info.md
git commit -m "docs: update cluster configuration"
```

---

## Task 27-28: 知识库和变更记录目录

**Files:**
- Create: `data/knowledge_base/projects/` 目录结构
- Create: `data/changes/` 目录

- [ ] **Step 1: Create directories**

```bash
mkdir -p D:/Project/dolphinscheduler-agent/data/knowledge_base/projects
mkdir -p D:/Project/dolphinscheduler-agent/data/changes
```

- [ ] **Step 2: Create example knowledge file**

```markdown
# data/knowledge_base/projects/example/spark_errors.md

## workflow: example_workflow

### task: spark_task

| 错误类型 | 发生时间 | 原配置 | 修复配置 | 结果 |
|---------|---------|-------|---------|-----|
| oom_executor | 2026-05-10 | {"spark.executor.memory": "2g"} | {"spark.executor.memory": "4g"} | SUCCESS |
```

- [ ] **Step 3: Commit**

```bash
git add data/knowledge_base/projects/ data/changes/
git commit -m "feat: add knowledge base and change record directories"
```

---

## Task 29: 每日指标采集脚本

**Files:**
- Create: `scripts/collect_metrics.py`

- [ ] **Step 1: Write collect_metrics.py**

```python
# scripts/collect_metrics.py
"""
每日任务指标采集

采集前一天任务执行数据，存储到 data/metrics/
"""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

def collect_daily_task_metrics(date: str) -> List[Dict]:
    """采集指定日期的任务指标"""
    metrics = []

    # 使用 dsctl 获取工作流实例
    # 实际实现需要调用 dsctl CLI
    # 这里提供框架结构

    try:
        # 获取所有项目
        projects_result = subprocess.run(
            ['dsctl', 'project', 'list'],
            capture_output=True, text=True
        )
        projects = json.loads(projects_result.stdout)

        for project in projects:
            workflows_result = subprocess.run(
                ['dsctl', 'workflow', 'list', '--project-code', project['code']],
                capture_output=True, text=True
            )
            workflows = json.loads(workflows_result.stdout)

            for workflow in workflows:
                instances_result = subprocess.run(
                    ['dsctl', 'workflow', 'instance', 'list',
                     '--workflow-code', workflow['code'],
                     '--date', date],
                    capture_output=True, text=True
                )
                instances = json.loads(instances_result.stdout)

                for instance in instances:
                    tasks_result = subprocess.run(
                        ['dsctl', 'workflow', 'instance', 'tasks',
                         '--instance-id', instance['id']],
                        capture_output=True, text=True
                    )
                    tasks = json.loads(tasks_result.stdout)

                    for task in tasks:
                        metrics.append({
                            'date': date,
                            'project_code': project['code'],
                            'workflow_code': workflow['code'],
                            'task_name': task['name'],
                            'task_type': task['type'],
                            'task_state': task['state'],
                            'submit_time': task.get('submitTime'),
                            'start_time': task.get('startTime'),
                            'end_time': task.get('endTime'),
                            'retry_count': task.get('retryCount', 0),
                            'app_id': task.get('appId')
                        })
    except Exception as e:
        print(f"Error collecting metrics: {e}")

    return metrics

def save_metrics(metrics: List[Dict], date: str):
    """保存指标到文件"""
    metrics_dir = Path('data/metrics')
    metrics_dir.mkdir(parents=True, exist_ok=True)

    output_file = metrics_dir / f'{date}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(metrics)} metrics to {output_file}")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=None)
    parser.add_argument('--yesterday', action='store_true')
    args = parser.parse_args()

    if args.yesterday:
        date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        date = args.date or datetime.now().strftime('%Y-%m-%d')

    metrics = collect_daily_task_metrics(date)
    save_metrics(metrics, date)
```

- [ ] **Step 2: Commit**

```bash
git add scripts/collect_metrics.py
git commit -m "feat: add daily metrics collection script"
```

---

## Task 30-34: 修改现有 Skills 模块

**Files:**
- Modify: `src/skills/registry.py`
- Modify: `src/skills/spark_skill.py`
- Modify: `src/skills/shell_skill.py`
- Modify: `src/skills/python_skill.py`
- Modify: `src/skills/datax_skill.py`

- [ ] **Step 1: Update src/skills/registry.py**

添加 SKILL.md 加载逻辑，保留现有 Python 类作为兼容层：

```python
# src/skills/registry.py 修改部分
"""
Skill 注册表 - 管理所有 Skills

支持两种模式：
1. 新模式：加载 skills/ 目录下的 SKILL.md
2. 兼容模式：使用现有 Python 类
"""

import sys
sys.path.insert(0, 'D:/Project/dolphinscheduler-agent')

from pathlib import Path
from typing import Optional
from .base import BaseSkill
from .spark_skill import SparkSkill
from .shell_skill import ShellSkill
from .python_skill import PythonSkill
from .datax_skill import DataXSkill
from ..models.analysis import ErrorAnalysis
from ..models.alert import AlertContext

# 尝试加载新的 registry
try:
    from skills.registry import skill_registry as new_registry
    NEW_REGISTRY_AVAILABLE = True
except ImportError:
    NEW_REGISTRY_AVAILABLE = False

class SkillRegistry:
    """
    Skill 注册表
    根据 taskType 返回对应的 Skill
    """

    def __init__(self):
        self._skills = {
            "SPARK": SparkSkill(),
            "SPARK_STREAMING": SparkSkill(),
            "SHELL": ShellSkill(),
            "PYTHON": PythonSkill(),
            "DATAX": DataXSkill(),
        }
        self._default_skill = DefaultSkill()

    def get_skill(self, task_type: str) -> BaseSkill:
        return self._skills.get(task_type.upper(), self._default_skill)

    def register_skill(self, task_types: list, skill: BaseSkill) -> None:
        for task_type in task_types:
            self._skills[task_type.upper()] = skill

    def get_skill_md_path(self, task_type: str) -> Optional[str]:
        """获取 SKILL.md 路径（新模式）"""
        if NEW_REGISTRY_AVAILABLE:
            skill_name = new_registry.match_skill_for_task_type(task_type)
            if skill_name:
                skill_info = new_registry.get_skill(skill_name)
                return skill_info.get('path')
        return None

# 全局注册表
skill_registry = SkillRegistry()

class DefaultSkill(BaseSkill):
    # 保持不变
    pass

__all__ = ["SkillRegistry", "skill_registry"]
```

- [ ] **Step 2: Update src/skills/shell_skill.py**

移除拼写错误映射（common_spell_errors、common_arg_errors），改为调用脚本：

```python
# src/skills/shell_skill.py 修改部分
"""
Shell Skill - Shell 任务错误分析专家

移除拼写错误映射，改为调用 skills/shell-error-analyzer/scripts/
"""

import subprocess
import json
from typing import Optional, Dict
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.alert import AlertContext
from .base import BaseSkill

class ShellSkill(BaseSkill):
    skill_name = "shell"
    task_types = ["SHELL"]

    # 移除 common_spell_errors 和 common_arg_errors
    # 改为调用脚本匹配

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """分析 Shell 脚本错误 - 调用脚本"""

        # 调用预处理脚本
        preprocess_result = self._call_script(
            'skills/common/preprocess_log.py',
            ['--log', log_content, '--task-type', 'SHELL']
        )

        if preprocess_result:
            error_blocks = preprocess_result.get('error_blocks', [])
            log_for_match = '\n'.join(error_blocks) if error_blocks else log_content[:500]
        else:
            log_for_match = log_content[:500]

        # 调用匹配脚本
        match_result = self._call_script(
            'skills/shell-error-analyzer/scripts/match_error.py',
            ['--patterns', 'skills/shell-error-analyzer/shell_patterns.md',
             '--log', log_for_match]
        )

        if match_result:
            return ErrorAnalysis(
                error_type=match_result.get('error_type', 'unknown'),
                category=ErrorCategory(match_result.get('category', 'UNKNOWN')),
                error_message=match_result.get('error_message', log_for_match),
                llm_hint=match_result.get('llm_hint'),
                matched_pattern=match_result.get('matched_pattern')
            )

        # 回退到默认处理
        return ErrorAnalysis(
            error_type='unknown',
            category=ErrorCategory.UNKNOWN,
            error_message=log_content[:500]
        )

    def _call_script(self, script_path: str, args: list) -> Optional[Dict]:
        """调用 Python 脚本"""
        try:
            result = subprocess.run(
                ['python', script_path] + args,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

__all__ = ["ShellSkill"]
```

- [ ] **Step 3: Update src/skills/spark_skill.py**

保留现有逻辑，添加脚本调用作为增强：

```python
# src/skills/spark_skill.py 修改部分
"""
Spark Skill - Spark 任务错误分析专家

保留现有逻辑，添加脚本调用作为增强
"""

import subprocess
import json
from typing import Optional, Dict
from ..models.analysis import ErrorAnalysis, ErrorCategory
from ..models.alert import AlertContext
from .base import BaseSkill

class SparkSkill(BaseSkill):
    skill_name = "spark"
    task_types = ["SPARK", "SPARK_STREAMING"]

    # 保留现有 error_patterns 和其他方法

    def analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """分析 Spark 任务错误 - 先预处理"""

        # 1. 调用预处理脚本
        preprocess_result = self._call_script(
            'skills/common/preprocess_log.py',
            ['--log', log_content, '--task-type', 'SPARK']
        )

        if preprocess_result:
            error_blocks = preprocess_result.get('error_blocks', [])
            data_metrics = preprocess_result.get('data_metrics', {})
            app_info = preprocess_result.get('app_info', {})

            # 2. 调用匹配脚本
            log_for_match = '\n'.join(error_blocks) if error_blocks else log_content
            match_result = self._call_script(
                'skills/spark-error-analyzer/scripts/match_error.py',
                ['--patterns', 'skills/spark-error-analyzer/spark_patterns.md',
                 '--log', log_for_match]
            )

            if match_result:
                # 3. 如果 AUTO_FIXABLE，调用 build_fix
                if match_result.get('category') == 'AUTO_FIXABLE':
                    config_lines = preprocess_result.get('config_lines', [])
                    fix_result = self._call_script(
                        'skills/spark-error-analyzer/scripts/build_fix.py',
                        ['--error-type', match_result['error_type'],
                         '--current-config', json.dumps(self._parse_config(config_lines)),
                         '--cluster-limit', json.dumps({'max_executor_mem': '16g', 'max_driver_mem': '8g'})]
                    )

                    return ErrorAnalysis(
                        error_type=match_result['error_type'],
                        category=ErrorCategory.AUTO_FIXABLE,
                        error_message=match_result['error_message'],
                        confidence=0.95,
                        matched_pattern=match_result['matched_pattern'],
                        quick_fix=fix_result,
                        spark_app_id=app_info.get('app_id')
                    )

                return ErrorAnalysis(
                    error_type=match_result['error_type'],
                    category=ErrorCategory(match_result['category']),
                    error_message=match_result['error_message'],
                    llm_hint=match_result.get('extra') or match_result.get('llm_hint'),
                    matched_pattern=match_result['matched_pattern'],
                    spark_app_id=app_info.get('app_id')
                )

        # 回退到现有逻辑
        return self._legacy_analyze(log_content, context)

    def _call_script(self, script_path: str, args: list) -> Optional[Dict]:
        """调用 Python 脚本"""
        try:
            result = subprocess.run(
                ['python', script_path] + args,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    def _parse_config(self, config_lines: list) -> Dict:
        """解析配置行"""
        config = {}
        for line in config_lines:
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].strip()
                value = parts[1].strip()
                config[key] = value
        return config

    def _legacy_analyze(self, log_content: str, context: AlertContext) -> ErrorAnalysis:
        """保留现有逻辑作为回退"""
        # 保留原有的 analyze 方法逻辑
        # ...

__all__ = ["SparkSkill"]
```

- [ ] **Step 4: Similar updates for python_skill.py and datax_skill.py**

按相同模式修改，添加预处理和脚本调用。

- [ ] **Step 5: Commit**

```bash
git add src/skills/
git commit -m "refactor(skills): update existing skills to use SKILL.md scripts"
```

---

## Task 35-38: 新增测试

**Files:**
- Create: `tests/skills/test_preprocess_log.py`（已在 Task 1）
- Create: `tests/skills/test_match_error.py`（已在 Task 7）
- Create: `tests/skills/test_timeout_analyzer.py`
- Create: `tests/skills/test_safety_check.py`（已在 Task 4）

- [ ] **Step 1: Write test_timeout_analyzer.py**

```python
# tests/skills/test_timeout_analyzer.py
import pytest
import sys
sys.path.insert(0, 'D:/Project/dolphinscheduler-agent')

from skills.timeout_analyzer.scripts.analyze_timeout import analyze_timeout_alert

def test_task_error_retry():
    """测试任务报错重试导致的超时"""
    tasks = [
        {'task_name': 'spark_task', 'retry_count': 2, 'queue_wait_time': 10, 'task_code': 'task_1'}
    ]
    historical = [
        {'task_code': 'task_1', 'queue_wait_time': 50}
    ]

    result = analyze_timeout_alert(tasks, historical)
    assert result['root_cause']['type'] == 'task_error_retry'
    assert result['root_cause']['task_name'] == 'spark_task'

def test_resource_waiting():
    """测试资源等待导致的超时"""
    tasks = [
        {'task_name': 'spark_task', 'retry_count': 0, 'queue_wait_time': 300, 'task_code': 'task_1'}
    ]
    historical = [
        {'task_code': 'task_1', 'queue_wait_time': 50}
    ]

    result = analyze_timeout_alert(tasks, historical)
    assert result['root_cause']['type'] == 'resource_waiting'
    assert result['root_cause']['queue_wait_time'] == 300

def test_unknown_cause():
    """测试未知超时原因"""
    tasks = [
        {'task_name': 'normal_task', 'retry_count': 0, 'queue_wait_time': 50, 'task_code': 'task_1'}
    ]
    historical = [
        {'task_code': 'task_1', 'queue_wait_time': 50}
    ]

    result = analyze_timeout_alert(tasks, historical)
    assert result['cause'] == 'unknown'
```

- [ ] **Step 2: Run tests**

```bash
cd D:/Project/dolphinscheduler-agent && python -m pytest tests/skills/ -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/skills/test_timeout_analyzer.py
git commit -m "test(skills): add timeout analyzer tests"
```

---

## 验收清单

- [ ] 4 个 error-analyzer skill 目录结构完整
- [ ] timeout-analyzer skill 完整
- [ ] common/preprocess_log.py 日志降噪验证通过
- [ ] patterns.md 为 Markdown 表格格式
- [ ] match_error.py 输出标准 JSON
- [ ] analyze_traceback.py 堆栈解析验证
- [ ] calculate_resource.py 资源建议（最高2倍）
- [ ] cluster_info.md 配置完整
- [ ] collect_metrics.py 每日采集脚本
- [ ] knowledge_base/projects/ 目录结构完整
- [ ] 超时分析（报错重试 + 资源等待）验证
- [ ] 无拼写错误映射残留（ShellSkill 已移除）
- [ ] 安全检查模块完整
- [ ] 所有测试通过