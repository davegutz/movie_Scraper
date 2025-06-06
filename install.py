#  install.py
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
import sys
from sqlite_scrape_util import run_shell_cmd
from Colors import Colors
import os
import shutil

debug = False

test_cmd_create = None
test_cmd_copy = None
popcorn_path = os.path.join(os.getcwd(), 'popcorn.png')
popcorn_dest_path = os.path.join(os.getcwd(), 'dist', 'GUI_sqlite_scrape', 'popcorn.png')
blank_path = os.path.join(os.getcwd(), 'blank.png')
blank_dest_path = os.path.join(os.getcwd(), 'dist', 'GUI_sqlite_scrape', 'blank.png')

# Create executable
if sys.platform == 'win32':

    # Check executable is local
    if sys.executable.__contains__("venv" + os.path.sep + "bin" + os.path.sep + "python"):
        pass
    else:
        print(Colors.fg.red, 'failed:  need to use local venv interpreter', Colors.reset)
        exit(1)

    test_cmd_create = 'pyinstaller .\\GUI_sqlite_scrape.py --i popcorn.ico -y'
    result = run_shell_cmd(test_cmd_create, silent=False)
    if result == -1:
        print(Colors.fg.red, 'failed', Colors.reset)
        exit(1)
    else:
        print(Colors.fg.green, 'success', Colors.reset)

    # Provide dependencies
    shutil.copyfile(popcorn_path, popcorn_dest_path)
    shutil.copystat(popcorn_path, popcorn_dest_path)
    shutil.copyfile(blank_path, blank_dest_path)
    shutil.copystat(blank_path, blank_dest_path)
    print(Colors.fg.green, "copied files", Colors.reset)

# Install as deeply as possible
test_cmd_install = None
if sys.platform == 'linux':
    try:
        login = os.getlogin()
    except OSError:
        login = os.environ['LOGNAME']
    desktop_entry = f"""[Desktop Entry]
Name=GUI_sqlite_scrape
Exec=/home/{login}/Documents/GitHub/movie_Scraper/.venv/bin/python3 /home/{login}/Documents/GitHub/movie_Scraper/GUI_sqlite_scrape.py
Path=/home/{login}/Documents/GitHub/movie_Scraper
Icon=/home/{login}/Documents/GitHub/movie_Scraper/popcorn.ico
comment=app
Type=Application
Terminal=true
Encoding=UTF-8
Categories=Utility
"""
    with open("/home/daveg/Desktop/GUI_sqlite_scrape.desktop", "w") as text_file:
        result = text_file.write("%s" % desktop_entry)
    if result == -1:
        print(Colors.fg.red, 'failed', Colors.reset)
    else:
        print(Colors.fg.green, 'success', Colors.reset)

    # Check executable is local
    if sys.executable.__contains__("venv" + os.path.sep + "bin" + os.path.sep + "python"):
        pass
    else:
        print(Colors.fg.red, 'failed:  need to use local venv interpreter', Colors.reset)
        exit(1)

    #  Launch permission
    test_cmd_launch = 'gio set /home/daveg/Desktop/GUI_sqlite_scrape.desktop metadata::trusted true'
    result = run_shell_cmd(test_cmd_launch, silent=False)
    if result == -1:
        print(Colors.fg.red, 'gio set failed', Colors.reset)
    else:
        print(Colors.fg.green, 'gio set success', Colors.reset)
    test_cmd_perm = 'chmod a+x ~/Desktop/GUI_sqlite_scrape.desktop'
    result = run_shell_cmd(test_cmd_perm, silent=False)
    if result == -1:
        print(Colors.fg.red, 'failed', Colors.reset)
    else:
        print(Colors.fg.green, 'success', Colors.reset)

    # Execute permission
    test_cmd_perm = 'chmod a+x ~/Desktop/GUI_sqlite_scrape.desktop'
    result = run_shell_cmd(test_cmd_perm, silent=False)
    if result != 0:
        print(Colors.fg.red, f"'chmod ...' failed code {result}", Colors.reset)
    else:
        print(Colors.fg.green, 'chmod success', Colors.reset)
    # exit(1)
    # Move file
    try:
        if debug is False:
            result = shutil.move('/home/daveg/Desktop/GUI_sqlite_scrape.desktop',
                                 '/usr/share/applications/GUI_sqlite_scrape.desktop')
    except PermissionError:
        print(Colors.fg.red, f"Stop and establish sudo permissions\n"
              f"  or\n"
              f"sudo mv /home/daveg/Desktop/GUI_sqlite_scrape.desktop /usr/share/applications/.",
              Colors.reset)
        exit(1)
    if result != '/usr/share/applications/GUI_sqlite_scrape.desktop':
        print(Colors.fg.red, f"'mv ...' failed code {result}", Colors.reset)
    else:
        print(Colors.fg.green,
              'mv success.  Browse apps :: and make it favorites.  Open and set path to dataReduction',
              Colors.reset)
        print(Colors.fg.green,
              "you shouldn't have to remake shortcuts",
              Colors.reset)
elif sys.platform == 'darwin':
    print(Colors.fg.green,
          f"Make sure 'Python Launcher' (Python Script Preferences) option for 'Allow override with #! in script' is checked.\n"
          f"in Finder double-click on 'popcorn.png'.  Edit-copy the image\n"
          f"in Finder ctrl-click on 'GUI_sqlite_scrape.py'\n"
          f"   - 'Get Info', click on 2nd icon, paste.   Drag item to taskbar.",
          Colors.reset)
else:
    print(Colors.fg.green,
          f"browse to executable in 'dist/GUI_sqlite_scrape' and double-click.  Create shortcut first time and move Desktop\n"
          f"double-click on  'GUI_sqlite_scrape.exe - Shortcut', browse to DB folder, pin to taskbar\n"
          f"in shortcut properties, make sure 'Start in:' is this folder where this script resides\n"
          f"you shouldn't have to remake shortcuts",
          Colors.reset)
