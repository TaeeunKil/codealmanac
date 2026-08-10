import argparse
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

from agentworkmemory.app import AgentWorkMemory, create_app
from agentworkmemory.services.auto_distillation.models import AutoDistillSettings
from agentworkmemory.services.automation.models import AutoSyncSettings
from agentworkmemory.services.curators.models import (
    ContentAccess,
    ReasoningEffort,
)
from agentworkmemory.services.diagnostics.models import DiagnosticStatus
from agentworkmemory.services.distillation.outcomes import (
    summarize_session_outcomes,
)
from agentworkmemory.services.improvement.models import ImprovementRun
from agentworkmemory.services.sessions.models import (
    LOCAL_TRANSCRIPT_PROVIDERS,
    SSH_REMOTE_TRANSCRIPT_PROVIDERS,
)
from agentworkmemory.services.synchronization.models import SyncReceipt, SyncStatus
from agentworkmemory.services.translations import Locale
from agentworkmemory.services.vault_repository.service import DEFAULT_COMMIT_MESSAGE
from agentworkmemory.settings import configure_improvement_proposer, load_config
from agentworkmemory.workflows.auto_distill import AutoDistillRunState
from agentworkmemory.workflows.collect import CollectAgentRecords
from agentworkmemory.workflows.distill import DistillSessions
from agentworkmemory.workflows.import_legacy import ImportLegacyAlmanac
from agentworkmemory.workflows.improve_harness import (
    PrepareImprovementRun,
    ProposeImprovement,
)
from agentworkmemory.workflows.remote_sync import SyncRemoteRecords
from agentworkmemory.workflows.setup import SetupAgentWorkMemory
from agentworkmemory.workflows.sync import SyncAgentRecords
from agentworkmemory.workflows.translate import TranslateWikiPages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awm",
        description="Keep agent work records in a private personal Wiki.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="Override the local Agent Work Memory state directory.",
    )
    parser.add_argument(
        "--ollama-url",
        help="Loopback Ollama origin (default: http://127.0.0.1:11434).",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Initialize the private Wiki Vault.")
    init.add_argument("path", type=Path)

    setup = commands.add_parser(
        "setup",
        help="Initialize, collect, and optionally install automatic sync.",
    )
    setup.add_argument("path", type=Path)
    setup.add_argument(
        "--vault-repo",
        help="Clone an existing private Vault repository into PATH first.",
    )
    setup.add_argument("--auto", action="store_true")
    setup.add_argument("--every", type=int, default=5, metavar="MINUTES")
    add_collection_options(setup)

    vault = commands.add_parser(
        "vault",
        help="Carry the private Markdown Vault in a separate Git repository.",
    )
    vault_commands = vault.add_subparsers(dest="vault_command", required=True)
    vault_connect = vault_commands.add_parser(
        "connect",
        help="Clone an existing Vault repository and use it on this machine.",
    )
    vault_connect.add_argument("repository")
    vault_connect.add_argument("path", type=Path)
    vault_publish = vault_commands.add_parser(
        "publish",
        help="Publish the configured Vault to an empty private repository.",
    )
    vault_publish.add_argument("repository")
    vault_commands.add_parser("status", help="Show the Vault repository state.")
    vault_commands.add_parser(
        "pull",
        help="Pull remote Vault changes when the local tree is clean.",
    )
    vault_push = vault_commands.add_parser(
        "push",
        help="Commit and push all current Vault changes.",
    )
    vault_push.add_argument("--message", default=DEFAULT_COMMIT_MESSAGE)
    vault_sync = vault_commands.add_parser(
        "sync",
        help="Commit local changes, pull with rebase, and push.",
    )
    vault_sync.add_argument("--message", default=DEFAULT_COMMIT_MESSAGE)

    note = commands.add_parser("note", help="Save a manual work note.")
    note.add_argument("text")
    note.add_argument("--title")
    note.add_argument("--cwd", type=Path)

    collect = commands.add_parser(
        "collect",
        help="Discover agent sessions and optionally retain their content.",
    )
    collect.add_argument(
        "--from",
        dest="providers",
        action="append",
        choices=LOCAL_TRANSCRIPT_PROVIDERS,
        help="Agent provider to collect. Repeat to select more than one.",
    )
    collect.add_argument(
        "--include-content",
        action="store_true",
        help=(
            "Copy transcript content into private state and Wiki; "
            "it may contain sensitive text."
        ),
    )
    collect.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help="Home directory containing provider session stores.",
    )

    sync = commands.add_parser(
        "sync",
        help="Run one locked incremental collection and refresh search.",
    )
    add_collection_options(sync)

    auto = commands.add_parser(
        "auto",
        help="Manage automatic Agent Work Memory collection.",
    )
    auto_commands = auto.add_subparsers(dest="auto_command", required=True)
    auto_install = auto_commands.add_parser(
        "install",
        help="Install periodic collection with the operating-system scheduler.",
    )
    auto_install.add_argument("--every", type=int, default=5, metavar="MINUTES")
    add_collection_options(auto_install)
    auto_commands.add_parser("status", help="Show scheduler and last-sync status.")
    auto_commands.add_parser("remove", help="Remove automatic collection.")

    auto_distill = commands.add_parser(
        "auto-distill",
        help="Manage opt-in scheduled Wiki distillation.",
    )
    auto_distill_commands = auto_distill.add_subparsers(
        dest="auto_distill_command",
        required=True,
    )
    auto_distill_install = auto_distill_commands.add_parser(
        "install",
        help="Install bounded scheduled distillation.",
    )
    auto_distill_install.add_argument(
        "--every",
        type=int,
        default=60,
        metavar="MINUTES",
    )
    auto_distill_install.add_argument("--limit", type=int, default=1)
    auto_distill_install.add_argument(
        "--for-days",
        type=int,
        default=7,
        metavar="DAYS",
        help="Expire the standing grant after this many days (default: 7).",
    )
    auto_distill_install.add_argument(
        "--max-total",
        type=int,
        default=24,
        metavar="SESSIONS",
        help="Maximum sessions for this standing grant (default: 24).",
    )
    auto_distill_install.add_argument(
        "--using",
        dest="runtime",
        default="codex",
    )
    auto_distill_install.add_argument("--model")
    auto_distill_install.add_argument("--effort", type=parse_reasoning_effort)
    auto_distill_access = auto_distill_install.add_mutually_exclusive_group()
    auto_distill_access.add_argument(
        "--allow-local-content",
        action="store_true",
        help="Persist permission to send selected bodies to a local runtime.",
    )
    auto_distill_access.add_argument(
        "--allow-remote-content",
        action="store_true",
        help="Persist permission to send selected bodies to the named runtime.",
    )
    auto_distill_configure = auto_distill_commands.add_parser(
        "configure",
        help="Change the curator model or reasoning effort in the current grant.",
    )
    auto_distill_configure.add_argument("--model")
    auto_distill_configure.add_argument(
        "--effort",
        type=parse_reasoning_effort,
    )
    auto_distill_configure.add_argument(
        "--limit",
        type=int,
        help="Maximum pending sessions per scheduled batch (1-20).",
    )
    auto_distill_configure.add_argument(
        "--max-total",
        type=int,
        metavar="SESSIONS",
        help="Resize the existing standing grant without resetting reservations.",
    )
    auto_distill_commands.add_parser(
        "status",
        help="Show automatic distillation settings and scheduler status.",
    )
    auto_distill_commands.add_parser(
        "run",
        help="Run one configured automatic-distillation batch now.",
    )
    auto_distill_commands.add_parser(
        "remove",
        help="Remove automatic distillation without deleting Wiki pages.",
    )

    remote = commands.add_parser(
        "remote",
        help="Manage explicit read-only SSH transcript sources.",
    )
    remote_commands = remote.add_subparsers(
        dest="remote_command",
        required=True,
    )
    remote_add = remote_commands.add_parser(
        "add",
        help="Register an SSH config alias or user@host.",
    )
    remote_add.add_argument("target")
    add_remote_provider_options(remote_add)
    remote_commands.add_parser("list", help="List registered SSH remotes.")
    remote_status = remote_commands.add_parser(
        "status",
        help="Show bounded sync status for one SSH remote.",
    )
    remote_status.add_argument("target")
    remote_sync = remote_commands.add_parser(
        "sync",
        help="Fetch changed transcripts from registered SSH remotes.",
    )
    remote_sync.add_argument("target", nargs="?")
    add_remote_provider_options(remote_sync)
    remote_sync.add_argument(
        "--include-content",
        action="store_true",
        help="Retain transcript bodies in private local state and Wiki.",
    )
    remote_remove = remote_commands.add_parser(
        "remove",
        help="Unregister an SSH remote without deleting retained records.",
    )
    remote_remove.add_argument("target")

    import_records = commands.add_parser(
        "import",
        help="Import a provider-neutral agent record JSON bundle.",
    )
    import_records.add_argument("path", type=Path)

    migrate = commands.add_parser(
        "migrate-almanac",
        help="Copy a legacy repository .almanac/pages tree for review.",
    )
    migrate.add_argument("path", type=Path)

    distill = commands.add_parser(
        "distill",
        help="Promote selected sessions into durable Wiki knowledge.",
    )
    distill.add_argument("session_ids", nargs="*")
    distill.add_argument(
        "--pending",
        action="store_true",
        help="Select newest captured sessions that have not been distilled.",
    )
    distill.add_argument(
        "--limit",
        type=int,
        help="Maximum pending sessions to select (default: 3, maximum: 20).",
    )
    distill.add_argument("--using", dest="runtime", default="codex")
    distill.add_argument("--model")
    distill.add_argument("--effort", type=parse_reasoning_effort)
    content_access = distill.add_mutually_exclusive_group()
    content_access.add_argument(
        "--allow-local-content",
        action="store_true",
        help="Allow selected session bodies to be sent to a local runtime.",
    )
    content_access.add_argument(
        "--allow-remote-content",
        action="store_true",
        help="Allow selected session event bodies to be sent to the runtime.",
    )

    improve = commands.add_parser(
        "improve",
        help="Prepare and inspect evidence-grounded harness improvements.",
    )
    improve_commands = improve.add_subparsers(
        dest="improve_command",
        required=True,
    )
    improve_prepare = improve_commands.add_parser(
        "prepare",
        help="Prepare an immutable improvement run from selected sessions.",
    )
    improve_prepare.add_argument("session_ids", nargs="+")
    improve_prepare.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository checkout whose current revision anchors the run.",
    )
    improve_prepare.add_argument(
        "--allow-local-content",
        action="store_true",
        help="Copy bodies only from the explicitly selected local sessions.",
    )
    improve_prepare.add_argument(
        "--editable",
        type=Path,
        action="append",
        nargs="+",
        required=True,
        help="Relative editable path; repeat or provide several paths explicitly.",
    )
    improve_commands.add_parser(
        "settings",
        help="Show the durable Codex improvement proposer defaults.",
    )
    improve_configure = improve_commands.add_parser(
        "configure",
        help="Update durable Codex improvement proposer defaults.",
    )
    improve_configure.add_argument("--model")
    improve_configure.add_argument("--effort", type=parse_reasoning_effort)
    improve_propose = improve_commands.add_parser(
        "propose",
        help="Create one candidate improvement in a detached Git worktree.",
    )
    improve_propose.add_argument("run_id")
    improve_propose.add_argument("--model")
    improve_propose.add_argument("--effort", type=parse_reasoning_effort)
    improve_commands.add_parser(
        "list",
        help="List prepared and evaluated improvement runs.",
    )
    improve_show = improve_commands.add_parser(
        "show",
        help="Show one improvement run without retained event bodies.",
    )
    improve_show.add_argument("run_id")

    translate = commands.add_parser(
        "translate",
        help="Create derived Korean or English Wiki representations.",
    )
    translate.add_argument("paths", nargs="*", type=Path)
    translate.add_argument(
        "--pending",
        action="store_true",
        help="Select canonical pages whose requested translation is missing or stale.",
    )
    translate.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum pending pages to translate (default: 1, maximum: 20).",
    )
    translate.add_argument(
        "--to",
        dest="locale",
        type=Locale,
        choices=tuple(Locale),
        required=True,
    )
    translate.add_argument("--using", dest="runtime", default="codex")
    translate.add_argument("--model")
    translate.add_argument("--effort", type=parse_reasoning_effort)
    translation_access = translate.add_mutually_exclusive_group()
    translation_access.add_argument(
        "--allow-local-content",
        action="store_true",
        help="Allow selected Wiki bodies to be sent to a local runtime.",
    )
    translation_access.add_argument(
        "--allow-remote-content",
        action="store_true",
        help="Allow selected Wiki bodies to be sent to the named runtime.",
    )

    commands.add_parser("runtimes", help="Check available curator runtimes.")

    doctor = commands.add_parser("doctor", help="Check the local installation.")
    doctor.add_argument("--home", type=Path, default=Path.home())
    doctor.add_argument("--runtimes", action="store_true")

    serve = commands.add_parser(
        "serve",
        help="Open the local Agent Work Memory viewer.",
    )
    serve.add_argument("--port", type=int, default=3928)
    serve.add_argument("--no-open", action="store_true")

    commands.add_parser("sessions", help="List retained agent sessions.")

    show = commands.add_parser("show", help="Show one retained session.")
    show.add_argument("session_id")

    search = commands.add_parser("search", help="Search sessions and Wiki Markdown.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.state_dir)
    try:
        app = (
            create_app(config)
            if args.ollama_url is None
            else create_app(config, ollama_url=args.ollama_url)
        )
        return dispatch(args, app)
    except (KeyError, OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def parse_reasoning_effort(value: str) -> ReasoningEffort:
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = {
        "extra-high": "xhigh",
        "x-high": "xhigh",
    }.get(normalized, normalized)
    try:
        return ReasoningEffort(normalized)
    except ValueError as error:
        choices = ", ".join(effort.value for effort in ReasoningEffort)
        raise argparse.ArgumentTypeError(
            f"reasoning effort must be one of: {choices}"
        ) from error


def curator_configuration_text(settings: AutoDistillSettings) -> str:
    model = settings.model or "runtime default"
    effort = settings.effort.value if settings.effort else "runtime default"
    return f"Curator: {model}; reasoning effort: {effort}."


def direct_curator_configuration_text(args: argparse.Namespace) -> str:
    model = args.model or "runtime default"
    effort = args.effort.value if args.effort else "runtime default"
    access = distill_content_access(args).value
    return (
        f"Curator: {args.runtime}; model {model}; reasoning effort {effort}; "
        f"content {access}."
    )


def dispatch(args: argparse.Namespace, app: AgentWorkMemory) -> int:
    if args.command == "init":
        path = app.vault.initialize(args.path)
        app.wiki.refresh()
        print(f"Initialized Agent Work Memory Vault at {path}")
        return 0
    if args.command == "setup":
        if args.vault_repo is not None:
            app.vault_repository.connect(args.vault_repo, args.path)
        result = app.setup.run(
            SetupAgentWorkMemory(
                vault_path=args.path,
                home=args.home.expanduser().resolve(),
                providers=tuple(
                    args.providers or LOCAL_TRANSCRIPT_PROVIDERS
                ),
                include_content=args.include_content,
                auto_interval_minutes=args.every if args.auto else None,
            )
        )
        print(f"Agent Work Memory ready at {result.vault_path}")
        print_sync_receipt(result.sync)
        if result.automation_installed:
            print(f"Automatic sync installed every {args.every} minute(s).")
        print("Open the Wiki with `awm serve` or Obsidian.")
        return 0
    if args.command == "vault":
        return dispatch_vault(args, app)
    if args.command == "import":
        app.vault.require_path()
        result = app.import_records.import_file(args.path)
        print(f"Imported {result.session_id}; added {result.events_added} event(s).")
        print(result.wiki_path)
        return 0
    if args.command == "migrate-almanac":
        app.vault.require_path()
        receipt = app.import_legacy.run(ImportLegacyAlmanac(source=args.path))
        print(
            f"Imported {receipt.files_copied} legacy page(s); "
            f"{receipt.files_unchanged} unchanged."
        )
        print(receipt.target.as_posix())
        return 0
    if args.command == "distill":
        app.vault.require_path()
        session_ids = distill_session_ids(args, app)
        if not session_ids:
            print("No captured sessions are waiting to be distilled.")
            return 0
        if args.pending:
            print(f"Selected {len(session_ids)} pending session(s):")
            for session_id in session_ids:
                print(session_id)
        print(direct_curator_configuration_text(args))
        receipt = app.distill.run(
            DistillSessions(
                session_ids=session_ids,
                runtime=args.runtime,
                model=args.model,
                effort=args.effort,
                content_access=distill_content_access(args),
            )
        )
        print(f"Distill {receipt.run_id}: {receipt.status.value}")
        if receipt.changed_files:
            for path in receipt.changed_files:
                print(path.as_posix())
        else:
            print("No durable Wiki pages changed.")
        return 0
    if args.command == "improve":
        return dispatch_improve(args, app)
    if args.command == "translate":
        app.vault.require_path()
        paths = translation_paths(args, app)
        if not paths:
            print("No Wiki pages are waiting for that translation.")
            return 0
        print(direct_curator_configuration_text(args))
        changed = app.translate.run(
            TranslateWikiPages(
                paths=paths,
                locale=args.locale,
                runtime=args.runtime,
                model=args.model,
                effort=args.effort,
                content_access=distill_content_access(args),
            )
        )
        print(f"Translated {len(changed)} Wiki page(s) to {args.locale.value}.")
        for path in changed:
            print(path.as_posix())
        return 0
    if args.command == "runtimes":
        for readiness in app.curators.readiness():
            status = "ready" if readiness.available else "unavailable"
            print(f"{readiness.runtime:<8} {status:<11} {readiness.message}")
            if readiness.repair:
                print(f"                     {readiness.repair}")
        return 0
    if args.command == "doctor":
        checks = app.diagnostics.run(
            args.home.expanduser().resolve(),
            include_runtimes=args.runtimes,
        )
        for check in checks:
            print(f"{check.status.value:<7} {check.name:<20} {check.message}")
        return int(any(check.status is DiagnosticStatus.ERROR for check in checks))
    if args.command == "serve":
        app.vault.require_path()
        app.wiki.refresh()
        from agentworkmemory.viewer.runner import serve_viewer

        serve_viewer(
            app,
            port=args.port,
            open_browser=not args.no_open,
        )
        return 0
    if args.command == "sync":
        app.vault.require_path()
        receipt = app.sync.run(sync_request(args), progress=print)
        print_sync_receipt(receipt)
        return 0 if receipt.status is not SyncStatus.FAILED else 1
    if args.command == "auto":
        return dispatch_auto(args, app)
    if args.command == "auto-distill":
        return dispatch_auto_distill(args, app)
    if args.command == "remote":
        return dispatch_remote(args, app)
    if args.command == "note":
        app.vault.require_path()
        session = app.sessions.add_manual_note(
            args.text,
            title=args.title,
            cwd=args.cwd,
        )
        page = app.vault.refresh_session(
            session,
            app.sessions.events(session.session_id),
        )
        app.wiki.refresh()
        print(f"Saved {session.session_id}")
        print(page)
        return 0
    if args.command == "collect":
        app.vault.require_path()
        selected = args.providers or [
            *LOCAL_TRANSCRIPT_PROVIDERS,
        ]
        receipt = app.collect.collect(
            CollectAgentRecords(
                providers=tuple(selected),
                home=args.home.expanduser().resolve(),
                include_content=args.include_content,
            ),
            progress=print,
        )
        print(
            f"Discovered {receipt.sessions_discovered} session(s); "
            f"added {receipt.events_added} event(s)."
        )
        if args.include_content:
            print("Content retained locally; review the private Wiki before sharing.")
        else:
            print("Metadata only. Use --include-content to retain transcript bodies.")
        return 0
    if args.command == "sessions":
        for session in app.sessions.list():
            captured = "content" if session.content_captured else "metadata"
            print(
                f"{session.session_id}  {session.provider:<6}  "
                f"{captured:<8}  {session.title}"
            )
        return 0
    if args.command == "show":
        session = app.sessions.get(args.session_id)
        print(f"{session.title} [{session.provider}]")
        if session.cwd is not None:
            print(f"workspace: {session.cwd}")
        for event in app.sessions.events(session.session_id):
            print(f"\n[{event.kind.value}] {event.label}")
            print(event.content)
        return 0
    if args.command == "search":
        for result in app.search.find(args.query, args.limit):
            print(f"{result.kind:<7} {result.identity}  {result.title}")
            if result.excerpt:
                print(f"        {result.excerpt}")
        return 0
    raise ValueError(f"unsupported command: {args.command}")


def add_collection_options(parser: argparse.ArgumentParser) -> None:
    add_provider_options(parser)
    parser.add_argument(
        "--include-content",
        action="store_true",
        help="Retain transcript bodies in private local state and Wiki.",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help="Home directory containing provider session stores.",
    )


def add_provider_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--from",
        dest="providers",
        action="append",
        choices=LOCAL_TRANSCRIPT_PROVIDERS,
        help="Agent provider to collect. Repeat to select more than one.",
    )


def add_remote_provider_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--from",
        dest="providers",
        action="append",
        choices=SSH_REMOTE_TRANSCRIPT_PROVIDERS,
        help="Remote agent provider to collect. Repeat to select more than one.",
    )


def distill_content_access(args: argparse.Namespace) -> ContentAccess:
    if args.allow_local_content:
        return ContentAccess.SELECTED_LOCAL
    if args.allow_remote_content:
        return ContentAccess.SELECTED_REMOTE
    return ContentAccess.METADATA_ONLY


def distill_session_ids(
    args: argparse.Namespace,
    app: AgentWorkMemory,
) -> tuple[str, ...]:
    explicit = tuple(args.session_ids)
    if args.pending and explicit:
        raise ValueError("--pending cannot be combined with session ids")
    if args.limit is not None and not args.pending:
        raise ValueError("--limit requires --pending")
    if not args.pending:
        if not explicit:
            raise ValueError("distill requires session ids or --pending")
        return explicit
    limit = 3 if args.limit is None else args.limit
    return tuple(
        session.session_id
        for session in app.sessions.pending_distillation(limit)
    )


def translation_paths(
    args: argparse.Namespace,
    app: AgentWorkMemory,
) -> tuple[Path, ...]:
    explicit = tuple(args.paths)
    if args.pending and explicit:
        raise ValueError("--pending cannot be combined with Wiki paths")
    if not args.pending:
        if not explicit:
            raise ValueError("translate requires Wiki paths or --pending")
        return explicit
    return app.translate.pending_paths(args.locale, args.limit)


def sync_request(args: argparse.Namespace) -> SyncAgentRecords:
    return SyncAgentRecords(
        providers=tuple(args.providers or LOCAL_TRANSCRIPT_PROVIDERS),
        home=args.home.expanduser().resolve(),
        include_content=args.include_content,
    )


def dispatch_improve(args: argparse.Namespace, app: AgentWorkMemory) -> int:
    if args.improve_command == "prepare":
        editable_paths = tuple(
            path
            for group in args.editable
            for path in group
        )
        request = PrepareImprovementRun(
            session_ids=tuple(args.session_ids),
            repository=args.repo.expanduser().resolve(),
            content_access=(
                ContentAccess.SELECTED_LOCAL
                if args.allow_local_content
                else ContentAccess.METADATA_ONLY
            ),
            editable_paths=editable_paths,
        )
        run = app.improve_harness.prepare(request)
        print(f"Prepared improvement run {run.run_id}.")
        print_improvement_run_summary(run)
        return 0
    if args.improve_command == "settings":
        settings = app.config.improvement_proposer
        print(f"model: {settings.model}")
        print(f"reasoning effort: {settings.reasoning_effort.value}")
        return 0
    if args.improve_command == "configure":
        config = configure_improvement_proposer(
            app.config,
            model=args.model,
            reasoning_effort=args.effort,
        )
        settings = config.improvement_proposer
        print("Improvement proposer settings updated.")
        print(f"model: {settings.model}")
        print(f"reasoning effort: {settings.reasoning_effort.value}")
        return 0
    if args.improve_command == "propose":
        candidate = app.improve_harness.propose(
            ProposeImprovement(
                run_id=args.run_id,
                model=args.model,
                reasoning_effort=args.effort,
            )
        )
        print(f"Proposed improvement candidate {candidate.candidate_id}.")
        print(
            "changed: "
            + ", ".join(path.as_posix() for path in candidate.changed_paths)
        )
        return 0
    if args.improve_command == "list":
        runs = app.improve_harness.list()
        if not runs:
            print("No improvement runs.")
            return 0
        for run in runs:
            print(
                f"{run.run_id}  {run.state.value:<18} "
                f"{len(run.evidence)} evidence session(s)  "
                f"base {run.base_revision}"
            )
        return 0
    if args.improve_command == "show":
        details = app.improve_harness.show(args.run_id)
        print_improvement_run_summary(details.run)
        print("candidates:")
        if not details.candidates:
            print("  none")
        for summary in details.candidates:
            candidate = summary.candidate
            print(f"  {candidate.candidate_id}  {candidate.component.value}")
            print(
                "    changed: "
                + ", ".join(path.as_posix() for path in candidate.changed_paths)
            )
            if summary.evaluation is None:
                print("    evaluation: pending")
            else:
                print(
                    f"    evaluation: {summary.evaluation.decision.value}"
                )
        return 0
    raise ValueError(f"unsupported improve command: {args.improve_command}")


def print_improvement_run_summary(run: ImprovementRun) -> None:
    print(f"run: {run.run_id}")
    print(f"state: {run.state.value}")
    print(f"repository: {run.repository}")
    print(f"base revision: {run.base_revision}")
    print(f"content access: {run.content_access.value}")
    print(f"evidence: {len(run.evidence)} session(s)")
    for evidence in run.evidence:
        print(
            f"  {evidence.session_id}  {evidence.provider}  "
            f"{len(evidence.events)} event metadata record(s)"
        )
    print(
        "editable: "
        + ", ".join(path.as_posix() for path in run.editable_paths)
    )


def dispatch_vault(args: argparse.Namespace, app: AgentWorkMemory) -> int:
    if args.vault_command == "connect":
        path = app.vault_repository.connect(args.repository, args.path)
        print(f"Connected Agent Work Memory Vault at {path}")
        print("Wiki navigation and local search were refreshed.")
        return 0
    if args.vault_command == "publish":
        result = app.vault_repository.publish(args.repository)
        print(f"Published Agent Work Memory Vault from {result.path}")
        return 0
    if args.vault_command == "status":
        status = app.vault_repository.status()
        state = "clean" if status.clean else f"{status.changes} change(s)"
        print(f"path: {status.path}")
        print(f"branch: {status.branch}")
        print(f"remote: {status.remote}")
        print(f"worktree: {state}")
        return 0
    if args.vault_command == "pull":
        result = app.vault_repository.pull()
        print(f"Pulled Agent Work Memory Vault at {result.path}")
        print("Wiki navigation and local search were refreshed.")
        return 0
    if args.vault_command == "push":
        result = app.vault_repository.push(args.message)
        action = "Committed and pushed" if result.committed else "Pushed"
        print(f"{action} Agent Work Memory Vault at {result.path}")
        return 0
    if args.vault_command == "sync":
        result = app.vault_repository.sync(args.message)
        action = (
            "Committed, pulled, and pushed"
            if result.committed
            else "Pulled and pushed"
        )
        print(f"{action} Agent Work Memory Vault at {result.path}")
        print("Wiki navigation and local search were refreshed.")
        return 0
    raise ValueError(f"unsupported vault command: {args.vault_command}")


def dispatch_auto(args: argparse.Namespace, app: AgentWorkMemory) -> int:
    if args.auto_command == "install":
        app.vault.require_path()
        settings = AutoSyncSettings(
            interval_minutes=args.every,
            providers=tuple(
                args.providers or LOCAL_TRANSCRIPT_PROVIDERS
            ),
            home=args.home.expanduser().resolve(),
            include_content=args.include_content,
        )
        status = app.automation.install(settings)
        print(status.message)
        return 0
    if args.auto_command == "status":
        status = app.automation.status()
        print(status.message)
        latest = app.synchronization.latest()
        if latest is None:
            print("No sync has run yet.")
        else:
            print_sync_receipt(latest)
        return 0
    if args.auto_command == "remove":
        app.automation.remove()
        print("Automatic Agent Work Memory collection removed.")
        return 0
    raise ValueError(f"unsupported auto command: {args.auto_command}")


def dispatch_auto_distill(args: argparse.Namespace, app: AgentWorkMemory) -> int:
    if args.auto_distill_command == "install":
        app.vault.require_path()
        if not 1 <= args.for_days <= 30:
            raise ValueError(
                "automatic distill grant duration must be between 1 and 30 days"
            )
        content_access = distill_content_access(args)
        settings = AutoDistillSettings(
            interval_minutes=args.every,
            limit=args.limit,
            runtime=args.runtime,
            model=args.model,
            effort=args.effort,
            content_access=content_access,
            expires_at=datetime.now(UTC) + timedelta(days=args.for_days),
            max_sessions_total=args.max_total,
        )
        app.curators.ensure_ready(settings.runtime)
        status = app.auto_distillation.install(settings)
        print(status.message)
        print(
            f"Every {settings.interval_minutes} minute(s), up to "
            f"{settings.limit} pending session(s) via {settings.runtime} "
            f"with {settings.content_access.value}."
        )
        print(curator_configuration_text(settings))
        print(
            f"Standing grant: at most {settings.max_sessions_total} session(s), "
            f"expires {settings.expires_at.isoformat()}."
        )
        return 0
    if args.auto_distill_command == "status":
        status = app.auto_distillation.status()
        print(status.message)
        if status.settings is not None:
            settings = status.settings
            print(
                f"Every {settings.interval_minutes} minute(s); "
                f"limit {settings.limit}; runtime {settings.runtime}; "
                f"content {settings.content_access.value}."
            )
            print(curator_configuration_text(settings))
            print(
                f"Standing grant: {settings.sessions_reserved}/"
                f"{settings.max_sessions_total} session(s); "
                f"expires {settings.expires_at.isoformat()}."
            )
        latest = app.distillation.list(1)
        if latest:
            receipt = latest[0]
            print(
                f"Latest distill {receipt.run_id}: {receipt.status.value}; "
                f"{len(receipt.session_ids)} session(s)."
            )
        return 0
    if args.auto_distill_command == "configure":
        settings = app.auto_distillation.configure(
            model=args.model,
            effort=args.effort,
            limit=args.limit,
            max_sessions_total=args.max_total,
        )
        print("Automatic distillation curator configuration updated.")
        print(curator_configuration_text(settings))
        print(
            f"Standing grant preserved: {settings.sessions_reserved}/"
            f"{settings.max_sessions_total} session(s); "
            f"expires {settings.expires_at.isoformat()}."
        )
        return 0
    if args.auto_distill_command == "run":
        app.vault.require_path()
        settings = app.auto_distillation.settings()
        print(curator_configuration_text(settings))
        print(f"Content access: {settings.content_access.value}.")
        with foreground_progress(
            "Automatic distillation started. Checking synchronization."
        ) as report_progress:
            receipt = app.auto_distill.run(progress=report_progress)
        if receipt.state is AutoDistillRunState.EMPTY:
            print("No captured sessions are waiting to be distilled.")
        elif receipt.state is AutoDistillRunState.GRANT_EXHAUSTED:
            print(
                "Automatic distillation standing grant is expired or exhausted; "
                "run `awm auto-distill install` to grant a new bounded window."
            )
        elif receipt.state is AutoDistillRunState.DISTILLATION_RUNNING:
            print(
                "Automatic distillation skipped because another Wiki "
                "distillation is already running."
            )
        elif receipt.state is AutoDistillRunState.SYNC_WAIT_EXPIRED:
            print(
                "Automatic distillation stopped because synchronization "
                "did not finish within 10 minutes."
            )
        else:
            print(
                f"Automatic distill succeeded for "
                f"{len(receipt.session_ids)} session(s)."
            )
            if receipt.distill is not None:
                print(
                    "Session outcomes: "
                    f"{summarize_session_outcomes(receipt.distill.session_outcomes)}."
                )
                for outcome in receipt.distill.session_outcomes:
                    pages = ", ".join(path.as_posix() for path in outcome.pages)
                    suffix = f" -> {pages}" if pages else ""
                    print(
                        f"{outcome.session_id}: {outcome.disposition.value}"
                        f"{suffix}"
                    )
                for path in receipt.distill.changed_files:
                    print(path.as_posix())
        return 0
    if args.auto_distill_command == "remove":
        app.auto_distillation.remove()
        print("Automatic distillation removed. Retained Wiki pages were kept.")
        return 0
    raise ValueError(
        f"unsupported auto-distill command: {args.auto_distill_command}"
    )


@contextmanager
def foreground_progress(
    message: str,
    *,
    stream: TextIO | None = None,
) -> Iterator[Callable[[str], None]]:
    output = stream or sys.stderr
    started_at = time.monotonic()
    stop = threading.Event()
    stage_lock = threading.Lock()
    current_stage = message
    interactive = output.isatty()
    print(message, file=output, flush=True)

    def report_progress(stage: str) -> None:
        nonlocal current_stage
        with stage_lock:
            current_stage = stage
        if interactive:
            print(
                f"\r{' ' * 100}\r{stage}",
                file=output,
                flush=True,
            )
        else:
            print(stage, file=output, flush=True)

    def render_elapsed() -> None:
        frames = "|/-\\"
        frame = 0
        while not stop.wait(1):
            elapsed = format_elapsed(time.monotonic() - started_at)
            with stage_lock:
                stage = current_stage
            print(
                f"\r{frames[frame % len(frames)]} {stage} "
                f"| elapsed {elapsed} | percentage unavailable",
                end="",
                file=output,
                flush=True,
            )
            frame += 1

    worker = None
    if interactive:
        worker = threading.Thread(target=render_elapsed, daemon=True)
        worker.start()
    completed = False
    try:
        yield report_progress
        completed = True
    finally:
        stop.set()
        if worker is not None:
            worker.join(timeout=1)
        elapsed = format_elapsed(time.monotonic() - started_at)
        prefix = "\r" if interactive else ""
        state = "finished" if completed else "stopped"
        print(
            f"{prefix}{' ' * 100}\r"
            f"Automatic distillation command {state} after {elapsed}.",
            file=output,
            flush=True,
        )


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, remaining = divmod(total, 60)
    return f"{minutes:02d}:{remaining:02d}"


def dispatch_remote(args: argparse.Namespace, app: AgentWorkMemory) -> int:
    if args.remote_command == "add":
        host = app.remotes.register(
            args.target,
            tuple(
                args.providers or SSH_REMOTE_TRANSCRIPT_PROVIDERS
            ),
        )
        providers = ", ".join(host.providers)
        print(f"Registered {host.target} ({providers}).")
        print("It will be included in future `awm sync` and automatic sync runs.")
        return 0
    if args.remote_command == "list":
        overviews = app.remotes.list()
        if not overviews:
            print("No SSH remotes registered.")
            return 0
        for overview in overviews:
            providers = ",".join(overview.host.providers)
            status = overview.status
            print(
                f"{overview.host.target:<28} {status.state.value:<9} "
                f"{providers:<13} {status.files_observed} file(s)"
            )
        return 0
    if args.remote_command == "status":
        overview = app.remotes.overview(app.remotes.get(args.target))
        status = overview.status
        print(f"target: {overview.host.target}")
        print(f"providers: {', '.join(overview.host.providers)}")
        print(f"state: {status.state.value}")
        print(f"last attempt: {status.last_attempt_at or 'never'}")
        print(f"last success: {status.last_success_at or 'never'}")
        print(f"files observed: {status.files_observed}")
        print(f"last download: {status.files_downloaded} file(s)")
        if status.error_type is not None:
            print(f"failure type: {status.error_type}")
        return 0
    if args.remote_command == "sync":
        app.vault.require_path()
        receipt = app.remote_sync.run(
            SyncRemoteRecords(
                targets=(args.target,) if args.target else (),
                providers=(
                    tuple(args.providers) if args.providers is not None else None
                ),
                include_content=args.include_content,
            )
        )
        app.search.refresh()
        if not receipt.remotes:
            print("No matching SSH remotes registered.")
            return 0
        for result in receipt.remotes:
            if result.succeeded:
                print(
                    f"{result.target}: synced; "
                    f"{result.files_downloaded} file(s) downloaded, "
                    f"{result.events_added} event(s) added."
                )
            else:
                print(f"{result.target}: failed ({result.error_type}).")
        return int(any(not result.succeeded for result in receipt.remotes))
    if args.remote_command == "remove":
        if not app.remotes.remove(args.target):
            raise KeyError(f"unknown remote host: {args.target}")
        print(f"Unregistered {args.target}. Retained local records were kept.")
        return 0
    raise ValueError(f"unsupported remote command: {args.remote_command}")


def print_sync_receipt(receipt: SyncReceipt) -> None:
    status = receipt.status.value
    print(
        f"Sync {receipt.run_id}: {status}; "
        f"{receipt.sessions_discovered} session(s), "
        f"{receipt.events_added} new event(s)."
    )
    if receipt.error_type is not None:
        print(f"Failure type: {receipt.error_type}")


if __name__ == "__main__":
    raise SystemExit(main())
