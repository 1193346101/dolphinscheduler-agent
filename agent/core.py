"""
DolphinScheduler Agent - Core module
GSD Architecture: Simple, direct, gets things done.
"""

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from .prompts import SYSTEM_PROMPT
from tools import get_ds_tools


class DolphinSchedulerAgent:
    """Main agent for DolphinScheduler operations."""

    def __init__(self, api_key: str, base_url: str = None, model: str = "glm-5"):
        self.llm = ChatAnthropic(
            model=model,
            api_key=api_key,
            anthropic_api_url=base_url,
            temperature=0,
        )
        self.tools = get_ds_tools()
        self.agent = create_tool_calling_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ])
        )
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
        )

    def run(self, query: str) -> str:
        """Execute a query and return the result."""
        result = self.executor.invoke({"input": query})
        return result.get("output", "No output")

    def chat(self):
        """Interactive chat mode."""
        print("DolphinScheduler Agent (type 'exit' to quit)")
        print("-" * 40)
        while True:
            try:
                query = input("\n> ").strip()
                if query.lower() in ("exit", "quit", "q"):
                    break
                if query:
                    print("\n" + self.run(query))
            except KeyboardInterrupt:
                break
        print("\nGoodbye!")