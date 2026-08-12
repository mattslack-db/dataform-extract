import subprocess
from pathlib import Path

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
