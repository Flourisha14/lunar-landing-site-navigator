"""Architecture smoke tests for the standalone lunar science engine."""

import ast
import importlib
from importlib.metadata import version
from pathlib import Path

import lunar_engine

SCIENTIFIC_MODULES = (
    "core",
    "astronomy",
    "coordinates",
    "terrain",
    "illumination",
    "communication",
    "analysis",
)

FORBIDDEN_IMPORT_ROOTS = {
    "fastapi",
    "react",
    "cesium",
    "babylon",
    "three",
    "unreal",
}


def test_scientific_modules_import() -> None:
    """Verify every scientific subsystem is independently importable."""
    for module_name in SCIENTIFIC_MODULES:
        module = importlib.import_module(f"lunar_engine.{module_name}")
        assert module.__name__ == f"lunar_engine.{module_name}"


def test_package_version_matches_distribution() -> None:
    """Verify package and installed distribution versions agree."""
    assert lunar_engine.__version__ == version("lunar-landing-engine")


def test_scientific_engine_has_no_frontend_imports() -> None:
    """Verify scientific source files do not import rendering frameworks."""
    package_directory = Path(lunar_engine.__file__).parent

    for source_file in package_directory.rglob("*.py"):
        syntax_tree = ast.parse(
            source_file.read_text(encoding="utf-8-sig"),
            filename=str(source_file),
        )

        for node in ast.walk(syntax_tree):
            imported_modules: list[str] = []

            if isinstance(node, ast.Import):
                imported_modules = [alias.name for alias in node.names]

            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    imported_modules = [node.module]

            for imported_module in imported_modules:
                import_root = imported_module.split(".")[0]

                assert import_root not in FORBIDDEN_IMPORT_ROOTS, (
                    f"Forbidden dependency '{import_root}' found in {source_file}"
                )
