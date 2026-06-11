from app.web.sparkline import sparkline_svg


def test_empty_series_is_placeholder():
    svg = sparkline_svg([])
    assert svg.startswith("<svg") and "polyline" not in svg


def test_series_renders_polyline_with_n_points():
    svg = sparkline_svg([10.0, 20.0, 15.0], width=100, height=20)
    assert "polyline" in svg
    # three coordinate pairs in the polyline
    points = svg.split('points="')[1].split('"')[0]
    assert len(points.split()) == 3
    # last point marked with a dot
    assert "<circle" in svg


def test_flat_series_does_not_divide_by_zero():
    svg = sparkline_svg([5.0, 5.0, 5.0])
    assert "polyline" in svg
