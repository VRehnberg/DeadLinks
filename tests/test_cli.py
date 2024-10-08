import subprocess
import pytest


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
    ],
)
def test_checksite_command(url):
    try:
        result = subprocess.run(
            ["python", "-m", "linkchecking.checksite", "--no-color", url],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        assert (
            "All 1 links OK!" in result.stdout
            or "Problematic links found" in result.stderr
        )

    except FileNotFoundError:
        pytest.fail("Command-line utility could not be found or executed.")
