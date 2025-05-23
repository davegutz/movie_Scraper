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
import time
import requests
import datetime


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
    Returns the file's last modification timestamp in seconds since the epoch (GMT).
    """
    timestamp = os.path.getmtime(file_path) + get_gmt_offset_seconds()
    return timestamp


def get_file_timestamp_from_github(repo_owner, repo_name, file_path, github_token=None):
    """
    Retrieves the last modified timestamp of a file in a GitHub repository.

    Args:
        repo_owner (str): The owner of the repository.
        repo_name (str): The name of the repository.
        file_path (str): The path to the file within the repository.
        github_token (str, optional): A personal access token for the GitHub API. Defaults to None.

    Returns:
        str: The last modified timestamp of the file in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ), or None if an error occurs.
    """
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
    params = {'path': file_path, 'per_page': 1}
    headers = {}
    if github_token:
        headers['Authorization'] = f"token {github_token}"

    try:
        response = requests.get(api_url, headers=headers, params=params)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        if response.status_code == 200 and response.headers.get('Last-Modified'):
            return response.headers['Last-Modified']
        else:
            return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None


def get_github_file_timestamp(repo_owner, repo_name, file_path, github_token=None):
    """
    Retrieves the timestamp of a file from a GitHub repository in Unix time.

    Args:
        repo_owner (str): The owner of the repository.
        repo_name (str): The name of the repository.
        file_path (str): The path to the file within the repository.
        github_token (str, optional): A GitHub personal access token. Defaults to None.

    Returns:
        int: The Unix timestamp of the file's last modification, or None if an error occurs.
    """
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits?path={file_path}&per_page=1"
    headers = {}
    if github_token:
        headers['Authorization'] = f"token {github_token}"

    response = requests.get(api_url, headers=headers)

    if response.status_code == 200:
        commits = response.json()
        if commits:
            date_str = commits[0]['commit']['author']['date']
            datetime_obj = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
            timestamp = int(datetime_obj.timestamp())
            return timestamp
        else:
            print("No commits found for this file.")
            return None
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None


def main():
    # Example usage
    local_path = "C:/Users/daveg/Documents/myComputer/IMDB_Films.db"  # self.db_folder + / + self.db_name

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
        #1748028810

    github_token = os.environ.get("GITHUB_TOKEN")  # it's better to use environment variables
    timestamp_GitHub = get_file_timestamp_from_github(repo_owner, repo_name, file_path, github_token)
    gethub_timestamp = get_github_file_timestamp(repo_owner, repo_name, file_path, github_token)
    if timestamp_GitHub:
        print(f"Last modified timestamp of {file_path}: {timestamp_GitHub}")
    else:
        print(f"Could not retrieve timestamp for {file_path}")

    time_diff = gethub_timestamp - local_timestamp
    print(f"Time difference = {time_diff}")


if __name__ == "__main__":
    main()
