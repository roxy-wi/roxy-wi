#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            PROXY)              PROXY=${VALUE} ;;
            SOCK_PORT)    SOCK_PORT=${VALUE} ;;
            STAT_PORT)    STAT_PORT=${VALUE} ;;
            STAT_FILE)    STAT_FILE=${VALUE} ;;
            STATS_USER)    STATS_USER=${VALUE} ;;
            STATS_PASS)    STATS_PASS=${VALUE} ;;
            HAPVER)    HAPVER=${VALUE} ;;
            HOST)    HOST=${VALUE} ;;
            USER)    USER=${VALUE} ;;
            PASS)    PASS=${VALUE} ;;
            KEY)    KEY=${VALUE} ;;
            SYN_FLOOD)    SYN_FLOOD=${VALUE} ;;
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
	ansible-playbook $PWD/roles/haproxy.yml -e "ansible_user=$USER ansible_ssh_pass=$PASS variable_host=$HOST PROXY=$PROXY HAPVER=$HAPVER SOCK_PORT=$SOCK_PORT STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS STAT_FILE=$STAT_FILE SSH_PORT=$SSH_PORT SYN_FLOOD=$SYN_FLOOD" -i $PWD/$HOST
else	
	ansible-playbook $PWD/roles/haproxy.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY HAPVER=$HAPVER SOCK_PORT=$SOCK_PORT STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS STAT_FILE=$STAT_FILE SSH_PORT=$SSH_PORT SYN_FLOOD=$SYN_FLOOD" -i $PWD/$HOST 
fi

if [ $? -gt 0 ]
then
        echo "error: Can't install Haproxy service <br /><br />"
        exit 1
fi
rm -f $PWD/$HOST
