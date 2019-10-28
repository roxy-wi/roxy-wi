FROM ubuntu

ENV MYSQL_ENABLE 0
ENV MYSQL_USER "haproxy-wi"
ENV MYSQL_PASS "haproxy-wi"
ENV MYSQL_DB "haproxywi2"
ENV MYSQL_HOST 127.0.0.1

ENV APACHE_RUN_DIR /var/www
ENV APACHE_LOG_DIR /var/log/apache2
ENV APACHE_RUN_USER www-data
ENV APACHE_RUN_GROUP www-data
ENV APACHE_PID_FILE /var/run/apache2$SUFFIX/apache2.pid
ENV APACHE_LOCK_DIR /var/lock/apache2
ENV LANG C
ENV APACHE_ULIMIT_MAX_FILES 'ulimit -n 65536'

RUN apt-get update && \
    apt-get install net-tools lshw dos2unix apache2 gcc netcat python3.5 python3-pip g++ freetype2-demos libatlas-base-dev python-ldap libpq-dev python-dev libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libffi-dev python3-dev libssl-dev libfreetype6-dev libpng-dev -y && \
    ln -s /usr/include/freetype2/ft2build.h /usr/include/

COPY . /var/www/haproxy-wi

WORKDIR /var/www/haproxy-wi

RUN chown -R www-data:www-data . && \
    pip3 install -r requirements.txt && \
    mkdir /var/www/haproxy-wi/keys/ && \
    mkdir -p /var/www/haproxy-wi/configs/hap_config && \
    cp /var/www/haproxy-wi/config_other/httpd/haproxy-wi.conf /etc/apache2/sites-available/ && \
    cp /var/www/haproxy-wi/config_other/httpd/000-default.conf /etc/apache2/sites-available/ && \
    ln -s /etc/apache2/mods-available/ssl.conf /etc/apache2/mods-enabled/ && \
    ln -s /etc/apache2/mods-available/ssl.load /etc/apache2/mods-enabled/ && \
    ln -s /etc/apache2/mods-available/socache_shmcb.load /etc/apache2/mods-enabled/ && \
    ln -s /etc/apache2/mods-available/cgi.load /etc/apache2/mods-enabled/ && \
    ln -s /etc/apache2/mods-available/cgid.load /etc/apache2/mods-enabled/ && \
    ln -s /etc/apache2/mods-available/cgid.conf /etc/apache2/mods-enabled/ && \
    ln -s /var/log/apache2 /var/log/httpd

# Build sql database
RUN set -ex; \
        if [ "$MYSQL_ENABLE" -eq 0 ]; then \
                cd /var/www/haproxy-wi/app && \
                ./create_db.py && \
                chown www-data:www-data /var/www/haproxy-wi/app/haproxy-wi.db; \
        fi

EXPOSE 443
VOLUME /var/www/haproxy-wi/

CMD /usr/sbin/apache2ctl -DFOREGROUND