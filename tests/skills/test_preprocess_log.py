"""
Test log preprocessing module for noise reduction
"""

import pytest
from src.skills.common.preprocess_log import (
    extract_config_lines,
    extract_error_blocks,
    extract_app_id,
    validate_extraction,
    preprocess_log,
)


class TestExtractConfigLines:
    """Tests for extracting Spark/Hadoop configuration lines"""

    def test_extract_spark_config_lines(self):
        """Test extracting Spark config lines"""
        log_content = """
Starting Spark application
spark.driver.memory=4g
spark.executor.memory=8g
spark.executor.cores=4
Some random log line
spark.shuffle.partitions=200
End of log
"""
        result = extract_config_lines(log_content)

        assert len(result) == 4
        assert "spark.driver.memory=4g" in result
        assert "spark.executor.memory=8g" in result
        assert "spark.executor.cores=4" in result
        assert "spark.shuffle.partitions=200" in result

    def test_extract_hadoop_config_lines(self):
        """Test extracting Hadoop config lines"""
        log_content = """
hadoop.fs.defaultFS=hdfs://namenode:8020
yarn.resourcemanager.address=resourcemanager:8032
dfs.replication=3
Regular log line
"""
        result = extract_config_lines(log_content)

        assert len(result) == 3
        assert "hadoop.fs.defaultFS=hdfs://namenode:8020" in result
        assert "yarn.resourcemanager.address=resourcemanager:8032" in result
        assert "dfs.replication=3" in result

    def test_extract_config_lines_empty_log(self):
        """Test with empty log content"""
        result = extract_config_lines("")

        assert result == []

    def test_extract_config_lines_no_config(self):
        """Test with no config lines present"""
        log_content = """
Starting application
Running task 1
Task completed
"""
        result = extract_config_lines(log_content)

        assert result == []

    def test_extract_config_lines_with_duplicates(self):
        """Test that duplicate config lines are preserved"""
        log_content = """
spark.executor.memory=4g
spark.executor.memory=4g
spark.driver.memory=2g
"""
        result = extract_config_lines(log_content)

        assert len(result) == 3
        assert result.count("spark.executor.memory=4g") == 2


class TestExtractErrorBlocks:
    """Tests for extracting complete error blocks"""

    def test_extract_error_block_with_stack_trace(self):
        """Test extracting ERROR with stack trace"""
        log_content = """
INFO: Starting application
ERROR: Something went wrong
    at com.example.MyClass.myMethod(MyClass.java:10)
    at com.example.MyClass.run(MyClass.java:5)
INFO: Application ended
"""
        result = extract_error_blocks(log_content)

        assert len(result) == 1
        assert "ERROR: Something went wrong" in result[0]
        assert "at com.example.MyClass.myMethod" in result[0]

    def test_extract_exception_block(self):
        """Test extracting Exception blocks"""
        log_content = """
INFO: Processing data
Exception: NullPointerException
    at com.example.DataProcessor.process(DataProcessor.java:50)
    at com.example.Main.main(Main.java:10)
Caused by: Invalid data format
INFO: Continuing
"""
        result = extract_error_blocks(log_content)

        assert len(result) == 1
        assert "Exception: NullPointerException" in result[0]
        assert "Caused by: Invalid data format" in result[0]

    def test_extract_fatal_error_block(self):
        """Test extracting FATAL error blocks"""
        log_content = """
INFO: Starting
FATAL: System out of memory
    at java.lang.OutOfMemoryError
INFO: Shutting down
"""
        result = extract_error_blocks(log_content)

        assert len(result) == 1
        assert "FATAL: System out of memory" in result[0]

    def test_extract_multiple_error_blocks(self):
        """Test extracting multiple separate error blocks"""
        log_content = """
ERROR: First error
    at com.example.First.method()
INFO: Some normal log
ERROR: Second error
    at com.example.Second.method()
FATAL: Fatal error occurred
"""
        result = extract_error_blocks(log_content)

        assert len(result) == 3

    def test_extract_nested_exceptions(self):
        """Test extracting nested exception chains"""
        log_content = """
ERROR: Outer exception
    at com.example.Outer.run()
Caused by: Inner exception
    at com.example.Inner.process()
Caused by: Root cause
    at com.example.Root.execute()
"""
        result = extract_error_blocks(log_content)

        assert len(result) == 1
        assert "Caused by: Inner exception" in result[0]
        assert "Caused by: Root cause" in result[0]

    def test_extract_error_blocks_empty_log(self):
        """Test with empty log"""
        result = extract_error_blocks("")

        assert result == []

    def test_extract_error_blocks_no_errors(self):
        """Test with no error blocks"""
        log_content = """
INFO: Starting
INFO: Running
INFO: Completed
"""
        result = extract_error_blocks(log_content)

        assert result == []


class TestExtractAppId:
    """Tests for extracting Application ID"""

    def test_extract_application_id_standard_format(self):
        """Test extracting standard application_XXX_XXX format"""
        log_content = """
INFO: Application application_1234567890_0001 submitted
INFO: Running application
"""
        result = extract_app_id(log_content)

        assert result == "application_1234567890_0001"

    def test_extract_application_id_app_format(self):
        """Test extracting app-XXX-XXX format"""
        log_content = """
INFO: Starting app-20240101-0001
"""
        result = extract_app_id(log_content)

        assert result == "app-20240101-0001"

    def test_extract_app_id_multiple_matches_returns_first(self):
        """Test that first app ID is returned when multiple exist"""
        log_content = """
INFO: Application application_1111_0001 started
INFO: Referenced application_2222_0002
"""
        result = extract_app_id(log_content)

        assert result == "application_1111_0001"

    def test_extract_app_id_not_found(self):
        """Test when no app ID is present"""
        log_content = """
INFO: Starting task
No application ID here
"""
        result = extract_app_id(log_content)

        assert result is None

    def test_extract_app_id_empty_log(self):
        """Test with empty log"""
        result = extract_app_id("")

        assert result is None


class TestPreprocessLogExtractDataMetrics:
    """Tests for extracting data metrics from Spark Event Log JSON"""

    def test_extract_metrics_from_spark_event_log(self):
        """Test extracting metrics from Spark Event Log JSON format"""
        from src.skills.common.preprocess_log import _extract_spark_metrics
        log_content = """
{"Event":"SparkListenerTaskEnd","Task Type":"ShuffleMapTask","Task Metrics":{"Input Metrics":{"Bytes Read":1048576},"Shuffle Read Metrics":{"Remote Bytes Read":2097152},"Shuffle Write Metrics":{"Shuffle Bytes Written":524288},"Memory Bytes Spilled":1024}}
{"Event":"SparkListenerTaskEnd","Task Type":"ResultTask","Task Metrics":{"Input Metrics":{"Bytes Read":2097152},"Shuffle Read Metrics":{"Remote Bytes Read":1048576},"Shuffle Write Metrics":{"Shuffle Bytes Written":262144},"Memory Bytes Spilled":2048}}
"""
        result = _extract_spark_metrics(log_content)

        assert result["input_bytes"] == 3145728  # Sum of both tasks
        assert result["shuffle_read_bytes"] == 3145728
        assert result["shuffle_write_bytes"] == 786432
        assert result["memory_spilled"] == 3072

    def test_extract_metrics_partial_data(self):
        """Test extracting metrics when only some metrics are present"""
        from src.skills.common.preprocess_log import _extract_spark_metrics
        log_content = """
{"Event":"SparkListenerTaskEnd","Task Metrics":{"Input Metrics":{"Bytes Read":1048576}}}
"""
        result = _extract_spark_metrics(log_content)

        assert result["input_bytes"] == 1048576
        assert result["shuffle_read_bytes"] == 0
        assert result["shuffle_write_bytes"] == 0
        assert result["memory_spilled"] == 0

    def test_extract_metrics_no_json(self):
        """Test with no JSON metrics data"""
        from src.skills.common.preprocess_log import _extract_spark_metrics
        log_content = """
Regular log without JSON metrics
"""
        result = _extract_spark_metrics(log_content)

        assert result["input_bytes"] == 0
        assert result["shuffle_read_bytes"] == 0
        assert result["shuffle_write_bytes"] == 0
        assert result["memory_spilled"] == 0

    def test_extract_metrics_empty_log(self):
        """Test with empty log"""
        from src.skills.common.preprocess_log import _extract_spark_metrics
        result = _extract_spark_metrics("")

        assert result["input_bytes"] == 0
        assert result["shuffle_read_bytes"] == 0
        assert result["shuffle_write_bytes"] == 0
        assert result["memory_spilled"] == 0


class TestValidateExtraction:
    """Tests for extraction validation"""

    def test_validate_extraction_complete(self):
        """Test validation with complete extraction"""
        original = "some log content"
        extracted = {
            "config_lines": ["spark.driver.memory=4g"],
            "error_blocks": ["ERROR: Something failed"],
            "app_info": {"app_id": "application_1234567890_0001"},
            "data_metrics": {
                "input_bytes": 1048576,
                "shuffle_read_bytes": 0,
                "shuffle_write_bytes": 0,
                "memory_spilled": 0
            },
            "resource_stats": []
        }

        result = validate_extraction(original, extracted)

        assert result["is_valid"] is True
        assert len(result["warnings"]) == 0

    def test_validate_extraction_missing_config_lines(self):
        """Test validation with missing config lines"""
        original = "some log content"
        extracted = {
            "config_lines": [],
            "error_blocks": ["ERROR: Something failed"],
            "app_info": {"app_id": "application_1234567890_0001"},
            "data_metrics": {
                "input_bytes": 1048576,
                "shuffle_read_bytes": 0,
                "shuffle_write_bytes": 0,
                "memory_spilled": 0
            },
            "resource_stats": []
        }

        result = validate_extraction(original, extracted)

        assert result["is_valid"] is True
        assert "No configuration lines found" in result["warnings"]

    def test_validate_extraction_missing_error_blocks(self):
        """Test validation with missing error blocks"""
        original = "some log content"
        extracted = {
            "config_lines": ["spark.driver.memory=4g"],
            "error_blocks": [],
            "app_info": {"app_id": "application_1234567890_0001"},
            "data_metrics": {
                "input_bytes": 1048576,
                "shuffle_read_bytes": 0,
                "shuffle_write_bytes": 0,
                "memory_spilled": 0
            },
            "resource_stats": []
        }

        result = validate_extraction(original, extracted)

        assert result["is_valid"] is True
        assert "No error blocks found" in result["warnings"]

    def test_validate_extraction_missing_app_id(self):
        """Test validation with missing app ID"""
        original = "some log content"
        extracted = {
            "config_lines": ["spark.driver.memory=4g"],
            "error_blocks": ["ERROR: Something failed"],
            "app_info": {"app_id": None},
            "data_metrics": {
                "input_bytes": 1048576,
                "shuffle_read_bytes": 0,
                "shuffle_write_bytes": 0,
                "memory_spilled": 0
            },
            "resource_stats": []
        }

        result = validate_extraction(original, extracted)

        assert result["is_valid"] is True
        assert "No application ID found" in result["warnings"]

    def test_validate_extraction_empty(self):
        """Test validation with empty extraction"""
        original = "some log content"
        extracted = {
            "config_lines": [],
            "error_blocks": [],
            "app_info": {"app_id": None},
            "data_metrics": {
                "input_bytes": 0,
                "shuffle_read_bytes": 0,
                "shuffle_write_bytes": 0,
                "memory_spilled": 0
            },
            "resource_stats": []
        }

        result = validate_extraction(original, extracted)

        assert result["is_valid"] is False
        assert len(result["warnings"]) >= 3


class TestPreprocessLog:
    """Tests for the main preprocess_log function"""

    def test_preprocess_log_extract_config_lines(self):
        """Test full log preprocessing extracts config lines"""
        log_content = """
spark.driver.memory=4g
spark.executor.memory=8g
INFO: Starting application application_1234567890_0001
ERROR: Task failed
    at com.example.Task.run(Task.java:10)
{"Event":"SparkListenerTaskEnd","Task Metrics":{"Input Metrics":{"Bytes Read":1048576}}}
"""
        result = preprocess_log(log_content)

        assert len(result["config_lines"]) == 2
        assert "spark.driver.memory=4g" in result["config_lines"]

    def test_preprocess_log_extract_error_blocks(self):
        """Test full log preprocessing extracts error blocks"""
        log_content = """
spark.driver.memory=4g
INFO: Starting application application_1234567890_0001
ERROR: Task failed
    at com.example.Task.run(Task.java:10)
{"Event":"SparkListenerTaskEnd","Task Metrics":{"Input Metrics":{"Bytes Read":1048576}}}
"""
        result = preprocess_log(log_content)

        assert len(result["error_blocks"]) == 1
        assert "ERROR: Task failed" in result["error_blocks"][0]

    def test_preprocess_log_extract_app_id(self):
        """Test full log preprocessing extracts app ID"""
        log_content = """
spark.driver.memory=4g
INFO: Starting application application_1234567890_0001
ERROR: Task failed
    at com.example.Task.run(Task.java:10)
{"Event":"SparkListenerTaskEnd","Task Metrics":{"Input Metrics":{"Bytes Read":1048576}}}
"""
        result = preprocess_log(log_content)

        assert result["app_info"]["app_id"] == "application_1234567890_0001"

    def test_preprocess_log_full(self):
        """Test full log preprocessing"""
        log_content = """
spark.driver.memory=4g
spark.executor.memory=8g
INFO: Starting application application_1234567890_0001
ERROR: Task failed
    at com.example.Task.run(Task.java:10)
{"Event":"SparkListenerTaskEnd","Task Metrics":{"Input Metrics":{"Bytes Read":1048576}}}
"""
        result = preprocess_log(log_content)

        assert len(result["config_lines"]) == 2
        assert len(result["error_blocks"]) == 1
        assert result["app_info"]["app_id"] == "application_1234567890_0001"
        assert result["data_metrics"]["input_bytes"] == 1048576
        assert result["resource_stats"] == []

    def test_preprocess_log_empty(self):
        """Test preprocessing empty log"""
        result = preprocess_log("")

        assert result["config_lines"] == []
        assert result["error_blocks"] == []
        assert result["app_info"]["app_id"] is None
        assert result["data_metrics"]["input_bytes"] == 0
        assert result["resource_stats"] == []

    def test_preprocess_log_with_task_type(self):
        """Test preprocessing with task_type parameter"""
        log_content = "spark.driver.memory=4g"
        result = preprocess_log(log_content, task_type="spark")

        assert len(result["config_lines"]) == 1
        assert result["resource_stats"] == []

    def test_preprocess_log_preserves_original(self):
        """Test that preprocessing doesn't modify original content"""
        original = """
spark.driver.memory=4g
ERROR: Error message
"""
        result = preprocess_log(original)

        assert "spark.driver.memory=4g" in original
        assert "ERROR: Error message" in original