# Project workflow

- Before starting work, fetch and fast-forward from the GitHub remote so the working tree is current. If local changes or a conflict make that unsafe, stop and report it.
- After changes, run the relevant tests and error checks.
- If checks pass, commit and push to GitHub without requesting separate approval, unless the user explicitly says not to upload.
- If tests fail or a Git conflict exists, do not push; report the failure.
- After pushing, check GitHub Pages or any connected deployment and report deployment failures.
- Ask before destructive or high-risk work such as deleting or resetting a database, changing environment variables, or making a large structural change.
