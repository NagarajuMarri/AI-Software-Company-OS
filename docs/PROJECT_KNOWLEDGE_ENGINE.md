# Project Knowledge Engine

The Project Knowledge Engine builds deterministic structural knowledge for a
registered project: repositories, directories, text files, languages, Python
symbols, imports, exports, dependencies, categories, and statistics. It is not
semantic AI and does not modify product repositories.

The scanner walks available local repository paths in stable order, excludes
version-control, cache, dependency, build, binary, and practical `.gitignore`
matches, and reads text as UTF-8. Python uses the standard `ast` module.
JavaScript and TypeScript use bounded deterministic syntax matching. JSON is
validated; YAML, TOML, Markdown, Dockerfiles, and requirements files are
classified and measured without adding parser dependencies.

`ProjectKnowledgeEngine` exposes `scan`, `repositories`, `files`, `modules`,
`classes`, `functions`, `dependencies`, `languages`, `statistics`, `find_file`,
`find_symbol`, `find_imports`, `find_dependents`, and `summary`. Multiple
repository tuples may be passed explicitly to `scan`; project identity always
comes from the Project Registry.

Knowledge is atomically stored as sorted, indented, schema-versioned UTF-8 JSON
at `<state-root>/knowledge/<project-id>/knowledge.json`. Storage is never
redirected into a managed repository.

```text
python -m runtime.knowledge.cli --registry projects.json --state-root .ascos knowledge scan project-id
python -m runtime.knowledge.cli --registry projects.json --state-root .ascos --json knowledge stats project-id
python -m runtime.knowledge.cli --registry projects.json --state-root .ascos knowledge find project-id SymbolName
```

Current limitations include no graph database, semantic inference, LLM calls,
autonomous coding, deep JavaScript/TypeScript AST, YAML/TOML semantic parsing,
or cross-language symbol resolution. Future reviewed LLM features may consume
this persisted structural layer without changing its deterministic boundary.
