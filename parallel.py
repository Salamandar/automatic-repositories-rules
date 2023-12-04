#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from typing import Any, Callable


def parallel(
        function: Callable,
        items: list[Any],
        *args) -> list[Any]:
    repeated_args = (repeat(arg) for arg in args)

    results = []
    executor = ThreadPoolExecutor(max_workers=100)
    for result in executor.map(function, *repeated_args, items):
        results.append(result)

    return results
