# 知识图谱使用指南

## 快速开始

### 1. 扫描项目图谱

```bash
python -m src.cli.graph_cli scan --project 12345 --name data_platform
```

扫描完成后，图谱保存在 `data/graph/12345_graph.json`

### 2. 查询下游依赖

```bash
python -m src.cli.graph_cli downstream --project 12345 --workflow 100
```

### 3. 查询表消费者

```bash
python -m src.cli.graph_cli table --project 12345 --name hive.db.source_table
```

### 4. 生成可视化图

```bash
python -m src.cli.graph_cli visualize --project 12345 --workflow 100
```

输出 Mermaid 图代码，可在 Markdown 中渲染。

## 钉钉集成

用户通过钉钉发送消息：

| 命令 | 功能 |
|------|------|
| 扫描项目 X 图谱 | 扫描项目并生成图谱 |
| 工作流 Y 的下游 | 查询下游工作流 |
| 表 T 被谁消费 | 查询表消费者 |
| 展示 Y 的影响链路 | 生成 Mermaid 可视化 |

## 告警集成

告警 Agent 自动使用本地图谱评估影响范围：

- 无需实时调用 DS API
- 快速返回下游依赖数量
- 图谱不存在时降级处理