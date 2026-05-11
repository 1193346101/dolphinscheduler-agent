#!/usr/bin/env python3
"""
Spark Exception Traceback Parser

Parses Spark exception stack traces to extract structured error information
including error type, message, root cause, and call chain.
"""

import re
from typing import Dict, List, Optional, Any


def parse_spark_exception(log: str) -> Dict[str, Any]:
    """
    Parse a Spark exception stack trace and extract structured information.

    Args:
        log: The log string containing a Spark exception stack trace

    Returns:
        Dict containing:
            - error_type: str - The exception class name (e.g., "SparkException")
            - error_message: str - The main error message
            - root_cause: dict - The deepest "Caused by" exception info
            - call_chain: list - List of call chain entries
    """
    result = {
        "error_type": "",
        "error_message": "",
        "root_cause": {},
        "call_chain": []
    }

    if not log or not log.strip():
        return result

    lines = log.strip().split('\n')

    # Pattern for outer exception: org.apache.spark.{ExceptionType}: {message}
    # Also handles other common Spark exception patterns
    outer_exception_pattern = re.compile(
        r'^(org\.apache\.spark\.)?(\w+Exception|\w+Error)(?::\s*(.+))?$'
    )

    # Pattern for "Caused by: {type}: {message}"
    caused_by_pattern = re.compile(
        r'^Caused by:\s*(.+?):\s*(.+)$'
    )

    # Pattern for call chain: at {class}.{method}({file}:{line})
    call_chain_pattern = re.compile(
        r'^\s*at\s+((?:[\w$]+\.)*[\w$]+)\.([\w$<>]+)\(([^:)]+)(?::(\d+))?\)$'
    )

    # Pattern for Java exception type
    java_exception_pattern = re.compile(
        r'^([a-zA-Z_$][a-zA-Z0-9_$]*(?:\.[a-zA-Z_$][a-zA-Z0-9_$]*)*):(.+)$'
    )

    caused_by_exceptions = []
    current_call_chain = []

    for line in lines:
        line_stripped = line.strip()

        # Check for outer exception
        if not result["error_type"]:
            match = outer_exception_pattern.match(line_stripped)
            if match:
                result["error_type"] = match.group(2) or ""
                result["error_message"] = match.group(3) or ""
                continue

            # Try Java exception pattern for first line
            match = java_exception_pattern.match(line_stripped)
            if match and ':' in line_stripped:
                # Extract just the class name without package
                full_class = match.group(1)
                result["error_type"] = full_class.split('.')[-1]
                result["error_message"] = match.group(2).strip()
                continue

        # Check for "Caused by"
        match = caused_by_pattern.match(line_stripped)
        if match:
            caused_by = {
                "error_type": match.group(1).strip(),
                "error_message": match.group(2).strip()
            }
            caused_by_exceptions.append(caused_by)

            # Also capture call chain for this caused-by section
            current_call_chain = []
            continue

        # Check for call chain entries
        match = call_chain_pattern.match(line)
        if match:
            call_entry = {
                "class": match.group(1),
                "method": match.group(2),
                "file": match.group(3),
                "line": match.group(4) if match.group(4) else "Unknown"
            }

            # Add to the appropriate call chain
            if caused_by_exceptions and not current_call_chain:
                # This is part of the last caused-by's call chain
                pass
            current_call_chain.append(call_entry)

    # Set root_cause to the deepest Caused by exception
    if caused_by_exceptions:
        result["root_cause"] = caused_by_exceptions[-1]

    # Set call chain from collected entries
    result["call_chain"] = current_call_chain

    return result


def format_parsed_exception(parsed: Dict[str, Any]) -> str:
    """
    Format parsed exception data for human-readable output.

    Args:
        parsed: The parsed exception dictionary from parse_spark_exception

    Returns:
        Formatted string representation
    """
    lines = []

    lines.append(f"Error Type: {parsed.get('error_type', 'Unknown')}")
    lines.append(f"Error Message: {parsed.get('error_message', 'N/A')}")

    root_cause = parsed.get('root_cause', {})
    if root_cause:
        lines.append(f"\nRoot Cause:")
        lines.append(f"  Type: {root_cause.get('error_type', 'Unknown')}")
        lines.append(f"  Message: {root_cause.get('error_message', 'N/A')}")

    call_chain = parsed.get('call_chain', [])
    if call_chain:
        lines.append(f"\nCall Chain ({len(call_chain)} frames):")
        for i, frame in enumerate(call_chain[:10], 1):  # Limit to 10 frames
            lines.append(f"  {i}. {frame['class']}.{frame['method']}({frame['file']}:{frame['line']})")
        if len(call_chain) > 10:
            lines.append(f"  ... and {len(call_chain) - 10} more frames")

    return '\n'.join(lines)


def extract_spark_errors(log: str) -> List[Dict[str, Any]]:
    """
    Extract all Spark exceptions from a log that may contain multiple errors.

    Args:
        log: The log string that may contain multiple exception traces

    Returns:
        List of parsed exception dictionaries
    """
    if not log:
        return []

    # Split log into individual exception blocks
    # Exception blocks typically start with a line containing "Exception" or "Error"
    exception_starts = []

    # Find all potential exception start lines
    lines = log.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith('org.apache.spark.') and
            ('Exception' in stripped or 'Error' in stripped)):
            exception_starts.append(i)
        elif stripped and ':' in stripped:
            # Check if this looks like a Java exception
            if re.match(r'^[a-zA-Z_$][a-zA-Z0-9_$]*(?:\.[a-zA-Z_$][a-zA-Z0-9_$]*)*:', stripped):
                if 'Exception' in stripped or 'Error' in stripped:
                    exception_starts.append(i)

    # If no exceptions found, try parsing the whole log
    if not exception_starts:
        parsed = parse_spark_exception(log)
        if parsed.get('error_type'):
            return [parsed]
        return []

    # Parse each exception block
    exceptions = []
    for i, start in enumerate(exception_starts):
        # Find the end of this exception block
        if i + 1 < len(exception_starts):
            end = exception_starts[i + 1]
        else:
            end = len(lines)

        block = '\n'.join(lines[start:end])
        parsed = parse_spark_exception(block)
        if parsed.get('error_type'):
            exceptions.append(parsed)

    return exceptions


if __name__ == "__main__":
    import json
    import sys

    def main():
        # Example usage
        sample_log = """
org.apache.spark.SparkException: Job aborted due to stage failure: Task 0 in stage 1.0 failed 4 times, most recent failure: Lost task 0.3 in stage 1.0 (TID 3, executor 1): java.lang.OutOfMemoryError: Java heap space
	at org.apache.spark.scheduler.DAGScheduler.failJobAndIndependentStages(DAGScheduler.scala:1923)
	at org.apache.spark.scheduler.DAGScheduler.$anonfun$abortStage$2(DAGScheduler.scala:1911)
	at org.apache.spark.scheduler.DAGScheduler.$anonfun$abortStage$2$adapted(DAGScheduler.scala:1910)
	at scala.collection.mutable.ResizableArray.foreach(ResizableArray.scala:62)
Caused by: java.lang.OutOfMemoryError: Java heap space
	at java.util.Arrays.copyOf(Arrays.java:3332)
	at java.lang.AbstractStringBuilder.ensureCapacityInternal(AbstractStringBuilder.java:124)
	at java.lang.AbstractStringBuilder.append(AbstractStringBuilder.java:448)
"""

        # Parse from stdin if provided, otherwise use sample
        if len(sys.argv) > 1:
            # Read from file
            with open(sys.argv[1], 'r') as f:
                log_content = f.read()
        elif not sys.stdin.isatty():
            # Read from stdin
            log_content = sys.stdin.read()
        else:
            log_content = sample_log

        parsed = parse_spark_exception(log_content)

        print("=== Parsed Exception ===")
        print(json.dumps(parsed, indent=2, ensure_ascii=False))

        print("\n=== Formatted Output ===")
        print(format_parsed_exception(parsed))

    main()