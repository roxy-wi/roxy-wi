#!/bin/bash
for ARGUMENT in "$@"
do
    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            SERVER)	    SERVER=${VALUE} ;;
            S3_SERVER)  S3_SERVER=${VALUE} ;;
            BUCKET)     BUCKET=${VALUE} ;;
            SECRET_KEY) SECRET_KEY=${VALUE} ;;
            ACCESS_KEY) ACCESS_KEY=${VALUE} ;;
            TAG)        TAG=${VALUE} ;;
            TIME)       TIME=${VALUE} ;;
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

ansible-playbook $PWD/roles/s3_backup.yml -e "SERVER=$SERVER S3_SERVER=$S3_SERVER BUCKET=$BUCKET SECRET_KEY=$SECRET_KEY ACCESS_KEY=$ACCESS_KEY TIME=$TIME" -t $TAG -i $PWD/$HOST

if [ $? -gt 0 ]
then
  echo "error: Cannot create a S3 backup job"
  exit 1
fi
