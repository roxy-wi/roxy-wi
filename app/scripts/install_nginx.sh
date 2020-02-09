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
            KEY)    KEY=${VALUE} ;;
            SYN_FLOOD)    SYN_FLOOD=${VALUE} ;;
			STAT_PORT)    STAT_PORT=${VALUE} ;;
			STAT_PAGE)    STAT_PAGE=${VALUE} ;;
			STATS_USER)    STATS_USER=${VALUE} ;;
            STATS_PASS)    STATS_PASS=${VALUE} ;;
            *)
    esac
done

if [ ! -d "/var/www/haproxy-wi/app/scripts/ansible/roles/nginxinc.nginx" ]; then
	if [ ! -z $PROXY ];then
		export https_proxy="$PROXY"
		export http_proxy="$PROXY"
	fi
	ansible-galaxy install nginxinc.nginx --roles-path /var/www/haproxy-wi/app/scripts/ansible/roles/
fi

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
PWD=`pwd`
PWD=$PWD/scripts/ansible/
echo $HOST > $PWD/$HOST

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/nginx.yml -e "ansible_user=$USER ansible_ssh_pass=$PASS variable_host=$HOST PROXY=$PROXY SYN_FLOOD=$SYN_FLOOD STAT_PAGE=$STAT_PAGE STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS" -i $PWD/$HOST
else	
	ansible-playbook $PWD/roles/nginx.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY SYN_FLOOD=$SYN_FLOOD STAT_PAGE=$STAT_PAGE STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS" -i $PWD/$HOST 
fi

if [ $? -gt 0 ]
then
        echo "error: Can't install Nginx service <br /><br />"
        exit 1
fi
rm -f $PWD/$HOST
