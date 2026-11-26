# Generated evidence

This directory intentionally ships without fabricated AWS experiment results.

Running `scripts/full_run.ps1` creates timestamped evidence under `evidence/runs/<run-id>/`, then generates:

- `claim_to_evidence.csv`
- `evidence_manifest.json`
- raw baseline/AWS request traces
- throughput/latency summaries
- CloudWatch measurements
- cost analysis
- cold-start trials
- NT-1 through NT-5 expected-vs-observed/recovery/residual-risk records

Commit the formal experiment run you use in the paper together with the Terraform lock file and captured pricing snapshot.
