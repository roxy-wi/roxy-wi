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
            VER)     VER=${VALUE} ;;
            EXP_PROM)     EXP_PROM=${VALUE} ;;
			      STAT_PORT)    STAT_PORT=${VALUE} ;;
			      STAT_PAGE)    STAT_PAGE=${VALUE} ;;
			      STATS_USER)    STATS_USER=${VALUE} ;;
            STATS_PASS)    STATS_PASS=${VALUE} ;;
			      SSH_PORT)    SSH_PORT=${VALUE} ;;
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
echo "$HOST ansible_port=$SSH_PORT" > $PWD/$HOST

if [[ $KEY == "" ]]; then
	ansible-playbook $PWD/roles/apache_exporter.yml -e "ansible_user=$USER ansible_ssh_pass='$PASS' variable_host=$HOST PROXY=$PROXY STAT_PAGE=$STAT_PAGE STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS SSH_PORT=$SSH_PORT apache_exporter_version=$VER" -i $PWD/$HOST
else	
	ansible-playbook $PWD/roles/apache_exporter.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST PROXY=$PROXY STAT_PAGE=$STAT_PAGE STAT_PORT=$STAT_PORT STATS_USER=$STATS_USER STATS_PASS=$STATS_PASS SSH_PORT=$SSH_PORT apache_exporter_version=$VER" -i $PWD/$HOST
fi

if [ $? -gt 0 ]
then
        echo "error: Can't install Apache exporter <br /><br />"
        exit 1
fi

if [ "$EXP_PROM" == 0 ]
then
  if ! sudo grep -Fxq "      - $HOST:9117" /etc/prometheus/prometheus.yml; then
    sudo echo "      - $HOST:9117" | sudo tee -a /etc/prometheus/prometheus.yml > /dev/null
    sudo systemctl reload prometheus 2>> /dev/null
  fi
fi

rm -f $PWD/$HOST
