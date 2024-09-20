import argparse
from unittest.mock import patch, MagicMock

import requests

from deadlinks.checksite import (
    simplify_link,
    get_links_from_page,
    is_internal_link,
    check_link_status,
    should_ignore_link,
    crawl_website,
    check_links,
)


def test_simplify_link():
    assert simplify_link("http://example.com/page?query=1") == "http://example.com/page"
    assert (
        simplify_link("https://example.com/path/to/page")
        == "https://example.com/path/to/page"
    )
    assert (
        simplify_link("https://example.com/page/#section")
        == "https://example.com/page/"
    )
    assert simplify_link("http://example.com/") == "http://example.com/"


# Mocked get_links_from_page
@patch("deadlinks.checksite.requests.get")
def test_get_links_from_page(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = "http://example.com"
    mock_response.content = b'<a href="/page1">Link 1</a><a href="http://external.com/page">External Link</a>'
    mock_get.return_value = mock_response

    url, links, success = get_links_from_page("http://example.com", timeout=5)

    assert success
    assert url == "http://example.com"
    assert links == {"/page1", "http://external.com/page"}


def test_is_internal_link():
    assert is_internal_link("/path", "example.com")
    assert is_internal_link("http://example.com/path", "example.com")
    assert not is_internal_link("http://external.com/path", "example.com")


@patch("deadlinks.checksite.requests.head")
def test_check_link_status(mock_head):
    # Case 1: Valid link
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_head.return_value = mock_response
    is_valid, status = check_link_status("http://example.com", timeout=5)
    assert is_valid
    assert status == 200

    # Case 2: Invalid link (404)
    mock_response.status_code = 404
    is_valid, status = check_link_status("http://example.com/notfound", timeout=5)
    assert not is_valid
    assert status == 404

    # Case 3: Exception during request
    mock_head.side_effect = requests.exceptions.RequestException("Connection error")
    is_valid, status = check_link_status("http://example.com/error", timeout=5)
    assert not is_valid
    assert "Connection error" in status


def test_should_ignore_link():
    ignore_patterns = ["^mailto:", "^#"]
    assert should_ignore_link("mailto:someone@example.com", ignore_patterns)
    assert should_ignore_link("#section", ignore_patterns)
    assert not should_ignore_link("http://example.com/page", ignore_patterns)


@patch("deadlinks.checksite.get_links_from_page")
def test_crawl_website(mock_get_links_from_page):
    mock_get_links_from_page.side_effect = [
        (
            "http://example.com",
            {"http://example.com/page1", "http://example.com/page2"},
            True,
        ),
        ("http://example.com/page1", {"http://example.com/page2"}, True),
        ("http://example.com/page2", set(), True),
    ]

    linked_pages = crawl_website(
        "http://example.com",
        max_depth=2,
        sleep_time=0,
        timeout=2,
        num_workers=1,
        verbose=True,
    )

    assert len(linked_pages) == 3
    assert "http://example.com" in linked_pages
    assert "http://example.com/page1" in linked_pages
    assert "http://example.com/page2" in linked_pages


# Mocked check_links
@patch("deadlinks.checksite.check_link_status")
def test_check_links(mock_check_link_status):
    # Mock results for checking each link
    mock_check_link_status.side_effect = [(True, 200), (False, 404), (True, 200)]

    linked_pages = {
        "http://example.com": {"http://example.com/page1", "http://example.com/page2"},
        "http://example.com/page1": {"http://example.com/page2"},
        "http://example.com/page2": set(),
    }

    all_ok = check_links(
        linked_pages, timeout=2, sleep_time=0, num_workers=1, verbose=True
    )

    assert not all_ok  # Because one of the links returned a 404 status


# Mocked `main`
@patch("deadlinks.checksite.crawl_website")
@patch("deadlinks.checksite.check_links")
@patch("argparse.ArgumentParser.parse_args")
def test_main(mock_parse_args, mock_check_links, mock_crawl_website):
    # Mock command-line arguments
    mock_parse_args.return_value = argparse.Namespace(
        start_url="http://example.com",
        max_depth=2,
        sleep_time=0,
        timeout=2,
        ignore=["^mailto:"],
        verbose=True,
        progressbar=False,
        num_workers=1,
    )

    # Mock crawling process
    mock_crawl_website.return_value = {
        "http://example.com": {"http://example.com/page1", "http://example.com/page2"},
        "http://example.com/page1": {"http://example.com/page2"},
        "http://example.com/page2": set(),
    }

    # Mock check_links returning True (all links OK)
    mock_check_links.return_value = True

    with patch("sys.exit") as mock_exit:
        from deadlinks.checksite import main

        main()
        mock_exit.assert_not_called()

    # Now simulate bad links (mock check_links returning False)
    mock_check_links.return_value = False

    with patch("sys.exit") as mock_exit:
        from deadlinks.checksite import main

        main()
        mock_exit.assert_called_once_with(1)
