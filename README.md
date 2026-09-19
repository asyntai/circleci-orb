# Asyntai knowledge sync orb for CircleCI

Keep the [Asyntai](https://asyntai.com) AI chatbot on your website current with
the documentation in your repository. Add one step to a pipeline. Every page you
change is in the chatbot's knowledge base by the end of the build, so visitors
get the answer that matches the version you just shipped.

Orb slug: `asyntai/knowledge-sync`

## Use it

```yaml
version: 2.1

orbs:
  asyntai: asyntai/knowledge-sync@1.0.0

workflows:
  publish-docs:
    jobs:
      - asyntai/sync:
          path: docs
          title-prefix: "Docs / "
          filters:
            branches:
              only: main
```

Or put the step inside a job you already have:

```yaml
      - asyntai/sync:
          path: build/html
          patterns: "*.html,*.md"
```

## Set up

1. Sign in to Asyntai, open **Settings**, then **API**, and copy your API key.
2. In CircleCI open **Project Settings**, then **Environment Variables**.
3. Add `ASYNTAI_API_KEY` with your key.

The API needs an Asyntai plan of Starter or higher.

## Parameters

| Name | Default | What it does |
| --- | --- | --- |
| `path` | required | The file or folder to read. |
| `patterns` | `*.md,*.mdx,*.txt` | Comma separated file patterns to include. |
| `exclude` | empty | Comma separated patterns to skip. |
| `title-prefix` | empty | Text put in front of every entry title. |
| `website-id` | empty | The Asyntai website to write to. Empty means your first one. |
| `api-key-var` | `ASYNTAI_API_KEY` | The environment variable that holds the key. |
| `base-url` | `https://asyntai.com` | Change this only for a private install. |
| `prune` | `false` | Remove entries with your prefix whose file is gone. Needs `title-prefix`. |
| `dry-run` | `false` | List the files and send nothing. |

## How the entries are named

Each file becomes one knowledge base entry. The title is the path of the file
inside `path`, with `title-prefix` in front. A file keeps the same title on
every run, so the step replaces the old entry with the new one. That lets the
pipeline run on every commit and still hold one entry per file.

A file whose text already matches the stored entry is left alone. So a run on a
day when the documentation did not change costs nothing against your daily
upload limit. Every run ends with a line like:

```
Done. 2 added, 1 updated, 14 unchanged, 0 deleted, 0 skipped.
```

## Several repositories, one chatbot

Give each repository its own `title-prefix`, for example `product-docs/` and
`handbook/`, then turn `prune` on. Each pipeline only touches the entries that
carry its own prefix.

```yaml
      - asyntai/sync:
          path: docs
          title-prefix: "product-docs/"
          prune: true
```

The step needs Python 3 in the image. The `asyntai/sync` job uses
`cimg/python` for you. If you call the `asyntai/sync` command inside your own
job, run it in an image that holds Python 3.

## Develop

```bash
python build.py                      # writes src/scripts/sync.sh from sync.py
circleci orb pack src > orb.yml
circleci orb validate orb.yml
python tests/run_tests.py orb.yml    # runs the shipped shell against a test API
```

`src/scripts/sync.py` is the one place to edit. `src/scripts/sync.sh` is
generated and must not be edited by hand.

## Publish

```bash
circleci namespace create asyntai github asyntai
circleci orb create asyntai/knowledge-sync
circleci orb publish orb.yml asyntai/knowledge-sync@1.0.0
```

## Licence

MIT. See `LICENSE`.
