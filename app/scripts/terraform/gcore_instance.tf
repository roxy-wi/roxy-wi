module "gcore_module" {
	source = "github.com/Aidaho12/haproxy-wi-terraform-modules?ref=gcore"

	region 					= var.region
	instance_type 			= var.instance_type
	network_type			= var.network_type
	network_name			= var.network_name
	volume_size				= var.volume_size
	delete_on_termination	= var.delete_on_termination
	volume_type				= var.volume_type
	name					= var.name
	os						= var.os
	ssh_key_name			= var.ssh_key_name
	firewall				= var.firewall
	username			    = var.username
	password    			= var.password
	project					= var.project
}
