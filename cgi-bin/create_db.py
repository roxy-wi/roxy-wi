#!/usr/bin/env python3
import sqlite3 as sqlite
import os
import sys

db = "haproxy-wi.db"

def check_db():
	if os.path.isfile(db):
		if os.path.getsize(db) > 100:
			with open(db,'r', encoding = "ISO-8859-1") as f:
				header = f.read(100)
				if header.startswith('SQLite format 3'):
					print("SQLite3 database has been detected.")
					return False
				else:
					return True
 
def get_cur():
	con = sqlite.connect(db, isolation_level=None)
	cur = con.cursor()    
	return con, cur

def create_table():
	con, cur = get_cur()
	sql = """
	BEGIN TRANSACTION;
	CREATE TABLE IF NOT EXISTS `user` (
		`id`	INTEGER NOT NULL,
		`username`	VARCHAR ( 64 ) UNIQUE,
		`email`	VARCHAR ( 120 ) UNIQUE,
		`password`	VARCHAR ( 128 ),
		`role`	VARCHAR ( 128 ),
		`groups`	VARCHAR ( 120 ),
		PRIMARY KEY(`id`) 
	);
	INSERT INTO `user` (username, email, password, role, groups) VALUES ('admin','admin@localhost','admin','admin','1'),
	 ('editor','editor@localhost','editor','editor','1'),
	 ('guest','guest@localhost','guest','guest','1');
	CREATE TABLE IF NOT EXISTS `servers` (
		`id`	INTEGER NOT NULL,
		`hostname`	VARCHAR ( 64 ) UNIQUE,
		`ip`	VARCHAR ( 64 ) UNIQUE,
		`groups`	VARCHAR ( 64 ),
		PRIMARY KEY(`id`) 
	);
	CREATE TABLE IF NOT EXISTS `roles_users` (
		`user_id`	INTEGER,
		`role_id`	INTEGER,
		FOREIGN KEY(`user_id`) REFERENCES `user`(`id`),
		FOREIGN KEY(`role_id`) REFERENCES `role`(`id`)
	);
	CREATE TABLE IF NOT EXISTS `role` (
		`id`	INTEGER NOT NULL,
		`name`	VARCHAR ( 80 ) UNIQUE,
		`description`	VARCHAR ( 255 ),
		PRIMARY KEY(`id`) 
	);
	INSERT INTO `role` (name, description) VALUES ('admin','Can do everything'),
	 ('editor','Can edit configs'),
	 ('guest','Read only access');
	CREATE TABLE IF NOT EXISTS `groups` (
		`id`	INTEGER NOT NULL,
		`name`	VARCHAR ( 80 ) UNIQUE,
		`description`	VARCHAR ( 255 ),
		PRIMARY KEY(`id`) 
	);
	INSERT INTO `groups` (name, description) VALUES ('All','All servers enter in this group');
	COMMIT;
	"""
	 
	try:    
		cur.executescript(sql)
	except sqlite.Error as e:
		print("An error occurred:", e.args[0])
	else:
		print("DB was created")
	cur.close() 
	con.close()
	
def update_db_v_2_0_1():
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN type_ip INTEGER NOT NULL DEFAULT(0);
	"""
	try:    
		cur.executescript(sql)
	except sqlite.Error as e:
		if e.args[0] == 'duplicate column name: type_ip':
			print('Updating... go to version 2.0.1.1')
			return False
		else:
			print("An error occurred:", e.args[0])
			return False
	else:
		print("DB was update to 2.0.1")
		return True
	cur.close() 
	con.close()

def update_db_v_2_0_1_1():
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN enable INTEGER NOT NULL DEFAULT(1);
	"""
	try:    
		cur.executescript(sql)
	except sqlite.Error as e:
		if e.args[0] == 'duplicate column name: enable':
			print('Already updated. No run more. Thx =^.^=')
			return False
		else:
			print("An error occurred:", e.args[0])
			return False
	else:
		print("DB was update to 2.0.1.1")
		return True
	cur.close() 
	con.close()
	
if check_db():	
	create_table()
else:
	print('DB already exists, try update')
if update_db_v_2_0_1():
	print('DB was property update to version 2.0.1.')
update_db_v_2_0_1_1()