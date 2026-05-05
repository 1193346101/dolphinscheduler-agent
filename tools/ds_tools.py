"""
DolphinScheduler Tools for LangChain Agent
GSD: Practical tools that work.
"""

import requests
from typing import Optional
from langchain_core.tools import tool

from config import settings


def get_ds_client():
    """Get DolphinScheduler API client."""
    return DolphinSchedulerClient(
        base_url=settings.DS_API_URL,
        token=settings.DS_TOKEN,
    )


class DolphinSchedulerClient:
    """Simple client for DolphinScheduler API."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"token": token})

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str, params: dict = None):
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict = None):
        return self._request("POST", path, json=json)

    def put(self, path: str, json: dict = None):
        return self._request("PUT", path, json=json)

    def delete(self, path: str):
        return self._request("DELETE", path)


# ============ Tools ============

@tool
def list_projects() -> str:
    """List all projects in DolphinScheduler."""
    client = get_ds_client()
    try:
        result = client.get("/projects")
        projects = result.get("data", {}).get("totalList", [])
        if not projects:
            return "No projects found."
        lines = [f"- {p['name']} (ID: {p['id']})" for p in projects]
        return "Projects:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@tool
def list_workflows(project_id: int) -> str:
    """List workflows in a project.

    Args:
        project_id: The project ID
    """
    client = get_ds_client()
    try:
        result = client.get(f"/projects/{project_id}/process-definition")
        workflows = result.get("data", {}).get("totalList", [])
        if not workflows:
            return "No workflows found in this project."
        lines = [f"- {w['name']} (ID: {w['id']}, State: {w.get('releaseState', 'N/A')})"
                 for w in workflows]
        return "Workflows:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@tool
def get_workflow_detail(project_id: int, workflow_id: int) -> str:
    """Get details of a specific workflow.

    Args:
        project_id: The project ID
        workflow_id: The workflow ID
    """
    client = get_ds_client()
    try:
        result = client.get(f"/projects/{project_id}/process-definition/{workflow_id}")
        data = result.get("data", {})
        return f"Workflow: {data.get('name')}\nDescription: {data.get('description', 'N/A')}\nState: {data.get('releaseState')}"
    except Exception as e:
        return f"Error: {e}"


@tool
def trigger_workflow(project_id: int, workflow_id: int) -> str:
    """Trigger a workflow execution.

    Args:
        project_id: The project ID
        workflow_id: The workflow ID
    """
    client = get_ds_client()
    try:
        result = client.post(f"/projects/{project_id}/executors/start-process-instance",
                            json={"processDefinitionCode": workflow_id})
        instance_id = result.get("data", {})
        return f"Workflow triggered. Instance ID: {instance_id}"
    except Exception as e:
        return f"Error: {e}"


@tool
def list_instances(project_id: int, page_size: int = 10) -> str:
    """List workflow execution instances.

    Args:
        project_id: The project ID
        page_size: Number of instances to return (default 10)
    """
    client = get_ds_client()
    try:
        result = client.get(f"/projects/{project_id}/process-instances",
                           params={"pageSize": page_size})
        instances = result.get("data", {}).get("totalList", [])
        if not instances:
            return "No instances found."
        lines = [f"- {i['name']} (ID: {i['id']}, State: {i['state']}, StartTime: {i.get('startTime', 'N/A')})"
                 for i in instances]
        return "Instances:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_ds_tools():
    """Get all DolphinScheduler tools."""
    return [
        list_projects,
        list_workflows,
        get_workflow_detail,
        trigger_workflow,
        list_instances,
    ]