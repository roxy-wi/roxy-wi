#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            PROXY)              PROXY=${VALUE} ;;
            *)
    esac
done

if [ ! -d "/var/www/haproxy-wi/app/scripts/ansible/roles/cloudalchemy.grafana" ]; then
	if [ ! -z $PROXY ];then
		export https_proxy="$PROXY"
		export http_proxy="$PROXY"
	fi
	ansible-galaxy install cloudalchemy.grafana --roles-path /var/www/haproxy-wi/app/scripts/ansible/roles/
fi

if [ ! -d "/var/www/haproxy-wi/app/scripts/ansible/roles/cloudalchemy.prometheus" ]; then
	if [ ! -z $PROXY ];then
		export https_proxy="$PROXY"
		export http_proxy="$PROXY"
	fi
	ansible-galaxy install cloudalchemy.prometheus --roles-path /var/www/haproxy-wi/app/scripts/ansible/roles/
fi

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
export ACTION_WARNINGS=False
export LOCALHOST_WARNING=False
export COMMAND_WARNINGS=False

PWD=`pwd`
PWD=$PWD/scripts/ansible/

ansible-playbook $PWD/roles/grafana.yml -e "PROXY=$PROXY"

if [ $? -gt 0 ]
then
	echo "error: Can't install Grafana and Prometheus services <br /><br />"
    exit 1
fi
if ! sudo grep -Fxq "  - job_name: proxy" /etc/prometheus/prometheus.yml; then
	sudo echo "  - job_name: proxy" | sudo tee -a /etc/prometheus/prometheus.yml > /dev/null
	sudo echo "    metrics_path: /metrics" | sudo tee -a /etc/prometheus/prometheus.yml > /dev/null
	sudo echo "    static_configs:" | sudo tee -a /etc/prometheus/prometheus.yml > /dev/null
	sudo echo "    - targets:" | sudo tee -a /etc/prometheus/prometheus.yml > /dev/null
fi
