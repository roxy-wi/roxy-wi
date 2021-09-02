#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo "$ARGUMENT" | cut -f1 -d=)
    VALUE=$(echo "$ARGUMENT" | cut -f2 -d=)

    case "$KEY" in
            PROXY)        PROXY=${VALUE} ;;
            UPDATE)       UPDATE=${VALUE} ;;
            maxmind_key)  maxmind_key=${VALUE} ;;
            haproxy_dir)  haproxy_dir=${VALUE} ;;
            HOST)         HOST=${VALUE} ;;
            USER)         USER=${VALUE} ;;
            PASS)         PASS=${VALUE} ;;
            KEY)          KEY=${VALUE} ;;
            SSH_PORT)     SSH_PORT=${VALUE} ;;
            *)
    esac
done

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
export LOCALHOST_WARNING=False
export COMMAND_WARNINGS=False

PWD=$(pwd)
PWD=$PWD/scripts/ansible/
echo "$HOST ansible_port=$SSH_PORT" > $PWD/$HOST

if [[ $maxmind_key == "" ]]; then
  echo "error: the Maxmind key cannot be empty"
  exit 1
fi

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/geoip.yml -e "ansible_user=$USER ansible_ssh_pass=$PASS variable_host=$HOST PROXY=$PROXY UPDATE=$UPDATE haproxy_dir=$haproxy_dir maxmind_key=$maxmind_key SSH_PORT=$SSH_PORT" -i $PWD/$HOST
else
	ansible-playbook $PWD/roles/geoip.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY UPDATE=$UPDATE haproxy_dir=$haproxy_dir maxmind_key=$maxmind_key SSH_PORT=$SSH_PORT" -i $PWD/$HOST
fi

if [ $? -gt 0 ]
then
        echo "error: Cannot download GeoLite2 database"
fi
rm -f $PWD/$HOST
