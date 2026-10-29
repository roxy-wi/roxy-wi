"""Opt-in qualification of native startup holds on a disposable Linux lab host.

Only uniquely named test units are changed; the real keepalived unit is untouched.
No reboot or full maintenance workflow is performed by this test.
"""
import ast
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

pytestmark=pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_MAINTENANCE_SYSTEMD')!='1' or not hasattr(os,'geteuid') or os.geteuid()!=0,
    reason='Requires explicit disposable systemd lab opt-in and root')


@pytest.mark.parametrize('policy',['enabled','disabled'])
def test_native_hold_persists_until_explicit_policy_restore(policy):
    unit='roxywi-maintenance-policy-test-'+uuid4().hex+'.service'
    path=Path('/usr/local/lib/systemd/system')/unit
    source=Path(__file__).resolve().parents[2]/'app/modules/service/ha_maintenance.py'
    module=ast.parse(source.read_text())
    function=next(node for node in module.body if isinstance(node,ast.FunctionDef) and node.name=='ka_startup')
    def command(*argv,allowed=(0,)):
        result=subprocess.run(['systemctl',*argv],capture_output=True,text=True,timeout=30)
        assert result.returncode in allowed,result.stderr
        return result.stdout.strip()
    class Remote:
        def __init__(self,server):pass
        def run(self,argv,*,allowed=(0,),timeout=90):
            assert argv[0]=='systemctl' and argv[-1]=='keepalived'
            return command(*argv[1:-1],unit,allowed=allowed)
    namespace={'Remote':Remote,'RoxywiValidationError':RuntimeError}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),namespace)
    startup=namespace['ka_startup']
    path.parent.mkdir(parents=True,exist_ok=True)
    assert not path.exists() and not path.is_symlink()
    path.write_text('[Unit]\nDescription=Disposable Roxy-WI startup-policy test\n'
                    '[Service]\nExecStart=/bin/sleep infinity\n'
                    '[Install]\nWantedBy=multi-user.target\n')
    try:
        command('daemon-reload')
        command('enable' if policy=='enabled' else 'disable',unit)
        command('start',unit)
        assert startup(None,'read')==policy
        assert startup(None,'hold')=='masked'
        # Masking holds future activation without stopping the working process.
        assert command('is-active',unit)=='active'
        mask=Path('/etc/systemd/system')/unit
        assert mask.is_symlink() and os.readlink(mask)=='/dev/null'
        command('stop',unit)
        command('daemon-reload')
        assert startup(None,'read')=='masked'
        result=subprocess.run(['systemctl','start',unit],capture_output=True,text=True,timeout=30)
        assert result.returncode!=0 and 'masked' in result.stderr.lower()
        assert startup(None,'restore',policy)==policy
        command('start',unit)
        assert command('is-active',unit)=='active'
        assert startup(None,'restore',policy)==policy  # Repeated approved recovery.
    finally:
        command('unmask',unit,allowed=(0,1))
        command('stop',unit,allowed=(0,5))
        command('disable',unit,allowed=(0,1))
        path.unlink(missing_ok=True)
        command('daemon-reload')
        command('reset-failed',unit,allowed=(0,1))
