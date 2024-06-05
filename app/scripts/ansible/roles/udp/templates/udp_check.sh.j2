#!/bin/bash

nc_cmd=`which nc`

nc_flavor=$($nc_cmd --version 2>&1 | grep -o nmap)
case "$nc_flavor" in
nmap)
    nc_flavor_opts="-i1"
    ;;
*) # default, probably openbsd
    nc_flavor_opts="-w1"
    ;;
esac

$nc_cmd -uzv $nc_flavor_opts $1 $2 > /dev/null
exit $?
