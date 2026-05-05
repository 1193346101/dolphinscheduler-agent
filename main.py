"""
DolphinScheduler Agent - Entry Point
GSD: Just run it.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from agent import DolphinSchedulerAgent
from config import settings


def main():
    """Main entry point."""
    agent = DolphinSchedulerAgent(
        api_key=settings.ANTHROPIC_API_KEY,
        base_url=settings.ANTHROPIC_BASE_URL,
        model=settings.MODEL_NAME,
    )

    print("=" * 50)
    print("DolphinScheduler Agent Ready")
    print("=" * 50)
    print("\nExamples:")
    print("  - List all projects")
    print("  - Show workflows in project 1")
    print("  - Trigger workflow 123 in project 1")
    print("  - Show recent executions")
    print("-" * 50)

    agent.chat()


if __name__ == "__main__":
    main()