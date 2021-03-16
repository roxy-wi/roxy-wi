module "aws_module" {
	source = "github.com/Aidaho12/haproxy-wi-terraform-modules?ref=aws"

	region 					= var.region
	instance_type 			= var.instance_type
	public_ip				= var.public_ip
	floating_ip				= var.floating_ip
	volume_size				= var.volume_size
	volume_type				= var.volume_type
	delete_on_termination	= var.delete_on_termination
	name					= var.name
	os						= var.os
	ssh_key_name			= var.ssh_key_name
	firewall				= var.firewall
	AWS_ACCESS_KEY			= var.AWS_ACCESS_KEY
	AWS_SECRET_KEY			= var.AWS_SECRET_KEY
}
