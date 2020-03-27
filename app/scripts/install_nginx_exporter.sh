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
			STAT_PORT)    STAT_PORT=${VALUE} ;;
			STAT_PAGE)    STAT_PAGE=${VALUE} ;;
			STATS_USER)    STATS_USER=${VALUE} ;;
            STATS_PASS)    STATS_PASS=${VALUE} ;;
			SSH_PORT)    SSH_PORT=${VALUE} ;;
            *)
    esac
done

if [ ! -d "/var/www/haproxy-wi/app/scripts/ansible/roles/bdellegrazie.nginx_exporter" ]; then
	if [ ! -z $PROXY ];then
		export https_proxy="$PROXY"
		export http_proxy="$PROXY"
	fi
	ansible-galaxy install bdellegrazie.nginx_exporter --roles-path /var/www/haproxy-wi/app/scripts/ansible/roles/
fi

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
export ANSIBLE_DEPRECATION_WARNINGS=False
PWD=`pwd`
PWD=$PWD/scripts/ansible/
echo $HOST > $PWD/$HOST

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/nginx_exporter.yml -e "ansible_user=$USER ansible_ssh_pass=$PASS variable_host=$HOST PROXY=$PROXY STAT_PAGE=$STAT_PAGE STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS SSH_PORT=$SSH_PORT" -i $PWD/$HOST
else	
	ansible-playbook $PWD/roles/nginx_exporter.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY STAT_PAGE=$STAT_PAGE STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS SSH_PORT=$SSH_PORT" -i $PWD/$HOST 
fi

if [ $? -gt 0 ]
then
        echo "error: Can't install Nginx exporter <br /><br />"
        exit 1
fi

if ! sudo grep -Fxq "      - $HOST:9113" /etc/prometheus/prometheus.yml; then
	sudo echo "      - $HOST:9113" | sudo tee -a /etc/prometheus/prometheus.yml > /dev/null
fi

sudo systemctl reload prometheus
rm -f $PWD/$HOST
