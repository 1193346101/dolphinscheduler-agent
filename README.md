# DolphinScheduler Agent

A LangChain-based agent for managing DolphinScheduler workflows.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Run:
```bash
python main.py
```

## Usage

Start interactive chat:
```bash
python main.py
```

Or use programmatically:
```python
from agent import DolphinSchedulerAgent

agent = DolphinSchedulerAgent(
    api_key="your-key",
    base_url="https://api.openai.com/v1",
    model="gpt-4"
)

result = agent.run("List all projects")
print(result)
```

## Features

- List projects and workflows
- View workflow details
- Trigger workflow executions
- Monitor instance status

## Architecture

GSD (Get Shit Done) - Simple, practical, effective.

```
├── agent/          # Core agent logic
├── tools/          # DolphinScheduler tools
├── config/         # Configuration
└── main.py         # Entry point
```