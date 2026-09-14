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
import datetime
import subprocess
import json

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

try:
    import requests
except ImportError:
    requests = None

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


def _http_get(url, headers=None, params=None, timeout=5):
    """
    HTTP GET helper returning (status_code, json_data, headers_dict).
    Uses requests if installed, otherwise falls back to urllib.request.
    """
    if params:
        query = '&'.join([f"{k}={v}" for k, v in params.items()])
        sep = '&' if '?' in url else '?'
        url = f"{url}{sep}{query}"

    req_headers = dict(headers or {})
    if 'User-Agent' not in req_headers:
        req_headers['User-Agent'] = 'Python-git-check'

    if requests is not None:
        r = requests.get(url, headers=req_headers, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = None
        return r.status_code, data, r.headers

    # Fallback to urllib.request
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            try:
                data = json.loads(body) if body else None
            except Exception:
                data = None
            return status, data, dict(response.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8') if hasattr(e, 'read') else ''
        try:
            data = json.loads(body) if body else None
        except Exception:
            data = None
        return e.code, data, dict(e.headers)
    except Exception as e:
        raise e


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
        status_code, _, resp_headers = _http_get(api_url, headers=headers, params=params, timeout=timeout)
        if status_code == 200 and resp_headers.get('Last-Modified'):
            return resp_headers['Last-Modified']
        else:
            return None

    except Exception as e:
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
        status_code, commits, _ = _http_get(api_url, headers=headers, timeout=timeout)

        if status_code == 200:
            if commits:
                date_str = commits[0]['commit']['author']['date']
                datetime_obj = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                timestamp = int(datetime_obj.timestamp())
                return timestamp
            else:
                # Try alternate case if file_path case differed
                alt_path = 'IMDB_Films.db' if file_path == 'IMDB_films.db' else 'IMDB_films.db'
                alt_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits?path={alt_path}&per_page=1"
                alt_status, alt_commits, _ = _http_get(alt_url, headers=headers, timeout=timeout)
                if alt_status == 200 and alt_commits:
                    date_str = alt_commits[0]['commit']['author']['date']
                    datetime_obj = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                    return int(datetime_obj.timestamp())

                print(f"No commits found for file '{file_path}'.")
                return None
        else:
            print(f"Error: HTTP {status_code}")
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def check_newer_git_repo(repo_dir=None, repo_owner=None, repo_name=None, file_path=None, github_token=None, timeout=5, print_status=True):
    """
    Checks if a newer version of a repository (or a specific file within it) exists in git.
    Uses git CLI with fetch if local directory is a git repository, and falls back to GitHub REST API.

    Args:
        repo_dir (str, optional): Path to local repository directory or file. Defaults to current directory.
        repo_owner (str, optional): GitHub repository owner. If None, auto-detected from origin remote.
        repo_name (str, optional): GitHub repository name. If None, auto-detected from origin remote.
        file_path (str, optional): Path or filename within repository to check. If None, checks entire repository.
        github_token (str, optional): GitHub personal access token (or env GITHUB_TOKEN).
        timeout (int): Timeout in seconds for git and network requests (default: 5).
        print_status (bool): If True, print status updates to the screen (default: True).

    Returns:
        tuple (bool, dict):
            bool: True if remote git has a newer version than local, False otherwise.
            dict: Info dictionary containing commit information, dates, and check details.
    """
    if repo_dir:
        repo_dir = os.path.abspath(repo_dir)
        if os.path.isfile(repo_dir):
            file_path = file_path or os.path.basename(repo_dir)
            repo_dir = os.path.dirname(repo_dir)
    else:
        repo_dir = os.path.abspath('.')

    # Handle case-insensitivity on local filesystem if file_path specified
    if file_path:
        full_file_path = os.path.join(repo_dir, file_path)
        if not os.path.exists(full_file_path) and os.path.isdir(repo_dir):
            target = file_path.lower()
            for f in os.listdir(repo_dir):
                if f.lower() == target:
                    file_path = f
                    full_file_path = os.path.join(repo_dir, f)
                    break

        if not os.path.exists(full_file_path):
            err = f"Local file does not exist: {full_file_path}"
            if print_status:
                print(Colors.fg.red, f"[Git Check] {err}", Colors.reset)
            return False, {'error': err}

    # 1. Check if repo_dir is inside a git repository
    is_git_repo = False
    try:
        r = subprocess.run(
            ['git', '-C', repo_dir, 'rev-parse', '--is-inside-work-tree'],
            capture_output=True, text=True, timeout=timeout
        )
        is_git_repo = (r.returncode == 0 and r.stdout.strip() == 'true')
    except Exception:
        pass

    # Extract repository owner/name from origin remote if available
    if is_git_repo:
        try:
            r = subprocess.run(
                ['git', '-C', repo_dir, 'remote', 'get-url', 'origin'],
                capture_output=True, text=True, timeout=timeout
            )
            if r.returncode == 0 and r.stdout.strip():
                url = r.stdout.strip()
                match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', url)
                if match:
                    if not repo_owner:
                        repo_owner = match.group(1)
                    if not repo_name:
                        repo_name = match.group(2)
        except Exception:
            pass

    repo_name = repo_name or os.path.basename(repo_dir)
    repo_owner = repo_owner or "davegutz"

    target_desc = f"'{repo_name}/{file_path}'" if file_path else f"repository '{repo_name}'"

    if print_status:
        print(f"[Git Check] Evaluating {target_desc} in '{repo_dir}'...")

    # 2. Try git CLI fetch & rev-list if local folder is a git repo
    git_fetch_success = False
    if is_git_repo:
        if print_status:
            print(f"[Git Check] Local git repository detected for {target_desc}.")
            print(f"[Git Check] Fetching updates from remote 'origin' (timeout {timeout}s)...")
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        try:
            r = subprocess.run(
                ['git', '-C', repo_dir, 'fetch', 'origin'],
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
                    ['git', '-C', repo_dir, 'rev-parse', '--verify', ref],
                    capture_output=True, text=True, timeout=timeout
                )
                if r.returncode == 0:
                    upstream = ref
                    break

            if upstream:
                if print_status:
                    print(f"[Git Check] Comparing HEAD against upstream '{upstream}' for {target_desc}...")
                rev_cmd = ['git', '-C', repo_dir, 'rev-list', '--count', f'HEAD..{upstream}']
                if file_path:
                    rev_cmd.extend(['--', file_path])

                r = subprocess.run(rev_cmd, capture_output=True, text=True, timeout=timeout)
                if r.returncode == 0:
                    count = int(r.stdout.strip())
                    if count > 0:
                        rem_cmd = ['git', '-C', repo_dir, 'log', '-1', '--format=%H%x00%ci%x00%s', upstream]
                        loc_cmd = ['git', '-C', repo_dir, 'log', '-1', '--format=%H%x00%ci%x00%s', 'HEAD']
                        if file_path:
                            rem_cmd.extend(['--', file_path])
                            loc_cmd.extend(['--', file_path])

                        r_log = subprocess.run(rem_cmd, capture_output=True, text=True, timeout=timeout)
                        rem_sha, rem_date, rem_msg = r_log.stdout.strip().split('\x00') if r_log.returncode == 0 and r_log.stdout.strip() else ('', '', '')

                        l_log = subprocess.run(loc_cmd, capture_output=True, text=True, timeout=timeout)
                        loc_sha, loc_date, loc_msg = l_log.stdout.strip().split('\x00') if l_log.returncode == 0 and l_log.stdout.strip() else ('', '', '')

                        if print_status:
                            print(Colors.fg.yellow, f"[Git Check] Remote '{upstream}' is ahead by {count} commit(s) for {target_desc}!", Colors.reset)
                            print(f"[Git Check]   Remote commit: {rem_sha[:7]} ({rem_date}) - {rem_msg}")
                            print(f"[Git Check]   Local commit:  {loc_sha[:7]} ({loc_date})")

                        return True, {
                            'method': 'git',
                            'repo_name': repo_name,
                            'remote_sha': rem_sha[:7],
                            'remote_date': rem_date,
                            'remote_msg': rem_msg,
                            'local_sha': loc_sha[:7] if loc_sha else 'None',
                            'local_date': loc_date if loc_date else 'None',
                            'behind_count': count,
                        }
                    else:
                        if print_status:
                            print(Colors.fg.green, f"[Git Check] Local repository is up to date with '{upstream}' for {target_desc}.", Colors.reset)
                        return False, {'method': 'git', 'repo_name': repo_name, 'status': 'up-to-date'}

    # 3. Fallback to GitHub REST API (if git fetch failed, upstream not found, or not a git repo)
    if print_status:
        print(f"[Git Check] Querying GitHub REST API for '{repo_owner}/{repo_name}'...")
    try:
        if not github_token:
            github_token = os.environ.get("GITHUB_TOKEN")
        headers = {}
        if github_token:
            headers['Authorization'] = f"token {github_token}"

        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
        params = {'per_page': 1}
        if file_path:
            params['path'] = file_path

        status_code, commits, _ = _http_get(api_url, headers=headers, params=params, timeout=timeout)

        # If no commits found with given filename case, try alternate case
        if not commits and file_path and status_code == 200:
            alt_filename = 'IMDB_Films.db' if file_path == 'IMDB_films.db' else 'IMDB_films.db'
            params['path'] = alt_filename
            alt_status, alt_commits, _ = _http_get(api_url, headers=headers, params=params, timeout=timeout)
            if alt_status == 200:
                commits = alt_commits

        if commits:
            rem_sha = commits[0]['sha']
            rem_date = commits[0]['commit']['author']['date']
            rem_msg = commits[0]['commit']['message']
            rem_dt = datetime.datetime.strptime(rem_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
            rem_ts = rem_dt.timestamp()

            if is_git_repo:
                loc_cmd = ['git', '-C', repo_dir, 'log', '-1', '--format=%H%x00%ct%x00%ci']
                if file_path:
                    loc_cmd.extend(['--', file_path])
                loc_log = subprocess.run(loc_cmd, capture_output=True, text=True, timeout=timeout)
                if loc_log.returncode == 0 and loc_log.stdout.strip():
                    parts = loc_log.stdout.strip().split('\x00')
                    loc_sha = parts[0]
                    loc_ts = parts[1]
                    loc_date = parts[2] if len(parts) > 2 else ''

                    if loc_sha == rem_sha:
                        if print_status:
                            print(Colors.fg.green, f"[Git Check] Local commit ({loc_sha[:7]}) matches GitHub commit for {target_desc}. Up to date.", Colors.reset)
                        return False, {'method': 'github_api', 'repo_name': repo_name, 'status': 'up-to-date'}

                    if rem_ts > float(loc_ts):
                        if print_status:
                            print(Colors.fg.yellow, f"[Git Check] GitHub has newer commit ({rem_sha[:7]} at {rem_date}) than local ({loc_sha[:7]}) for {target_desc}.", Colors.reset)
                        return True, {
                            'method': 'github_api',
                            'repo_name': repo_name,
                            'remote_sha': rem_sha[:7],
                            'remote_date': rem_date,
                            'remote_msg': rem_msg,
                            'local_sha': loc_sha[:7],
                            'local_date': loc_date,
                        }
                    else:
                        if print_status:
                            print(Colors.fg.green, f"[Git Check] Local commit ({loc_sha[:7]}) is equal or newer than GitHub ({rem_sha[:7]}) for {target_desc}.", Colors.reset)
                        return False, {'method': 'github_api', 'repo_name': repo_name, 'status': 'up-to-date'}

            # Non-git folder with file_path
            if file_path:
                full_file_path = os.path.join(repo_dir, file_path)
                local_mtime = os.path.getmtime(full_file_path)
                if rem_ts > local_mtime + 60:
                    loc_time_str = datetime.datetime.fromtimestamp(local_mtime, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    if print_status:
                        print(Colors.fg.yellow, f"[Git Check] GitHub commit ({rem_date}) is newer than local file ({loc_time_str}).", Colors.reset)
                    return True, {
                        'method': 'github_api',
                        'repo_name': repo_name,
                        'remote_sha': rem_sha[:7],
                        'remote_date': rem_date,
                        'remote_msg': rem_msg,
                        'local_mtime': loc_time_str,
                    }
                else:
                    if print_status:
                        print(Colors.fg.green, f"[Git Check] Local file modification time is up to date with GitHub commit.", Colors.reset)
                    return False, {'method': 'github_api', 'repo_name': repo_name, 'status': 'up-to-date'}

        elif status_code == 403:
            msg = "GitHub API rate limit exceeded"
            if print_status:
                print(Colors.fg.orange, f"[Git Check] {msg}", Colors.reset)
            return False, {'method': 'github_api', 'repo_name': repo_name, 'status': 'rate-limited', 'error': msg}
        elif status_code != 200:
            msg = f"HTTP {status_code} from GitHub API"
            if print_status:
                print(Colors.fg.orange, f"[Git Check] {msg}", Colors.reset)
            return False, {'method': 'github_api', 'repo_name': repo_name, 'status': msg}

    except Exception as e:
        if print_status:
            print(Colors.fg.orange, f"[Git Check] Error querying GitHub API: {e}", Colors.reset)
        return False, {'status': 'error', 'repo_name': repo_name, 'error': str(e)}

    return False, {'status': 'up-to-date', 'repo_name': repo_name}


def check_newer_git_database(local_db_path=None, repo_owner="davegutz", repo_name="myComputer", file_path="IMDB_Films.db", github_token=None, timeout=5, print_status=True):
    """
    Checks if a newer version of the database exists in the git repository (e.g. myComputer).
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

    return check_newer_git_repo(
        repo_dir=db_folder,
        repo_owner=repo_owner,
        repo_name=repo_name,
        file_path=db_filename,
        github_token=github_token,
        timeout=timeout,
        print_status=print_status
    )


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

    print("\n--- Checking for newer application repository (movie_Scraper) ---")
    app_dir = os.path.dirname(os.path.abspath(__file__))
    is_newer_app, info_app = check_newer_git_repo(repo_dir=app_dir)
    print(f"Application update available: {is_newer_app}")
    print(f"Details: {info_app}")

    print("\n--- Checking for newer database file (IMDB_Films.db) ---")
    is_newer_db, info_db = check_newer_git_database(local_path, repo_owner=repo_owner, repo_name=repo_name, file_path=file_path)
    print(f"Database update available: {is_newer_db}")
    print(f"Details: {info_db}")


if __name__ == "__main__":
    main()
