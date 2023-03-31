#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            PROXY)        PROXY=${VALUE} ;;
            MASTER)       MASTER=${VALUE} ;;
            ETH)          ETH=${VALUE} ;;
            ETH_SLAVE)    ETH_SLAVE=${VALUE} ;;
            keepalived_path_logs)    keepalived_path_logs=${VALUE} ;;
            IP)           IP=${VALUE} ;;
            HOST)         HOST=${VALUE} ;;
            USER)         USER=${VALUE} ;;
            router_id)    router_id=${VALUE} ;;
            PASS)         PASS=${VALUE} ;;
            KEY)          KEY=${VALUE} ;;
            SYN_FLOOD)    SYN_FLOOD=${VALUE} ;;
            RESTART)      RESTART=${VALUE} ;;
            RETURN_TO_MASTER)    RETURN_TO_MASTER=${VALUE} ;;
            ADD_VRRP)     ADD_VRRP=${VALUE} ;;
            SSH_PORT)     SSH_PORT=${VALUE} ;;
            HAPROXY)      HAPROXY=${VALUE} ;;
            NGINX)        NGINX=${VALUE} ;;
            *)
    esac
done

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
export LOCALHOST_WARNING=False
export COMMAND_WARNINGS=False

PWD=`pwd`
PWD=$PWD/scripts/ansible/
echo "$HOST ansible_port=$SSH_PORT" > $PWD/$HOST

if [[ $MASTER == 'BACKUP' ]]; then
  sleep 5
fi

if [[ $KEY == "" ]]; then
  ansible-playbook $PWD/roles/keepalived.yml -e "ansible_user=$USER ansible_ssh_pass='$PASS' variable_host=$HOST SYN_FLOOD=$SYN_FLOOD PROXY=$PROXY MASTER=$MASTER ETH=$ETH ETH_SLAVE=$ETH_SLAVE keepalived_path_logs=$keepalived_path_logs IP=$IP RESTART=$RESTART RETURN_TO_MASTER=$RETURN_TO_MASTER ADD_VRRP=$ADD_VRRP router_id=$router_id HAPROXY=$HAPROXY NGINX=$NGINX SSH_PORT=$SSH_PORT" -i $PWD/$HOST
else
  ansible-playbook $PWD/roles/keepalived.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST SYN_FLOOD=$SYN_FLOOD PROXY=$PROXY MASTER=$MASTER ETH=$ETH ETH_SLAVE=$ETH_SLAVE keepalived_path_logs=$keepalived_path_logs IP=$IP RESTART=$RESTART RETURN_TO_MASTER=$RETURN_TO_MASTER ADD_VRRP=$ADD_VRRP router_id=$router_id HAPROXY=$HAPROXY NGINX=$NGINX SSH_PORT=$SSH_PORT" -i $PWD/$HOST
fi

if [ $? -gt 0 ]
then
  echo "error: Can't install keepalived service <br />"
  rm -f $PWD/$HOST
  exit 1
fi
rm -f $PWD/$HOST