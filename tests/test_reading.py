import subprocess
import sys

from cysuml import classdiagram as C
from cysuml import reading as R
from cysuml import sequencediagram as S


def test_both_diagrams_raise_the_shared_input_error():
    assert C.InputError is R.InputError and S.InputError is R.InputError


def test_sequence_diagram_does_not_load_class_diagram():
    code = "import sys, cysuml.sequencediagram; print('cysuml.classdiagram' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "False"
