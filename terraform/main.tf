locals {
  safe_project = lower(replace(var.project_name, "_", "-"))
  bucket_name  = "${local.safe_project}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
}

data "archive_file" "ingestion" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/ingestion/handler.py"
  output_path = "${path.module}/ingestion.zip"
}

data "archive_file" "transformer" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/transformer/handler.py"
  output_path = "${path.module}/transformer.zip"
}

resource "aws_s3_bucket" "events" {
  bucket        = local.bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "events" {
  bucket                  = aws_s3_bucket.events.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}


resource "aws_s3_bucket_policy" "enforce_conditional_writes" {
  bucket = aws_s3_bucket.events.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyUnconditionalEventOverwrite"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.events.arn}/events/*"
        Condition = {
          StringNotEquals = {
            "s3:if-none-match" = "*"
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.events]
}

resource "aws_s3_bucket_versioning" "events" {
  bucket = aws_s3_bucket.events.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "events" {
  bucket = aws_s3_bucket.events.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "events" {
  bucket     = aws_s3_bucket.events.id
  depends_on = [aws_s3_bucket_versioning.events]
  rule {
    id     = "event-retention"
    status = "Enabled"
    filter { prefix = "events/" }
    expiration { days = var.s3_retention_days }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

resource "aws_dynamodb_table" "idempotency" {
  name         = "${local.safe_project}-event-status"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.safe_project}-dlq"
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "events" {
  name                       = "${local.safe_project}-events"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 10
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_iam_role" "ingestion" {
  name = "${local.safe_project}-ingestion-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ingestion" {
  role = aws_iam_role.ingestion.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.events.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.ingestion.arn}:*"
      }
    ]
  })
}

resource "aws_iam_role" "transformer" {
  name = "${local.safe_project}-transformer-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "transformer" {
  role = aws_iam_role.transformer.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.events.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.dlq.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:HeadObject"]
        Resource = "${aws_s3_bucket.events.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.events.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.idempotency.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.transformer.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/aws/lambda/${local.safe_project}-ingestion"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "transformer" {
  name              = "/aws/lambda/${local.safe_project}-transformer"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "ingestion" {
  function_name    = "${local.safe_project}-ingestion"
  role             = aws_iam_role.ingestion.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.ingestion.output_path
  source_code_hash = data.archive_file.ingestion.output_base64sha256
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_seconds

  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.events.id
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingestion, aws_iam_role_policy.ingestion]
}

resource "aws_lambda_function" "transformer" {
  function_name    = "${local.safe_project}-transformer"
  role             = aws_iam_role.transformer.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.transformer.output_path
  source_code_hash = data.archive_file.transformer.output_base64sha256
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_seconds

  environment {
    variables = {
      OUTPUT_BUCKET     = aws_s3_bucket.events.bucket
      IDEMPOTENCY_TABLE = aws_dynamodb_table.idempotency.name
      DLQ_URL           = aws_sqs_queue.dlq.id
    }
  }

  depends_on = [aws_cloudwatch_log_group.transformer, aws_iam_role_policy.transformer]
}

resource "aws_lambda_event_source_mapping" "sqs_transformer" {
  event_source_arn                   = aws_sqs_queue.events.arn
  function_name                      = aws_lambda_function.transformer.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 1
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_apigatewayv2_api" "api" {
  name          = "${local.safe_project}-api"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["POST", "OPTIONS"]
    allow_headers = ["content-type"]
  }
}

resource "aws_apigatewayv2_integration" "ingestion" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.ingestion.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "events" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /events"
  target    = "integrations/${aws_apigatewayv2_integration.ingestion.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_cloudwatch_metric_alarm" "ingestion_errors" {
  alarm_name          = "${local.safe_project}-ingestion-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.ingestion.function_name }
}

resource "aws_cloudwatch_metric_alarm" "transformer_errors" {
  alarm_name          = "${local.safe_project}-transformer-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.transformer.function_name }
}

resource "aws_cloudwatch_metric_alarm" "dlq_nonempty" {
  alarm_name          = "${local.safe_project}-dlq-nonempty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.safe_project}-operations"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6,
        properties = {
          title  = "Lambda Invocations / Errors"
          region = var.aws_region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.ingestion.function_name],
            [".", "Errors", ".", "."],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.transformer.function_name],
            [".", "Errors", ".", "."]
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6,
        properties = {
          title  = "SQS Queue Depth"
          region = var.aws_region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.events.name],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.dlq.name]
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 24, height = 6,
        properties = {
          title  = "Lambda Duration"
          region = var.aws_region
          view   = "timeSeries"
          period = 60
          stat   = "Average"
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.ingestion.function_name],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.transformer.function_name]
          ]
        }
      }
    ]
  })
}
