# Troubleshooting

## `aws sts get-caller-identity` fails

Authenticate first:

```powershell
aws configure
```

or use your SSO profile and set `AWS_PROFILE`.

## `docker info` fails

Open Docker Desktop and wait until the engine is running, then rerun bootstrap.

## PowerShell blocks scripts

The included `.bat` launchers use `-ExecutionPolicy Bypass` only for the launched project script. From VS Code you can also run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\full_run.ps1
```

## Terraform says a resource name already exists

Use the same Terraform state rather than deleting the state file. If resources were created manually or state was lost, import or remove the orphaned project resources before redeploying.

## NT-3 is HOLD

Your AWS identity probably cannot call the Price List Query API or the automatic price-dimension heuristic did not normalize one of the services. This is intentional. Inspect `config/pricing_snapshot.json` if it exists and do not publish a cost number until the missing rate is resolved.

## NT-4 does not see the DLQ record immediately

SQS/Lambda retry and approximate queue metrics are eventually consistent. Rerun the test with a longer wait or inspect the transformer logs/DLQ in AWS. Do not change the result to PASS without evidence.

## Dashboard has zero events

Run:

```powershell
.\.venv\Scripts\python.exe .\analytics\rebuild.py
```

and confirm `config/runtime.json` points at the deployed bucket.
