from __future__ import annotations

import argparse
import os
import re
import sys
from time import sleep
from urllib.parse import urljoin, urlparse, urlunparse
from typing import Optional, Union

import requests
from bs4 import BeautifulSoup
from termcolor import colored
from tqdm.contrib.concurrent import thread_map


def simplify_link(link: str) -> str:
    parsed_url = urlparse(link)
    return urlunparse(
        (parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "", "")
    )


def get_links_from_page(url: str, timeout: float) -> tuple[str, set[str], bool]:
    """Extract all links from a given page."""
    try:
        response = requests.get(url, timeout=timeout)
    except Exception as e:
        print(
            f"{colored('Error', 'red')} fetching {colored(url, 'red')}: {e}",
            file=sys.stderr,
        )
        return url, set(), False
    else:
        if response.url != url:
            print(
                f"{colored('WARN', 'yellow')} Link not pointing to endpoint {colored(url, 'yellor')} -> {response.url}",
                file=sys.stderr,
            )
            url = response.url
        if response.status_code != 200:
            print(
                f"{colored('Failed', 'red')} to retrieve {colored(url, 'red')}. Status code: {response.status_code}"
            )
            return url, set(), False

        soup = BeautifulSoup(response.content, "html.parser")
        links = set(
            simplify_link(a_tag["href"]) for a_tag in soup.find_all("a", href=True)
        )
        return url, links, True


def is_internal_link(link: str, base_domain: str) -> bool:
    """Check if the link is an internal link to the website."""
    link_domain = urlparse(link).netloc
    return link_domain == "" or link_domain == base_domain


def check_link_status(link: str, timeout: float) -> tuple[bool, Union[int, str]]:
    """Check if the link is reachable."""
    try:
        response = requests.head(link, allow_redirects=True, timeout=timeout)
    except requests.exceptions.RequestException as e:
        return False, str(e)
    except Exception as e:
        print(
            f"{colored('Unknown error', 'red')} requesting {colored(link, 'red')}: {e}",
            file=sys.stderr,
        )
        return False, str(e)
    else:
        if response.status_code >= 400:
            return False, response.status_code
        return True, response.status_code


def should_ignore_link(link: str, ignore_patterns: list[str]) -> bool:
    """Check if a link matches any ignore patterns."""
    return any(re.search(pattern, link) for pattern in ignore_patterns)


def crawl_website(
    start_url: str,
    max_depth: int = 2,
    sleep_time: float = 0.0,
    timeout: float = 2.0,
    ignore_patterns: Optional[list[str]] = None,
    verbose: bool = False,
    num_workers: int = 1,
    progressbar: bool = False,
) -> dict[str, dict[str, bool]]:
    """Crawl the website from the start_url and check all links."""
    if ignore_patterns is None:
        ignore_patterns = []

    base_domain = urlparse(start_url).netloc

    def worker(current_url: str) -> tuple[str, dict[str, bool]]:
        """For an url, return resulting url, and dictionary with all links and
        if thery are internal"""
        current_url, links, success = get_links_from_page(current_url, timeout)
        if verbose:
            print(f"Found {len(links)} links in {current_url}")
        if not success:
            return (current_url, dict())

        def get_full_link(link: str) -> str:
            return urljoin(current_url, link)

        links = {
            full_link: is_internal_link(full_link, base_domain)
            for full_link in map(get_full_link, links)
            if not should_ignore_link(full_link, ignore_patterns)
        }

        # Sleep between requests to avoid overloading the server
        sleep(sleep_time)
        return current_url, links

    visited_pages = set()
    pages_to_visit = {start_url}
    linked_pages = dict()

    depth = 0
    while len(pages_to_visit) > 0:
        linked_pages.update(
            dict(
                thread_map(
                    worker,
                    pages_to_visit,
                    desc=f"Crawling at depth {depth}",
                    max_workers=num_workers,
                    disable=not progressbar,
                )
            )
        )
        visited_pages |= pages_to_visit
        visited_pages |= set(linked_pages.keys())
        internal_links = set(
            link
            for links in linked_pages.values()
            for link, is_internal in links.items()
            if is_internal
        )
        pages_to_visit = internal_links - visited_pages

        depth += 1
        if max_depth is not None and depth > max_depth:
            break

    if not any(linked_pages.values()):
        requests.get(start_url, timeout=timeout).raise_for_status()
        # if error not thrown on line above
        print(f"{colored('WARN', 'yellow')} No links found! Check {start_url}")

    return linked_pages


def check_links(
    linked_pages: dict[str, dict[str, bool]],
    timeout: float = 2.0,
    sleep_time: float = 0.0,
    progressbar: bool = False,
    verbose: bool = False,
    num_workers: int = 1,
) -> bool:
    """Check for bad links, return true if all are ok."""

    def worker(link):
        valid, status_link = check_link_status(link, timeout)
        sleep(sleep_time)
        return valid, status_link

    # Check links in parallel
    unique_links = set(
        link for links in linked_pages.values() for link, is_internal in links.items()
    )
    link_check_results = dict(
        zip(
            unique_links,
            thread_map(
                worker,
                unique_links,
                desc="Checking links",
                max_workers=num_workers,
                disable=not progressbar,
            ),
        )
    )

    # Print problematic links to stderr
    all_links_ok = all(valid for valid, _ in link_check_results.values())
    if all_links_ok:
        print(
            colored(
                f"All {sum(len(links) for links in linked_pages.values())} links OK!",
                "green",
            )
        )
    else:
        print(colored("Problematic links found:", "red"), file=sys.stderr)
        num_invalid_links = 0
        for current_link, links in linked_pages.items():
            for link in links:
                valid, status_code = link_check_results[link]
                if not valid:
                    num_invalid_links += 1
                    print(
                        f"  {colored(link, 'red')} at {colored(current_link, 'yellow')} status code {status_code}",
                        file=sys.stderr,
                    )
        print(
            f"in total {colored(str(num_invalid_links), 'red')}/{sum(len(links) for links in linked_pages.values())} links where invalid."
        )

    return all_links_ok


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Crawl a website and check for broken links."
    )
    parser.add_argument("start_url", help="The starting URL of the website to crawl.")
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum depth when crawling (default: no-limit).",
    )
    parser.add_argument(
        "--sleep-time",
        type=float,
        default=0.0,
        help="The time to sleep between requests (default: 0 seconds).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="The request timeout in seconds (default: 2 seconds).",
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        help="List of patterns (regex) to ignore when crawling.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Increase verbosity."
    )
    parser.add_argument(
        "--progressbar", action="store_true", help="Enable progress bar."
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="Number of threads to use (default: max(32, cpu_count() + 4)).",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colors in output."
    )

    args = parser.parse_args()

    # Disable color if selected
    if args.no_color:
        os.environ["NO_COLOR"] = "1"

    # Start the crawling process with the provided parameters
    linked_pages = crawl_website(
        args.start_url,
        max_depth=args.max_depth,
        sleep_time=args.sleep_time,
        timeout=args.timeout,
        ignore_patterns=args.ignore,
        verbose=args.verbose,
        progressbar=args.progressbar,
        num_workers=args.num_workers,
    )
    links_ok = check_links(
        linked_pages=linked_pages,
        sleep_time=args.sleep_time,
        timeout=args.timeout,
        verbose=args.verbose,
        progressbar=args.progressbar,
        num_workers=args.num_workers,
    )
    if not links_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
