# DeadLinks
A command line utility for checking a site for deadlinks. Useful for CI for
projects building sites.

**Note:** This only uses requests. Does not deal with javascript.

## Installation
```bash
pip install deadlinks
```

## Usage
```bash
python -m deadlinks.checksite --help
```

## Alternatives
 - <https://www.deadlinkchecker.com/> no install required for manual use
 - <https://github.com/linkchecker/linkchecker> better maintained and more proper, but can be much slower
