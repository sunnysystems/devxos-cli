"""DevXOS CLI — analyze Git repositories for engineering signal vs noise."""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from devxos.i18n import get_strings, SUPPORTED_LANGS
from devxos.platform.telemetry import span, record_metric, record_counter, record_duration, flush
from devxos.ingestion.git_reader import read_commits
from devxos.ingestion.github_reader import read_pull_requests
from devxos.metrics.aggregator import aggregate
from devxos.models.context import AnalysisContext
from devxos.reports.narrative import generate_narrative
from devxos.reports.writer import write_output

VERSION = "v1.0"


def _merge_durability(metrics, durability):
    """Merge durability results into a ReportMetrics (frozen dataclass)."""
    from dataclasses import asdict
    from devxos.models.metrics import ReportMetrics

    d = asdict(metrics)
    d["durability_files_analyzed"] = durability.files_analyzed
    d["durability_by_origin"] = {
        bo.origin: {
            "lines_introduced": bo.lines_introduced,
            "lines_surviving": bo.lines_surviving,
            "survival_rate": bo.survival_rate,
            "median_age_days": bo.median_age_days,
        }
        for bo in durability.by_origin
    }
    return ReportMetrics(**{k: v for k, v in d.items()})


def _merge_quality_metrics(metrics, dup_result, move_result, ops_result, provenance, new_churn):
    """Merge all code quality analysis results into ReportMetrics."""
    from dataclasses import asdict
    from devxos.models.metrics import ReportMetrics

    d = asdict(metrics)

    if dup_result is not None:
        d["duplicate_block_rate"] = dup_result.duplicate_block_rate
        d["duplicate_block_count"] = dup_result.total_duplicate_blocks
        d["duplicate_median_block_size"] = dup_result.median_duplicate_block_size
        if dup_result.by_origin:
            d["duplicate_by_origin"] = {
                bo.origin: {
                    "commits_analyzed": bo.commits_analyzed,
                    "commits_with_duplicates": bo.commits_with_duplicates,
                    "duplicate_rate": bo.duplicate_rate,
                    "total_duplicate_blocks": bo.total_duplicate_blocks,
                    "median_block_size": bo.median_block_size,
                }
                for bo in dup_result.by_origin
            }

    if move_result is not None:
        d["moved_code_pct"] = move_result.moved_code_pct
        d["refactoring_ratio"] = move_result.refactoring_ratio
        if move_result.by_origin:
            d["move_by_origin"] = {
                bo.origin: {
                    "commits_analyzed": bo.commits_analyzed,
                    "commits_with_moves": bo.commits_with_moves,
                    "moved_lines": bo.moved_lines,
                    "total_changed_lines": bo.total_changed_lines,
                    "moved_code_pct": bo.moved_code_pct,
                }
                for bo in move_result.by_origin
            }

    if ops_result is not None:
        d["operation_distribution"] = {
            "added": ops_result.overall.pct_added,
            "deleted": ops_result.overall.pct_deleted,
            "updated": ops_result.overall.pct_updated,
            "moved": ops_result.overall.pct_moved,
            "duplicated": ops_result.overall.pct_duplicated,
        }
        d["operation_dominant"] = ops_result.overall.dominant_operation
        if ops_result.by_origin:
            d["operation_by_origin"] = {
                bo.origin: {
                    "added": bo.mix.pct_added,
                    "deleted": bo.mix.pct_deleted,
                    "updated": bo.mix.pct_updated,
                    "moved": bo.mix.pct_moved,
                    "duplicated": bo.mix.pct_duplicated,
                    "dominant": bo.mix.dominant_operation,
                    "commits_analyzed": bo.commits_analyzed,
                }
                for bo in ops_result.by_origin
            }

    if provenance is not None:
        overall = provenance.overall
        d["revision_age_distribution"] = {
            "under_2_weeks": overall.pct_under_2_weeks,
            "2_to_4_weeks": overall.pct_2_to_4_weeks,
            "1_to_12_months": overall.pct_1_to_12_months,
            "1_to_2_years": overall.pct_1_to_2_years,
            "over_2_years": overall.pct_over_2_years,
        }
        d["pct_revising_new_code"] = round(
            overall.pct_under_2_weeks + overall.pct_2_to_4_weeks, 3
        )
        d["pct_revising_mature_code"] = round(
            overall.pct_1_to_2_years + overall.pct_over_2_years, 3
        )
        if provenance.by_origin:
            d["provenance_by_origin"] = {
                bo.origin: {
                    "pct_new_code": round(
                        bo.distribution.pct_under_2_weeks + bo.distribution.pct_2_to_4_weeks, 3
                    ),
                    "pct_mature_code": round(
                        bo.distribution.pct_1_to_2_years + bo.distribution.pct_over_2_years, 3
                    ),
                    "median_age_days": bo.distribution.median_age_days,
                    "lines_sampled": bo.distribution.lines_sampled,
                    "commits_analyzed": bo.commits_analyzed,
                }
                for bo in provenance.by_origin
            }

    if new_churn is not None:
        d["new_code_churn_rate_2w"] = new_churn.new_code_churn_rate_2w
        d["new_code_churn_rate_4w"] = new_churn.new_code_churn_rate_4w
        if new_churn.by_origin:
            d["new_code_churn_by_origin"] = {
                bo.origin: {
                    "files_with_new_code": bo.files_with_new_code,
                    "files_churned_2w": bo.files_churned_2w,
                    "files_churned_4w": bo.files_churned_4w,
                    "churn_rate_2w": bo.churn_rate_2w,
                    "churn_rate_4w": bo.churn_rate_4w,
                }
                for bo in new_churn.by_origin
            }

    return ReportMetrics(**{k: v for k, v in d.items()})


def _is_git_repo(path: str) -> bool:
    """Check if path contains a .git directory."""
    return os.path.isdir(os.path.join(path, ".git"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="devxos",
        description=(
            "Engineering intelligence for the AI era. "
            "Analyzes a Git repository and generates an impact report "
            "measuring delivery signal vs noise."
        ),
        epilog=(
            "commands:\n"
            "  devxos login                          Connect to DevXOS platform\n"
            "  devxos auth status                    Show current auth config\n"
            "  devxos auth logout                    Remove saved credentials\n"
            "  devxos hook install <repo> [--auto-push]  Install AI commit tracking\n"
            "  devxos hook uninstall <repo>          Remove hooks from a repo\n"
            "  devxos hook status <repo>             Check hook installation\n"
            "  devxos push <metrics.json>            Push metrics file to platform\n"
            "  devxos upgrade                        Update to latest version\n"
            "  devxos uninstall                      Remove DevXOS from your machine\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=None,
        help="Path to a local Git repository",
    )
    parser.add_argument(
        "--org",
        default=None,
        help="Path to organization directory containing Git repositories",
    )
    parser.add_argument(
        "--repos",
        default=None,
        help="Comma-separated list of repo names to analyze (requires --org)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Lookback window in days (default: 90)",
    )
    parser.add_argument(
        "--churn-days",
        type=int,
        default=14,
        help="Churn detection window in days (default: 14)",
    )
    parser.add_argument(
        "--out",
        default="out",
        help="Output directory (default: out)",
    )
    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGS,
        default="en",
        help="Report language (default: en)",
    )
    parser.add_argument(
        "--trend",
        action="store_true",
        default=False,
        help="Enable trend analysis (compare recent vs baseline)",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=30,
        help="Recent window in days for trend analysis (default: 30)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        default=False,
        help="(default if logged in) Push metrics to DevXOS platform",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        default=False,
        help="Skip auto-push even if logged in (write to filesystem only)",
    )
    return parser.parse_args(argv)


def _run_single_repo(args: argparse.Namespace) -> None:
    """Run analysis on a single repository (original mode)."""
    analysis_start = time.time()
    s = get_strings(args.lang)

    repo = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo):
        print(s["cli_error_not_dir"].format(path=args.repo_path), file=sys.stderr)
        sys.exit(1)

    if not _is_git_repo(repo):
        print(s["cli_error_not_git"].format(path=args.repo_path), file=sys.stderr)
        sys.exit(1)

    repo_name = os.path.basename(repo)
    org_name = os.path.basename(os.path.dirname(repo))
    out_dir = os.path.join(os.path.abspath(args.out), f"{args.days}d")

    ctx = AnalysisContext(
        repo_path=repo,
        repo_name=repo_name,
        days=args.days,
        churn_days=args.churn_days,
        out_dir=out_dir,
        org_name=org_name,
        lang=args.lang,
    )

    # Check early if we'll push (to adjust output)
    from devxos.platform.config import get_auth
    will_push = not args.no_push and get_auth() is not None

    print(f"DevXOS {VERSION}")
    print(f"{s['cli_banner_repo']:<14}: {repo}")
    print(f"{s['cli_banner_lookback']:<14}: {args.days} {s['unit_days']}")
    print(f"{s['cli_banner_churn']:<14}: {args.churn_days} {s['unit_days']}")
    if not will_push:
        print(f"{s['cli_banner_output']:<14}: {out_dir}")
    print()

    # Step 1: Ingest commits
    print(s["cli_reading_commits"], end=" ", flush=True)
    with span("ingestion.commits", {"repo": repo_name, "days": args.days}):
        commits = read_commits(repo, days=args.days)
    print(s["cli_commits_found"].format(count=len(commits)))

    if not commits:
        print(s["cli_no_commits"])
        sys.exit(0)

    # Step 2: Fetch pull requests (optional, graceful fallback)
    print(s["cli_reading_prs"], end=" ", flush=True)
    with span("ingestion.pull_requests", {"repo": repo_name}):
        try:
            prs = read_pull_requests(repo, days=args.days)
        except Exception:
            prs = []
    if prs:
        print(s["cli_prs_found"].format(count=len(prs)))
    else:
        print(s["cli_prs_skipped"])

    # Step 3: Classify commits by intent
    print(s["cli_classifying"], end=" ", flush=True)

    # Step 4: Analyze and aggregate metrics
    with span("analysis.aggregate", {"repo": repo_name, "commits": len(commits)}):
        metrics = aggregate(commits, churn_days=args.churn_days, prs=prs or None)
    print(s["cli_classified"].format(count=len(commits)))

    if metrics.fix_latency_median_hours is not None:
        print(s["cli_fix_latency_computed"].format(
            median=metrics.fix_latency_median_hours,
            count=metrics.churn_events,
        ))
    else:
        print(s["cli_fix_latency_none"])

    # Step 5: Trend analysis (optional, opt-in)
    trend = None
    if args.trend:
        from devxos.analysis.trend_delta import compute_trend_delta

        print(s["cli_trend_analyzing"], end=" ", flush=True)
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.recent_days)
        recent_commits = [c for c in commits if c.date >= cutoff]
        recent_prs = [p for p in (prs or []) if p.created_at >= cutoff] or None

        recent_metrics = aggregate(
            recent_commits, churn_days=args.churn_days, prs=recent_prs,
        )
        trend = compute_trend_delta(
            baseline=metrics,
            recent=recent_metrics,
            baseline_days=args.days,
            recent_days=args.recent_days,
            lang=args.lang,
        )
        if trend.has_sufficient_data:
            print(s["cli_trend_done"].format(
                recent=args.recent_days, baseline=args.days,
            ))
        else:
            print(s["cli_trend_insufficient"].format(
                count=len(recent_commits),
            ))

    # Step 4b: Priming doc detection
    from devxos.analysis.priming_detector import detect_priming

    priming = detect_priming(repo)
    if priming.has_priming:
        file_list = ", ".join(f.path for f in priming.files)
        print(f"Priming docs detected: {file_list}")
    else:
        print("No priming docs detected.")

    # Step 4c: Code durability (git blame)
    from devxos.analysis.durability import calculate_durability
    from devxos.analysis.origin_classifier import classify_origins

    origin_classified = classify_origins(commits)
    durability = calculate_durability(repo, commits, origin_classified)
    if durability:
        print(f"Durability: {durability.files_analyzed} files analyzed via git blame.")
        metrics = _merge_durability(metrics, durability)
    else:
        print("Durability: skipped (insufficient multi-touch files).")

    # Step 4d: Diff-based code quality analyses
    from devxos.ingestion.diff_reader import read_commit_diffs
    from devxos.analysis.duplicate_detector import detect_duplicates
    from devxos.analysis.move_detector import detect_moves
    from devxos.analysis.operation_classifier import classify_operations
    from devxos.analysis.code_provenance import calculate_provenance
    from devxos.analysis.new_code_churn import calculate_new_code_churn

    print(s["cli_reading_diffs"], end=" ", flush=True)
    with span("analysis.diffs", {"repo": repo_name}):
        commit_diffs = read_commit_diffs(repo, commits)
    print(s["cli_diffs_analyzed"].format(count=len(commit_diffs)))

    dup_result = detect_duplicates(commit_diffs, origin_classified)
    if dup_result:
        print(s["cli_duplicates_found"].format(
            rate=dup_result.duplicate_block_rate,
            count=dup_result.total_duplicate_blocks,
        ))
    else:
        print(s["cli_duplicates_none"])

    move_result = detect_moves(commit_diffs, origin_classified, dup_result)
    if move_result:
        print(s["cli_moves_found"].format(pct=move_result.moved_code_pct))
    else:
        print(s["cli_moves_none"])

    ops_result = classify_operations(
        commits, commit_diffs, origin_classified, dup_result, move_result,
    )
    if ops_result:
        print(s["cli_operations_done"].format(dominant=ops_result.overall.dominant_operation))
    else:
        print(s["cli_operations_none"])

    # Step 4e: Code provenance (blame-based)
    provenance = calculate_provenance(repo, commits, origin_classified)
    if provenance:
        print(s["cli_provenance_done"].format(
            files=provenance.files_blamed,
            lines=provenance.overall.lines_sampled,
        ))
    else:
        print(s["cli_provenance_none"])

    # Step 4f: New code churn rate
    new_churn = calculate_new_code_churn(commits, origin_classified)
    if new_churn:
        print(s["cli_new_churn_done"].format(
            rate_2w=new_churn.new_code_churn_rate_2w,
            rate_4w=new_churn.new_code_churn_rate_4w,
        ))
    else:
        print(s["cli_new_churn_none"])

    # Merge all quality metrics
    metrics = _merge_quality_metrics(
        metrics, dup_result, move_result, ops_result, provenance, new_churn,
    )

    # Step 5b: Adoption timeline detection
    adoption = None
    from devxos.analysis.adoption_detector import detect_adoption, MIN_AI_COMMITS
    from devxos.models.adoption import AdoptionResult

    event, pre_commits, post_commits = detect_adoption(commits)
    if event is None:
        print(s["cli_adoption_none"])
    elif event.adoption_confidence == "insufficient":
        print(s["cli_adoption_insufficient"].format(
            count=event.total_ai_commits, min=MIN_AI_COMMITS,
        ))
    elif not pre_commits:
        print(s["cli_adoption_no_pre"])
    else:
        print(s["cli_adoption_detected"].format(
            confidence=event.adoption_confidence,
            date=event.first_ai_commit_date.strftime("%Y-%m-%d"),
        ))

        # Split PRs by adoption date
        pre_prs = [p for p in (prs or []) if p.created_at < event.adoption_ramp_start] or None
        post_prs = [p for p in (prs or []) if p.created_at >= event.adoption_ramp_start] or None

        pre_metrics = aggregate(pre_commits, churn_days=args.churn_days, prs=pre_prs)
        post_metrics = aggregate(post_commits, churn_days=args.churn_days, prs=post_prs)

        # Compute day spans from commit date ranges
        pre_days = max(1, (pre_commits[-1].date - pre_commits[0].date).days)
        post_days = max(1, (post_commits[-1].date - post_commits[0].date).days)

        from devxos.analysis.trend_delta import compute_trend_delta

        comparison = compute_trend_delta(
            baseline=pre_metrics,
            recent=post_metrics,
            baseline_days=pre_days,
            recent_days=post_days,
            lang=args.lang,
        )

        adoption = AdoptionResult(
            event=event,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            comparison=comparison,
            pre_days=pre_days,
            post_days=post_days,
        )

    # Step 5c: Velocity analysis
    velocity = None
    from devxos.analysis.velocity import compute_velocity, MIN_COMMITS_FOR_VELOCITY

    velocity = compute_velocity(commits, churn_days=args.churn_days)
    if velocity:
        print(s["cli_velocity_computed"].format(
            cpw=velocity.overall_commits_per_week,
            trend=velocity.velocity_trend,
        ))
    else:
        print(s["cli_velocity_skipped"].format(min=MIN_COMMITS_FOR_VELOCITY))

    # Step 6: Generate narrative
    narrative = generate_narrative(metrics, lang=args.lang, trend=trend)

    # Step 7: Write output
    # If pushing, write to a temp dir (don't pollute the repo)
    import tempfile
    if will_push:
        tmp_out = tempfile.mkdtemp(prefix="devxos-")
        actual_out_dir = ctx.out_dir
        ctx = AnalysisContext(
            repo_path=ctx.repo_path, repo_name=ctx.repo_name,
            org_name=ctx.org_name, out_dir=tmp_out,
            days=ctx.days, churn_days=ctx.churn_days, lang=ctx.lang,
        )

    print(s["cli_writing_report"], end=" ", flush=True)
    report_path, metrics_path = write_output(
        ctx, metrics, narrative_sections=narrative, trend=trend,
        adoption=adoption, velocity=velocity, priming=priming,
    )
    print(s["cli_done"])

    # Record telemetry
    record_duration("devxos.analysis.duration_seconds", analysis_start, {"repo": repo_name})
    record_counter("devxos.analysis.commits_analyzed", len(commits), {"repo": repo_name})
    record_metric("devxos.metrics.stabilization_ratio", metrics.stabilization_ratio, {"repo": repo_name})
    record_metric("devxos.metrics.churn_events", float(metrics.churn_events), {"repo": repo_name})
    record_metric("devxos.metrics.revert_rate", metrics.revert_rate, {"repo": repo_name})

    # Push or write to filesystem
    if will_push:
        import shutil
        # Extract unique commit authors using GitHub API to resolve real names.
        import re
        import subprocess

        def _gh_username(email: str) -> str | None:
            """Extract GitHub username from noreply email."""
            m = re.match(r"(?:\d+\+)?(.+)@users\.noreply\.github\.com$", email)
            return m.group(1) if m else None

        def _resolve_gh_name(username: str) -> str | None:
            """Resolve GitHub username to real name via gh API."""
            try:
                r = subprocess.run(
                    ["gh", "api", f"users/{username}", "-q", ".name"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            return None

        # Step 1: Collect all unique emails and resolve GitHub usernames
        email_to_names: dict[str, set[str]] = {}
        gh_usernames: set[str] = set()

        for c in commits:
            email = (c.author_email or "").lower()
            if email:
                email_to_names.setdefault(email, set()).add(c.author)
                gh = _gh_username(email)
                if gh:
                    gh_usernames.add(gh)

        # Step 2: Resolve GitHub usernames to real names
        gh_name_cache: dict[str, str] = {}
        for username in gh_usernames:
            real_name = _resolve_gh_name(username)
            if real_name:
                gh_name_cache[username.lower()] = real_name

        # Step 3: Build identity map — group by GitHub username or email local
        identity_names: dict[str, str] = {}  # key → best name
        for email, names in email_to_names.items():
            gh = _gh_username(email)
            key = (gh or email.split("@")[0]).lower()

            # Best name: GitHub API name > longest git name
            best = gh_name_cache.get(key) or max(names, key=len)
            if key in identity_names:
                # Keep the one with spaces (real name) or longest
                old = identity_names[key]
                if " " in best and " " not in old:
                    identity_names[key] = best
                elif len(best) > len(old):
                    identity_names[key] = best
            else:
                identity_names[key] = best

        active_users = sorted(set(identity_names.values()))
        with span("push", {"repo": repo_name}):
            _push_after_analysis(metrics_path, repo_name, args.days, active_users=active_users)
        record_counter("devxos.push.success", 1, {"repo": repo_name})
        shutil.rmtree(tmp_out, ignore_errors=True)
    else:
        print()
        print(f"{s['cli_label_report']:<14}: {report_path}")
        print(f"{s['cli_label_metrics']:<14}: {metrics_path}")

    flush()


def _run_org(args: argparse.Namespace) -> None:
    """Run analysis across all repos in an organization directory."""
    from devxos.org_runner import run_org_analysis

    s = get_strings(args.lang)

    org_path = os.path.abspath(args.org)
    if not os.path.isdir(org_path):
        print(s["cli_error_org_not_dir"].format(path=args.org), file=sys.stderr)
        sys.exit(1)

    out_dir = os.path.join(os.path.abspath(args.out), f"{args.days}d")

    filter_repos = None
    if args.repos:
        filter_repos = [r.strip() for r in args.repos.split(",") if r.strip()]

    org_name = os.path.basename(os.path.normpath(org_path))

    print(f"DevXOS {VERSION}")
    print(f"{s['cli_org_banner']:<14}: {org_name}")
    print(f"{s['cli_banner_lookback']:<14}: {args.days} {s['unit_days']}")
    print(f"{s['cli_banner_churn']:<14}: {args.churn_days} {s['unit_days']}")
    print(f"{s['cli_banner_output']:<14}: {out_dir}")
    print()

    run_org_analysis(
        org_path=org_path,
        days=args.days,
        churn_days=args.churn_days,
        out_dir=out_dir,
        lang=args.lang,
        trend_enabled=args.trend,
        recent_days=args.recent_days,
        filter_repos=filter_repos,
    )


def _run_login(argv: list[str]) -> None:
    """Handle `devxos login` — browser-based auth flow."""
    from devxos.platform.auth import browser_login, manual_login

    # Parse optional flags
    server = None
    token = None
    i = 0
    while i < len(argv):
        if argv[i] == "--server" and i + 1 < len(argv):
            server = argv[i + 1]
            i += 2
        elif argv[i] == "--token" and i + 1 < len(argv):
            token = argv[i + 1]
            i += 2
        else:
            i += 1

    # Manual token login (for CI/CD)
    if token:
        s = server or "https://devxos.ai"
        if not manual_login(s, token):
            sys.exit(1)
        return

    # Browser login
    if not browser_login(server):
        sys.exit(1)


def _run_auth(argv: list[str]) -> None:
    """Handle `devxos auth login|status|logout` subcommands."""
    from devxos.platform.config import load_config, save_config, get_auth, get_org_slug

    if not argv:
        print("Usage: devxos auth <login|status|logout>", file=sys.stderr)
        sys.exit(1)

    action = argv[0]

    if action == "login":
        # Delegate to the browser login flow
        _run_login(argv[1:])

    elif action == "status":
        auth = get_auth()
        if auth:
            server, token = auth
            org = get_org_slug()
            print(f"Server: {server}")
            print(f"Token:  {token[:12]}...")
            if org:
                print(f"Org:    {org}")
        else:
            print("Not authenticated. Run: devxos login")

    elif action == "logout":
        config = load_config()
        config.pop("token", None)
        config.pop("org_slug", None)
        save_config(config)
        print("Logged out. Token and org removed from config.")

    else:
        print(f"Unknown auth action: {action}", file=sys.stderr)
        print("Usage: devxos auth <login|status|logout>", file=sys.stderr)
        sys.exit(1)


def _run_push(argv: list[str]) -> None:
    """Handle `devxos push [metrics.json]` subcommand."""
    from devxos.platform.config import get_auth
    from devxos.platform.push import push_metrics

    auth = get_auth()
    if not auth:
        print("Not authenticated. Run: devxos auth login", file=sys.stderr)
        sys.exit(1)

    server, token = auth

    if not argv:
        print("Usage: devxos push <metrics.json> [--repo <name>]", file=sys.stderr)
        sys.exit(1)

    metrics_path = argv[0]
    if not os.path.exists(metrics_path):
        print(f"File not found: {metrics_path}", file=sys.stderr)
        sys.exit(1)

    # Parse optional --repo flag
    repo_name = None
    if "--repo" in argv:
        idx = argv.index("--repo")
        if idx + 1 < len(argv):
            repo_name = argv[idx + 1]

    # Infer repo name from filename if not provided
    if not repo_name:
        basename = os.path.basename(metrics_path)
        # Pattern: {org}-{repo}-metrics.json
        if basename.endswith("-metrics.json"):
            parts = basename[:-len("-metrics.json")].split("-", 1)
            repo_name = parts[1] if len(parts) > 1 else parts[0]
        else:
            repo_name = basename.replace(".json", "")

    print(f"Pushing to {server}...")
    print(f"Repository: {repo_name}")

    try:
        result = push_metrics(
            server_url=server,
            token=token,
            repository=repo_name,
            metrics_path=metrics_path,
            cli_version=VERSION,
        )
        print(f"Push successful.")
        print(f"  Run ID:  {result.get('run_id', 'unknown')}")
        print(f"  Repo ID: {result.get('repository_id', 'unknown')}")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _push_after_analysis(
    metrics_path: str,
    repo_name: str,
    window_days: int,
    active_users: list[str] | None = None,
) -> None:
    """Push metrics to platform after analysis."""
    from devxos.platform.config import get_auth, get_github_user
    from devxos.platform.push import push_metrics

    auth = get_auth()
    if not auth:
        print("\n--push: Not authenticated. Run: devxos login")
        return

    server, token = auth
    github_user = get_github_user()
    print(f"\nPushing to {server}...", end=" ", flush=True)

    try:
        result = push_metrics(
            server_url=server,
            token=token,
            repository=repo_name,
            metrics_path=metrics_path,
            window_days=window_days,
            github_user=github_user,
            active_users=active_users,
            cli_version=VERSION,
        )
        print(f"done. (run: {result.get('run_id', '?')[:8]})")
    except RuntimeError as e:
        print(f"failed: {e}")


def _run_hook(argv: list[str]) -> None:
    """Handle `devxos hook install|uninstall|status` subcommands."""
    from devxos.hooks.manager import install, uninstall, status

    if not argv:
        print("Usage: devxos hook <install|uninstall|status> [repo_path]", file=sys.stderr)
        sys.exit(1)

    action = argv[0]
    repo_path = os.path.abspath(argv[1]) if len(argv) > 1 else os.getcwd()

    if action == "install":
        try:
            hook_path = install(repo_path)
            print(f"DevXOS hook installed: {hook_path}")
            print("AI agent detection enabled for: $AI_AGENT, $CLAUDE_CODE, $CURSOR_SESSION, $WINDSURF_SESSION")
        except FileExistsError:
            print("DevXOS hook is already installed.")
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

    elif action == "uninstall":
        if uninstall(repo_path):
            print("DevXOS post-commit hook removed.")
        else:
            print("DevXOS hook is not installed.")

    elif action == "status":
        info = status(repo_path)
        if info["installed"]:
            print(f"DevXOS hook: installed")
            print(f"Hook path:   {info['hook_path']}")
        else:
            print(f"DevXOS hook: not installed")
            print(f"Hooks dir:   {info['hooks_dir']}")

    else:
        print(f"Unknown hook action: {action}", file=sys.stderr)
        print("Usage: devxos hook <install|uninstall|status> [repo_path]", file=sys.stderr)
        sys.exit(1)


def _run_uninstall() -> None:
    """Remove DevXOS from the system."""
    import shutil

    install_dir = os.path.expanduser("~/.devxos")
    bin_wrapper = os.path.join(install_dir, "bin", "devxos")

    print("")
    print("  This will remove DevXOS from your machine:")
    print("")
    if os.path.isdir(install_dir):
        print(f"    - Delete {install_dir}/ (venv, config, bin)")
    else:
        print(f"    - {install_dir}/ not found")

    # Check shell rc files for PATH entry
    shell_rc_files = [
        os.path.expanduser("~/.zshrc"),
        os.path.expanduser("~/.bash_profile"),
        os.path.expanduser("~/.bashrc"),
        os.path.expanduser("~/.profile"),
    ]
    rc_with_devxos = []
    for rc in shell_rc_files:
        if os.path.isfile(rc):
            with open(rc) as f:
                if ".devxos/bin" in f.read():
                    rc_with_devxos.append(rc)

    if rc_with_devxos:
        print(f"    - Remove PATH entry from: {', '.join(rc_with_devxos)}")

    # Check pipx
    is_pipx = False
    if not os.path.isdir(install_dir):
        # Might be installed via pipx
        pipx_path = os.path.expanduser("~/.local/pipx/venvs/devxos")
        if os.path.isdir(pipx_path):
            is_pipx = True
            print(f"    - Uninstall pipx package: devxos")

    print("")
    try:
        reply = input("  Proceed? [y/N] ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if reply.lower() not in ("y", "yes"):
        print("  Cancelled.")
        return

    # Remove install dir
    if os.path.isdir(install_dir):
        shutil.rmtree(install_dir)
        print(f"  Removed {install_dir}/")

    # Clean shell rc files
    for rc in rc_with_devxos:
        with open(rc) as f:
            lines = f.readlines()
        with open(rc, "w") as f:
            skip_next = False
            for line in lines:
                if "# DevXOS" in line:
                    skip_next = True
                    continue
                if skip_next and ".devxos/bin" in line:
                    skip_next = False
                    continue
                skip_next = False
                f.write(line)
        print(f"  Cleaned {rc}")

    # Pipx uninstall
    if is_pipx:
        os.system("pipx uninstall devxos 2>/dev/null")
        print("  Uninstalled pipx package")

    print("")
    print("  DevXOS has been removed. Restart your terminal to complete.")
    print("")


def _run_upgrade() -> None:
    """Upgrade DevXOS CLI to the latest version."""
    import subprocess

    install_dir = os.path.expanduser("~/.devxos")
    venv_pip = os.path.join(install_dir, "venv", "bin", "pip")
    repo_url = "git+https://github.com/sunnysystems/devxos-cli.git@main"

    # Detect install method
    is_pipx = not os.path.isdir(install_dir) and os.path.isdir(
        os.path.expanduser("~/.local/pipx/venvs/devxos")
    )

    print(f"\n  DevXOS {VERSION}")
    print(f"  Checking for updates...\n")

    try:
        if is_pipx:
            subprocess.run(["pipx", "upgrade", "devxos"], check=True)
        elif os.path.isfile(venv_pip):
            subprocess.run(
                [venv_pip, "install", "--quiet", "--upgrade", repo_url],
                check=True,
            )
        else:
            print("  Could not detect install method.", file=sys.stderr)
            print("  Reinstall with: curl -fsSL https://devxos.ai/install.sh | sh")
            sys.exit(1)

        # Show new version
        result = subprocess.run(
            [os.path.join(install_dir, "venv", "bin", "devxos") if not is_pipx else "devxos",
             ".", "--help"],
            capture_output=True, text=True,
        )
        print("  Upgrade complete.\n")
    except subprocess.CalledProcessError as e:
        print(f"  Upgrade failed: {e}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    # Intercept subcommands before argparse (they use different arg structures)
    raw_argv = argv if argv is not None else sys.argv[1:]
    if raw_argv and raw_argv[0] == "upgrade":
        _run_upgrade()
        return
    if raw_argv and raw_argv[0] == "uninstall":
        _run_uninstall()
        return
    if raw_argv and raw_argv[0] == "hook":
        _run_hook(raw_argv[1:])
        return
    if raw_argv and raw_argv[0] == "login":
        _run_login(raw_argv[1:])
        return
    if raw_argv and raw_argv[0] == "auth":
        _run_auth(raw_argv[1:])
        return
    if raw_argv and raw_argv[0] == "push":
        _run_push(raw_argv[1:])
        return

    args = parse_args(argv)
    s = get_strings(args.lang)

    # Validate mutually exclusive modes
    if args.org and args.repo_path:
        print(s["cli_error_org_mutex"], file=sys.stderr)
        sys.exit(1)

    if args.org:
        _run_org(args)
    elif args.repo_path:
        _run_single_repo(args)
    else:
        print("Error: either repo_path or --org is required.", file=sys.stderr)
        sys.exit(1)
