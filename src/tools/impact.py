"""
ImpactTool - 下游影响分析工具
"""

from typing import Dict, List, Set


class ImpactTool:
    """下游影响分析工具"""

    def analyze_downstream(self, task_relations: List[Dict], task_code: str) -> Dict:
        """分析下游任务"""
        downstream = self._find_downstream_tasks(task_relations, task_code)
        downstream_count = len(downstream)
        impact_summary = self._build_impact_summary(task_code, downstream, downstream_count)

        return {
            "downstream_tasks": downstream_count,
            "downstream_list": downstream,
            "impact_summary": impact_summary,
        }

    def _find_downstream_tasks(self, task_relations: List[Dict], task_code: str) -> List[str]:
        """查找所有下游依赖任务"""
        downstream: Set[str] = set()
        to_process = [task_code]

        while to_process:
            current = to_process.pop()
            for rel in task_relations:
                pre_code = str(rel.get("preTaskCode", 0))
                post_code = str(rel.get("postTaskCode", 0))

                if pre_code == current and post_code not in downstream:
                    downstream.add(post_code)
                    to_process.append(post_code)

        return list(downstream)

    def _build_impact_summary(self, task_code: str, downstream: List[str], count: int) -> str:
        """构建影响摘要"""
        if count == 0:
            return f"任务 {task_code} 没有下游依赖"

        lines = [f"任务 {task_code} 影响 {count} 个下游任务:"]
        for task in downstream[:10]:
            lines.append(f"- {task}")

        if count > 10:
            lines.append(f"... 以及另外 {count - 10} 个")

        return "\n".join(lines)


__all__ = ["ImpactTool"]