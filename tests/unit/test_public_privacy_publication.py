from pathlib import Path

import pytest

from sugarglider.offline_regions.copy_public_privacy import copy_public_privacy


def test_unfinished_policy_cannot_enter_the_public_site(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    policy = tmp_path / "policy.html"
    policy.write_text('<html data-policy-status="approved">{{CONTACT}}</html>')
    with pytest.raises(ValueError, match="publisher review"):
        copy_public_privacy(policy, site)
    assert list(site.iterdir()) == []


def test_reviewed_page_keeps_bytes_and_existing_region_files(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    region = site / "catalog.json"
    region.write_bytes(b"regional fixture unchanged\n")
    policy = tmp_path / "policy.html"
    content = '<html data-policy-status="approved">Sugarglider — Privacy</html>\n'
    policy.write_text(content)
    output = copy_public_privacy(policy, site)
    assert output.read_bytes() == content.encode()
    assert region.read_bytes() == b"regional fixture unchanged\n"
    with pytest.raises(FileExistsError):
        copy_public_privacy(policy, site)
    assert output.read_bytes() == content.encode()


@pytest.mark.parametrize(
    "content",
    [
        '<html data-policy-status="draft">Unreviewed</html>',
        '<html data-policy-status="approved"><script>example()</script></html>',
        '<html data-policy-status="approved"><iframe src="example"></iframe></html>',
    ],
)
def test_unreviewed_or_active_pages_are_rejected(tmp_path: Path, content: str) -> None:
    site = tmp_path / "site"
    site.mkdir()
    policy = tmp_path / "policy.html"
    policy.write_text(content)
    with pytest.raises(ValueError, match="publisher review"):
        copy_public_privacy(policy, site)
    assert list(site.iterdir()) == []


def test_policy_cannot_write_through_a_site_symlink(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    site = tmp_path / "site"
    site.symlink_to(actual, target_is_directory=True)
    policy = tmp_path / "policy.html"
    policy.write_text('<html data-policy-status="approved">Privacy</html>')
    with pytest.raises(ValueError, match="regular site"):
        copy_public_privacy(policy, site)
    assert list(actual.iterdir()) == []
