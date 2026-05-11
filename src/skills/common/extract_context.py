"""Context extraction module for extracting IPs, hostnames, and HDFS paths from logs."""

import re
from typing import List, Dict, Any


def extract_targets(log_content: str) -> List[Dict[str, Any]]:
    """
    Extract network targets from log content.

    Extracts:
    - IP:port combinations (e.g., 192.168.1.100:8080)
    - hostname:port combinations (e.g., master-server:7077)
    - HDFS paths (e.g., hdfs://namenode:8020/path/to/data)

    Args:
        log_content: The log content to parse

    Returns:
        List of dictionaries with extracted targets:
        - IP:port: {'type': 'ip_port', 'ip': str, 'port': int}
        - hostname:port: {'type': 'hostname_port', 'hostname': str, 'port': int}
        - HDFS: {'type': 'hdfs', 'hdfs_path': str}

        Results are deduplicated.
    """
    if not log_content:
        return []

    results = []
    seen = set()  # For deduplication

    # Extract HDFS paths first (they may contain hostnames/ports)
    hdfs_pattern = r'hdfs://[^\s\]\)\'"<>]+'
    for match in re.finditer(hdfs_pattern, log_content, re.IGNORECASE):
        hdfs_path = match.group(0)
        # Remove trailing punctuation that might have been captured
        hdfs_path = hdfs_path.rstrip('.,;:)]\'"')
        key = ('hdfs', hdfs_path)
        if key not in seen:
            seen.add(key)
            results.append({
                'type': 'hdfs',
                'hdfs_path': hdfs_path
            })

    # Extract IP:port patterns
    # Pattern matches valid IPv4 addresses followed by a port
    ip_port_pattern = r'\b((?:\d{1,3}\.){3}\d{1,3}):(\d{1,5})\b'
    for match in re.finditer(ip_port_pattern, log_content):
        ip = match.group(1)
        port = int(match.group(2))

        # Validate IP address octets
        octets = ip.split('.')
        if all(0 <= int(octet) <= 255 for octet in octets):
            key = ('ip_port', ip, port)
            if key not in seen:
                seen.add(key)
                results.append({
                    'type': 'ip_port',
                    'ip': ip,
                    'port': port
                })

    # Extract hostname:port patterns
    # Hostnames can contain letters, digits, hyphens, underscores, and dots
    # Pattern: word chars, hyphens, underscores, dots followed by colon and port
    # Must not be preceded by 'hdfs://' (already captured above)
    hostname_port_pattern = r'(?<!hdfs://)(?<!/)\b([a-zA-Z][a-zA-Z0-9_\-.]*[a-zA-Z0-9_]):(\d{1,5})\b'

    for match in re.finditer(hostname_port_pattern, log_content):
        hostname = match.group(1)
        port = int(match.group(2))

        # Skip if this looks like part of an HDFS path (should have been captured already)
        # Check if it's a valid port number
        if 1 <= port <= 65535:
            key = ('hostname_port', hostname, port)
            if key not in seen:
                seen.add(key)
                results.append({
                    'type': 'hostname_port',
                    'hostname': hostname,
                    'port': port
                })

    return results