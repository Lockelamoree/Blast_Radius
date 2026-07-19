import struct
from pathlib import Path

from scripts import submission_preflight as preflight


def _write_png(path: Path, width: int = 1200, height: int = 800, tail: bytes = b"") -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + tail
    )


def test_png_dimensions_reads_header(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    _write_png(image, 640, 480)
    assert preflight._png_dimensions(image) == (640, 480)


def test_gallery_check_detects_duplicate_assets(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in preflight.GALLERY:
        _write_png(assets / name)
    result = preflight._gallery_check(tmp_path)
    assert result.status == "warn"
    assert "duplicate" in result.detail


def test_documentation_check_detects_stale_claims(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("409 tests passed", encoding="utf-8")
    (tmp_path / "16_DEVPOST_FINAL_COPY.md").write_text("ready", encoding="utf-8")
    result = preflight._documentation_check(tmp_path)
    assert result.status == "fail"
    assert "409 tests passed" in result.detail


def test_current_submission_has_no_structural_failures() -> None:
    failures = [check for check in preflight.run_checks() if check.status == "fail"]
    assert failures == []
