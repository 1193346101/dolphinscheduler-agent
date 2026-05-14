"""
Re-scan ad_monitor project and validate lineage

Steps:
1. Run scan with improved scanner (jar-based project extraction)
2. Validate lineage against DS API
3. Compare with previous validation results
"""

import sys
import os

project_root = "D:/Project/dolphinscheduler-agent"
sys.path.insert(0, project_root)

from src.graph import GraphScanner, GraphStorage, GraphIndexer
from src.graph.lineage_validator import LineageValidator
from src.config import settings
from src.integrations import project_resolver

def main():
    project_name = "ad_monitor"

    # Resolve project code
    project_code, resolved_name = project_resolver.resolve(project_name)

    if not project_code:
        print(f"[ERROR] Cannot find project: {project_name}")
        return

    print("=" * 70)
    print(f"Re-scanning project: {project_name} (code: {project_code})")
    print("=" * 70)

    # Code root
    code_root = os.getenv("CODE_ROOT", "D:/Project/spark-etl")
    print(f"Code root: {code_root}")

    # Initialize
    storage = GraphStorage()
    scanner = GraphScanner(storage=storage, code_root=code_root)

    # Run scan
    print("\n[Step 1] Running graph scan...")
    try:
        scan_result = scanner.scan_project(
            project_code=str(project_code),
            project_name=resolved_name or project_name,
            ds_api_url=settings.DS_API_URL,
            ds_api_token=settings.DS_API_TOKEN,
        )

        print(f"  Workflows: {scan_result['workflows_count']}")
        print(f"  Tasks: {scan_result['tasks_count']}")
        print(f"  Tables: {scan_result['tables_count']}")

    except Exception as e:
        print(f"[ERROR] Scan failed: {e}")
        return

    # Generate indexes
    print("\n[Step 2] Generating indexes...")
    indexer = GraphIndexer(storage)
    indexer.generate_all_indexes(str(project_code))

    # Count classes
    graph_data = storage.load_graph(str(project_code))
    classes_count = 0
    produces_count = 0
    consumes_count = 0

    if graph_data:
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", {})
        classes_count = len(nodes.get("classes", []))
        produces_count = len(edges.get("task_produces_table", []))
        consumes_count = len(edges.get("task_consumes_table", []))

    print(f"  Classes: {classes_count}")
    print(f"  Produces edges: {produces_count}")
    print(f"  Consumes edges: {consumes_count}")

    # Validate lineage
    print("\n[Step 3] Validating lineage...")
    validator = LineageValidator()
    validation_result = validator.validate_project(str(project_code))

    print(f"\nValidation Summary:")
    print(f"  Workflow match rate: {validation_result['accuracy_metrics']['workflow_match_rate']}")
    print(f"  Task match rate: {validation_result['accuracy_metrics']['task_match_rate']}")
    print(f"  Classes: {validation_result['accuracy_metrics']['class_count']}")
    print(f"  Produces edges: {validation_result['accuracy_metrics']['produces_edge_count']}")
    print(f"  Consumes edges: {validation_result['accuracy_metrics']['consumes_edge_count']}")

    # Issues
    issues = validation_result.get("issues", [])
    high_count = sum(1 for i in issues if i["severity"] == "HIGH")
    medium_count = sum(1 for i in issues if i["severity"] == "MEDIUM")

    print(f"\nIssues: {high_count} HIGH, {medium_count} MEDIUM")

    # Compare with previous
    print("\n" + "=" * 70)
    print("Comparison with previous scan:")
    print("=" * 70)

    prev_class_count = 0
    prev_produces = 0
    prev_consumes = 73

    print(f"  Classes: {prev_class_count} -> {classes_count}")
    print(f"  Produces edges: {prev_produces} -> {produces_count}")
    print(f"  Consumes edges: {prev_consumes} -> {consumes_count}")

    if classes_count > prev_class_count:
        print("\n[SUCCESS] Class-task mapping improved!")

    if produces_count > prev_produces:
        print("[SUCCESS] Output table detection improved!")


if __name__ == "__main__":
    main()