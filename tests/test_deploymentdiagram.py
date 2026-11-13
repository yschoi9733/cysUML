"""배치도(deployment diagram): 노드 안에 두기, 통신 경로(화살촉 없는 연관), «deploy», 노드 안의 노드, 자리 잡기 요령의 수치."""
import string

import pytest

from cysuml import boxcheck as K
from cysuml import deploymentdiagram as D
from cysuml import guide
from cysuml.canvas import Line, Text
from cysuml.parsing import InputError
from cysuml.shapes import DEPTH, NODE
from cysuml.text import text_width


def el(kind, name, left, top, **more):
    return {"kind": kind, "name": name, "left": left, "top": top, **more}


def inside(parent, kind, name, left, top, **more):
    return el(kind, name, left, top, **{"in": parent}, **more)


def rel(kind, source, target, **more):
    return {"kind": kind, "from": source, "to": target, **more}


def path(source, target, **more):
    return rel("association", source, target, **more)


def deploy(source, target, **more):
    return rel("dependency", source, target, stereotype="deploy", **more)


def https(source, target, **more):
    return path(source, target, name="HTTPS", **more)


def draw(elements, relations=()):
    return D.render({"elements": list(elements), "relations": list(relations)})


def report(elements, relations=()):
    return K.check(draw(elements, relations))


def kinds(r):
    return [f.kind for f in r.failures]


def placed(drawing, key):
    return drawing.layout.by_key[key]


def device(name, left, top, **more):
    return el("node", name, left, top, stereotype="device", **more)


# 노드 넷: PC·Web·App(안에 실행 환경 노드)·DB. 스테레오타입을 단 노드라 안의 요소는 top + 66부터 둔다
FOUR = [device("PC", 0, 0), inside("PC", "component", "Browser", 20, 66),
        device("Web Server", 240, 0), inside("Web Server", "artifact", "index.html", 260, 66),
        device("App Server", 480, 0), el("node", "JVM", 500, 66, stereotype="executionEnvironment", **{"in": "App Server"}),
        inside("JVM", "component", "OrderService", 520, 132), inside("JVM", "artifact", "order.jar", 520, 240),
        device("DB Server", 800, 0), inside("DB Server", "artifact", "orders.db", 820, 66)]
PATHS = [path("PC", "Web Server", name="HTTPS"), path("Web Server", "App Server", name="HTTP"),
         path("App Server", "DB Server", name="JDBC"),
         rel("dependency", "order.jar", "OrderService", stereotype="manifest")]


# ---------------------------------------------------------------- 이슈의 확인 넷


def test_four_nodes_with_components_and_artifacts_inside_and_paths_between_pass():
    r = report(FOUR, PATHS)
    assert r.passed, r.summary()


def test_deploy_from_a_component_or_artifact_outside_onto_a_node_passes():
    d = draw([el("artifact", "shop.war", 20, 0), el("component", "Batch", 300, 0),
              device("Server", 0, 140, width=400), inside("Server", "component", "Api", 20, 206)],
             [deploy("shop.war", "Server"), deploy("Batch", "Server")])
    assert K.check(d).passed, K.check(d).summary()
    for drawn in d.drawn:  # 점선 화살표, 이름 자리에 «deploy»
        assert drawn.line.dash is not None and [h for h in drawn.heads if isinstance(h, Line)]
        assert [t.text for t in drawn.labels[0]] == ["«deploy»"]


@pytest.mark.parametrize("target", ["Docker", "Server"])
def test_deploy_from_an_element_inside_a_node_to_that_node_is_an_input_error(target):
    # 노드 안에 두는 표기와 «deploy»를 한 그림에 섞어 쓸 수는 있어도, 안에 둔 요소에서 제 노드나 그 바깥 노드로 긋지는 않는다
    elements = [device("Server", 0, 0), el("node", "Docker", 20, 66, stereotype="executionEnvironment", **{"in": "Server"}),
                inside("Docker", "artifact", "app.jar", 40, 132)]
    with pytest.raises(InputError, match="품은 요소와 그 안의 요소는 선으로 잇지 않는다"):
        draw(elements, [deploy("app.jar", target)])
    assert "노드 안에 둔 요소에서 그 노드(나 그 노드를 품은 노드)로는 긋지 않는다" in D.TOOL


def test_node_inside_a_node_passes():
    r = report([device("Server", 0, 0), el("node", "Docker", 20, 66, stereotype="executionEnvironment", **{"in": "Server"}),
                el("node", "Tomcat", 40, 132, stereotype="executionEnvironment", **{"in": "Docker"}),
                inside("Tomcat", "component", "Api", 60, 198), inside("Docker", "artifact", "app.jar", 340, 198)],
               [deploy("app.jar", "Tomcat")])
    assert r.passed, r.summary()


def test_path_through_a_node_it_does_not_connect_and_the_element_inside_fails():
    # PC에서 DB Server로 곧게 가는 경로가 사이의 Web Server와 그 안의 index.html을 지난다
    elements = [device("PC", 0, 0, height=180), device("Web Server", 240, 0, height=180),
                inside("Web Server", "artifact", "index.html", 260, 66), device("DB Server", 480, 0, height=180)]
    r = report(elements, [path("PC", "DB Server")])
    through = [f.elements[1] for f in r.failures if f.kind == "line_through_box"]
    assert through == ["Web Server", "index.html"] and not r.passed


def test_path_into_a_nested_node_through_a_sibling_element_fails():
    # App 안 JVM으로 가는 경로는 끝을 품은 App은 지나도 되지만, 그 안의 다른 요소 Cache를 지나면 불합격이다
    r = report([el("node", "PC", 0, 60), el("node", "App", 200, 0), inside("App", "component", "Cache", 220, 52),
                inside("App", "node", "JVM", 380, 52), inside("JVM", "component", "Svc", 400, 104)],
               [path("PC", "JVM", name="RMI")])
    assert [(f.kind, f.elements) for f in r.failures] == [("line_through_box", ("PC->JVM", "Cache"))]


# ---------------------------------------------------------------- 통신 경로와 표기


def test_communication_path_has_no_arrowhead_unless_navigable_says_so():
    nodes = [el("node", "A", 0, 0), el("node", "B", 300, 0)]
    plain, = draw(nodes, [path("A", "B", name="HTTPS")]).drawn
    assert plain.heads == () and plain.line.dash is None
    one_way, = draw(nodes, [path("A", "B", navigable="to")]).drawn
    assert [h for h in one_way.heads if isinstance(h, Line)]
    assert '"to"·"from"·"both"·"none"(기본)' in D.TOOL and guide.relation_fields(D.SPEC) in D.TOOL
    # 기본 방향은 도구 전체에 걸리므로(클래스끼리 이은 연관도 화살촉 없이 그린다) 표기 절이 그것을 알린다
    classes, = draw([el("class", "Order", 0, 0), el("class", "Customer", 200, 0)], [path("Order", "Customer")]).drawn
    assert classes.heads == () and "클래스끼리 이은 연관·집합·합성도 같으니, 화살촉이 필요하면 navigable을 준다" in D.TOOL


def test_path_takes_a_name_and_a_stereotype_on_the_line():
    d = draw([el("node", "A", 0, 0), el("node", "B", 300, 0)], [path("A", "B", name="HTTPS", stereotype="internet")])
    assert [t.text for t in d.drawn[0].labels[0]] == ["«internet»", "HTTPS"]
    assert K.check(d).passed


def test_node_kinds_are_stereotypes_above_the_name_on_the_same_shape():
    d = draw([device("PC", 0, 0), el("node", "JVM", 200, 0, stereotype="executionEnvironment")])
    texts = [(t.text, t.bold) for t in d.canvas.records if isinstance(t, Text)]
    assert texts == [("«device»", False), ("PC", True), ("«executionEnvironment»", False), ("JVM", True)]
    assert placed(d, "PC").shape is placed(d, "JVM").shape is NODE


def test_takes_the_elements_of_the_package_tool_and_nothing_else():
    # 패키지도·컴포넌트도와 함께 받는 공용 요소 종류(아이콘 표기 두 종류 포함) 그대로다 — 다른 도구의 종류가 섞이면 걸린다
    assert set(D.SPEC.shapes) == {"class", "abstract", "interface", "enum", "package", "component", "artifact", "component_icon",
                                  "artifact_icon", "node"}
    with pytest.raises(InputError) as e:
        draw([el("usecase", "U", 0, 0)])
    assert [p.split(":")[0] for p in e.value.problems] == ["elements[0].kind"]


# ---------------------------------------------------------------- 자리 잡기 요령의 수치


def test_nodes_in_a_row_with_the_same_top_and_height_get_straight_paths():
    # App Server는 안의 JVM에 맞춰 늘어나 다른 노드보다 높다 — 결과의 높이를 다른 노드의 height로 주면 경로가 곧다
    slanted = draw(FOUR, PATHS)
    assert any(len({y for _, y in r.points}) > 1 for r in slanted.layout.relations[:3])
    tallest = placed(slanted, "App Server").height
    same = [{**e, "height": tallest} if e["kind"] == "node" and "in" not in e else e for e in FOUR]
    straight = draw(same, PATHS)
    assert all(len({y for _, y in r.points}) == 1 for r in straight.layout.relations[:3])
    assert K.check(straight).passed
    assert "top과 height를, 세로 한 단에 쌓은 노드는 left와 width를 같게" in D.TIPS and "다시 늘면 다시 맞춘다" in D.TIPS


def test_nodes_stacked_in_a_column_with_the_same_left_and_width_get_a_straight_path():
    # 위아래로 쌓은 두 노드는 이름 길이가 달라 폭이 달라 경로가 비스듬하다 — 넓은 쪽 폭을 다른 노드의 width로 주면 곧다
    column = [device("PC", 0, 0), device("Application Server", 0, 200)]
    slanted = draw(column, [path("PC", "Application Server")])
    assert len({x for x, _ in slanted.layout.relations[0].points}) > 1
    widest = max(placed(slanted, k).width for k in ("PC", "Application Server"))
    straight = draw([{**e, "width": widest} for e in column], [path("PC", "Application Server")])
    assert len({x for x, _ in straight.layout.relations[0].points}) == 1 and K.check(straight).passed


@pytest.mark.parametrize("node, top", [(el("node", "N", 0, 0), 52), (device("N", 0, 0), 66),
                                       (el("node", ["App", "Server"], 0, 0, id="N", stereotype="device"), 80)])
def test_element_inside_a_node_starts_14px_lower_for_each_name_line(node, top):
    # 이름 한 줄 노드는 top + 52, 스테레오타입이나 이름 줄이 하나 늘 때마다 14px 아래부터 둔다
    assert report([node, inside("N", "component", "C", 20, top)]).passed
    (f,) = report([node, inside("N", "component", "C", 20, top - 14)]).failures
    assert f.kind == "inner_off_area"
    assert "«device» 노드면 top + 66, 이름이 두 줄인 «device» 노드면 top + 80" in D.TIPS and "노드면 노드 top + 52부터" in D.TIPS


OUTER = [device("App Server", 0, 0),
         el("node", "Tomcat", 20, 66, stereotype="executionEnvironment", **{"in": "App Server"}),
         inside("Tomcat", "component", "Svc", 40, 132)]


def size_of(element):
    p = placed(draw([element]), element.get("id", element["name"]))
    return p.width, p.height


def internet(*names):
    """«internet» 스테레오타입과 이름 줄(names)을 단 통신 경로 — 선 글자가 1 + 이름 줄 수만큼의 줄이다."""
    def make(source, target, **more):
        return path(source, target, stereotype="internet", name=list(names), **more)
    return make


LABELS = {  # 선 글자 → (선 만들기, 줄)
    "deploy": (deploy, ("«deploy»",)),
    "https": (https, ("HTTPS",)),
    "two-lines": (internet("HTTPS"), ("«internet»", "HTTPS")),
    "three-lines": (internet("HTTPS", "port 443"), ("«internet»", "HTTPS", "port 443")),
}


def estimate(s):
    """요령의 선 글자 폭 어림: 영문·숫자·ASCII 기호 한 글자 11px(W·@·%는 14px), 한글 12px, 그 밖의 글자 14px."""
    def one(c):
        if c.isascii():
            return 14 if c in "W@%" else 11
        return 12 if "가" <= c <= "힣" else 14
    return sum(one(c) for c in s)


def drawable(c):
    try:
        text_width(c)
    except ValueError:  # 함께 넣은 글꼴에 없는 글자 — 도구는 입력 오류로 돌려준다
        return False
    return True


def test_label_width_estimate_of_the_tip_is_an_upper_bound_for_every_character():
    # 글자마다 상한이라 어떤 선 글자든 어림이 실제 폭 이상이다(대문자 프로토콜 이름 AMQP·MQTT·CORBA·WWW 등과 한자·가나·화살표도).
    # 함께 넣은 글꼴에 없는 글자는 도구가 입력 오류로 돌려주므로 보지 않는다
    others = [chr(c) for r in ((0xA0, 0x100), (0x2010, 0x2060), (0x2190, 0x2200), (0x3041, 0x30FF), (0x4E00, 0x9FFF),
                               (0xFF01, 0xFF5F)) for c in range(*r)]
    chars = ([c for c in string.printable if c.isprintable()] + ["«", "»"] + [chr(c) for c in range(0xAC00, 0xD7A4)]
             + [c for c in others if c.isprintable() and drawable(c)])
    assert [c for c in chars if text_width(c) > estimate(c)] == []
    for label in ("«deploy»", "«internet»", "HTTPS", "AMQP", "MQTT", "SMTP", "SOAP", "CORBA", "WWW", "user@host",
                  "100%", "port 443", "웹 소켓", "애플리케이션", "gRPC → 日本 キュー"):
        assert text_width(label) <= estimate(label), label
    assert "영문·숫자·ASCII 기호 한 글자 11px(W·@·%는 14px), 한글 12px, 그 밖의 글자 14px로 어림하고" in D.TIPS


def side_gaps(outer, lines, end="Tomcat", measure=estimate):
    """요령의 간격: (왼쪽, 오른쪽, 아래). 옆은 가장 바깥 노드 테두리 ~ 끝 요소 거리 + 가장 긴 줄의 폭(measure로 잰다) + 20, 아래는
    그 거리 + 40 + 줄이 늘 때마다 15."""
    d = draw(outer)
    o, i = placed(d, outer[0]["name"]).rect, placed(d, end).rect
    width = max(measure(s) for s in lines)
    return i[0] - o[0] + width + 20, o[2] - i[2] + width + 20, o[3] - i[3] + 40 + 15 * (len(lines) - 1)


def above_gap(lines):
    """요령의 위쪽 간격: 80 + 줄이 늘 때마다 15."""
    return 80 + 15 * (len(lines) - 1)


def sent_from(outer, sender, side, gap, make, end="Tomcat", offset=20):
    """가장 바깥 노드의 side 쪽으로 gap 떨어진 자리에 sender를 두고 끝 요소 end로 make 선을 그은 검사 결과. 옆이면 sender의 top을
    끝 요소 윗변 + offset에, 아래면 left를 끝 요소 왼변 + offset에 둔다(요령대로 끝 요소 높이·가로 자리 안)."""
    d = draw(outer)
    o, i = placed(d, outer[0]["name"]).rect, placed(d, end).rect
    w, _ = size_of(sender)
    left, top = {"left": (o[0] - gap - w, i[1] + offset), "right": (o[2] + gap, i[1] + offset),
                 "below": (i[0] + offset, o[3] + gap)}[side]
    return report([{**sender, "left": left, "top": top}, *outer], [make(sender["name"], end)])


@pytest.mark.parametrize("label", LABELS)
def test_line_into_a_nested_node_from_above_crosses_the_outer_name_but_not_from_the_side_or_below(label):
    make, lines = LABELS[label]
    sender = el("artifact", "order.war", 60, -140)
    r = report([sender, *OUTER], [make("order.war", "Tomcat")])
    assert ("line_through_name", ("order.war->Tomcat", "App Server")) in [(f.kind, f.elements) for f in r.failures]
    for side, gap in zip(("left", "right", "below"), side_gaps(OUTER, lines)):
        r = sent_from(OUTER, sender, side, gap, make)
        assert r.passed, (side, gap, r.summary())


# 세 겹: App Server 안 Docker 안 Tomcat 안 Svc
DEEP = [device("App Server", 0, 0),
        el("node", "Docker", 20, 66, stereotype="executionEnvironment", **{"in": "App Server"}),
        el("node", "Tomcat", 40, 132, stereotype="executionEnvironment", **{"in": "Docker"}),
        inside("Tomcat", "component", "Svc", 60, 198)]


@pytest.mark.parametrize("outer, end", [(OUTER, "Svc"), (DEEP, "Tomcat"), (DEEP, "Svc")])
@pytest.mark.parametrize("label", ["deploy", "two-lines"])
def test_side_or_below_sender_reaches_a_deeper_end_with_the_gap_measured_to_that_end(outer, end, label):
    # 끝 요소가 노드 안 노드의 요소이거나 더 깊어도, 간격을 가장 바깥 노드 테두리에서 끝 요소까지로 재고 보내는 요소를 끝 요소
    # 높이·가로 자리에 두면 합격한다(끝을 품은 노드들의 이름도 지나지 않는다)
    make, lines = LABELS[label]
    sender = el("artifact", "a.war", 0, 0)
    for side, gap in zip(("left", "right", "below"), side_gaps(outer, lines, end)):
        for offset in (0, 20):
            r = sent_from(outer, sender, side, gap, make, end, offset)
            assert r.passed, (side, offset, r.summary())
    assert "그 노드 테두리에서 끝 요소까지의 거리" in D.TIPS and "끝 요소와 같은 높이로" in D.TIPS


def test_side_sender_picks_the_side_with_nothing_in_the_way():
    # Server 안에 A(왼쪽)와 B(오른쪽). 왼쪽에서 B로 보내면 선이 A를 지나고, 길이 빈 오른쪽·아래에서 보내면 합격한다
    server = [device("Server", 0, 0), inside("Server", "artifact", "A", 20, 66), inside("Server", "artifact", "B", 200, 66)]
    sender = el("artifact", "x.war", 0, 0)
    gaps = dict(zip(("left", "right", "below"), side_gaps(server, ("«deploy»",), "B")))
    r = sent_from(server, sender, "left", gaps["left"], deploy, "B")
    assert ("line_through_box", ("x.war->B", "A")) in [(f.kind, f.elements) for f in r.failures]
    for side in ("right", "below"):
        assert sent_from(server, sender, side, gaps[side], deploy, "B").passed, side
    assert "끝 요소까지 가는 길에 다른 요소가 없는 쪽을 고른다" in D.TIPS


def test_bend_from_above_does_not_reach_a_deeper_end():
    # 꺾는 점 처방은 끝 요소가 가장 바깥 노드 바로 안의 노드일 때만 통한다. 더 깊으면 안쪽 노드(Tomcat) 이름을 지난다
    sender = above(OUTER, el("artifact", "w", 0, 0), -50, 80)
    assert report([sender, *OUTER], [deploy("w", "Tomcat", via=tip_bend(OUTER, sender))]).passed
    r = report([sender, *OUTER], [deploy("w", "Svc", via=tip_bend(OUTER, sender))])
    assert ("line_through_name", ("w->Svc", "Tomcat")) in [(f.kind, f.elements) for f in r.failures]
    assert "끝 요소가 더 깊으면 위에 두지 않는다" in D.TIPS


@pytest.mark.parametrize("name, label, left", [("order.war", "deploy", 305), ("w", "two-lines", 330)])
def test_sender_near_the_top_right_corner_moves_20px_off_the_bevel(name, label, left):
    # 바깥 노드(오른변 260) 오른쪽 위에서 꺾는 점으로 가는 선이 45°쯤이면 오른쪽 위 모서리의 비스듬한 두께 띠 선을 따라간다.
    # 보내는 요소를 어느 쪽으로든 20px 옮기면 합격한다
    make, lines = LABELS[label]

    def sent(at):
        sender = above(OUTER, el("artifact", name, 0, 0), at, above_gap(lines))
        return report([sender, *OUTER], [make(name, "Tomcat", via=tip_bend(OUTER, sender))])
    assert ("line_along_container", (f"{name}->Tomcat", "App Server")) in [(f.kind, f.elements) for f in sent(left).failures]
    assert sent(left - 20).passed and sent(left + 20).passed
    assert "비스듬한 두께 띠 선을 따라가 불합격하면, 보내는 요소를 옆으로 20px쯤 옮긴다" in D.TIPS


@pytest.mark.parametrize("side", ["left", "right", "below"])
def test_side_or_below_sender_closer_than_the_tip_puts_the_label_on_the_outer_border(side):
    # 안쪽 노드가 바깥 노드 왼쪽 테두리에서 140px 들어가 있다. 선 글자는 선 가운데쯤에 놓이므로, 요령의 간격(옆은 실제 글자 폭
    # — 불합격 항목에 나오는 폭 — 으로 잰 것)보다 30px 가까이 두면 글자가 바깥 노드 테두리에 걸리고 요령대로 띄우면 합격한다
    # (옆은 20px 가까워도 걸리고, 아래 +40은 여유를 둔 값이다)
    outer = [device("App", 0, 0), el("node", "Tomcat", 140, 66, stereotype="executionEnvironment", **{"in": "App"}),
             inside("Tomcat", "component", "Svc", 160, 132)]
    sender = el("artifact", "a.war", 0, 0)
    gap = dict(zip(("left", "right", "below"), side_gaps(outer, ("«deploy»",), measure=text_width)))[side]
    offset = 40 if side == "below" else 20
    (f,) = sent_from(outer, sender, side, gap - 30, deploy, offset=offset).failures
    assert f.kind == "text_on_box" and f.elements == ("a.war->Tomcat", "App")
    assert sent_from(outer, sender, side, gap, deploy, offset=offset).passed
    assert "거리 + 선 글자 폭(가장 긴 줄) + 20px" in D.TIPS and "끝 요소 아랫변까지의 거리 + 40px 이상" in D.TIPS


def test_label_of_three_lines_from_below_needs_15px_more_for_each_extra_line():
    # «internet»·HTTPS·port 443 세 줄 글자는 아래 간격 + 40만으로는 바깥 노드 아랫변에 걸리고, 줄마다 15px를 더하면 합격한다
    make, lines = LABELS["three-lines"]
    sender = el("artifact", "a.war", 0, 0)
    gap = side_gaps(OUTER, lines)[2]
    (f,) = sent_from(OUTER, sender, "below", gap - 30, make, offset=40).failures
    assert f.kind == "text_on_box" and f.elements == ("a.war->Tomcat", "App Server")
    assert sent_from(OUTER, sender, "below", gap, make, offset=40).passed
    assert "보내는 요소가 아래나 위일 때 간격에 한 줄마다 15px를 더한다" in D.TIPS


CLUSTER = [device("Application Server Cluster", 0, 0),
           el("node", "Tomcat", 20, 66, stereotype="executionEnvironment", **{"in": "Application Server Cluster"}),
           inside("Tomcat", "component", "Svc", 40, 132)]


def tip_bend(outer, sender):
    """요령의 꺾는 점: 이름 칸에서 보내는 요소 쪽으로 40px 바깥, 이름 칸 아랫변 10px 아래."""
    zone = placed(draw(outer), outer[0]["name"]).zones[0].rect
    middle = sender["left"] + size_of(sender)[0] / 2
    return [[zone[0] - 40 if middle < (zone[0] + zone[2]) / 2 else zone[2] + 40, zone[3] + 10]]


def above(outer, sender, left, gap):
    """바깥 노드 윗변에서 gap 위에 밑변이 오게 둔 sender."""
    return {**sender, "left": left, "top": placed(draw(outer), outer[0]["name"]).rect[1] - gap - size_of(sender)[1]}


@pytest.mark.parametrize("outer, left", [(OUTER, -50), (OUTER, 190), (CLUSTER, -140), (CLUSTER, 280)])
@pytest.mark.parametrize("label", LABELS)
def test_sender_above_beside_the_name_follows_the_tip_with_one_bend(outer, left, label):
    # 이름 칸 바로 위는 아니지만 곧은 선이 이름 칸을 지나는 자리(바깥 노드 윗변에서 요령의 간격만큼 위)에서, 요령의 꺾는 점을
    # 하나 주면 합격한다. 이름이 길어 이름 칸 옆 앞면이 34px뿐이라 꺾는 점이 앞면 밖에 놓여도 같다
    make, lines = LABELS[label]
    sender = above(outer, el("artifact", "order.war", 0, 0), left, above_gap(lines))
    assert "line_through_name" in kinds(report([sender, *outer], [make("order.war", "Tomcat")]))
    holder = placed(draw(outer), outer[0]["name"])
    ((x, _),) = via = tip_bend(outer, sender)
    if outer is CLUSTER:
        assert holder.rect[2] - DEPTH - holder.zones[0].rect[2] < 40 and not holder.rect[0] < x < holder.rect[2] - DEPTH
    r = report([sender, *outer], [make("order.war", "Tomcat", via=via)])
    assert r.passed, r.summary()
    assert "40px쯤 바깥, 이름 칸 아랫변에서 10px 아래에 꺾는 점(via)을 하나 준다" in D.TIPS
    assert "꺾는 점이 앞면 밖(두께 띠나 노드 밖)에 놓여도 된다" in D.TIPS


@pytest.mark.parametrize("left", [-20, 190])
@pytest.mark.parametrize("label, near", [("deploy", 60), ("two-lines", 80)])
def test_sender_above_closer_than_the_tip_puts_the_label_on_the_outer_border_even_with_the_bend(left, label, near):
    # 요령의 꺾는 점을 줘도, 한 줄 글자는 바깥 노드 윗변에서 60px(기본 세로 간격)만, 두 줄 글자는 한 줄 기준 80px만 떼면 선
    # 글자가 바깥 노드 테두리에 걸린다. 요령대로(80px, 줄마다 15px 더) 떼면 합격한다
    make, lines = LABELS[label]
    sender = el("artifact", "w", 0, 0)
    close, far = above(OUTER, sender, left, near), above(OUTER, sender, left, above_gap(lines))
    (f,) = report([close, *OUTER], [make("w", "Tomcat", via=tip_bend(OUTER, close))]).failures
    assert f.kind == "text_on_box" and f.elements == ("w->Tomcat", "App Server")
    assert report([far, *OUTER], [make("w", "Tomcat", via=tip_bend(OUTER, far))]).passed
    assert "바깥 노드 윗변에서 80px 이상 떼어(선 글자가 여러 줄이면 한 줄마다 15px 더)" in D.TIPS


def test_returned_places_draw_the_same_picture():
    d = draw(FOUR, PATHS)
    again = [{**e, "left": p.rect[0], "top": p.rect[1], "width": p.width, "height": p.height}
             for e, p in zip(FOUR, d.layout.boxes)]
    assert [repr(r) for r in draw(again, PATHS).canvas.records] == [repr(r) for r in d.canvas.records]
