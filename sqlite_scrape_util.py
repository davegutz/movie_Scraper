#  Utilities for GUI_sqlite_scrape.py
#  2024-Apr-13  Dave Gutz   Create
# Copyright (C) 2024 Dave Gutz
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation;
# version 2.1 of the License.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# See http://www.fsf.org/licensing/licenses/lgpl.txt for full license text.
import os
import sys
import subprocess
from Colors import Colors


# Run shell command showing stdout progress (special logic for Windows)
# Hope it works on Mac and Linux
def run_shell_cmd(cmd, silent=False, save_stdout=False, colorize=False):
    stdout_line = None
    if save_stdout:
        stdout_line = []
    if colorize:
        print(Colors.bg.brightblack, Colors.fg.wheat)
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            bufsize=1, universal_newlines=True)
    # Poll process for new output until finished
    while True:
        try:
            nextline = proc.stdout.readline()
        except AttributeError:
            nextline = ''
        if nextline == '' and proc.poll() is not None:
            break
        if save_stdout:
            stdout_line.append(nextline)
        if not silent:
            sys.stdout.write(nextline)
            sys.stdout.flush()
    if colorize:
        print(Colors.reset)
    if save_stdout and not silent:
        print('stdout', stdout_line)
    output = proc.communicate()[0]
    exit_code = proc.returncode
    if exit_code == 0:
        if save_stdout:
            return stdout_line
        else:
            return exit_code
    else:
        return -1


