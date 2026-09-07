# Project workflow

- Before starting work, verify that `origin` is `https://github.com/lucidcoach/lucid-platform.git`, fetch `origin/main`, and fast-forward the current folder to the latest version. Never overwrite local changes; report conflicts instead.
- After changes, run the relevant tests and error checks.
- If checks pass, commit and push to GitHub without requesting separate approval, unless the user explicitly says not to upload.
- Do not push when tests fail, Git conflicts exist, or a known deployment check is failing. Report the failure to the user.
- After pushing, check Render and GitHub Pages deployment status when either is configured, and report any deployment failure.
- Ask before destructive or high-risk work such as deleting or resetting a database, changing environment variables, or making a large structural change.
