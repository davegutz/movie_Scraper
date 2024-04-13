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

# Can create Windows executable as follows:
#  use pycharm settings to install pyinstaller
#  use pycharm terminal app to run:
#    pyinstaller .\GUI_sqlite_scrape.py --i popcorn.ico -y
#    cp blank.png .\dist\GUI_sqlite_scrape\.; cp popcorn.png .\dist\GUI_sqlite_scrape\.
#  double-click, browse to database, and pin to taskbar
#
#  Linux:
#    pyinstaller ./GUI_sqlite_scrape.py --hidden-import='PIL._tkinter_finder' --icon="popcorn.ico" -y
#    cp blank.png ./dist/GUI_sqlite_scrape/.; cp popcorn.png ./dist/GUI_sqlite_scrape/.
#  result found in dist folder

test_cmd_create = None
test_cmd_copy = None
popcorn_path = os.path.join(os.getcwd(), 'popcorn.png')
popcorn_dest_path = os.path.join(os.getcwd(), 'dist', 'GUI_sqlite_scrape', 'popcorn.png')
blank_path = os.path.join(os.getcwd(), 'blank.png')
blank_dest_path = os.path.join(os.getcwd(), 'dist', 'GUI_sqlite_scrape', 'blank.png')

# Create executable
if sys.platform == 'linux':
    test_cmd_create = "./GUI_sqlite_scrape.py --hidden-import='PIL._tkinter_finder' --icon='popcorn.ico' -y"
elif sys.platform == 'Darwin':
    print(f"macOS not done yet")
else:
    test_cmd_create = 'pyinstaller .\\GUI_sqlite_scrape.py --i popcorn.ico -y'
result = run_shell_cmd(test_cmd_create, silent=False)
if result == -1:
    print(Colors.fg.red, 'failed', Colors.reset)
else:
    print(Colors.fg.green, 'success', Colors.reset)

# Provide dependencies
shutil.copyfile(popcorn_path, popcorn_dest_path)
shutil.copystat(popcorn_path, popcorn_dest_path)
shutil.copyfile(blank_path, blank_dest_path)
shutil.copystat(blank_path, blank_dest_path)

# Install as deeply as possible
test_cmd_install = None
if sys.platform == 'linux':

    # Install
    test_cmd_install = f'cat << EOF > /home/daveg/Desktop/GUI_sqlite_scrape.desktop\n'
    f'[Desktop Entry]\n'
    f'Name=GUI_sqlite_scrape\n'
    f'Exec=/home/daveg/Documents/GitHub/movie_Scraper/dist/GUI_sqlite_scrape/GUI_sqlite_scrape\n'
    f'Path=/home/daveg/Documents/GitHub/movie_Scraper/dist/GUI_sqlite_scrape\n'
    f'Icon=/home/daveg/Documents/GitHub/movie_Scraper/popcorn.ico\n'
    f'comment=app\n'
    f'Type=Application\n'
    f'Terminal=true\n'
    f'Encoding=UTF-8\n'
    f'Categories=Utility;\n'
    f'EOF'
    result = run_shell_cmd(test_cmd_install, silent=False)
    if result == -1:
        print(Colors.fg.red, 'failed', Colors.reset)
    else:
        print(Colors.fg.green, 'success', Colors.reset)

    #  Launch permission
    test_cmd_launch = 'gio set /home/daveg/Desktop/GUI_sqlite_scrape.desktop metadata::trusted true'
    result = run_shell_cmd(test_cmd_launch, silent=False)
    if result == -1:
        print(Colors.fg.red, 'failed', Colors.reset)
    else:
        print(Colors.fg.green, 'success', Colors.reset)
    test_cmd_perm = 'chmod a+x ~/Desktop/GUI_sqlite_scrape.desktop'
    result = run_shell_cmd(test_cmd_perm, silent=False)
    if result == -1:
        print(Colors.fg.red, 'failed', Colors.reset)
    else:
        print(Colors.fg.green, 'success', Colors.reset)

    # Move file
    test_cmd_move = 'sudo mv /home/daveg/Desktop/GUI_sqlite_scrape.desktop /usr/share/applications/'
    result = run_shell_cmd(test_cmd_move, silent=False)
    if result == -1:
        print(Colors.fg.red, 'failed', Colors.reset)
    else:
        print(Colors.fg.green, 'success', Colors.reset)

# Instructions
if sys.platform == 'linux':
    print(f"open applications, find GUI... and add to favorites")
elif sys.platform == 'Darwin':
    print(f"macOS not done yet")
else:
    print(Colors.fg.green,
          f"double-click on  'GUI_sqlite_scrape.exe - Shortcut', browse to DB folder, pin to taskbar",
          Colors.reset)
