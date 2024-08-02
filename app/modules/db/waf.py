from app.modules.db.db_model import Waf, WafNginx, WafRules, Server
from app.modules.db.common import out_error


def select_waf_metrics_enable_server(ip):
	query = Waf.select(Waf.metrics).join(Server, on=(Waf.server_id == Server.server_id)).where(Server.ip == ip)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for en in query_res:
			return en.metrics


def select_waf_servers(serv):
	query = Server.select(Server.ip).join(Waf, on=(Waf.server_id == Server.server_id)).where(Server.ip == serv)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for en in query_res:
			return en.ip


def select_waf_nginx_servers(serv):
	query = Server.select(Server.ip).join(WafNginx, on=(WafNginx.server_id == Server.server_id)).where(Server.ip == serv)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for en in query_res:
			return en.ip


def insert_waf_nginx_server(server_ip):
	try:
		server_id = Server.get(Server.ip == server_ip).server_id
		WafNginx.insert(server_id=server_id).execute()
	except Exception as e:
		out_error(e)


def select_waf_servers_metrics_for_master():
	query = Server.select(Server.ip).join(
		Waf, on=(Waf.server_id == Server.server_id)
	).where((Server.enabled == 1) & Waf.metrics == 1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_waf_servers_metrics(group_id):
	if group_id == '1':
		query = Waf.select(Server.ip).join(Server, on=(Waf.server_id == Server.server_id)).where(
            (Server.enabled == 1) & (Waf.metrics == 1)
		)
	else:
		query = Waf.select(Server.ip).join(Server, on=(Waf.server_id == Server.server_id)).where(
            (Server.enabled == 1) & (Waf.metrics == 1) & (Server.group_id == group_id)
		)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_waf_metrics_enable(serv, enable):
	try:
		server_id = Server.get(Server.ip == serv).server_id
		Waf.insert(server_id=server_id, metrics=enable).execute()
	except Exception as e:
		out_error(e)


def insert_waf_rules(serv):
	data_source = [
		{'serv': serv, 'rule_name': 'Ignore static', 'rule_file': 'modsecurity_crs_10_ignore_static.conf',
			'desc': 'This ruleset will skip all tests for media files, but will skip only the request body phase (phase 2) '
					'for text files. To skip the outbound stage for text files, add file 47 (skip_outbound_checks) '
					'to your configuration, in addition to this fileth/aws/login'},
		{'serv': serv, 'rule_name': 'Brute force protection', 'rule_file': 'modsecurity_crs_11_brute_force.conf',
			'desc': 'Anti-Automation Rule for specific Pages (Brute Force Protection) This is a rate-limiting rule set and '
					'does not directly correlate whether the authentication attempt was successful or not'},
		{'serv': serv, 'rule_name': 'DOS Protections', 'rule_file': 'modsecurity_crs_11_dos_protection.conf',
			'desc': 'Enforce an existing IP address block and log only 1-time/minute. We do not want to get flooded by alerts '
					'during an attack or scan so we are only triggering an alert once/minute.  You can adjust how often you '
					'want to receive status alerts by changing the expirevar setting below'},
		{'serv': serv, 'rule_name': 'XML enabler', 'rule_file': 'modsecurity_crs_13_xml_enabler.conf',
			'desc': 'The rules in this file will trigger the XML parser upon an XML request'},
		{'serv': serv, 'rule_name': 'Protocol violations', 'rule_file': 'modsecurity_crs_20_protocol_violations.conf',
			'desc': 'Some protocol violations are common in application layer attacks. Validating HTTP requests eliminates a '
					'large number of application layer attacks. The purpose of this rules file is to enforce HTTP RFC requirements '
					'that state how  the client is supposed to interact with the server. http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html'},
		{'serv': serv, 'rule_name': 'Protocol anomalies', 'rule_file': 'modsecurity_crs_21_protocol_anomalies.conf',
			'desc': 'Some common HTTP usage patterns are indicative of attacks but may also be used by non-browsers for '
					'legitimate uses. Do not accept requests without common headers. All normal web browsers include Host, '
					'User-Agent and Accept headers. Implies either an attacker or a legitimate automation client'},
		{'serv': serv, 'rule_name': 'Detect CC#', 'rule_file': 'modsecurity_crs_25_cc_known.conf',
			'desc': 'Detect CC# in input, log transaction and sanitize'},
		{'serv': serv, 'rule_name': 'CC traker', 'rule_file': 'modsecurity_crs_25_cc_track_pan.conf',
			'desc': 'Credit Card Track 1 and 2 and PAN Leakage Checks'},
		{'serv': serv, 'rule_name': 'HTTP policy', 'rule_file': 'modsecurity_crs_30_http_policy.conf',
			'desc': 'HTTP policy enforcement The HTTP policy enforcement rule set sets limitations on the use of HTTP by '
					'clients. Few applications require the breadth and depth of the HTTP protocol. On the other hand many '
					'attacks abuse valid but rare HTTP use patterns. Restricting  HTTP protocol usage is effective in '
					'therefore effective in blocking many  application layer attacks'},
		{'serv': serv, 'rule_name': 'Bad robots', 'rule_file': 'modsecurity_crs_35_bad_robots.conf',
			'desc': 'Bad robots detection is based on checking elements easily controlled by the client. As such a '
					'determined attacked can bypass those checks. Therefore bad robots detection should not be viewed '
					'as a security mechanism against targeted attacks but rather as a nuisance reduction, eliminating '
					'most of the random attacks against your web site'},
		{'serv': serv, 'rule_name': 'OS Injection Attacks', 'rule_file': 'modsecurity_crs_40_generic_attacks.conf',
			'desc': 'OS Command Injection Attacks'},
		{'serv': serv, 'rule_name': 'SQL injection', 'rule_file': 'modsecurity_crs_41_sql_injection_attacks.conf',
			'desc': 'SQL injection protection'},
		{'serv': serv, 'rule_name': 'XSS Protections', 'rule_file': 'modsecurity_crs_41_xss_attacks.conf',
			'desc': 'XSS attacks protection'},
		{'serv': serv, 'rule_name': 'Comment spam', 'rule_file': 'modsecurity_crs_42_comment_spam.conf',
			'desc': 'Comment spam is an attack against blogs, guestbooks, wikis and other types of interactive web sites '
					'that accept and display hyperlinks submitted by visitors. The spammers automatically post specially '
					'crafted random comments which include links that point to the spammer\'s web site. The links artificially '
					'increase the site\'s search engine ranking and may make the site more noticable in search results.'},
		{'serv': serv, 'rule_name': 'Trojans Protections', 'rule_file': 'modsecurity_crs_45_trojans.conf ',
			'desc': 'The trojan access detection rules detects access to known Trojans already installed on a server. '
					'Uploading of Trojans is part of the Anti-Virus rules  and uses external Anti Virus program when uploading '
					'files. Detection of Trojans access is especially important in a hosting environment where the actual Trojan '
					'upload may be done through valid methods and not through hacking'},
		{'serv': serv, 'rule_name': 'RFI Protections', 'rule_file': 'modsecurity_crs_46_slr_et_lfi_attacks.conf',
			'desc': 'Remote file inclusion is an attack targeting vulnerabilities in web applications that dynamically reference '
					'external scripts. The perpetrator’s goal is to exploit the referencing function in an application to upload '
					'malware (e.g., backdoor shells) from a remote URL located within a different domain'},
		{'serv': serv, 'rule_name': 'RFI Protections 2', 'rule_file': 'modsecurity_crs_46_slr_et_rfi_attacks.conf',
			'desc': 'Remote file inclusion is an attack targeting vulnerabilities in web applications that dynamically reference '
					'external scripts. The perpetrator’s goal is to exploit the referencing function in an application to '
					'upload malware (e.g., backdoor shells) from a remote URL located within a different domain'},
		{'serv': serv, 'rule_name': 'SQLi Protections', 'rule_file': 'modsecurity_crs_46_slr_et_sqli_attacks.conf',
			'desc': 'SQLi injection attacks protection'},
		{'serv': serv, 'rule_name': 'XSS Protections 2', 'rule_file': 'modsecurity_crs_46_slr_et_xss_attacks.conf',
			'desc': 'XSS attacks protection'},
		{'serv': serv, 'rule_name': 'Common exceptions', 'rule_file': 'modsecurity_crs_47_common_exceptions.conf',
			'desc': 'This file is used as an exception mechanism to remove common false positives that may be encountered'},
	]
	try:
		WafRules.insert_many(data_source).execute()
	except Exception as e:
		out_error(e)
	else:
		return True


def insert_nginx_waf_rules(serv):
	data_source = [
		{'serv': serv, 'rule_name': 'Initialization', 'rule_file': 'REQUEST-901-INITIALIZATION.conf',
			'desc': 'This file REQUEST-901-INITIALIZATION.conf initializes the Core Rules and performs preparatory actions. '
					'It also fixes errors and omissions of variable definitions in the file crs-setup.conf The setup.conf'
					'can and should be edited by the user, this file. is part of the CRS installation and should not be altered.',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Drupal exclusion rules', 'rule_file': 'REQUEST-903.9001-DRUPAL-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default Drupal install. The exclusions are only active '
					'if crs_exclusions_drupal=1 is set. See rule 900130 in crs-setup.conf for instructions.',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Nextcloud exclusion rules', 'rule_file': 'REQUEST-903.9003-NEXTCLOUD-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default NextCloud install. They will likely work with OwnCloud '
					'too, but you may have to modify them. The exclusions are only active if crs_exclusions_nextcloud=1 is set. '
					'See rule 900130 in crs-setup.conf for instructions.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Dokuwiki exclusion rules', 'rule_file': 'REQUEST-903.9004-DOKUWIKI-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default Dokuwiki install. The exclusions are only active '
					'if crs_exclusions_dokuwiki=1 is set. See rule 900130 in crs-setup.conf for instructions.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'CPanel exclusion rules', 'rule_file': 'REQUEST-903.9005-CPANEL-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default CPanel install. The exclusions are only active '
					'if crs_exclusions_cpanel=1 is set. See rule 900130 in crs-setup.conf for instructions.',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'XenForo exclusion rules', 'rule_file': 'REQUEST-903.9006-XENFORO-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default XenForo install. The exclusions are only active '
					'if crs_exclusions_xenforo=1 is set. See rule 900130 in crs-setup.conf for instructions.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Common exceptions', 'rule_file': 'REQUEST-905-COMMON-EXCEPTIONS.conf',
			'desc': 'This file is used as an exception mechanism to remove common false positives that may be encountered.',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'IP reputation', 'rule_file': 'REQUEST-910-IP-REPUTATION.conf',
			'desc': 'IP reputation rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Method enforcement', 'rule_file': 'REQUEST-911-METHOD-ENFORCEMENT.conf',
			'desc': 'Method enforcement rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'DDOS protection', 'rule_file': 'REQUEST-912-DOS-PROTECTION.conf',
			'desc': 'Anti-Automation rules to detect Denial of Service attacks.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Protocol enforcement', 'rule_file': 'REQUEST-920-PROTOCOL-ENFORCEMENT.conf',
			'desc': 'Some protocol violations are common in application layer attacks. Validating HTTP requests eliminates '
					'a large number of application layer attacks. The purpose of this rules file is to enforce HTTP RFC '
					'requirements that state how the client is supposed to interact with the server.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Protocol attack', 'rule_file': 'REQUEST-921-PROTOCOL-ATTACK.conf',
			'desc': 'Protocol attack rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack LFI', 'rule_file': 'REQUEST-930-APPLICATION-ATTACK-LFI.conf',
			'desc': 'Application attack LFI rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack RCE', 'rule_file': 'REQUEST-932-APPLICATION-ATTACK-RCE.conf',
			'desc': 'Application attack RCE rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack PHP', 'rule_file': 'REQUEST-933-APPLICATION-ATTACK-PHP.conf',
			'desc': 'Application attack PHP rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack NodeJS', 'rule_file': 'REQUEST-934-APPLICATION-ATTACK-NODEJS.conf',
			'desc': 'Application attack NodeJS rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack SQLI', 'rule_file': 'REQUEST-942-APPLICATION-ATTACK-SQLI.conf',
			'desc': 'Application attack SQLI rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack session-fixation', 'rule_file': 'REQUEST-943-APPLICATION-ATTACK-SESSION-FIXATION.conf',
			'desc': 'Application attack session-fixation rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack JAVA', 'rule_file': 'REQUEST-944-APPLICATION-ATTACK-JAVA.conf',
			'desc': 'Application attack JAVA rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack blocking evaluation', 'rule_file': 'REQUEST-949-BLOCKING-EVALUATION.conf',
			'desc': 'Application attack blocking evaluation rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages', 'rule_file': 'RESPONSE-950-DATA-LEAKAGES.conf',
			'desc': 'The paranoia level skip rules 950020, 950021 and 950022 have odd numbers not in sync with other paranoia '
					'level skip rules in other. files. This is done to avoid rule id collisions with CRSv2. This is also true '
					'for rule 950130.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages SQL', 'rule_file': 'RESPONSE-951-DATA-LEAKAGES-SQL.conf',
			'desc': 'Data leakages SQL rule', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages JAVA', 'rule_file': 'RESPONSE-952-DATA-LEAKAGES-JAVA.conf',
			'desc': 'Data leakages JAVA rule', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages PHP', 'rule_file': 'RESPONSE-953-DATA-LEAKAGES-PHP.conf',
			'desc': 'Data leakages PHP rule', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages IIS', 'rule_file': 'RESPONSE-954-DATA-LEAKAGES-IIS.conf',
			'desc': 'Data leakages IIS rule', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Blocking evaluation', 'rule_file': 'RESPONSE-959-BLOCKING-EVALUATION.conf',
			'desc': 'You should set the score to the proper threshold you would prefer. If kept at "@gt 0" it will work '
					'similarly to previous Mod CRS rules and will create an event in the error_log file if there are any '
					'rules that match.  If you would like to lessen the number of events generated in the error_log file, '
					'you should increase the anomaly score threshold to something like "@gt 20".  This would only generate '
					'an event in the error_log file if there are multiple lower severity rule matches or if any 1 higher '
					'severity item matches. You should also set the desired disruptive action (deny, redirect, etc...).',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Correlation', 'rule_file': 'RESPONSE-980-CORRELATION.conf',
			'desc': 'This file is used in post processing after the response has been sent to the client (in the logging phase). '
					'Its purpose is to provide inbound+outbound correlation of events to provide a more intelligent designation '
					'as to the outcome or result of the transaction - meaning, was this a successful attack?',
			'service': 'nginx'},
	]
	try:
		WafRules.insert_many(data_source).execute()
	except Exception as e:
		out_error(e)
	else:
		return True


def select_waf_rules(serv, service):
	query = WafRules.select(WafRules.id, WafRules.rule_name, WafRules.en, WafRules.desc).where(
		(WafRules.serv == serv)
		& (WafRules.service == service)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def delete_waf_rules(serv):
	query = WafRules.delete().where(WafRules.serv == serv)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_waf_rule_by_id(rule_id):
	try:
		query = WafRules.get(WafRules.id == rule_id)
	except Exception as e:
		out_error(e)
	else:
		return query.rule_file


def update_enable_waf_rules(rule_id, serv, en):
	query = WafRules.update(en=en).where((WafRules.id == rule_id) & (WafRules.serv == serv))
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_new_waf_rule(rule_name: str, rule_file: str, rule_description: str, service: str, serv: str) -> int:
	try:
		last_id = WafRules.insert(
			serv=serv,
			rule_name=rule_name,
			rule_file=rule_file,
			desc=rule_description,
			service=service
		).execute()
	except Exception as e:
		out_error(e)
	else:
		return last_id


def delete_waf_server(server_id):
	query = Waf.delete().where(Waf.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def update_waf_metrics_enable(name, enable):
	server_id = 0
	try:
		server_id = Server.get(Server.hostname == name).server_id
	except Exception as e:
		out_error(e)

	try:
		Waf.update(metrics=enable).where(Waf.server_id == server_id).execute()
	except Exception as e:
		out_error(e)
