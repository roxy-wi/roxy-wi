#!/bin/bash
CONF=/etc/keepalived/keepalived.conf

if [ -f $CONF ];then
	echo -e 'error: Keepalived already installed. You can edit config <a href="/app/keepalivedconfig.py" title="Edit Keepalived config">here</a><br /><br />'
	exit 1
fi

if hash apt-get 2>/dev/null; then
	sudo apt-get install keepalived  -y
else
	sudo yum install keepalived -y > /dev/null
fi

if [ $? -eq 1 ]
then	
	echo "error: Can't install keepalived <br /><br />"
    exit 1
fi
sudo echo "" > $CONF

sudo bash -c cat << EOF > $CONF
global_defs {
   router_id LVS_DEVEL
}

#health-check for keepalive
vrrp_script chk_haproxy { # Requires keepalived-1.1.13
    script "pidof haproxy"
    interval 2 # check every 2 seconds
    weight 3 # addA 3 points of prio if OK
}

vrrp_instance VI_1 {
    state MASTER
    interface eth0
    virtual_router_id 100
    priority 102

    #check if we are still running
    track_script {
        chk_haproxy
    }

    advert_int 1
    authentication {
        auth_type PASS
        auth_pass VerySecretPass
    }
    virtual_ipaddress {
        0.0.0.0
    }
}
EOF
if [ $? -eq 1 ]
then
        echo "error: Can't read keepalived config <br /><br />"
        exit 1
fi
sudo sed -i "s/MASTER/$1/g" $CONF
sudo sed -i "s/eth0/$2/g" $CONF
sudo sed -i "s/0.0.0.0/$3/g" $CONF

if [[ $1 == "BACKUP" ]];then
	sudo sed -i "s/102/103/g" $CONF
fi

sudo systemctl enable keepalived
sudo systemctl restart keepalived
sudo echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
sudo sysctl -p
sudo firewall-cmd --direct --permanent --add-rule ipv4 filter INPUT 0 --in-interface enp0s8 --destination 224.0.0.18 --protocol vrrp -j ACCEPT
sudo firewall-cmd --direct --permanent --add-rule ipv4 filter OUTPUT 0 --out-interface enp0s8 --destination 224.0.0.18 --protocol vrrp -j ACCEPT
sudo firewall-cmd --reload

if [ $? -eq 1 ]
then
        echo "error: Can't start keepalived <br /><br />"
        exit 1
fi
echo "success"