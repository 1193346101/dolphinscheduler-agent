"""
Cluster configuration lookup module

This module provides functions to parse cluster configuration from Markdown files
and look up service information by IP and port.
"""

import re
from typing import Optional, Dict, List


def parse_hosts_table(cluster_file: str) -> List[Dict]:
    """
    Parse the hosts table from a Markdown cluster configuration file.

    The function expects a Markdown file with a "Hosts Table" section containing
    a table in the format:
    | IP | Hostname | Services |

    Args:
        cluster_file: Path to the Markdown cluster configuration file

    Returns:
        List of dictionaries, each containing:
        - ip: The IP address
        - hostname: The hostname
        - services: Raw services string from the table
    """
    try:
        with open(cluster_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except (FileNotFoundError, IOError):
        return []

    # Find the Hosts Table section
    hosts_section = _find_section(content, "Hosts Table")

    if not hosts_section:
        return []

    # Parse the markdown table
    hosts = []

    for line in hosts_section.split('\n'):
        line = line.strip()

        # Skip empty lines and header separator lines
        if not line or line.startswith('|---') or line.startswith('| ---'):
            continue

        # Skip header line (contains "IP", "Hostname", etc.)
        if '| IP' in line or '|IP' in line:
            continue

        # Parse table row
        row = _parse_table_row(line)
        if row and len(row) >= 3:
            hosts.append({
                "ip": row[0].strip(),
                "hostname": row[1].strip(),
                "services": row[2].strip()
            })

    return hosts


def lookup_service(ip: str, port: int, cluster_file: str) -> Optional[Dict]:
    """
    Look up service information by IP address and port.

    Args:
        ip: The IP address to look up
        port: The port number to look up
        cluster_file: Path to the Markdown cluster configuration file

    Returns:
        Dictionary containing:
        - ip: The IP address
        - hostname: The hostname
        - service: The service name
        - port: The port number

        Returns None if no matching service is found.
    """
    # Validate IP format
    if not _is_valid_ip(ip):
        return None

    hosts = parse_hosts_table(cluster_file)

    # Find the host with matching IP
    for host in hosts:
        if host["ip"] == ip:
            # Parse services to find matching port
            service_info = _parse_service_with_port(host["services"], port)
            if service_info:
                return {
                    "ip": ip,
                    "hostname": host["hostname"],
                    "service": service_info["service"],
                    "port": service_info["port"]
                }

    return None


def _find_section(content: str, section_title: str) -> Optional[str]:
    """
    Find and extract a section from Markdown content by its title.

    Args:
        content: The full Markdown content
        section_title: The title of the section to find (without #)

    Returns:
        The content of the section (until the next section), or None if not found
    """
    lines = content.split('\n')
    section_start = -1
    section_level = 0

    # Find section start
    for i, line in enumerate(lines):
        if line.strip().startswith('#'):
            # Extract heading level and title
            match = re.match(r'^(#+)\s+(.+)$', line.strip())
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()

                if title.lower() == section_title.lower():
                    section_start = i
                    section_level = level
                    break

    if section_start == -1:
        return None

    # Find section end (next heading of same or higher level)
    section_end = len(lines)
    for i in range(section_start + 1, len(lines)):
        line = lines[i].strip()
        if line.startswith('#'):
            match = re.match(r'^(#+)\s+', line)
            if match:
                level = len(match.group(1))
                if level <= section_level:
                    section_end = i
                    break

    # Extract section content (without the heading itself)
    section_content = '\n'.join(lines[section_start + 1:section_end])
    return section_content


def _parse_table_row(line: str) -> Optional[List[str]]:
    """
    Parse a Markdown table row into cells.

    Args:
        line: A line from the Markdown table

    Returns:
        List of cell values, or None if not a valid table row
    """
    if not line.startswith('|') or not line.endswith('|'):
        return None

    # Remove leading and trailing pipe
    line = line[1:-1]

    # Split by pipe and strip whitespace
    cells = [cell.strip() for cell in line.split('|')]

    return cells if cells else None


def _parse_service_with_port(services_str: str, target_port: int) -> Optional[Dict]:
    """
    Parse services string to find a service matching the target port.

    Services are expected in format: "ServiceName (Port)"
    Multiple services are comma-separated.

    Args:
        services_str: The raw services string from the hosts table
        target_port: The port to search for

    Returns:
        Dictionary with 'service' and 'port' keys, or None if not found
    """
    # Pattern to match "ServiceName (Port)"
    pattern = r'([^,]+?)\s*\((\d+)\)'

    matches = re.findall(pattern, services_str)

    for service_name, port_str in matches:
        port = int(port_str)
        if port == target_port:
            return {
                "service": service_name.strip(),
                "port": port
            }

    return None


def _is_valid_ip(ip: str) -> bool:
    """
    Validate if a string is a valid IP address.

    Args:
        ip: The string to validate

    Returns:
        True if valid IP address, False otherwise
    """
    # Simple IPv4 validation
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'

    if not re.match(pattern, ip):
        return False

    # Check each octet is in valid range
    octets = ip.split('.')
    for octet in octets:
        if int(octet) > 255:
            return False

    return True


__all__ = [
    "parse_hosts_table",
    "lookup_service",
]