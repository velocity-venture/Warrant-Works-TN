import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import synthetic_forms as sf  # noqa: E402
from warrantworks.db import Store  # noqa: E402
from warrantworks.service import Harmonizer  # noqa: E402

ACTOR = "Test Clerk"


@pytest.fixture(scope="session")
def forms():
    return sf.build_set()


@pytest.fixture()
def hz(tmp_path):
    return Harmonizer(Store(tmp_path / "data"))


def load_family(h, forms, with_requirements=True):
    fam = h.create_family("Synthetic Arrest Warrant", "arrest_warrant", "test", ACTOR)
    ids = {}
    for v, (name, data) in forms.items():
        role = "approved_master" if v == "reference" else "version"
        ids[v] = h.add_document(fam["id"], name, data, role, v, ACTOR)["id"]
    if with_requirements:
        for t in sf.REQUIRED_TEST_PASSAGES:
            h.add_requirement(fam["id"], t, "historical test wording", ACTOR)
    return fam, ids


@pytest.fixture(scope="session")
def loaded(tmp_path_factory, forms):
    """One fully loaded family (uploads are the slow part because of OCR)."""
    h = Harmonizer(Store(tmp_path_factory.mktemp("shared") / "data"))
    fam, ids = load_family(h, forms)
    return h, fam, ids
