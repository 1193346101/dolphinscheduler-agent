"""
模拟告警测试数据

用于测试 DolphinScheduler Agent 的完整告警处理流程
"""

# 模拟 Spark 任务 OOM 告警
SPARK_OOM_ALERT = {
    "alerts": """[
        {
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "processId": 123456789,
            "taskCode": 987654321,
            "taskType": "SPARK",
            "taskState": "FAILURE",
            "taskName": "spark_data_processing",
            "processName": "数据处理工作流",
            "projectName": "数据平台",
            "taskEndTime": "2026-05-08 15:30:00",
            "workerGroup": "default",
            "taskHost": "worker-01"
        }
    ]"""
}

# 模拟子工作流任务失败告警
SUBWORKFLOW_ALERT = {
    "alerts": """[
        {
            "projectCode": 11598158952448,
            "processDefinitionCode": 12345678901234,  # 子工作流 B 的编码
            "processId": 98765432109876,  # 子工作流实例 ID
            "taskCode": 111111111,  # 子工作流中失败的任务编码
            "taskType": "SHELL",
            "taskState": "FAILURE",
            "taskName": "task_d_in_subworkflow",
            "processName": "子工作流B",
            "projectName": "数据平台",
            "taskEndTime": "2026-05-08 15:30:00",
            "workerGroup": "default",
            "taskHost": "worker-01",
            "rootProcessInstanceId": 12345678901234,  # 主工作流实例 ID
            "parentProcessInstanceId": 12345678901234  # 父工作流实例 ID
        }
    ]"""
}

# 模拟 Shell 任务脚本错误告警
SHELL_SCRIPT_ERROR_ALERT = {
    "alerts": """[
        {
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "processId": 123456789,
            "taskCode": 987654321,
            "taskType": "SHELL",
            "taskState": "FAILURE",
            "taskName": "shell_data_export",
            "processName": "数据导出工作流",
            "projectName": "数据平台",
            "taskEndTime": "2026-05-08 15:30:00",
            "workerGroup": "default",
            "taskHost": "worker-01"
        }
    ]"""
}

# 模拟 Python 任务告警
PYTHON_ERROR_ALERT = {
    "alerts": """[
        {
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "processId": 123456789,
            "taskCode": 987654321,
            "taskType": "PYTHON",
            "taskState": "FAILURE",
            "taskName": "python_analysis",
            "processName": "数据分析工作流",
            "projectName": "数据平台",
            "taskEndTime": "2026-05-08 15:30:00",
            "workerGroup": "default",
            "taskHost": "worker-01"
        }
    ]"""
}

# 模拟 DataX 任务告警
DATAX_ERROR_ALERT = {
    "alerts": """[
        {
            "projectCode": 11598158952448,
            "processDefinitionCode": 21451302002208,
            "processId": 123456789,
            "taskCode": 987654321,
            "taskType": "DATAX",
            "taskState": "FAILURE",
            "taskName": "datax_sync",
            "processName": "数据同步工作流",
            "projectName": "数据平台",
            "taskEndTime": "2026-05-08 15:30:00",
            "workerGroup": "default",
            "taskHost": "worker-01"
        }
    ]"""
}