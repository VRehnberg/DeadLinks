# LinkChecking
A command line utility for checking a site for dead links. Useful for CI for
projects building sites.

**Note:** This only uses requests. Does not deal with javascript.

## Installation
```bash
pip install https://github.com/VRehnberg/LinkChecking/archive/v0.0.1.zip
```

## Usage
```bash
python -m linkchecking.checksite --help
```

## Alternatives
 - <https://www.deadlinkchecker.com/> no install required for manual use
 - <https://github.com/linkchecker/linkchecker> better maintained and more proper, but can be much slower
