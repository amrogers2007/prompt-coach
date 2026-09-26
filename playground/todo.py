"""A tiny command-line to-do list.

Usage:
    python todo.py add "Buy milk"
    python todo.py list
    python todo.py done 1
    python todo.py remove 1
    python todo.py clear      (removes all completed items)
"""

import json
import sys
from pathlib import Path

TODO_FILE = Path(__file__).with_name("todos.json")


def load():
    if TODO_FILE.exists():
        return json.loads(TODO_FILE.read_text(encoding="utf-8"))
    return []


def save(todos):
    TODO_FILE.write_text(json.dumps(todos, indent=2), encoding="utf-8")


def show(todos):
    if not todos:
        print("Nothing to do. Add one with: python todo.py add \"Your task\"")
        return
    for i, todo in enumerate(todos, start=1):
        mark = "x" if todo["done"] else " "
        print(f"{i}. [{mark}] {todo['text']}")


def pick(todos, arg):
    try:
        index = int(arg) - 1
    except ValueError:
        sys.exit(f"'{arg}' isn't a number. Use the number shown by 'list'.")
    if not 0 <= index < len(todos):
        sys.exit(f"There's no item {arg}. Run 'list' to see your items.")
    return index


def main(args):
    todos = load()
    command = args[0] if args else "list"

    if command == "add" and len(args) > 1:
        todos.append({"text": " ".join(args[1:]), "done": False})
        save(todos)
        print(f"Added: {todos[-1]['text']}")
    elif command == "list":
        show(todos)
    elif command == "done" and len(args) == 2:
        todo = todos[pick(todos, args[1])]
        todo["done"] = True
        save(todos)
        print(f"Done: {todo['text']}")
    elif command == "remove" and len(args) == 2:
        todo = todos.pop(pick(todos, args[1]))
        save(todos)
        print(f"Removed: {todo['text']}")
    elif command == "clear":
        remaining = [todo for todo in todos if not todo["done"]]
        save(remaining)
        print(f"Cleared {len(todos) - len(remaining)} completed item(s).")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
