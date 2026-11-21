from fastapi.testclient import TestClient

from warrantworks.api import create_app


def test_http_workflow(tmp_path, forms):
    c = TestClient(create_app(tmp_path / "d"))
    H = {"X-Actor": "API Clerk"}
    assert c.post("/api/families", json={"name": "x", "form_type": "criminal_summons"}).status_code == 400  # no name
    fam = c.post("/api/families", json={"name": "Summons test", "form_type": "criminal_summons"}, headers=H).json()
    ids = {}
    for v in ("reference", "agency_a", "agency_b"):
        name, data = forms[v]
        r = c.post(f"/api/families/{fam['id']}/documents", headers=H,
                   files={"file": (name, data)}, data={"role": "approved_master" if v == "reference" else "version", "label": v})
        assert r.status_code == 200, r.text
        ids[v] = r.json()["id"]
    assert c.get(f"/api/documents/{ids['agency_a']}/pages/0.png").headers["content-type"] == "image/png"
    cmp_ = c.post(f"/api/families/{fam['id']}/comparisons", headers=H,
                  json={"version_ids": [ids["agency_a"], ids["agency_b"]], "base_id": ids["agency_a"], "master_id": ids["reference"]}).json()
    it = cmp_["items"][0]
    src = next(s for v in it["variants"] for s in v["sources"] if s["segs"])
    hl = c.get(f"/api/documents/{src['doc']}/highlight", params={"segs": ",".join(map(str, src["segs"]))}).json()
    assert hl["segments"][0]["rect"] and 0 <= hl["segments"][0]["rect"][0] <= 1
    assert c.post(f"/api/comparisons/{cmp_['id']}/revisions", headers=H, json={}).status_code == 400
    assert c.post(f"/api/comparisons/{cmp_['id']}/accept", headers=H, json={"scope": "all"}).json()["accepted"] == len(cmp_["items"])
    rev = c.post(f"/api/comparisons/{cmp_['id']}/revisions", headers=H, json={"note": "n"}).json()
    ex = c.post(f"/api/revisions/{rev['id']}/exports", headers=H, json={"format": "pdf"}).json()
    assert ex["verification"]["passed"]
    f = c.get(f"/api/exports/{ex['id']}/file")
    assert f.content[:5] == b"%PDF-" and "attachment" in f.headers["content-disposition"]
    assert c.get("/api/audit/verify").json()["ok"]
    assert c.get("/").status_code == 200 and "WarrantWorks TN" in c.get("/").text
