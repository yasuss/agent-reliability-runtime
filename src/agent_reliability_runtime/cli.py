"""Developer ingestion and fail-closed sanitized replay export commands."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.providers.http import (
    HTTPProviderConfig,
    OllamaEmbeddingProvider,
)
from agent_reliability_runtime.replay import export_replay
from agent_reliability_runtime.retrieval.service import ingest
from agent_reliability_runtime.retrieval.text import read_source


def local_embeddings() -> OllamaEmbeddingProvider:
    return OllamaEmbeddingProvider(
        HTTPProviderConfig(
            provider_id="ollama-local",
            model_id="qwen3-embedding:0.6b",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=300,
        )
    )


async def ingest_paths(root: Path, paths: list[str]) -> None:
    plans = [read_source(root, path) for path in paths]
    engine = create_engine(database_url())
    try:
        for plan in plans:
            print(json.dumps(asdict(await ingest(engine, local_embeddings(), plan))))
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ingestion = sub.add_parser("ingest")
    ingestion.add_argument("sources", nargs="+")
    exporting = sub.add_parser("export-replays")
    exporting.add_argument("--run-id", required=True)
    exporting.add_argument("--receipt", type=Path, required=True)
    exporting.add_argument("--source-git-sha", required=True)
    exporting.add_argument("--output", type=Path, required=True)
    evaluating = sub.add_parser("eval")
    modes = evaluating.add_mutually_exclusive_group(required=True)
    modes.add_argument("--calibrate", action="store_true")
    modes.add_argument("--mandatory", action="store_true")
    modes.add_argument("--live-local", action="store_true")
    evaluating.add_argument("--output", type=Path)
    evaluating.add_argument(
        "--phase", choices=["freeze", "next", "finalize", "summary"]
    )
    evaluating.add_argument("--trial-id")
    evaluating.add_argument("--review", type=Path)
    running = sub.add_parser("run")
    requests = running.add_mutually_exclusive_group(required=True)
    requests.add_argument("--scenario", dest="scenario_id")
    requests.add_argument("--task")
    running.add_argument("--workspace-id", required=True)
    running.add_argument("--user-id", required=True)
    args = parser.parse_args()
    if args.command == "eval":
        from agent_reliability_runtime.evals.calibration import calibrate
        from agent_reliability_runtime.observability import canonical

        if args.live_local:
            from agent_reliability_runtime.evals import campaign
            from agent_reliability_runtime.evals.contracts import AnswerQualityReview
            from agent_reliability_runtime.runtime.checkpoints import run_async

            if args.output is None or args.phase is None:
                parser.error(
                    "--live-local requires external --output and explicit --phase"
                )
            engine = create_engine(database_url())

            async def live_phase() -> dict[str, Any]:
                if args.phase == "freeze":
                    return await campaign.freeze(engine, args.output)
                if args.phase == "next":
                    return await campaign.start_next(engine, args.output)
                if args.phase == "summary":
                    return await campaign.summary(args.output, engine)
                await campaign.revalidate(args.output, engine)
                if not args.trial_id or not args.review:
                    parser.error("finalize requires --trial-id and --review")
                review = AnswerQualityReview.model_validate_json(
                    args.review.read_bytes()
                )
                return campaign.finalize(engine, args.output, args.trial_id, review)

            try:
                report = run_async(live_phase())
            finally:
                engine.dispose()
            print(canonical(report).decode())
            if report.get("G8") == "FAIL" or report.get("task_success") is False:
                raise SystemExit(1)
            return

        if args.mandatory:
            from agent_reliability_runtime.evals.execution import mandatory_suite
            from agent_reliability_runtime.runtime.checkpoints import run_async

            if args.output is None:
                parser.error("--mandatory requires an external --output directory")
            engine = create_engine(database_url())
            try:
                summary = run_async(mandatory_suite(engine, args.output))
            finally:
                engine.dispose()
            print(canonical(summary).decode())
            if not summary["passed"]:
                raise SystemExit(1)
            return
        result = calibrate()
        data = canonical(result.model_dump(mode="json"))
        print(data.decode())
        if args.output:
            args.output.write_bytes(data)
        if not result.passed:
            raise SystemExit(1)
    elif args.command == "run":
        from agent_reliability_runtime.observability import canonical, read_run
        from agent_reliability_runtime.runtime.checkpoints import run_async
        from agent_reliability_runtime.runtime.local import RunRequest, local_runtime

        request = RunRequest(
            workspace_id=args.workspace_id,
            user_id=args.user_id,
            task=args.task,
            scenario_id=args.scenario_id,
        )
        engine = create_engine(database_url())

        async def launch() -> None:
            run = request.run()
            async with local_runtime(engine) as runtime:
                await runtime.start(run)
            with engine.connect() as con:
                persisted = read_run(con, run.run_id)
            assert persisted is not None
            print(canonical(persisted.model_dump(mode="json")).decode())
            if persisted.status.value in {"FAILED", "BUDGET_EXCEEDED"}:
                raise SystemExit(1)

        try:
            run_async(launch())
        finally:
            engine.dispose()
    elif args.command == "export-replays":
        engine = create_engine(database_url())
        try:
            export_replay(
                engine,
                args.run_id,
                json.loads(args.receipt.read_text()),
                args.source_git_sha,
                args.output,
            )
        finally:
            engine.dispose()
    else:
        asyncio.run(ingest_paths(Path.cwd(), args.sources))


if __name__ == "__main__":
    main()
