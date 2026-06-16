from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import pytest
from PIL import Image

from formatter import DEFAULT_PALETTE, FormatOptions, InvalidInputError, UnsupportedFormatError, format_file, format_image


def test_dimensions_preserve_aspect_ratio_and_scale():
    source = Image.new("RGB", (40, 20), "red")
    output = format_image(source, FormatOptions(width=8, grid=False, scale=3))
    assert output.size == (24, 12)


def test_palette_matching_uses_only_supported_colors():
    source = Image.new("RGB", (2, 1))
    source.putdata([(250, 65, 5), (215, 215, 215)])
    output = np.asarray(format_image(source, FormatOptions(width=2, grid=False, scale=1)).convert("RGB"))
    assert all(any(np.array_equal(pixel, color) for color in DEFAULT_PALETTE) for pixel in output.reshape(-1, 3))


def test_transparency_is_preserved():
    source = Image.new("RGBA", (2, 1), (255, 0, 0, 255))
    source.putpixel((1, 0), (0, 0, 0, 0))
    output = format_image(source, FormatOptions(width=2, grid=False, scale=1))
    assert output.getpixel((1, 0))[3] == 0


@pytest.mark.parametrize("width", [0, 1001])
def test_invalid_width(width):
    with pytest.raises(InvalidInputError):
        format_image(Image.new("RGB", (1, 1)), FormatOptions(width=width))


def test_invalid_and_unsupported_files(tmp_path: Path):
    invalid = tmp_path / "broken.png"
    invalid.write_bytes(b"not an image")
    with pytest.raises(InvalidInputError):
        format_file(invalid, tmp_path / "out.png", FormatOptions(width=2))
    unsupported = tmp_path / "file.txt"
    unsupported.write_text("hello")
    with pytest.raises(UnsupportedFormatError):
        format_file(unsupported, tmp_path / "out.png", FormatOptions(width=2))


def test_static_file_smoke(tmp_path: Path):
    source = tmp_path / "source.png"
    Image.new("RGB", (4, 2), "blue").save(source)
    result = format_file(source, tmp_path / "result.png", FormatOptions(width=2, grid=False))
    assert result.output_path.is_file()
    assert Image.open(result.output_path).size == (20, 10)


def test_gif_smoke(tmp_path: Path):
    source = tmp_path / "source.gif"
    frames = [Image.new("RGBA", (4, 2), color) for color in ("red", "blue")]
    frames[0].save(source, save_all=True, append_images=frames[1:], duration=40, loop=0)
    result = format_file(source, tmp_path / "result.gif", FormatOptions(width=2, grid=False, scale=1))
    assert result.frame_count == 2
    with Image.open(result.output_path) as output:
        assert output.n_frames == 2


def test_video_smoke(tmp_path: Path):
    source = tmp_path / "source.mp4"
    writer = imageio.get_writer(source, fps=2, codec="libx264", macro_block_size=1)
    try:
        writer.append_data(np.full((4, 4, 3), (255, 0, 0), dtype=np.uint8))
        writer.append_data(np.full((4, 4, 3), (0, 0, 255), dtype=np.uint8))
    finally:
        writer.close()
    result = format_file(source, tmp_path / "result.mp4", FormatOptions(width=2, grid=False, scale=1))
    assert result.frame_count == 2
    assert result.output_path.stat().st_size > 0
