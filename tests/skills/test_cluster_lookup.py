"""
Test cluster configuration lookup module
"""

import pytest
import tempfile
import os
from pathlib import Path

# Module to be implemented - will fail initially
from src.skills.common.cluster_lookup import (
    parse_hosts_table,
    lookup_service,
)


# Sample cluster_info.md content for testing
SAMPLE_CLUSTER_INFO = """# Cluster Information

## Hosts Table

| IP | Hostname | Services |
|------|----------|----------|
| 192.168.1.10 | master-node | Spark Master (8080), HDFS NameNode (9870), YARN ResourceManager (8088) |
| 192.168.1.11 | worker-node-1 | Spark Worker (8081), HDFS DataNode (9864), YARN NodeManager (8042) |
| 192.168.1.12 | worker-node-2 | Spark Worker (8081), HDFS DataNode (9864), YARN NodeManager (8042) |
| 192.168.1.13 | hive-server | HiveServer2 (10000), Hive Metastore (9083) |

## Service Dependencies

| Service | Depends On | Port |
|---------|-----------|------|
| Spark Worker | Spark Master | 8080 |
| YARN NodeManager | YARN ResourceManager | 8088 |
| HiveServer2 | Hive Metastore | 9083 |

## Resource Limits

| Service | CPU Limit | Memory Limit | Max Instances |
|---------|-----------|--------------|---------------|
| Spark Master | 4 cores | 8GB | 1 |
| Spark Worker | 8 cores | 32GB | 10 |
| HiveServer2 | 4 cores | 16GB | 2 |
"""


class TestParseHostsTable:
    """Tests for parsing the hosts table from Markdown"""

    @pytest.fixture
    def temp_cluster_file(self):
        """Create a temporary cluster_info.md file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_CLUSTER_INFO)
            temp_path = f.name
        yield temp_path
        os.unlink(temp_path)

    def test_parse_hosts_table_extracts_all_hosts(self, temp_cluster_file):
        """Test that parse_hosts_table extracts all hosts"""
        result = parse_hosts_table(temp_cluster_file)

        assert len(result) == 4

    def test_parse_hosts_table_returns_correct_structure(self, temp_cluster_file):
        """Test that parse_hosts_table returns correct dict structure"""
        result = parse_hosts_table(temp_cluster_file)

        # Check first host
        assert result[0]["ip"] == "192.168.1.10"
        assert result[0]["hostname"] == "master-node"
        assert "Spark Master" in result[0]["services"]
        assert "8080" in result[0]["services"]

    def test_parse_hosts_table_extracts_services(self, temp_cluster_file):
        """Test that services are properly extracted"""
        result = parse_hosts_table(temp_cluster_file)

        # Check services are extracted for master node
        master = result[0]
        assert "Spark Master (8080)" in master["services"]
        assert "HDFS NameNode (9870)" in master["services"]
        assert "YARN ResourceManager (8088)" in master["services"]

    def test_parse_hosts_table_worker_node(self, temp_cluster_file):
        """Test parsing worker node information"""
        result = parse_hosts_table(temp_cluster_file)

        # Check worker-node-1
        worker1 = result[1]
        assert worker1["ip"] == "192.168.1.11"
        assert worker1["hostname"] == "worker-node-1"
        assert "Spark Worker (8081)" in worker1["services"]

    def test_parse_hosts_table_empty_file(self):
        """Test with empty file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            result = parse_hosts_table(temp_path)
            assert result == []
        finally:
            os.unlink(temp_path)

    def test_parse_hosts_table_no_hosts_section(self):
        """Test with file that has no hosts table"""
        content = """# No Hosts Here
Just some text without a hosts table.
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            result = parse_hosts_table(temp_path)
            assert result == []
        finally:
            os.unlink(temp_path)


class TestLookupService:
    """Tests for looking up service by IP and port"""

    @pytest.fixture
    def temp_cluster_file(self):
        """Create a temporary cluster_info.md file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_CLUSTER_INFO)
            temp_path = f.name
        yield temp_path
        os.unlink(temp_path)

    def test_lookup_service_by_ip_and_port_spark_master(self, temp_cluster_file):
        """Test looking up Spark Master by IP and port"""
        result = lookup_service("192.168.1.10", 8080, temp_cluster_file)

        assert result is not None
        assert result["hostname"] == "master-node"
        assert result["ip"] == "192.168.1.10"
        assert result["service"] == "Spark Master"
        assert result["port"] == 8080

    def test_lookup_service_by_ip_and_port_yarn_rm(self, temp_cluster_file):
        """Test looking up YARN ResourceManager by IP and port"""
        result = lookup_service("192.168.1.10", 8088, temp_cluster_file)

        assert result is not None
        assert result["hostname"] == "master-node"
        assert result["service"] == "YARN ResourceManager"
        assert result["port"] == 8088

    def test_lookup_service_by_ip_and_port_hive(self, temp_cluster_file):
        """Test looking up HiveServer2 by IP and port"""
        result = lookup_service("192.168.1.13", 10000, temp_cluster_file)

        assert result is not None
        assert result["hostname"] == "hive-server"
        assert result["service"] == "HiveServer2"
        assert result["port"] == 10000

    def test_lookup_service_worker_node(self, temp_cluster_file):
        """Test looking up service on worker node"""
        result = lookup_service("192.168.1.11", 8081, temp_cluster_file)

        assert result is not None
        assert result["hostname"] == "worker-node-1"
        assert result["service"] == "Spark Worker"
        assert result["port"] == 8081

    def test_lookup_service_not_found_ip(self, temp_cluster_file):
        """Test looking up with IP not in cluster"""
        result = lookup_service("10.0.0.1", 8080, temp_cluster_file)

        assert result is None

    def test_lookup_service_not_found_port(self, temp_cluster_file):
        """Test looking up with port not found on host"""
        result = lookup_service("192.168.1.10", 9999, temp_cluster_file)

        assert result is None

    def test_lookup_service_empty_file(self):
        """Test lookup with empty cluster file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            result = lookup_service("192.168.1.10", 8080, temp_path)
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_lookup_service_invalid_ip(self, temp_cluster_file):
        """Test lookup with invalid IP format"""
        result = lookup_service("invalid-ip", 8080, temp_cluster_file)

        assert result is None