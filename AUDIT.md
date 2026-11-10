# Dautu repository audit

Branch: `codex/dautu-audit-hardening`

## Changes made in this branch

- [x] Fail the HTML build when `FIREBASE_CONFIG` is missing, malformed, or lacks required Firebase fields. This prevents a broken authentication configuration from being published.
- [x] Fail closed in the generated `index.html`: if the Firestore account/role lookup fails, the app does not proceed to load screener data.
- [x] Remove the artificial -50% / +100% clamp from historical CAGR. Reject non-finite and non-positive endpoint prices instead of silently distorting returns.
- [x] Add regression tests for CAGR bounds/invalid prices and Firebase configuration validation.
- [x] Add a Python test workflow for pull requests and pushes to the maintenance branch.
- [x] Add `.gitignore` entries for Python bytecode, virtual environments, local secrets, and editor files.
- [x] Correct the README commands to use the actual `analyze_ai.py` entry point.

## Phase 2: financial metric consistency

- Extracted BCTC calculations into financial_metrics.py so the formulas can be tested independently of the market-data crawler.
- Added cfo_ttm: sum CFO over the latest four consecutive quarter periods, matching the period basis used for net_profit_ttm.
- Both TTM fields remain null unless all four consecutive periods exist. The extractor no longer substitutes an older quarter when latest-quarter CFO is absent.
- The screener cash-conversion bonus now compares CFO TTM with net-profit TTM, not latest-quarter CFO with four-quarter profit.
- The old debt_to_equity field is retained for compatibility, but explicitly documented and surfaced as total liabilities/equity (liabilities_to_equity), not interest-bearing debt/equity.
- The UI now displays CFO TTM and the accurate liabilities/equity label.
- Added tests for four-quarter aggregation, missing quarter handling, no fallback to stale CFO, non-finite values, and screener scoring.

Important assumption: the provider's period='quarter' cash-flow rows are treated as standalone quarterly values. This matches the inspected Q1–Q3 sample patterns, but any provider restatement or cumulative annual Q4 representation must be detected before extending this formula to other statement sources.

## Phase 2: GitHub Actions safety

- Production data-generation workflows now run only on main; the render and Quant workflows also restrict push triggers to main.
- The Quant and AI workflows share a concurrency group because both update data.json.
- The render workflow has its own concurrency group because it updates generated HTML and simulator outputs.
- Data jobs refresh from the latest main revision before running, and failed rebases are no longer swallowed as successful operations.
- A render workflow run on the maintenance branch exposed the old unsafe rebase/push behavior. It conflicted while rebasing and did not push; branch restrictions and explicit failure handling have since been added.

## Phase 3: sector mapping integrity

- Compared the 99 unique symbols in the BCTC crawler list against the screener's sector map.
- Found 13 unmapped symbols and one duplicate assignment (PHR).
- Removed PHR's duplicate real-estate mapping; it now resolves once to cyclical materials.
- Unmapped symbols now appear as CHUA_PHAN_LOAI instead of being silently assigned to defensive manufacturing/consumer.
- Unclassified symbols do not receive the sector-specific score component until their business sector and suitable thresholds are reviewed.
- Added SECTOR_MAPPING_REVIEW.md with the symbols requiring manual classification.

## Phase 4: non-finite data handling

- Normalize optional CFO, TTM profit, liabilities/equity, and gross-margin fields before screener scoring.
- Convert NaN and infinite optional metrics to null instead of allowing them into the result payload.
- Export screener JSON with allow_nan=false so non-standard JSON numbers fail loudly instead of being published.

## Phase 5: duplicate-period safeguards and authentication review

- Quarterly cash-flow and net-profit extraction now rejects duplicate observations for the same quarter instead of silently taking the first row.
- Added regression coverage to ensure duplicate CFO or profit observations invalidate the affected latest-quarter/TTM metric.
- Added SECURITY_REVIEW.md documenting the verified browser-side auth flow, the conditional privilege-escalation risk if Firestore rules are permissive, the target authorization model, and a safe migration checklist.
- No production Firestore Rules were changed: deployed rules and trusted admin identity are not accessible from this repository review.

## Phase 6: Firestore rules hardening candidate

- Reviewed the Firestore Rules supplied by the repository owner.
- Identified broad signed-in reads of all allowed_users documents, unconstrained client-supplied expiry on create, and overly broad owner updates.
- Added firestore.rules candidate: owner-only account get, admin-only collection listing, strict user-only self-registration, seven-day maximum expiry using server request.time, admin-only account updates, with client-side deletion disabled, and verified-email requirement for the allow-listed admin.
- Updated frontend account creation and admin extension to store Firestore Timestamp values instead of ISO strings.
- Documented migration requirements and deployment blockers in SECURITY_REVIEW.md.
- Candidate rules are not deployed. The frontend now denies login when an account record is missing or has invalid expiry, and no longer silently recreates deleted account records.
- Registration guards the auth-state callback while creating the trial record to avoid a duplicate Firestore write.
- Added Firebase Emulator authorization tests covering unauthenticated access, owner-only reads, admin-only list, verified-admin requirement, self-registration limits, user update/delete denial, admin operations, and UID-scoped watchlists.
- CI now runs those emulator tests. Their result must be checked before the rules candidate is considered validated.

## Confirmed findings requiring a follow-up phase

### Authentication and authorization

- The repository now contains a candidate `firestore.rules` and `firebase.json` emulator configuration. The deployed Firebase rules still cannot be inspected or changed from this repository.
- The browser currently reads the `allowed_users` document and uses its `role` / `expiresAt` fields to decide what to show. Browser-side checks are not an authorization boundary. Firestore rules or a trusted backend must enforce who can read and modify account records.
- Registration and account administration still write directly from the browser. The candidate rules constrain these writes, but the emulator suite and live Admin bootstrap must be validated before deployment.
- `login.html` contains a Firebase configuration for a different Firebase project from the generated `index.html`. Confirm whether `login.html` is still deployed/used before aligning or retiring it.
- Firebase client configuration values are public identifiers, not server secrets. The security boundary must be enforced by Firebase Auth, Firestore Rules, and/or a trusted backend.

### Financial-data correctness

- `fetch_data_local.py` currently exposes `cfo_latest` and `net_profit_ttm` to the screener, and the screener compares them in a cash-flow bonus rule. CFO and net profit are now both aggregated over four consecutive quarter labels. The calculation still depends on the data provider returning standalone quarterly cash-flow figures for each quarter.
- `debt_to_equity` is currently calculated as total liabilities / equity. This is a liabilities-to-equity ratio, not necessarily interest-bearing debt / equity. Rename or redefine only after checking the source line items and sector-specific meaning.
- Missing financial values are frequently defaulted to zero. This conflates unavailable data with a genuine zero and can affect scoring. A schema/data-quality migration should introduce explicit missing-value states before changing scores.
- The screener's fallback sector currently classifies unknown tickers as defensive manufacturing/consumer. An explicit unknown sector is safer, but changing it may alter existing ranking behavior and should be covered by a reviewed mapping for all tracked symbols.

### Historical-return interpretation

- CAGR is calculated from mean close prices in the first and last available quarters in the five-year window. It is a price-return approximation, not a dividend-reinvested total-return backtest.
- Corporate actions, adjusted-price semantics, and incomplete history coverage should be validated against the data provider before presenting the figure as investor total return.
- Removing the arbitrary clamp preserves mathematically calculated extreme returns; it does not itself validate the underlying market data.

### CI and runtime

- The existing data-generation workflows write to the same default branch. Their commit/push behavior should be consolidated or made conflict-safe in a separate change after reviewing the PC-side auto-push scripts.
- The test workflow checks Python regressions, a Quant Screener smoke test, and candidate Firestore rules in the Emulator. It is not a full integration test of live data crawling, AI provider calls, Firebase Authentication, or the production website.
- `requirements.txt` already includes `vnstock`; no dependency change was necessary for that package.

## Validation performed

- CI compiles Python sources and runs regression tests for configuration validation, CAGR, financial metric aggregation, and screener cash-conversion scoring.
- CI also runs the Quant Screener against checked-in data and the Firestore Rules Emulator authorization suite.
- The current branch's CI result must be checked after the latest commits; adding a test workflow is not evidence that the tests passed.
- Production Firebase rules, secrets, deployed Authentication state, and provider credentials were not accessible through this repository review and have not been changed.


## Phase 7: consolidate the legacy login entry point

- Found that root `login.html` was a stale second copy of the app, configured for the unrelated Firebase project `hoc-tieng-trung-64b8d`.
- The legacy page also used a different account collection on registration and continued loading app data when Firestore authorization failed.
- Replaced the duplicate page with a redirect to the canonical `index.html`, preserving query parameters and fragments.
- This removes the conflicting client-side entry point from the maintenance branch; it does not modify live Firebase settings or account records.

- Added a regression test ensuring the legacy `login.html` cannot reintroduce a second Firebase project or old authorization path.
