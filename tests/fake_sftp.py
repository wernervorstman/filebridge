#!/usr/bin/env python3
"""A small SFTP server for tests and the manual pictures: serves one folder, accepts one user.

    python tests/fake_sftp.py ROOT [PORT]     # user "demo", password "demo"

Built on paramiko (already a FileBridge dependency); only for local testing, never expose it.
"""
import logging
import os
import socket
import sys
import threading

import paramiko
from paramiko import SFTP_FAILURE, SFTP_NO_SUCH_FILE, SFTP_OK, SFTPAttributes, SFTPHandle, SFTPServer
from paramiko.sftp_server import SFTPServerInterface

USER, PASSWORD = 'demo', 'demo'
logging.getLogger('paramiko').setLevel(logging.CRITICAL)  # a client that only knocks is not an error


class _Server(paramiko.ServerInterface):
    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL if (username, password) == (USER, PASSWORD) else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return 'password'

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_subsystem_request(self, channel, name):
        return super().check_channel_subsystem_request(channel, name)


class _Handle(SFTPHandle):
    def stat(self):
        try:
            return SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    def chattr(self, attr):
        return SFTP_OK


class _SFTP(SFTPServerInterface):
    ROOT = '/'

    def _real(self, path):
        return os.path.join(self.ROOT, self.canonicalize(path).lstrip('/'))

    def canonicalize(self, path):
        return os.path.normpath('/' + (path or '').lstrip('/')).replace('\\', '/')

    def list_folder(self, path):
        real = self._real(path)
        try:
            out = []
            for name in os.listdir(real):
                attr = SFTPAttributes.from_stat(os.lstat(os.path.join(real, name)))
                attr.filename = name
                out.append(attr)
            return out
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    def stat(self, path):
        try:
            return SFTPAttributes.from_stat(os.stat(self._real(path)))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    lstat = stat

    def open(self, path, flags, attr):
        real = self._real(path)
        try:
            fd = os.open(real, flags | getattr(os, 'O_BINARY', 0), 0o644)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        if flags & os.O_WRONLY:
            mode = 'ab' if flags & os.O_APPEND else 'wb'
        elif flags & os.O_RDWR:
            mode = 'a+b' if flags & os.O_APPEND else 'r+b'
        else:
            mode = 'rb'
        try:
            f = os.fdopen(fd, mode)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        h = _Handle(flags)
        h.filename, h.readfile, h.writefile = real, f, f
        return h

    def remove(self, path):
        try:
            os.remove(self._real(path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rename(self, old, new):
        try:
            os.rename(self._real(old), self._real(new))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    posix_rename = rename

    def mkdir(self, path, attr):
        try:
            os.mkdir(self._real(path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rmdir(self, path):
        try:
            os.rmdir(self._real(path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def chattr(self, path, attr):
        real = self._real(path)
        try:
            if attr.st_mode is not None:
                os.chmod(real, attr.st_mode & 0o7777)
            if attr.st_mtime is not None:
                os.utime(real, (attr.st_atime or attr.st_mtime, attr.st_mtime))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def readlink(self, path):
        return SFTP_NO_SUCH_FILE

    def symlink(self, target, path):
        return SFTP_FAILURE


def serve(root, port=2299):
    """Start the server in the background; returns the listening socket."""
    _SFTP.ROOT = os.path.abspath(root)
    key = paramiko.Ed25519Key.from_private_key_file(_host_key())
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', port))
    sock.listen(10)

    def handle(conn):
        t = paramiko.Transport(conn)
        t.add_server_key(key)
        t.set_subsystem_handler('sftp', SFTPServer, _SFTP)
        try:
            t.start_server(server=_Server())
        except (paramiko.SSHException, EOFError, OSError):
            pass  # a client that only knocked (e.g. Test connection reading the greeting)

    def loop():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
    return sock


def _host_key():
    """A host key for the test server, made once (paramiko can read OpenSSH Ed25519 keys)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.fake_sftp_host_key')
    if not os.path.exists(path):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        pem = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                                         serialization.NoEncryption())
        with open(path, 'wb') as f:
            f.write(pem)
        os.chmod(path, 0o600)
    return path


if __name__ == '__main__':
    serve(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2299)
    print(f'SFTP on 127.0.0.1:{sys.argv[2] if len(sys.argv) > 2 else 2299} – user {USER}, password {PASSWORD}', flush=True)
    threading.Event().wait()
