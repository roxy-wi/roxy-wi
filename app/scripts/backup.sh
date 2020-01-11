#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            RPATH)	RPATH=${VALUE} ;;
            TIME)    TIME=${VALUE} ;;
            TYPE)    TYPE=${VALUE} ;;
            HOST)    HOST=${VALUE} ;;
            SERVER)    SERVER=${VALUE} ;;
            USER)    USER=${VALUE} ;;
            KEY)    KEY=${VALUE} ;;
			DELJOB) DELJOB=${VALUE} ;;
            *)
    esac
done

export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_DISPLAY_SKIPPED_HOSTS=False
PWD=`pwd`
PWD=$PWD/scripts/ansible/
echo '[backup]' > $PWD/$HOST
echo $HOST >> $PWD/$HOST
echo '[haproxy_wi]' >> $PWD/$HOST
echo 'localhost' >> $PWD/$HOST

if [[ $TYPE == 'synchronization' ]]; then
	TYPE='--delete'
else
	TYPE=''
fi 

ansible-playbook $PWD/roles/backup.yml --key-file $KEY -e "ansible_user=$USER variable_host=$HOST RPATH=$RPATH TYPE=$TYPE TIME=$TIME HOST=$HOST SERVER=$SERVER KEY=$KEY DELJOB=$DELJOB" -i $PWD/$HOST

if [ $? -gt 0 ]
then
        echo "error: Can't create backup job"
        exit 1
fi
rm -f $PWD/$HOST