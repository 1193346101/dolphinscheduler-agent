# Cluster Information

This file contains cluster configuration information for service lookup.

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

## Usage

This file is used by `src/skills/common/cluster_lookup.py` to:
1. Parse host information from the Markdown table
2. Look up service information by IP and port

### Adding New Hosts

To add a new host, add a row to the Hosts Table:

```
| IP_ADDRESS | HOSTNAME | Service1 (PORT1), Service2 (PORT2) |
```

### Service Format

Services in the Services column should follow the format:
- `ServiceName (Port)` - e.g., `Spark Master (8080)`
- Multiple services are comma-separated

### Example Lookup

```python
from src.skills.common.cluster_lookup import lookup_service

# Look up Spark Master
result = lookup_service("192.168.1.10", 8080, "config/cluster_info.md")
# Returns: {"ip": "192.168.1.10", "hostname": "master-node", "service": "Spark Master", "port": 8080}
```