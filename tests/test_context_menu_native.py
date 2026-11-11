"""Record-aware Axiom right-click should not hijack the native editor menu."""
from __future__ import annotations

from superforge.context_menu import menu_for


def test_record_context_suggestions_are_real_registered_paths():
    rows=menu_for("job","52","job_tracker")
    keys=[r["key"] for r in rows]
    assert keys[:5]==["job_tracker","ez_methods","quality","inventory","clocking"]
    assert all(x["suggested"] for x in rows[:5])
    assert all(x["href"].endswith("context_type=job&context_id=52") for x in rows)
    assert sum(item["current"] for item in rows)==1
    assert "bean" in keys
    assert "reports" in keys

    document=menu_for("document","21","vault")
    assert [r["key"] for r in document[:4]]==["vault","ezfair","ez_methods","quality"]
    sheet=menu_for("sheet_book","7","sheets")
    assert [r["key"] for r in sheet[:4]]==["sheets","accounting","payroll","reports"]


def test_native_right_click_preserved_for_editable_and_nonrecord_surfaces(tmp_path,monkeypatch):
    monkeypatch.setenv("AXIOM_DATA_DIR",str(tmp_path/"context"))
    from superforge.app import create_app
    client=create_app({"TESTING":True}).test_client()
    doc=client.get("/sheets").get_data(as_text=True)
    # Source-policy assertions accompany the backend tests; these do not
    # substitute for a real browser integration acceptance test.
    assert "e.target.closest('a,button,input,textarea,select,[contenteditable],[role=\"textbox\"]')" in doc
    assert "if(!target || !target.dataset.entityType || !target.dataset.entityId)return" in doc
    assert doc.index("if(!target || !target.dataset.entityType || !target.dataset.entityId)return")<doc.index("e.preventDefault(); closeMenu();")
    assert 'Right-click records' in doc
    assert "data-pin-current-module" in doc
    assert "result.saved!==true" in doc

    response=client.get("/api/context-menu?entity_type=sheet_book&entity_id=7&current_module=sheets")
    assert response.status_code==200
    data=response.get_json()["items"]
    assert data[0]["key"]=="sheets"
    assert data[0]["suggested"]
