# Changelog

All notable changes to DevXOS are documented here.

---

## v0.6 — Code Quality Intelligence (2026-03-31)

5 new analysis modules inspired by GitClear's "AI Copilot Code Quality 2025" research (211M lines analyzed). Total: 20 analysis modules.

### Code Quality Analysis
- **Duplicate block detection** — find identical 5+ line blocks across files within commits, by origin
- **Code movement / refactoring health** — detect lines moved between files (refactoring signal) + refactoring ratio (moved / (moved + duplicated))
- **Code provenance** — age of revised code via git blame on parent commits, with age bracket distribution
- **New code churn rate** — % of newly added code re-modified within 2 weeks and 4 weeks, by origin
- **Operation classification** — classify commit changes into added/deleted/updated/moved/duplicated with dominant operation

### Infrastructure
- **Diff reader** — new `git show` based ingestion for parsing actual line content from commits

### Documentation
- Updated METHODOLOGY.md with 5 new metric sections and research citations
- Updated VISION.md, ONE-PAGER.md, CHANGELOG.md

---

## v0.5 — Signal Discovery Complete (2026-03-27)

Stage 0 complete. 15 analysis modules validated on 58 repositories.

### AI Impact Analysis
- **Origin classifier** with tool-level detection (Copilot, Claude, Cursor, Codeium, Tabnine, Amazon Q, Gemini)
- **Code durability** — line survival rate via git blame, by origin
- **Correction cascades** — fix-following pattern detection by origin
- **Acceptance rate** — code review survival by origin and AI tool
- **Origin funnel** — commit -> PR -> stabilized -> lines surviving
- **Attribution gap** — flag unattributed high-velocity commits
- **AI detection coverage** metric with low-coverage caveat

### Temporal Intelligence
- **Activity timeline** — weekly breakdown of commits, LOC, intent, origin, and quality
- **Delivery pulse** — visual heatmap of weekly health
- **Pattern detection** — burst-then-fix, quiet periods, AI ramps, intent shifts

### Structural Analysis
- **Churn investigation** — top churning files with chains (feat->fix->fix) + file coupling detection
- **Stability map** — per-directory stabilization and churn aggregation
- **Knowledge priming detection** — scan for CLAUDE.md, .cursor/rules, copilot-instructions

### Infrastructure
- **prepare-commit-msg hook** — `devxos hook install/uninstall/status`
- Detects $CLAUDE_CODE, $AI_AGENT, $CURSOR_SESSION, $WINDSURF_SESSION
- Compatible with existing hooks (husky, lefthook, git-ai symlinks)

### Documentation
- Knowledge Priming research document (SUN-135)
- Updated VISION.md with validated findings
- Complete README rewrite

---

## v0.4b — Organization Intelligence (2026-03-22)

### Added
- **Org execution mode** — `devxos --org /path` analyzes all repos and generates cross-repo report
- **Cross-repo intelligence** — change attribution, attention signals, delivery narrative
- **Org report** with repository overview table (commits, stabilization, delta, PRs, attention)
- **Adoption timeline** — detect AI adoption inflection point and before/after comparison
- **Delivery velocity** — commits/week trend with velocity-durability correlation
- **Fix latency** — time-to-rework analysis by origin (fast/medium/slow buckets)
- **Commit shape** — structural profile by origin (focused, spread, bulk, surgical)
- **AI detection coverage** metric

### Fixed
- Git log parser: extract co-authors from multi-line commit bodies
- PR fetch limit scaling with analysis window
- Two-pass PR fetch strategy for large repos (avoids GitHub 504 timeouts)

---

## v0.4a — Attention Signals (2026-03-20)

### Added
- **Co-occurrence detection** — multi-metric reinforcing patterns (stability cascade, fix instability, workflow slowdown, recovery)
- **Attention summary** — 1-sentence dominant pattern description

---

## v0.3 — Trend Analysis (2026-03-18)

### Added
- **Trend delta** — compare recent window vs baseline (opt-in via `--trend`)
- **Delta classification** — stable, notable, significant per metric
- **Trend findings** in narrative section

---

## v0.2.1 — Intent & PR Lifecycle (2026-03-15)

### Added
- **Intent classification** — Feature, Fix, Refactor, Config, Unknown
- **Intent metrics** — distribution, churn by intent, stabilization by intent
- **PR lifecycle** — merge time, review rounds, single-pass rate, PR size
- **Narrative engine** — Key Findings with systemic context

---

## v0.1 — Initial Release (2026-02-23)

### Added
- Git commit ingestion via `git log`
- Stabilization ratio calculation
- Churn detection (file re-modification within window)
- Revert detection by commit message pattern
- Markdown report + JSON metrics output
- PT-BR language support
