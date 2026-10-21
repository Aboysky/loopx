"""CLI for source preparation and the same learning model used by the App."""
from pathlib import Path

from ...paths import default_registry_path, effective_runtime_root
from .experience import ExperienceWorkspace, read_experience_json
from .media import MediaWorkspace


def register_experience_commands(subparsers, add_format) -> None:
    parser = subparsers.add_parser("experience", help="Prepare a finite learning model; explore, play and replay it in Content production.")
    parser.add_argument("operation", choices=("prepare", "list", "inspect", "run"))
    parser.add_argument("--goal-id", required=True)
    parser.add_argument("--plan-json", help="Source-bound teaching model; at most 128 KiB.")
    parser.add_argument("--experience-id")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--run-json", help="Parameters/scenario and a policy or manual actions; at most 16 KiB.")
    add_format(parser)


def handle_experience_command(args) -> dict:
    registry = Path(args.registry) if args.registry else default_registry_path()
    work = ExperienceWorkspace(MediaWorkspace(registry_path=registry, goal_id=args.goal_id,
        runtime_root=effective_runtime_root(registry, args.runtime_root)))
    if args.operation == "prepare":
        if not args.plan_json or args.run_json:
            raise ValueError("prepare requires --plan-json, without run input")
        return work.prepare(read_experience_json(args.plan_json), experience_id=args.experience_id,
                            expected_revision=args.expected_revision)
    if args.plan_json:
        raise ValueError("Only prepare accepts --plan-json")
    if args.operation == "list":
        if args.experience_id or args.expected_revision is not None or args.run_json:
            raise ValueError("list reads the Goal's prepared experiences without an item or run")
        return work.list()
    if not args.experience_id:
        raise ValueError("Select an existing --experience-id")
    if args.operation == "inspect":
        if args.run_json or args.expected_revision is not None:
            raise ValueError("inspect reads the current revision without run input")
        return work.inspect(args.experience_id)
    if args.expected_revision is None:
        raise ValueError("Read the current --expected-revision")
    return work.run(args.experience_id, expected_revision=args.expected_revision,
                    request=read_experience_json(args.run_json, limit=16 * 1024) if args.run_json else {})
