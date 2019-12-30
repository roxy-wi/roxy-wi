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
VERSION=$(echo $VERSION | awk -F"-" '{print $1}')
VERSION_MAJ=$(echo $VERSION | awk -F"." '{print $1"."$2}')

if (( $(awk 'BEGIN {print ("'$VERSION_MAJ'" < "'1.8'")}') )); then
	echo 'error: Need HAProxy version 1.8 or later <a title="Close" id="errorMess"><b>X</b></a>'
	exit 1
fi

if [[ $PROXY != "" ]]
then
	export http_proxy="$PROXY"
	export https_proxy="$PROXY"
fi

if [ -f $HAPROXY_PATH/waf/modsecurity.conf  ];then
	echo -e 'Info: Haproxy WAF already installed.  <br /><br />'
	exit 1
fi
if hash apt-get 2>/dev/null; then
	sudo apt install libevent-dev apache2-dev libpcre3-dev libxml2-dev gcc pcre-devel -y
else
	sudo yum install -y http://rpmfind.net/linux/centos/7/os/x86_64/Packages/yajl-devel-2.0.4-4.el7.x86_64.rpm >> /dev/null
	sudo yum install -y http://mirror.centos.org/centos/7/os/x86_64/Packages/libevent-devel-2.0.21-4.el7.x86_64.rpm >> /dev/null
	sudo yum install -y httpd-devel libxml2-devel gcc curl-devel pcre-devel -y >> /dev/null
fi

wget -O /tmp/modsecurity.tar.gz https://www.modsecurity.org/tarball/2.9.2/modsecurity-2.9.2.tar.gz >> /dev/null

if [ $? -eq 1 ]; then
	echo -e "Can't download waf application. Check Internet connection"
	exit 1
fi
cd /tmp
sudo tar xf modsecurity.tar.gz
sudo mv modsecurity-2.9.2 modsecurity
sudo bash -c 'cd /tmp/modsecurity && \
sudo ./configure --prefix=/tmp/modsecurity --enable-standalone-module --disable-mlogc --enable-pcre-study --without-lua --enable-pcre-jit >> /dev/null && \
sudo make >> /dev/null && \
sudo make -C standalone install >> /dev/null'
if [ $? -eq 1 ]; then
	echo -e "error: Can't compile waf application"
	exit 1
fi
sudo mkdir -p /tmp/modsecurity/INSTALL/include
sudo cp -R /tmp/modsecurity/standalone/.libs/ /tmp/modsecurity/INSTALL/include
sudo cp -R /tmp/modsecurity/standalone/ /tmp/modsecurity/INSTALL/include
sudo cp -R /tmp/modsecurity/apache2/ /tmp/modsecurity/INSTALL/include
sudo chown -R $(whoami):$(whoami) /tmp/modsecurity/
mv /tmp/modsecurity/INSTALL/include/.libs/* /tmp/modsecurity/INSTALL/include
mv /tmp/modsecurity/INSTALL/include/apache2/* /tmp/modsecurity/INSTALL/include
mv /tmp/modsecurity/INSTALL/include/standalone/* /tmp/modsecurity/INSTALL/include

wget -O /tmp/haproxy-$VERSION.tar.gz http://www.haproxy.org/download/$VERSION_MAJ/src/haproxy-$VERSION.tar.gz

if [ $? -eq 1 ]; then
	echo -e "error: Can't download Haproxy application. Check Internet connection"
	exit 1
fi
cd /tmp
sudo tar xf /tmp/haproxy-$VERSION.tar.gz
sudo mkdir $HAPROXY_PATH/waf
sudo mkdir $HAPROXY_PATH/waf/bin
sudo mkdir $HAPROXY_PATH/waf/rules
cd /tmp/haproxy-$VERSION/contrib/modsecurity
if hash apt-get 2>/dev/null; then
	sudo make MODSEC_INC=/tmp/modsecurity/INSTALL/include MODSEC_LIB=/tmp/modsecurity/INSTALL/include APR_INC=/usr/include/apr-1 >> /dev/null
else
	sudo make MODSEC_INC=/tmp/modsecurity/INSTALL/include MODSEC_LIB=/tmp/modsecurity/INSTALL/include APACHE2_INC=/usr/include/httpd/ APR_INC=/usr/include/apr-1 >> /dev/null
fi
if [ $? -eq 1 ]; then
	echo -e "error: Can't compile waf application"
	exit 1
fi
sudo mv /tmp/haproxy-$VERSION/contrib/modsecurity/modsecurity $HAPROXY_PATH/waf/bin
if [ $? -eq 1 ]; then
	echo -e "error: Can't compile waf application"
	exit 1
fi
wget -O /tmp/modsecurity.conf https://github.com/SpiderLabs/ModSecurity/raw/v2/master/modsecurity.conf-recommended 

sudo bash -c cat << EOF >> /tmp/modsecurity.conf
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

sudo mv /tmp/modsecurity.conf $HAPROXY_PATH/waf/modsecurity.conf 
wget -O /tmp/unicode.mapping https://github.com/SpiderLabs/ModSecurity/raw/v2/master/unicode.mapping
sudo mv /tmp/unicode.mapping $HAPROXY_PATH/waf/unicode.mapping
wget -O /tmp/owasp.tar.gz https://github.com/SpiderLabs/owasp-modsecurity-crs/archive/v3.0.2.tar.gz
cd /tmp/
sudo tar xf /tmp/owasp.tar.gz
sudo mv /tmp/owasp-modsecurity-crs-3.0.2/crs-setup.conf.example  $HAPROXY_PATH/waf/rules/modsecurity_crs_10_setup.conf 
sudo mv /tmp/owasp-modsecurity-crs-3.0.2/*rules/* $HAPROXY_PATH/waf/rules/
sudo sed -i 's/#SecAction/SecAction/' $HAPROXY_PATH/waf/rules/modsecurity_crs_10_setup.conf 
sudo sed -i 's/SecRuleEngine DetectionOnly/SecRuleEngine On/' $HAPROXY_PATH/waf/modsecurity.conf
sudo sed -i 's/SecAuditLogParts ABIJDEFHZ/SecAuditLogParts ABIJDEH/' $HAPROXY_PATH/waf/modsecurity.conf
sudo rm -f /tmp/owasp.tar.gz

sudo bash -c cat << EOF > /tmp/waf.service 
[Unit]
Description=Haproxy WAF
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
sudo mv /tmp/waf.service  /etc/systemd/system/multi-user.target.wants/waf.service 
sudo bash -c 'cat << EOF > /etc/rsyslog.d/waf.conf 
if $programname startswith "waf" then /var/log/waf.log
& stop
EOF'

sudo bash -c cat << EOF > /tmp/waf.conf
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

sudo mv /tmp/waf.conf $HAPROXY_PATH/waf.conf
if sudo grep -q "backend waf" $HAPROXY_PATH/haproxy.cfg; then
	echo -e "Backend for WAF exists"
else
	sudo bash -c 'cat << EOF >> /etc/haproxy/haproxy.cfg

backend waf
    mode tcp
    timeout connect 5s
    timeout server  3m
    server waf 127.0.0.1:12345 check
EOF'
fi
	
sudo systemctl daemon-reload
sudo systemctl enable waf
sudo systemctl restart waf
sudo rm -f /tmp/modsecurity.tar.gz
sudo rm -rf /tmp/haproxy-$VERSION.tar.gz

if [ $? -eq 1 ]; then
	echo "error: Can't start Haproxy WAF service <br /><br />"
    exit 1
fi
echo "success"