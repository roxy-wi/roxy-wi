import select

import paramiko


class SshConnection:
    def __init__(self, server_ip: str, ssh_settings: dict):
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.server_ip = server_ip
        self.ssh_port = ssh_settings['port']
        self.ssh_user_name = ssh_settings['user']
        self.ssh_user_password = ssh_settings['password']
        self.ssh_enable = ssh_settings['enabled']
        self.ssh_key_name = ssh_settings['key']
        self.ssh_passphrase = ssh_settings['passphrase']

    # noinspection PyExceptClausesOrder
    def __enter__(self):
        kwargs = {
            'hostname': self.server_ip,
            'port': self.ssh_port,
            'username': self.ssh_user_name,
            'timeout': 11,
            'banner_timeout': 200,
            'look_for_keys': False
        }
        if self.ssh_enable == 1:
            kwargs.setdefault('key_filename', self.ssh_key_name)
            if self.ssh_passphrase:
                kwargs.setdefault('passphrase', self.ssh_passphrase)
        else:
            kwargs.setdefault('password', self.ssh_user_password)
        try:
            self.ssh.connect(**kwargs)
        except paramiko.AuthenticationException:
            raise paramiko.SSHException(f'{self.server_ip} Authentication failed, please verify your credentials')
        except paramiko.SSHException as sshException:
            raise paramiko.SSHException(f'{self.server_ip} Unable to establish SSH connection: {sshException}')
        except paramiko.PasswordRequiredException as e:
            raise paramiko.SSHException(f'{self.server_ip} {e}')
        except paramiko.BadHostKeyException as badHostKeyException:
            raise paramiko.SSHException(f'{self.server_ip} Unable to verify server\'s host key: {badHostKeyException}')
        except Exception as e:
            if e == "No such file or directory":
                raise paramiko.SSHException(f'{self.server_ip} {e}. Check SSH key')
            elif e == "Invalid argument":
                raise paramiko.SSHException(f'{self.server_ip} Check the IP of the server')
            else:
                raise paramiko.SSHException(f'{self.server_ip} {e}')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ssh.close()

    def run_command(self, command, **kwargs):
        if kwargs.get('timeout'):
            timeout = kwargs.get('timeout')
        else:
            timeout = 5
        try:
            stdin, stdout, stderr = self.ssh.exec_command(command, get_pty=True, timeout=timeout)
        except Exception as e:
            raise paramiko.SSHException(str(e))

        return stdin, stdout, stderr

    def get_sftp(self, config_path, cfg):
        try:
            sftp = self.ssh.open_sftp()
        except Exception as e:
            raise paramiko.SSHException(str(e))

        try:
            sftp.get(config_path, cfg)
        except Exception as e:
            sftp.close()
            raise paramiko.SSHException(str(e))

        try:
            sftp.close()
        except Exception as e:
            raise paramiko.SSHException(str(e))

    def put_sftp(self, file, full_path):
        try:
            sftp = self.ssh.open_sftp()
        except Exception as e:
            raise paramiko.SSHException(str(e))

        try:
            sftp.put(file, full_path)
        except Exception as e:
            raise paramiko.SSHException(str(e))

        try:
            sftp.close()
        except Exception as e:
            raise paramiko.SSHException(str(e))

    def generate(self, command):
        with self as ssh_something:
            stdin, stdout, stderr = ssh_something.ssh.exec_command(command)
            channel = stdout.channel

            # we do not need stdin.
            stdin.close()
            # indicate that we're not going to write to that channel anymore
            channel.shutdown_write()

            # read stdout/stderr in order to prevent read block hangs
            yield stdout.channel.recv(len(stdout.channel.in_buffer))

            # chunked read to prevent stalls
            while not channel.closed or channel.recv_ready() or channel.recv_stderr_ready():
                # stop if channel was closed prematurely,
                # and there is no data in the buffers.
                got_chunk = False
                readq, _, _ = select.select([stdout.channel], [], [], 1)
                for c in readq:
                    if c.recv_ready():
                        yield stdout.channel.recv(len(c.in_buffer))
                        got_chunk = True
                    if c.recv_stderr_ready():
                        # make sure to read stderr to prevent stall
                        yield stderr.channel.recv_stderr(
                            len(c.in_stderr_buffer))
                        got_chunk = True

                """
                1) make sure that there are at least 2 cycles with no data
                   in the input buffers in order to not exit too early
                   (i.e. cat on a >200k file).
                2) if no data arrived in the last loop,
                   check if we already received the exit code
                3) check if input buffers are empty
                4) exit the loop
                """
                if (not got_chunk and
                   stdout.channel.exit_status_ready() and not
                   stderr.channel.recv_stderr_ready() and not
                   stdout.channel.recv_ready()):
                    # indicate that we're not going
                    # to read from this channel anymore
                    stdout.channel.shutdown_read()
                    # close the channel
                    stdout.channel.close()
                    # exit as remote side is finished
                    # and our bufferes are empty
                    break
            # close all the pseudofiles
            stdout.close()
            stderr.close()
            self.ssh.close()
