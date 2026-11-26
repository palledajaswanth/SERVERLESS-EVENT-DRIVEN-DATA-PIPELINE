# AWS deployment permissions

The AWS identity running Terraform needs create/read/update/delete permissions for:

- API Gateway v2
- Lambda
- SQS
- S3
- DynamoDB
- CloudWatch Logs, Metrics, Alarms and Dashboards
- IAM roles and inline role policies
- STS caller identity

For pricing automation it also needs:

- `pricing:GetProducts`

Use a dedicated development account/role when possible. Do not deploy with AWS root credentials. Do not commit long-lived access keys.
