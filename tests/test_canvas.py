import math
import unicodedata

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
    head = rec[5]
    assert isinstance(head, Line) and len(head.points) == 3 and head.points[1] == (120, 150)
    assert math.dist(head.points[0], head.points[1]) == pytest.approx(10)
    assert math.dist(head.points[2], head.points[1]) == pytest.approx(10)
    assert rec[6] == Ellipse(240, 20, 12, 12)
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
    fx, fy, fr, fb = c.frame()
    assert (fx, fy) == (20 - PAD, 20 - PAD)
    assert 252 + PAD <= fr < 252 + PAD + 1 / 1.6 and bottom + PAD <= fb < bottom + PAD + 1 / 1.6


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


def test_dash_pattern_carries_over_bend_points():
    c = Canvas(8)
    c.line([(x, 10) for x in range(0, 31, 3)], dash=(5, 4))  # 구간마다 3 — 무늬를 새로 시작하면 실선이 된다
    img = c.to_image()
    assert pixel(c, img, 2, 10) < 60 and pixel(c, img, 7, 10) > 200 and pixel(c, img, 11, 10) < 60
    assert pixel(c, img, 16, 10) > 200 and pixel(c, img, 20, 10) < 60


def test_text_record_keeps_its_placement_and_normalized_text():
    c = Canvas()
    c.text(10, 20, unicodedata.normalize("NFD", "주문 Order"), anchor="mm")
    r = c.records[-1]
    assert r.text == "주문 Order"
    assert r.placement == T.place(10, 20, "주문 Order", anchor="mm") and r.box == r.placement.box
    hand = Text(10, 20, unicodedata.normalize("NFD", "주문 Order"), False, "mm")  # 손으로 만든 기록도 모으고 놓는다
    assert hand.text == "주문 Order" and hand.placement == r.placement


def test_bg_flag_is_recorded_as_bool():
    c = Canvas()
    c.text(0, 0, "a", bg=0)
    c.text(0, 20, "b", bg=1)
    assert [r.bg for r in c.records if isinstance(r, Text)] == [False, True]


def test_zero_area_erase_leaves_the_drawing_alone():
    c = Canvas(8)
    c.line([(0, 0), (10, 0)])
    c.erase(5, -5, 5, 5)
    img = c.to_image()
    assert pixel(c, img, 5, 0) < 60


@pytest.mark.parametrize("scale", [0.25, 0.75, 1.6])
def test_zero_size_boxes_render_at_any_scale(scale):
    c = Canvas(scale)
    c.rect(10, 10, 0, 10)
    c.ellipse(20, 10, 0, 0)
    c.rect(30, 10, 5, 5)
    c.erase(31, 11, 31, 11)
    c.to_image()


def test_bends_are_joined_round_in_solid_and_dashed_lines():
    c = Canvas(8)
    c.line([(0, 0), (10, 0), (10, 10)])
    c.line([(30, 0), (40, 0), (40, 10)], dash=(5, 4))  # 9~14 칸이 꺾는 점(40, 0)을 지난다
    img = c.to_image()
    for x in (10, 40):
        assert pixel(c, img, x + 0.3, -0.3) < 128  # 바깥 모서리가 파이지 않았다


def test_painter_refuses_unknown_records():
    c = Canvas()
    c.line([(0, 0), (10, 0)])
    c.records.append(object())
    with pytest.raises(TypeError):
        c.to_image()


def test_painter_stops_on_a_hand_made_dash_with_no_period():
    c = Canvas()
    c.records.append(Line(((0.0, 0.0), (5.0, 5.0)), (0.0, 0.0)))
    with pytest.raises(ValueError, match="점선 무늬"):
        c.to_image()


def test_borders_of_boxes_and_polygons_are_centred_on_their_edges_like_lines():
    c = Canvas(8)
    c.rect(10, 10, 40, 20)
    c.line([(50, 50), (50, 70)])
    c.poly([(70, 50), (90, 50), (90, 70), (70, 70)])
    c.diamond((110, 60), (200, 60), filled=False)
    img = c.to_image()
    fx, fy, _, _ = c.frame()
    for x, y in ((50, 20), (50, 60), (70, 60), (110, 60)):
        row = int((y - fy) * c.scale)
        dark = [px for px in range(int((x - 2 - fx) * c.scale), int((x + 2 - fx) * c.scale)) if img.getpixel((px, row)) < 128]
        centre = fx + (dark[0] + dark[-1] + 1) / 2 / c.scale
        width = (dark[-1] + 1 - dark[0]) / c.scale
        if x == 110:  # 마름모 꼭짓점: 둥근 이음이 반 획만큼 바깥으로 나온다
            assert fx + dark[0] / c.scale == pytest.approx(110 - 0.5, abs=0.15)
        else:
            assert centre == pytest.approx(x, abs=0.1) and width == pytest.approx(1, abs=0.2)


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
    fx, fy, fr, fb = c.frame()
    assert (fx, fy) == (100 - PAD, 100 - PAD)
    assert 150 + PAD <= fr < 150 + PAD + 1 / 1.6 and 130 + PAD <= fb < 130 + PAD + 1 / 1.6
    size = c.save(tmp_path / "out.png")
    assert size == (round((fr - fx) * 1.6), round((fb - fy) * 1.6))
    assert size[0] == pytest.approx((50 + 2 * PAD) * 1.6, abs=1)
    with Image.open(tmp_path / "out.png") as img:
        assert img.format == "PNG" and img.size == size
        assert img.getextrema()[0] < 50


@pytest.mark.parametrize("width", [100.13, 333.33, 1023.97])
def test_frame_maps_output_pixels_exactly(width):
    c = Canvas(1.6)
    c.rect(0.3, 0.7, width, 50.07)
    fx, fy, fr, fb = c.frame()
    img = c.to_image()
    assert img.size[0] / 1.6 == pytest.approx(fr - fx) and img.size[1] / 1.6 == pytest.approx(fb - fy)


def test_drawing_calls_return_what_they_record():
    c = Canvas()
    made = [c.line([(0, 0), (10, 0)]), c.rect(0, 0, 5, 5), c.ellipse(0, 0, 5, 5), c.poly([(0, 0), (5, 0), (0, 5)]),
            c.open_arrow((20, 0), (0, 0)), c.closed_arrow((20, 0), (0, 0)), c.diamond((0, 0), (20, 0)),
            c.erase(0, 0, 1, 1)]
    assert made == c.records
    label = c.text(0, 0, "가", bg=True)
    assert label is c.records[-1] and label.bg and type(c.records[-2]).__name__ == "Mask"


def test_measure_gives_the_framed_size_and_the_png_size():
    c = Canvas(1.6)
    c.rect(0.3, 0.7, 333.33, 50.07)
    (w, h), png = c.measure()  # Measure(size, png)
    assert (w, h) == pytest.approx((333.33 + 2 * PAD, 50.07 + 2 * PAD))
    assert png == c.to_image().size
    assert Canvas().measure() is None


def test_nothing_drawn_cannot_be_rendered():
    c = Canvas()
    with pytest.raises(ValueError, match="그린 것이 없다"):
        c.to_image()
    c.text(0, 0, "  ")
    assert c.bounds() is None


@pytest.mark.parametrize("scale, pts", [(1.6, [(0, 0), (5000, 5000)]), (1e308, [(0, 0), (100, 100)]),
                                        (1.6, [(-1e308, 0), (1e308, 0)])])
def test_oversized_drawing_is_rejected_before_allocating(scale, pts):
    c = Canvas(scale)
    c.line(pts)
    for call in (c.frame, c.to_image):
        with pytest.raises(ValueError, match="너무 크다"):
            call()
    assert c.measure().png is None


@pytest.mark.parametrize("scale", [0.25, 1.6, 3.0])
def test_measured_png_size_is_the_size_to_image_draws(scale):
    c = Canvas(scale)
    c.rect(0.3, 0.7, 333.33, 50.07)
    c.text(10, 10, "가 A")
    assert c.measure().png == c.to_image().size
    assert Canvas(scale).measure() is None


def test_box_outline_coordinates_are_rounded_to_centre_the_border():
    from cysuml.canvas import _Painter

    painter = _Painter(Image.new("L", (1, 1)), 0, 0, 6.4)
    assert painter.lw == 6
    assert painter._outlined(10, 10, 40, 20) == [(61, 61), (322, 194)]
    thin = _Painter(Image.new("L", (1, 1)), 0, 0, 1)
    assert thin._outlined(12, 12, 0, 0) == [(12, 12), (12, 12)]  # round()였으면 (12, 12)~(11, 11)로 뒤집힌다
    assert thin._pixels(10.5, 2.5, 13.5, 4.5) == [(11, 3), (13, 4)]


@pytest.mark.parametrize("k", [1, 2.5, 4, 6.4, 9.6])
@pytest.mark.parametrize("v", [5.0, 5.3, 5.5, 5.77])
def test_strokes_joints_and_box_edges_fill_the_same_pixels(k, v):
    from cysuml.canvas import _Painter

    img = Image.new("L", (300, 300), 255)
    painter = _Painter(img, 0, 0, k)
    y, h = v * k, painter.lw / 2
    painter._stroke([(1 * k, y), (20 * k, y), (20 * k, 30 * k)])  # 가로선과 꺾는 점(20, v) — 4배 그림판 좌표
    want = list(range(math.floor(y - h + 0.5), math.floor(y + h + 0.5)))
    assert [r for r in range(300) if img.getpixel((round(10 * k), r)) < 128] == want
    (_, top), (_, bottom) = painter._pixels(0, y - h, 1, y + h)  # 이음 점과 상자 변이 쓰는 규칙
    assert (top, bottom) == (want[0], want[-1])


def test_erase_accepts_far_apart_edges_and_arrow_angle_errors_say_angle():
    c = Canvas()
    c.erase(-1e308, 0, 1e308, 10)
    assert isinstance(c.records[-1], Mask)
    with pytest.raises(ValueError, match="각"):
        c.open_arrow((0, 0), (5, 5), spread=0)


def test_self_crossing_polygon_is_accepted():
    c = Canvas()
    c.poly([(0, 0), (10, 10), (10, 0), (0, 10)])
    assert isinstance(c.records[-1], Polygon)


def test_invalid_input_is_rejected_without_a_record():
    for scale in (0, -1, 0.001, 0.2, math.nan, math.inf, "2", None):
        with pytest.raises(ValueError):
            Canvas(scale)
    c = Canvas()
    bad = [
        lambda: c.line([(0, 0)]),
        lambda: c.line([(0, 0), (math.nan, 5)]),
        lambda: c.line([(5, 5), (5, 5)]),
        lambda: c.line([(5, 5), (5, 5), (5, 5)], dash=(3, 2)),
        lambda: c.line([1, 2]),
        lambda: c.line(5),
        lambda: c.line([(0, 0), (1, 2, 3)]),
        lambda: c.line([(0, 0), ("1", 2)]),
        lambda: c.line([(0, 0), (5, 5)], dash=(0.1, 3)),
        lambda: c.line([(0, 0), (5, 5)], dash=(5, 0)),
        lambda: c.line([(0, 0), (5, 5)], dash=(5,)),
        lambda: c.line([(0, 0), (5, 5)], dash=(5, 4, 3)),
        lambda: c.line([(0, 0), (100_001, 0)], dash=(0.5, 0.5)),
        lambda: c.rect("1", 2, 3, 4),
        lambda: c.rect(1, 2, 3, 4, fill=123),
        lambda: c.text(0, 0, 123),
        lambda: c.closed_arrow((0, 0), (5, 5), size="big"),
        lambda: c.poly([(0, 0), (5, 5)]),
        lambda: c.poly([(5, 5), (5, 5), (5, 5)]),
        lambda: c.poly([(0, 0), (1, 1), (2, 2)]),
        lambda: c.open_arrow((0, 0), (5, 5), size=0),
        lambda: c.open_arrow((0, 0), (5, 5), spread=math.pi / 2),
        lambda: c.closed_arrow((0, 0), (5, 5), size=-1),
        lambda: c.diamond((0, 0), (5, 5), half=0),
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
