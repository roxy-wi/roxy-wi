module "do_module" {
	source = "github.com/Aidaho12/haproxy-wi-terraform-modules?ref=digitalocean"

	region 	    		= var.region
	size     	        = var.size
	private_networking  = var.private_networking
	floating_ip	    	= var.floating_ip
	ssh_key_name	    = var.ssh_key_name
	name			    = var.name
	os				    = var.os
	ssh_ids 		    = var.ssh_ids
	firewall		    = var.firewall
	backup      	    = var.backup
	monitoring     	    = var.monitoring
	token       	    = var.token
}
