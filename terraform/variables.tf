variable "project_name" {
  description = "Lowercase DNS-safe project name."
  type        = string
  default     = "serverless-event-pipeline"
}

variable "aws_region" {
  description = "AWS region for the project."
  type        = string
  default     = "ap-south-1"
}

variable "lambda_memory_mb" {
  type    = number
  default = 256
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 20
}

variable "s3_retention_days" {
  type    = number
  default = 90
}

variable "log_retention_days" {
  type    = number
  default = 14
}
