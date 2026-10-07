#!/usr/bin/env python3
"""
ptyrun.py - run a command on a real pseudo-terminal and type answers into it.

Interactive prompts (`read -p "..."`) only appear, and only echo what was
typed, when the program is attached to a tty.  This drives the program through
pty.fork(), waits for it to go quiet, then types the next answer.  The captured
transcript therefore contains the prompts AND the typed replies exactly as they
appeared on screen - nothing is edited in afterwards.

Usage:
    python3 ptyrun.py --log logs/02_script.log --cwd '~/x' \
            --input 'Prince Kumar' --input '24bcs10658' -- bash script.sh
"""
import argparse
import errno
import shlex
import os
import pty
import select
import sys
import time


def run(cmd, inputs, idle=0.45, timeout=120):
    pid, fd = pty.fork()
    if pid == 0:                                     # child
        os.environ["TERM"] = "xterm-256color"
        os.environ["COLUMNS"] = "140"
        try:
            os.execvp(cmd[0], cmd)
        finally:
            os._exit(127)

    chunks = []
    pending = list(inputs)
    last_data = time.time()
    start = time.time()

    while True:
        if time.time() - start > timeout:
            break
        try:
            r, _, _ = select.select([fd], [], [], 0.1)
        except (OSError, select.error):
            break
        if r:
            try:
                data = os.read(fd, 4096)
            except OSError as e:
                if e.errno == errno.EIO:
                    break
                raise
            if not data:
                break
            chunks.append(data)
            last_data = time.time()
        else:
            # the program has stopped printing - it is waiting for input
            if pending and time.time() - last_data > idle:
                answer = pending.pop(0)
                os.write(fd, answer.encode() + b"\n")
                last_data = time.time()
            elif not pending and time.time() - last_data > 3.0:
                break

    os.close(fd)
    _, status = os.waitpid(pid, 0)
    return b"".join(chunks).decode("utf-8", "replace"), os.waitstatus_to_exitcode(status)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--cwd", default=None)
    ap.add_argument("--input", action="append", default=[])
    ap.add_argument("--append", action="store_true")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        ap.error("no command given")

    out, rc = run(cmd, a.input)

    mode = "a" if a.append else "w"
    with open(a.log, mode, encoding="utf-8") as fh:
        if a.cwd:
            fh.write(f"#CWD {a.cwd}\n")
        fh.write("$ " + shlex.join(cmd) + "\n")
        # the pty gives us CRLF line endings; a terminal shows them as LF
        fh.write(out.replace("\r\n", "\n"))
        if not out.endswith("\n"):
            fh.write("\n")
        fh.write("\n")

    print(f"exit={rc}  captured {len(out)} bytes -> {a.log}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
