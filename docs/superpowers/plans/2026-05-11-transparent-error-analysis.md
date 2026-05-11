# 透明化错误分析报告实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除置信度字段，添加透明化错误分析报告字段，让用户理解错误分析的完整推理过程

**Architecture:** 
- ErrorAnalysis 数据类新增 `original_log_error`, `analysis_process`, `reasoning` 三个字段
- spark_skill.py 在构建 ErrorAnalysis 时填充这些字段，利用 build_fix.py 的 message/source 信息
- analyze.py 更新通知格式，展示透明化分析报告而非置信度

**Tech Stack:** Python dataclasses, DolphinScheduler Agent

---

## 文件结构

**修改文件:**
- `src/models/analysis.py` - ErrorAnalysis 数据类定义
- `src/skills/spark_skill.py` - 构建 ErrorAnalysis，填充新字段
- `src/workflow/nodes/analyze.py` - 通知格式，展示分析报告

---

### Task 1: 更新 ErrorAnalysis 数据类

**Files:**
- Modify: `src/models/analysis.py:22-49`

- [ ] **Step 1: 删除 confidence 字段，添加透明化分析报告字段**

```python
@dataclass
class ErrorAnalysis:
    """错误分析结果"""

    # 错误类型标识
    error_type: str                      # oom_executor, syntax_error, command_not_found...

    # 分析类别（核心）
    category: ErrorCategory              # AUTO_FIXABLE / KNOWN_NEEDS_LLM / UNKNOWN

    # 错误消息片段
    error_message: str                   # 日志片段（用于 LLM 分析）

    # 匹配的模式（调试用）
    matched_pattern: Optional[str] = None

    # 快速修复方案（仅 AUTO_FIXABLE 有）
    quick_fix: Optional[Dict] = None     # {"action_type": "modify_script", "script_changes": {"ech": "echo"}}

    # 给 LLM 的提示（仅 KNOWN_NEEDS_LLM 有）
    llm_hint: Optional[str] = None       # 如 "语法错误，请定位具体位置和原因"

    # === 透明化分析报告 ===
    # 原始日志错误信息（从 error_blocks 中提取的关键片段）
    original_log_error: Optional[str] = None

    # 分析过程说明（如何识别出错误类型）
    analysis_process: Optional[str] = None

    # 建议理由（为什么给出这样的修复建议）
    reasoning: Optional[str] = None

    # 任务类型特有信息
    spark_app_id: Optional[str] = None
    executor_count: Optional[int] = None
```

- [ ] **Step 2: 运行测试验证修改**

Run: `pytest tests/models/test_analysis.py -v`
Expected: PASS (或测试文件不存在时无报错)

- [ ] **Step 3: Commit**

```bash
git add src/models/analysis.py
git commit -m "refactor: 移除 confidence 字段，添加透明化分析报告字段"
```

---

### Task 2: 更新 spark_skill.py 填充新字段

**Files:**
- Modify: `src/skills/spark_skill.py:371-467`

- [ ] **Step 1: 在 analyze() 方法中构建透明化报告字段**

```python
# 原始日志错误（第一个 error_block）
original_log_error = error_blocks[0] if error_blocks else error_text[:300]

# 分析过程说明
analysis_process_parts = []
if preprocessed.get("config_lines"):
    analysis_process_parts.append(f"提取配置项 {len(preprocessed['config_lines'])} 条")
if error_blocks:
    analysis_process_parts.append(f"提取错误块 {len(error_blocks)} 个")
if app_info.get("app_id"):
    analysis_process_parts.append(f"识别 AppId: {app_info['app_id']}")
if match_result.get("matched_pattern"):
    analysis_process_parts.append(f"匹配模式: {match_result['matched_pattern']}")

analysis_process = "，".join(analysis_process_parts) if analysis_process_parts else "通过错误模式库匹配"

# 建议理由
reasoning = ""
if category == ErrorCategory.AUTO_FIXABLE:
    if fix_result:
        reasoning = fix_result.get("message", "")
        source = fix_result.get("source", "default")
        if source == "historical":
            reasoning += "（基于历史成功配置）"
        elif source == "limited":
            reasoning += "（受集群资源限制调整）"
    else:
        reasoning = "根据错误模式匹配结果，提供标准修复方案"
elif category == ErrorCategory.KNOWN_NEEDS_LLM:
    reasoning = match_result.get("extra", "") or "已知错误类型，需进一步分析具体原因"
else:
    reasoning = "未知错误类型，建议人工分析或查阅相关文档"
```

- [ ] **Step 2: 更新 ErrorAnalysis 构建（删除 confidence，添加新字段）**

```python
return ErrorAnalysis(
    error_type=match_result["error_type"],
    category=category,
    error_message=match_result.get("error_message", error_text[:500]),
    matched_pattern=match_result.get("matched_pattern", ""),
    llm_hint=match_result.get("extra", "") if category == ErrorCategory.KNOWN_NEEDS_LLM else "",
    quick_fix=quick_fix,
    # 新增透明化字段
    original_log_error=original_log_error,
    analysis_process=analysis_process,
    reasoning=reasoning,
    spark_app_id=app_info.get("app_id"),
    data_metrics=data_metrics,
)
```

- [ ] **Step 3: 同步更新 _legacy_analyze 方法**

```python
original_log_error = self._extract_error_message(log_content, pattern)
analysis_process = f"通过内置模式库匹配: {error_type}"
reasoning = "根据错误模式匹配结果，提供标准修复方案"

# AUTO_FIXABLE 返回
return ErrorAnalysis(
    error_type=error_type,
    category=ErrorCategory.AUTO_FIXABLE,
    error_message=error_message,
    matched_pattern=pattern,
    quick_fix=quick_fix,
    original_log_error=original_log_error,
    analysis_process=analysis_process,
    reasoning=reasoning,
    spark_app_id=self._extract_app_id(log_content),
)

# KNOWN_NEEDS_LLM 返回
return ErrorAnalysis(
    error_type=error_type,
    category=ErrorCategory.KNOWN_NEEDS_LLM,
    error_message=error_message,
    matched_pattern=pattern,
    llm_hint=llm_hint,
    original_log_error=original_log_error,
    analysis_process=analysis_process,
    reasoning=llm_hint or "已知错误类型，需进一步分析具体原因",
    spark_app_id=self._extract_app_id(log_content),
)

# UNKNOWN 返回
return ErrorAnalysis(
    error_type="unknown",
    category=ErrorCategory.UNKNOWN,
    error_message=log_content[:500],
    original_log_error=log_content[:300],
    analysis_process="无匹配错误模式",
    reasoning="未知错误类型，建议人工分析或查阅相关文档",
)
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/skills/test_spark_skill.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/skills/spark_skill.py
git commit -m "feat: spark_skill 填充透明化分析报告字段"
```

---

### Task 3: 更新 analyze.py 通知格式

**Files:**
- Modify: `src/workflow/nodes/analyze.py:246-310`

- [ ] **Step 1: 删除置信度显示，替换为透明化报告**

```python
# 删除第 290 行的置信度显示
# notification_text += f"**分析置信度:** {confidence_score:.2%}\n\n"

# 替换为透明化报告
if analysis_process:
    notification_text += f"**分析过程:**\n> {analysis_process}\n\n"

if reasoning:
    notification_text += f"**建议理由:**\n> {reasoning}\n\n"
```

- [ ] **Step 2: 更新原始日志错误显示**

```python
# 优先使用 skill_result 的 original_log_error
if skill_result and hasattr(skill_result, 'original_log_error') and skill_result.original_log_error:
    display_log = skill_result.original_log_error[:500]
    notification_text += f"**原始日志错误信息:**\n```\n{display_log}\n```\n\n"
elif log_error_lines:
    notification_text += f"**日志错误信息:**\n```\n{log_error_lines[:500]}\n```\n\n"
```

- [ ] **Step 3: 运行测试**

Run: `pytest tests/workflow/test_analyze.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/workflow/nodes/analyze.py
git commit -m "refactor: 通知格式展示透明化分析报告而非置信度"
```

---

### Task 4: 更新其他 Skill 类

**Files:**
- Modify: `src/skills/shell_skill.py`
- Modify: `src/skills/python_skill.py`
- Modify: `src/skills/datax_skill.py`

- [ ] **Step 1: 更新 shell_skill.py 的 ErrorAnalysis 构建**

添加新字段填充（删除 confidence）。

- [ ] **Step 2: Commit shell_skill**

```bash
git add src/skills/shell_skill.py
git commit -m "feat: shell_skill 填充透明化分析报告字段"
```

- [ ] **Step 3: 更新 python_skill.py 的 ErrorAnalysis 构建**

添加新字段填充（删除 confidence）。

- [ ] **Step 4: Commit python_skill**

```bash
git add src/skills/python_skill.py
git commit -m "feat: python_skill 填充透明化分析报告字段"
```

- [ ] **Step 5: 更新 datax_skill.py 的 ErrorAnalysis 构建**

添加新字段填充（删除 confidence）。

- [ ] **Step 6: Commit datax_skill**

```bash
git add src/skills/datax_skill.py
git commit -m "feat: datax_skill 填充透明化分析报告字段"
```

---

## 验证

运行完整测试套件:

```bash
pytest tests/ -v --tb=short
```

### 预期通知效果

```
## 🔍 错误分析结果

**错误类型:** `oom_executor`
**错误类别:** AUTO_FIXABLE

**分析过程:**
> 提取配置项 15 条，提取错误块 2 个，匹配模式: OutOfMemoryError

**原始日志错误信息:**
```
java.lang.OutOfMemoryError: Java heap space
...
```

**建议理由:**
> Increased executor memory to resolve OOM
```

---

## 实现完成后

推送更改:

```bash
git push origin main
```