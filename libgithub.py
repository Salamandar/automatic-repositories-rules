#!/usr/bin/env python3

import base64
import json
import logging
from functools import cache
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


def set_repo_protection_info(api: GhApi, org: str, repo: str, branch: str, info: Any) -> None:
    logging.info("Setting protection for %s / %s / %s", org, repo, branch)
    api.repos.update_branch_protection(
        org,
        repo,
        branch,
        **info
    )


def set_repo_default_branch(api: GhApi, org: str, repo: str, branch: str):
    logging.info("Setting default branch for %s / %s to %s", org, repo, branch)
    api.repos.update(
        org,
        repo,
        default_branch=branch
    )

@cache
@file_cached("cache-repositories.json")
def get_repos(api: GhApi, org: str) -> dict[str, Any]:
    def repo_get_branches(api, org, repo):
        try:
            branches = [
                branch["name"]
                for branch in pages(api.repos.list_branches, 1, org, repo).concat()
            ]
            return (repo, branches)
        except HTTPError:
            raise
        except Exception as err:
            print(f"repo {repo} returned {err}")
            return (repo, None)

    repos_list = pages(api.repos.list_for_org, 30, org, per_page=30).concat().map(lambda x: x.name)

    result = parallel(repo_get_branches, repos_list, api, org)
    return dict(result)


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

    return dict(parallel(parallel_maintainers, repos, api, org))
