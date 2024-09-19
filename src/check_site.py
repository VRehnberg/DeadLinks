import argparse
import re
import sys
from collections import defaultdict
from time import sleep
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


def simplify_link(link):
    parsed_url = urlparse(link)
    return urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))


def get_links_from_page(url, timeout):
    """Extract all links from a given page."""
    try:
        response = requests.get(url, timeout=timeout)
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return [], False
    else:
        if response.status_code != 200:
            print(f"Failed to retrieve {url}. Status code: {response.status_code}")
            return [], False

        soup = BeautifulSoup(response.content, 'html.parser')
        links = set(
            simplify_link(a_tag['href'])
            for a_tag in soup.find_all('a', href=True)
        )
        return links, True


def is_internal_link(link, base_domain):
    """Check if the link is an internal link to the website."""
    link_domain = urlparse(link).netloc
    return link_domain == "" or link_domain == base_domain


def check_link_status(link, timeout):
    """Check if the link is reachable."""
    try:
        response = requests.head(link, allow_redirects=True, timeout=timeout)
    except requests.exceptions.RequestException as e:
        return False, str(e)
    except Exception as e:
        print(f"Unknown error requesting {link}: {e}", file=sys.stderr)
        return False, str(e)
    else:
        if response.status_code >= 400:
            return False, response.status_code
        return True, response.status_code


def should_ignore_link(link, ignore_patterns):
    """Check if a link matches any ignore patterns."""
    return any(re.search(pattern, link) for pattern in ignore_patterns)


def crawl_website(start_url, max_depth=2, sleep_time=0.2, timeout=5, ignore_patterns=None, verbose=False):
    """Crawl the website from the start_url and check all links."""
    if ignore_patterns is None:
        ignore_patterns = []

    base_domain = urlparse(start_url).netloc
    visited_pages = set()
    pages_to_visit = [(start_url, 0)]
    linked_pages = defaultdict(set)

    while pages_to_visit:
        current_url, depth = pages_to_visit.pop(0)

        if current_url in visited_pages:
            if verbose: print(f"Skipping already visited {current_url}")
            continue

        if depth > max_depth:
            continue

        visited_pages.add(current_url)

        if verbose: print(f"Crawling: {current_url}")
        links, success = get_links_from_page(current_url, timeout)
        if verbose: print(f"Found {len(links)} links in {current_url}")
        if not success:
            continue

        for link in links:
            full_link = urljoin(current_url, link)  # convert relative links to absolute
            if verbose: print(f"{current_url} + {link} -> {full_link}")
            
            # Skip links that match any ignore patterns
            if should_ignore_link(full_link, ignore_patterns):
                if verbose: print(f"Ignoring link: {full_link}")
                continue
            else:
                linked_pages[current_url].add(full_link)

            # If it's an internal link and we haven't visited it, add to the queue
            is_internal = is_internal_link(full_link, base_domain)
            if is_internal and full_link not in visited_pages:
                pages_to_visit.append((simplify_link(full_link), depth + 1))

        # Sleep between requests to avoid overloading the server
        sleep(sleep_time)
    return linked_pages


def check_links(linked_pages: dict[str, set], timeout: float = 5, sleep_time: float = 0.2, progressbar: bool = False, verbose: bool = False) -> bool:
    '''Check for bad links, return true if all are ok.'''
    links_ok = True
    already_checked = {}
    pbar = tqdm(desc="Checking links:", total=len(set.union(*linked_pages.values())), disable=not progressbar)
    for current_link, links in linked_pages.items():
        for link in links:
            if verbose: pbar.write(f"Checking: {link}")
            if link in already_checked:
                valid, status_code = already_checked[link]
            else:
                valid, status_code = check_link_status(link, timeout)
                already_checked[link] = (valid, status_code)
                pbar.update(1)
                if verbose: pbar.write(f"Sleep {sleep_time} s to reduce load on server")
                sleep(sleep_time)

            if not valid:
                links_ok = False
                print(
                    f"Problematic link {link} on page {current_link}, status code {status_code}",
                    file=sys.stderr,
                )
            
    return links_ok


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Crawl a website and check for broken links.")
    parser.add_argument("start_url", help="The starting URL of the website to crawl.")
    parser.add_argument("--max-depth", type=int, default=2, help="Maximum depth when crawling (default: 2).")
    parser.add_argument("--sleep-time", type=float, default=0.1, help="The time to sleep between requests (default: 0.1 seconds).")
    parser.add_argument("--timeout", type=int, default=2, help="The request timeout in seconds (default: 2 seconds).")
    parser.add_argument("--ignore", nargs="*", default=[], help="List of patterns (regex) to ignore when crawling.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase verbosity.")
    parser.add_argument("--progressbar", action="store_true", help="Enable progress bar.")

    args = parser.parse_args()

    # Start the crawling process with the provided parameters
    linked_pages = crawl_website(
        args.start_url,
        max_depth=args.max_depth,
        sleep_time=args.sleep_time,
        timeout=args.timeout,
        ignore_patterns=args.ignore,
        verbose=args.verbose,
    )
    links_ok = check_links(
        linked_pages=linked_pages,
        sleep_time=args.sleep_time,
        timeout=args.timeout,
        verbose=args.verbose,
        progressbar=args.progressbar,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
