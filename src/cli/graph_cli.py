"""
Graph CLI - 图谱命令行工具
"""

import argparse
import json
import sys
from ..graph.storage import GraphStorage
from ..graph.scanner import GraphScanner
from ..graph.indexer import GraphIndexer
from ..graph.querier import GraphQuerier
from ..graph.mermaid_generator import MermaidGenerator
from ..config import settings


def cmd_scan(args):
    """扫描图谱"""
    scanner = GraphScanner(
        storage=GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH),
        code_root=settings.CODE_ROOT_PATH
    )

    result = scanner.scan_project(
        project_code=args.project,
        project_name=args.name,
        ds_api_url=settings.DS_API_URL,
        ds_api_token=settings.DS_API_TOKEN
    )

    # 生成索引
    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    indexer = GraphIndexer(storage=storage)
    indexer.generate_all_indexes(args.project)

    print(f"扫描完成:")
    print(f"  工作流: {result['workflows_count']}")
    print(f"  任务: {result['tasks_count']}")
    print(f"  表: {result['tables_count']}")


def cmd_downstream(args):
    """查询下游"""
    querier = GraphQuerier(GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH))
    result = querier.query_workflow_downstream(args.project, args.workflow)

    if result['found']:
        print(f"下游依赖: {result['count']} 个")
        for wf in result['all']:
            print(f"  - {wf}")
    else:
        print(f"未找到: {result['message']}")


def cmd_table(args):
    """查询表"""
    querier = GraphQuerier(GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH))

    if args.type == 'consumers':
        result = querier.query_table_consumers(args.project, args.name)
    else:
        result = querier.query_table_producers(args.project, args.name)

    if result['found']:
        print(f"工作流: {len(result['workflows'])} 个")
        for wf in result['workflows']:
            print(f"  - {wf}")
        print(f"任务: {len(result['tasks'])} 个")
        for task in result['tasks']:
            print(f"  - {task}")
    else:
        print(f"未找到: {result['message']}")


def cmd_visualize(args):
    """生成可视化"""
    generator = MermaidGenerator(GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH))
    mermaid = generator.generate_downstream_graph(args.project, args.workflow)
    print(mermaid)


def cmd_list(args):
    """列出图谱"""
    import os
    storage = GraphStorage(data_dir=settings.GRAPH_STORAGE_PATH)
    graph_dir = storage.data_dir

    if os.path.exists(graph_dir):
        for f in os.listdir(graph_dir):
            if f.endswith('_graph.json'):
                project_code = f.replace('_graph.json', '')
                graph = storage.load_graph(project_code)
                if graph:
                    print(f"{project_code}: {graph.get('project_name', 'N/A')} ({graph.get('scanned_at', 'N/A')})")
    else:
        print("无图谱")


def main():
    parser = argparse.ArgumentParser(description='知识图谱 CLI')
    subparsers = parser.add_subparsers(dest='command')

    # scan
    scan_parser = subparsers.add_parser('scan', help='扫描图谱')
    scan_parser.add_argument('--project', required=True, help='项目代码')
    scan_parser.add_argument('--name', required=True, help='项目名称')

    # downstream
    downstream_parser = subparsers.add_parser('downstream', help='查询下游')
    downstream_parser.add_argument('--project', required=True)
    downstream_parser.add_argument('--workflow', required=True)

    # table
    table_parser = subparsers.add_parser('table', help='查询表')
    table_parser.add_argument('--project', required=True)
    table_parser.add_argument('--name', required=True)
    table_parser.add_argument('--type', choices=['consumers', 'producers'], default='consumers')

    # visualize
    visualize_parser = subparsers.add_parser('visualize', help='可视化')
    visualize_parser.add_argument('--project', required=True)
    visualize_parser.add_argument('--workflow', required=True)

    # list
    list_parser = subparsers.add_parser('list', help='列出图谱')

    args = parser.parse_args()

    if args.command == 'scan':
        cmd_scan(args)
    elif args.command == 'downstream':
        cmd_downstream(args)
    elif args.command == 'table':
        cmd_table(args)
    elif args.command == 'visualize':
        cmd_visualize(args)
    elif args.command == 'list':
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()