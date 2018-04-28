#!/bin/bash
CONF=/etc/keepalived/keepalived.conf

yum install keepalived -y > /dev/null
if [ $? -eq 1 ]
then
        exit 1
fi
echo "" > $CONF

cat << EOF > $CONF
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
        echo "Can't read keepalived config"
        exit 1
fi
sed -i "s/MASTER/$1/g" $CONF
sed -i "s/eth0/$2/g" $CONF
sed -i "s/0.0.0.0/$3/g" $CONF

if [[ $1 == "BACKUP" ]];then
	sed -i "s/102/103/g" $CONF
fi

systemctl enable keepalived
systemctl restart keepalived
echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
sysctl -p
firewall-cmd --direct --permanent --add-rule ipv4 filter INPUT 0 --in-interface enp0s8 --destination 224.0.0.18 --protocol vrrp -j ACCEPT
firewall-cmd --direct --permanent --add-rule ipv4 filter OUTPUT 0 --out-interface enp0s8 --destination 224.0.0.18 --protocol vrrp -j ACCEPT
firewall-cmd --reload

if [ $? -eq 1 ]
then
        echo "Can't start keepalived"
        exit 1
fi