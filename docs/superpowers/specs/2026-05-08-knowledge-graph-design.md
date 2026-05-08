# DolphinScheduler Agent 知识图谱设计文档

## 概述

本设计将原有血缘解析服务的实时查询改为本地知识图谱查询，用户命令触发扫描更新，告警时直接查询本地图谱，避免实时 API 调用。

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    用户触发层                                │
│  更新命令: "扫描项目 X" / "更新图谱" → 触发扫描重建          │
│  查询命令: "工作流 Y 下游" / "表 T 被谁消费" → 仅查询图谱    │
├─────────────────────────────────────────────────────────────┤
│                    知识图谱服务                              │
│  ┌──────────────┬──────────────┬──────────────┬───────────┐ │
│  │ 图谱扫描器   │ 图谱查询器   │ 索引管理器   │ 图谱存储  │ │
│  │ (Scanner)    │ (Querier)    │ (Indexer)    │ (Storage) │ │
│  └──────────────┴──────────────┴──────────────┴───────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    数据源层                                  │
│  ┌──────────────┬──────────────┬──────────────┬───────────┐ │
│  │ DS API       │ 本地代码仓库 │ Spark主类解析│ SQL解析   │ │
│  │ (工作流定义) │ (类名→表名)  │ (--class)    │ (正则+    │ │
│  │              │              │              │  sqlparse)│ │
│  └──────────────┴──────────────┴──────────────┴───────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    存储层                                    │
│  data/graph/                                                 │
│  ├── {project_code}_graph.json    # 主图谱                   │
│  ├── {project_code}_index_downstream.json  # 下游依赖索引    │
│  ├── {project_code}_index_table_consumer.json # 表消费索引  │
│  └── {project_code}_index_workflow_nodes.json # 工作流节点  │
└─────────────────────────────────────────────────────────────┘
```

**核心组件职责**：

| 组件 | 职责 |
|------|------|
| Scanner | 扫描 DS 工作流定义 + 本地代码，构建图谱 |
| Querier | 查询本地图谱和索引，返回结果 |
| Indexer | 从主图谱生成查询索引文件 |
| Storage | JSON 文件读写管理 |

---

## 图谱数据结构

### 主图谱 JSON 结构

文件：`data/graph/{project_code}_graph.json`

```json
{
  "project_code": 11598158952448,
  "project_name": "data_platform",
  "scanned_at": "2026-05-08T10:00:00",
  "version": 1,
  
  "nodes": {
    "workflows": [
      {
        "code": "123",
        "name": "daily_etl",
        "schedule_type": "CRON",
        "schedule_cron": "0 8 * * *",
        "is_sub_workflow": false,
        "parent_workflow": null
      }
    ],
    
    "tasks": [
      {
        "code": "789",
        "name": "spark_transform",
        "workflow_code": "123",
        "task_type": "SPARK",
        "spark_main_class": "com.example.TransformJob",
        "params": {}
      }
    ],
    
    "tables": [
      {
        "full_name": "hive.db.target_table",
        "table_type": "HIVE"
      }
    ],
    
    "classes": [
      {
        "name": "com.example.TransformJob",
        "file_path": "/code_root/data_platform/src/main/java/com/example/TransformJob.java",
        "cross_project": false,
        "source_project": null,
        "tables_input": ["hive.db.source_table"],
        "tables_output": ["hive.db.target_table"]
      }
    ]
  },
  
  "edges": {
    "workflow_contains_task": [
      {"workflow": "123", "task": "789"}
    ],
    
    "workflow_depends_workflow": [
      {"from": "123", "to": "456"}
    ],
    
    "workflow_calls_subworkflow": [
      {"parent": "123", "child": "124"}
    ],
    
    "task_depends_task": [
      {"from": "789", "to": "790"}
    ],
    
    "task_produces_table": [
      {"task": "789", "table": "hive.db.target_table"}
    ],
    
    "task_consumes_table": [
      {"task": "789", "table": "hive.db.source_table"}
    ],
    
    "class_maps_to_task": [
      {"class": "com.example.TransformJob", "task": "789"}
    ]
  }
}
```

### 节点类型和关系类型

**节点类型**：

| 节点类型 | 属性 |
|----------|------|
| workflow | code, name, schedule_type, schedule_cron, is_sub_workflow, parent_workflow |
| task | code, name, workflow_code, task_type, spark_main_class, params |
| table | full_name, table_type |
| class | name, file_path, cross_project, source_project, tables_input, tables_output |

**关系类型**：

| 关系类型 | 说明 |
|----------|------|
| workflow_contains_task | 工作流包含节点 |
| workflow_depends_workflow | 工作流依赖上游工作流 |
| workflow_calls_subworkflow | 工作流调用子工作流 |
| task_depends_task | 节点依赖前节点 |
| task_produces_table | 节点产出表 |
| task_consumes_table | 节点消费表 |
| class_maps_to_task | 类名对应节点 |

---

## 索引文件结构

### 下游依赖索引

文件：`data/graph/{project_code}_index_downstream.json`

```json
{
  "generated_at": "2026-05-08T10:00:00",
  "workflow_downstream": {
    "123": {
      "direct": ["456", "457"],
      "all": ["456", "457", "458", "459"],
      "count": 4
    }
  },
  "task_downstream": {
    "789": {
      "direct": ["790", "791"],
      "all": ["790", "791", "792"],
      "count": 3
    }
  }
}
```

### 表消费索引

文件：`data/graph/{project_code}_index_table_consumer.json`

```json
{
  "generated_at": "2026-05-08T10:00:00",
  "table_consumers": {
    "hive.db.source_table": {
      "workflows": ["123", "456"],
      "tasks": ["789", "800"],
      "classes": ["com.example.TransformJob"]
    }
  },
  "table_producers": {
    "hive.db.target_table": {
      "workflows": ["123"],
      "tasks": ["789"],
      "classes": ["com.example.TransformJob"]
    }
  }
}
```

### 工作流节点索引

文件：`data/graph/{project_code}_index_workflow_nodes.json`

```json
{
  "generated_at": "2026-05-08T10:00:00",
  "workflow_tasks": {
    "123": {
      "tasks": ["789", "790", "791"],
      "task_names": {
        "789": "spark_transform",
        "790": "datax_sync",
        "791": "shell_check"
      },
      "task_types": {
        "789": "SPARK",
        "790": "DATAX",
        "791": "SHELL"
      },
      "spark_classes": {
        "789": "com.example.TransformJob"
      }
    }
  }
}
```

**索引用途**：

| 索引文件 | 加速的查询 |
|----------|------------|
| downstream | "工作流 X 下游有多少"、"节点 Y 的下游链路" |
| table_consumer | "表 T 被哪些工作流消费"、"修改表的影响范围" |
| workflow_nodes | "工作流 W 有哪些节点"、"节点 N 的类型和参数" |

---

## 扫描流程

### 流程步骤

```
1. 解析命令获取项目名称 → 定位代码根目录 /code_root/{project_name}/
2. 调用 DS API 获取项目下所有工作流定义
3. 解析工作流定义 → 提取工作流信息、节点信息、依赖关系
4. 提取 SPARK 节点的 --class 参数 → 得到主类名列表
5. 按类名搜索代码文件（见下方搜索策略）
6. 解析找到的文件 → 提取 SQL → 正则 + sqlparse
7. 建立 类名→输入表、类名→输出表 映射
8. 合成图谱节点和边 → 写入主图谱 JSON
9. 生成三个索引文件 → 写入索引 JSON
10. 返回扫描结果 → "扫描完成，工作流 50 个，节点 200 个，表 30 个"
```

### 代码文件搜索策略

**搜索优先级**：

```
第一优先：项目模块目录内搜索
/code_root/{project_name}/src/main/java/com/example/TransformJob.java
                    ↓ 找到 → 直接解析
                    ↓ 未找到
                    
第二优先：整个代码仓库按类名搜索
/code_root/**/com/example/TransformJob.java
                    ↓ 找到 → 解析并记录跨项目引用
                    ↓ 未找到
                    
记录为：类名存在但代码文件未找到（可能外部依赖）
```

**类名路径转换规则**：

| 类名格式 | 搜索路径模式 |
|----------|--------------|
| `com.example.Job` | `**/com/example/Job.java` |
| `com.example.Job` | `**/com/example/Job.scala` |
| `com.example.Job` | `**/com/example/Job.py` |
| `com.example.Job$Inner` | `**/com/example/Job.java` (Scala 内部类) |

### SQL 解析方式

**混合解析策略**：

1. **正则表达式快速提取**：
   - 匹配 `INSERT INTO/OVERWRITE TABLE xxx`
   - 匹配 `FROM xxx`、`JOIN xxx`
   - 快速返回初步结果

2. **sqlparse 处理复杂 SQL**：
   - 子查询、多层 JOIN、嵌套语句
   - 使用 Python sqlparse 库解析语法树
   - 提取完整表名链路

**按文件类型选择解析方式**：

| 文件类型 | 解析方式 |
|----------|----------|
| .java/.scala | 正则匹配 SQL 字符串 + sqlparse |
| .py | 正则匹配 SQL 字符串 |
| .sql | 直接 sqlparse 解析 |

---

## 查询能力

### 基础查询（直接读索引）

| 查询类型 | 实现方式 | 示例 |
|----------|----------|------|
| 工作流下游依赖 | 读 downstream 索引 | "工作流 123 下游有哪些" |
| 工作流上游依赖 | 读 downstream 索引反向遍历 | "工作流 456 上游有哪些" |
| 节点输入/输出表 | 读 workflow_nodes 索引 + 主图谱 | "节点 789 读写哪些表" |
| 节点前后依赖 | 读主图谱 task_depends_task 边 | "节点 789 的前节点是什么" |
| 表被谁消费 | 读 table_consumer 索引 | "表 source_table 被谁使用" |
| 工作流包含节点 | 读 workflow_nodes 索引 | "工作流 123 有哪些节点" |

### 深度查询（计算 + 索引辅助）

| 查询类型 | 实现方式 | 示例 |
|----------|----------|------|
| 路径分析 | NetworkX 图算法计算最短路径 | "从节点 A 到节点 B 的路径" |
| 影响链路可视化 | 生成 Mermaid 图代码 | "展示工作流 123 的下游链路图" |
| 跨项目血缘追溯 | 多项目图谱合并查询 | "表 T 跨项目的完整血缘链路" |

### 路径分析实现

```python
# 加载主图谱到 NetworkX
import networkx as nx

G = nx.DiGraph()
for edge in graph["edges"]["workflow_depends_workflow"]:
    G.add_edge(edge["from"], edge["to"])

# 查询最短路径
path = nx.shortest_path(G, source="123", target="459")
# 返回: ["123", "456", "458", "459"]
```

### 影响链路可视化实现

```python
def visualize_downstream(workflow_code, graph):
    downstream = graph["index_downstream"]["workflow_downstream"][workflow_code]["all"]
    edges = []
    deps = graph["edges"]["workflow_depends_workflow"]
    for e in deps:
        if e["to"] in downstream or e["from"] == workflow_code:
            edges.append(e)
    
    mermaid = "graph TD\n"
    for e in edges:
        mermaid += f"  {e['from']} --> {e['to']}\n"
    return mermaid
```

---

## 与现有系统集成

### 告警 Agent 集成

**集成流程**：

```
告警触发 → risk 节点需要评估影响范围
          ↓
        查询本地图谱（不实时调用 DS API）
          ↓
        读 downstream 索引 → 获取下游工作流数量
          ↓
        读 workflow_nodes 索引 → 获取节点信息
          ↓
        如果图谱不存在 → 降级处理，返回"图谱未扫描，无法评估影响"
          ↓
        返回风险评估结果
```

**风险评估修改点**：

| 现有逻辑 | 改为 |
|----------|------|
| 实时调用 DS API 获取依赖关系 | 查询本地图谱索引 |
| ImpactTool 分析下游任务 | 从图谱下游索引获取 |
| 无图谱时报错 | 降级返回提示信息 |

### Chat Agent 集成

**集成流程**：

```
用户命令 → parse_intent 解析意图
          ↓
        intent_type = "lineage_query" → 调用图谱查询
          ↓
        intent_type = "scan_graph" → 调用图谱扫描
          ↓
        query_lineage 节点 → 查询本地图谱
          ↓
        format_response → 格式化为钉钉消息
```

**新增对话意图**：

| intent_type | 示例命令 | 处理 |
|-------------|----------|------|
| scan_graph | "扫描项目 X 图谱" | 调用 Scanner 执行扫描 |
| lineage_query | "工作流 123 下游" | 调用 Querier 查询 |
| visualize_lineage | "展示 123 的影响链路" | 生成 Mermaid 图 |

### 钉钉回复格式

```markdown
### 工作流 123 血缘分析

**下游依赖**: 4 个工作流
- 456 (daily_summary)
- 457 (weekly_report)
- 458 (monthly_agg)
- 459 (archive)

**包含节点**: 3 个
- spark_transform (SPARK) → com.example.TransformJob
- datax_sync (DATAX)
- shell_check (SHELL)

**调度时间**: 每天 08:00

---
点击查看影响链路图
```

---

## 文件结构

**新增文件**：

```
src/graph/
├── __init__.py
├── scanner.py          # 图谱扫描器
├── querier.py          # 图谱查询器
├── indexer.py          # 索引生成器
├── storage.py          # JSON 存储管理
├── sql_parser.py       # SQL 解析（正则 + sqlparse）
├── code_searcher.py    # 代码文件搜索

data/graph/             # 图谱存储目录

tests/test_graph/
├── test_scanner.py
├── test_querier.py
├── test_indexer.py
├── test_sql_parser.py
├── test_code_searcher.py
```

**修改文件**：

```
src/tools/risk_assess.py    # 改为查询本地图谱
src/tools/impact.py         # 改为查询图谱索引
src/workflow/nodes/risk.py  # 集成图谱查询
src/agent/chat_agent.py     # 新增 scan_graph/lineage_query 意图
config/settings.py          # 新增 CODE_ROOT_PATH 配置
```

---

## 配置项

**新增配置**：

```python
# config/settings.py

CODE_ROOT_PATH = "/path/to/code_root"  # 总代码仓库根路径
GRAPH_STORAGE_PATH = "data/graph"      # 图谱存储路径
```

**代码仓库结构假设**：

```
/code_root/
├── data_platform/       # 项目模块目录
│   ├── src/main/java/
│   ├── src/main/scala/
│   └── sql/
├── other_project/
│   └── src/main/java/
└── ...
```

---

## 实现优先级

| Phase | 内容 | 产物 |
|-------|------|------|
| Phase 1 | 基础图谱服务 | Scanner + Storage + 主图谱 JSON |
| Phase 2 | 索引生成 | Indexer + 三个索引 JSON |
| Phase 3 | 查询服务 | Querier + 基础查询 |
| Phase 4 | 深度查询 | NetworkX 集成 + 路径分析 + Mermaid 可视化 |
| Phase 5 | 系统集成 | 告警 Agent 改造 + Chat Agent 新增意图 |

---

## 总结

**核心变化**：
- 告警时不再实时查询 DS API，改为查询本地图谱索引
- 用户手动触发扫描更新图谱
- 图谱包含：项目→工作流→节点→表→类名 的完整链路
- 索引加速常用查询，NetworkX 支持深度分析

**性能提升**：
- 告警风险评估无需实时 API 调用，响应更快
- 索引查询直接读取预计算结果，避免重复遍历
- 图谱生成一次，多次查询复用