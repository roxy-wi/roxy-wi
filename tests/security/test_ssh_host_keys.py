import paramiko

from app.modules.server.ssh_connection import SshConnection


def test_unknown_ssh_host_keys_are_accepted_automatically():
    connection = SshConnection(
        '192.0.2.10',
        {
            'port': 22,
            'user': 'test-user',
            'password': 'test-password',
            'enabled': 0,
            'key': None,
            'passphrase': None,
        },
    )

    assert isinstance(connection.ssh._policy, paramiko.AutoAddPolicy)
