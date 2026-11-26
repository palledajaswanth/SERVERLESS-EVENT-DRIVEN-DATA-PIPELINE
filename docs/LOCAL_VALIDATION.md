# Local package validation performed before delivery

Validation performed on 2026-09-19:

- Python source compilation (`python -m compileall`) passed.
- Unit test suite passed: 3 tests, 0 failures.
- Always-on FastAPI baseline was started locally and exercised through the asynchronous load generator with 20/20 successful requests.
- Terraform source files were checked for balanced syntax delimiters.

The AWS Terraform plan/apply cannot be truthfully executed without the project owner's authenticated AWS account. The included deployment automation therefore runs `terraform validate`, `terraform apply`, and a deployed end-to-end smoke test on the target machine before experiments begin. Formal AWS KPI results are generated only after that deployment succeeds.
