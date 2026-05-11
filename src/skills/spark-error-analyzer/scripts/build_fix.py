"""
Spark Fix Builder - Build fix configurations for Spark errors

This module provides functions to build fix configurations for Spark errors
based on error type, current config, cluster limits, and historical data.
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional, Any


def parse_memory(mem_str: str) -> int:
    """
    Parse memory string to megabytes (MB).

    Args:
        mem_str: Memory string like "4g", "2048m", "1t", "512"

    Returns:
        Memory value in MB

    Examples:
        >>> parse_memory("4g")
        4096
        >>> parse_memory("2048m")
        2048
        >>> parse_memory("1t")
        1048576
        >>> parse_memory("512")
        512
    """
    if not mem_str:
        return 0

    mem_str = str(mem_str).strip().lower()

    # Extract number and unit
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([kmgt]?)b?$', mem_str)
    if not match:
        # Try to parse as plain number (assume MB)
        try:
            return int(float(mem_str))
        except ValueError:
            return 0

    value = float(match.group(1))
    unit = match.group(2)

    # Convert to MB
    multipliers = {
        '': 1,      # No unit, assume MB
        'k': 1 / 1024,  # KB to MB
        'm': 1,     # MB
        'g': 1024,  # GB to MB
        't': 1024 * 1024,  # TB to MB
    }

    return int(value * multipliers.get(unit, 1))


def format_memory(mb: int) -> str:
    """
    Format memory in MB to a human-readable string.

    Prefers GB for values >= 1024 MB, otherwise uses MB.

    Args:
        mb: Memory value in MB

    Returns:
        Formatted memory string like "4g" or "512m"

    Examples:
        >>> format_memory(4096)
        '4g'
        >>> format_memory(512)
        '512m'
        >>> format_memory(1536)
        '1536m'
    """
    if mb <= 0:
        return "0m"

    # Use GB if >= 1024 MB and divisible by 1024
    if mb >= 1024 and mb % 1024 == 0:
        return f"{mb // 1024}g"

    return f"{mb}m"


def _get_current_memory(config: Dict[str, Any], key: str, default_mb: int = 0) -> int:
    """
    Get current memory value from config in MB.

    Args:
        config: Current Spark configuration dict
        key: Configuration key (e.g., "spark.executor.memory")
        default_mb: Default value in MB if not found

    Returns:
        Memory value in MB
    """
    value = config.get(key)
    if value is None:
        return default_mb
    return parse_memory(str(value))


def _load_historical_configs(historical_file: Optional[str]) -> list[Dict[str, Any]]:
    """
    Load historical successful configurations from file.

    Args:
        historical_file: Path to historical configs JSON file

    Returns:
        List of historical config dicts
    """
    if not historical_file:
        return []

    path = Path(historical_file)
    if not path.exists():
        return []

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'configs' in data:
                return data['configs']
            return []
    except (json.JSONDecodeError, IOError):
        return []


def _find_historical_fix(
    error_type: str,
    historical_configs: list[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Find a successful historical config for the given error type.

    Args:
        error_type: Type of error (e.g., "oom_executor")
        historical_configs: List of historical successful configs

    Returns:
        Historical config if found, None otherwise
    """
    if not historical_configs:
        return None

    # Look for configs that were used to fix similar errors
    for config in historical_configs:
        fixed_errors = config.get('fixed_errors', [])
        if error_type in fixed_errors:
            return config.get('config', {})

    # If no specific fix found, return the most recent successful config
    if historical_configs:
        return historical_configs[0].get('config', {})

    return None


def _apply_memory_limit(
    proposed_mb: int,
    max_mb: Optional[int],
    current_mb: int
) -> int:
    """
    Apply memory limits to proposed value.

    Rules:
    - Maximum 2x current config
    - Cannot exceed cluster limit

    Args:
        proposed_mb: Proposed memory in MB
        max_mb: Maximum allowed memory from cluster limits
        current_mb: Current memory setting in MB

    Returns:
        Adjusted memory value in MB
    """
    # Apply 2x current limit
    max_increase = current_mb * 2
    result = min(proposed_mb, max_increase)

    # Apply cluster limit if specified
    if max_mb is not None and max_mb > 0:
        result = min(result, max_mb)

    return result


def build_fix(
    error_type: str,
    current_config: Dict[str, Any],
    cluster_limit: Optional[Dict[str, Any]] = None,
    historical_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build fix configuration for a Spark error.

    Fix Rules:
    - Maximum 2x current config
    - Check cluster limits (max_executor_mem, max_driver_mem)
    - Prefer historical successful configs

    Default Fixes:
    - oom_executor: executor.memory × 2
    - oom_driver: driver.memory × 2
    - container_killed_memory: executor.memory × 2
    - broadcast_timeout: autoBroadcastJoinThreshold=-1

    Args:
        error_type: Type of error (e.g., "oom_executor", "oom_driver")
        current_config: Current Spark configuration dict
        cluster_limit: Cluster resource limits dict with keys:
            - max_executor_mem: Maximum executor memory in MB or string
            - max_driver_mem: Maximum driver memory in MB or string
        historical_file: Path to JSON file with historical successful configs

    Returns:
        Dict with keys:
            - status: "success" or "no_fix_needed"
            - fix_type: Type of fix applied
            - config_changes: Dict of config changes to apply
            - source: "default", "historical", or "limited"
            - message: Human-readable description
            - files_created: List of files created (always empty for this function)
            - commit_sha: Always None for this function
    """
    if cluster_limit is None:
        cluster_limit = {}

    # Load historical configs
    historical_configs = _load_historical_configs(historical_file)

    # Check for historical fix first
    historical_fix = _find_historical_fix(error_type, historical_configs)

    # Define default fix strategies
    default_fixes = {
        "oom_executor": {
            "fix_type": "memory_increase",
            "config_changes": {
                "spark.executor.memory": None,  # Will be computed
                "spark.executor.memoryOverhead": None,  # Will be computed
            },
            "message": "Increased executor memory to resolve OOM",
        },
        "oom_driver": {
            "fix_type": "memory_increase",
            "config_changes": {
                "spark.driver.memory": None,  # Will be computed
                "spark.driver.maxResultSize": None,  # Will be computed
            },
            "message": "Increased driver memory to resolve OOM",
        },
        "container_killed_memory": {
            "fix_type": "memory_increase",
            "config_changes": {
                "spark.executor.memory": None,  # Will be computed
                "spark.executor.memoryOverhead": None,  # Will be computed
            },
            "message": "Increased executor memory to prevent container kill",
        },
        "broadcast_timeout": {
            "fix_type": "config_change",
            "config_changes": {
                "spark.sql.autoBroadcastJoinThreshold": "-1",
            },
            "message": "Disabled broadcast join to prevent timeout",
        },
        "oom_driver_direct": {
            "fix_type": "memory_increase",
            "config_changes": {
                "spark.driver.maxResultSize": "2g",
            },
            "message": "Increased driver max result size",
        },
        "oom_offheap": {
            "fix_type": "memory_increase",
            "config_changes": {
                "spark.memory.offHeap.enabled": "true",
                "spark.memory.offHeap.size": "2g",
            },
            "message": "Enabled off-heap memory",
        },
        "oom_storage": {
            "fix_type": "config_change",
            "config_changes": {
                "spark.memory.storageFraction": "0.3",
            },
            "message": "Adjusted storage fraction",
        },
        "shuffle_timeout": {
            "fix_type": "config_change",
            "config_changes": {
                "spark.shuffle.io.timeout": "120s",
            },
            "message": "Increased shuffle timeout",
        },
        "network_timeout": {
            "fix_type": "config_change",
            "config_changes": {
                "spark.network.timeout": "300s",
            },
            "message": "Increased network timeout",
        },
        "rpc_timeout": {
            "fix_type": "config_change",
            "config_changes": {
                "spark.rpc.timeout": "300s",
            },
            "message": "Increased RPC timeout",
        },
        "executor_lost_heartbeat": {
            "fix_type": "config_change",
            "config_changes": {
                "spark.executor.heartbeatInterval": "60s",
                "spark.network.timeout": "300s",
            },
            "message": "Adjusted heartbeat and network timeout",
        },
        "gc_overhead": {
            "fix_type": "memory_increase",
            "config_changes": {
                "spark.executor.memory": None,  # Will be computed
                "spark.executor.memoryOverhead": None,  # Will be computed
            },
            "message": "Increased memory to reduce GC overhead",
        },
        "driver_memory_insufficient": {
            "fix_type": "memory_increase",
            "config_changes": {
                "spark.driver.memory": None,  # Will be computed
                "spark.driver.memoryOverhead": None,  # Will be computed
            },
            "message": "Increased driver memory",
        },
        "executor_memory_insufficient": {
            "fix_type": "memory_increase",
            "config_changes": {
                "spark.executor.memory": None,  # Will be computed
                "spark.executor.memoryOverhead": None,  # Will be computed
            },
            "message": "Increased executor memory",
        },
    }

    # Check if error type has a fix strategy
    if error_type not in default_fixes:
        return {
            "status": "no_fix_needed",
            "fix_type": None,
            "config_changes": {},
            "source": None,
            "message": f"No default fix strategy for error type: {error_type}",
            "files_created": [],
            "commit_sha": None,
        }

    fix_strategy = default_fixes[error_type]
    config_changes = dict(fix_strategy["config_changes"])

    # Compute memory-based fixes
    source = "default"

    if error_type in ("oom_executor", "container_killed_memory", "executor_memory_insufficient", "gc_overhead"):
        # Get current executor memory
        current_mem = _get_current_memory(current_config, "spark.executor.memory", 1024)
        max_executor_mem = cluster_limit.get("max_executor_mem")
        if max_executor_mem:
            max_executor_mem = parse_memory(str(max_executor_mem))

        # Calculate proposed memory (2x current)
        proposed_mem = current_mem * 2

        # Apply limits
        final_mem = _apply_memory_limit(proposed_mem, max_executor_mem, current_mem)

        # Use historical fix if available and within limits
        if historical_fix:
            hist_mem = _get_current_memory(historical_fix, "spark.executor.memory")
            if hist_mem >= proposed_mem and (max_executor_mem is None or hist_mem <= max_executor_mem):
                final_mem = hist_mem
                source = "historical"

        # Set config changes
        config_changes["spark.executor.memory"] = format_memory(final_mem)
        config_changes["spark.executor.memoryOverhead"] = format_memory(max(final_mem // 4, 256))

    elif error_type in ("oom_driver", "driver_memory_insufficient"):
        # Get current driver memory
        current_mem = _get_current_memory(current_config, "spark.driver.memory", 512)
        max_driver_mem = cluster_limit.get("max_driver_mem")
        if max_driver_mem:
            max_driver_mem = parse_memory(str(max_driver_mem))

        # Calculate proposed memory (2x current)
        proposed_mem = current_mem * 2

        # Apply limits
        final_mem = _apply_memory_limit(proposed_mem, max_driver_mem, current_mem)

        # Use historical fix if available and within limits
        if historical_fix:
            hist_mem = _get_current_memory(historical_fix, "spark.driver.memory")
            if hist_mem >= proposed_mem and (max_driver_mem is None or hist_mem <= max_driver_mem):
                final_mem = hist_mem
                source = "historical"

        # Set config changes
        config_changes["spark.driver.memory"] = format_memory(final_mem)
        if "spark.driver.maxResultSize" in config_changes:
            config_changes["spark.driver.maxResultSize"] = format_memory(min(final_mem, 2048))

    elif source == "default" and historical_fix:
        # For non-memory fixes, prefer historical if available
        source = "historical"
        for key in config_changes:
            if key in historical_fix:
                config_changes[key] = historical_fix[key]

    # Check if we hit the limit
    if source == "default":
        # Check if final value is less than proposed (meaning we hit a limit)
        if error_type in ("oom_executor", "container_killed_memory", "executor_memory_insufficient", "gc_overhead"):
            current_mem = _get_current_memory(current_config, "spark.executor.memory", 1024)
            if parse_memory(config_changes.get("spark.executor.memory", "0")) < current_mem * 2:
                source = "limited"
        elif error_type in ("oom_driver", "driver_memory_insufficient"):
            current_mem = _get_current_memory(current_config, "spark.driver.memory", 512)
            if parse_memory(config_changes.get("spark.driver.memory", "0")) < current_mem * 2:
                source = "limited"

    return {
        "status": "success",
        "fix_type": fix_strategy["fix_type"],
        "config_changes": config_changes,
        "source": source,
        "message": fix_strategy["message"],
        "files_created": [],
        "commit_sha": None,
    }


__all__ = [
    "parse_memory",
    "format_memory",
    "build_fix",
]