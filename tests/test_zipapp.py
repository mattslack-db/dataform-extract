import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build-zipapp.sh"
ARTIFACT = ROOT / "dist" / "dataform-extract"

def test_build_zipapp_produces_runnable_artifact():
    build = subprocess.run([str(BUILD)], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    assert ARTIFACT.exists()
    ver = subprocess.run([str(ARTIFACT), "--version"], capture_output=True, text=True)
    assert ver.returncode == 0, ver.stderr
    assert ver.stdout.strip() == "dataform-extract 0.1.0"


def test_zipapp_propagates_nonzero_exit_code(tmp_path):
    build = subprocess.run([str(BUILD)], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    py_dir = str(Path(sys.executable).parent)
    env = dict(os.environ, PATH=f"{py_dir}:/usr/bin:/bin")
    if shutil.which("python3", path=env["PATH"]) is None:
        pytest.skip("python3 not resolvable on sanitized PATH")
    if shutil.which("gcloud", path=env["PATH"]) is not None:
        pytest.skip("gcloud present on sanitized PATH; cannot force AuthError")
    result = subprocess.run(
        [str(ARTIFACT), "--repo", "projects/p/locations/us/repositories/r",
         "--commitish", "main", "--out", str(tmp_path / "out")],
        capture_output=True, text=True, env=env)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
