"""The notebook runs top to bottom on the synthetic fixtures (no key, no network).  pytest -q"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

nbformat = pytest.importorskip("nbformat")
pytest.importorskip("nbconvert")
from nbconvert.preprocessors import ExecutePreprocessor              # noqa: E402


def test_notebook_executes_in_fixture_mode(monkeypatch, tmp_path):
    # Run on THIS interpreter's kernel, not whatever "python3" kernel the user's Jupyter has registered.
    import sys
    monkeypatch.setenv("JUPYTER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JUPYTER_PATH", os.path.join(sys.prefix, "share", "jupyter"))
    monkeypatch.setenv("PYTHONPATH", ROOT)
    monkeypatch.setenv("PE_USE_FIXTURES", "1")
    monkeypatch.setenv("MPLBACKEND", "Agg")
    monkeypatch.delenv("PUNTERSEDGE_API_KEY", raising=False)
    with open(os.path.join(ROOT, "research.ipynb"), encoding="utf-8") as fh:
        nb = nbformat.read(fh, as_version=4)
    ExecutePreprocessor(timeout=120, kernel_name="python3").preprocess(nb, {"metadata": {"path": ROOT}})
    text = "\n".join(o.get("text", "") for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", []))
    assert "FIXTURES (synthetic data, not real races)" in text
    assert "4 of 5 priced races joined to a result on race_id." in text
    assert "no API calls, no credits" in text


def test_committed_notebook_has_no_outputs():
    with open(os.path.join(ROOT, "research.ipynb"), encoding="utf-8") as fh:
        nb = nbformat.read(fh, as_version=4)
    assert all(not c.get("outputs") for c in nb.cells if c.cell_type == "code")
