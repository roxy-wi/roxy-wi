#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            PROXY)   PROXY=${VALUE} ;;
            HOST)    HOST=${VALUE} ;;
            USER)    USER=${VALUE} ;;
            PASS)    PASS=${VALUE} ;;
            KEY)    KEY=${VALUE} ;;
            SSH_PORT)    SSH_PORT=${VALUE} ;;
            DOMAIN)    DOMAIN=${VALUE} ;;
			      EMAIL)    EMAIL=${VALUE} ;;
			      SSL_PATH)    SSL_PATH=${VALUE} ;;
            *)
    esac
done

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
PWD=`pwd`
PWD=$PWD/scripts/ansible/
echo $HOST > $PWD/$HOST

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/letsencrypt.yml -e "ansible_user=$USER ansible_ssh_pass=$PASS ansible_port=$SSH_PORT variable_host=$HOST PROXY=$PROXY DOMAIN=$DOMAIN EMAIL=$EMAIL SSL_PATH=$SSL_PATH" -i $PWD/$HOST
else
	ansible-playbook $PWD/roles/letsencrypt.yml --key-file $KEY -e "ansible_user=$USER ansible_port=$SSH_PORT variable_host=$HOST PROXY=$PROXY DOMAIN=$DOMAIN EMAIL=$EMAIL SSL_PATH=$SSL_PATH" -i $PWD/$HOST
fi

if [ $? -gt 0 ]
then
    echo "error: Can't create SSL certificate"
    exit 1
else
	echo "ok"
fi
rm -f $PWD/$HOST
