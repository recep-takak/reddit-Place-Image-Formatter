from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageSequence, UnidentifiedImageError

DEFAULT_PALETTE = np.array(
    [
        (109, 0, 26), (190, 0, 57), (255, 69, 0), (255, 168, 0),
        (255, 214, 53), (255, 248, 184), (0, 163, 104), (0, 204, 120),
        (126, 237, 86), (0, 117, 111), (0, 158, 170), (0, 204, 192),
        (36, 80, 164), (54, 144, 234), (81, 233, 244), (73, 58, 193),
        (106, 92, 255), (148, 179, 255), (129, 30, 159), (180, 74, 192),
        (228, 171, 255), (222, 16, 127), (255, 56, 129), (255, 153, 170),
        (109, 72, 47), (156, 105, 38), (255, 180, 112), (0, 0, 0),
        (81, 82, 82), (137, 141, 144), (212, 215, 217), (255, 255, 255),
    ],
    dtype=np.uint8,
)

IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
ANIMATED_EXTENSIONS = {".gif"}
VIDEO_EXTENSIONS = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | ANIMATED_EXTENSIONS | VIDEO_EXTENSIONS


class FormatterError(ValueError):
    pass


class InvalidInputError(FormatterError):
    pass


class UnsupportedFormatError(FormatterError):
    pass


@dataclass(frozen=True)
class FormatOptions:
    width: int
    grid: bool = True
    scale: int = 10
    max_pixels: int = 20_000_000
    max_frames: int = 300

    def validate(self) -> None:
        if not 1 <= self.width <= 1000:
            raise InvalidInputError("Width must be between 1 and 1000 pixels.")
        if not 1 <= self.scale <= 50:
            raise InvalidInputError("Scale must be between 1 and 50.")
        if self.max_pixels < 1 or self.max_frames < 1:
            raise InvalidInputError("Processing limits must be positive.")


@dataclass(frozen=True)
class FormatResult:
    output_path: Path
    media_type: str
    frame_count: int


def _target_size(image: Image.Image, width: int) -> tuple[int, int]:
    if image.width < 1 or image.height < 1:
        raise InvalidInputError("Image dimensions must be positive.")
    return width, max(1, round(width * image.height / image.width))


def _nearest_palette(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    colors, inverse = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True)
    colors_lab = cv2.cvtColor(colors[np.newaxis, :, :], cv2.COLOR_RGB2LAB)[0].astype(np.int16)
    palette_lab = cv2.cvtColor(palette[np.newaxis, :, :], cv2.COLOR_RGB2LAB)[0].astype(np.int16)
    distances = ((colors_lab[:, None, :] - palette_lab[None, :, :]) ** 2).sum(axis=2)
    return palette[distances.argmin(axis=1)][inverse].reshape(rgb.shape)


def format_image(
    image: Image.Image,
    options: FormatOptions,
    palette: np.ndarray = DEFAULT_PALETTE,
) -> Image.Image:
    options.validate()
    if image.width * image.height > options.max_pixels:
        raise InvalidInputError("Image dimensions exceed the configured pixel limit.")
    if palette.ndim != 2 or palette.shape[1] != 3 or len(palette) < 1:
        raise InvalidInputError("Palette must contain at least one RGB color.")

    rgba = image.convert("RGBA")
    target = _target_size(rgba, options.width)
    reduced = rgba.resize(target, Image.Resampling.LANCZOS)
    pixels = np.asarray(reduced)
    matched = _nearest_palette(pixels[:, :, :3], np.asarray(palette, dtype=np.uint8))
    formatted = Image.fromarray(np.dstack((matched, pixels[:, :, 3])))

    output_size = (target[0] * options.scale, target[1] * options.scale)
    formatted = formatted.resize(output_size, Image.Resampling.NEAREST)
    if options.grid and options.scale > 1:
        draw = ImageDraw.Draw(formatted)
        for x in range(0, output_size[0], options.scale):
            draw.line((x, 0, x, output_size[1]), fill=(0, 0, 0, 255))
        for y in range(0, output_size[1], options.scale):
            draw.line((0, y, output_size[0], y), fill=(0, 0, 0, 255))
    return formatted


def _save_gif(source: Path, destination: Path, options: FormatOptions) -> FormatResult:
    try:
        with Image.open(source) as image:
            frames: list[Image.Image] = []
            durations: list[int] = []
            for index, frame in enumerate(ImageSequence.Iterator(image), start=1):
                if index > options.max_frames:
                    raise InvalidInputError("Animation exceeds the configured frame limit.")
                frames.append(format_image(frame, options))
                durations.append(int(frame.info.get("duration", image.info.get("duration", 100))))
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidInputError("The uploaded GIF could not be decoded.") from exc
    if not frames:
        raise InvalidInputError("The uploaded GIF contains no frames.")
    frames[0].save(
        destination,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
    )
    return FormatResult(destination, "image/gif", len(frames))


def _video_frames(source: Path, max_frames: int) -> Iterable[np.ndarray]:
    try:
        reader = imageio.get_reader(source)
        try:
            for index, frame in enumerate(reader, start=1):
                if index > max_frames:
                    raise InvalidInputError("Video exceeds the configured frame limit.")
                yield frame
        finally:
            reader.close()
    except InvalidInputError:
        raise
    except Exception as exc:
        raise InvalidInputError("The uploaded video could not be decoded.") from exc


def _save_video(source: Path, destination: Path, options: FormatOptions) -> FormatResult:
    try:
        reader = imageio.get_reader(source)
        metadata = reader.get_meta_data()
        reader.close()
        fps = float(metadata.get("fps") or 10)
    except Exception as exc:
        raise InvalidInputError("The uploaded video could not be decoded.") from exc

    writer = imageio.get_writer(destination, fps=max(1.0, fps), codec="libx264", macro_block_size=1)
    count = 0
    try:
        for frame in _video_frames(source, options.max_frames):
            writer.append_data(np.asarray(format_image(Image.fromarray(frame), options).convert("RGB")))
            count += 1
    finally:
        writer.close()
    if count == 0:
        destination.unlink(missing_ok=True)
        raise InvalidInputError("The uploaded video contains no frames.")
    return FormatResult(destination, "video/mp4", count)


def format_file(source: str | Path, destination: str | Path, options: FormatOptions) -> FormatResult:
    source_path = Path(source)
    destination_path = Path(destination)
    options.validate()
    extension = source_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(f"Unsupported file format: {extension or 'none'}.")
    if not source_path.is_file():
        raise InvalidInputError("Input file does not exist.")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    if extension in ANIMATED_EXTENSIONS:
        return _save_gif(source_path, destination_path.with_suffix(".gif"), options)
    if extension in VIDEO_EXTENSIONS:
        return _save_video(source_path, destination_path.with_suffix(".mp4"), options)

    try:
        with Image.open(source_path) as image:
            output = format_image(image, options)
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidInputError("The uploaded image could not be decoded.") from exc
    actual_destination = destination_path.with_suffix(".png")
    output.save(actual_destination, format="PNG")
    return FormatResult(actual_destination, "image/png", 1)
