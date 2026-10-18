import json
from pathlib import Path
import shlex

from jinja2 import Environment

from app.modules.db.db_model import WafNginx, WafRules
from app.modules.service import installation


def test_nginx_installation_registers_all_included_rules_and_retry_preserves_edits(product):
    installation.waf_actions_after_install(product.server.ip, 'nginx')
    rules = list(WafRules.select().where(WafRules.serv == product.server.ip))
    rules[0].en = 0
    rules[0].desc = 'Edited by administrator'
    rules[0].save()
    installation.waf_actions_after_install(product.server.ip, 'nginx')
    assert WafRules.select().count() == len(rules)
    assert WafNginx.select().count() == 1
    assert WafRules.get_by_id(rules[0].id).en == 0
    assert WafRules.get_by_id(rules[0].id).desc == 'Edited by administrator'
    template = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles/waf_nginx/templates/waf.conf.j2'
    environment = Environment()
    environment.filters['to_json'] = json.dumps
    rendered = environment.from_string(template.read_text()).render(SERVICE_PATH='/srv/nginx')
    includes = {Path(shlex.split(line)[1]).name for line in rendered.splitlines() if '/rules/' in line}
    assert {rule.rule_file for rule in rules} == includes
