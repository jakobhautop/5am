from __future__ import annotations

from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, ListItem, ListView

from db import connect_db, list_todos, update_status


class TodoListItem(ListItem):
    def __init__(self, todo_id: int, text: str, status: str) -> None:
        super().__init__(Label(text))
        self.todo_id = todo_id
        self.status = status


class TodoApp(App):
    CSS = """
    #lists {
        height: 1fr;
    }
    .pane {
        width: 1fr;
        padding: 1 2;
    }
    .pane ListView {
        height: 1fr;
        border: round $accent;
    }
    .title {
        padding-bottom: 1;
    }
    """

    BINDINGS = [
        ("h", "focus_left", "Focus Todo list"),
        ("l", "focus_right", "Focus Done list"),
        ("j", "move_down", "Move down"),
        ("k", "move_up", "Move up"),
        ("f", "flip_state", "Flip state"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.connection = connect_db()

    def compose(self) -> ComposeResult:
        with Horizontal(id="lists"):
            with Vertical(classes="pane"):
                yield Label("Todo", classes="title")
                yield ListView(id="todo-list")
            with Vertical(classes="pane"):
                yield Label("Done", classes="title")
                yield ListView(id="done-list")

    def on_mount(self) -> None:
        self.refresh_lists()
        self.query_one("#todo-list", ListView).focus()

    def refresh_lists(self) -> None:
        todo_list = self.query_one("#todo-list", ListView)
        done_list = self.query_one("#done-list", ListView)
        todo_list.clear()
        done_list.clear()
        for record in list_todos(self.connection, "todo"):
            todo_list.append(TodoListItem(record.todo_id, record.text, record.status))
        for record in list_todos(self.connection, "done"):
            done_list.append(TodoListItem(record.todo_id, record.text, record.status))

    def get_active_list(self) -> ListView:
        focused = self.focused
        if isinstance(focused, ListView) and focused.id in {"todo-list", "done-list"}:
            return focused
        return self.query_one("#todo-list", ListView)

    def get_highlighted_item(self, list_view: ListView) -> Optional[TodoListItem]:
        index = getattr(list_view, "highlighted", None)
        if index is None:
            index = getattr(list_view, "index", None)
        if index is None:
            return None
        try:
            item = list_view.children[index]
        except (IndexError, TypeError):
            return None
        if isinstance(item, TodoListItem):
            return item
        return None

    def action_focus_left(self) -> None:
        self.query_one("#todo-list", ListView).focus()

    def action_focus_right(self) -> None:
        self.query_one("#done-list", ListView).focus()

    def action_move_down(self) -> None:
        list_view = self.get_active_list()
        move = getattr(list_view, "action_cursor_down", None)
        if move:
            move()

    def action_move_up(self) -> None:
        list_view = self.get_active_list()
        move = getattr(list_view, "action_cursor_up", None)
        if move:
            move()

    def action_flip_state(self) -> None:
        list_view = self.get_active_list()
        item = self.get_highlighted_item(list_view)
        if not item:
            return
        new_status = "done" if item.status == "todo" else "todo"
        update_status(self.connection, item.todo_id, new_status)
        self.refresh_lists()
        list_view.focus()


def main() -> None:
    app = TodoApp()
    app.run()


if __name__ == "__main__":
    main()
