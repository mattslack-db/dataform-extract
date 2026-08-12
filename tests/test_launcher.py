import subprocess
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "dataform-extract"

def test_launcher_version():
    result = subprocess.run([str(LAUNCHER), "--version"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "dataform-extract 0.1.0"

def test_launcher_help_mentions_repo_flag():
    result = subprocess.run([str(LAUNCHER), "--help"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "--repo" in result.stdout
