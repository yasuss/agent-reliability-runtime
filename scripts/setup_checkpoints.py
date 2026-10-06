"""Explicit portable setup for framework-owned LangGraph tables."""

from agent_reliability_runtime.runtime.checkpoints import run_async, setup_checkpoints

if __name__ == "__main__":
    run_async(setup_checkpoints())
    print("LangGraph PostgreSQL checkpoint setup complete")
