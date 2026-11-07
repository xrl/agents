import argparse
import fcntl
import json
import os
import pty
import re
import select
import shutil
import struct
import sys
import termios
import time

HELP = '''Drive `claude mcp login <server> --no-browser` under a pseudo-terminal. The CLI refuses without a
TTY ("stdin isn't a terminal"), and `script -q` with a fifo stdin dies silently. Run this with
run_in_background: it keeps the CLI alive, logs its output, and writes the authorize URL to --url-file
(0600) as soon as it appears. Open that URL in the persona's playwright session and click Authorize;
the CLI's localhost callback completes the login with nothing pasted. If the callback cannot be reached,
write the final redirect URL to --reply-file and it is typed into the CLI. Prints one JSON line at the end
and exits with the CLI's status.'''

ANSI = re.compile(rb'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07')
URL = re.compile(rb'https://[^\s\x1b"\'<>]*authorize[^\s\x1b"\'<>]*')


def main():
    p = argparse.ArgumentParser(description=HELP)
    p.add_argument('--server', required=True, help='MCP server name given to `claude mcp add`, e.g. reveal-pr-43404')
    p.add_argument('--config-dir', required=True, help='the scratch CLAUDE_CONFIG_DIR')
    p.add_argument('--cwd', required=True, help='project dir the --scope local server was added from')
    p.add_argument('--log', required=True, help='append the CLI output here')
    p.add_argument('--url-file', required=True, help='write the authorize URL here')
    p.add_argument('--reply-file', help='if this file appears, its contents are typed into the CLI')
    p.add_argument('--timeout', type=int, default=900)
    p.add_argument('--claude', default=shutil.which('claude') or 'claude')
    a = p.parse_args()

    env = dict(os.environ, CLAUDE_CONFIG_DIR=a.config_dir)
    started = time.time()
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(a.cwd)
        os.execve(a.claude, [a.claude, 'mcp', 'login', a.server, '--no-browser'], env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 4000, 0, 0))

    buf = b''
    url_seen = False
    sent = False
    status = None
    with open(a.log, 'ab', buffering=0) as log:
        while time.time() - started < a.timeout:
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    data = b''
                if not data:
                    _, status = os.waitpid(pid, 0)
                    break
                log.write(data)
                buf = (buf + ANSI.sub(b'', data))[-65536:]
                if not url_seen:
                    m = URL.search(buf)
                    if m:
                        fdu = os.open(a.url_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                        os.write(fdu, m.group(0) + b'\n')
                        os.close(fdu)
                        url_seen = True
            if a.reply_file and not sent and os.path.exists(a.reply_file) and os.path.getsize(a.reply_file) > 0:
                with open(a.reply_file, 'rb') as f:
                    os.write(fd, f.read().strip() + b'\r')
                sent = True
            done, st = os.waitpid(pid, os.WNOHANG)
            if done:
                status = st
                break
        else:
            os.kill(pid, 15)
            _, status = os.waitpid(pid, 0)
        log.write(f'\n[mcp_login_pty exit {status}]\n'.encode())

    code = os.waitstatus_to_exitcode(status) if status is not None else 1
    print(json.dumps({'exit': code, 'url_seen': url_seen, 'reply_sent': sent, 'seconds': round(time.time() - started, 1)}))
    sys.exit(code if code >= 0 else 1)


if __name__ == '__main__':
    main()
