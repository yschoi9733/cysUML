import math

import pytest
from PIL import Image

from cysuml import text as T
from cysuml.canvas import PAD, Canvas, Ellipse, Line, Mask, Polygon, Rect, Text


def draw_sample(scale=1.6):
    c = Canvas(scale)
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
    rec = draw_sample().records
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
    rec = [r for r in draw_sample().records if isinstance(r, Text)]
    assert [r.text for r in rec] == ["주문 Order", "0..*"]
    assert rec[0].box == T.place(70, 35, "주문 Order", True, "mm").box
    assert rec[0].bold and rec[0].owner == "Order" and not rec[0].bg


def test_bg_text_leaves_a_mask_just_before_it():
    rec = draw_sample().records
    i = next(i for i, r in enumerate(rec) if isinstance(r, Text) and r.bg)
    mask = rec[i - 1]
    assert isinstance(mask, Mask)
    l, t, r, b = T.place(150, 40, "0..*", anchor="mm").ink
    assert (mask.left, mask.top, mask.right, mask.bottom) == pytest.approx((l - 2, t - 2, r + 2, b + 2))


def test_blank_bg_text_lays_no_mask():
    c = Canvas()
    c.line([(0, 10), (100, 10)])
    c.text(50, 10, "   ", anchor="mm", bg=True)
    assert [type(r) for r in c.records] == [Line, Text] and not c.records[-1].bg


def test_records_do_not_depend_on_scale():
    assert draw_sample(1.6).records == draw_sample(0.5).records


def test_frame_is_the_drawing_plus_padding():
    c = draw_sample()
    bottom = 150 + 10 * math.sin(math.radians(28))  # 열린 화살촉 끝
    assert c.bounds() == pytest.approx((20, 20, 252, bottom))
    assert c.frame() == pytest.approx((20 - PAD, 20 - PAD, 252 + PAD, bottom + PAD))


def pixel(c, img, x, y):
    fx, fy, _, _ = c.frame()
    return img.getpixel((int((x - fx) * c.scale), int((y - fy) * c.scale)))


def test_diamond_and_arrow_fill():
    c = Canvas(8)
    c.diamond((10, 20), (90, 20), filled=True)
    c.diamond((10, 60), (90, 60), filled=False)
    c.closed_arrow((90, 80), (10, 80), filled=False, size=18, half=9)
    img = c.to_image()
    assert pixel(c, img, 19, 20) < 60
    assert pixel(c, img, 19, 60) > 200
    assert pixel(c, img, 84, 80) > 200
    assert pixel(c, img, 72.2, 80) < 60


def test_dashed_line_has_gaps():
    c = Canvas(8)
    c.line([(0, 10), (100, 10)], dash=(5, 4))
    img = c.to_image()
    assert pixel(c, img, 2, 10) < 60 and pixel(c, img, 7, 10) > 200 and pixel(c, img, 11, 10) < 60


def test_box_border_is_centred_on_its_edge_like_lines():
    c = Canvas(8)
    c.rect(10, 10, 40, 20)
    c.line([(50, 50), (50, 70)])
    img = c.to_image()
    fx, fy, _, _ = c.frame()
    for y in (20, 60):
        row = int((y - fy) * c.scale)
        dark = [px for px in range(int((48 - fx) * c.scale), int((52 - fx) * c.scale)) if img.getpixel((px, row)) < 128]
        centre = fx + (dark[0] + dark[-1] + 1) / 2 / c.scale
        assert centre == pytest.approx(50, abs=0.1)
        assert (dark[-1] + 1 - dark[0]) / c.scale == pytest.approx(1, abs=0.2)


def test_bg_text_erases_the_line_under_it():
    c = Canvas(8)
    c.line([(0, 20), (200, 20)])
    c.text(100, 20, "선 위 label", anchor="mm", bg=True)
    img = c.to_image()
    l, _, r, _ = T.place(100, 20, "선 위 label", anchor="mm").ink
    assert pixel(c, img, l - 1, 20) > 200 and pixel(c, img, r + 1, 20) > 200
    assert pixel(c, img, l - 5, 20) < 60


@pytest.mark.parametrize("s", ["registerMemberAccountWithVerificationCode()", "회원가입요청을처리한다 longName", "※ 참고 ① Item"])
def test_drawn_text_matches_its_record_at_any_scale(s):
    extents = []
    for scale in (2, 4, 8):
        c = Canvas(scale)
        c.text(10, 20, s)
        img = c.to_image()
        l, _, r, _ = img.point(lambda p: 255 if p < 128 else 0).getbbox()
        fx = c.frame()[0]
        extents.append((fx + l / scale, fx + r / scale))
        box = c.records[-1].box
        assert box[0] - 0.5 <= extents[-1][0] and extents[-1][1] <= box[2] + 0.5
    lefts, rights = [e[0] for e in extents], [e[1] for e in extents]
    assert max(lefts) - min(lefts) < 0.6 and max(rights) - min(rights) < 0.6


def render_text(s):
    c = Canvas()
    c.text(5, 15, s)
    return c.to_image()


def test_korean_is_drawn_with_real_glyphs():
    assert render_text("가").tobytes() != render_text("나").tobytes()  # 글꼴에 없는 글자면 둘 다 같은 빈 네모로 그려진다
    assert render_text("※").tobytes() != render_text("①").tobytes()


def test_output_is_scaled_and_framed_around_the_drawing(tmp_path):
    c = Canvas()
    c.rect(100, 100, 50, 30)
    assert c.frame() == (100 - PAD, 100 - PAD, 150 + PAD, 130 + PAD)
    size = c.save(tmp_path / "out.png")
    assert size[0] == pytest.approx((50 + 2 * PAD) * 1.6, abs=1)
    assert size[1] == pytest.approx((30 + 2 * PAD) * 1.6, abs=1)
    with Image.open(tmp_path / "out.png") as img:
        assert img.format == "PNG" and img.size == size
        assert img.getextrema()[0] < 50


def test_nothing_drawn_cannot_be_rendered():
    c = Canvas()
    with pytest.raises(ValueError, match="그린 것이 없다"):
        c.to_image()
    c.text(0, 0, "  ")
    assert c.bounds() is None


def test_oversized_drawing_is_rejected_before_allocating():
    c = Canvas()
    c.line([(0, 0), (5000, 5000)])
    with pytest.raises(ValueError, match="너무 크다"):
        c.to_image()


def test_invalid_input_is_rejected_without_a_record():
    for scale in (0, -1, math.nan, math.inf):
        with pytest.raises(ValueError):
            Canvas(scale)
    c = Canvas()
    bad = [
        lambda: c.line([(0, 0)]),
        lambda: c.line([(0, 0), (math.nan, 5)]),
        lambda: c.line([(0, 0), (5, 5)], dash=(0.1, 3)),
        lambda: c.line([(0, 0), (5, 5)], dash=(5, 0)),
        lambda: c.poly([(0, 0), (5, 5)]),
        lambda: c.rect(5, 5, -1, 2),
        lambda: c.rect(1, 1, 10, 10, fill="#zz"),
        lambda: c.ellipse(5, 5, 2, -1),
        lambda: c.poly([(0, 0), (5, 5), (0, 5)], fill="no-such-color"),
        lambda: c.erase(5, 5, 4, 6),
        lambda: c.text(0, 0, "a", anchor="rs"),
        lambda: c.text(math.inf, 0, "a"),
        lambda: c.text(0, 0, "a\tb"),
        lambda: c.text(0, 0, "😀", bg=True),
        lambda: c.open_arrow((3, 3), (3, 3)),
        lambda: c.closed_arrow((3, 3), (3, 3)),
        lambda: c.diamond((3, 3), (3, 3)),
    ]
    for call in bad:
        with pytest.raises(ValueError):
            call()
    assert c.records == []
