#!/bin/bash

for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            PROXY)              PROXY=${VALUE} ;;
            MASTER)    MASTER=${VALUE} ;;
            ETH)    ETH=${VALUE} ;;
            IP)    IP=${VALUE} ;;
            HOST)    HOST=${VALUE} ;;
            USER)    USER=${VALUE} ;;
            PASS)    PASS=${VALUE} ;;
            KEY)    KEY=${VALUE} ;;
            *)
    esac
done

export ANSIBLE_HOST_KEY_CHECKING=False
PWD=`pwd`
PWD=$PWD/scripts/ansible/
echo $HOST > $PWD/$HOST

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/keepalived.yml -e "ansible_user=$USER ansible_ssh_pass=$PASS variable_host=$HOST PROXY=$PROXY MASTER=$MASTER ETH=$ETH IP=$IP" -i $PWD/$HOST > /tmp/install_keepalived.log
else	
	ansible-playbook $PWD/roles/keepalived.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY MASTER=$MASTER ETH=$ETH IP=$IP" -i $PWD/$HOST > /tmp/install_keepalived.log
fi

if [ $? -eq 1 ]
then
        echo "error: Can't install keepalived service. Look log in the /tmp/install_keepalived.log<br /><br />"
        exit 1
fi
echo "success"
rm -f $PWD/$HOST