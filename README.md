# DevXOS CLI

Engineering intelligence for the AI era. Analyze Git repositories to measure what survives, not what ships.

DevXOS examines your repository's commit history to distinguish **durable engineering outcomes** (signal) from **corrective or unstable activity** (noise). Zero dependencies beyond Python. Zero cloud required.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/sunnysystems/devxos-cli/main/install/install.sh | sh
```

Or manually with pip:

```bash
pip install git+https://github.com/sunnysystems/devxos-cli.git
```

Requires Python 3.11+.

## Usage

Analyze a single repository:

```bash
devxos /path/to/repo
```

Analyze all repos in a directory:

```bash
devxos --org /path/to/org
```

With temporal trend analysis:

```bash
devxos /path/to/repo --trend
```

### Options

| Flag | Description |
|------|-------------|
| `--window N` | Analysis window in days (default: 90) |
| `--trend` | Enable temporal trend analysis |
| `--format md\|json` | Output format (default: md) |
| `--out DIR` | Output directory (default: ./out) |
| `--lang en\|pt-br\|es` | Report language |
| `--org` | Treat path as directory of repos |
| `--push` | Push results to DevXOS platform |
| `--token TOKEN` | API token for platform push |

## What it measures

### Stabilization & Churn
- **Stabilization ratio** — percentage of commits that remain stable (not reverted or heavily modified)
- **Churn detection** — files repeatedly modified within short timeframes
- **Revert rate** — frequency of revert commits

### Code Origin & Intent
- **Origin classification** — human vs AI-assisted code detection
- **Intent classification** — feature, fix, refactor, test, docs, chore
- **Acceptance rate** — single-pass vs multi-iteration pull requests

### Durability & Quality
- **Code durability** — survival rate of introduced lines over time
- **Fix latency** — time between bug introduction and fix
- **Cascade detection** — commits that trigger chains of follow-up fixes
- **Duplicate detection** — repeated patterns across the codebase

### Delivery Intelligence
- **PR lifecycle** — time-to-merge, review patterns, merge frequency
- **Activity timeline** — contribution patterns over time
- **Velocity metrics** — throughput and cycle time

## Output

DevXOS generates Markdown reports with metrics, charts, and narrative analysis. See [examples/sample-report.md](examples/sample-report.md) for a full example.

## Git Hook

Install a prepare-commit-msg hook that tags AI-assisted commits:

```bash
devxos hook install /path/to/repo
```

This enables more accurate origin classification in future analyses.

## Platform Integration

Push analysis results to the [DevXOS platform](https://devxos.ai) for dashboards and temporal tracking:

```bash
devxos /path/to/repo --push --token dxos_your_token_here
```

## License

MIT
