import json
from pathlib import Path

import pytest

from runtime.knowledge import *
from runtime.knowledge.cli import main as cli_main
from runtime.knowledge.errors import *
from runtime.projects import FileProjectRegistry, InMemoryProjectRegistry, ManagedProject


def project(project_id, root):
    return ManagedProject(project_id, project_id, "Test project",
                          f"https://example.com/{project_id}", "main", local_path=str(root))


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"; root.mkdir()
    (root / "app.py").write_text(
        '"""Module docs."""\nimport os\nfrom lib import helper\n\n'
        '@staticmethod\nclass Public:\n    """Class docs."""\n    def method(self):\n        return 1\n\n'
        'def main():\n    return helper()\n\n_PRIVATE = 1\nCONSTANT = 2\n', encoding="utf-8")
    (root / "lib.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (root / "README.md").write_text("# Sample\n", encoding="utf-8")
    (root / "package.json").write_text('{"dependencies":{"x":"1"}}', encoding="utf-8")
    tests = root / "tests"; tests.mkdir()
    (tests / "test_app.py").write_text("from app import main\n", encoding="utf-8")
    return root


@pytest.fixture
def engine(tmp_path, repository):
    registry = InMemoryProjectRegistry((project("sample", repository),))
    value = ProjectKnowledgeEngine.create("sample", registry, KnowledgeStore(tmp_path / "state"))
    value.scan()
    return value


def test_scanner_collects_files_directories_and_languages(engine):
    assert [x.path for x in engine.files()] == sorted(x.path for x in engine.files())
    assert len(engine.files()) == 5
    assert {x.language for x in engine.files()} >= {"Python", "Markdown", "JSON"}
    assert engine.statistics().directories == 1


def test_python_ast_extracts_symbols_methods_docs_decorators(engine):
    public = engine.find_symbol("Public")[0]
    method = engine.find_symbol("method")[0]
    assert public.kind == "class"
    assert public.docstring == "Class docs."
    assert public.decorators == ("staticmethod",)
    assert method.kind == "method"
    assert method.parent == "Public"


def test_python_extracts_imports_constants_and_qualified_names(engine):
    assert {x.target for x in engine.dependencies()} >= {"os", "lib"}
    constant = engine.find_symbol("CONSTANT")[0]
    assert constant.kind == "constant"
    assert constant.qualified_name == "app.CONSTANT"


def test_python_private_flag(tmp_path):
    (tmp_path / "a.py").write_text("def _private():\n    pass\n", encoding="utf-8")
    symbol = RepositoryScanner().scan("x", tmp_path).files[0].symbols[0]
    assert symbol.public is False


def test_javascript_typescript_import_export_and_symbols(tmp_path):
    (tmp_path / "a.ts").write_text(
        "import x from 'pkg';\nexport class Example {}\nexport function run() {}\n",
        encoding="utf-8")
    repo = RepositoryScanner().scan("r", tmp_path)
    file = repo.files[0]
    assert file.language == "TypeScript"
    assert file.imports[0].module == "pkg"
    assert [x.name for x in file.symbols] == ["Example", "run"]
    assert [x.name for x in file.exports] == ["Example", "run"]


@pytest.mark.parametrize(("name", "language"), [
    ("data.yaml", "YAML"), ("data.yml", "YAML"), ("config.toml", "TOML"),
    ("Dockerfile", "Dockerfile"), ("requirements.txt", "Requirements"),
    ("index.js", "JavaScript"), ("index.ts", "TypeScript")])
def test_supported_file_classification(tmp_path, name, language):
    (tmp_path / name).write_text("value\n", encoding="utf-8")
    assert RepositoryScanner().scan("r", tmp_path).files[0].language == language


def test_malformed_python_and_json_are_retained_and_marked(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(", encoding="utf-8")
    (tmp_path / "bad.json").write_text("{broken", encoding="utf-8")
    files = RepositoryScanner().scan("r", tmp_path).files
    assert all(x.malformed for x in files)


def test_binary_files_are_excluded(tmp_path):
    (tmp_path / "binary.dat").write_bytes(b"a\x00b")
    assert RepositoryScanner().scan("r", tmp_path).files == ()


def test_fixed_ignored_directories_are_excluded(tmp_path):
    ignored = tmp_path / "node_modules"; ignored.mkdir()
    (ignored / "x.js").write_text("function ignored() {}", encoding="utf-8")
    assert RepositoryScanner().scan("r", tmp_path).files == ()


def test_gitignore_patterns_are_respected(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored.py\ncache/\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("def ignored(): pass", encoding="utf-8")
    cache = tmp_path / "cache"; cache.mkdir()
    (cache / "x.py").write_text("def x(): pass", encoding="utf-8")
    paths = [x.path for x in RepositoryScanner().scan("r", tmp_path).files]
    assert paths == [".gitignore"]


def test_categories_and_statistics(engine):
    stats = engine.statistics()
    assert stats.tests == 1
    assert stats.documentation == 1
    assert stats.configuration == 1
    assert stats.classes == 1
    assert stats.functions == 3
    assert stats.largest_files[0] == "app.py"


def test_package_json_dependencies_are_edges(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"z":"1","a":"1"},"devDependencies":{"test":"1"}}',
        encoding="utf-8")
    assert [x.target for x in RepositoryScanner().scan("r", tmp_path).dependencies] == [
        "a", "test", "z"]


def test_requirements_dependencies_are_edges(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "# comment\nrequests==2\npytest>=8\n-r base.txt\n", encoding="utf-8")
    assert [x.target for x in RepositoryScanner().scan("r", tmp_path).dependencies] == [
        "pytest", "requests"]


@pytest.mark.parametrize(("path", "category"), [
    ("docs/guide.md", "documentation"),
    ("tests/unit.py", "test"),
    ("migrations/001.sql", "migration"),
    (".github/workflows/ci.yml", "configuration"),
    (".env", "environment"),
    ("logo.svg", "asset"),
])
def test_structural_categories(tmp_path, path, category):
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("content", encoding="utf-8")
    assert RepositoryScanner().scan("r", tmp_path).files[0].category == category


def test_find_queries_and_dependents(engine):
    assert engine.find_file("app.py")[0].module == "app"
    assert engine.find_symbol("main")[0].name == "main"
    assert engine.find_dependents("lib") == ("app.py",)
    assert engine.find_imports("lib")[0].source == "app.py"


def test_empty_repository(tmp_path):
    registry = InMemoryProjectRegistry((project("empty", tmp_path),))
    engine = ProjectKnowledgeEngine.create("empty", registry, KnowledgeStore(tmp_path / "state"))
    engine.scan()
    assert engine.statistics().files == 0
    assert engine.summary()["languages"] == {}


def test_multiple_repositories_are_deterministically_ordered(tmp_path):
    first = tmp_path / "a"; second = tmp_path / "b"
    first.mkdir(); second.mkdir()
    (first / "a.py").write_text("A = 1", encoding="utf-8")
    (second / "b.py").write_text("B = 2", encoding="utf-8")
    registry = InMemoryProjectRegistry((project("multi", first),))
    engine = ProjectKnowledgeEngine.create("multi", registry, KnowledgeStore(tmp_path / "state"))
    engine.scan((("z", second), ("a", first)))
    assert [x.repository_id for x in engine.repositories()] == ["a", "z"]


def test_unavailable_repository_fails_without_state_mutation(tmp_path):
    registry = InMemoryProjectRegistry((project("missing", tmp_path / "missing"),))
    engine = ProjectKnowledgeEngine.create("missing", registry, KnowledgeStore(tmp_path))
    before = engine.current()
    with pytest.raises(RepositoryUnavailableError):
        engine.scan()
    assert engine.current() == before


def test_project_without_local_path_fails_clearly(tmp_path):
    registry = InMemoryProjectRegistry((ManagedProject(
        "portable", "Portable", "No checkout", "https://example.com/portable", "main"),))
    with pytest.raises(RepositoryUnavailableError):
        ProjectKnowledgeEngine.create("portable", registry, KnowledgeStore(tmp_path)).scan()


def test_save_load_round_trip_is_deterministic(engine):
    engine.save()
    path = engine.store.path_for("sample")
    first = path.read_text(encoding="utf-8")
    loaded = ProjectKnowledgeEngine.load("sample",
        InMemoryProjectRegistry((engine.project,)), engine.store)
    assert loaded.current() == engine.current()
    loaded.save()
    assert path.read_text(encoding="utf-8") == first
    assert json.loads(first)["schema_version"] == 1
    assert not list(path.parent.glob("*.tmp"))


def test_missing_corrupt_and_future_storage(tmp_path, repository):
    store = KnowledgeStore(tmp_path / "state")
    registry = InMemoryProjectRegistry((project("sample", repository),))
    with pytest.raises(KnowledgeNotFoundError):
        ProjectKnowledgeEngine.load("sample", registry, store)
    path = store.path_for("sample"); path.parent.mkdir(parents=True)
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(KnowledgeCorruptError):
        ProjectKnowledgeEngine.load("sample", registry, store)
    path.write_text('{"schema_version":99}', encoding="utf-8")
    with pytest.raises(UnsupportedKnowledgeSchemaError):
        ProjectKnowledgeEngine.load("sample", registry, store)


def test_storage_is_project_isolated(tmp_path):
    store = KnowledgeStore(tmp_path)
    assert store.path_for("a") != store.path_for("b")
    assert store.path_for("a").parent.name == "a"


def test_large_fixture_is_ordered(tmp_path):
    for index in range(100):
        (tmp_path / f"file_{index:03}.py").write_text(f"VALUE_{index} = {index}\n", encoding="utf-8")
    repo = RepositoryScanner().scan("large", tmp_path)
    assert len(repo.files) == 100
    assert repo.files[0].path == "file_000.py"
    assert repo.files[-1].path == "file_099.py"


def test_cli_scan_stats_find_and_expected_error(tmp_path, repository, capsys):
    registry_path = tmp_path / "registry.json"
    FileProjectRegistry(registry_path).register(project("cli", repository))
    prefix = ["--registry", str(registry_path), "--state-root", str(tmp_path / "state")]
    assert cli_main(prefix + ["knowledge", "scan", "cli"]) == 0
    assert cli_main(prefix + ["--json", "knowledge", "stats", "cli"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["files"] == 5
    assert cli_main(prefix + ["--json", "knowledge", "find", "cli", "main"]) == 0
    assert json.loads(capsys.readouterr().out)["symbols"][0]["name"] == "main"
    assert cli_main(prefix + ["knowledge", "summary", "missing"]) == 2
    assert capsys.readouterr().out.startswith("error:")
