"""Degradation: clean PDFs become light scans, heavy scans and phone photos, from a seed."""

import io
import random
from datetime import date

import numpy as np
import pypdfium2 as pdfium
import pytest
from PIL import Image

from tools.synthetic.degrade import CONDITIONS, make_file, rasterize
from tools.synthetic.docgen import generate
from tools.synthetic.facts import load_facts
from tools.synthetic.families import FAMILIES
from tools.synthetic.render import business_block, render_pdf


@pytest.fixture(scope="module")
def clean_pdf() -> bytes:
    facts = load_facts()
    family = FAMILIES[0]
    vendor = next(v for v in facts.vendors if v.id == "V01")
    doc = generate(random.Random(4), facts, vendor, "d-4", date(2026, 5, 20), 4, family.style)
    return render_pdf(doc, family, business_block(facts))


def pixels(data: bytes, extension: str) -> np.ndarray:
    if extension == "pdf":
        image = pdfium.PdfDocument(data)[0].render(scale=1.0).to_pil()
    else:
        image = Image.open(io.BytesIO(data))
    return np.asarray(image.convert("L"), dtype=float)


def test_the_four_conditions_are_named_in_the_docs() -> None:
    assert CONDITIONS == ("clean_pdf", "scan_light", "scan_heavy", "phone_photo")


def test_clean_pdf_is_returned_unchanged(clean_pdf: bytes) -> None:
    data, extension = make_file(clean_pdf, "clean_pdf", seed=1)
    assert (data, extension) == (clean_pdf, "pdf")


@pytest.mark.parametrize("condition", ["scan_light", "scan_heavy", "phone_photo"])
def test_degrading_is_deterministic_from_the_seed(clean_pdf: bytes, condition: str) -> None:
    first, ext = make_file(clean_pdf, condition, seed=11)
    again, _ = make_file(clean_pdf, condition, seed=11)
    other, _ = make_file(clean_pdf, condition, seed=12)
    assert first == again
    assert first != other
    assert ext in {"pdf", "jpg"}


@pytest.mark.parametrize("condition", ["scan_light", "scan_heavy"])
def test_scans_are_image_only_pdfs_with_no_text_layer(clean_pdf: bytes, condition: str) -> None:
    data, extension = make_file(clean_pdf, condition, seed=2)
    assert extension == "pdf" and data.startswith(b"%PDF")
    document = pdfium.PdfDocument(data)
    assert len(document) == 1
    assert document[0].get_textpage().get_text_range().strip() == ""


def test_phone_photo_is_a_jpeg_of_phone_size(clean_pdf: bytes) -> None:
    data, extension = make_file(clean_pdf, "phone_photo", seed=2)
    assert extension == "jpg"
    image = Image.open(io.BytesIO(data))
    assert image.format == "JPEG" and 1000 <= max(image.size) <= 2200


def test_heavy_scans_are_worse_than_light_scans(clean_pdf: bytes) -> None:
    light = pixels(*make_file(clean_pdf, "scan_light", seed=5))
    heavy = pixels(*make_file(clean_pdf, "scan_heavy", seed=5))

    def sharpness(a: np.ndarray) -> float:
        return float(np.var(np.diff(a, axis=1)))

    assert sharpness(heavy) < sharpness(light)
    assert np.percentile(heavy, 95) < np.percentile(light, 95) - 10  # paper is no longer white


def test_phone_photos_include_a_background_around_the_page(clean_pdf: bytes) -> None:
    clean = pixels(clean_pdf, "pdf")
    photo = pixels(*make_file(clean_pdf, "phone_photo", seed=3))
    assert photo.mean() < clean.mean() - 8  # darker: desk, shadows, vignette


def test_held_out_degradations_are_a_different_family_of_damage(clean_pdf: bytes) -> None:
    tuned = make_file(clean_pdf, "scan_heavy", seed=5, profile="tuned")[0]
    held = make_file(clean_pdf, "scan_heavy", seed=5, profile="heldout")[0]
    assert tuned != held
    photo_tuned = make_file(clean_pdf, "phone_photo", seed=5, profile="tuned")[0]
    photo_held = make_file(clean_pdf, "phone_photo", seed=5, profile="heldout")[0]
    assert photo_tuned != photo_held


def test_unknown_condition_or_profile_is_an_error(clean_pdf: bytes) -> None:
    with pytest.raises(ValueError, match="condition"):
        make_file(clean_pdf, "blurry", seed=1)
    with pytest.raises(ValueError, match="profile"):
        make_file(clean_pdf, "scan_light", seed=1, profile="secret")


def test_rasterize_gives_a_page_image_at_the_requested_resolution(clean_pdf: bytes) -> None:
    image = rasterize(clean_pdf, dpi=100)
    assert image.mode == "RGB"
    assert abs(image.width - 612 * 100 / 72) <= 2
