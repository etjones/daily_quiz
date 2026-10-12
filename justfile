default:
    @just --list

run *args:
    uv run dq {{args}}

test *args:
    uv run pytest -q {{args}}

watch:
    uv run --with pytest-watcher ptw . --now

validate:
    uv run dq validate

status:
    uv run dq status

skills *args:
    uv run dq skills {{args}}

init name:
    uv run dq init {{name}}

placement name:
    uv run dq placement {{name}}

oral name:
    uv run dq oral {{name}}

grade name photo:
    uv run dq grade {{name}} {{photo}}

mood name level *args:
    uv run dq mood {{name}} {{level}} {{args}}

next name:
    uv run dq next {{name}}

report name:
    uv run dq report {{name}} --pdf

lint:
    uvx ruff check .
