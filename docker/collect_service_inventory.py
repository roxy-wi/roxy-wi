#!/usr/bin/env python3
"""Publish a small read-only deployment inventory; never publish inspect/env output.

Run on the deployment host as the Docker/Podman owner. Roxy-WI itself only reads
the resulting JSON file from its existing data volume, without an engine socket.
"""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ALIASES = {
    'web': 'roxy-wi-web', 'scheduler': 'roxy-wi-scheduler',
    'service-events': 'roxy-wi-service-events', 'operations': 'roxy-wi-operations',
    'metrics': 'roxy-wi-metrics', 'checker': 'roxy-wi-checker',
    'portscanner': 'roxy-wi-portscanner', 'port-scanner': 'roxy-wi-portscanner',
    'socket': 'roxy-wi-socket', 'keep_alive': 'roxy-wi-keep_alive',
    'keep-alive': 'roxy-wi-keep_alive', 'auto-start': 'roxy-wi-keep_alive',
    'autostart': 'roxy-wi-keep_alive', 'prometheus-exporter': 'roxy-wi-prometheus-exporter',
    'smon': 'roxy-wi-smon',
}
SERVICES = set(ALIASES.values())
PACKAGES = {
    'roxy-wi-keep-alive': 'roxy-wi-keep_alive',
    'roxy-wi-keep_alive': 'roxy-wi-keep_alive',
    **{name: name for name in SERVICES if name not in {
        'roxy-wi-web', 'roxy-wi-scheduler', 'roxy-wi-service-events', 'roxy-wi-operations',
    }},
}


def command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout


def service_name(container):
    name = container.get('Name', '').lstrip('/')
    if name in SERVICES:
        return name
    for prefix in ('roxy-wi-', 'roxywi-'):
        if name.startswith(prefix) and name[len(prefix):] in ALIASES:
            return ALIASES[name[len(prefix):]]
    labels = container.get('Config', {}).get('Labels') or {}
    # Do not classify unrelated projects just because they have a service 'web'.
    project = labels.get('com.docker.compose.project', '')
    reference = container.get('ImageName') or container.get('Config', {}).get('Image', '')
    if 'roxy' in project.lower() or reference.startswith('ghcr.io/roxy-wi/'):
        return ALIASES.get(labels.get('com.docker.compose.service', ''))
    return None


def image_version(image, reference):
    labels = image.get('Config', {}).get('Labels') or {}
    version = labels.get('org.opencontainers.image.version', '')
    if version and len(version) <= 128:
        return version, 'image_label'
    # A pinned image tag identifies the deployed artifact, not a runtime probe.
    tag = reference.rsplit('/', 1)[-1].partition(':')[2] if '@' not in reference else ''
    if re.fullmatch(r'v?\d+(?:\.\d+){1,3}(?:(?:a|b|rc)\d+)?', tag):
        return tag, 'image_tag'
    return None, 'unknown'


def collect_containers(engine):
    ids = command([engine, 'ps', '-aq']).split()
    services = []
    images = {}
    containers = []
    for offset in range(0, len(ids), 64):
        containers.extend(json.loads(command([engine, 'container', 'inspect', *ids[offset:offset + 64]])))
    for container in containers:
        name = service_name(container)
        if name is None:
            continue
        image_id = container['Image']
        if image_id not in images:
            images[image_id] = json.loads(command([engine, 'image', 'inspect', image_id]))[0]
        reference = container.get('ImageName') or container.get('Config', {}).get('Image', '')
        version, source = image_version(images[image_id], reference)
        services.append({
            'service': name, 'version': version, 'version_source': source,
            'running': container.get('State', {}).get('Running') is True,
            'container': container.get('Name', '').lstrip('/'),
            'image': reference, 'image_id': image_id, 'manager': engine,
        })
    return services


def collect_packages():
    services = []
    for package, service in PACKAGES.items():
        try:
            if shutil.which('dpkg-query'):
                output = command(['dpkg-query', '-W', '-f=${db:Status-Status}\t${Version}', package])
                state, version = output.strip().split('\t', 1)
                if state != 'installed':
                    continue
            elif shutil.which('rpm'):
                version = command(['rpm', '-q', '--qf', '%{VERSION}', package]).strip()
            else:
                break
        except subprocess.CalledProcessError:
            continue
        running = False
        if shutil.which('systemctl'):
            for unit in dict.fromkeys((service, package)):
                result = subprocess.run(['systemctl', 'is-active', '--quiet', unit], timeout=10)
                if result.returncode == 0:
                    running = True
                    break
        services.append({'service': service, 'version': version, 'version_source': 'package',
                         'running': running, 'manager': 'package'})
    return services


def output_directory(path, gid):
    """Pin each directory without following links from application-owned storage."""
    if not path.is_absolute() or '..' in path.parts or not path.name:
        raise ValueError('Inventory output must be an absolute path without parent components')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open('/', flags)
    try:
        for component in path.parent.parts[1:]:
            created = False
            try:
                child = os.open(component, flags, dir_fd=directory)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o750, dir_fd=directory)
                    created = True
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=directory)
            os.close(directory)
            directory = child
            if created:
                os.fchmod(directory, 0o750)
                if gid is not None:
                    os.fchown(directory, -1, gid)
        return directory
    except BaseException:
        os.close(directory)
        raise


def publish(path, services, gid=None):
    if len(services) > 256:
        raise ValueError('Inventory exceeds the supported 256 service records')
    path = Path(path)
    payload = {'schema': 1, 'complete': True,
               'observed_at': datetime.now(timezone.utc).isoformat(), 'services': services}
    directory = output_directory(path, gid)
    temporary = '.deployment-inventory-' + secrets.token_hex(12)
    created = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        created = True
        with os.fdopen(descriptor, 'w') as stream:
            os.fchmod(stream.fileno(), 0o640)
            if gid is not None:
                os.fchown(stream.fileno(), -1, gid)
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            if created:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
        finally:
            os.close(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('docker', 'podman'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gid', type=int, help='Group allowed to read the inventory (application GID)')
    parser.add_argument('--packages', action='store_true', help='Also inspect packages on this host')
    args = parser.parse_args()
    # On any engine failure keep the last snapshot, which expires in the UI.
    services = collect_containers(args.engine)
    if args.packages:
        services.extend(collect_packages())
    publish(args.output, services, args.gid)
    print(f'Published {len(services)} service records to {args.output}')


if __name__ == '__main__':
    main()
