FROM centos
MAINTAINER Pavel Loginov (https://github.com/Aidaho12/haproxy-wi)

ENV http_proxy ip:3128
ENV https_proxy ip:3128

COPY epel.repo /etc/yum.repos.d/epel.repo

RUN yum -y install git nmap-ncat python34 dos2unix python34-pip httpd yum-plugin-remove-with-leaves svn gcc-c++ gcc gcc-gfortran python34-devel

COPY haproxy-wi.conf /etc/httpd/conf.d/haproxy-wi.conf

RUN git clone https://github.com/Aidaho12/haproxy-wi.git /var/www/haproxy-wi

RUN mkdir /var/www/haproxy-wi/keys/
RUN mkdir /var/www/haproxy-wi/app/certs/
RUN chown -R apache:apache /var/www/haproxy-wi/
RUN pip3 install -r /var/www/haproxy-wi/requirements.txt --no-cache-dir
RUN chmod +x /var/www/haproxy-wi/app/*.py
RUN chmod +x /var/www/haproxy-wi/app/tools/*.py
WORKDIR /var/www/haproxy-wi/app
RUN ./update_db.py
RUN chown -R apache:apache /var/www/haproxy-wi/
RUN chown -R apache:apache /var/log/httpd/
RUN tools/checker_master.py &

RUN yum -y erase git python34-pip python34-devel gcc-c++  gcc-gfortran gcc --remove-leaves
RUN yum -y autoremove yum-plugin-remove-with-leaves
RUN yum clean all
RUN rm -rf /var/cache/yum
RUN rm -f /etc/yum.repos.d/*

EXPOSE 80
VOLUME /var/www/haproxy-wi/

CMD /usr/sbin/httpd -DFOREGROUND