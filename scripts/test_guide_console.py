"""Finite pytest entrypoint with normal inherited Windows temp ACLs."""
from pathlib import Path
import uuid
import pytest

root = Path('.code2guide/console-test-output').resolve()
root.mkdir(parents=True, exist_ok=True)

class LocalTemp:
    @pytest.fixture
    def tmp_path(self):
        directory = root / uuid.uuid4().hex
        directory.mkdir()
        return directory

raise SystemExit(pytest.main(['tests/test_contracts_guide_lab.py', 'tests/test_guide_lab_console.py', 'tests/test_guide_lab_editor.py', '-q', '-p', 'no:cacheprovider'], plugins=[LocalTemp()]))
