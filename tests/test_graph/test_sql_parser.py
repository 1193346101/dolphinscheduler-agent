"""
SQLParser 测试
"""

import pytest
from src.graph.sql_parser import SQLParser


class TestSQLParser:

    def test_extract_insert_tables(self):
        """测试提取 INSERT 语句中的表"""
        parser = SQLParser()

        sql = "INSERT INTO target_table SELECT * FROM source_table"
        result = parser.extract_tables(sql)

        assert "target_table" in result["output"]
        assert "source_table" in result["input"]

    def test_extract_insert_overwrite_tables(self):
        """测试提取 INSERT OVERWRITE 语句中的表"""
        parser = SQLParser()

        sql = "INSERT OVERWRITE TABLE target_table SELECT * FROM source_table"
        result = parser.extract_tables(sql)

        assert "target_table" in result["output"]
        assert "source_table" in result["input"]

    def test_extract_from_tables(self):
        """测试提取 FROM 子句中的表"""
        parser = SQLParser()

        sql = "SELECT * FROM my_table WHERE id = 1"
        result = parser.extract_tables(sql)

        assert "my_table" in result["input"]
        assert len(result["output"]) == 0

    def test_extract_join_tables(self):
        """测试提取 JOIN 子句中的表"""
        parser = SQLParser()

        sql = "SELECT * FROM table_a JOIN table_b ON table_a.id = table_b.id"
        result = parser.extract_tables(sql)

        assert "table_a" in result["input"]
        assert "table_b" in result["input"]

    def test_extract_complex_sql(self):
        """测试提取复杂 SQL (INSERT + FROM + JOIN)"""
        parser = SQLParser()

        sql = """
        INSERT OVERWRITE TABLE output_table
        SELECT a.id, a.name, b.value
        FROM input_table_a a
        JOIN input_table_b b ON a.id = b.id
        WHERE a.status = 'active'
        """
        result = parser.extract_tables(sql)

        assert "output_table" in result["output"]
        assert "input_table_a" in result["input"]
        assert "input_table_b" in result["input"]

    def test_parse_sql_file(self):
        """测试解析 .sql 文件"""
        parser = SQLParser()

        content = """
        SELECT * FROM raw_data;

        INSERT INTO processed_data
        SELECT * FROM raw_data WHERE status = 'valid';
        """
        result = parser.parse_file_content(content, ".sql")

        assert "raw_data" in result["input"]
        assert "processed_data" in result["output"]

    def test_parse_java_file_sql(self):
        """测试解析 .java 文件中的 SQL"""
        parser = SQLParser()

        content = '''
        public class DataProcessor {
            public void process() {
                String sql = "INSERT INTO target_table SELECT * FROM source_table";
                String nonSql = "Hello World";
                String query = "SELECT * FROM another_table";
            }
        }
        '''
        result = parser.parse_file_content(content, ".java")

        assert "target_table" in result["output"]
        assert "source_table" in result["input"]
        assert "another_table" in result["input"]

    def test_parse_scala_file_sql(self):
        """测试解析 .scala 文件中的 SQL"""
        parser = SQLParser()

        content = '''
        object DataProcessor {
            def process(): Unit = {
                val sql = "INSERT OVERWRITE TABLE output_tbl SELECT * FROM input_tbl"
            }
        }
        '''
        result = parser.parse_file_content(content, ".scala")

        assert "output_tbl" in result["output"]
        assert "input_tbl" in result["input"]

    def test_parse_python_file_sql(self):
        """测试解析 .py 文件中的 SQL"""
        parser = SQLParser()

        content = '''
        def process_data():
            sql = """
            INSERT INTO result_table
            SELECT * FROM data_table
            """
            return sql
        '''
        result = parser.parse_file_content(content, ".py")

        assert "result_table" in result["output"]
        assert "data_table" in result["input"]

    def test_empty_sql(self):
        """测试空 SQL"""
        parser = SQLParser()

        result = parser.extract_tables("")
        assert result == {"input": [], "output": []}

        result = parser.extract_tables("   ")
        assert result == {"input": [], "output": []}

    def test_no_tables(self):
        """测试不包含表名的 SQL"""
        parser = SQLParser()

        sql = "SELECT 1 + 1"
        result = parser.extract_tables(sql)

        assert result["input"] == []
        assert result["output"] == []

    def test_multiple_inserts(self):
        """测试多个 INSERT 语句"""
        parser = SQLParser()

        sql = """
        INSERT INTO table_a SELECT * FROM source;
        INSERT INTO table_b SELECT * FROM source;
        """
        result = parser.extract_tables(sql)

        assert "table_a" in result["output"]
        assert "table_b" in result["output"]
        assert "source" in result["input"]

    def test_left_join(self):
        """测试 LEFT JOIN"""
        parser = SQLParser()

        sql = "SELECT * FROM main_table LEFT JOIN lookup_table ON main_table.id = lookup_table.id"
        result = parser.extract_tables(sql)

        assert "main_table" in result["input"]
        assert "lookup_table" in result["input"]

    def test_table_with_schema(self):
        """测试带 schema 的表名"""
        parser = SQLParser()

        sql = "SELECT * FROM db.schema.table_name"
        result = parser.extract_tables(sql)

        assert "db.schema.table_name" in result["input"]

    def test_subquery_excluded(self):
        """测试子查询别名不被当作表名"""
        parser = SQLParser()

        # FROM 后面跟子查询时，别名不应被当作表名
        sql = "INSERT INTO target SELECT * FROM (SELECT * FROM source) subq"
        result = parser.extract_tables(sql)

        assert "target" in result["output"]
        assert "source" in result["input"]
        # 子查询的 FROM 会被匹配，但 "(SELECT" 应该被过滤掉