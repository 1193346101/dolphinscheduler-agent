"""
SQL Parser - Parse SQL statements to extract table names

Uses regex + sqlparse to extract input/output tables from SQL statements
"""

import re
from typing import Dict, List, Optional

# Try to import sqlparse (optional dependency)
try:
    import sqlparse
    SQLPARSE_AVAILABLE = True
except ImportError:
    SQLPARSE_AVAILABLE = False


class SQLParser:
    """SQL parser to extract table names"""

    # Regex patterns - improved version
    # INSERT OVERWRITE TABLE xxx or INSERT INTO TABLE xxx
    INSERT_OVERWRITE_PATTERN = r'INSERT\s+(?:OVERWRITE|INTO)\s+(?:TABLE\s+)?([^\s(]+)'
    # FROM table or FROM (subquery) - need to exclude subqueries
    FROM_PATTERN = r'FROM\s+([a-zA-Z_][a-zA-Z0-9_.]*(?:\.[a-zA-Z_][a-zA-Z0-9_.]*)?)'
    # JOIN table [alias] ON - allow optional alias between table and ON
    JOIN_PATTERN = r'JOIN\s+([a-zA-Z_][a-zA-Z0-9_.]*(?:\.[a-zA-Z_][a-zA-Z0-9_.]*)?)\s*(?:[a-zA-Z_][a-zA-Z0-9_]*\s+)?ON'
    # CTE pattern: WITH cte_name AS (...)
    CTE_PATTERN = r'WITH\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\('

    # SQL keywords (for recognizing SQL strings in code files)
    SQL_KEYWORDS = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE']

    def __init__(self):
        """Initialize compiled regex patterns"""
        self._insert_re = re.compile(self.INSERT_OVERWRITE_PATTERN, re.IGNORECASE | re.MULTILINE)
        self._from_re = re.compile(self.FROM_PATTERN, re.IGNORECASE)
        self._join_re = re.compile(self.JOIN_PATTERN, re.IGNORECASE)
        self._cte_re = re.compile(self.CTE_PATTERN, re.IGNORECASE | re.DOTALL)

    def extract_tables(self, sql: str) -> Dict[str, List[str]]:
        """
        Extract table names from SQL statement

        Args:
            sql: SQL statement string

        Returns:
            Dict containing input and output table name lists
            {"input": [...], "output": [...]}
        """
        result = {"input": [], "output": []}

        if not sql or not sql.strip():
            return result

        # Prefer sqlparse for complex SQL
        if SQLPARSE_AVAILABLE:
            result = self._extract_with_sqlparse(sql)

        # Regex extraction as supplement (ensure comprehensive coverage)
        regex_result = self._extract_with_regex(sql)
        self._merge_results(result, regex_result)

        return result

    def _extract_with_sqlparse(self, sql: str) -> Dict[str, List[str]]:
        """
        Use sqlparse to parse SQL (handles complex nested statements)

        Args:
            sql: SQL statement

        Returns:
            Table name dict
        """
        result = {"input": [], "output": []}

        if not SQLPARSE_AVAILABLE:
            return result

        try:
            parsed = sqlparse.parse(sql)
            for statement in parsed:
                # Use regex as supplement to sqlparse
                # sqlparse table name extraction requires more complex logic, use regex here
                statement_str = str(statement)
                regex_result = self._extract_with_regex(statement_str)
                self._merge_results(result, regex_result)

        except Exception:
            # sqlparse parse failed, fallback to regex
            pass

        return result

    def _extract_cte_names(self, sql: str) -> List[str]:
        """
        Extract CTE (Common Table Expression) names from WITH clauses

        Supports both single CTE and multiple CTEs (comma-separated):
        - WITH cte1 AS (...)
        - WITH cte1 AS (...), cte2 AS (...), cte3 AS (...)

        Args:
            sql: SQL statement

        Returns:
            List of CTE names
        """
        cte_names = []

        # Find WITH clause start
        with_match = re.search(r'WITH\s+', sql, re.IGNORECASE)
        if not with_match:
            return cte_names

        # Extract the WITH clause section (until first non-CTE keyword like SELECT)
        with_start = with_match.end()

        # Match all CTE definitions: cte_name AS (...)
        # Pattern handles: name AS (...) or name AS (...) , name2 AS (...)
        cte_def_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\('

        # Find all CTE names in the WITH clause
        for match in re.finditer(cte_def_pattern, sql[with_start:], re.IGNORECASE):
            cte_name = match.group(1)
            if cte_name:
                cte_names.append(cte_name.lower())

        return cte_names

    def _extract_with_regex(self, sql: str) -> Dict[str, List[str]]:
        """
        Use regex to extract table names

        Args:
            sql: SQL statement

        Returns:
            Table name dict
        """
        result = {"input": [], "output": []}

        # Extract CTE names first (to exclude them from input tables)
        cte_names = self._extract_cte_names(sql)

        # Extract output tables (INSERT OVERWRITE/INTO TABLE)
        for match in self._insert_re.finditer(sql):
            table = match.group(1)
            # Clean table name (remove possible trailing symbols like semicolons, brackets)
            table = self._clean_table_name(table)
            if table and table not in result["output"]:
                result["output"].append(table)

        # Extract input tables (FROM)
        for match in self._from_re.finditer(sql):
            table = match.group(1)
            table = self._clean_table_name(table)
            # Exclude subquery aliases (like FROM (SELECT ...) alias)
            # Exclude CTE names (WITH cte_name AS ...)
            if table and not table.startswith('(') and table.upper() not in ('SELECT', 'DUAL'):
                # Check if this is a CTE name
                if table.lower() not in cte_names:
                    if table not in result["input"]:
                        result["input"].append(table)

        # Extract input tables (JOIN)
        for match in self._join_re.finditer(sql):
            table = match.group(1)
            table = self._clean_table_name(table)
            # Exclude CTE names
            if table and table.lower() not in cte_names:
                if table not in result["input"]:
                    result["input"].append(table)

        return result

    def parse_file_content(self, content: str, file_ext: str) -> Dict[str, List[str]]:
        """
        Extract SQL from file content and parse table names

        Args:
            content: File content
            file_ext: File extension (.java, .scala, .py, .sql)

        Returns:
            Dict containing all SQL extracted input and output table name lists
        """
        result = {"input": [], "output": []}

        if not content:
            return result

        file_ext = file_ext.lower()

        if file_ext == '.sql':
            # SQL file direct parse
            return self.extract_tables(content)

        elif file_ext in ('.java', '.scala'):
            # Java/Scala files: extract strings containing SQL keywords
            sql_strings = self._extract_java_scala_strings(content)
            for sql in sql_strings:
                tables = self.extract_tables(sql)
                self._merge_results(result, tables)

            # Scala special handling: recognize val xxxSql = """...""" pattern
            scala_sql_blocks = self._extract_scala_sql_blocks(content)
            for sql in scala_sql_blocks:
                tables = self.extract_tables(sql)
                self._merge_results(result, tables)

        elif file_ext == '.py':
            # Python files: extract strings containing SQL keywords
            sql_strings = self._extract_python_strings(content)
            for sql in sql_strings:
                tables = self.extract_tables(sql)
                self._merge_results(result, tables)

        return result

    def _clean_table_name(self, table: str) -> str:
        """
        Clean table name, remove trailing symbols

        Args:
            table: Original table name

        Returns:
            Cleaned table name
        """
        # Remove trailing semicolons, brackets, commas
        table = table.rstrip(';,)')
        # Remove leading brackets
        table = table.lstrip('(')
        # Remove special characters
        table = table.strip()
        # Filter invalid table names (empty string, special symbols)
        if not table or table in ('|', '(', ')', ',', ';'):
            return ''
        # Filter SQL keyword aliases
        if table.upper() in ('SELECT', 'FROM', 'WHERE', 'JOIN', 'ON', 'AND', 'OR', 'AS', 'T', 'A', 'B', 'C', 'DUAL'):
            return ''
        return table

    def _merge_results(self, target: Dict[str, List[str]], source: Dict[str, List[str]]) -> None:
        """
        Merge results into target dict (deduplicate)

        Args:
            target: Target dict
            source: Source dict
        """
        for table in source.get("input", []):
            if table not in target["input"]:
                target["input"].append(table)
        for table in source.get("output", []):
            if table not in target["output"]:
                target["output"].append(table)

    def _extract_java_scala_strings(self, content: str) -> List[str]:
        """
        Extract strings containing SQL keywords from Java/Scala code

        Args:
            content: File content

        Returns:
            SQL string list
        """
        sql_strings = []

        # Match double-quote strings
        string_pattern = r'"([^"\\]*(?:\\.[^"\\]*)*)"'

        for match in re.finditer(string_pattern, content):
            string_val = match.group(1)
            # Check if contains SQL keywords
            if any(keyword in string_val.upper() for keyword in self.SQL_KEYWORDS):
                sql_strings.append(string_val)

        return sql_strings

    def _extract_scala_sql_blocks(self, content: str) -> List[str]:
        """
        Extract SQL blocks from Scala code (val xxxSql = triple-quoted strings).
        """
        sql_blocks = []

        # Scala multi-line string pattern: """..."""
        # Match val/val xxx = """..."""
        pattern = r'(?:val|var)\s+\w*\s*=\s*"""([^"]*(?:""[^"]*)*?)"""'

        for match in re.finditer(pattern, content, re.DOTALL):
            sql_block = match.group(1)
            # Check if contains SQL keywords
            if any(keyword in sql_block.upper() for keyword in self.SQL_KEYWORDS):
                sql_blocks.append(sql_block)

        return sql_blocks

    def _extract_python_strings(self, content: str) -> List[str]:
        """
        Extract strings containing SQL keywords from Python code

        Args:
            content: File content

        Returns:
            SQL string list
        """
        sql_strings = []

        # Match triple-quote strings (single or double quote)
        triple_quote_pattern = r'(\'\'\'(.*?)\'\'\'|"""(.*?)""")'

        for match in re.finditer(triple_quote_pattern, content, re.DOTALL):
            string_val = match.group(2) or match.group(3)
            if string_val and any(keyword in string_val.upper() for keyword in self.SQL_KEYWORDS):
                sql_strings.append(string_val)

        # Match normal single-line strings (single or double quote)
        single_line_pattern = r'(\'[^\']*\'|"[^"]*")'

        for match in re.finditer(single_line_pattern, content):
            string_val = match.group(1)[1:-1]  # Remove quotes
            if any(keyword in string_val.upper() for keyword in self.SQL_KEYWORDS):
                sql_strings.append(string_val)

        return sql_strings


__all__ = ["SQLParser"]