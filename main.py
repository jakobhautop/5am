from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Sparkline

from db import (
    add_todo,
    add_focus_seconds,
    connect_db,
    delete_todo,
    list_completed_counts_by_day,
    list_focus_minutes_by_day,
    list_todos,
    TodoRecord,
    update_status,
    update_parent,
    update_priority,
)


class TodoListItem(ListItem):
    def __init__(self, record: TodoRecord, depth: int) -> None:
        indent = "  " * depth
        priority_label = (
            f"{record.priority}".rjust(2) if record.priority is not None else "  "
        )
        super().__init__(Label(f"{indent}{priority_label} {record.text}"))
        self.todo_id = record.todo_id
        self.status = record.status
        self.text = record.text
        self.parent_id = record.parent_id
        self.sort_order = record.sort_order
        self.priority = record.priority
        self.depth = depth


@dataclass
class PendingTask:
    parent_id: int | None
    status: str
    sort_order: float
    reparent_id: int | None
    placeholder: str


class FocusModal(ModalScreen[int]):
    BINDINGS = [("t", "stop_focus", "Stop focus")]

    def __init__(self, todo_text: str) -> None:
        super().__init__()
        self.todo_text = todo_text
        self._start = self.app.time
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="focus-modal"):
            yield Label("Focus", id="focus-modal-title")
            yield Label(self.todo_text, id="focus-modal-text")
            yield Label("00:00:00", id="focus-modal-timer")

    def on_mount(self) -> None:
        self._start = self.app.time
        self._timer = self.set_interval(1, self._update_focus_timer)

    def _update_focus_timer(self) -> None:
        elapsed = int(self.app.time - self._start)
        timer_label = self.query_one("#focus-modal-timer", Label)
        timer_label.update(str(timedelta(seconds=elapsed)))

    def action_stop_focus(self) -> None:
        elapsed = int(self.app.time - self._start)
        if self._timer:
            self._timer.stop()
        self.dismiss(elapsed)


class TodoApp(App):
    CSS = """
    Screen {
        background: #0b0b0b;
        color: #d0d0d0;
    }
    FocusModal {
        align: center middle;
    }
    #lists {
        height: 2fr;
    }
    #app-title {
        padding: 1 1 0 1;
        color: #f0f0f0;
        text-style: bold;
        text-align: center;
        width: 100%;
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
        margin-top: 1;
    }
    .sparkline-title {
        text-align: center;
        color: #a0a0a0;
        width: 100%;
    }
    #completed-sparkline {
        height: 1fr;
    }
    #focus-sparkline {
        height: 1fr;
        margin-top: 1;
    }
    #focus-modal {
        width: 60%;
        padding: 1 2;
        border: heavy #5f5f5f;
        background: #0f0f0f;
    }
    #focus-modal-title {
        text-align: center;
        text-style: bold;
        color: #f0f0f0;
        margin-bottom: 1;
    }
    #focus-modal-text {
        text-align: center;
        color: #d0d0d0;
        margin-bottom: 1;
    }
    #focus-modal-timer {
        text-align: center;
        color: #a0a0a0;
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
        background: transparent;
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
        ("d", "delete_item", "Delete item"),
        ("t", "focus_task", "Focus task"),
        ("c", "new_child_task", "New child task"),
        ("p", "new_parent_task", "New parent task"),
        ("n", "new_task", "New task"),
        ("o", "toggle_priority_order", "Toggle priority order"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.connection = connect_db()
        self.focus_session: Optional[tuple[int, float, str]] = None
        self.pending_task: PendingTask | None = None
        self.default_placeholder = "New task…"
        self.priority_order = False

    @property
    def time(self) -> float:
        return monotonic()

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
            yield Label("Completed per day", classes="sparkline-title")
            yield Sparkline(id="completed-sparkline")
            yield Label("Focus minutes per day", classes="sparkline-title")
            yield Sparkline(id="focus-sparkline")
        yield Input(placeholder="New task…", id="new-task-input")
        yield Label(
            "h/l switch lists  •  j/k move  •  1-9 priority  •  o order  •  f flip item  •  t focus time  •  c child  •  p parent  •  d delete item  •  n new task",
            id="footer-help",
        )

    def on_mount(self) -> None:
        self.refresh_lists()
        self.query_one("#todo-list", ListView).focus()

    def refresh_lists(self) -> None:
        todo_list = self.query_one("#todo-list", ListView)
        done_list = self.query_one("#done-list", ListView)
        todo_list.clear()
        done_list.clear()
        for record, depth in self.build_display_items("todo"):
            todo_list.append(TodoListItem(record, depth))
        for record, depth in self.build_display_items("done"):
            done_list.append(TodoListItem(record, depth))
        self.refresh_sparkline()

    def build_display_items(self, status: str) -> list[tuple[TodoRecord, int]]:
        records = list_todos(self.connection, status)
        if status == "todo" and self.priority_order:
            def flat_sort_key(item) -> tuple[float, float, int]:
                priority_value = float(item.priority) if item.priority is not None else 99.0
                return (priority_value, item.sort_order, item.todo_id)

            ordered = sorted(records, key=flat_sort_key)
            return [(record, 0) for record in ordered]
        record_by_id = {record.todo_id: record for record in records}
        children_map: dict[int, list] = {record.todo_id: [] for record in records}
        roots = []
        for record in records:
            if record.parent_id in record_by_id:
                children_map[record.parent_id].append(record)
            else:
                roots.append(record)

        def sort_key(item) -> tuple[float, float, int]:
            return (item.sort_order, item.todo_id, item.todo_id)

        roots.sort(key=sort_key)
        for children in children_map.values():
            children.sort(key=sort_key)

        ordered: list[tuple] = []

        def walk(node, depth: int) -> None:
            ordered.append((node, depth))
            for child in children_map.get(node.todo_id, []):
                walk(child, depth + 1)

        for root in roots:
            walk(root, 0)
        return ordered

    def refresh_sparkline(self) -> None:
        sparkline = self.query_one("#completed-sparkline", Sparkline)
        sparkline.data = list_completed_counts_by_day(self.connection)
        focus_sparkline = self.query_one("#focus-sparkline", Sparkline)
        focus_sparkline.data = list_focus_minutes_by_day(self.connection)

    def get_active_list(self) -> ListView:
        focused = self.focused
        if isinstance(focused, ListView) and focused.id in {"todo-list", "done-list"}:
            return focused
        return self.query_one("#todo-list", ListView)

    def get_highlighted_item(self, list_view: ListView) -> Optional[TodoListItem]:
        index = self.get_highlighted_index(list_view)
        if index is None:
            return None
        try:
            item = list_view.children[index]
        except (IndexError, TypeError):
            return None
        if isinstance(item, TodoListItem):
            return item
        return None

    def get_highlighted_index(self, list_view: ListView) -> int | None:
        index = getattr(list_view, "highlighted", None)
        if index is None:
            index = getattr(list_view, "index", None)
        if index is None:
            return None
        return index

    def get_list_items(self, list_view: ListView) -> list[TodoListItem]:
        return [
            item for item in list_view.children if isinstance(item, TodoListItem)
        ]

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

    def action_toggle_priority_order(self) -> None:
        self.priority_order = not self.priority_order
        focused = self.focused
        focus_id = focused.id if hasattr(focused, "id") else "#todo-list"
        self.refresh_lists()
        self.query_one(focus_id, ListView).focus()

    def action_flip_state(self) -> None:
        list_view = self.get_active_list()
        item = self.get_highlighted_item(list_view)
        if not item:
            return
        new_status = "done" if item.status == "todo" else "todo"
        update_status(self.connection, item.todo_id, new_status)
        self.refresh_lists()
        list_view.focus()

    def action_delete_item(self) -> None:
        list_view = self.get_active_list()
        item = self.get_highlighted_item(list_view)
        if not item:
            return
        delete_todo(self.connection, item.todo_id)
        self.refresh_lists()
        list_view.focus()

    def action_new_task(self) -> None:
        self.pending_task = None
        input_box = self.query_one("#new-task-input", Input)
        input_box.placeholder = self.default_placeholder
        input_box.focus()

    def action_focus_task(self) -> None:
        list_view = self.get_active_list()
        item = self.get_highlighted_item(list_view)
        if not item or item.status != "todo":
            return
        if self.focus_session and self.focus_session[0] != item.todo_id:
            self._record_focus_session()
        if self.focus_session and self.focus_session[0] == item.todo_id:
            self._record_focus_session()
            return
        self.focus_session = (item.todo_id, self.time, item.text)
        self.push_screen(
            FocusModal(item.text),
            callback=self._handle_focus_complete,
        )

    def action_new_child_task(self) -> None:
        list_view = self.get_active_list()
        item = self.get_highlighted_item(list_view)
        if not item:
            return
        items = self.get_list_items(list_view)
        index = self.get_highlighted_index(list_view)
        if index is None:
            return
        last_index = index
        for next_index in range(index + 1, len(items)):
            if items[next_index].depth <= item.depth:
                break
            last_index = next_index
        sort_order = self.sort_order_after_index(items, last_index)
        self.pending_task = PendingTask(
            parent_id=item.todo_id,
            status=item.status,
            sort_order=sort_order,
            reparent_id=None,
            placeholder="New child task…",
        )
        input_box = self.query_one("#new-task-input", Input)
        input_box.placeholder = self.pending_task.placeholder
        input_box.focus()

    def action_new_parent_task(self) -> None:
        list_view = self.get_active_list()
        item = self.get_highlighted_item(list_view)
        if not item:
            return
        items = self.get_list_items(list_view)
        index = self.get_highlighted_index(list_view)
        if index is None:
            return
        sort_order = self.sort_order_before_index(items, index)
        self.pending_task = PendingTask(
            parent_id=item.parent_id,
            status=item.status,
            sort_order=sort_order,
            reparent_id=item.todo_id,
            placeholder="New parent task…",
        )
        input_box = self.query_one("#new-task-input", Input)
        input_box.placeholder = self.pending_task.placeholder
        input_box.focus()

    def sort_order_after_index(self, items: list[TodoListItem], index: int) -> float:
        prev_order = items[index].sort_order
        if index + 1 < len(items):
            next_order = items[index + 1].sort_order
            if next_order <= prev_order:
                return prev_order + 1
            return (prev_order + next_order) / 2
        return prev_order + 1

    def sort_order_before_index(self, items: list[TodoListItem], index: int) -> float:
        next_order = items[index].sort_order
        if index > 0:
            prev_order = items[index - 1].sort_order
            if next_order <= prev_order:
                return next_order - 1
            return (prev_order + next_order) / 2
        return next_order - 1

    def _record_focus_session(self) -> None:
        if not self.focus_session:
            return
        todo_id, start_time, _text = self.focus_session
        elapsed = int(self.time - start_time)
        if elapsed > 0:
            add_focus_seconds(self.connection, todo_id, elapsed)
            self.refresh_sparkline()
        self.focus_session = None

    def _handle_focus_complete(self, elapsed: int | None) -> None:
        if not self.focus_session:
            return
        todo_id, start_time, _text = self.focus_session
        if elapsed is None:
            elapsed = int(self.time - start_time)
        if elapsed > 0:
            add_focus_seconds(self.connection, todo_id, elapsed)
        self.focus_session = None
        self.refresh_sparkline()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "new-task-input":
            return
        text = event.value.strip()
        if not text:
            return
        focus_list_id = "#todo-list"
        if self.pending_task:
            new_record = add_todo(
                self.connection,
                text,
                status=self.pending_task.status,
                parent_id=self.pending_task.parent_id,
                sort_order=self.pending_task.sort_order,
            )
            if self.pending_task.reparent_id is not None:
                update_parent(
                    self.connection,
                    self.pending_task.reparent_id,
                    new_record.todo_id,
                )
            if self.pending_task.status == "done":
                focus_list_id = "#done-list"
            self.pending_task = None
            event.input.placeholder = self.default_placeholder
        else:
            add_todo(self.connection, text)
        event.input.value = ""
        self.refresh_lists()
        self.query_one(focus_list_id, ListView).focus()

    def on_key(self, event) -> None:
        if isinstance(self.focused, Input):
            return
        if event.key in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            list_view = self.get_active_list()
            if list_view.id != "todo-list":
                return
            item = self.get_highlighted_item(list_view)
            if not item:
                return
            update_priority(self.connection, item.todo_id, int(event.key))
            index = self.get_highlighted_index(list_view)
            self.refresh_lists()
            refreshed_list = self.query_one("#todo-list", ListView)
            if index is not None and refreshed_list.children:
                refreshed_list.index = min(index, len(refreshed_list.children) - 1)
            refreshed_list.focus()


def main() -> None:
    app = TodoApp()
    app.run()


if __name__ == "__main__":
    main()
