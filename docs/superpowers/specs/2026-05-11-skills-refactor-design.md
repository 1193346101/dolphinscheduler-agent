# Skills 重构设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构现有 skills 模块为 anthropics/skills 规范格式，并增强错误分析能力

**Architecture:** 参考 pdf skill 结构：SKILL.md + patterns.md + scripts/。增加日志预处理、超时分析、历史数据采集等增强功能。

**Tech Stack:** Python 3.x, Markdown, JSON, dsctl, YARN API, Spark History API

---

## 背景

当前 skills 模块（SparkSkill, ShellSkill, PythonSkill, DataXSkill）问题：

1. 不符合 anthropics/skills 规范（无 SKILL.md）
2. ShellSkill 包含 370+ 行拼写错误映射（耗费 token）
3. 模式表硬编码，人不可编辑
4. 日志处理简单（固定前200后300行）
5. 超时告警分析能力不足
6. 缺少历史数据支撑分析

---

## 目标结构

```
skills/
├── common/                        # 公共模块
│   ├── preprocess_log.py          # 日志降噪（所有 skill 共用）
│   ├── extract_context.py         # IP/域名/HDFS 提取
│   └── cluster_lookup.py          # 集群配置关联
│
├── shell-error-analyzer/
│   ├── SKILL.md                   # 核心工作流
│   ├── shell_patterns.md          # 错误模式表
│   └── scripts/
│       ├── match_error.py         # 匹配脚本
│       └── analyze_traceback.py   # 堆栈深度解析
│
├── spark-error-analyzer/
│   ├── SKILL.md
│   ├── spark_patterns.md
│   └── scripts/
│       ├── match_error.py
│       ├── analyze_traceback.py
│       └── build_fix.py           # 构建修复方案（AUTO_FIXABLE）
│       └── calculate_resource.py  # 资源建议计算（最高2倍）
│
├── python-error-analyzer/
│   ├── SKILL.md
│   ├── python_patterns.md
│   └── scripts/
│       ├── match_error.py
│       └── analyze_traceback.py   # Python traceback 深度解析
│
├── datax-error-analyzer/
│   ├── SKILL.md
│   ├── datax_patterns.md
│   └── scripts/
│       └── match_error.py
│
├── timeout-analyzer/              # 超时分析独立 skill
│   ├── SKILL.md
│   └── scripts/
│       ├── analyze_timeout.py     # 超时根因分析
│       └── check_cluster.py       # 集群资源状态
│
└── registry.py                    # 统一注册表

config/
├── cluster_info.md                # 集群配置（IP/服务映射）
└── projects.yaml                  # 项目配置（保留）

data/
├── metrics/                       # 每日任务执行指标
│   ├── 2026-05-10.json
│   ├── 2026-05-11.json
│   └── summary/
│       └── workflow_xxx.json      # 按工作流汇总
│
├── knowledge_base/                # 知识库（增强版）
│   ├── spark_oom.md              # 通用知识
│   ├── projects/
│   │   └ 21451302002208/
│   │       ├── spark_errors.md    # 项目历史（含修复记录）
│   │       └── workflow_errors.md
│   └── approved/
│       └── spark_oom_approved.md  # 人工确认的知识
```

---

## 功能清单

### 1. 日志降噪（通用预处理）

**位置：** `skills/common/preprocess_log.py`

**作用：** 所有 skills 共用，智能提取关键信息，替代固定前200后300行

```python
def preprocess_log(log_content: str, task_type: str) -> Dict:
    """智能提取日志关键信息"""
    result = {
        'config_lines': [],      # Spark/Hadoop 配置
        'error_blocks': [],      # 完整错误堆栈
        'resource_stats': [],    # 资源使用统计
        'app_info': {}           # Application ID 等
    }
    
    lines = log_content.split('\n')
    
    # 1. 提取配置行
    for line in lines:
        if any(prefix in line for prefix in ['spark.', 'hadoop.', 'yarn.']):
            result['config_lines'].append(line.strip())
    
    # 2. 提取完整错误块（ERROR 行 + 后续堆栈）
    i = 0
    while i < len(lines):
        line = lines[i]
        if any(kw in line for kw in ['ERROR', 'FATAL', 'Exception', 'Caused by']):
            block = [line]
            j = i + 1
            # 继续提取堆栈（空格/tab开头的行）
            while j < len(lines) and (lines[j].startswith(' ') or lines[j].startswith('\t') or 'at ' in lines[j]):
                block.append(lines[j])
                j += 1
            result['error_blocks'].append('\n'.join(block))
            i = j
        else:
            i += 1
    
    # 3. 提取 Application ID
    app_match = re.search(r'application_\d+_\d+', log_content)
    if app_match:
        result['app_info']['app_id'] = app_match.group(0)
    
    return result

def validate_extraction(original: str, extracted: Dict) -> bool:
    """验证提取完整性"""
    original_errors = re.findall(r'(ERROR|FATAL|Exception)', original)
    extracted_errors = sum(len(block) for block in extracted['error_blocks'])
    return len(original_errors) == extracted_errors
```

**效果：** 从 500 行 → 20-50 行关键信息

---

### 2. 错误传播链分析

**位置：** `skills/*/scripts/match_error.py` 内

**作用：** 分析多个错误的因果关系，定位根因

```python
def analyze_error_chain(errors: List[Dict]) -> Dict:
    """分析错误链"""
    # 按时间排序
    sorted_errors = sorted(errors, key=lambda e: e['timestamp'])
    
    # 因果关系映射
    causal_map = {
        'oom_driver': ['executor_lost', 'shuffle_failed'],
        'connection_refused': ['timeout', 'retry_failed'],
        'class_not_found': ['job_aborted']
    }
    
    root_error = sorted_errors[0]
    for later_error in sorted_errors[1:]:
        if later_error['error_type'] in causal_map.get(root_error['error_type'], []):
            later_error['caused_by'] = root_error['error_type']
    
    return {
        'root_cause': root_error,
        'chain': sorted_errors,
        'llm_hint': f"{root_error['error_type']} 导致后续错误"
    }
```

---

### 3. 知识库增强（项目历史）

**位置：** `data/knowledge_base/projects/{workflow_code}/`

**格式：** Markdown 表格（含历史修复记录）

```markdown
# knowledge_base/projects/21451302002208/spark_errors.md

## workflow: daily_etl

### task: spark_transform

| 错误类型 | 发生时间 | 原配置 | 修复配置 | 结果 |
|---------|---------|-------|---------|-----|
| oom_executor | 2026-05-10 | 2g | 4g | ✅ SUCCESS |
| connection_timeout | 2026-05-08 | 30s | 120s | ✅ SUCCESS |

### 通用建议（基于历史）

- OOM: 建议使用 4g（历史验证）
- Timeout: 建议使用 120s

---

## approved 状态

本知识已由运维团队审核确认。
```

**匹配优先级：** 项目历史 > 通用知识 > LLM 分析

---

### 4. 资源建议（最高2倍）

**位置：** `skills/spark-error-analyzer/scripts/calculate_resource.py`

**策略：**

1. 优先使用历史成功配置
2. 默认翻倍（最高2倍）
3. 检查集群上限

```python
def calculate_resource_suggestion(error_type: str, current_config: Dict, historical: List[Dict]) -> Dict:
    current_mem = parse_memory(current_config.get('spark.executor.memory', '1g'))
    
    # 1. 优先历史成功配置
    if historical:
        success_config = find_success_config(historical, error_type)
        if success_config:
            return {'suggested': success_config, 'reason': '历史验证', 'confidence': 0.95}
    
    # 2. 默认翻倍（上限2倍）
    suggested_mem = current_mem * 2
    
    # 3. 检查集群上限
    cluster_limit = get_cluster_limit()
    if suggested_mem > cluster_limit:
        suggested_mem = cluster_limit
        return {'suggested': suggested_mem, 'reason': '已达上限', 'warning': '无法继续增加'}
    
    return {
        'suggested': format_memory(suggested_mem),
        'reason': '当前配置翻倍',
        'current': format_memory(current_mem),
        'max_limit': format_memory(cluster_limit)
    }
```

---

### 5. 错误分析 + 配置审计（合并）

**位置：** `skills/*/scripts/match_error.py`

**触发条件：** 特定错误类型触发审计

```python
def analyze_error_with_config_audit(log: str, task_config: Dict) -> Dict:
    result = match_error(log)
    
    # 特定错误触发配置审计
    audit_errors = ['class_not_found', 'jar_not_found', 'main_class_not_found']
    if result['error_type'] in audit_errors:
        config_issues = audit_task_config(result['error_type'], task_config)
        result['config_issues'] = config_issues
        if config_issues:
            result['llm_hint'] += f"\n配置问题: {config_issues[0]['issue']}"
    
    return result

def audit_task_config(error_type: str, task_config: Dict) -> List[Dict]:
    issues = []
    
    if error_type in ['class_not_found', 'main_class_not_found']:
        jar_path = task_config.get('jarPath')
        main_class = task_config.get('mainClass')
        if not check_class_in_jar(jar_path, main_class):
            issues.append({'field': 'mainClass', 'issue': f'类 {main_class} 不存在'})
    
    if error_type == 'jar_not_found':
        if not check_resource_uploaded(task_config.get('jarPath')):
            issues.append({'field': 'jarPath', 'issue': 'Jar 包未上传'})
    
    return issues
```

---

### 6. 堆栈深度解析

**位置：** `skills/*/scripts/analyze_traceback.py`

**作用：** 定位具体代码文件和行号

```python
def parse_python_traceback(log: str) -> Dict:
    pattern = r'Traceback \(most recent call last\):\n(.*?)(\n(\w+Error): (.+))'
    match = re.search(pattern, log, re.DOTALL)
    
    if not match:
        return {}
    
    stack_text = match.group(1)
    error_type = match.group(3)
    error_msg = match.group(4)
    
    call_chain = []
    for line in stack_text.split('\n'):
        if 'File "' in line:
            file_match = re.search(r'File "([^"]+)", line (\d+), in (\w+)', line)
            if file_match:
                call_chain.append({
                    'file': file_match.group(1),
                    'line': int(file_match.group(2)),
                    'function': file_match.group(3)
                })
    
    root = call_chain[-1] if call_chain else {}
    
    return {
        'error_type': error_type,
        'error_message': error_msg,
        'call_chain': call_chain,
        'root_cause': {'file': root.get('file'), 'line': root.get('line'), 'function': root.get('function')}
    }

def parse_spark_exception(log: str) -> Dict:
    # 提取最外层异常 + Caused by（根因）
    outer_match = re.search(r'org\.apache\.spark\.(\w+Exception): (.+)', log)
    caused_match = re.search(r'Caused by: ([\w.]+(?:Error|Exception)): (.+)', log)
    
    if caused_match:
        return {
            'error_type': outer_match.group(1),
            'root_cause': {'type': caused_match.group(1), 'message': caused_match.group(2)}
        }
    
    return {'error_type': outer_match.group(1) if outer_match else 'unknown'}
```

---

### 7. 服务依赖图 + 知识图谱下游

**位置：** `config/cluster_info.md` + 知识图谱查询

**cluster_info.md 新增依赖表：**

```markdown
## Service Dependencies

| Service | Depends On | Impact If Down |
|---------|------------|----------------|
| Spark SQL | Hive Metastore | Cannot query tables |
| DataX MySQL | MySQL Server | Cannot sync data |
```

**下游影响查询：**

```python
def get_downstream_impact(workflow_code: str) -> Dict:
    # 知识图谱查询下游工作流
    downstream = query_knowledge_graph(workflow_code)
    
    return {
        'downstream_workflows': downstream,
        'affected_tasks': len(downstream),
        'llm_hint': f"影响 {len(downstream)} 个下游工作流"
    }
```

---

### 8. 错误频率统计（7天）

**作用：** 检测反复出现的错误

```python
def analyze_error_frequency(error_type: str, workflow_code: str) -> Dict:
    # 查询最近 7 天相同错误次数
    count = query_error_history(workflow_code, error_type, days=7)
    
    if count >= 3:
        return {
            'frequency': 'HIGH',
            'count': count,
            'suggestion': f'最近 7 天出现 {count} 次，建议系统性排查'
        }
    
    return {'frequency': 'LOW', 'count': count}
```

---

### 9. 超时分析（简化版）

**位置：** `skills/timeout-analyzer/scripts/analyze_timeout.py`

**触发超时的两个原因：**

| 原因 | 分析方式 | 定位 |
|-----|---------|-----|
| 任务报错重试 | retry_count > 0 + 错误类型 | 哪个任务报错 |
| 资源等待 | queue_wait_time vs 历史（7天） | 集群资源竞争 |

```python
def analyze_timeout_alert(workflow_code: str, alert_time: str) -> Dict:
    current_tasks = get_current_tasks(workflow_code)
    historical = get_historical_metrics(workflow_code, days=7)
    
    analysis = []
    for task in current_tasks:
        task_analysis = {
            'task_name': task['task_name'],
            'retry_count': task['retry_count'],
            'queue_wait_time': task['queue_wait_time'],
            'timeout_reason': None,
            'is_timeout_cause': False
        }
        
        # 原因1: 任务报错重试
        if task['retry_count'] > 0:
            task_logs = get_task_logs(task['task_code'])
            error = match_error(task_logs)
            
            task_analysis['error_type'] = error['error_type']
            task_analysis['timeout_reason'] = 'task_error_retry'
            task_analysis['is_timeout_cause'] = True
            task_analysis['llm_hint'] = f"报错 {error['error_type']}，重试 {task['retry_count']} 次"
        
        # 原因2: 资源等待
        else:
            task_history = [h for h in historical if h['task_code'] == task['task_code']]
            avg_queue_wait = calc_avg(task_history, 'queue_wait_time')
            
            if task['queue_wait_time'] > avg_queue_wait * 2:
                task_analysis['timeout_reason'] = 'resource_waiting'
                task_analysis['avg_queue_wait'] = avg_queue_wait
                task_analysis['is_timeout_cause'] = True
                task_analysis['llm_hint'] = f"队列等待 {task['queue_wait_time']}s（历史平均 {avg_queue_wait}s）"
        
        analysis.append(task_analysis)
    
    # 定位根因
    timeout_tasks = [a for a in analysis if a['is_timeout_cause']]
    if not timeout_tasks:
        return {'cause': 'unknown'}
    
    root_task = max(timeout_tasks, key=lambda t: t.get('total_duration', 0))
    
    # 集群资源状态（如果是资源等待）
    if root_task['timeout_reason'] == 'resource_waiting':
        cluster = get_cluster_resource_status(alert_time)
        return {
            'root_cause': {'type': 'resource_waiting', 'task_name': root_task['task_name']},
            'cluster_status': cluster,
            'llm_hint': f"{root_task['task_name']} 等待资源，集群利用率 {cluster['utilization']:.2%}"
        }
    
    return {
        'root_cause': {'type': 'task_error_retry', 'task_name': root_task['task_name'], 'error_type': root_task['error_type']},
        'llm_hint': f"{root_task['task_name']} 报错 {root_task['error_type']}，重试 {root_task['retry_count']} 次"
    }

def get_cluster_resource_status(time: str) -> Dict:
    yarn_metrics = get_yarn_cluster_metrics()
    return {
        'utilization': yarn_metrics['usedMB'] / yarn_metrics['totalMB'],
        'running_apps': yarn_metrics['appsRunning'],
        'pending_apps': yarn_metrics['appsPending']
    }
```

---

### 10. 数据量检测（日志提取 + Spark History API）

**优先级：** 日志提取 > Spark History API

**来源1：Spark Event Log（优先）**

Spark Event Log JSON 包含完整数据量指标：

```json
{
  "Event": "SparkListenerTaskEnd",
  "Task Metrics": {
    "Input Metrics": {
      "Bytes Read": 1073741824,       // 输入数据量
      "Records Read": 10000000        // 输入记录数
    },
    "Output Metrics": {
      "Bytes Written": 536870912,     // 输出数据量
      "Records Written": 5000000      // 输出记录数
    },
    "Shuffle Read Metrics": {
      "Total Bytes Read": 2147483648, // Shuffle 读数据量
      "Fetch Wait Time": 5000         // Shuffle 等待时间
    },
    "Shuffle Write Metrics": {
      "Bytes Written": 2147483648     // Shuffle 写数据量
    },
    "Memory Bytes Spilled": 536870912, // Spill 到磁盘
    "Disk Bytes Spilled": 268435456
  }
}
```

**提取逻辑：**

```python
def extract_data_metrics_from_event_log(event_log: str) -> Dict:
    """从 Spark Event Log 提取数据量指标"""
    
    metrics = {
        'input_bytes': 0,
        'input_records': 0,
        'output_bytes': 0,
        'output_records': 0,
        'shuffle_read_bytes': 0,
        'shuffle_write_bytes': 0,
        'shuffle_fetch_wait_time': 0,
        'memory_spilled': 0,
        'disk_spilled': 0,
        'stage_metrics': []
    }
    
    for line in event_log.split('\n'):
        if not line.strip():
            continue
        
        try:
            event = json.loads(line)
            
            if event['Event'] == 'SparkListenerTaskEnd':
                task_metrics = event.get('Task Metrics', {})
                
                # Input
                input_m = task_metrics.get('Input Metrics', {})
                metrics['input_bytes'] += input_m.get('Bytes Read', 0)
                metrics['input_records'] += input_m.get('Records Read', 0)
                
                # Output
                output_m = task_metrics.get('Output Metrics', {})
                metrics['output_bytes'] += output_m.get('Bytes Written', 0)
                metrics['output_records'] += output_m.get('Records Written', 0)
                
                # Shuffle
                shuffle_read = task_metrics.get('Shuffle Read Metrics', {})
                metrics['shuffle_read_bytes'] += shuffle_read.get('Total Bytes Read', 0)
                metrics['shuffle_fetch_wait_time'] += shuffle_read.get('Fetch Wait Time', 0)
                
                shuffle_write = task_metrics.get('Shuffle Write Metrics', {})
                metrics['shuffle_write_bytes'] += shuffle_write.get('Bytes Written', 0)
                
                # Spill（关键指标：内存不足时 spill 到磁盘）
                metrics['memory_spilled'] += task_metrics.get('Memory Bytes Spilled', 0)
                metrics['disk_spilled'] += task_metrics.get('Disk Bytes Spilled', 0)
            
            elif event['Event'] == 'SparkListenerStageCompleted':
                stage_info = event.get('Stage Info', {})
                metrics['stage_metrics'].append({
                    'stage_id': stage_info.get('Stage ID'),
                    'num_tasks': stage_info.get('Number of Tasks'),
                    'input_bytes': stage_info.get('Input Bytes', 0),
                    'shuffle_read_bytes': stage_info.get('Shuffle Read Bytes', 0)
                })
        
        except json.JSONDecodeError:
            continue
    
    return metrics
```

**来源2：Spark History Server API（补充）**

```python
def get_data_volume_from_history(app_id: str) -> Dict:
    """通过 Spark History API 获取（补充验证）"""
    history_url = get_spark_history_url()
    stages = requests.get(f'{history_url}/api/v1/applications/{app_id}/stages').json()
    
    return {
        'input_bytes': sum(s.get('inputBytes', 0) for s in stages),
        'output_bytes': sum(s.get('outputBytes', 0) for s in stages),
        'shuffle_read_bytes': sum(s.get('shuffleReadBytes', 0) for s in stages)
    }
```

**数据量异常检测：**

```python
def detect_data_anomaly(current_metrics: Dict, historical_avg: Dict) -> Dict:
    """检测数据量异常"""
    anomalies = []
    
    # 输入数据量突增
    if current_metrics['input_bytes'] > historical_avg['input_bytes'] * 5:
        anomalies.append({
            'type': 'input_volume_spike',
            'current': format_bytes(current_metrics['input_bytes']),
            'avg': format_bytes(historical_avg['input_bytes']),
            'ratio': current_metrics['input_bytes'] / historical_avg['input_bytes'],
            'suggestion': '数据量突增，可能需要增加资源'
        })
    
    # Shuffle 数据量大（可能数据倾斜）
    shuffle_ratio = current_metrics['shuffle_read_bytes'] / current_metrics['input_bytes']
    if shuffle_ratio > 10:
        anomalies.append({
            'type': 'shuffle_heavy',
            'shuffle_bytes': format_bytes(current_metrics['shuffle_read_bytes']),
            'input_bytes': format_bytes(current_metrics['input_bytes']),
            'ratio': shuffle_ratio,
            'suggestion': 'Shuffle 数据量大，可能数据倾斜，建议优化分区'
        })
    
    # Spill 到磁盘（内存不足）
    if current_metrics['memory_spilled'] > 0:
        anomalies.append({
            'type': 'memory_spill',
            'spill_bytes': format_bytes(current_metrics['memory_spilled']),
            'suggestion': f'内存不足，Spill {format_bytes(current_metrics["memory_spilled"])}, 建议增加 executor.memory'
        })
    
    return {'anomalies': anomalies, 'has_anomaly': len(anomalies) > 0}
```

---

### 11. 并行任务冲突

**与超时分析结合**

```python
def analyze_parallel_conflict(alert_time: str) -> Dict:
    concurrent_tasks = get_concurrent_tasks(alert_time)
    
    total_mem = sum(t['requested_memory'] or 0 for t in concurrent_tasks)
    cluster_capacity = get_cluster_capacity()
    
    utilization = total_mem / cluster_capacity['memory']
    
    if utilization > 0.8:
        top_consumers = sorted(concurrent_tasks, key=lambda t: t['requested_memory'] or 0, reverse=True)[:5]
        return {
            'confusion': True,
            'utilization': utilization,
            'top_consumers': [{'task': t['task_name'], 'mem': t['requested_memory']} for t in top_consumers]
        }
    
    return {'confusion': False}
```

---

## 每日数据采集

**位置：** `scripts/collect_metrics.py`

**每日定时执行，采集前一天任务执行数据：**

```python
def collect_daily_task_metrics(date: str):
    """采集每日任务指标"""
    projects = get_all_projects()
    
    task_metrics = []
    for project in projects:
        workflows = get_workflows(project['code'])
        
        for workflow in workflows:
            instances = dsctl_get_workflow_instances(project['code'], workflow['code'], date)
            
            for instance in instances:
                tasks = get_task_instances(instance['id'])
                
                for task in tasks:
                    app_info = {}
                    if task['app_id']:
                        app_info = get_yarn_application_info(task['app_id'])
                    
                    task_metrics.append({
                        'date': date,
                        'project_name': project['name'],
                        'workflow_name': workflow['name'],
                        'task_name': task['name'],
                        'task_type': task['type'],
                        'task_state': task['state'],
                        
                        # 时间
                        'submit_time': task['submit_time'],
                        'start_time': task['start_time'],
                        'end_time': task['end_time'],
                        'queue_wait_time': calc_queue_wait(task, app_info),
                        'exec_duration': calc_exec_duration(app_info),
                        
                        # 资源
                        'app_id': task['app_id'],
                        'requested_memory': app_info.get('allocatedMB'),
                        'retry_count': task.get('retryCount', 0)
                    })
    
    save_metrics(task_metrics, f'data/metrics/{date}.json')
```

**任务指标字段：**

| 字段 | 说明 | 来源 |
|-----|-----|-----|
| queue_wait_time | 提交→开始运行 | DS submit - YARN start |
| exec_duration | 真实执行时长 | YARN start - YARN end |
| requested_memory | 请求内存 | YARN API |
| retry_count | 重试次数 | DS API |

---

## Context-Aware 分析

**集群配置：** `config/cluster_info.md`

```markdown
## ali-odp-test

### Hosts

| IP | Hostname | Services |
|----|----------|----------|
| 192.168.1.100 | ali-dolphin-test-01 | DolphinScheduler:12345, YARN RM:8032 |
| 192.168.1.101 | ali-odp-test-02 | Spark History:18082, HDFS NN:9000 |

### Service Dependencies

| Service | Depends On |
|---------|------------|
| Spark SQL | Hive Metastore |

### Resource Limits

| Max Executor Mem | Max Driver Mem |
|------------------|----------------|
| 16g | 8g |
```

**IP 关联逻辑：**

```python
def lookup_service(ip: str, port: int, cluster_file: str) -> Dict:
    hosts = parse_hosts_table(cluster_file)
    for host in hosts:
        if host['ip'] == ip:
            for service in host['services']:
                if service['port'] == port:
                    return {'service': service['name'], 'hostname': host['hostname']}
    return {}
```

---

## SKILL.md 提示词设计

SKILL.md 是 skills 的核心，定义了错误分析的完整流程。参考 anthropics/skills 规范，使用 YAML frontmatter + Markdown 结构。

---

### spark-error-analyzer/SKILL.md

```markdown
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

见下方安全规则部分。

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

---

### shell-error-analyzer/SKILL.md

```markdown
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

---

### timeout-analyzer/SKILL.md

```markdown
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
cat data/metrics/2026-05-{10..16}.json | grep "<workflow_code>"
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
  "llm_hint": "spark_transform 报错 connection_refused，重试 2 次，建议修复任务本身"
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
    "running_apps": 15,
    "pending_apps": 8
  },
  "llm_hint": "spark_aggregate 等待资源 300s（历史平均 50s），集群利用率 85%"
}
```

---

## 重要规则

1. 只分析 2 种原因 - 任务报错重试 或 资源等待
2. 使用 7 天历史 - 计算平均等待时间
3. 队列等待 > 历史 × 2 才算异常
4. 集群利用率 > 80% 表明资源紧张
```

---

### python-error-analyzer/SKILL.md

```markdown
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

Python 错误通常有完整的 traceback，调用堆栈解析脚本：

```bash
python scripts/analyze_traceback.py --log "<error_blocks>" --type python
```

输出：
- `error_type`: 异常类型（如 ValueError, ImportError）
- `error_message`: 错误信息
- `call_chain`: 调用链（文件、行号、函数）
- `root_cause`: 根因位置（具体文件和行号）

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
| indentation_error | `IndentationError` | 检查缩进一致性 |
| type_error | `TypeError` | 类型不匹配，检查参数 |
| value_error | `ValueError` | 值无效，检查输入 |
| key_error | `KeyError` | 键不存在，检查字典/配置 |
| attribute_error | `AttributeError` | 属性不存在，检查对象 |
| connection_error | `ConnectionError` | 网络问题，检查目标服务 |
| timeout_error | `TimeoutError` | 操作超时，检查网络/目标 |

---

## 重要规则

1. 必须预处理日志
2. 堆栈解析定位根因 - 找到具体文件和行号
3. ImportError 需检查环境 - 依赖是否安装
4. 大多数错误需 LLM - Python 很少可自动修复
5. 分析 call_chain - 理解调用顺序
```

---

### datax-error-analyzer/SKILL.md

```markdown
---
name: datax-error-analyzer
description: 分析 DataX 任务执行错误并给出修复建议。当 DataX 任务失败时触发，适用于连接失败、权限不足、字段不匹配、数据类型错误等。不要用于 SPARK、SHELL 等其他任务类型。
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
| auth_failed | `Access denied for user` | 权限不足，检查账号密码 |
| table_not_found | `Table 'xxx' doesn't exist` | 目标表不存在 |
| column_mismatch | `Unknown column 'xxx'` | 字段不匹配，检查配置 |
| type_conversion | `Data truncation` | 类型转换失败 |
| primary_key_dup | `Duplicate entry` | 主键重复 |
| timeout | `connect timed out` | 连接超时，检查网络 |
| oom | `OutOfMemoryError` | 内存不足，增加 JVM 配置 |

---

## DataX 特定分析

### 任务配置检查

DataX 错误常与任务配置相关，需要检查：
- `job.content[0].reader.parameter.connection` - 源端连接
- `job.content[0].writer.parameter.connection` - 目标端连接
- `job.content[0].reader.parameter.username/password` - 账号密码
- `job.content[0].writer.parameter.username/password` - 账号密码
- `job.content[0].reader.parameter.column` - 读取字段
- `job.content[0].writer.parameter.column` - 写入字段

### 增强上下文

DataX 连接错误需要识别具体数据库：
- 提取 IP/端口/数据库名
- 通过 cluster_info.md 查找对应服务
- 检查服务状态和依赖关系

---

## 输出格式

```json
{
  "error_type": "connection_refused",
  "category": "KNOWN_NEEDS_LLM",
  "error_message": "Communications link failure...",
  "targets": [{"ip": "192.168.1.100", "port": 3306, "service": "MySQL Server"}],
  "config_issues": [{"field": "connection", "issue": "目标 MySQL 连接失败"}],
  "llm_hint": "目标 MySQL 192.168.1.100:3306 连接失败，请检查服务状态和网络"
}
```

---

## 重要规则

1. 必须预处理日志
2. 连接错误需增强上下文 - 识别具体数据库
3. 字段错误需检查配置 - column 配置是否匹配
4. 权限错误需检查账号 - username/password 是否正确
5. 所有 DataX 错误需 LLM - 无自动修复场景
```

---

## 操作安全规则

执行任何修复操作前，必须进行安全检查，确保不会对集群或调度系统产生影响。

---

### 1. 集群资源安全检查

**修改配置前必须检查集群状态：**

```bash
curl "{yarn_url}/ws/v1/cluster/metrics"
```

检查项：
- `availableMB` - 集群可用内存
- `appsPending` - 排队任务数
- `utilization = usedMB / totalMB` - 内存利用率

**安全阈值：**

| 检查项 | 安全阈值 | 超阈值处理 |
|-------|---------|-----------|
| 内存利用率 | < 80% | > 80% 禁止增加资源，建议错峰 |
| 排队任务数 | < 10 | > 10 禁止增加资源，等待队列释放 |
| 可用内存 | > 建议 2 倍 | 不足时降级建议或审批 |

---

### 2. 调度系统影响检查

**重跑任务前必须检查：**

| 检查项 | 查询方式 | 安全阈值 |
|-------|---------|---------|
| 下游依赖数 | 知识图谱查询 | < 5 无需审批，> 5 需审批 |
| 并发任务数 | DS API 查询 | < 10 正常，> 10 建议延迟 |
| 定时任务冲突 | 检查定时配置 | 有冲突时建议错峰 |

**下游依赖查询：**

```bash
python -m src.cli.graph_cli downstream --workflow <workflow_code>
```

---

### 3. 配置修改安全约束

| 修改类型 | 集群条件 | 是否允许 | 审批要求 |
|---------|---------|---------|---------|
| 增加内存 | 利用率 < 80% | ✅ 允许 | 无需审批 |
| 增加内存 | 利用率 > 80% | ❌ 禁止 | 必须审批，建议错峰 |
| 修改 Spark 参数 | 非结构性 | ✅ 允许 | 无需审批 |
| 修改依赖关系 | 结构性 | ❌ 禁止 | 必须审批 |
| 重跑任务 | 下游 < 5 | ✅ 允许 | 无需审批 |
| 重跑任务 | 下游 > 5 | ⚠️ 需评估 | 需审批 |

---

### 4. 回滚机制

**记录变更到文件：**

```json
{
  "timestamp": "2026-05-11 10:00:00",
  "operation": "modify_config",
  "workflow_code": "xxx",
  "task_code": "xxx",
  "original_config": {"spark.executor.memory": "2g"},
  "new_config": {"spark.executor.memory": "4g"},
  "operator": "agent",
  "reason": "oom_executor"
}
```

存储位置：`data/changes/{workflow_code}_{timestamp}.json`

**回滚触发条件：**
- 重跑后仍然失败
- 集群资源告警
- 人工确认需回滚

---

### 5. 操作前验证清单

执行任何操作前，必须验证以下清单：

- [ ] 集群利用率 < 80%
- [ ] 排队任务数 < 10
- [ ] 下游依赖数 < 5
- [ ] 原配置已记录（支持回滚）
- [ ] 操作可逆（配置可还原）
- [ ] 不影响定时任务

**任一项不满足 → 需审批或降级建议**

---

### 6. 超时分析安全规则

**资源等待导致的超时：**
- ❌ 不能直接增加资源（会加剧集群负载）
- ✅ 建议错峰执行、调整定时时间
- ✅ 建议拆分大任务为小任务

**任务报错重试导致的超时：**
- ✅ 修复任务本身（解决根因）
- ❌ 不能仅增加重试次数（延长占用时间）
- ❌ 不能调整超时阈值（掩盖问题）

**下游影响评估：**
- 下游 > 5 → 需通知下游任务负责人
- 下游 > 10 → 需审批后才能继续

---

### 7. 安全检查脚本

**位置：** `skills/common/safety_check.py`

```python
def check_cluster_safety(yarn_url: str) -> Dict:
    """检查集群资源安全性"""
    metrics = get_yarn_metrics(yarn_url)
    
    utilization = metrics['usedMB'] / metrics['totalMB']
    pending_apps = metrics['appsPending']
    available_mb = metrics['availableMB']
    
    issues = []
    
    if utilization > 0.8:
        issues.append({
            'type': 'high_utilization',
            'value': utilization,
            'message': '集群利用率超过 80%，禁止增加资源'
        })
    
    if pending_apps > 10:
        issues.append({
            'type': 'queue_overload',
            'value': pending_apps,
            'message': '排队任务超过 10 个，建议等待队列释放'
        })
    
    return {
        'safe': len(issues) == 0,
        'utilization': utilization,
        'pending_apps': pending_apps,
        'available_mb': available_mb,
        'issues': issues
    }

def check_downstream_impact(workflow_code: str) -> Dict:
    """检查下游影响"""
    downstream = query_knowledge_graph(workflow_code)
    
    downstream_count = len(downstream)
    
    return {
        'safe': downstream_count < 5,
        'downstream_count': downstream_count,
        'requires_approval': downstream_count >= 5,
        'message': f'下游依赖 {downstream_count} 个工作流' + ('，需审批' if downstream_count >= 5 else '')
    }
```

---

## 验收标准

- [ ] 4 个 error-analyzer skill 目录结构完整
- [ ] timeout-analyzer skill 完整
- [ ] common/preprocess_log.py 日志降噪验证通过
- [ ] patterns.md 为 Markdown 表格格式
- [ ] match_error.py 输出标准 JSON
- [ ] analyze_traceback.py 堆栈解析验证
- [ ] calculate_resource.py 资源建议（最高2倍）
- [ ] cluster_info.md 配置完整
- [ ] collect_metrics.py 每日采集运行正常
- [ ] knowledge_base/projects/ 目录结构完整
- [ ] analyze.py 集成测试通过
- [ ] 超时分析（报错重试 + 资源等待）验证
- [ ] 无拼写错误映射残留