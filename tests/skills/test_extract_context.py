"""Tests for context extraction module."""

import pytest
from src.skills.common.extract_context import extract_targets


class TestExtractIPPort:
    """Tests for IP:port extraction."""

    def test_extract_ip_port_basic(self):
        """Test basic IP:port extraction."""
        log_content = "Connection established to 192.168.1.100:8080"
        result = extract_targets(log_content)

        assert len(result) == 1
        assert result[0]['type'] == 'ip_port'
        assert result[0]['ip'] == '192.168.1.100'
        assert result[0]['port'] == 8080

    def test_extract_multiple_ip_ports(self):
        """Test extraction of multiple IP:port pairs."""
        log_content = """
        Connecting to master at 10.0.0.1:7077
        Worker registered from 10.0.0.2:7077
        Driver submitted to 10.0.0.3:4040
        """
        result = extract_targets(log_content)

        assert len(result) == 3
        ips = [r['ip'] for r in result]
        assert '10.0.0.1' in ips
        assert '10.0.0.2' in ips
        assert '10.0.0.3' in ips

    def test_extract_ip_port_various_ports(self):
        """Test extraction with various port numbers."""
        log_content = "Server listening on 172.16.0.1:22 and 172.16.0.1:443"
        result = extract_targets(log_content)

        assert len(result) == 2
        ports = [r['port'] for r in result]
        assert 22 in ports
        assert 443 in ports

    def test_no_ip_port_in_log(self):
        """Test when no IP:port patterns exist."""
        log_content = "This is a plain log without any IP addresses"
        result = extract_targets(log_content)

        ip_ports = [r for r in result if r['type'] == 'ip_port']
        assert len(ip_ports) == 0


class TestExtractHostname:
    """Tests for hostname:port extraction."""

    def test_extract_hostname_port_basic(self):
        """Test basic hostname:port extraction."""
        log_content = "Connecting to master-server:7077 for Spark"
        result = extract_targets(log_content)

        assert len(result) == 1
        assert result[0]['type'] == 'hostname_port'
        assert result[0]['hostname'] == 'master-server'
        assert result[0]['port'] == 7077

    def test_extract_hostname_with_domain(self):
        """Test hostname with domain extraction."""
        log_content = "HDFS namenode at nn01.hadoop.cluster:9000"
        result = extract_targets(log_content)

        assert len(result) == 1
        assert result[0]['type'] == 'hostname_port'
        assert result[0]['hostname'] == 'nn01.hadoop.cluster'
        assert result[0]['port'] == 9000

    def test_extract_multiple_hostnames(self):
        """Test extraction of multiple hostnames."""
        log_content = """
        NameNode: namenode.example.com:8020
        ResourceManager: resourcemanager.example.com:8032
        HistoryServer: historyserver.example.com:19888
        """
        result = extract_targets(log_content)

        assert len(result) == 3
        hostnames = [r['hostname'] for r in result]
        assert 'namenode.example.com' in hostnames
        assert 'resourcemanager.example.com' in hostnames
        assert 'historyserver.example.com' in hostnames

    def test_hostname_underscores_allowed(self):
        """Test that hostnames with underscores are extracted."""
        log_content = "Worker at worker_node_01:8081 connected"
        result = extract_targets(log_content)

        assert len(result) == 1
        assert result[0]['type'] == 'hostname_port'
        assert result[0]['hostname'] == 'worker_node_01'


class TestExtractHdfsPath:
    """Tests for HDFS path extraction."""

    def test_extract_hdfs_path_basic(self):
        """Test basic HDFS path extraction."""
        log_content = "Reading data from hdfs://namenode:8020/user/hive/warehouse/table"
        result = extract_targets(log_content)

        hdfs_results = [r for r in result if r['type'] == 'hdfs']
        assert len(hdfs_results) == 1
        assert hdfs_results[0]['hdfs_path'] == 'hdfs://namenode:8020/user/hive/warehouse/table'

    def test_extract_hdfs_path_without_port(self):
        """Test HDFS path without explicit port."""
        log_content = "Output written to hdfs:///tmp/spark-output/job001"
        result = extract_targets(log_content)

        hdfs_results = [r for r in result if r['type'] == 'hdfs']
        assert len(hdfs_results) == 1
        assert hdfs_results[0]['hdfs_path'] == 'hdfs:///tmp/spark-output/job001'

    def test_extract_multiple_hdfs_paths(self):
        """Test extraction of multiple HDFS paths."""
        log_content = """
        Input: hdfs://cluster/data/input/source.parquet
        Output: hdfs://cluster/data/output/result.parquet
        Checkpoint: hdfs://cluster/checkpoints/streaming
        """
        result = extract_targets(log_content)

        hdfs_results = [r for r in result if r['type'] == 'hdfs']
        assert len(hdfs_results) == 3
        paths = [r['hdfs_path'] for r in hdfs_results]
        assert 'hdfs://cluster/data/input/source.parquet' in paths
        assert 'hdfs://cluster/data/output/result.parquet' in paths
        assert 'hdfs://cluster/checkpoints/streaming' in paths

    def test_no_hdfs_path_in_log(self):
        """Test when no HDFS paths exist."""
        log_content = "Local file at /tmp/local-data/file.txt processed"
        result = extract_targets(log_content)

        hdfs_results = [r for r in result if r['type'] == 'hdfs']
        assert len(hdfs_results) == 0


class TestExtractMixed:
    """Tests for mixed content extraction."""

    def test_extract_mixed_targets(self):
        """Test extraction of mixed IP, hostname, and HDFS paths."""
        log_content = """
        Spark job connecting to 192.168.1.10:7077
        Reading from hdfs://namenode:9000/user/data/input
        Worker node worker-01:8081 registered
        Driver at 10.20.30.40:4040
        """
        result = extract_targets(log_content)

        # Should have IP ports, hostname ports, and HDFS paths
        types = [r['type'] for r in result]
        assert 'ip_port' in types
        assert 'hostname_port' in types
        assert 'hdfs' in types

        # Check specific values
        ip_ports = [r for r in result if r['type'] == 'ip_port']
        assert len(ip_ports) == 2

        hdfs_results = [r for r in result if r['type'] == 'hdfs']
        assert len(hdfs_results) == 1

        hostname_ports = [r for r in result if r['type'] == 'hostname_port']
        assert len(hostname_ports) == 1

    def test_deduplicate_targets(self):
        """Test that duplicate targets are deduplicated."""
        log_content = """
        Connecting to 192.168.1.1:8080
        Reconnected to 192.168.1.1:8080
        Same server: 192.168.1.1:8080
        """
        result = extract_targets(log_content)

        ip_ports = [r for r in result if r['type'] == 'ip_port']
        assert len(ip_ports) == 1
        assert ip_ports[0]['ip'] == '192.168.1.1'
        assert ip_ports[0]['port'] == 8080

    def test_empty_log_content(self):
        """Test extraction from empty content."""
        result = extract_targets("")
        assert result == []

    def test_no_matching_patterns(self):
        """Test log with no matching patterns."""
        log_content = """
        Job started at 2024-01-15 10:30:00
        Processing records: 1000
        Job completed successfully
        """
        result = extract_targets(log_content)
        assert result == []