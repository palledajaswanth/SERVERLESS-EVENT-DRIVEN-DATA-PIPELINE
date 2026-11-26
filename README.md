# Serverless Event-Driven Data Pipeline

End-to-end capstone implementation with automated AWS infrastructure creation, an always-on baseline, deterministic workload generation, raw traces, KPI experiments, five negative tests, analytics, dashboarding, evidence hashing, and one-command cleanup.

## Architecture

```text
Deterministic Event Generator
          |
          +-------------------------+-------------------------------+
          |                         |                               |
          v                         v                               |
Always-on baseline            API Gateway                          |
FastAPI + SQLite                   |                               |
(local Docker)                     v                               |
                              Ingestion Lambda                     |
                                   |                               |
                                   v                               |
                                  SQS -----> DLQ                   |
                                   |                               |
                                   v                               |
                             Transformer Lambda                    |
                               |           |                       |
                               v           v                       |
                              S3       DynamoDB                    |
                               |                                   |
                               v                                   |
                         S3 sync + DuckDB                          |
                               |                                   |
                               v                                   |
                      Streamlit/Plotly Dashboard                   |
                                                                   |
CloudWatch <------ Lambda/SQS operational telemetry ---------------+
```

## AWS resources created automatically

Terraform creates:

- API Gateway HTTP API (`POST /events`)
- AWS Lambda ingestion function
- Amazon SQS event queue
- Amazon SQS dead-letter queue
- AWS Lambda transformation/storage function
- Amazon S3 event bucket with versioning, encryption, lifecycle and public-access blocking
- Amazon DynamoDB event-status/idempotency index
- IAM roles and least-privilege inline policies for both Lambdas
- CloudWatch log groups
- CloudWatch alarms
- CloudWatch operations dashboard
- Lambda-to-SQS event source mapping

The S3 bucket is account/region-qualified to avoid global name collisions.

## Idempotency and duplicate safety

The transformer stores each event under a deterministic S3 key containing the event ID and uses `IfNoneMatch="*"`. SQS retry of the same event therefore cannot create a second object. DynamoDB records the final `STORED` status, S3 key and ETag. This design makes duplicate delivery observable while keeping the stored result idempotent.

## Local software

Required:

- Windows 10/11 with PowerShell
- Python 3.12
- Git
- AWS CLI v2
- Terraform >= 1.6
- Docker Desktop
- VS Code is recommended

The first-time setup script can install missing command-line prerequisites through `winget`.

## Security: do not put AWS secrets in this project

Do **not** place an AWS access key or secret key in source code, Terraform files, JSON, `.env`, GitHub, or chat messages.

Configure authentication locally, for example:

```powershell
aws configure
```

or authenticate with AWS SSO and set the desired profile:

```powershell
$env:AWS_PROFILE="your-profile"
aws sts get-caller-identity
```

Use a non-root AWS identity. The deploying identity needs permission to create/manage the AWS services listed above, including IAM roles/policies. `pricing:GetProducts` is optional but recommended for the automated cost guardrail.

## Fastest path: first run

Open the extracted project folder in VS Code, then open a PowerShell terminal.

### 1. Configure AWS once

```powershell
aws configure
aws sts get-caller-identity
```

The default project region is `ap-south-1` (Mumbai). Change `config/project.json` if required.

### 2. First-time local setup

Double-click:

```text
FIRST_TIME_SETUP.bat
```

or run:

```powershell
.\scripts\bootstrap.ps1 -InstallMissing
```

This checks/installs prerequisites, creates `.venv`, installs Python packages, runs unit tests, checks Docker and verifies AWS identity.

Docker Desktop may need to be opened once after installation.

### 3. Run the full project

Double-click:

```text
RUN_PROJECT.bat
```

or run:

```powershell
.\scripts\full_run.ps1
```

This executes the complete workflow:

1. prerequisite and unit-test check
2. Terraform AWS deployment
3. deployed end-to-end smoke test
4. local Docker always-on baseline startup
5. frozen deterministic workload against baseline
6. same workload shape against AWS serverless path
7. optional saturation sweeps across configured concurrency levels
8. S3-to-DuckDB analytics rebuild
9. CloudWatch evidence capture
10. AWS pricing snapshot attempt
11. per-run cost analysis from Lambda REPORT usage + captured prices
12. all five negative tests
13. claim-to-evidence map generation
14. SHA-256 evidence manifest generation

AWS infrastructure is intentionally left running after the experiment so you can inspect it and demonstrate it. Destroy it when finished.

## Dashboard

Run:

```powershell
.\scripts\run_dashboard.ps1
```

or double-click `RUN_DASHBOARD.bat`.

The dashboard rebuilds DuckDB from the actual S3 event objects and then launches a polished Streamlit research dashboard. The sidebar lets you select a complete experiment run and navigate six evidence-backed sections:

1. **Overview** — stored events, AWS-run success rate, event types, processing statistics, event trend/mix, recent records and CloudWatch telemetry.
2. **Event Analytics** — interactive event-type/source filtering, distributions, values, processing-time analysis, recent records and analytics import quality.
3. **Baseline vs AWS** — throughput, p50/p95/p99 latency, error rate, raw latency distribution and saturation/concurrency charts.
4. **Cold Start Analysis** — the configured cold-start trials, success rate, distribution, p50/p95/p99 and NT-1 acceptance evidence.
5. **Cost Analysis** — Lambda/API Gateway/SQS/S3/DynamoDB cost breakdown, cost per event, captured pricing, measured Lambda usage and the explicitly modeled always-on reference.
6. **Negative Tests** — NT-1 through NT-5 with PASS/HOLD/FAIL status, expected-vs-observed behavior, recovery action/time, residual risk and evidence paths.

The dashboard does not fabricate missing measurements. If an experiment or pricing artifact is absent, the relevant panel reports it as unavailable/HOLD and points back to the required evidence. See `docs/DASHBOARD_GUIDE.md` for details.

## Clean up AWS

Interactive:

```powershell
.\scripts\destroy.ps1
```

Non-interactive:

```powershell
.\scripts\destroy.ps1 -AutoApprove
```

or double-click `DESTROY_AWS.bat`.

`force_destroy = true` is set on the project S3 bucket so Terraform can remove experiment objects during cleanup. Do not use this Terraform configuration for unrelated production data.

## Individual commands

### Deploy only

```powershell
.\scripts\bootstrap.ps1
.\scripts\deploy.ps1 -AutoApprove
```

### Start the baseline only

```powershell
.\scripts\start_baseline.ps1
```

Baseline health:

```text
http://127.0.0.1:8000/health
```

### Run one controlled workload

```powershell
.\.venv\Scripts\python.exe .\workload\load_test.py --target baseline --count 500 --concurrency 25 --run-id demo-001
.\.venv\Scripts\python.exe .\workload\load_test.py --target aws      --count 500 --concurrency 25 --run-id demo-001
```

### Run saturation experiments

```powershell
.\.venv\Scripts\python.exe .\experiments\saturation.py --target baseline --count 500 --run-id sat-001
.\.venv\Scripts\python.exe .\experiments\saturation.py --target aws      --count 500 --run-id sat-001
```

### Run all negative tests

```powershell
.\scripts\run_negative_tests.ps1 -RunId acceptance-001
```

### Rebuild analytics

```powershell
.\.venv\Scripts\python.exe .\analytics\rebuild.py
```

### Rebuild evidence manifest

```powershell
.\.venv\Scripts\python.exe .\experiments\build_claim_map.py
.\.venv\Scripts\python.exe .\experiments\generate_manifest.py
```

## Five negative tests

### NT-1: cold start

For each configured trial, the test updates a harmless Lambda environment nonce, waits for the function update, sends a request, and records latency. This forces a fresh Lambda execution environment without changing the event contract.

Default: 30 trials.

Evidence:

```text
evidence/runs/<run-id>/cold_start_trials.csv
evidence/runs/<run-id>/negative_tests/nt-1.json
```

### NT-2: vendor/degraded endpoint portability

The client is pointed at a deliberately unreachable endpoint. Instead of silently losing the event, it writes the vendor-neutral JSON event into a durable local outbox and replays the exact event to the restored AWS endpoint.

This demonstrates degraded-mode/replay at the event-contract boundary; it does **not** claim that the entire Terraform implementation is cloud-neutral.

### NT-3: cost surprise guardrail

The script attempts to capture current regional price dimensions from the AWS Price List Query API. A declared pre-spend upper-bound model projects the configured large workload and either ALLOWs or BLOCKs the scale-up relative to the budget.

If pricing cannot be retrieved, the test records `HOLD` rather than inventing a price. Publication cost-per-event should still use the measured usage evidence plus the captured pricing snapshot.

### NT-4: defective critical partition

Healthy records and deliberately invalid records in a `defective-partition` are injected directly into SQS. Invalid records that deterministically fail the quality contract are sent directly to the DLQ rather than being silently committed; transient infrastructure failures remain retryable through the SQS/Lambda partial-batch mechanism.

### NT-5: access control / evidence exposure

The test verifies S3 public-access blocking, server-side encryption and denial of anonymous bucket access.

## Evidence layout

After execution:

```text
evidence/
├── claim_to_evidence.csv
├── evidence_manifest.json
└── runs/
    └── <run-id>/
        ├── baseline_trace.csv
        ├── baseline_summary.json
        ├── aws_trace.csv
        ├── aws_summary.json
        ├── comparison.json
        ├── cloudwatch_metrics.json
        ├── cost_analysis.json
        ├── cold_start_trials.csv
        └── negative_tests/
            ├── nt-1.json
            ├── nt-2.json
            ├── nt-3.json
            ├── nt-4.json
            └── nt-5.json
```

Every workload request has a raw CSV trace. `evidence_manifest.json` hashes versionable project/evidence files with SHA-256. `claim_to_evidence.csv` resolves project claims to concrete evidence files and hashes; missing evidence is explicitly marked.

## Frozen workload

The deterministic generator uses the seed in `config/project.json`. Baseline and candidate runs therefore use the same workload distribution and schema while preserving unique event IDs per run.

Default experiment values:

```json
{
  "default_events": 500,
  "default_concurrency": 25,
  "saturation_concurrency": [1, 5, 10, 25, 50, 100],
  "cold_start_trials": 30
}
```

Change these before a formal experiment and then commit the configuration with the resulting evidence.

## Measured vs modeled results

The project intentionally separates them:

- throughput: measured
- request latency p50/p95/p99: measured
- error rate: measured
- saturation behavior: measured
- cold-start request latency: measured
- CloudWatch Lambda usage/latency telemetry: measured from AWS
- S3/DynamoDB stored state: observed from AWS
- current price dimensions: captured from AWS Pricing API when permitted
- large-scale cost guardrail: modeled from the captured prices and declared assumptions
- always-on infrastructure cost: should be modeled against the declared EC2 instance price or replaced by an actual deployed always-on cloud baseline if your evaluator requires billed-cloud-vs-billed-cloud comparison

Do not present modeled values as measured experimental results.

## Project structure

```text
serverless-event-driven-pipeline/
├── terraform/              AWS IaC
├── lambdas/                ingestion + transformer code
├── baseline/               always-on FastAPI Docker baseline
├── workload/               deterministic generator + raw load traces
├── experiments/            saturation, cold start, pricing, CW capture, hashes
├── negative_tests/         NT-1 ... NT-5
├── analytics/              S3 sync + DuckDB regeneration
├── dashboard/              Streamlit/Plotly UI
├── tests/                  unit + deployed integration smoke test
├── scripts/                PowerShell automation
├── config/                 frozen workload/evidence contract/runtime outputs
├── evidence/               generated traces, manifests and acceptance evidence
├── docker-compose.yml
├── FIRST_TIME_SETUP.bat
├── RUN_PROJECT.bat
├── RUN_DASHBOARD.bat
└── DESTROY_AWS.bat
```

## Cost control

This project creates billable AWS resources. The experiment volume is intentionally small by default, but charges can still occur. Use `destroy.ps1` after your demo/experiment. Check AWS Billing/Cost Explorer independently; this repository does not claim that local estimates equal the final AWS invoice.

## Research integrity

The repository ships with implementation and measurement tooling, not fabricated results. Formal KPI tables should be regenerated from the evidence created in your AWS account. If a required test fails or a price cannot be captured, the scripts retain FAIL/HOLD evidence instead of silently converting it into a pass.
