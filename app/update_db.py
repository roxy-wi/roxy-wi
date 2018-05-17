#!/usr/bin/env python3
# -*- coding: utf-8 -*-"
import create_db
import funct

mysql_enable = funct.get_config_var('mysql', 'enable')

if mysql_enable == '1':
	from mysql.connector import errorcode
	import mysql.connector as sqltool
else:
	db = "haproxy-wi.db"
	import sqlite3 as sqltool
	
create_db.create_table()
create_db.update_all()