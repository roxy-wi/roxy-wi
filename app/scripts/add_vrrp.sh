#!/bin/bash
CONF=/etc/keepalived/keepalived.conf
IP=`sudo cat $CONF |grep $3 |sed s/' '//g|sed s/'\t'//g| head -1`
VI=`sudo cat /etc/keepalived/keepalived.conf |grep VI |awk '{print $2}' |awk -F"_" '{print $2}' |tail -1`
VI=$(($VI+1))

if [[ $IP == $3 ]];then
        echo -e "error: VRRP address alredy use"
        exit 1
fi

sudo bash -c cat << EOF >> $CONF
vrrp_instance VI_$VI {
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
sudo sed -i "s/MASTER/$1/g" $CONF
sudo sed -i "s/eth1/$2/g" $CONF
sudo sed -i "s/0.0.0.1/$3/g" $CONF

if [[ $1 == "BACKUP" ]];then
	sudo sed -i "s/103/104/g" $CONF
fi

if [[ $4 == "1" ]];then
	sudo systemctl restart keepalived
fi
echo "success"