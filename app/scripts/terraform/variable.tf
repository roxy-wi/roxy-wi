variable "region" {}
variable "instance_type" {
  default = "123"
}
variable "public_ip" {
  default = false
}
variable "floating_ip" {}
variable "volume_size" {
  default = "123"
}
variable "delete_on_termination" {
  default = false
}
variable "name" {}
variable "os" {}
variable "ssh_key_name" {}
variable "firewall" {}
variable "AWS_ACCESS_KEY" {
  default = "123"
}
variable "AWS_SECRET_KEY" {
  default = "123"
}

variable "size" {
  default = "123"
}
variable "private_networking" {
  default = false
}
variable "ssh_ids" {
  default = ""
}
variable "backup" {
  default = false
}
variable "privet_net" {
  default = false
}
variable "monitoring" {
  default = false
}
variable "token" {
  default = "123"
}