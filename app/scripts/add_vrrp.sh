#!/bin/bash
CONF=/etc/keepalived/keepalived.conf
IP=`cat $CONF |grep $3 |sed s/' '//g|sed s/'\t'//g`

if [[ $IP == $3 ]];then
        echo -e "error: VRRP address alredy use"
        exit 1
fi

cat << EOF >> $CONF
vrrp_instance VI_2 {
	state MASTER
	interface eth1
	virtual_router_id 101
	priority 103

	#check if we are still running
	track_script {
		chk_haproxy
	}

	advert_int 1
	authentication {
		auth_type PASS
		auth_pass VerySecretPass2!
	}
	virtual_ipaddress {
		0.0.0.1
	}

}
EOF
if [ $? -eq 1 ]
then
        echo "Can't read keepalived config"
        exit 1
fi
sed -i "s/MASTER/$1/g" $CONF
sed -i "s/eth1/$2/g" $CONF
sed -i "s/0.0.0.1/$3/g" $CONF

if [[ $1 == "BACKUP" ]];then
	sed -i "s/102/103/g" $CONF
fi

if [[ $4 == "1" ]];then
	systemctl restart keepalived
fi
echo "success"