"""OCR wrapper: Tesseract output parsing, the command it runs, its failures, and the fake."""

import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from PIL import Image

from citetally.models import Word
from citetally.reading import layout, ocr

FIXTURE = Path(__file__).parent / "fixtures" / "tesseract_clean_1700x2200.tsv"
HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


def row(
    text: str, left: int = 100, top: int = 200, width: int = 300, height: int = 40, conf: str = "96"
) -> str:
    return f"5\t1\t1\t1\t1\t1\t{left}\t{top}\t{width}\t{height}\t{conf}\t{text}"


def tsv(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def test_a_word_row_becomes_a_word_with_a_box_as_fractions_of_the_image() -> None:
    page = ocr.parse_tsv(tsv(row("Total", 170, 440, 340, 110, "91.5")), 1700, 2200)
    (word,) = page.words
    assert word.t == "Total" and word.c == 91.5
    assert (word.x0, word.y0, word.x1, word.y1) == pytest.approx((0.1, 0.2, 0.3, 0.25))
    assert page.mean_confidence == 91.5


def test_rows_that_are_not_words_are_ignored() -> None:
    rows = [
        "1\t1\t0\t0\t0\t0\t0\t0\t1700\t2200\t-1\t",
        "2\t1\t1\t0\t0\t0\t90\t90\t900\t90\t-1\t",
        "4\t1\t1\t1\t1\t0\t90\t90\t900\t40\t-1\t",
        row("kept"),
        row("   ", conf="95"),  # blank text
        row("noconf", conf="-1"),
        row("flat", width=0),
        "5\t1\t1\t1\t1\t1\t1\t2\tx\t4\t90\tgarbled",
        "5\t1\t1\t1\t1\t1\t1\t2",  # too short to be a row
    ]
    page = ocr.parse_tsv(tsv(*rows), 1700, 2200)
    assert [w.t for w in page.words] == ["kept"]


def test_no_words_means_no_confidence() -> None:
    assert ocr.parse_tsv("", 100, 100) == ocr.OcrPage(words=[], mean_confidence=None)
    assert ocr.parse_tsv(HEADER + "\n", 100, 100).mean_confidence is None


def test_mean_confidence_is_the_average_over_words() -> None:
    page = ocr.parse_tsv(tsv(row("a", conf="100"), row("b", conf="50")), 1700, 2200)
    assert page.mean_confidence == 75.0


def test_boxes_that_run_past_the_image_are_clamped() -> None:
    page = ocr.parse_tsv(tsv(row("edge", left=1650, top=2180, width=200, height=100)), 1700, 2200)
    word = page.words[0]
    assert (word.x1, word.y1) == (1.0, 1.0)


def test_text_with_a_tab_in_it_is_kept_whole() -> None:
    page = ocr.parse_tsv(tsv(row("a\tb")), 1700, 2200)
    assert page.words[0].t == "a\tb"  # layout.clean_token collapses it later


def test_a_recorded_tesseract_output_is_read_and_its_text_survives_into_the_layout() -> None:
    page = ocr.parse_tsv(FIXTURE.read_text(encoding="utf-8"), 1700, 2200)
    assert len(page.words) > 80
    assert page.mean_confidence is not None and page.mean_confidence > 80
    for word in page.words:
        assert 0 <= word.x0 < word.x1 <= 1 and 0 <= word.y0 < word.y1 <= 1
    text = re.sub(r"\s+", " ", layout.build_text(page.words))
    assert "MILLRACE PLUMBING SUPPLY CO" in text
    assert "billing@millraceplumbing.example.com" in text


class Recorder:
    def __init__(self, output: str = "") -> None:
        self.output = output
        self.calls: list[tuple[list[str], float]] = []
        self.image_seen: tuple[int, int] | None = None

    def __call__(self, args: Sequence[str], timeout_s: float) -> str:
        self.calls.append((list(args), timeout_s))
        image = Path(args[1])
        assert image.exists()  # the page is on disk while Tesseract runs
        with Image.open(image) as opened:
            self.image_seen = opened.size
        return self.output


@pytest.fixture
def fake_exe(tmp_path: Path) -> str:
    exe = tmp_path / "tesseract.exe"
    exe.write_bytes(b"")
    return str(exe)


def test_the_command_reads_english_as_tsv_and_the_page_file_is_removed_afterwards(
    fake_exe: str,
) -> None:
    runner = Recorder(tsv(row("ok")))
    engine = ocr.TesseractOcr(fake_exe, psm=6, dpi=250, timeout_s=33, runner=runner)
    page = engine.read_page(Image.new("RGB", (120, 80), "white"))
    ((args, timeout),) = runner.calls
    assert args[0] == fake_exe and args[2] == "stdout" and args[-1] == "tsv"
    assert args[args.index("-l") + 1] == "eng"
    assert args[args.index("--psm") + 1] == "6"
    assert args[args.index("--dpi") + 1] == "250"
    assert timeout == 33
    assert runner.image_seen == (120, 80)
    assert not Path(args[1]).exists()
    assert [w.t for w in page.words] == ["ok"]


def test_the_file_is_removed_even_when_the_run_fails(fake_exe: str) -> None:
    seen: list[str] = []

    def failing(args: Sequence[str], timeout_s: float) -> str:
        seen.append(args[1])
        raise ocr.OcrError("Tesseract failed (exit code 1).")

    engine = ocr.TesseractOcr(fake_exe, runner=failing)
    with pytest.raises(ocr.OcrError):
        engine.read_page(Image.new("L", (50, 50), 255))
    assert not Path(seen[0]).exists()


def test_a_missing_program_is_reported_as_unavailable(tmp_path: Path) -> None:
    engine = ocr.TesseractOcr(str(tmp_path / "nope.exe"), runner=Recorder())
    with pytest.raises(ocr.OcrUnavailable, match="not found"):
        engine.read_page(Image.new("L", (50, 50), 255))


def test_unavailable_is_a_kind_of_ocr_error() -> None:
    assert issubclass(ocr.OcrUnavailable, ocr.OcrError)


def test_the_real_runner_reports_failures_without_any_output(tmp_path: Path) -> None:
    with pytest.raises(ocr.OcrUnavailable):
        ocr._run([str(tmp_path / "missing-program.exe")], 5)


def test_find_tesseract_prefers_the_configured_path(fake_exe: str) -> None:
    assert ocr.find_tesseract(fake_exe) == fake_exe
    assert ocr.find_tesseract(fake_exe + ".nothere") is None


def test_the_fake_returns_its_pages_in_turn_then_repeats_the_last() -> None:
    first, second = ocr.fake_page(["one"]), ocr.fake_page(["two"])
    engine = ocr.FakeOcr([first, second])
    image = Image.new("L", (30, 40))
    assert [engine.read_page(image) for _ in range(3)] == [first, second, second]
    assert engine.calls == [(30, 40)] * 3
    assert engine.name == "fake"


def test_an_unprepared_fake_finds_nothing_and_a_failing_fake_raises() -> None:
    image = Image.new("L", (10, 10))
    assert ocr.FakeOcr().read_page(image).words == []
    with pytest.raises(ocr.OcrUnavailable):
        ocr.FakeOcr(error=ocr.OcrUnavailable("Tesseract was not found.")).read_page(image)


def test_fake_pages_lay_out_back_into_the_lines_they_came_from() -> None:
    lines = ["Description Qty Amount", "Wax ring 2 $10.80", "Total $10.80"]
    page = ocr.fake_page(lines, confidence=88)
    assert page.mean_confidence == 88
    assert all(isinstance(w, Word) for w in page.words)
    assert [line.split() for line in layout.build_text(page.words).splitlines()] == [
        line.split() for line in lines
    ]


@pytest.mark.skipif(ocr.find_tesseract() is None, reason="Tesseract is not installed")
def test_the_real_program_reads_printed_words_on_a_plain_page() -> None:
    """A wrapper check only (the program starts, output parses). How well it reads is measured."""
    from PIL import ImageDraw, ImageFont

    image = Image.new("L", (900, 200), 255)
    font = ImageFont.load_default(size=48)
    ImageDraw.Draw(image).text((30, 60), "Total due 649.92", fill=0, font=font)
    page = ocr.TesseractOcr().read_page(image)
    assert {"Total", "due"} <= {w.t for w in page.words}
    assert page.mean_confidence is not None and page.mean_confidence > 50
