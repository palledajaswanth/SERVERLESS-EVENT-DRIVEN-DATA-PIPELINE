provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "Terraform"
      Purpose   = "KL-Capstone-Serverless-Event-Pipeline"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
