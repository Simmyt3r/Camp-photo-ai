# Security tests (planned)

Section 28: path-traversal attempts via participant names (see
`tests/unit/test_file_utils.py::TestSafeOutputPath` for the unit-level
version of this), safe deletion, and confirming raw embeddings never
reach the logs (`app/utilities/logging_config.py::RedactBiometricFilter`).

A dedicated fuzz/adversarial-input pass against the CLI and (once built)
the GUI belongs here.
