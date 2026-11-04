# Local E5 retrieval

Runtime: sentence-transformers on CPU, SQLite FTS5 and sqlite-vec 0.1.6.
The trained 384-dimensional `snippet-e5-small` artifact must be placed in
`models/snippet-e5-small/` before building Docker, or selected with SEARCH_MODEL_PATH.
Weights are excluded from Git but included in the Docker build context.
Copy the complete exported model directory, including tokenizer and pooling files.
The local installation uses the artifact from the sibling snippet_stack_model project.
No runtime downloads or external inference services are used.

SEARCH_MODEL identifies the embedding version (default snippet-e5-small-v1).
Change it whenever replacing weights, then run `python manage.py index_search --rebuild`.
Both Compose services must use the same model and version. The background indexer
replaces old-model vectors automatically; --rebuild also repairs bulk updates.
Use `python manage.py index_search --watch` for local background indexing.

E5 inputs use `query: ` and `passage: ` prefixes, matching training. Documents
contain title, description, tags and code; the model truncates to its saved window.
Vectors remain in SearchDocument BLOBs. sqlite-vec computes exact cosine distances
inside SQLite after owner and UI filters, before LIMIT. This is a linear scan,
not an ANN index. BM25 and vector rankings are combined with RRF.
Edits invalidate vectors immediately; compare-and-swap protects concurrent indexing.
Missing models/extensions fall back to keyword search. Python must support SQLite
loadable extensions (the Docker Python image does); macOS builds without this feature use the bundled pysqlite3 dependency.
Extension loading is enabled only around loading the installed sqlite_vec library.

Validation: `RUN_SEMANTIC_TESTS=1 python manage.py test snippets.test_search`.
See https://github.com/asg017/sqlite-vec/blob/main/examples/simple-python/demo.py
for the extension loading API.
