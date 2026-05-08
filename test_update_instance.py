"""测试修改工作流实例中的任务脚本"""
import sys
# 添加父目录以支持 src.xxx 导入
sys.path.insert(0, 'D:/Project/dolphinscheduler-cli/src')
sys.path.insert(0, 'D:/Project/dolphinscheduler-agent')

# 设置环境变量
import os
os.environ['DS_API_URL'] = 'http://ali-dolphin-test-01:12345/dolphinscheduler'
os.environ['DS_API_TOKEN'] = '771c3c883c17618846a5deae40f89d86'

from src.integrations.ds_cli import DSCLIClient

ds_cli = DSCLIClient()

# 测试修改工作流实例中的任务脚本
result = ds_cli.process_instance_update_task_script(
    project_code=11598158952448,
    process_instance_id=833841,
    task_code=21451298573345,
    script_changes={'ech': 'echo'},
)

print(f'success: {result.success}')
print(f'output: {result.output}')
print(f'error: {result.error}')
print(f'data: {result.data}')