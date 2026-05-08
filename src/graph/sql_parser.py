"""
SQL Parser - 解析 SQL 语句提取表名

使用正则表达式从 SQL 语句中提取输入输出表
"""

import re
from typing import Dict, List


class SQLParser:
    """SQL 解析器，提取表名"""

    # 正则表达式模式
    INSERT_PATTERN = r'INSERT\s+(?:INTO|OVERWRITE)\s+(?:TABLE\s+)?(\S+)'
    FROM_PATTERN = r'FROM\s+(\S+)'
    JOIN_PATTERN = r'JOIN\s+(\S+)(?:\s+\w+)?\s+ON'

    # SQL 关键字（用于从代码文件中识别 SQL 字符串）
    SQL_KEYWORDS = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE']

    def __init__(self):
        """初始化编译正则表达式"""
        self._insert_re = re.compile(self.INSERT_PATTERN, re.IGNORECASE)
        self._from_re = re.compile(self.FROM_PATTERN, re.IGNORECASE)
        self._join_re = re.compile(self.JOIN_PATTERN, re.IGNORECASE)

    def extract_tables(self, sql: str) -> Dict[str, List[str]]:
        """
        从 SQL 语句中提取表名

        Args:
            sql: SQL 语句字符串

        Returns:
            包含 input 和 output 表名列表的字典
            {"input": [...], "output": [...]}
        """
        result = {"input": [], "output": []}

        if not sql or not sql.strip():
            return result

        # 提取输出表 (INSERT INTO/OVERWRITE)
        for match in self._insert_re.finditer(sql):
            table = match.group(1)
            # 清理表名（移除可能的尾部符号如分号、括号等）
            table = self._clean_table_name(table)
            if table and table not in result["output"]:
                result["output"].append(table)

        # 提取输入表 (FROM)
        for match in self._from_re.finditer(sql):
            table = match.group(1)
            table = self._clean_table_name(table)
            # 排除子查询别名（如 FROM (SELECT ...) alias）
            if table and not table.startswith('(') and table.upper() not in ('SELECT', 'DUAL'):
                if table not in result["input"]:
                    result["input"].append(table)

        # 提取输入表 (JOIN)
        for match in self._join_re.finditer(sql):
            table = match.group(1)
            table = self._clean_table_name(table)
            if table and table not in result["input"]:
                result["input"].append(table)

        return result

    def parse_file_content(self, content: str, file_ext: str) -> Dict[str, List[str]]:
        """
        从文件内容中提取 SQL 并解析表名

        Args:
            content: 文件内容
            file_ext: 文件扩展名 (.java, .scala, .py, .sql)

        Returns:
            包含所有 SQL 提取的 input 和 output 表名列表
        """
        result = {"input": [], "output": []}

        if not content:
            return result

        file_ext = file_ext.lower()

        if file_ext == '.sql':
            # SQL 文件直接解析
            return self.extract_tables(content)

        elif file_ext in ('.java', '.scala'):
            # Java/Scala 文件：提取包含 SQL 关键字的字符串
            sql_strings = self._extract_java_scala_strings(content)
            for sql in sql_strings:
                tables = self.extract_tables(sql)
                self._merge_results(result, tables)

        elif file_ext == '.py':
            # Python 文件：提取包含 SQL 关键字的字符串
            sql_strings = self._extract_python_strings(content)
            for sql in sql_strings:
                tables = self.extract_tables(sql)
                self._merge_results(result, tables)

        return result

    def _clean_table_name(self, table: str) -> str:
        """
        清理表名，移除尾部符号

        Args:
            table: 原始表名

        Returns:
            清理后的表名
        """
        # 移除尾部的分号、括号、逗号等
        table = table.rstrip(';,)')
        # 移除前部的括号
        table = table.lstrip('(')
        return table

    def _merge_results(self, target: Dict[str, List[str]], source: Dict[str, List[str]]) -> None:
        """
        合并结果到目标字典（去重）

        Args:
            target: 目标字典
            source: 源字典
        """
        for table in source.get("input", []):
            if table not in target["input"]:
                target["input"].append(table)
        for table in source.get("output", []):
            if table not in target["output"]:
                target["output"].append(table)

    def _extract_java_scala_strings(self, content: str) -> List[str]:
        """
        从 Java/Scala 代码中提取包含 SQL 关键字的字符串

        Args:
            content: 文件内容

        Returns:
            SQL 字符串列表
        """
        sql_strings = []

        # 匹配双引号字符串
        string_pattern = r'"([^"\\]*(?:\\.[^"\\]*)*)"'

        for match in re.finditer(string_pattern, content):
            string_val = match.group(1)
            # 检查是否包含 SQL 关键字
            if any(keyword in string_val.upper() for keyword in self.SQL_KEYWORDS):
                sql_strings.append(string_val)

        return sql_strings

    def _extract_python_strings(self, content: str) -> List[str]:
        """
        从 Python 代码中提取包含 SQL 关键字的字符串

        Args:
            content: 文件内容

        Returns:
            SQL 字符串列表
        """
        sql_strings = []

        # 匹配三引号字符串 (单引号或双引号)
        triple_quote_pattern = r'(\'\'\'(.*?)\'\'\'|"""(.*?)""")'

        for match in re.finditer(triple_quote_pattern, content, re.DOTALL):
            string_val = match.group(2) or match.group(3)
            if string_val and any(keyword in string_val.upper() for keyword in self.SQL_KEYWORDS):
                sql_strings.append(string_val)

        # 匹配普通单行字符串 (单引号或双引号)
        single_line_pattern = r'(\'[^\']*\'|"[^"]*")'

        for match in re.finditer(single_line_pattern, content):
            string_val = match.group(1)[1:-1]  # 去掉引号
            if any(keyword in string_val.upper() for keyword in self.SQL_KEYWORDS):
                sql_strings.append(string_val)

        return sql_strings