#!/usr/bin/env python3
"""
Configure an org's repositories rules
"""

import argparse
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from ghapi.all import GhApi, print_summary

from libgithub import (connect_github, get_repo_maintainers,
                       get_repo_protection_info, get_repos, get_repos_maintainers)
from merge_dicts import merge_list_of_dicts


def filter_repos(repogroups: list[Any], repos: dict[str, Any]) -> dict[str, list[str]]:
    repos_with_rules: dict[str, list[str]] = {}

    for repo, repoinfo in repos.items():
        rules = []
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
                rules.extend(repogroup.get("rulesets", []))

        if rules:
            repos_with_rules[repo] = rules

    return repos_with_rules


def setup_repo(api: GhApi, org: str, name: str, rulesets: dict[str, dict[str, Any]]) -> None:
    rules = merge_list_of_dicts(rulesets.values())
    for branch, branch_rules in rules.get("branches", {}).items():
        branch_rules = branch_rules or {}

        # Is required if signed_commit...
        api.repos.update_branch_protection(
            org,
            name,
            branch,
            enforce_admins=False,
            required_pull_request_reviews={},
            required_status_checks={"strict": False, "contexts": []},
            restrictions={"users": [], "teams": []},
            allow_force_pushes=False
        )

        if "signed_commits" in branch_rules.keys():
            if branch_rules["signed_commits"]:
                api.repos.create_commit_signature_protection(org, name, branch)
            else:
                api.repos.delete_commit_signature_protection(org, name, branch)

        # api.repos.update_branch_protection(
        #     org,
        #     name,

        # )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand")
    repositories = subparsers.add_parser("download_repositories")
    repositories.add_argument("-f", "--force")
    maintainers = subparsers.add_parser("download_maintainers")
    maintainers.add_argument("-f", "--force")
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.WARN)

    config_path = Path(__file__).parent / "config.yaml"
    config = yaml.safe_load(config_path.open("r", encoding="utf-8"))

    org = config["org"]
    api = connect_github()
    # api.debug = print_summary

    if args.subcommand == "download_maintainers":
        all_repos = get_repos(api, org)
        repos = list(all_repos.keys())
        get_repos_maintainers(api, org, repos, uncache=True)

    # all_repos = get_repos(api, org)

    # repos = filter_repos(config["repositories"], all_repos)

    # for repo, rulenames in repos.items():
    #     rules = {rule: config["rulesets"][rule] for rule in rulenames}
    #     setup_repo(api, org, repo, rules)

    # repos_data = parallel(get_repo, all_repos, api, org)
    # print(yaml.dump(get_repo_protection_info(api, org, "endi_ynh")))

    # print(get_repo_maintainers(api, org, "endi_ynh"))
    # print(len(repos_data))
    # print(repos_data[-1])


if __name__ == "__main__":
    main()
