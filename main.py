from __future__ import annotations

from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView

from db import add_todo, connect_db, list_todos, update_status


class TodoListItem(ListItem):
    def __init__(self, todo_id: int, text: str, status: str) -> None:
        super().__init__(Label(text))
        self.todo_id = todo_id
        self.status = status


class NewTaskScreen(ModalScreen[Optional[str]]):
    CSS = """
    NewTaskScreen {
        align: center middle;
    }
    #dialog {
        width: 60%;
        max-width: 60;
        border: solid #3a3a3a;
        background: #0b0b0b;
        padding: 1 2;
    }
    #dialog Label {
        color: #c0c0c0;
        padding-bottom: 1;
    }
    #dialog Input {
        border: solid #3a3a3a;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Create task"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("New task")
            yield Input(placeholder="Describe the task...")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        text = self.query_one(Input).value.strip()
        self.dismiss(text or None)


class TodoApp(App):
    CSS = """
    Screen {
        background: #0b0b0b;
        color: #d0d0d0;
    }
    #lists {
        height: 1fr;
    }
    .pane {
        width: 1fr;
        padding: 0 1;
    }
    .pane ListView {
        height: 1fr;
        border: solid #3a3a3a;
    }
    .pane ListView:focus {
        border: solid #5f5f5f;
    }
    .title {
        padding: 0 1;
        color: #a0a0a0;
    }
    ListView > ListItem {
        padding: 0 1;
    }
    ListView > ListItem.--highlight {
        background: #2a2a2a;
        color: #f0f0f0;
    }
    #footer-help {
        height: 1;
        background: #111111;
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
        with Horizontal(id="lists"):
            with Vertical(classes="pane"):
                yield Label("Todo", classes="title")
                yield ListView(id="todo-list")
            with Vertical(classes="pane"):
                yield Label("Done", classes="title")
                yield ListView(id="done-list")
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
        self.push_screen(NewTaskScreen(), self.handle_new_task)

    def handle_new_task(self, text: Optional[str]) -> None:
        if not text:
            return
        add_todo(self.connection, text)
        self.refresh_lists()
        self.query_one("#todo-list", ListView).focus()


def main() -> None:
    app = TodoApp()
    app.run()


if __name__ == "__main__":
    main()
