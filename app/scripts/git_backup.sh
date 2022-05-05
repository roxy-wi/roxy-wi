#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            HOST)       HOST=${VALUE} ;;
            DELJOB)     DELJOB=${VALUE} ;;
            SERVICE)    SERVICE=${VALUE} ;;
            INIT)       INIT=${VALUE} ;;
            REPO)       REPO=${VALUE} ;;
            BRANCH)     BRANCH=${VALUE} ;;
            PERIOD)     PERIOD=${VALUE} ;;
            CONFIG_DIR)    CONFIG_DIR=${VALUE} ;;
            USER)       USER=${VALUE} ;;
            KEY)        KEY=${VALUE} ;;
			      SSH_PORT)   SSH_PORT=${VALUE} ;;
			      PROXY)      PROXY=${VALUE} ;;
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
echo "$HOST ansible_port=$SSH_PORT" >> $PWD/$HOST


ansible-playbook $PWD/roles/git_backup.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST DELJOB=$DELJOB SERVICE=$SERVICE INIT=$INIT REPO=$REPO BRANCH=$BRANCH PERIOD=$PERIOD CONFIG_DIR=$CONFIG_DIR PROXY=$PROXY KEY=$KEY" -i $PWD/$HOST

if [ $? -gt 0 ]
then
        echo "error: Cannot create a git job"
fi
rm -f $PWD/$HOST