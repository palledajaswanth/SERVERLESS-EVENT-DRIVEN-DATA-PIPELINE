terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60, < 7.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.5, < 3.0"
    }
  }
}
