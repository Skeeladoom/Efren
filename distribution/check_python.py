"""Non-mutating import/protocol check using only the staged interpreter."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def check(staging):
    staging = Path(staging).resolve()
    python = staging / "runtime/python/python.exe"
    env = {key.upper(): value for key, value in os.environ.items()}
    for key in ("PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PATH"] = str(Path(env["SYSTEMROOT"]) / "System32")
    probe = (
        "import sys,json,tkinter,PIL,pymorphy3,panel_backend; "
        "from pathlib import Path; "
        "root=Path.cwd(); "
        "assert Path(sys.executable).resolve().is_relative_to(root); "
        "assert Path(PIL.__file__).resolve().is_relative_to(root); "
        "assert panel_backend.panel.worker_python_path()==Path(sys.executable); "
        "tk=tkinter.Tk(); tk.withdraw(); tk.update(); tk.destroy(); "
        "assert pymorphy3.MorphAnalyzer().parse('диме')[0].normal_form == 'дима'; "
        "print(json.dumps({'python':sys.version.split()[0],'pillow':PIL.__version__,'pymorphy3':pymorphy3.__version__})); "
        "panel_backend.serve()"
    )
    result = subprocess.run([str(python), "-s", "-c", probe], cwd=staging, env=env,
                            input='{"action":"not-authorized-test"}\n',
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr)
    lines = result.stdout.strip().splitlines()
    versions = json.loads(lines[0])
    response = json.loads(lines[-1])
    assert response["ok"] is False and "пароль" in response["error"]
    print("PASS: bundled Python", versions["python"], "; Pillow", versions["pillow"], "; pymorphy3", versions["pymorphy3"],
          "; Tk; backend imports; bundled worker selection; protected stdio protocol.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging")
    check(parser.parse_args().staging)
