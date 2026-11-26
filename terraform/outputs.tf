output "api_url" {
  value = "${aws_apigatewayv2_api.api.api_endpoint}/events"
}

output "bucket_name" {
  value = aws_s3_bucket.events.bucket
}

output "queue_url" {
  value = aws_sqs_queue.events.id
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.id
}

output "dynamodb_table" {
  value = aws_dynamodb_table.idempotency.name
}

output "ingestion_function" {
  value = aws_lambda_function.ingestion.function_name
}

output "transformer_function" {
  value = aws_lambda_function.transformer.function_name
}

output "cloudwatch_dashboard" {
  value = aws_cloudwatch_dashboard.main.dashboard_name
}

output "aws_region" {
  value = var.aws_region
}
