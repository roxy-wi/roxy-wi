#!/bin/bash

for ARGUMENT in "$@"
do

    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)

    case "$KEY" in
            PROXY)              PROXY=${VALUE} ;;
            VERSION)            VERSION=${VALUE} ;;
            HAPROXY_PATH)       HAPROXY_PATH=${VALUE} ;;
            *)
    esac


done

VERSION_MAJ=$(echo $VERSION | awk -F"." '{print $1"."$2}')

if [[ $PROXY != "" ]]
then
	export http_proxy="$PROXY"
	export https_proxy="$PROXY"
	echo "Exporting proxy"
fi

if [ -f $HAPROXY_PATH/waf/modsecurity.conf  ];then
	echo -e 'error: Haproxy WAF already installed. You can edit config<a href="/app/config.py" title="Edit HAProxy config">here</a> <br /><br />'
	exit 1
fiif hash apt-get 2>/dev/null; then
	sudo apt-get install yajl-dev libevent-dev httpd-dev libxml2-dev gcc curl-dev -y
else
	wget -O /tmp/yajl-devel-2.0.4-4.el7.x86_64.rpm http://rpmfind.net/linux/centos/7.5.1804/os/x86_64/Packages/yajl-devel-2.0.4-4.el7.x86_64.rpm
	wget -O /tmp/libevent-devel-2.0.21-4.el7.x86_64.rpm http://mirror.centos.org/centos/7/os/x86_64/Packages/libevent-devel-2.0.21-4.el7.x86_64.rpm
	wget -O /tmp/modsecurity-2.9.2.tar.gz https://www.modsecurity.org/tarball/2.9.2/modsecurity-2.9.2.tar.gz
	sudo yum install /tmp/libevent-devel-2.0.21-4.el7.x86_64.rpm /tmp/yajl-devel-2.0.4-4.el7.x86_64.rpm  httpd-devel libxml2-devel gcc curl-devel -y
if

if [ $? -eq 1 ]; then
	echo -e "Can't download waf application. Check Internet connection"
	exit 1
fi
cd /tmp
sudo tar xf modsecurity-2.9.2.tar.gz
cd /tmp/modsecurity-2.9.2
sudo ./configure --prefix=/tmp/modsecurity-2.9.2 --enable-standalone-module --disable-mlogc --enable-pcre-study --without-lua --enable-pcre-jit
sudo make
sudo make -C standalone install
if [ $? -eq 1 ]; then
	echo -e "Can't compile waf application"
	exit 1
fi
sudo mkdir -p /tmp/modsecurity-2.9.2/INSTALL/include
sudo cp standalone/.libs/* /tmp/modsecurity-2.9.2/INSTALL/include
sudo cp standalone/* /tmp/modsecurity-2.9.2/INSTALL/include
sudo cp apache2/*.h /tmp/modsecurity-2.9.2/INSTALL/include

wget -O /tmp/haproxy-$VERSION.tar.gz http://www.haproxy.org/download/$VERSION_MAJ/src/haproxy-$VERSION.tar.gz

if [ $? -eq 1 ]; then
	echo -e "Can't download Haproxy application. Check Internet connection"
	exit 1
fi
cd /tmp
sudo tar xf /tmp/haproxy-$VERSION.tar.gz
sudo mkdir $HAPROXY_PATH/waf
sudo mkdir $HAPROXY_PATH/waf/bin
sudo mkdir $HAPROXY_PATH/waf/rules
cd /tmp/haproxy-$VERSION/contrib/modsecurity
sudo make MODSEC_INC=/tmp/modsecurity-2.9.2/INSTALL/include MODSEC_LIB=/tmp/modsecurity-2.9.2/INSTALL/include APACHE2_INC=/usr/include/httpd/ APR_INC=/usr/include/apr-1
if [ $? -eq 1 ]; then
	echo -e "Can't compile waf application"
	exit 1
fi
sudo mv /tmp/haproxy-$VERSION/contrib/modsecurity/modsecurity $HAPROXY_PATH/waf/bin
wget -O $HAPROXY_PATH/waf/modsecurity.conf https://github.com/SpiderLabs/ModSecurity/raw/v2/master/modsecurity.conf-recommended 

sudo bash -c cat << EOF >> 	$HAPROXY_PATH/waf/modsecurity.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_10_ignore_static.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_10_setup.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_11_avs_traffic.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_11_brute_force.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_11_dos_protection.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_13_xml_enabler.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_16_authentication_tracking.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_16_scanner_integration.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_16_username_tracking.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_16_username_tracking.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_20_protocol_violations.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_21_protocol_anomalies.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_23_request_limits.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_25_cc_known.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_25_cc_track_pan.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_30_http_policy.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_35_bad_robots.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_40_generic_attacks.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_40_http_parameter_pollution.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_41_sql_injection_attacks.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_41_xss_attacks.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_42_comment_spam.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_42_tight_security.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_45_trojans.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_46_av_scanning.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_46_scanner_integration.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_46_slr_et_xss_attacks.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_46_slr_et_lfi_attacks.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_46_slr_et_sqli_attacks.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_47_common_exceptions.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_49_inbound_blocking.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_50_outbound.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_55_marketing.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_56_pvi_checks.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_59_outbound_blocking.conf
Include $HAPROXY_PATH/waf/rules/modsecurity_crs_60_correlation.conf
EOF

wget -O $HAPROXY_PATH/waf/unicode.mapping https://github.com/SpiderLabs/ModSecurity/raw/v2/master/unicode.mapping
wget -O /tmp/owasp.tar.gz https://github.com/SpiderLabs/owasp-modsecurity-crs/archive/2.2.9.tar.gz
cd /tmp/
sudo tar xf /tmp/owasp.tar.gz
sudo mv /tmp/owasp-modsecurity-crs-2.2.9/modsecurity_crs_10_setup.conf.example  $HAPROXY_PATH/waf/rules/modsecurity_crs_10_setup.conf 
sudo mv /tmp/owasp-modsecurity-crs-2.2.9/*rules/* $HAPROXY_PATH/waf/rules/
sudo sed -i 's/#SecAction/SecAction/' $HAPROXY_PATH/waf/rules/modsecurity_crs_10_setup.conf 
sudo sed -i 's/SecRuleEngine DetectionOnly/SecRuleEngine On/' $HAPROXY_PATH/waf/modsecurity.conf
sudo sed -i 's/SecAuditLogParts ABIJDEFHZ/SecAuditLogParts ABIJDEH/' $HAPROXY_PATH/waf/modsecurity.conf
sudo rm -f /tmp/owasp.tar.gz

sudo bash -c cat << EOF > /etc/systemd/system/multi-user.target.wants/waf.service 
[Unit]
Description=Defender WAF
After=syslog.target network.target

[Service]
ExecStart=$HAPROXY_PATH/waf/bin/modsecurity -n 4 -f $HAPROXY_PATH/waf/modsecurity.conf
ExecReload=/bin/kill -USR2 $MAINPID
KillMode=mixed

StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=waf

[Install]
WantedBy=multi-user.target
EOF

sudo bash -c cat << EOF > /etc/rsyslog.d/waf.conf 
if $programname startswith 'waf' then /var/log/waf.log
& stop
EOF

sudo bash -c cat << EOF > $HAPROXY_PATH/waf.conf
[modsecurity]
spoe-agent modsecurity-agent
   messages check-request
   option var-prefix modsec
   timeout hello      100ms
   timeout idle       30s
   timeout processing 15ms
   use-backend waf
   
spoe-message check-request
   args unique-id method path query req.ver req.hdrs_bin req.body_size req.body
   event on-frontend-http-request
EOF
if sudo grep -q "backend spoe-modsecurity" $HAPROXY_PATH/haproxy.cfg; then
	echo -e "Backend for WAF exists"
else
	sudo bash -c cat << EOF >> $HAPROXY_PATH/haproxy.cfg

backend waf
    mode tcp
    timeout connect 5s
    timeout server  3m
    server waf 127.0.0.1:12345 check
EOF
fi
	
sudo systemctl daemon-reload
sudo systemctl enable waf
sudo systemctl restart waf
sudo rm -f /tmp/libevent-devel-2.0.21-4.el7.x86_64.rpm
sudo rm -f /tmp/modsecurity-2.9.2.tar.gz
sudo rm -f /tmp/yajl-devel-2.0.4-4.el7.x86_64.rpm
sudo rm -rf /tmp/haproxy-$VERSION
sudo rm -rf /tmp/haproxy-$VERSION.tar.gz
sudo rm -rf /tmp/modsecurity-2.9.2

if [ $? -eq 1 ]; then
	echo "error: Can't start Haproxy WAF service <br /><br />"
    exit 1
fi
echo "success"