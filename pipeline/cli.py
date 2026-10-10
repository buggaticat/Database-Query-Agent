from __future__ import annotations

import argparse

from pipeline.config import load_env_local
from pipeline.orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the query agent."""
    parser = argparse.ArgumentParser(description="CCTV natural-language database query agent")
    return parser


def run_cli() -> None:
    """Run the interactive CLI loop for the query agent."""
    build_parser().parse_args()
    load_env_local()
    orchestrator = Orchestrator()

    print("Database Query Agent")
    print("Type a prompt and press Enter. Use Ctrl + C to exit.")

    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt:
            continue
        if prompt.lower() in {"/exit", "exit", "quit", "/quit"}:
            break

        state = orchestrator.run_with_progress(prompt, progress=print)
        response = state.get("response", "")
        print(response)


if __name__ == "__main__":
    run_cli()
