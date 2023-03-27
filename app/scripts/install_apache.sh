#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            PROXY)              PROXY=${VALUE} ;;
            HOST)    HOST=${VALUE} ;;
            USER)    USER=${VALUE} ;;
            PASS)    PASS=${VALUE} ;;
            KEY)     KEY=${VALUE} ;;
            SYN_FLOOD)    SYN_FLOOD=${VALUE} ;;
            STAT_PORT)    STAT_PORT=${VALUE} ;;
            STAT_PAGE)    STAT_PAGE=${VALUE} ;;
            STATS_USER)   STATS_USER=${VALUE} ;;
            STATS_PASS)   STATS_PASS=${VALUE} ;;
            SSH_PORT)     SSH_PORT=${VALUE} ;;
            CONFIG_PATH)  CONFIG_PATH=${VALUE} ;;
	          DOCKER)       DOCKER=${VALUE} ;;
            CONT_NAME)    CONT_NAME=${VALUE} ;;
            service_dir)          service_dir=${VALUE} ;;
            *)
    esac
done

if [[ $DOCKER == '1' ]]; then
  tags='docker'
else
  tags='system'
fi

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
export LOCALHOST_WARNING=False
export COMMAND_WARNINGS=False

PWD=`pwd`
PWD=$PWD/scripts/ansible/
echo "$HOST ansible_port=$SSH_PORT" > $PWD/$HOST

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/apache.yml -e "ansible_user=$USER ansible_ssh_pass='$PASS' variable_host=$HOST PROXY=$PROXY CONT_NAME=$CONT_NAME service_dir=$service_dir SYN_FLOOD=$SYN_FLOOD STAT_PAGE=$STAT_PAGE STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS CONFIG_PATH=$CONFIG_PATH SSH_PORT=$SSH_PORT service=apache" -i $PWD/$HOST -t $tags
else
	ansible-playbook $PWD/roles/apache.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY CONT_NAME=$CONT_NAME service_dir=$service_dir SYN_FLOOD=$SYN_FLOOD STAT_PAGE=$STAT_PAGE STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS CONFIG_PATH=$CONFIG_PATH SSH_PORT=$SSH_PORT service=apache" -i $PWD/$HOST -t $tags
fi

if [ $? -gt 0 ]
then
    echo "error: Can't install Apache service <br /><br />"
    rm -f $PWD/$HOST
    exit 1
else
	echo "ok"
fi
rm -f $PWD/$HOST
