"""Suite status colors carry meanings, not just brand decoration."""
from superforge.app import table_html

def test_review_required_is_not_approved_green():
    html=table_html([{"status":"review_required"}],[("status","Status")],"fai")
    assert "badge pending" in html
    assert "badge good" not in html
    assert "badge accent" not in html

def test_success_and_failure_have_distinct_style():
    html=table_html([{"status":"complete"},{"status":"failed"}],
                    [("status","Status")],"fai")
    assert "badge good" in html and "badge danger" in html

def test_default_gothic_lime_style():
    from pathlib import Path
    css=(Path(__file__).resolve().parents[1]/"superforge"/"ui.py").read_text()
    assert "#79DE4B" in css and "--bg:#0F1113" in css
    assert ".badge.pending" in css and ".badge.good" in css
