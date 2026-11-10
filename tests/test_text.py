import re
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from cysuml import text as T

SRC = Path(T.__file__).parent


def code_lines():
    for p in SRC.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            yield f"{p.name}:{i}", line


def test_code_has_no_os_font_paths():
    os_path = re.compile(r"/System/Library|/Library/Fonts|/usr/(local/)?share/fonts|\.fonts/|Windows[\\/]+Fonts", re.I)
    assert [where for where, line in code_lines() if os_path.search(line)] == []


def test_code_names_only_bundled_font_files():
    bundled = {p.name for p in T.FONT_DIR.iterdir()}
    named = {name for _, line in code_lines() for name in re.findall(r"[\w.-]+\.(?:ttf|otf|ttc)\b", line, re.I)}
    assert named and named <= bundled


def test_fonts_come_from_the_package():
    for korean in (False, True):
        for bold in (False, True):
            path = Path(T.font(korean, bold, T.SIZE).path)
            assert path.parent == T.FONT_DIR and path.is_file()
    assert (T.FONT_DIR / "LiberationSans-LICENSE.txt").is_file()
    assert (T.FONT_DIR / "NotoSansKR-LICENSE.txt").is_file()


@pytest.mark.parametrize("ch", ["가", "힣", "ㄱ", "ᄀ", "漢", "。", "（", "㈜", "※", "①", "★", "◆", "⇒", "℃", "✓"])
def test_characters_missing_from_liberation_use_noto(ch):
    assert T.is_korean(ch)
    assert ord(ch) in TTFont(str(T.FONT_DIR / "NotoSansKR-Regular.otf"), lazy=True).getBestCmap()


@pytest.mark.parametrize("ch", ["A", "z", "0", " ", "«", "»", "·", "…", "→", "é", "_"])
def test_latin_font_characters(ch):
    assert not T.is_korean(ch)


def test_regular_and_bold_cover_the_same_characters():
    for regular, bold in (("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
                          ("NotoSansKR-Regular.otf", "NotoSansKR-Bold.otf")):
        a = TTFont(str(T.FONT_DIR / regular), lazy=True).getBestCmap()
        b = TTFont(str(T.FONT_DIR / bold), lazy=True).getBestCmap()
        assert set(a) == set(b)


def test_split_runs():
    assert T.split_runs("Order 주문 #1") == [("Order ", False), ("주문", True), (" #1", False)]
    assert T.split_runs("회원") == [("회원", True)]
    assert T.split_runs("") == []


# 글꼴 파일이나 재는 방법이 바뀌면 이 값이 바뀐다 — 바꿀 때는 그린 그림을 다시 확인한다.
@pytest.mark.parametrize("s, bold, width", [
    ("Order", False, 33.234375),
    ("Order", True, 35.40625),
    ("주문", False, 23.90625),
    ("주문", True, 23.90625),
    ("Order 주문", False, 60.75),
    ("회원 Member", False, 75.203125),
    ("«interface»", False, 64.34375),
    ("0..*", False, 19.515625),
    ("※ 참고 ①", False, 57.125),
])
def test_width_is_fixed(s, bold, width):
    assert T.text_width(s, bold) == pytest.approx(width, abs=0.02)


def test_mixed_width_is_sum_of_runs():
    assert T.text_width("Order 주문") == pytest.approx(T.text_width("Order ") + T.text_width("주문"))
    assert T.text_width("A가B", True) == pytest.approx(T.text_width("A", True) + T.text_width("가", True) + T.text_width("B", True))


def test_place_left_and_middle_anchor():
    w = T.text_width("Order 주문")
    left = T.place(10, 20, "Order 주문")
    mid = T.place(10, 20, "Order 주문", anchor="mm")
    assert left.box[0] == 10 and left.box[2] == pytest.approx(10 + w)
    assert mid.box[0] == pytest.approx(10 - w / 2) and mid.box[2] == pytest.approx(10 + w / 2)
    for p in (left, mid):
        assert (p.box[1] + p.box[3]) / 2 == pytest.approx(20)
        assert p.box[3] - p.box[1] == pytest.approx(T.ASCENT + T.DESCENT)
        assert p.box[1] < p.baseline < p.box[3]


def test_glyphs_are_placed_one_by_one_across_fonts():
    p = T.place(5, 0, "Order 주문 Item")
    assert "".join(ch for _, ch, _ in p.glyphs) == "Order 주문 Item"
    xs = {i: x for i, (x, _, _) in enumerate(p.glyphs)}
    assert xs[0] == 5
    assert xs[6] == pytest.approx(5 + T.text_width("Order ")) and p.glyphs[6][2]
    assert xs[8] == pytest.approx(5 + T.text_width("Order 주문")) and not p.glyphs[8][2]
    assert list(xs.values()) == sorted(xs.values())
    last_x, last, _ = p.glyphs[-1]
    assert last_x + T.text_width(last) == pytest.approx(p.box[2])


def test_glyph_positions_keep_kerning():
    p = T.place(0, 0, "AV")
    assert T.text_width("AV") < T.text_width("A") + T.text_width("V")
    assert p.glyphs[1][0] == pytest.approx(T.text_width("AV") - T.text_width("V"))


def test_ink_of_mixed_text_stays_in_line_box():
    p = T.place(0, 0, "Order 주문 gy", bold=True)
    l, t, r, b = p.ink
    assert p.box[0] <= l < r <= p.box[2] + 0.5
    assert p.box[1] <= t < p.baseline < b <= p.box[3]


def test_blank_text_has_no_ink():
    assert T.place(0, 0, "   ").ink is None
    assert T.place(0, 0, "").ink is None


def test_place_rejects_unknown_anchor_and_newline():
    with pytest.raises(ValueError):
        T.place(0, 0, "x", anchor="ls")
    with pytest.raises(ValueError):
        T.place(0, 0, "a\nb")
