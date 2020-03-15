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
            SYN_FLOOD)    SYN_FLOOD=${VALUE} ;;
            RESTART)    RESTART=${VALUE} ;;
            ADD_VRRP)    ADD_VRRP=${VALUE} ;;
            SSH_PORT)    SSH_PORT=${VALUE} ;;
            *)
    esac
done

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
PWD=`pwd`
PWD=$PWD/scripts/ansible/
echo $HOST > $PWD/$HOST

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/keepalived.yml -e "ansible_user=$USER ansible_ssh_pass=$PASS variable_host=$HOST SYN_FLOOD=$SYN_FLOOD PROXY=$PROXY MASTER=$MASTER ETH=$ETH IP=$IP RESTART=$RESTART ADD_VRRP=$ADD_VRRP SSH_PORT=$SSH_PORT" -i $PWD/$HOST
else	
	ansible-playbook $PWD/roles/keepalived.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST SYN_FLOOD=$SYN_FLOOD PROXY=$PROXY MASTER=$MASTER ETH=$ETH IP=$IP RESTART=$RESTART ADD_VRRP=$ADD_VRRP SSH_PORT=$SSH_PORT" -i $PWD/$HOST
fi

if [ $? -gt 0 ]
then
        echo "error: Can't install keepalived service <br /><br />"
        exit 1
fi
rm -f $PWD/$HOST