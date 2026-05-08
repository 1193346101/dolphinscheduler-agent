#!/usr/bin/env python
"""
知识图谱使用示例

演示如何使用知识图谱 API 进行查询和扫描
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.graph.storage import GraphStorage
from src.graph.scanner import GraphScanner
from src.graph.indexer import GraphIndexer
from src.graph.querier import GraphQuerier
from src.graph.mermaid_generator import MermaidGenerator
from src.graph.networkx_analyzer import NetworkXAnalyzer
from src.config import settings


def demo_scan():
    """演示扫描图谱"""
    print("=" * 50)
    print("示例 1: 扫描项目图谱")
    print("=" * 50)

    # 初始化存储
    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)

    # 初始化扫描器
    scanner = GraphScanner(
        storage=storage,
        code_root=settings.CODE_ROOT_PATH
    )

    # 扫描项目 (示例值，实际使用时需要替换)
    project_code = "12345"
    project_name = "data_platform"

    print(f"\n扫描项目: {project_name} (code: {project_code})")

    # 执行扫描
    result = scanner.scan_project(
        project_code=project_code,
        project_name=project_name,
        ds_api_url=settings.DS_API_URL,
        ds_api_token=settings.DS_API_TOKEN
    )

    print(f"\n扫描结果:")
    print(f"  工作流数量: {result['workflows_count']}")
    print(f"  任务数量: {result['tasks_count']}")
    print(f"  表数量: {result['tables_count']}")
    print(f"  类数量: {result['classes_count']}")

    # 生成索引
    print("\n生成查询索引...")
    indexer = GraphIndexer(storage=storage)
    indexer.generate_all_indexes(project_code)

    print("索引生成完成")


def demo_query():
    """演示查询图谱"""
    print("\n" + "=" * 50)
    print("示例 2: 查询下游依赖")
    print("=" * 50)

    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    querier = GraphQuerier(storage)

    project_code = "12345"
    workflow_code = "100"

    print(f"\n查询工作流 {workflow_code} 的下游依赖...")

    result = querier.query_workflow_downstream(project_code, workflow_code)

    if result['found']:
        print(f"\n下游依赖: {result['count']} 个工作流")
        print(f"直接下游: {result['direct']}")
        print(f"全部下游: {result['all']}")
    else:
        print(f"\n查询失败: {result['message']}")


def demo_table_query():
    """演示查询表消费者"""
    print("\n" + "=" * 50)
    print("示例 3: 查询表消费者")
    print("=" * 50)

    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    querier = GraphQuerier(storage)

    project_code = "12345"
    table_name = "hive.db.source_table"

    print(f"\n查询表 {table_name} 的消费者...")

    result = querier.query_table_consumers(project_code, table_name)

    if result['found']:
        print(f"\n消费工作流: {len(result['workflows'])} 个")
        for wf in result['workflows'][:5]:
            print(f"  - {wf}")
        print(f"\n消费任务: {len(result['tasks'])} 个")
        for task in result['tasks'][:5]:
            print(f"  - {task}")
    else:
        print(f"\n查询失败: {result['message']}")


def demo_visualize():
    """演示可视化"""
    print("\n" + "=" * 50)
    print("示例 4: 生成 Mermaid 可视化图")
    print("=" * 50)

    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    generator = MermaidGenerator(storage)

    project_code = "12345"
    workflow_code = "100"

    print(f"\n生成工作流 {workflow_code} 的下游依赖图...")

    mermaid = generator.generate_downstream_graph(project_code, workflow_code)

    print("\nMermaid 图代码:")
    print(mermaid)
    print("\n可在支持 Mermaid 的 Markdown 编辑器中渲染此图")


def demo_path_analysis():
    """演示路径分析"""
    print("\n" + "=" * 50)
    print("示例 5: NetworkX 路径分析")
    print("=" * 50)

    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    analyzer = NetworkXAnalyzer(storage)

    project_code = "12345"
    source = "100"
    target = "300"

    print(f"\n查找从 {source} 到 {target} 的最短路径...")

    path = analyzer.find_shortest_path(project_code, source, target)

    if path:
        print(f"\n最短路径: {path}")

        # 生成路径图
        generator = MermaidGenerator(storage)
        graph = storage.load_graph(project_code)

        workflow_names = {}
        if graph:
            for wf in graph.get('nodes', {}).get('workflows', []):
                workflow_names[wf['code']] = wf['name']

        mermaid = generator.generate_path_graph(path, workflow_names)
        print("\n路径可视化:")
        print(mermaid)
    else:
        print(f"\n无路径或图谱不存在")


def demo_list():
    """演示列出图谱"""
    print("\n" + "=" * 50)
    print("示例 6: 列出已扫描的图谱")
    print("=" * 50)

    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)

    import os
    graph_dir = storage.data_dir

    print(f"\n图谱存储目录: {graph_dir}")

    if os.path.exists(graph_dir):
        graphs = []
        for f in os.listdir(graph_dir):
            if f.endswith('_graph.json'):
                project_code = f.replace('_graph.json', '')
                graph = storage.load_graph(project_code)
                if graph:
                    graphs.append({
                        'code': project_code,
                        'name': graph.get('project_name', 'N/A'),
                        'scanned_at': graph.get('scanned_at', 'N/A'),
                        'workflows': len(graph.get('nodes', {}).get('workflows', [])),
                        'tasks': len(graph.get('nodes', {}).get('tasks', [])),
                    })

        if graphs:
            print(f"\n已扫描图谱: {len(graphs)} 个")
            for g in graphs:
                print(f"  {g['code']}: {g['name']}")
                print(f"    扫描时间: {g['scanned_at']}")
                print(f"    工作流: {g['workflows']}, 任务: {g['tasks']}")
        else:
            print("\n无已扫描图谱")
    else:
        print("\n图谱目录不存在")


def main():
    """主函数"""
    print("知识图谱使用示例")
    print("=" * 50)

    # 检查配置
    print("\n检查配置...")
    print(f"  CODE_ROOT_PATH: {settings.CODE_ROOT_PATH}")
    print(f"  GRAPH_STORAGE_PATH: {settings.GRAPH_STORAGE_PATH}")
    print(f"  DS_API_URL: {settings.DS_API_URL}")

    if not settings.DS_API_URL:
        print("\n警告: DS_API_URL 未配置，部分示例无法运行")
        print("请在 .env 文件中配置 DolphinScheduler API 地址")

    # 运行示例
    # 注意: 这些示例需要实际的配置和图谱数据才能正常运行

    print("\n可用示例:")
    print("  1. demo_scan() - 扫描项目图谱")
    print("  2. demo_query() - 查询下游依赖")
    print("  3. demo_table_query() - 查询表消费者")
    print("  4. demo_visualize() - 生成可视化图")
    print("  5. demo_path_analysis() - 路径分析")
    print("  6. demo_list() - 列出已扫描图谱")

    print("\n运行示例: python scripts/demo_knowledge_graph.py")


if __name__ == '__main__':
    main()