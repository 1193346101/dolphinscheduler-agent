# DolphinScheduler Agent

A LangChain-based agent for managing DolphinScheduler workflows with lineage analysis capabilities.

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

3. Configure projects in `config/projects.yaml`

## Usage

### Interactive Agent

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

### Lineage Visualization Server

Start the lineage visualization service:
```bash
python lineage_server.py                    # Start server (default port 8889)
python lineage_server.py --port 9999        # Specify port
python lineage_server.py --scan             # Scan lineage before starting
python lineage_server.py --implicit         # Scan implicit dependencies
python lineage_server.py --ngrok            # Enable ngrok for public access
python lineage_server.py --scan --ngrok     # Full scan + ngrok
```

Pages:
- `index.html` - Workflow lineage query
- `implicit_index.html` - Implicit dependency analysis

### Implicit Dependency Analysis

Analyze implicit dependencies (SUB_PROCESS, DEPENDENT, table lineage):
```bash
python scripts/analyze_implicit_dependency.py <project_name>
```

Or programmatically:
```python
from src.tools.implicit_dependency_analyzer import analyze_implicit_dependency

result = analyze_implicit_dependency('ad_monitor')
print(f"Missing DEPENDENT tasks: {len(result.missing_dependencies)}")
```

## Features

- List projects and workflows
- View workflow details
- Trigger workflow executions
- Monitor instance status
- **Workflow lineage visualization** - Scan and visualize table dependencies
- **Implicit dependency analysis** - Detect SUB_PROCESS, DEPENDENT, and table lineage driven dependencies
- **Missing DEPENDENT detection** - Alert when independent workflows use producer outputs without DEPENDENT tasks

## Architecture

```
├── agent/                      # Core agent logic
├── src/
│   ├── tools/                  # DolphinScheduler tools
│   │   └── implicit_dependency_analyzer.py  # Implicit dependency analysis
│   ├── graph/                  # Graph storage and scanner
│   │   ├── sql_parser.py       # SQL parser with CTE filtering
│   │   ├── scanner.py          # Workflow scanner
│   │   └── storage.py          # Graph storage
│   └── integrations/           # External integrations
│       └── dsctl_wrapper.py    # dsctl CLI wrapper
├── scripts/                    # CLI scripts
│   └── analyze_implicit_dependency.py
├── config/                     # Configuration
│   └ projects.yaml             # Project definitions
├── data/graph/                 # Generated visualization data
│   ├── index.html              # Lineage query page
│   └── implicit_index.html     # Implicit dependency page
├── lineage_server.py           # Visualization server
└── main.py                     # Entry point
```

## Implicit Dependency Analysis Logic

| Consumer Type | Producer Type | Check DEPENDENT? | Reason |
|--------------|--------------|------------------|--------|
| Independent workflow | Child workflow (SUB_PROCESS) | ✅ Yes | Uses output without explicit dependency |
| Independent workflow | Independent workflow | ✅ Yes | Cross-workflow table dependency |
| Child workflow | Child workflow | ❌ No | Dependencies in parent DAG |

**Table lineage detection**: 
- Consumer workflow inputs tables = Producer workflow outputs tables
- Filter CTE/temporary view names (`view_*`, `temp_*`)
- Alert if no DEPENDENT task waiting for producer