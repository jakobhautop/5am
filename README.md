# 5am

Terminal todo app built with Textual.

## Usage

Install with uv and run:

```bash
uv tool install .
5am
```

## Data storage

Todos are stored in a SQLite database at:

* `$XDG_DATA_HOME/5am/5am.db` when `XDG_DATA_HOME` is set
* otherwise `~/.local/share/5am/5am.db`
