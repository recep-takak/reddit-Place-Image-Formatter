import io

from PIL import Image

from web import create_app


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (4, 2), "red").save(output, format="PNG")
    return output.getvalue()


def test_health():
    client = create_app({"TESTING": True}).test_client()
    assert client.get("/health").json == {"status": "ok"}


def test_upload_smoke():
    client = create_app({"TESTING": True}).test_client()
    response = client.post(
        "/format",
        data={"file": (io.BytesIO(_png_bytes()), "sample.png"), "width": "2", "scale": "1"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_rejects_spoofed_and_oversized_uploads():
    client = create_app({"TESTING": True, "MAX_CONTENT_LENGTH": 128}).test_client()
    spoofed = client.post(
        "/format",
        data={"file": (io.BytesIO(b"not an image"), "sample.png"), "width": "2"},
        content_type="multipart/form-data",
    )
    assert spoofed.status_code in {400, 413}
    oversized = client.post(
        "/format",
        data={"file": (io.BytesIO(b"x" * 1024), "sample.png"), "width": "2"},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 413
