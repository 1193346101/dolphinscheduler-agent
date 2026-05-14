"""
fetch_logs node

Get Spark task logs - using dsctl CLI + Spark History + YARN

日志获取顺序：
1. dsctl Driver Logs (完整日志，包含配置、执行、失败信息)
2. Spark History Event Log (提取配置、错误事件)
3. YARN Application Info (状态、诊断信息)

DS 3.2.0 使用 download-log API 返回完整日志，不再截取。
Agent端通过 preprocess_log.py 智能提取关键信息。
"""

import json
from typing import Dict
from ..state import AgentState
from ...tools.spark_hist import SparkHistTool
from ...tools.yarn_log import YARNLogTool
from ...tools.k8s_log import K8sLogTool
from ...integrations.dsctl_wrapper import DSCLIClient


def fetch_logs(state: AgentState) -> AgentState:
    """
    Get logs - dsctl download-log API 返回完整日志

    日志内容包含：
    - 任务配置（driverMemory, executorMemory等）
    - 执行过程（Application report轮询）
    - 失败信息（exitStatusCode, process has exited, FINALIZE_SESSION）
    """
    print("\n" + "="*50)
    print("[3/10] fetch_logs - Fetch logs")
    print("="*50)

    project_config = state.get("project_config")

    if not project_config:
        print("[FAIL] No project config, skip log fetch")
        return {
            **state,
            "driver_logs": None,
            "spark_logs": None,
            "yarn_logs": None,
            "k8s_logs": None,
            "log_fetch_error": "No project config",
        }

    task_type = state.get("task_type", "UNKNOWN")
    print(f"  >> Task type: {task_type}")

    # 1. Use dsctl CLI to get driver logs (complete log via download-log API)
    driver_logs = None
    log_fetch_error = None

    print("  >> Trying to get Driver logs...")
    try:
        dsctl = DSCLIClient()

        # Prefer taskInstanceId
        task_instance_id = state["alert_raw"].get("taskInstanceId")

        # If no taskInstanceId, parse from logPath
        if not task_instance_id:
            log_path = state["alert_raw"].get("logPath")
            if log_path:
                import os
                filename = os.path.basename(log_path)
                if filename.endswith(".log"):
                    task_instance_id = filename[:-4]
                    try:
                        task_instance_id = int(task_instance_id)
                        print(f"  >> Parsed taskInstanceId from logPath: {task_instance_id}")
                    except ValueError:
                        print(f"  [WARN] logPath filename not numeric: {filename}")
                        task_instance_id = None

        if task_instance_id:
            # dsctl download-log API returns complete log
            result = dsctl.get_task_logs(task_instance_id)
            if result.success:
                driver_logs = result.stdout
                print(f"  >> Driver log length: {len(driver_logs) if driver_logs else 0} chars")
            else:
                log_fetch_error = f"dsctl log fetch failed: {result.stderr}"
                print(f"  [WARN] {log_fetch_error}")
        else:
            print("  [WARN] Cannot get taskInstanceId, skip log fetch")
    except Exception as e:
        log_fetch_error = f"dsctl exception: {str(e)}"
        print(f"  [WARN] {log_fetch_error}")

    # 2. Get Spark History logs (only for Spark tasks)
    spark_logs = None
    app_id = None
    spark_config = project_config.get("spark_log", {})
    spark_history_url = spark_config.get("history_url", "")

    if task_type == "SPARK" and spark_history_url and driver_logs:
        print("  >> Trying to get Spark History logs...")
        try:
            spark_tool = SparkHistTool(history_url=spark_history_url)
            app_id = spark_tool.extract_app_id(driver_logs)

            if app_id:
                print(f"  >> Found Spark app_id: {app_id}")
                spark_logs_dict = spark_tool.fetch_logs(app_id)

                if spark_logs_dict and spark_logs_dict.get("event_log"):
                    event_log = spark_logs_dict.get("event_log", "")

                    # 构建分析用的日志摘要
                    spark_logs = _extract_spark_summary(event_log, spark_logs_dict)
                    print(f"  >> Spark History log extracted: {len(spark_logs)} chars")

                    # 提取错误事件用于分析
                    errors = spark_tool.extract_errors_from_event_log(event_log)
                    if errors:
                        print(f"  >> Found {len(errors)} error events in Spark History")
                        spark_logs += f"\n[SPARK ERRORS]\n"
                        for err in errors[:10]:
                            spark_logs += f"  Stage {err.get('stage_id', 'N/A')}: {err.get('reason', 'N/A')[:150]}\n"
        except Exception as e:
            print(f"  [WARN] Spark History exception: {str(e)}")
            if not log_fetch_error:
                log_fetch_error = f"Spark History exception: {str(e)}"

    # 3. Get YARN logs (only for Spark tasks)
    yarn_logs = None
    yarn_gateway_url = spark_config.get("yarn_gateway_url", "")
    yarn_username = spark_config.get("yarn_username", "")
    yarn_password = spark_config.get("yarn_password", "")

    if task_type == "SPARK" and yarn_gateway_url and app_id:
        print("  >> Trying to get YARN logs...")
        try:
            yarn_tool = YARNLogTool(
                gateway_url=yarn_gateway_url,
                username=yarn_username,
                password=yarn_password
            )
            yarn_logs_dict = yarn_tool.fetch_logs(app_id)

            if yarn_logs_dict and not yarn_logs_dict.get("error"):
                yarn_logs = _extract_yarn_summary(yarn_logs_dict)
                print(f"  >> YARN log extracted: {len(yarn_logs)} chars")

                # 如果 YARN 有诊断信息（错误），添加到日志
                diagnostics = yarn_logs_dict.get("diagnostics", "")
                if diagnostics and "failed" in diagnostics.lower() or "killed" in diagnostics.lower():
                    print(f"  >> YARN diagnostics contains error info")
            else:
                print(f"  [WARN] YARN fetch failed: {yarn_logs_dict.get('error', 'unknown')}")
        except Exception as e:
            print(f"  [WARN] YARN exception: {str(e)}")
            if not log_fetch_error:
                log_fetch_error = f"YARN exception: {str(e)}"

    print("[OK] Log fetch complete")
    return {
        **state,
        "driver_logs": driver_logs,
        "spark_logs": spark_logs,
        "yarn_logs": yarn_logs,
        "k8s_logs": None,
        "log_fetch_error": log_fetch_error,
    }


def _extract_spark_summary(event_log: str, spark_logs_dict: Dict) -> str:
    """
    从 Spark History event log 提取关键信息摘要

    包括：
    - Spark 配置（内存、cores、shuffle partitions）
    - Executor 信息
    - Stage/Job 统计
    """
    summary = f"=== Spark History Summary ===\n"
    summary += f"Application: {spark_logs_dict.get('app_name', 'N/A')}\n"
    summary += f"Event Log Size: {spark_logs_dict.get('event_log_size', 0)} bytes\n\n"

    # 提取 Spark 配置
    for line in event_log.splitlines()[:100]:
        try:
            event = json.loads(line)
            if event.get('Event') == 'SparkListenerEnvironmentUpdate':
                spark_props = event.get('Spark Properties', {})
                summary += "[Spark Configuration]\n"
                for key in ['spark.driver.memory', 'spark.executor.memory',
                            'spark.executor.instances', 'spark.executor.cores',
                            'spark.sql.shuffle.partitions', 'spark.memory.offHeap.enabled']:
                    if key in spark_props:
                        summary += f"  {key}: {spark_props[key]}\n"
                break
        except json.JSONDecodeError:
            pass

    # 统计执行信息
    job_count = 0
    stage_count = 0
    task_count = 0
    failed_tasks = 0

    for line in event_log.splitlines():
        try:
            event = json.loads(line)
            event_type = event.get('Event', '')

            if event_type == 'SparkListenerJobStart':
                job_count += 1
            elif event_type == 'SparkListenerStageSubmitted':
                stage_count += 1
            elif event_type == 'SparkListenerTaskEnd':
                task_count += 1
                reason = event.get('Task End Reason', {})
                if reason.get('Failure'):
                    failed_tasks += 1
        except json.JSONDecodeError:
            pass

    summary += f"\n[Execution Stats]\n"
    summary += f"  Jobs: {job_count}, Stages: {stage_count}, Tasks: {task_count}\n"
    summary += f"  Failed Tasks: {failed_tasks}\n"

    return summary


def _extract_yarn_summary(yarn_logs_dict: Dict) -> str:
    """
    从 YARN 应用信息提取关键信息摘要

    包括：
    - 应用状态
    - 执行时长
    - 资源分配
    - 诊断信息（错误原因）
    """
    summary = f"=== YARN Application Summary ===\n"
    summary += f"Application: {yarn_logs_dict.get('app_name', 'N/A')}\n"
    summary += f"App ID: {yarn_logs_dict.get('app_id', 'N/A')}\n"
    summary += f"State: {yarn_logs_dict.get('state', 'N/A')}/{yarn_logs_dict.get('final_status', 'N/A')}\n"
    summary += f"User: {yarn_logs_dict.get('user', 'N/A')}\n"

    elapsed_time = yarn_logs_dict.get('elapsed_time', 0)
    if elapsed_time:
        summary += f"Duration: {elapsed_time} ms ({elapsed_time/1000:.1f} seconds)\n"

    # 资源信息
    memory_mb = yarn_logs_dict.get('allocated_memory_mb', 0)
    vcores = yarn_logs_dict.get('allocated_vcores', 0)
    if memory_mb > 0:
        summary += f"Allocated Memory: {memory_mb} MB\n"
    if vcores > 0:
        summary += f"Allocated VCores: {vcores}\n"

    # 诊断信息（重要：错误原因）
    diagnostics = yarn_logs_dict.get('diagnostics', '')
    if diagnostics:
        summary += f"\n[YARN Diagnostics]\n"
        summary += diagnostics[:1000]  # 限制长度，但保留足够信息

    return summary


__all__ = ["fetch_logs"]