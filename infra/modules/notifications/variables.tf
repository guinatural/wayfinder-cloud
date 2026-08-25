variable "environment"        { type = string }
variable "kms_key_arn"        { type = string }
variable "alert_email"        { type = string }
variable "slack_workspace_id" { type = string  default = "" }
variable "slack_channel_id"   { type = string  default = "" }
