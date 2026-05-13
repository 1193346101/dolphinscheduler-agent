"""
为所有项目生成单独的 graph_data.js 文件
使用项目编码作为目录名，避免中文编码问题
"""

import os
import sys
import json

# 设置导入路径
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base_dir)

# 导入项目配置
import src.config.projects as projects_module

def generate_all_project_graph_js():
    graph_dir = os.path.join(base_dir, "data", "graph")

    # 从配置文件获取所有项目
    projects_registry = projects_module.projects_registry
    all_projects = projects_registry.all_projects()

    print(f"项目总数: {len(all_projects)}")

    results = []

    for project in all_projects:
        project_name = project.name
        project_code = str(project.code)

        # 使用项目编码作为目录名（避免中文编码问题）
        safe_dir_name = project_code

        graph_file = os.path.join(graph_dir, f"{project_code}_graph.json")

        if not os.path.exists(graph_file):
            print(f"Skip: {project_name} - graph file not found")
            continue

        print(f"Processing: {project_name} ({project_code})")

        # 创建项目目录
        project_dir = os.path.join(graph_dir, safe_dir_name)
        if not os.path.exists(project_dir):
            os.makedirs(project_dir)
            print(f"  Created directory: {safe_dir_name}")

        with open(graph_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes = data.get("nodes", {})
        edges = data.get("edges", {})

        # 构建图谱数据
        graph_data = {
            "project_code": project_code,
            "project_name": project_name,
            "nodes": {
                "workflows": nodes.get("workflows", []),
                "tasks": nodes.get("tasks", []),
                "tables": nodes.get("tables", []),
                "classes": nodes.get("classes", []),
            },
            "edges": {
                "workflow_contains_task": edges.get("workflow_contains_task", []),
                "task_depends_task": edges.get("task_depends_task", []),
                "workflow_calls_subworkflow": edges.get("workflow_calls_subworkflow", []),
                "workflow_depends_workflow": edges.get("workflow_depends_workflow", []),
                "task_consumes_table": edges.get("task_consumes_table", []),
                "task_produces_table": edges.get("task_produces_table", []),
                "class_maps_to_task": edges.get("class_maps_to_task", []),
            },
        }

        # 写入 JS 文件（使用统一的变量名 graphData）
        js_content = f"window.graphData = {json.dumps(graph_data, ensure_ascii=False)};"

        js_file = os.path.join(project_dir, "graph_data.js")
        with open(js_file, "w", encoding="utf-8") as f:
            f.write(js_content)

        workflows = graph_data["nodes"]["workflows"]
        tasks = graph_data["nodes"]["tasks"]
        tables = graph_data["nodes"]["tables"]

        print(f"  Workflows: {len(workflows)}, Tasks: {len(tasks)}, Tables: {len(tables)}")

        results.append({
            "name": project_name,
            "code": project_code,
            "dir": safe_dir_name,
            "workflows": len(workflows),
            "tasks": len(tasks),
            "tables": len(tables),
        })

    # 生成项目列表索引文件
    index_content = f"const projectList = {json.dumps(results, ensure_ascii=False)};"
    index_file = os.path.join(graph_dir, "project_list.js")
    with open(index_file, "w", encoding="utf-8") as f:
        f.write(index_content)

    print(f"\n生成完成!")
    print(f"项目数: {len(results)}")
    print(f"索引文件: {index_file}")

    # 打印汇总
    total_workflows = sum(r["workflows"] for r in results)
    total_tasks = sum(r["tasks"] for r in results)
    total_tables = sum(r["tables"] for r in results)
    print(f"总计: {total_workflows} workflows, {total_tasks} tasks, {total_tables} tables")


if __name__ == "__main__":
    generate_all_project_graph_js()