"""Page pre-processing: upright, straight, evened out, with boxes that map back to the original."""

import io
import random
from datetime import date

import numpy as np
import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw

from citetally.models import Word
from citetally.reading import preprocess
from tools.synthetic.degrade import CONDITIONS, make_file
from tools.synthetic.docgen import generate
from tools.synthetic.facts import load_facts
from tools.synthetic.families import FAMILIES
from tools.synthetic.render import business_block, render_pdf


@pytest.fixture(scope="module")
def pdf() -> bytes:
    facts = load_facts()
    family = FAMILIES[0]
    vendor = next(v for v in facts.vendors if v.id == "V01")
    doc = generate(random.Random(4), facts, vendor, "d-4", date(2026, 5, 20), 4, family.style)
    return render_pdf(doc, family, business_block(facts))


@pytest.fixture(scope="module")
def page(pdf: bytes) -> Image.Image:
    image: Image.Image = pdfium.PdfDocument(pdf)[0].render(scale=200 / 72).to_pil().convert("RGB")
    return image


def turned(image: Image.Image, degrees: float) -> Image.Image:
    return image.rotate(
        degrees, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255)
    )


def test_the_working_size_keeps_the_shape_and_is_grey() -> None:
    for size in [(600, 800), (1700, 2200), (3000, 4000), (4000, 3000)]:
        out = preprocess.to_working_size(Image.new("RGB", size, "white"))
        assert out.mode == "L"
        assert preprocess.WORKING_MIN_LONG_SIDE <= max(out.size) <= preprocess.WORKING_MAX_LONG_SIDE
        assert abs(out.width / out.height - size[0] / size[1]) < 0.01


def test_a_page_that_is_already_in_range_is_not_resampled() -> None:
    image = Image.new("L", (1700, 2200), 255)
    assert preprocess.to_working_size(image).size == (1700, 2200)


def test_a_shadow_across_the_paper_is_evened_out() -> None:
    ramp = np.tile(np.linspace(250, 120, 1700), (2200, 1))
    shaded = Image.fromarray(ramp.astype(np.uint8), "L")
    flat = np.asarray(preprocess.flatten_light(shaded), dtype=float)
    assert np.asarray(shaded, dtype=float).std() > 35
    assert flat.std() < 6
    assert flat.mean() > 240


def test_text_survives_flattening(page: Image.Image) -> None:
    flat = preprocess.flatten_light(preprocess.to_working_size(page))
    data = np.asarray(flat)
    assert (data < 100).mean() > 0.01  # ink is still dark
    assert np.median(data) >= 250  # paper is white


def test_low_contrast_is_stretched_and_a_blank_page_is_left_alone() -> None:
    rng = np.random.default_rng(1)
    base = np.full((300, 300), 200.0)
    base[rng.random((300, 300)) < 0.05] = 140.0  # faint ink
    faint = Image.fromarray(base.astype(np.uint8), "L")
    stretched = np.asarray(preprocess.stretch_contrast(faint))
    assert stretched.min() <= 5 and np.median(stretched) >= 250
    blank = Image.new("L", (300, 300), 200)
    assert (np.asarray(preprocess.stretch_contrast(blank)) == 200).all()


def test_speckle_is_removed_but_a_stroke_is_kept() -> None:
    data = np.full((60, 60), 255, dtype=np.uint8)
    data[10, 10] = 0  # a lone dark speck
    data[30:33, 5:55] = 0  # a three-pixel stroke
    out = np.asarray(preprocess.remove_speckle(Image.fromarray(data, "L")))
    assert out[10, 10] == 255
    assert out[31, 30] == 0


def test_an_upright_straight_page_is_not_turned(page: Image.Image) -> None:
    pre = preprocess.preprocess(page)
    assert pre.image.mode == "L"
    assert abs(pre.skew_degrees) < 0.2
    assert pre.quarter_turns == 0
    assert all(abs(t.degrees) < 0.2 for t in pre.turns)


@pytest.mark.parametrize("tilt", [-4.0, -1.5, 0.8, 3.0, 6.0])
def test_tilt_is_measured_and_removed(page: Image.Image, tilt: float) -> None:
    pre = preprocess.preprocess(turned(page, tilt))  # Pillow turns counter-clockwise: rises
    assert pre.skew_degrees == pytest.approx(tilt, abs=0.3)
    ink = preprocess._ink_image(pre.image, Image.new("L", pre.image.size, 255))
    assert abs(preprocess.measure_tilt(ink)) < 0.3  # the cleaned page is level


@pytest.mark.parametrize("quarter_turns", [1, 2, 3])
def test_a_page_turned_by_quarter_turns_comes_back_upright(
    page: Image.Image, quarter_turns: int
) -> None:
    pre = preprocess.preprocess(turned(page, 90 * quarter_turns))
    assert (pre.quarter_turns + quarter_turns) % 4 == 0
    assert abs(pre.skew_degrees) < 0.3


def test_a_sideways_page_that_is_also_tilted_comes_back_upright(page: Image.Image) -> None:
    pre = preprocess.preprocess(turned(page, 90 + 3.0))
    assert (pre.quarter_turns + 1) % 4 == 0


def test_a_blank_page_is_left_alone() -> None:
    pre = preprocess.preprocess(Image.new("RGB", (1700, 2200), "white"))
    assert pre.turns == ()
    assert pre.skew_degrees == 0


@pytest.mark.parametrize("condition", CONDITIONS)
def test_every_condition_gives_a_grey_page_in_working_size(pdf: bytes, condition: str) -> None:
    data, _ = make_file(pdf, condition, seed=7)
    if data[:4] == b"%PDF":
        image = pdfium.PdfDocument(data)[0].render(scale=200 / 72).to_pil()
    else:
        image = Image.open(io.BytesIO(data))
    pre = preprocess.preprocess(image.convert("RGB"))
    assert pre.image.mode == "L"
    assert (
        preprocess.WORKING_MIN_LONG_SIDE
        <= max(pre.image.size)
        <= 1.3 * preprocess.WORKING_MAX_LONG_SIDE
    )
    assert abs(pre.skew_degrees) <= preprocess.MAX_TILT_DEGREES
    assert pre.quarter_turns == 0


def test_the_same_page_gives_the_same_result(page: Image.Image) -> None:
    first = preprocess.preprocess(turned(page, 2.0))
    second = preprocess.preprocess(turned(page, 2.0))
    assert first.image.tobytes() == second.image.tobytes()
    assert first.skew_degrees == second.skew_degrees


def square_page() -> tuple[Image.Image, tuple[float, float]]:
    """A white page with one black square in a known place, and that place as fractions."""
    image = Image.new("L", (800, 1000), 255)
    ImageDraw.Draw(image).rectangle((560, 140, 600, 180), fill=0)
    return image, (580 / 800, 160 / 1000)


def where_is_the_square(image: Image.Image) -> tuple[float, float]:
    ys, xs = np.nonzero(np.asarray(image) < 128)
    return float(xs.mean()) / image.width, float(ys.mean()) / image.height


@pytest.mark.parametrize("degrees", [[90], [180], [270], [3.5], [-7.25], [90, 2.0], [2.0, 180]])
def test_a_point_on_the_cleaned_image_maps_back_to_the_original(degrees: list[float]) -> None:
    original, expected = square_page()
    image, turns = original, []
    for angle in degrees:
        image, turn = preprocess._rotate(image, angle, 255)
        turns.append(turn)
    pre = preprocess.Preprocessed(image=image, skew_degrees=0.0, turns=tuple(turns))
    x, y = pre.point_on_original(*where_is_the_square(image))
    assert abs(x - expected[0]) * original.width < 2
    assert abs(y - expected[1]) * original.height < 2


def test_a_word_box_maps_back_with_its_text_and_stays_on_the_page() -> None:
    original, _ = square_page()
    rotated, turn = preprocess._rotate(original, 4.0, 255)
    pre = preprocess.Preprocessed(image=rotated, skew_degrees=0.0, turns=(turn,))
    word = Word(t="Total", x0=0.0, y0=0.0, x1=1.0, y1=1.0, c=91.0)
    (back,) = preprocess.preprocess_words(pre, [word])
    assert (back.t, back.c) == ("Total", 91.0)
    assert 0 <= back.x0 <= back.x1 <= 1 and 0 <= back.y0 <= back.y1 <= 1
    sideways = preprocess.Preprocessed(
        image=original, skew_degrees=0.0, turns=(preprocess._rotate(original, 90, 255)[1],)
    )
    narrow = Word(t="x", x0=0.1, y0=0.2, x1=0.3, y1=0.25, c=None)
    box = sideways.word_on_original(narrow)
    assert (box.x1 - box.x0) < (box.y1 - box.y0)  # a wide word was lying on its side
