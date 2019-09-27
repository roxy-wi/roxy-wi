FROM centos

MAINTAINER Pavel Loginov (https://github.com/Aidaho12/haproxy-wi)
# REFACT by Vagner Rodrigues Fernandes (vagner.rodrigues@gmail.com)
# REFACT by Mauricio Nunes ( mutila@gmail.com )

ENV MYSQL_ENABLE 0
ENV MYSQL_USER "haproxy-wi"
ENV MYSQL_PASS "haproxy-wi"
ENV MYSQL_DB "haproxywi"
ENV MYSQL_HOST 127.0.0.1

# Copy external files
COPY httpd/haproxy-wi.conf /etc/httpd/conf.d/haproxy-wi.conf

# Yum clean cache
RUN yum remove epel-release && \
        rm -rf /var/lib/rpm/__db* && \
        yum clean all

# Yum install base packages
RUN yum -y install https://centos7.iuscommunity.org/ius-release.rpm && \ 
        yum -y install \
		epel-release \
        git \
        nmap-ncat \
        net-tools \
        python35u \
        python35u-pip \
        python35u-devel \
        python34-devel \
        dos2unix \
        httpd \
        gcc-c++ \
        gcc \
        gcc-gfortran \
        yum-plugin-remove-with-leaves \
        openldap-devel \
		mod_ssl

# Clone haproxy-wi git repo
RUN git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/haproxy-wi && \
        sed -i "s/enable = 0/enable = $MYSQL_ENABLE/g" /var/www/haproxy-wi/app/haproxy-wi.cfg && \
        sed -i "s/mysql_user = haproxy-wi/mysql_user = $MYSQL_USER/g" /var/www/haproxy-wi/app/haproxy-wi.cfg && \
        sed -i "s/mysql_password = haproxy-wi/mysql_password = $MYSQL_PASS/g" /var/www/haproxy-wi/app/haproxy-wi.cfg && \
        sed -i "s/mysql_db = haproxywi/mysql_db = $MYSQL_DB/g" /var/www/haproxy-wi/app/haproxy-wi.cfg && \
        sed -i "s/mysql_host = 127.0.0.1/mysql_host = $MYSQL_HOST/g" /var/www/haproxy-wi/app/haproxy-wi.cfg && \
        mkdir /var/www/haproxy-wi/keys/ && \
        mkdir -p /var/www/haproxy-wi/configs/hap_config && \
        chown -R apache:apache /var/www/haproxy-wi/

# PIP Install deps
RUN pip3.5 install -r /var/www/haproxy-wi/requirements.txt --no-cache-dir

# Fix app haproxy-wi perms
RUN chmod +x /var/www/haproxy-wi/app/*.py && \
        chmod +x /var/www/haproxy-wi/app/tools/*.py && \
        chown -R apache:apache /var/log/httpd/    


RUN chown -R apache:apache /var/www/haproxy-wi

# Yum clear container
RUN yum -y erase \
        git \
        python35u-pip \
        gcc-c++ \
        gcc-gfortran \
        gcc \
        --remove-leaves && \
        yum -y autoremove yum-plugin-remove-with-leaves && \
        yum clean all && \
        rm -rf /var/cache/yum && \
        rm -f /etc/yum.repos.d/*

# Python link
RUN ln -s /usr/bin/python3.5 /usr/bin/python3

# Build sql database
RUN set -ex; \
        if [ $MYSQL_ENABLE -eq 0 ]; then \
                cd /var/www/haproxy-wi/app && \
                ./create_db.py && \
                chown apache:apache /var/www/haproxy-wi/app/haproxy-wi.db \
        fi

EXPOSE 443
VOLUME /var/www/haproxy-wi/

CMD /usr/sbin/httpd -DFOREGROUND
