"""
工作流血缘关系可视化服务

功能:
1. 扫描所有项目生成血缘数据 (可选)
2. 生成前端可视化数据文件
3. 启动本地HTTP服务器
4. 通过ngrok暴露外网访问

页面:
- index.html: 工作流血缘关系查询
- implicit_index.html: 隐式依赖分析

使用方法:
    python lineage_server.py                    # 启动服务(默认端口8889)
    python lineage_server.py --port 9999        # 指定端口
    python lineage_server.py --scan             # 先扫描再启动
    python lineage_server.py --implicit         # 扫描隐式依赖
    python lineage_server.py --ngrok            # 启动ngrok外网访问
    python lineage_server.py --scan --ngrok     # 扫描+ngrok
"""

import os
import sys
import json
import argparse
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

# 默认配置
DEFAULT_PORT = 8889
GRAPH_DIR = "data/graph"


def setup_environment():
    """设置环境变量"""
    os.environ['DS_API_URL'] = 'http://47.102.148.252:12345/dolphinscheduler'
    os.environ['DS_API_TOKEN'] = '80dd955473212947fa6bb2dda326a53b'
    os.environ['DS_VERSION'] = '3.2.0'


def scan_all_projects():
    """扫描所有项目生成血缘数据"""
    print("=" * 60)
    print("Step 1: 扫描所有项目工作流血缘")
    print("=" * 60)

    base_dir = Path(__file__).parent
    sys.path.insert(0, str(base_dir))

    setup_environment()

    try:
        import src.integrations.dsctl_wrapper as dsctl_wrapper
        import src.graph.scanner as scanner_module
        import src.graph.storage as storage_module
        import src.config.projects as projects_module

        DSCLIClient = dsctl_wrapper.DSCLIClient
        GraphScanner = scanner_module.GraphScanner
        GraphStorage = storage_module.GraphStorage
        projects_registry = projects_module.projects_registry

        storage = GraphStorage()
        scanner = GraphScanner(storage=storage, code_root="")

        all_projects = projects_registry.all_projects()
        print(f"项目总数: {len(all_projects)}")

        results = []
        for project in all_projects:
            project_name = project.name
            project_code = str(project.code)

            print(f"\n扫描: {project_name} ({project_code})")

            try:
                result = scanner.scan_project(
                    project_code=project_code,
                    project_name=project_name,
                    ds_api_url=os.environ['DS_API_URL'],
                    ds_api_token=os.environ['DS_API_TOKEN'],
                )
                workflows = result.get('workflows_count', 0)
                tasks = result.get('tasks_count', 0)
                tables = result.get('tables_count', 0)
                print(f"  ✓ 工作流: {workflows}, 任务: {tasks}, 表: {tables}")
                results.append({"name": project_name, "code": project_code, "success": True})
            except Exception as e:
                print(f"  ✗ 失败: {e}")
                results.append({"name": project_name, "code": project_code, "success": False})

        success = sum(1 for r in results if r['success'])
        print(f"\n扫描完成: 成功 {success}/{len(results)}")
        return True

    except Exception as e:
        print(f"扫描失败: {e}")
        return False


def generate_graph_data():
    """生成前端可视化数据文件"""
    print("\n" + "=" * 60)
    print("Step 2: 生成可视化数据文件")
    print("=" * 60)

    base_dir = Path(__file__).parent
    sys.path.insert(0, str(base_dir))

    graph_dir = base_dir / GRAPH_DIR

    try:
        import src.config.projects as projects_module
        projects_registry = projects_module.projects_registry
        all_projects = projects_registry.all_projects()

        results = []
        for project in all_projects:
            project_name = project.name
            project_code = str(project.code)

            graph_file = graph_dir / f"{project_code}_graph.json"
            if not graph_file.exists():
                continue

            print(f"处理: {project_name}")

            with open(graph_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            nodes = data.get("nodes", {})
            edges = data.get("edges", {})

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

            # 创建项目目录（按项目名称）
            project_dir = graph_dir / project_name
            project_dir.mkdir(exist_ok=True)

            # 写入JS文件（与 HTML index.html 保持一致）
            js_content = f"const graphData = {json.dumps(graph_data, ensure_ascii=False)};"
            js_file = project_dir / "graph_data.js"
            with open(js_file, "w", encoding="utf-8") as f:
                f.write(js_content)

            workflows = len(graph_data["nodes"]["workflows"])
            tasks = len(graph_data["nodes"]["tasks"])
            tables = len(graph_data["nodes"]["tables"])

            results.append({
                "name": project_name,
                "code": project_code,
                "dir": project_name,  # 按项目名称分目录
                "workflows": workflows,
                "tasks": tasks,
                "tables": tables,
            })

        # 生成项目列表索引
        index_content = f"const projectList = {json.dumps(results, ensure_ascii=False)};"
        index_file = graph_dir / "project_list.js"
        with open(index_file, "w", encoding="utf-8") as f:
            f.write(index_content)

        total_wf = sum(r["workflows"] for r in results)
        total_tasks = sum(r["tasks"] for r in results)
        total_tables = sum(r["tables"] for r in results)

        print(f"\n生成完成: {len(results)}个项目")
        print(f"总计: {total_wf}工作流, {total_tasks}任务, {total_tables}表")
        return True

    except Exception as e:
        print(f"生成失败: {e}")
        return False


def check_ngrok():
    """检查ngrok是否已安装"""
    try:
        result = subprocess.run(["ngrok", "version"], capture_output=True, text=True)
        return True
    except FileNotFoundError:
        return False


def update_env_file(public_url: str):
    """将 ngrok 公网地址写入 .env 文件"""
    base_dir = Path(__file__).parent
    env_file = base_dir / ".env"

    # 读取现有 .env 内容
    env_lines = []
    env_vars = {}

    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            env_lines = f.readlines()
            for line in env_lines:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    env_vars[key] = value

    # 更新公网地址变量
    env_vars["LINEAGE_PUBLIC_URL"] = f"{public_url}/index.html"
    env_vars["IMPLICIT_DEPENDENCY_PUBLIC_URL"] = f"{public_url}/implicit_index.html"
    env_vars["NGROK_PUBLIC_URL"] = public_url

    # 重建 .env 文件内容
    new_lines = []
    for line in env_lines:
        if "=" in line and not line.startswith("#"):
            key = line.strip().split("=", 1)[0]
            if key in env_vars:
                new_lines.append(f"{key}={env_vars[key]}\n")
                del env_vars[key]
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # 添加新变量（如果不在原有内容中）
    for key, value in env_vars.items():
        new_lines.append(f"{key}={value}\n")

    # 写回 .env 文件
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"[OK] 已更新 .env 文件:")
    print(f"  LINEAGE_PUBLIC_URL={public_url}/index.html")
    print(f"  IMPLICIT_DEPENDENCY_PUBLIC_URL={public_url}/implicit_index.html")


def start_ngrok(port):
    """启动ngrok隧道"""
    print(f"\n启动ngrok隧道 (端口: {port})...")

    if not check_ngrok():
        print("错误: ngrok未安装")
        print("下载地址: https://ngrok.com/download")
        return None

    try:
        # 启动ngrok
        process = subprocess.Popen(
            ["ngrok", "http", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # 等待ngrok启动
        time.sleep(3)

        # 获取ngrok API地址
        try:
            import urllib.request
            response = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels")
            tunnels_data = json.loads(response.read().decode())

            if tunnels_data.get("tunnels"):
                public_url = tunnels_data["tunnels"][0]["public_url"]
                print(f"[OK] ngrok已启动")
                print(f"  公网地址: {public_url}")

                # 自动写入 .env 文件
                update_env_file(public_url)

                return public_url
        except Exception as e:
            print(f"获取ngrok地址失败: {e}")

        return "http://待获取.ngrok.io"

    except Exception as e:
        print(f"启动ngrok失败: {e}")
        return None


def start_http_server(port, graph_dir):
    """启动HTTP服务器"""
    print(f"\n启动HTTP服务器 (端口: {port})...")
    print(f"目录: {graph_dir}")

    os.chdir(graph_dir)

    # 使用Python内置HTTP服务器
    subprocess.run([sys.executable, "-m", "http.server", str(port)])


def scan_implicit_dependencies():
    """扫描所有项目的隐式依赖"""
    print("\n" + "=" * 60)
    print("扫描隐式依赖关系")
    print("=" * 60)

    base_dir = Path(__file__).parent
    sys.path.insert(0, str(base_dir))

    try:
        import src.config.projects as projects_module
        from src.tools.implicit_dependency_analyzer import analyze_implicit_dependency

        projects_registry = projects_module.projects_registry
        all_projects = projects_registry.all_projects()

        graph_dir = base_dir / GRAPH_DIR
        results = []

        for project in all_projects:
            project_name = project.name
            print(f"\n分析: {project_name}")

            try:
                result = analyze_implicit_dependency(project_name, str(graph_dir))
                if result.total_workflows > 0:
                    print(f"  ✓ 工作流: {result.total_workflows}, 主调度: {len(result.main_workflows)}, 独立: {len(result.independent_workflows)}")
                    results.append({"name": project_name, "success": True})
                else:
                    print(f"  ✗ 分析失败")
                    results.append({"name": project_name, "success": False})
            except Exception as e:
                print(f"  ✗ 失败: {e}")
                results.append({"name": project_name, "success": False})

        success = sum(1 for r in results if r['success'])
        print(f"\n隐式依赖扫描完成: 成功 {success}/{len(results)}")
        return True

    except Exception as e:
        print(f"扫描失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="工作流血缘关系可视化服务")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="HTTP服务器端口")
    parser.add_argument("--scan", action="store_true", help="扫描所有项目血缘数据")
    parser.add_argument("--implicit", action="store_true", help="扫描隐式依赖关系")
    parser.add_argument("--ngrok", action="store_true", help="启动ngrok外网访问")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")

    args = parser.parse_args()

    base_dir = Path(__file__).parent
    graph_dir = base_dir / GRAPH_DIR

    print("=" * 60)
    print("DolphinScheduler 工作流血缘关系服务")
    print("=" * 60)

    # Step 1: 扫描血缘(可选)
    if args.scan:
        scan_all_projects()
        generate_graph_data()

    # Step 2: 扫描隐式依赖(可选)
    if args.implicit:
        scan_implicit_dependencies()

    # 检查页面文件是否存在
    index_html = graph_dir / "index.html"
    implicit_html = graph_dir / "implicit_index.html"

    pages = []
    if index_html.exists():
        pages.append(("血缘关系", "index.html"))
    if implicit_html.exists():
        pages.append(("隐式依赖", "implicit_index.html"))

    if not pages:
        print("\n警告: 无页面文件")
        print("请使用 --scan 扫描血缘数据，或 --implicit 扫描隐式依赖")
        return

    # Step 3: ngrok(可选)
    public_url = None
    if args.ngrok:
        public_url = start_ngrok(args.port)
        if public_url:
            print(f"\n外网访问地址:")
            for name, file in pages:
                print(f"  {name}: {public_url}/{file}")

    # 本地访问地址
    print(f"\n本地访问地址:")
    for name, file in pages:
        print(f"  {name}: http://localhost:{args.port}/{file}")

    # 自动打开浏览器
    main_page = "implicit_index.html" if args.implicit else "index.html"
    local_url = f"http://localhost:{args.port}/{main_page}"

    if not args.no_browser:
        print("\n正在打开浏览器...")
        webbrowser.open(local_url)

    print("\n" + "=" * 60)
    print("服务器已启动，按 Ctrl+C 停止")
    print("=" * 60)

    # 启动HTTP服务器
    try:
        start_http_server(args.port, graph_dir)
    except KeyboardInterrupt:
        print("\n服务器已停止")


if __name__ == "__main__":
    main()