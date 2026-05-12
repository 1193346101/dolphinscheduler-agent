"""
测试告警 JSON 识别逻辑
"""

from src.integrations.dingtalk_stream import is_alert_json


def test_alert_json():
    """测试告警 JSON 识别"""

    # 测试用例
    test_cases = [
        # 告警 JSON 格式（应该返回 True）
        ('{"alerts": "[{\"projectCode\":123, \"taskInstanceId\":456}]"}', True),
        ('{"projectCode": 11598178397184, "processDefinitionCode": 123, "taskInstanceId": 836917, "taskType": "SPARK"}', True),
        ('[{"projectCode": 123, "taskInstanceId": 456}]', True),

        # 对话消息格式（应该返回 False）
        ('ad_monitor 下今天有哪些工作流实例', False),
        ('查询工作流状态', False),
        ('{"message": "hello"}', False),
        ('普通文本消息', False),
    ]

    print("=" * 60)
    print("告警 JSON 识别测试")
    print("=" * 60)

    all_passed = True
    for content, expected in test_cases:
        result = is_alert_json(content)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        if result != expected:
            all_passed = False

        print(f"\n{status}")
        print(f"  内容: {content[:50]}...")
        print(f"  预期: {expected}, 实际: {result}")

    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过 ✅")
    else:
        print("部分测试失败 ❌")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    test_alert_json()