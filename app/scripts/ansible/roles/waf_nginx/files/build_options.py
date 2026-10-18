"""Read module build inputs from the installed NGINX binary (host Python 3.6)."""
import json
import re
import shlex
import subprocess


def build_options(output):
    version = re.search(r'^nginx version: nginx/(\d+\.\d+\.\d+)(?:\s|$)', output, re.MULTILINE)
    configure = re.search(r'^configure arguments:\s*(.*)$', output, re.MULTILINE)
    if not version or not configure:
        raise ValueError('Cannot determine the installed NGINX version and build options')
    # Package builders' external module source directories do not exist here.
    arguments = [argument for argument in shlex.split(configure.group(1))
                 if not argument.startswith(('--add-module=', '--add-dynamic-module='))]
    if '--with-compat' not in arguments:
        arguments.append('--with-compat')
    return dict(version=version.group(1), arguments=arguments)


if __name__ == '__main__':
    result = subprocess.run(['nginx', '-V'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            universal_newlines=True, check=True, timeout=10)
    print(json.dumps(build_options(result.stdout)))
