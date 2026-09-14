#  Utilities for GitHub
#  2025-May-23  Dave Gutz   Create
# Copyright (C) 2025 Dave Gutz
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
import re
import sys
import time
import requests
import datetime
import subprocess

try:
    from Colors import Colors
except ImportError:
    class Colors:
        reset = ''
        bold = ''
        class fg:
            green = ''
            yellow = ''
            red = ''
            orange = ''
            cyan = ''
            blue = ''


def get_file_timestamps(file_path):
    """
    Retrieves the creation, modification, and access timestamps of a file.

    Args:
        file_path: The path to the file.

    Returns:
        A dictionary containing the creation, modification, and access times
        in human-readable format, or None if the file does not exist.
    """
    if not os.path.exists(file_path):
        return None

    creation_time = os.path.getctime(file_path)
    modification_time = os.path.getmtime(file_path)
    access_time = os.path.getatime(file_path)

    return {
        "creation_time": time.ctime(creation_time),
        "modification_time": time.ctime(modification_time),
        "access_time": time.ctime(access_time)
    }


def get_gmt_offset_seconds():
    """
    Calculates the offset in seconds between the local time zone and GMT.
    """
    if time.daylight == 0:
        return time.timezone
    else:
        return time.altzone


def get_file_timestamp_gmt(file_path):
    """
    Returns the file's last modification timestamp in seconds since the epoch (GMT/UTC).
    """
    return os.path.getmtime(file_path)


def get_file_timestamp_from_github(repo_owner, repo_name, file_path, github_token=None, timeout=5):
    """
    Retrieves the last modified timestamp of a file in a GitHub repository.

    Args:
        repo_owner (str): The owner of the repository.
        repo_name (str): The name of the repository.
        file_path (str): The path to the file within the repository.
        github_token (str, optional): A personal access token for the GitHub API. Defaults to None.
        timeout (int): Timeout in seconds for the network request. Defaults to 5.

    Returns:
        str: The last modified timestamp of the file in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ), or None if an error occurs.
    """
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
    params = {'path': file_path, 'per_page': 1}
    headers = {}
    if github_token:
        headers['Authorization'] = f"token {github_token}"

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        if response.status_code == 200 and response.headers.get('Last-Modified'):
            return response.headers['Last-Modified']
        else:
            return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None


def get_github_file_timestamp(repo_owner, repo_name, file_path, github_token=None, timeout=5):
    """
    Retrieves the timestamp of a file from a GitHub repository in Unix time.

    Args:
        repo_owner (str): The owner of the repository.
        repo_name (str): The name of the repository.
        file_path (str): The path to the file within the repository.
        github_token (str, optional): A GitHub personal access token. Defaults to None.
        timeout (int): Timeout in seconds for the network request. Defaults to 5.

    Returns:
        int: The Unix timestamp of the file's last modification, or None if an error occurs.
    """
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits?path={file_path}&per_page=1"
    headers = {}
    if github_token:
        headers['Authorization'] = f"token {github_token}"

    try:
        response = requests.get(api_url, headers=headers, timeout=timeout)

        if response.status_code == 200:
            commits = response.json()
            if commits:
                date_str = commits[0]['commit']['author']['date']
                datetime_obj = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                timestamp = int(datetime_obj.timestamp())
                return timestamp
            else:
                # Try alternate case if file_path case differed
                alt_path = 'IMDB_Films.db' if file_path == 'IMDB_films.db' else 'IMDB_films.db'
                alt_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits?path={alt_path}&per_page=1"
                alt_resp = requests.get(alt_url, headers=headers, timeout=timeout)
                if alt_resp.status_code == 200:
                    commits = alt_resp.json()
                    if commits:
                        date_str = commits[0]['commit']['author']['date']
                        datetime_obj = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                        return int(datetime_obj.timestamp())

                print(f"No commits found for file '{file_path}'.")
                return None
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def check_newer_git_database(local_db_path=None, repo_owner="davegutz", repo_name="myComputer", file_path="IMDB_Films.db", github_token=None, timeout=5, print_status=True):
    """
    Checks if a newer version of the database exists in the git repository.
    Uses git CLI with fetch if local directory is a git repository, and falls back to GitHub REST API.

    Args:
        local_db_path (str, optional): Path to local database file. Defaults to None.
        repo_owner (str): GitHub repository owner (default: 'davegutz').
        repo_name (str): GitHub repository name (default: 'myComputer').
        file_path (str): Database file name (default: 'IMDB_Films.db').
        github_token (str, optional): GitHub personal access token (or env GITHUB_TOKEN).
        timeout (int): Timeout in seconds for git and network requests (default: 5).
        print_status (bool): If True, print status updates to the screen (default: True).

    Returns:
        tuple (bool, dict):
            bool: True if remote git has a newer version than local, False otherwise.
            dict: Info dictionary containing commit information, dates, and check details.
    """
    if local_db_path:
        local_db_path = os.path.abspath(local_db_path)
        db_folder = os.path.dirname(local_db_path)
        db_filename = os.path.basename(local_db_path)
    else:
        db_folder = os.path.abspath('.')
        db_filename = file_path
        local_db_path = os.path.join(db_folder, db_filename)

    # Handle case-insensitivity on local filesystem if file not found
    if not os.path.exists(local_db_path) and os.path.isdir(db_folder):
        target = db_filename.lower()
        for f in os.listdir(db_folder):
            if f.lower() == target:
                local_db_path = os.path.join(db_folder, f)
                db_filename = f
                break

    if print_status:
        print(f"[Git Check] Evaluating database file: {local_db_path}")

    if not os.path.exists(local_db_path):
        err = f"Local file does not exist: {local_db_path}"
        if print_status:
            print(Colors.fg.red, f"[Git Check] {err}", Colors.reset)
        return False, {'error': err}

    # 1. Check if db_folder is inside a git repository
    is_git_repo = False
    try:
        r = subprocess.run(
            ['git', '-C', db_folder, 'rev-parse', '--is-inside-work-tree'],
            capture_output=True, text=True, timeout=timeout
        )
        is_git_repo = (r.returncode == 0 and r.stdout.strip() == 'true')
    except Exception:
        pass

    # Extract repository owner/name from origin remote if available
    if is_git_repo:
        try:
            r = subprocess.run(
                ['git', '-C', db_folder, 'remote', 'get-url', 'origin'],
                capture_output=True, text=True, timeout=timeout
            )
            if r.returncode == 0 and r.stdout.strip():
                url = r.stdout.strip()
                match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', url)
                if match:
                    repo_owner = match.group(1)
                    repo_name = match.group(2)
        except Exception:
            pass

    # 2. Try git CLI fetch & rev-list if local folder is a git repo
    git_fetch_success = False
    if is_git_repo:
        if print_status:
            print(f"[Git Check] Local git repository detected in '{db_folder}'.")
            print(f"[Git Check] Fetching updates from remote 'origin' (timeout {timeout}s)...")
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        try:
            r = subprocess.run(
                ['git', '-C', db_folder, 'fetch', 'origin'],
                capture_output=True, text=True, timeout=timeout, env=env
            )
            if r.returncode == 0:
                git_fetch_success = True
                if print_status:
                    print(f"[Git Check] Git fetch completed successfully.")
            else:
                if print_status:
                    print(f"[Git Check] Git fetch returned code {r.returncode}. Falling back to cached/GitHub API.")
        except subprocess.TimeoutExpired:
            if print_status:
                print(f"[Git Check] Git fetch timed out after {timeout}s.")
        except Exception as e:
            if print_status:
                print(f"[Git Check] Git fetch exception: {e}")

        if git_fetch_success:
            upstream = None
            for ref in ['@{u}', 'origin/main', 'origin/master']:
                r = subprocess.run(
                    ['git', '-C', db_folder, 'rev-parse', '--verify', ref],
                    capture_output=True, text=True, timeout=timeout
                )
                if r.returncode == 0:
                    upstream = ref
                    break

            if upstream:
                if print_status:
                    print(f"[Git Check] Comparing HEAD against upstream '{upstream}' for '{db_filename}'...")
                # Check if upstream branch has commits ahead of HEAD for db_filename
                r = subprocess.run(
                    ['git', '-C', db_folder, 'rev-list', '--count', f'HEAD..{upstream}', '--', db_filename],
                    capture_output=True, text=True, timeout=timeout
                )
                if r.returncode == 0:
                    count = int(r.stdout.strip())
                    if count > 0:
                        r_log = subprocess.run(
                            ['git', '-C', db_folder, 'log', '-1', '--format=%H%x00%ci%x00%s', upstream, '--', db_filename],
                            capture_output=True, text=True, timeout=timeout
                        )
                        rem_sha, rem_date, rem_msg = r_log.stdout.strip().split('\x00') if r_log.returncode == 0 and r_log.stdout.strip() else ('', '', '')

                        l_log = subprocess.run(
                            ['git', '-C', db_folder, 'log', '-1', '--format=%H%x00%ci%x00%s', 'HEAD', '--', db_filename],
                            capture_output=True, text=True, timeout=timeout
                        )
                        loc_sha, loc_date, loc_msg = l_log.stdout.strip().split('\x00') if l_log.returncode == 0 and l_log.stdout.strip() else ('', '', '')

                        if print_status:
                            print(Colors.fg.yellow, f"[Git Check] Remote '{upstream}' is ahead by {count} commit(s) for '{db_filename}'!", Colors.reset)
                            print(f"[Git Check]   Remote commit: {rem_sha[:7]} ({rem_date}) - {rem_msg}")
                            print(f"[Git Check]   Local commit:  {loc_sha[:7]} ({loc_date})")

                        return True, {
                            'method': 'git',
                            'remote_sha': rem_sha[:7],
                            'remote_date': rem_date,
                            'remote_msg': rem_msg,
                            'local_sha': loc_sha[:7] if loc_sha else 'None',
                            'local_date': loc_date if loc_date else 'None',
                            'behind_count': count,
                        }
                    else:
                        if print_status:
                            print(Colors.fg.green, f"[Git Check] Local repository is up to date with '{upstream}' for '{db_filename}'.", Colors.reset)
                        return False, {'method': 'git', 'status': 'up-to-date'}

    # 3. Fallback to GitHub REST API (if git fetch failed, upstream not found, or not a git repo)
    if print_status:
        print(f"[Git Check] Querying GitHub REST API for '{repo_owner}/{repo_name}' path '{db_filename}'...")
    try:
        if not github_token:
            github_token = os.environ.get("GITHUB_TOKEN")
        headers = {}
        if github_token:
            headers['Authorization'] = f"token {github_token}"

        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
        params = {'path': db_filename, 'per_page': 1}
        resp = requests.get(api_url, headers=headers, params=params, timeout=timeout)

        commits = []
        if resp.status_code == 200:
            commits = resp.json()

        # If no commits found with given filename case, try alternate case
        if not commits and resp.status_code == 200:
            alt_filename = 'IMDB_Films.db' if db_filename == 'IMDB_films.db' else 'IMDB_films.db'
            params = {'path': alt_filename, 'per_page': 1}
            alt_resp = requests.get(api_url, headers=headers, params=params, timeout=timeout)
            if alt_resp.status_code == 200:
                commits = alt_resp.json()

        if commits:
            rem_sha = commits[0]['sha']
            rem_date = commits[0]['commit']['author']['date']
            rem_msg = commits[0]['commit']['message']
            rem_dt = datetime.datetime.strptime(rem_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
            rem_ts = rem_dt.timestamp()

            if is_git_repo:
                loc_log = subprocess.run(
                    ['git', '-C', db_folder, 'log', '-1', '--format=%H%x00%ct%x00%ci', '--', db_filename],
                    capture_output=True, text=True, timeout=timeout
                )
                if loc_log.returncode == 0 and loc_log.stdout.strip():
                    parts = loc_log.stdout.strip().split('\x00')
                    loc_sha = parts[0]
                    loc_ts = parts[1]
                    loc_date = parts[2] if len(parts) > 2 else ''

                    if loc_sha == rem_sha:
                        if print_status:
                            print(Colors.fg.green, f"[Git Check] Local commit ({loc_sha[:7]}) matches GitHub commit. Up to date.", Colors.reset)
                        return False, {'method': 'github_api', 'status': 'up-to-date'}

                    if rem_ts > float(loc_ts):
                        if print_status:
                            print(Colors.fg.yellow, f"[Git Check] GitHub has newer commit ({rem_sha[:7]} at {rem_date}) than local ({loc_sha[:7]}).", Colors.reset)
                        return True, {
                            'method': 'github_api',
                            'remote_sha': rem_sha[:7],
                            'remote_date': rem_date,
                            'remote_msg': rem_msg,
                            'local_sha': loc_sha[:7],
                            'local_date': loc_date,
                        }
                    else:
                        if print_status:
                            print(Colors.fg.green, f"[Git Check] Local commit ({loc_sha[:7]}) is equal or newer than GitHub ({rem_sha[:7]}).", Colors.reset)
                        return False, {'method': 'github_api', 'status': 'up-to-date'}

            # Non-git folder: compare with local file mtime
            local_mtime = os.path.getmtime(local_db_path)
            if rem_ts > local_mtime + 60:
                loc_time_str = datetime.datetime.fromtimestamp(local_mtime, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                if print_status:
                    print(Colors.fg.yellow, f"[Git Check] GitHub commit ({rem_date}) is newer than local file ({loc_time_str}).", Colors.reset)
                return True, {
                    'method': 'github_api',
                    'remote_sha': rem_sha[:7],
                    'remote_date': rem_date,
                    'remote_msg': rem_msg,
                    'local_mtime': loc_time_str,
                }
            else:
                if print_status:
                    print(Colors.fg.green, f"[Git Check] Local file modification time is up to date with GitHub commit.", Colors.reset)
                return False, {'method': 'github_api', 'status': 'up-to-date'}

        elif resp.status_code == 403:
            msg = "GitHub API rate limit exceeded"
            if print_status:
                print(Colors.fg.orange, f"[Git Check] {msg}", Colors.reset)
            return False, {'method': 'github_api', 'status': 'rate-limited', 'error': msg}
        elif resp.status_code != 200:
            msg = f"HTTP {resp.status_code} from GitHub API"
            if print_status:
                print(Colors.fg.orange, f"[Git Check] {msg}", Colors.reset)
            return False, {'method': 'github_api', 'status': msg}

    except Exception as e:
        if print_status:
            print(Colors.fg.orange, f"[Git Check] Error querying GitHub API: {e}", Colors.reset)
        return False, {'status': 'error', 'error': str(e)}

    return False, {'status': 'up-to-date'}


def main():
    # Example usage
    if sys.platform == 'linux':
        local_path = "/home/daveg/Documents/GitHub/myComputer/IMDB_Films.db"
    elif sys.platform == 'darwin':
        local_path = "/Users/daveg/Documents/GitHub/myComputer/IMDB_Films.db"
    else:
        local_path = "C:/Users/daveg/Documents/myComputer/IMDB_Films.db"

    repo_owner = "davegutz"
    repo_name = "myComputer"
    file_path = "IMDB_Films.db"

    timestamps = get_file_timestamps(local_path)
    local_timestamp = get_file_timestamp_gmt(local_path)
    if timestamps:
        print(f"File timestamps for local file '{file_path}':")
        print(f"Unix time GMT modification time:  {local_timestamp}")
        print(f"  Creation Time: {timestamps['creation_time']}")
        print(f"  Modification Time: {timestamps['modification_time']}")
        print(f"  Access Time: {timestamps['access_time']}\n")
    else:
        print(f"File '{file_path}' not found.")

    github_token = os.environ.get("GITHUB_TOKEN")
    timestamp_GitHub = get_file_timestamp_from_github(repo_owner, repo_name, file_path, github_token)
    gethub_timestamp = get_github_file_timestamp(repo_owner, repo_name, file_path, github_token)
    if timestamp_GitHub:
        print(f"Last modified timestamp of {file_path}: {timestamp_GitHub}")
    else:
        print(f"Could not retrieve timestamp for {file_path}")

    if gethub_timestamp and local_timestamp:
        time_diff = gethub_timestamp - local_timestamp
        print(f"Time difference = {time_diff}")

    print("\nChecking for newer git database version:")
    is_newer, info = check_newer_git_database(local_path, repo_owner=repo_owner, repo_name=repo_name, file_path=file_path)
    print(f"Newer version available: {is_newer}")
    print(f"Details: {info}")


if __name__ == "__main__":
    main()
