from __future__ import annotations

from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, ListItem, ListView, Sparkline

from db import add_todo, connect_db, list_completed_counts_by_day, list_todos, update_status


class TodoListItem(ListItem):
    def __init__(self, todo_id: int, text: str, status: str) -> None:
        super().__init__(Label(text))
        self.todo_id = todo_id
        self.status = status


class TodoApp(App):
    CSS = """
    Screen {
        background: #0b0b0b;
        color: #d0d0d0;
    }
    #lists {
        height: 2fr;
    }
    #app-title {
        padding: 1 1 0 1;
        color: #f0f0f0;
        text-style: bold;
        text-align: center;
    }
    .pane {
        width: 1fr;
        padding: 0 1;
    }
    .pane ListView {
        height: 1fr;
        border: solid #3a3a3a;
        background: transparent;
    }
    .pane ListView:focus {
        border: solid #5f5f5f;
    }
    .title {
        padding: 0 1;
        color: #a0a0a0;
        text-align: center;
        width: 100%;
    }
    #sparkline-panel {
        height: 1fr;
        padding: 0 1;
    }
    #sparkline-title {
        text-align: center;
        color: #a0a0a0;
        width: 100%;
    }
    #completed-sparkline {
        height: 1fr;
    }
    ListView > ListItem {
        padding: 0 1;
    }
    ListView > ListItem.--highlight {
        background: transparent;
        color: #f0f0f0;
        text-style: bold;
    }
    #new-task-input {
        margin: 0 1;
        border: solid #3a3a3a;
    }
    #footer-help {
        height: 1;
        background: transparent;
        color: #c0c0c0;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("h", "focus_left", "Focus Todo list"),
        ("l", "focus_right", "Focus Done list"),
        ("j", "move_down", "Move down"),
        ("k", "move_up", "Move up"),
        ("f", "flip_state", "Flip state"),
        ("n", "new_task", "New task"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.connection = connect_db()

    def compose(self) -> ComposeResult:
        yield Label("5am", id="app-title")
        with Horizontal(id="lists"):
            with Vertical(classes="pane"):
                yield Label("Todo", classes="title")
                yield ListView(id="todo-list")
            with Vertical(classes="pane"):
                yield Label("Done", classes="title")
                yield ListView(id="done-list")
        with Vertical(id="sparkline-panel"):
            yield Label("Completed per day", id="sparkline-title")
            yield Sparkline(id="completed-sparkline")
        yield Input(placeholder="New task…", id="new-task-input")
        yield Label("h/l switch lists  •  j/k move  •  f flip item  •  n new task", id="footer-help")

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
        self.refresh_sparkline()

    def refresh_sparkline(self) -> None:
        sparkline = self.query_one("#completed-sparkline", Sparkline)
        sparkline.data = list_completed_counts_by_day(self.connection)

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

    def action_new_task(self) -> None:
        self.query_one("#new-task-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "new-task-input":
            return
        text = event.value.strip()
        if not text:
            return
        add_todo(self.connection, text)
        event.input.value = ""
        self.refresh_lists()
        self.query_one("#todo-list", ListView).focus()


def main() -> None:
    app = TodoApp()
    app.run()


if __name__ == "__main__":
    main()
