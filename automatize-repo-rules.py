#!/usr/bin/env python3
"""
Configure an org's repositories rules
"""

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from ghapi.all import GhApi

from libgithub import (connect_github, get_repos, get_repos_maintainers,
                       set_repo_default_branch, set_repo_protection_info)


def match_repos_rules(repogroups: list[Any], repos: dict[str, Any]) -> dict[str, dict[str, Any]]:
    repos_with_rules: dict[str, dict[str, Any]] = {}

    for repo, repoinfo in repos.items():
        for repogroup in repogroups:
            included = False
            excluded = False
            include_rule = ""
            exclude_rule = ""
            for include in repogroup.get("include", []):
                if re.match(include, repo):
                    included = True
                    include_rule = include
                    break
            for exclude in repogroup.get("exclude", []):
                if re.match(exclude, repo):
                    excluded = True
                    exclude_rule = exclude
                    break

            if excluded:
                logging.info("Repo %s was excluded by rule %s", repo, exclude_rule)
            if included:
                logging.info("Repo %s was included by rule %s", repo, include_rule)

            if included and not excluded:
                repos_with_rules[repo] = repogroup
                break

    return repos_with_rules


def setup_repo(api: GhApi, org: str, name: str, branches_rules: dict[str, dict[str, Any]]) -> None:
    for branch, branch_rules in branches_rules.items():
        branch_rules = branch_rules or {}
        protection_args = branch_rules["branch_protection"]

        set_repo_protection_info(api, org, name, branch, protection_args)


def replace_maintainers_placeholders(data, maintainers, super_maintainers):
    # serialize then replace then deserialize
    data_str = json.dumps(data)
    maintainers_str = json.dumps(maintainers)
    super_maintainers_str = json.dumps(super_maintainers)

    data_str = data_str.replace('"@maintainers"', maintainers_str)
    data_str = data_str.replace('"@super-maintainers"', super_maintainers_str)

    data = json.loads(data_str)
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand")
    repositories = subparsers.add_parser("download_repositories")
    repositories.add_argument("-f", "--force")
    maintainers = subparsers.add_parser("download_maintainers")
    maintainers.add_argument("-f", "--force")
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.DEBUG)

    config_path = Path(__file__).parent / "config.yaml"
    config = yaml.safe_load(config_path.open("r", encoding="utf-8"))

    org = config["org"]
    api = connect_github()
    # api.debug = print_summary

    all_repos = get_repos(api, org)
    repos = match_repos_rules(config["repositories"], all_repos)

    if args.subcommand == "download_maintainers":
        maintainers_uncache = True
    else:
        maintainers_uncache = False
    repos_list_str = list(all_repos.keys())
    apps_maintainers = get_repos_maintainers(api, org, repos_list_str, uncache=maintainers_uncache)

    for repo, rules in repos.items():
        super_maintainers = config["super-maintainers"]
        app_maintainers = apps_maintainers[repo]

        branch_rules = {
            branch: replace_maintainers_placeholders(
                config["rulesets"][rulename],
                app_maintainers, super_maintainers)
            for branch, rulename in rules.get("branches", {}).items()
        }
        setup_repo(api, org, repo, branch_rules)

        if "default" in rules.keys():
            set_repo_default_branch(api, org, repo, rules["default"])


if __name__ == "__main__":
    main()
