#!/bin/bash

for ARGUMENT in "$@"
do
    KEY=$(echo "$ARGUMENT" | cut -f1 -d=)
    VALUE=$(echo "$ARGUMENT" | cut -f2 -d=)

    case "$KEY" in
            PROXY)              PROXY=${VALUE} ;;
            VERSION)            VERSION=${VALUE} ;;
            HAPROXY_PATH)       HAPROXY_PATH=${VALUE} ;;
            HOST)         HOST=${VALUE} ;;
            USER)         USER=${VALUE} ;;
            PASS)         PASS=${VALUE} ;;
            KEY)          KEY=${VALUE} ;;
            SSH_PORT)     SSH_PORT=${VALUE} ;;
            *)
    esac
done
VERSION=$(echo "$VERSION"| awk -F"-" '{print $1}')
VERSION_MAJ=$(echo "$VERSION" | awk -F"." '{print $1"."$2}')

if (( $(awk 'BEGIN {print ("'$VERSION_MAJ'" < "'1.8'")}') )); then
	echo 'error: Need HAProxy version 1.8 or later'
	exit 1
fi

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
export LOCALHOST_WARNING=False
export COMMAND_WARNINGS=False

PWD=$(pwd)
PWD=$PWD/scripts/ansible/
echo "$HOST ansible_port=$SSH_PORT" > $PWD/$HOST

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/waf.yml -e "ansible_user=$USER ansible_ssh_pass='$PASS' variable_host=$HOST PROXY=$PROXY HAPROXY_PATH=$HAPROXY_PATH VERSION=$VERSION VERSION_MAJ=$VERSION_MAJ SSH_PORT=$SSH_PORT" -i $PWD/$HOST
else
	ansible-playbook $PWD/roles/waf.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY HAPROXY_PATH=$HAPROXY_PATH VERSION=$VERSION VERSION_MAJ=$VERSION_MAJ SSH_PORT=$SSH_PORT" -i $PWD/$HOST
fi

if [ $? -gt 0 ]
then
  echo "error: Cannot install WAF"
  exit 1
else
  echo "success"
fi
rm -f $PWD/$HOST
