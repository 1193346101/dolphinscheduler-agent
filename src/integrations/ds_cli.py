"""
DS CLI Client - DolphinScheduler API 调用

使用 dsctl generated versions ds_3_2_0 的 DS320Client 进行 API 调用
"""

import json
from dataclasses import dataclass
from typing import Optional
from collections import deque

from dsctl.generated.versions.ds_3_2_0.client import DS320Client
from dsctl.generated.versions.ds_3_2_0.api.operations.task_instance import QueryProcessTaskListPagingParams
from dsctl.generated.versions.ds_3_2_0.api.operations.executor import (
    ControlProcessInstanceParams,
    TriggerProcessDefinitionParams,
)
from dsctl.generated.versions.ds_3_2_0.api.operations.process_definition import (
    UpdateProcessDefinitionParams,
    ReleaseProcessDefinitionParams,
)
from dsctl.generated.versions.ds_3_2_0.api.operations.process_instance import (
    UpdateProcessInstanceParams,
)
from dsctl.generated.versions.ds_3_4_1.api.operations.logger import QueryLogGetLogDetailParams
from dsctl.generated.versions.ds_3_4_1.api.enums.execute_type import ExecuteType
from dsctl.generated.versions.ds_3_4_1.common.enums.failure_strategy import FailureStrategy
from dsctl.generated.versions.ds_3_4_1.common.enums.warning_type import WarningType

# DS 3.2.0 recover-failed 使用 START_FAILURE_TASK_PROCESS (code=3)
RECOVER_EXECUTE_TYPE = ExecuteType.START_FAILURE_TASK_PROCESS
from dsctl.generated.versions.ds_3_4_1.common.enums.release_state import ReleaseState

from ..config import settings


LOG_CHUNK_SIZE = 1000
MAX_LOG_CHUNKS = 20


@dataclass
class CLIResult:
    """CLI 执行结果"""
    success: bool
    output: str
    error: Optional[str] = None
    data: Optional[dict] = None


class DSCLIClient:
    """
    DolphinScheduler CLI 客户端

    使用 ds_3_2_0 DS320Client 进行 API 调用
    """

    def __init__(self):
        """初始化客户端"""
        self._client = DS320Client(
            base_url=settings.DS_API_URL,
            token=settings.DS_API_TOKEN,
        )

    def task_log(self, task_instance_id: int, lines: int = 200) -> CLIResult:
        """获取任务日志（分块读取）

        Args:
            task_instance_id: 任务实例 ID
            lines: 返回最后 N 行

        Returns:
            CLIResult 包含日志文本
        """
        try:
            all_lines: deque[str] = deque(maxlen=lines)
            skip_line_num = 0

            for _ in range(MAX_LOG_CHUNKS):
                params = QueryLogGetLogDetailParams(
                    taskInstanceId=task_instance_id,
                    skipLineNum=skip_line_num,
                    limit=LOG_CHUNK_SIZE,
                )
                chunk = self._client.logger.query_log_get_log_detail(params)

                chunk_lines = (chunk.message or "").splitlines()
                all_lines.extend(chunk_lines)

                if chunk.lineNum < LOG_CHUNK_SIZE:
                    break

                skip_line_num += chunk.lineNum

            text = "\n".join(all_lines)
            return CLIResult(
                success=True,
                output=text,
                data={"text": text, "lineCount": len(all_lines)},
            )
        except Exception as e:
            return CLIResult(
                success=False,
                output="",
                error=str(e),
            )

    def task_instance_list(self, process_instance_id: int) -> CLIResult:
        """列出工作流实例中的任务

        Args:
            process_instance_id: 工作流实例 ID (DS 3.2.0 使用 processInstanceId)

        Returns:
            CLIResult 包含任务列表
        """
        try:
            params = QueryProcessTaskListPagingParams(
                processInstanceId=process_instance_id,
                pageNo=1,
                pageSize=100,
            )
            result = self._client.task_instance.query_task_list_paging(1, params)

            data = {
                "totalList": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "taskCode": item.taskCode,
                        "taskType": item.taskType,
                        "state": item.state.value if item.state else None,
                        "endTime": item.endTime,
                        "host": item.host,
                        "logPath": item.logPath,
                        "taskParams": item.taskParams,
                    }
                    for item in result.totalList
                ],
                "total": result.total,
                "items": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "taskCode": item.taskCode,
                        "taskType": item.taskType,
                        "state": item.state.value if item.state else None,
                        "endTime": item.endTime,
                        "host": item.host,
                        "logPath": item.logPath,
                        "taskParams": item.taskParams,
                    }
                    for item in result.totalList
                ],
            }
            return CLIResult(
                success=True,
                output="",
                data=data,
            )
        except Exception as e:
            return CLIResult(
                success=False,
                output="",
                error=str(e),
            )

    def workflow_get(self, project_code: int, process_definition_code: int) -> CLIResult:
        """获取工作流定义详情

        Args:
            project_code: 项目代码
            process_definition_code: 工作流定义代码

        Returns:
            CLIResult 包含工作流定义数据
        """
        try:
            dag = self._client.process_definition.query_process_definition_by_code(
                project_code,
                process_definition_code,
            )

            # 转换为字典格式
            data = {
                "processDefinition": {
                    "code": dag.processDefinition.code if dag.processDefinition else None,
                    "name": dag.processDefinition.name if dag.processDefinition else None,
                    "version": dag.processDefinition.version if dag.processDefinition else None,
                    "releaseState": dag.processDefinition.releaseState.value if dag.processDefinition and dag.processDefinition.releaseState else None,
                },
                "processTaskRelationList": [
                    {
                        "preTaskCode": rel.preTaskCode,
                        "postTaskCode": rel.postTaskCode,
                    }
                    for rel in (dag.processTaskRelationList or [])
                ],
                "taskDefinitionList": [
                    {
                        "code": task.code,
                        "name": task.name,
                        "taskType": task.taskType,
                        "taskParams": task.taskParams,
                    }
                    for task in (dag.taskDefinitionList or [])
                ],
            }
            return CLIResult(
                success=True,
                output="",
                data=data,
            )
        except Exception as e:
            return CLIResult(
                success=False,
                output="",
                error=str(e),
            )

    def workflow_update_task_script(
        self,
        project_code: int,
        process_definition_code: int,
        task_code: int,
        script_changes: dict,
    ) -> CLIResult:
        """更新工作流定义中的任务脚本

        Args:
            project_code: 项目代码
            process_definition_code: 工作流定义代码
            task_code: 任务代码
            script_changes: 脚本修改映射 {"错误拼写": "正确拼写"}

        Returns:
            CLIResult 包含更新结果
        """
        try:
            # 1. 获取当前工作流定义
            dag = self._client.process_definition.query_process_definition_by_code(
                project_code,
                process_definition_code,
            )

            # 2. 修改目标任务的脚本
            task_definitions = dag.taskDefinitionList or []
            modified_tasks = []

            for task in task_definitions:
                task_dict = {
                    "code": task.code,
                    "name": task.name,
                    "taskType": task.taskType,
                    "taskParams": task.taskParams,
                    "description": task.description,
                    "flag": task.flag,
                    "taskPriority": task.taskPriority,
                    "workerGroup": task.workerGroup,
                    "environmentCode": task.environmentCode,
                    "timeout": task.timeout,
                    "delayTime": task.delayTime,
                    "failRetryTimes": task.failRetryTimes,
                    "failRetryInterval": task.failRetryInterval,
                    "cpuQuota": task.cpuQuota,
                    "memoryMax": task.memoryMax,
                }

                # 如果是目标任务，修改脚本
                if task.code == task_code:
                    task_params_str = task.taskParams or "{}"
                    try:
                        task_params = json.loads(task_params_str)
                    except json.JSONDecodeError:
                        task_params = {}

                    raw_script = task_params.get("rawScript", "")
                    new_script = raw_script
                    for wrong, correct in script_changes.items():
                        new_script = new_script.replace(wrong, correct)

                    if new_script != raw_script:
                        task_params["rawScript"] = new_script
                        task_dict["taskParams"] = json.dumps(task_params)

                modified_tasks.append(task_dict)

            # 3. 构建 taskRelationJson
            task_relations = dag.processTaskRelationList or []
            relation_list = [
                {
                    "preTaskCode": rel.preTaskCode,
                    "postTaskCode": rel.postTaskCode,
                }
                for rel in task_relations
            ]

            # 4. 更新工作流定义
            update_params = UpdateProcessDefinitionParams(
                name=dag.processDefinition.name if dag.processDefinition else "",
                description=dag.processDefinition.description if dag.processDefinition else None,
                globalParams=dag.processDefinition.globalParams if dag.processDefinition else None,
                locations=dag.processDefinition.locations if dag.processDefinition else None,
                timeout=dag.processDefinition.timeout if dag.processDefinition else 0,
                taskRelationJson=json.dumps(relation_list),
                taskDefinitionJson=json.dumps(modified_tasks),
            )

            self._client.process_definition.update_process_definition(
                project_code,
                process_definition_code,
                update_params,
            )

            # 5. 重新上线工作流
            release_params = ReleaseProcessDefinitionParams(
                releaseState=ReleaseState.ONLINE,
            )
            self._client.process_definition.release_process_definition(
                project_code,
                process_definition_code,
                release_params,
            )

            return CLIResult(
                success=True,
                output="workflow updated",
                data={
                    "status": "success",
                    "changes": script_changes,
                    "task_code": task_code,
                },
            )
        except Exception as e:
            return CLIResult(
                success=False,
                output="",
                error=str(e),
            )

    def workflow_recover(self, project_code: int, process_instance_id: int) -> CLIResult:
        """恢复失败的工作流

        注意：recover-failed 会使用实例创建时的任务定义版本，
        如果任务定义已更新，建议使用 workflow_run 启动新实例。

        Args:
            project_code: 项目代码
            process_instance_id: 工作流实例 ID

        Returns:
            CLIResult 包含恢复结果
        """
        try:
            params = ControlProcessInstanceParams(
                processInstanceId=process_instance_id,
                executeType=RECOVER_EXECUTE_TYPE,
            )
            self._client.executor.control_process_instance(project_code, params)

            return CLIResult(
                success=True,
                output="recover requested",
                data={"status": "success"},
            )
        except Exception as e:
            return CLIResult(
                success=False,
                output="",
                error=str(e),
            )

    def workflow_run(self, project_code: int, process_definition_code: int) -> CLIResult:
        """启动新的工作流实例

        使用最新版本的任务定义启动新实例。

        注意：如果下游工作流依赖 process_instance_id 关联，
        启动新实例会改变 ID，可能导致关联丢失。
        这种情况下建议使用 process_instance_update_task_script。

        Args:
            project_code: 项目代码
            process_definition_code: 工作流定义代码

        Returns:
            CLIResult 包含新实例信息
        """
        try:
            # DS 3.2.0 使用 trigger_process_definition 启动工作流
            params = TriggerProcessDefinitionParams(
                processDefinitionCode=process_definition_code,
                scheduleTime="",  # 空字符串表示立即执行
                failureStrategy=FailureStrategy.CONTINUE,
                warningType=WarningType.NONE,
            )
            result = self._client.executor.trigger_process_definition(project_code, params)

            # result 是 list[int]，第一个元素是 process instance code
            instance_code = result[0] if result else None

            return CLIResult(
                success=True,
                output="workflow started",
                data={
                    "status": "success",
                    "process_instance_code": instance_code,
                },
            )
        except Exception as e:
            return CLIResult(
                success=False,
                output="",
                error=str(e),
            )

    def process_instance_update_task_script(
        self,
        project_code: int,
        process_instance_id: int,
        task_code: int,
        script_changes: dict,
    ) -> CLIResult:
        """修改工作流实例中的任务脚本并恢复失败

        直接修改工作流实例中的任务定义，然后恢复失败任务。
        这样可以保持 process_instance_id 不变，下游依赖不受影响。

        Args:
            project_code: 项目代码
            process_instance_id: 工作流实例 ID
            task_code: 任务代码
            script_changes: 脚本修改映射 {"错误拼写": "正确拼写"}

        Returns:
            CLIResult 包含修改和恢复结果
        """
        try:
            import requests

            headers = {"token": self._client.token}

            # 1. 获取工作流实例的 dagData
            url = f"{self._client.base_url}/projects/{project_code}/process-instances/{process_instance_id}"
            resp = requests.get(url, headers=headers)
            data = resp.json().get("data", {})
            dag_data = data.get("dagData", {})

            if not dag_data:
                return CLIResult(
                    success=False,
                    output="",
                    error="工作流实例缺少 dagData",
                )

            # 2. 获取任务定义列表和关系列表
            task_defs = dag_data.get("taskDefinitionList", [])
            task_relations = dag_data.get("processTaskRelationList", [])
            process_def = dag_data.get("processDefinition", {})

            # 3. 修改目标任务的脚本
            modified_tasks = []
            for task in task_defs:
                # 复制完整的任务定义
                task_dict = {}
                for key in ["code", "name", "version", "description", "taskType", "taskParams",
                            "flag", "taskPriority", "workerGroup", "environmentCode",
                            "failRetryTimes", "failRetryInterval", "timeout", "delayTime",
                            "cpuQuota", "memoryMax", "taskExecuteType", "taskGroupId",
                            "taskGroupPriority", "isCache"]:
                    if key in task:
                        task_dict[key] = task[key]

                # 如果是目标任务，修改脚本
                if task.get("code") == task_code:
                    task_params_obj = task.get("taskParams", {})
                    if isinstance(task_params_obj, dict):
                        task_params = task_params_obj.copy()
                    else:
                        task_params_str = task_params_obj if isinstance(task_params_obj, str) else "{}"
                        try:
                            task_params = json.loads(task_params_str)
                        except json.JSONDecodeError:
                            task_params = {}

                    raw_script = task_params.get("rawScript", "")
                    new_script = raw_script
                    for wrong, correct in script_changes.items():
                        new_script = new_script.replace(wrong, correct)

                    if new_script != raw_script:
                        task_params["rawScript"] = new_script
                        task_dict["taskParams"] = task_params

                modified_tasks.append(task_dict)

            # 4. 构建完整的请求参数（模拟 dsctl workflow-instance edit）
            relation_list = [
                {
                    "name": rel.get("name"),
                    "preTaskCode": rel.get("preTaskCode"),
                    "preTaskVersion": rel.get("preTaskVersion", 0),
                    "postTaskCode": rel.get("postTaskCode"),
                    "postTaskVersion": rel.get("postTaskVersion", 0),
                    "conditionType": rel.get("conditionType", "NONE"),
                    "conditionParams": rel.get("conditionParams", {}),
                }
                for rel in task_relations
            ]

            # 获取其他必要参数
            global_params = process_def.get("globalParams", "[]")
            locations = process_def.get("locations", "[]")
            timeout = process_def.get("timeout", 0)

            # 5. 更新工作流实例
            update_url = f"{self._client.base_url}/projects/{project_code}/process-instances/{process_instance_id}"
            update_data = {
                "taskRelationJson": json.dumps(relation_list),
                "taskDefinitionJson": json.dumps(modified_tasks),
                "globalParams": global_params,
                "locations": locations,
                "timeout": timeout,
                "syncDefine": False,
            }
            update_resp = requests.put(update_url, headers=headers, data=update_data)
            update_result = update_resp.json()

            if update_result.get("code", 0) != 0:
                return CLIResult(
                    success=False,
                    output="",
                    error=f"更新失败: {update_result.get('msg', 'unknown error')}",
                )

            # 6. 恢复失败任务
            recover_params = ControlProcessInstanceParams(
                processInstanceId=process_instance_id,
                executeType=RECOVER_EXECUTE_TYPE,
            )
            self._client.executor.control_process_instance(project_code, recover_params)

            return CLIResult(
                success=True,
                output="task script updated and recover requested",
                data={
                    "status": "success",
                    "changes": script_changes,
                    "task_code": task_code,
                    "process_instance_id": process_instance_id,
                },
            )
        except Exception as e:
            return CLIResult(
                success=False,
                output="",
                error=str(e),
            )


__all__ = ["DSCLIClient", "CLIResult"]