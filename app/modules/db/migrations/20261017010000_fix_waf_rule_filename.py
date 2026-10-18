from app.modules.db.db_model import WafRules


def up():
    # Older installations registered this bundled rule with a trailing space.
    WafRules.update(rule_file='modsecurity_crs_45_trojans.conf').where(
        WafRules.rule_file == 'modsecurity_crs_45_trojans.conf '
    ).execute()


def down():
    raise RuntimeError('Restoring an invalid WAF filename would prevent rule management')
