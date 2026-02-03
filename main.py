from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Input,
    Label,
    ListItem,
    ListView,
    Sparkline,
    Switch,
)

from db import (
    add_todo,
    add_focus_seconds,
    connect_db,
    delete_todo,
    get_bool_setting,
    list_created_counts_by_day,
    list_completed_counts_by_day,
    list_done_todos_for_today,
    list_focus_minutes_by_day,
    list_todos,
    TodoRecord,
    set_bool_setting,
    update_status,
    update_parent,
    update_priority,
    update_sort_order,
    update_text,
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


@dataclass
class PendingMove:
    todo_id: int
    status: str
    list_id: str


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


class SettingsModal(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Close settings")]

    def __init__(
        self,
        show_done_today_only: bool,
        show_done_items: bool,
        show_prioritized_only_ordered: bool,
    ) -> None:
        super().__init__()
        self.show_done_today_only = show_done_today_only
        self.show_done_items = show_done_items
        self.show_prioritized_only_ordered = show_prioritized_only_ordered

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-modal"):
            yield Label("Settings", id="settings-modal-title")
            yield Label("Dashboard", classes="settings-heading")
            with Container(classes="settings-box"):
                with Horizontal(classes="settings-row"):
                    yield Label(
                        "Show done items",
                        classes="settings-label",
                    )
                    yield Switch(
                        value=self.show_done_items,
                        id="show-done-toggle",
                    )
            yield Label("Done list", classes="settings-heading")
            with Container(classes="settings-box"):
                with Horizontal(classes="settings-row"):
                    yield Label(
                        "Show items completed today only",
                        classes="settings-label",
                    )
                    yield Switch(
                        value=self.show_done_today_only,
                        id="done-today-toggle",
                    )
            yield Label("Ordered view", classes="settings-heading")
            with Container(classes="settings-box"):
                with Horizontal(classes="settings-row"):
                    yield Label(
                        "Only show prioritized items",
                        classes="settings-label",
                    )
                    yield Switch(
                        value=self.show_prioritized_only_ordered,
                        id="ordered-priority-toggle",
                    )

    def action_close(self) -> None:
        self.dismiss()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        app = self.app
        if isinstance(app, TodoApp):
            if event.switch.id == "done-today-toggle":
                app.set_show_done_today_only(event.value)
            elif event.switch.id == "show-done-toggle":
                app.set_show_done_items(event.value)
            elif event.switch.id == "ordered-priority-toggle":
                app.set_show_prioritized_only_ordered(event.value)


class TodoApp(App):
    CSS = """
    Screen {
        background: #0b0b0b;
        color: #d0d0d0;
    }
    TabbedContent {
        height: 1fr;
    }
    FocusModal {
        align: center middle;
    }
    SettingsModal {
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
    .pane-box {
        height: 1fr;
        border: solid #3a3a3a;
        background: transparent;
    }
    .pane-box:focus-within {
        border: solid #5f5f5f;
    }
    .pane ListView {
        height: 1fr;
        border: none;
        background: transparent;
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
    .sparkline-group {
        height: 1fr;
        background: transparent;
    }
    .sparkline-group Sparkline {
        height: 1fr;
    }
    .sparkline-legend {
        dock: top;
        height: 1;
        padding: 0 1;
        text-align: left;
        color: #a0a0a0;
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
        text-wrap: wrap;
        width: 100%;
    }
    #focus-modal-timer {
        text-align: center;
        color: #a0a0a0;
    }
    #settings-modal {
        width: 60%;
        padding: 1 2;
        max-height: 90%;
        border: heavy #5f5f5f;
        background: #0f0f0f;
        overflow-y: auto;
    }
    #settings-modal-title {
        text-align: center;
        text-style: bold;
        color: #f0f0f0;
        margin-bottom: 1;
    }
    ListView > ListItem {
        padding: 0 1;
    }
    ListView > ListItem.--highlight {
        background: transparent;
        color: #f0f0f0;
        text-style: bold;
    }
    ListView > ListItem.moving-item {
        background: #1f7a1f;
        color: #e8ffe8;
    }
    ListView > ListItem.moving-item.--highlight {
        background: #2faa2f;
        color: #f4fff4;
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
    .settings-heading {
        color: #f0f0f0;
        text-style: bold;
    }
    .settings-box {
        height: auto;
        margin-top: 0;
        padding: 0 1;
        border: none;
        background: transparent;
    }
    .settings-row {
        align: center middle;
        padding: 0 1;
        width: 100%;
    }
    .settings-label {
        width: 1fr;
        color: #d0d0d0;
    }
    .settings-row Switch {
        margin-left: 1;
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
        ("s", "new_sibling_task", "New sibling task"),
        ("p", "new_parent_task", "New parent task"),
        ("m", "start_move", "Move task"),
        ("n", "new_task", "New task"),
        ("o", "toggle_priority_order", "Toggle priority order"),
        ("e", "edit_task", "Edit task"),
        ("a", "open_settings", "Settings"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.connection = connect_db()
        self.show_done_today_only = get_bool_setting(
            self.connection,
            "donelist.show_completed_today_only",
            default=False,
        )
        self.show_done_items = get_bool_setting(
            self.connection,
            "dashboard.show_done_items",
            default=True,
        )
        self.show_prioritized_only_ordered = get_bool_setting(
            self.connection,
            "ordered.show_prioritized_only",
            default=True,
        )
        self.focus_session: Optional[tuple[int, float, str]] = None
        self.pending_task: PendingTask | None = None
        self.pending_move: PendingMove | None = None
        self.editing_task_id: int | None = None
        self.default_placeholder = "New task…"
        self.priority_order = False

    @property
    def time(self) -> float:
        return monotonic()

    def compose(self) -> ComposeResult:
        yield Label("5am", id="app-title")
        with Vertical(id="tasks-view"):
            with Horizontal(id="lists"):
                with Vertical(classes="pane", id="todo-pane"):
                    with Vertical(classes="pane-box"):
                        yield Label("Todo", classes="title")
                        yield ListView(id="todo-list")
                with Vertical(classes="pane", id="done-pane"):
                    with Vertical(classes="pane-box"):
                        yield Label("Done", classes="title")
                        yield ListView(id="done-list")
            with Vertical(id="sparkline-panel"):
                with Container(classes="sparkline-group"):
                    yield Sparkline(id="created-sparkline")
                    yield Label("Created per day", classes="sparkline-legend")
                with Container(classes="sparkline-group"):
                    yield Sparkline(id="completed-sparkline")
                    yield Label("Completed per day", classes="sparkline-legend")
                with Container(classes="sparkline-group"):
                    yield Sparkline(id="focus-sparkline")
                    yield Label("Focus minutes per day", classes="sparkline-legend")
            yield Input(placeholder="New task…", id="new-task-input")
            yield Label(
                "h/j/k/l move, 0-9 prio, o order, f flip, e edit, t time, m move, c child, s sibling, p parent, d delete, a settings",
                id="footer-help",
            )

    def on_mount(self) -> None:
        self.refresh_lists()
        self.query_one("#todo-list", ListView).focus()

    def refresh_lists(self) -> None:
        todo_list = self.query_one("#todo-list", ListView)
        done_list = self.query_one("#done-list", ListView)
        done_pane = self.query_one("#done-pane", Vertical)
        if self.show_done_items:
            done_pane.styles.display = "block"
        else:
            done_pane.styles.display = "none"
            if isinstance(self.focused, ListView) and self.focused.id == "done-list":
                todo_list.focus()
        todo_list.clear()
        done_list.clear()
        for record, depth in self.build_display_items("todo"):
            item = TodoListItem(record, depth)
            if self.pending_move and record.todo_id == self.pending_move.todo_id:
                item.add_class("moving-item")
            todo_list.append(item)
        if self.show_done_items:
            for record, depth in self.build_display_items("done"):
                item = TodoListItem(record, depth)
                if self.pending_move and record.todo_id == self.pending_move.todo_id:
                    item.add_class("moving-item")
                done_list.append(item)
        self.refresh_sparkline()

    def build_display_items(self, status: str) -> list[tuple[TodoRecord, int]]:
        if status == "done" and self.show_done_today_only:
            records = list_done_todos_for_today(self.connection)
        else:
            records = list_todos(self.connection, status)
        if status == "todo" and self.priority_order:
            if self.show_prioritized_only_ordered:
                records = [record for record in records if record.priority is not None]

            def flat_sort_key(item) -> tuple[float, str, int]:
                priority_value = (
                    float(item.priority) if item.priority is not None else 99.0
                )
                return (priority_value, item.timestamp, item.todo_id)

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

        def sort_key(item) -> tuple[str, int]:
            return (item.timestamp, item.todo_id)

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
        created_sparkline = self.query_one("#created-sparkline", Sparkline)
        created_sparkline.data = list_created_counts_by_day(self.connection)
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

    def find_item_by_id(
        self, items: list[TodoListItem], todo_id: int
    ) -> TodoListItem | None:
        for item in items:
            if item.todo_id == todo_id:
                return item
        return None

    def is_descendant(
        self,
        candidate_id: int,
        ancestor_id: int,
        parent_by_id: dict[int, int | None],
    ) -> bool:
        current = parent_by_id.get(candidate_id)
        while current is not None:
            if current == ancestor_id:
                return True
            current = parent_by_id.get(current)
        return False

    def last_descendant_index(
        self, items: list[TodoListItem], index: int
    ) -> int:
        parent = items[index]
        last_index = index
        for next_index in range(index + 1, len(items)):
            if items[next_index].depth <= parent.depth:
                break
            last_index = next_index
        return last_index

    def sort_order_after_subtree(
        self, items: list[TodoListItem], index: int
    ) -> float:
        last_index = self.last_descendant_index(items, index)
        return self.sort_order_after_index(items, last_index)

    def action_focus_left(self) -> None:
        self.query_one("#todo-list", ListView).focus()

    def action_focus_right(self) -> None:
        if not self.show_done_items:
            self.query_one("#todo-list", ListView).focus()
            return
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

    def action_start_move(self) -> None:
        if self.priority_order:
            return
        list_view = self.get_active_list()
        item = self.get_highlighted_item(list_view)
        if not item:
            return
        self.pending_move = PendingMove(
            todo_id=item.todo_id,
            status=item.status,
            list_id=list_view.id or "",
        )
        self.refresh_lists()
        list_view.focus()

    def action_toggle_priority_order(self) -> None:
        self.priority_order = not self.priority_order
        self.pending_move = None
        focused = self.focused
        focus_id = focused.id if hasattr(focused, "id") else "#todo-list"
        if focus_id and not focus_id.startswith("#"):
            focus_id = f"#{focus_id}"
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
        self.editing_task_id = None
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
        if self.pending_move:
            self.perform_move("child")
            return
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
        self.editing_task_id = None
        input_box = self.query_one("#new-task-input", Input)
        input_box.placeholder = self.pending_task.placeholder
        input_box.focus()

    def action_new_parent_task(self) -> None:
        if self.pending_move:
            self.perform_move("parent")
            return
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
        self.editing_task_id = None
        input_box = self.query_one("#new-task-input", Input)
        input_box.placeholder = self.pending_task.placeholder
        input_box.focus()

    def action_new_sibling_task(self) -> None:
        if self.pending_move:
            self.perform_move("sibling")
            return
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
            parent_id=item.parent_id,
            status=item.status,
            sort_order=sort_order,
            reparent_id=None,
            placeholder="New sibling task…",
        )
        self.editing_task_id = None
        input_box = self.query_one("#new-task-input", Input)
        input_box.placeholder = self.pending_task.placeholder
        input_box.focus()

    def perform_move(self, relationship: str) -> None:
        move_request = self.pending_move
        self.pending_move = None
        if not move_request:
            return
        list_view = self.get_active_list()
        if list_view.id != move_request.list_id:
            return
        items = self.get_list_items(list_view)
        source_item = self.find_item_by_id(items, move_request.todo_id)
        target_item = self.get_highlighted_item(list_view)
        if not source_item or not target_item:
            return
        if source_item.todo_id == target_item.todo_id:
            return
        if source_item.status != target_item.status:
            return
        parent_by_id = {item.todo_id: item.parent_id for item in items}
        if self.is_descendant(target_item.todo_id, source_item.todo_id, parent_by_id):
            if relationship == "sibling":
                source_parent = parent_by_id.get(source_item.todo_id)
                source_index = items.index(source_item)
                sort_order = self.sort_order_after_subtree(items, source_index)
                update_parent(self.connection, target_item.todo_id, source_parent)
                update_sort_order(self.connection, target_item.todo_id, sort_order)
                self.refresh_lists()
                list_view.focus()
            return
        target_index = self.get_highlighted_index(list_view)
        if target_index is None:
            return
        if relationship == "child":
            sort_order = self.sort_order_after_subtree(items, target_index)
            update_parent(self.connection, source_item.todo_id, target_item.todo_id)
            update_sort_order(self.connection, source_item.todo_id, sort_order)
        elif relationship == "sibling":
            sort_order = self.sort_order_after_subtree(items, target_index)
            update_parent(self.connection, source_item.todo_id, target_item.parent_id)
            update_sort_order(self.connection, source_item.todo_id, sort_order)
        elif relationship == "parent":
            sort_order = self.sort_order_before_index(items, target_index)
            update_parent(self.connection, source_item.todo_id, target_item.parent_id)
            update_sort_order(self.connection, source_item.todo_id, sort_order)
            update_parent(self.connection, target_item.todo_id, source_item.todo_id)
        self.refresh_lists()
        list_view.focus()

    def action_edit_task(self) -> None:
        list_view = self.get_active_list()
        item = self.get_highlighted_item(list_view)
        if not item:
            return
        self.pending_task = None
        self.editing_task_id = item.todo_id
        input_box = self.query_one("#new-task-input", Input)
        input_box.placeholder = "Edit task…"
        input_box.value = item.text
        input_box.cursor_position = len(item.text)
        input_box.focus()

    def action_open_settings(self) -> None:
        self.push_screen(
            SettingsModal(
                self.show_done_today_only,
                self.show_done_items,
                self.show_prioritized_only_ordered,
            )
        )

    def set_show_done_today_only(self, value: bool) -> None:
        self.show_done_today_only = value
        set_bool_setting(
            self.connection,
            "donelist.show_completed_today_only",
            value,
        )
        self.refresh_lists()

    def set_show_done_items(self, value: bool) -> None:
        self.show_done_items = value
        set_bool_setting(
            self.connection,
            "dashboard.show_done_items",
            value,
        )
        self.refresh_lists()
        if not value:
            self.query_one("#todo-list", ListView).focus()

    def set_show_prioritized_only_ordered(self, value: bool) -> None:
        self.show_prioritized_only_ordered = value
        set_bool_setting(
            self.connection,
            "ordered.show_prioritized_only",
            value,
        )
        self.refresh_lists()

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
        if self.editing_task_id is not None:
            todo_id = self.editing_task_id
            self.editing_task_id = None
            update_text(self.connection, todo_id, text)
            event.input.value = ""
            event.input.placeholder = self.default_placeholder
            self.refresh_lists()
            self.get_active_list().focus()
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
            if event.key == "escape":
                input_box = self.query_one("#new-task-input", Input)
                input_box.value = ""
                input_box.placeholder = self.default_placeholder
                self.pending_task = None
                self.editing_task_id = None
                self.query_one("#todo-list", ListView).focus()
                event.stop()
            return
        if event.key in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            list_view = self.get_active_list()
            if list_view.id != "todo-list":
                return
            item = self.get_highlighted_item(list_view)
            if not item:
                return
            priority = int(event.key)
            update_priority(
                self.connection,
                item.todo_id,
                None if priority == 0 else priority,
            )
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
