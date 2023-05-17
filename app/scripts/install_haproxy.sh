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
            DOCKER)    DOCKER=${VALUE} ;;
            HAP_DIR)    HAP_DIR=${VALUE} ;;
            CONT_NAME)    CONT_NAME=${VALUE} ;;
            *)
    esac
done

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
export LOCALHOST_WARNING=False
export COMMAND_WARNINGS=False

PWD=/var/www/haproxy-wi/app/scripts/ansible/
echo "$HOST ansible_port=$SSH_PORT" > $PWD/$HOST

if [[ $DOCKER == '1' ]]; then
  tags='docker'
else
  tags='system'
fi

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/haproxy.yml -e "ansible_user=$USER ansible_ssh_pass='$PASS' variable_host=$HOST PROXY=$PROXY HAPVER=$HAPVER HAP_DIR=$HAP_DIR CONT_NAME=$CONT_NAME SOCK_PORT=$SOCK_PORT STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS='$STATS_PASS' STAT_FILE=$STAT_FILE SSH_PORT=$SSH_PORT SYN_FLOOD=$SYN_FLOOD" -i $PWD/$HOST -t $tags
else	
	ansible-playbook $PWD/roles/haproxy.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY HAPVER=$HAPVER HAP_DIR=$HAP_DIR CONT_NAME=$CONT_NAME SOCK_PORT=$SOCK_PORT STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS='$STATS_PASS' STAT_FILE=$STAT_FILE SSH_PORT=$SSH_PORT SYN_FLOOD=$SYN_FLOOD" -i $PWD/$HOST -t $tags
fi

if [ $? -gt 0 ]
then
        echo "error: Cannot install Haproxy service"
        rm -f $PWD/$HOST
        exit 1
fi

rm -f $PWD/$HOST
