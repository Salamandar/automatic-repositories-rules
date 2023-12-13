#!/usr/bin/env python3

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import tomlkit
import yaml
from fastcore.xtras import obj2dict
from ghapi.all import GhApi, pages

from parallel import parallel


def file_cached(jsonfile):
    def decorator(fn):
        def wrapped(*args, uncache=False, **kwargs):
            cache_path = Path(__file__).parent / jsonfile
            if uncache:
                cache_path.unlink(missing_ok=True)
            if cache_path.exists():
                return json.load(cache_path.open("r", encoding="utf-8"))
            data = fn(*args, **kwargs)
            json.dump(data, cache_path.open("w", encoding="utf-8"), indent=4)
            return data
        return wrapped
    return decorator


def connect_github() -> GhApi:
    secrets_path = Path(__file__).parent / "secrets.yaml"
    secrets = yaml.safe_load(secrets_path.open("r", encoding="utf-8"))

    api = GhApi(token=secrets["token"])
    return api


@file_cached("cache-repositories.json")
def get_repos(api: GhApi, org: str) -> dict[str, Any]:
    """file-cached repo list"""
    repos_list = pages(api.repos.list_for_org, 8, org).concat().map(lambda x: x.name)

    repos_info = parallel(get_repo_protection_info, repos_list, api, org)
    repos = {
        name: info
        for name, info in repos_info
    }
    return repos


def get_repo_protection_info(api: GhApi, org: str, repo: str) -> tuple[str, Any]:
    branches = pages(api.repos.list_branches, 1, org, repo).concat()
    protections: dict[str, Any] = {}
    for branch in branches:
        name = branch.name
        if branch.get("protected"):
            protection = api.repos.get_branch_protection(org, repo, name)
            protections[name] = obj2dict(protection)
        else:
            protections[name] = None

    return (repo, protections)


def set_repo_protection_info(api: GhApi, org: str, repo: str, branch, info: Any) -> None:
    api.repos.update_branch_protection(
        org,
        repo,
        branch,
        **info
    )


def get_repo_maintainers(api: GhApi, org: str, repo: str) -> list[str] | None:
    manifestv = 0
    try:
        result = api.repos.get_content(org, repo, "manifest.toml", "master")
        manifestv = 2
    except HTTPError as err:
        if err.code != 404:
            raise
        try:
            result = api.repos.get_content(org, repo, "manifest.json", "master")
            manifestv = 1
        except HTTPError as err2:
            if err2.code != 404:
                raise
            return None

    contentb64 = result.get("content")
    content = base64.decodebytes(contentb64.encode("utf-8")).decode("utf-8")

    if manifestv == 1:
        manifest = json.loads(content)
        maintainer = manifest.get("maintainer", {})
        if not isinstance(maintainer, list):
            maintainers = [maintainer]
        maintainers = list(
            filter(lambda x: " " not in x,
                   map(lambda x: x["name"],
                       filter(lambda x: "name" in x.keys(),
                              maintainers))))

    if manifestv == 2:
        manifest = tomlkit.loads(content)
        maintainers = list(manifest.get("maintainers", []))

    print(repo, maintainers)
    return maintainers


@file_cached("cache-maintainers.json")
def get_repos_maintainers(api: GhApi, org: str, repos: list[str]) -> dict[str, list[str]|None]:
    def parallel_maintainers(api, org, repo, *args, **kwargs):
        try:
            return (
                repo,
                get_repo_maintainers(api, org, repo, *args, **kwargs)
            )
        except HTTPError:
            raise
        except Exception as err:
            print(f"repo {repo} returned {err}")
            return (repo, None)

    maintainers = parallel(parallel_maintainers, repos, api, org)
    return dict(maintainers)
