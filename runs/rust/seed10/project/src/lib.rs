// lib.rs is not strictly necessary for a binary-only crate, but good practice if we want to test logic.
// However, the prompt asks for a binary target. We can put tests in main.rs or a tests/ directory.
// Let's create a tests directory for integration tests as requested ("unit tests for validation rules").
// Actually, unit tests are best in the same file or mod tests. Let's put them in main.rs for simplicity
// or in a separate test module. Given the "return every file" constraint, I'll put tests in src/main.rs
// under a `#[cfg(test)]` module.
