"""
导入测试 - 验证所有模块是否正确导入
"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 设置 PYTHONPATH 使相对导入正常工作
os.environ['PYTHONPATH'] = os.path.join(project_root, 'src')

def test_imports():
    """测试所有模块导入"""
    print("Testing imports...")
    errors = []

    # 测试 models 模块 (独立模块，无外部依赖)
    try:
        # 直接导入 models 模块
        models_path = os.path.join(project_root, 'src', 'models')
        sys.path.insert(0, models_path)

        from alert import AlertInfo, AlertContext
        from risk import RiskLevel, AutoFixAction
        from analysis import ErrorAnalysis
        print("[OK] models")
        sys.path.pop(0)
    except Exception as e:
        errors.append(f"models: {e}")
        print(f"[FAIL] models: {e}")

    # 测试 config 模块
    try:
        config_path = os.path.join(project_root, 'src', 'config')
        sys.path.insert(0, config_path)
        from settings import Settings, settings
        print("[OK] config.settings")
        sys.path.pop(0)
    except Exception as e:
        errors.append(f"config.settings: {e}")
        print(f"[FAIL] config.settings: {e}")

    # 测试 skills 模块 (使用绝对导入)
    try:
        # 添加 src 目录
        src_path = os.path.join(project_root, 'src')
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

        # 临时修改导入方式
        import importlib.util

        # 加载 base skill
        base_spec = importlib.util.spec_from_file_location("base", os.path.join(src_path, "skills", "base.py"))
        base_module = importlib.util.module_from_spec(base_spec)
        sys.modules['skills.base'] = base_module
        base_spec.loader.exec_module(base_module)

        # 加载 spark skill
        spark_spec = importlib.util.spec_from_file_location("spark_skill", os.path.join(src_path, "skills", "spark_skill.py"))
        spark_module = importlib.util.module_from_spec(spark_spec)
        sys.modules['skills.spark_skill'] = spark_module
        spark_spec.loader.exec_module(spark_module)

        print("[OK] skills (partial)")
    except Exception as e:
        errors.append(f"skills: {e}")
        print(f"[FAIL] skills: {e}")

    # 测试 integrations
    try:
        src_path = os.path.join(project_root, 'src')
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

        import importlib.util
        dingtalk_spec = importlib.util.spec_from_file_location("dingtalk", os.path.join(src_path, "integrations", "dingtalk.py"))
        dingtalk_module = importlib.util.module_from_spec(dingtalk_spec)
        dingtalk_spec.loader.exec_module(dingtalk_module)
        print("[OK] integrations.dingtalk")
    except Exception as e:
        errors.append(f"integrations: {e}")
        print(f"[FAIL] integrations: {e}")

    print()
    print("=" * 50)
    if errors:
        print(f"Import failed: {len(errors)} errors")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("All modules imported successfully!")
        return True


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)