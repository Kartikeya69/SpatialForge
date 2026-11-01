from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from spatialforge.engine.ingestion.images import PhotoSetPipeline, decode_oriented_image
from spatialforge.engine.ingestion.pipeline import CaptureConfig, create_scene_layout


def _pattern(path: Path, shift: int = 0) -> Path:
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.rectangle(image, (10 + shift, 10), (100 + shift, 90), (20, 180, 240), -1)
    cv2.line(image, (0, 119), (159, 0), (255, 255, 255), 3)
    assert cv2.imwrite(str(path), image)
    return path


def test_decode_applies_exif_orientation(tmp_path: Path) -> None:
    source = tmp_path / "oriented.jpg"
    image = Image.new("RGB", (40, 20), "red")
    exif = Image.Exif()
    exif[274] = 6
    image.save(source, exif=exif)
    decoded = decode_oriented_image(source)
    assert decoded.shape[:2] == (40, 20)


def test_photo_set_creates_colmap_ready_manifest(tmp_path: Path) -> None:
    sources = [_pattern(tmp_path / f"photo-{index}.jpg", index * 8) for index in range(3)]
    _, scene = create_scene_layout(tmp_path / "datasets", "scene_photos")
    config = CaptureConfig(min_width=80, min_height=60, enable_blur_filter=False, enable_duplicate_filter=False)
    manifest = PhotoSetPipeline(config).process(sources, scene)
    assert manifest["capture_mode"] == "photo_set"
    assert manifest["accepted_frames"] == 3
    assert all((scene / record["path"]).is_file() for record in manifest["images"])


def test_photo_set_rejects_duplicates(tmp_path: Path) -> None:
    first = _pattern(tmp_path / "first.jpg")
    second = tmp_path / "second.jpg"
    second.write_bytes(first.read_bytes())
    _, scene = create_scene_layout(tmp_path / "datasets", "scene_duplicates")
    config = CaptureConfig(min_width=80, min_height=60, enable_blur_filter=False, duplicate_threshold=0.999)
    manifest = PhotoSetPipeline(config).process([first, second], scene)
    assert manifest["accepted_frames"] == 1
    assert manifest["rejection_reasons"] == {"near_duplicate": 1}

