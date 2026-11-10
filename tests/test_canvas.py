import math

import pytest
from PIL import Image

from cysuml import text as T
from cysuml.canvas import PAD, SS, Canvas, Ellipse, Line, Mask, Polygon, Rect, Text


def draw_sample(scale):
    c = Canvas((0, 0, 300, 200), scale)
    c.rect(20, 20, 100, 60, owner="Order")
    c.line([(120, 50), (200, 50), (200, 120)], owner="Order->Customer")
    c.line([(20, 150), (120, 150)], dash=(5, 4))
    c.closed_arrow((200, 120), (200, 50), owner="Order->Customer")
    c.diamond((120, 50), (200, 50), filled=False)
    c.open_arrow((120, 150), (20, 150))
    c.ellipse(240, 20, 12, 12)
    c.text(70, 35, "주문 Order", bold=True, anchor="mm", owner="Order")
    c.text(150, 40, "0..*", anchor="mm", bg=True)
    c.erase(60, 145, 70, 155)
    return c


def flat(points):
    return [v for p in points for v in p]


def test_shapes_are_recorded_in_logical_coordinates():
    rec = draw_sample(1.6).records
    assert rec[0] == Rect(20, 20, 100, 60, "white", "Order")
    assert rec[1] == Line(((120.0, 50.0), (200.0, 50.0), (200.0, 120.0)), None, "Order->Customer")
    assert rec[2] == Line(((20.0, 150.0), (120.0, 150.0)), (5.0, 4.0))
    arrow = rec[3]
    assert isinstance(arrow, Polygon) and arrow.fill == "black" and arrow.owner == "Order->Customer"
    assert flat(arrow.points) == pytest.approx(flat([(200, 120), (204.5, 110), (195.5, 110)]))
    diamond = rec[4]
    assert isinstance(diamond, Polygon) and diamond.fill == "white"
    assert flat(diamond.points) == pytest.approx(flat([(120, 50), (129, 56), (138, 50), (129, 44)]))
    heads = rec[5:7]
    assert all(isinstance(h, Line) and h.points[0] == (120, 150) for h in heads)
    assert all(math.dist(*h.points) == pytest.approx(10) for h in heads)
    assert rec[7] == Ellipse(240, 20, 12, 12)
    assert rec[-1] == Mask(60, 145, 70, 155)


def test_text_is_recorded_with_its_line_box():
    rec = [r for r in draw_sample(1.6).records if isinstance(r, Text)]
    assert [r.text for r in rec] == ["주문 Order", "0..*"]
    assert rec[0].box == T.place(70, 35, "주문 Order", True, "mm").box
    assert rec[0].bold and rec[0].owner == "Order" and not rec[0].bg


def test_bg_text_leaves_a_mask_around_its_ink():
    rec = draw_sample(1.6).records
    i = next(i for i, r in enumerate(rec) if isinstance(r, Text) and r.bg)
    mask = rec[i - 1]
    assert isinstance(mask, Mask)
    l, t, r, b = T.place(150, 40, "0..*", anchor="mm").ink
    assert (mask.left, mask.top, mask.right, mask.bottom) == pytest.approx((l - 2, t - 2, r + 2, b + 2))


def test_records_do_not_depend_on_scale():
    assert draw_sample(1.6).records == draw_sample(0.5).records


def pixel(c, x, y):
    return c.img.getpixel((round((x - c.minx) * c.k), round((y - c.miny) * c.k)))


def test_diamond_and_arrow_fill():
    c = Canvas((0, 0, 100, 100))
    c.diamond((10, 20), (90, 20), filled=True)
    c.diamond((10, 60), (90, 60), filled=False)
    c.closed_arrow((90, 80), (10, 80), filled=False, size=18, half=9)
    assert pixel(c, 19, 20) == 0
    assert pixel(c, 19, 60) == 255
    assert pixel(c, 84, 80) == 255
    assert pixel(c, 72, 80) == 0


def test_dashed_line_has_gaps():
    c = Canvas((0, 0, 100, 20))
    c.line([(0, 10), (100, 10)], dash=(5, 4))
    assert pixel(c, 2, 10) == 0 and pixel(c, 7, 10) == 255 and pixel(c, 11, 10) == 0


def test_bg_text_erases_the_line_under_it():
    c = Canvas((0, 0, 200, 40))
    c.line([(0, 20), (200, 20)])
    c.text(100, 20, "선 위 label", anchor="mm", bg=True)
    l, _, r, _ = T.place(100, 20, "선 위 label", anchor="mm").ink
    assert pixel(c, l - 1, 20) == 255 and pixel(c, r + 1, 20) == 255
    assert pixel(c, l - 5, 20) == 0


def drawn_extent(c):
    l, _, r, _ = c.img.point(lambda p: 255 if p < 128 else 0).getbbox()
    return l / c.k + c.minx, r / c.k + c.minx


@pytest.mark.parametrize("s", ["registerMemberAccountWithVerificationCode()", "회원가입요청을처리한다 longName", "※ 참고 ① Item"])
def test_drawn_text_matches_its_record_at_any_scale(s):
    extents = []
    for scale in (0.5, 1.6, 3.0):
        c = Canvas((0, 0, 400, 40), scale)
        c.text(10, 20, s)
        extents.append(drawn_extent(c))
        box = c.records[-1].box
        assert box[0] - 0.5 <= extents[-1][0] and extents[-1][1] <= box[2] + 0.5
    lefts, rights = [e[0] for e in extents], [e[1] for e in extents]
    assert max(lefts) - min(lefts) < 0.5 and max(rights) - min(rights) < 0.5


def render_text(s):
    c = Canvas((0, 0, 60, 30))
    c.text(5, 15, s)
    return c.to_image()


def test_korean_is_drawn_with_real_glyphs():
    a, b = render_text("가"), render_text("나")
    assert a.tobytes() != b.tobytes()  # 글꼴에 없는 글자면 둘 다 같은 빈 네모로 그려진다
    assert render_text("A").tobytes() != render_text("B").tobytes()


def test_output_is_scaled_and_cropped_around_the_drawing(tmp_path):
    c = Canvas((0, 0, 1000, 800))
    c.rect(100, 100, 50, 30)
    size = c.save(tmp_path / "out.png")
    margin = round(PAD * 1.6)
    assert size[0] == pytest.approx(50 * 1.6 + 2 * margin, abs=3)
    assert size[1] == pytest.approx(30 * 1.6 + 2 * margin, abs=3)
    with Image.open(tmp_path / "out.png") as img:
        assert img.format == "PNG" and img.size == size
        assert img.getextrema()[0] < 50  # 검은 선이 실제로 남았다


def test_supersampled_canvas_size():
    c = Canvas((10, 20, 110, 70), 1.6)
    assert c.img.size == (math.ceil(100 * 1.6 * SS), math.ceil(50 * 1.6 * SS))


def test_invalid_input_is_rejected():
    with pytest.raises(ValueError):
        Canvas((0, 0, 0, 10))
    with pytest.raises(ValueError):
        Canvas((0, 0, 10, 10), 0)
    c = Canvas((0, 0, 10, 10))
    with pytest.raises(ValueError):
        c.line([(0, 0)])
    with pytest.raises(ValueError):
        c.line([(0, 0), (5, 5)], dash=(0, 3))
    with pytest.raises(ValueError):
        c.poly([(0, 0), (5, 5)])
    with pytest.raises(ValueError):
        c.text(0, 0, "a", anchor="rs")
    with pytest.raises(ValueError):
        c.rect(5, 5, -1, 2)
    with pytest.raises(ValueError):
        c.ellipse(5, 5, 2, -1)
    with pytest.raises(ValueError):
        c.erase(5, 5, 4, 6)
    for decorate in (c.open_arrow, c.closed_arrow, c.diamond):
        with pytest.raises(ValueError):
            decorate((3, 3), (3, 3))
    assert c.records == []


def test_oversized_canvas_is_rejected_before_allocating():
    with pytest.raises(ValueError, match="너무 크다"):
        Canvas((0, 0, 5000, 5000))
    Canvas((0, 0, 1800, 1800))
