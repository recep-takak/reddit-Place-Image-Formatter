from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from flask import Flask, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from formatter import FormatOptions, InvalidInputError, UnsupportedFormatError, format_file
from formatter.core import SUPPORTED_EXTENSIONS

DEFAULT_MAX_UPLOAD_MB = 16


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=_positive_int("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB) * 1024 * 1024,
        FORMATTER_MAX_PIXELS=_positive_int("MAX_IMAGE_PIXELS", 20_000_000),
        FORMATTER_MAX_FRAMES=_positive_int("MAX_MEDIA_FRAMES", 300),
    )
    if test_config:
        app.config.update(test_config)

    @app.get("/")
    def index():
        formats = ", ".join(sorted(extension.removeprefix(".") for extension in SUPPORTED_EXTENSIONS))
        return render_template("index.html", formats=formats)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/format")
    def format_upload():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return render_template("index.html", error="Choose a file to format."), 400
        filename = secure_filename(upload.filename)
        extension = Path(filename).suffix.lower()
        if not filename or extension not in SUPPORTED_EXTENSIONS:
            return render_template("index.html", error="That file type is not supported."), 415
        try:
            width = int(request.form.get("width", ""))
            scale = int(request.form.get("scale", "10"))
        except ValueError:
            return render_template("index.html", error="Width and scale must be numbers."), 400

        options = FormatOptions(
            width=width,
            grid=request.form.get("grid") == "on",
            scale=scale,
            max_pixels=app.config["FORMATTER_MAX_PIXELS"],
            max_frames=app.config["FORMATTER_MAX_FRAMES"],
        )
        try:
            options.validate()
            with tempfile.TemporaryDirectory(prefix="place-formatter-") as temp_dir:
                source = Path(temp_dir) / filename
                destination = Path(temp_dir) / f"pixel_{Path(filename).stem}{extension}"
                upload.save(source)
                result = format_file(source, destination, options)
                payload = result.output_path.read_bytes()
                download_name = result.output_path.name
        except (InvalidInputError, UnsupportedFormatError) as exc:
            return render_template("index.html", error=str(exc)), 400
        return send_file(
            io.BytesIO(payload),
            mimetype=result.media_type,
            as_attachment=True,
            download_name=download_name,
        )

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return render_template("index.html", error=f"Upload exceeds the {limit_mb} MB limit."), 413

    return app


app = create_app()
