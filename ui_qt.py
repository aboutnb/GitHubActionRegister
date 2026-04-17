from __future__ import annotations

import os
import re
import sys
import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets


UI_PREFS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ui_prefs.json")


def _load_ui_prefs() -> dict[str, Any]:
    try:
        if os.path.isfile(UI_PREFS_FILE):
            with open(UI_PREFS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_ui_prefs(prefs: dict[str, Any]) -> None:
    try:
        with open(UI_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def apply_light_desktop_palette(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    base = QtGui.QColor("#ffffff")
    alt = QtGui.QColor("#f6f7f9")
    text = QtGui.QColor("#111827")
    muted = QtGui.QColor("#6b7280")
    line = QtGui.QColor("#e5e7eb")
    primary = QtGui.QColor("#2563eb")

    pal.setColor(QtGui.QPalette.Window, base)
    pal.setColor(QtGui.QPalette.Base, base)
    pal.setColor(QtGui.QPalette.AlternateBase, alt)
    pal.setColor(QtGui.QPalette.Text, text)
    pal.setColor(QtGui.QPalette.WindowText, text)
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#f3f4f6"))
    pal.setColor(QtGui.QPalette.ButtonText, text)
    pal.setColor(QtGui.QPalette.Highlight, primary)
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.PlaceholderText, muted)
    pal.setColor(QtGui.QPalette.Mid, line)
    pal.setColor(QtGui.QPalette.Light, QtGui.QColor("#f9fafb"))
    app.setPalette(pal)


@dataclass
class AccountRow:
    email: str
    password: str
    status: str


class AccountsModel(QtCore.QAbstractTableModel):
    COL_IDX = 0
    COL_EMAIL = 1
    COL_PASSWORD = 2
    COL_STATUS = 3

    def __init__(self, get_rows: Callable[[], list[AccountRow]]):
        super().__init__()
        self._get_rows = get_rows

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._get_rows())

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 4

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            return ["#", "邮箱", "密码", "状态"][section]
        return str(section + 1)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        rows = self._get_rows()
        row = rows[index.row()]
        col = index.column()

        if role == QtCore.Qt.DisplayRole:
            if col == self.COL_IDX:
                return str(index.row() + 1)
            if col == self.COL_EMAIL:
                return row.email
            if col == self.COL_PASSWORD:
                # 密码列默认显示为掩码；真实值用于复制
                return "•" * min(12, max(6, len(row.password)))
            if col == self.COL_STATUS:
                return row.status
        if role == QtCore.Qt.TextAlignmentRole:
            if col == self.COL_STATUS:
                return int(QtCore.Qt.AlignCenter)
            if col == self.COL_IDX:
                return int(QtCore.Qt.AlignCenter)
        if role == QtCore.Qt.FontRole and col == self.COL_PASSWORD:
            f = QtGui.QFont("Menlo")
            f.setStyleHint(QtGui.QFont.Monospace)
            return f
        if role == QtCore.Qt.ForegroundRole:
            # 用“桌面 UX”常见颜色表达状态（轻量，不依赖暗色主题）
            s = row.status
            if s in ("成功",):
                return QtGui.QBrush(QtGui.QColor("#047857"))
            if s in ("失败",):
                return QtGui.QBrush(QtGui.QColor("#b91c1c"))
            if s in ("进行中", "人机验证", "取码验证", "获取2FA"):
                return QtGui.QBrush(QtGui.QColor("#1d4ed8"))
            if s in ("已跳过",):
                return QtGui.QBrush(QtGui.QColor("#6b7280"))
        return None

    def refresh_all(self) -> None:
        self.beginResetModel()
        self.endResetModel()


class Worker(QtCore.QObject):
    log = QtCore.Signal(str)
    status = QtCore.Signal(int, str)         # idx, status_text
    progress = QtCore.Signal(int, int)       # done, total
    current = QtCore.Signal(str)             # current label
    done = QtCore.Signal(int, int)           # success, fail

    def __init__(
        self,
        run_one: Callable[[dict[str, Any], Callable[[str], None], Callable[[str], None], Callable[[], bool]], str],
        accounts_ref: list[dict[str, Any]],
        indices: list[int],
        is_cancelled: Callable[[], bool],
        status_texts: dict[str, str],
    ):
        super().__init__()
        self._run_one = run_one
        self._accounts = accounts_ref
        self._indices = indices
        self._is_cancelled = is_cancelled
        self._success = 0
        self._fail = 0
        self._status_texts = status_texts

    @QtCore.Slot()
    def run(self) -> None:
        total = len(self._indices)
        for seq, idx in enumerate(self._indices):
            if self._is_cancelled():
                break

            acc = self._accounts[idx]
            email = acc.get("email", "")
            self.current.emit(f"处理中: {email}")
            self.log.emit("\n" + "=" * 55)
            self.log.emit(f"[{seq + 1}/{total}] 开始: {email} (小水滴取件)")
            self.log.emit("=" * 55)

            def _log(msg: str) -> None:
                self.log.emit(msg)

            def _on_status(st: str) -> None:
                self.status.emit(idx, st)

            result = self._run_one(acc, _log, _on_status, self._is_cancelled)

            if result in ("success", "partial"):
                self._success += 1
            elif result == "failed":
                self._fail += 1

            self.progress.emit(seq + 1, total)

        self.done.emit(self._success, self._fail)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        *,
        window_title: str,
        output_file: str,
        failed_file: str,
        failed_accounts_file: str,
        parse_mail_line: Callable[[str], Optional[dict[str, str]]],
        run_one: Callable[[dict[str, Any], Callable[[str], None], Callable[[str], None], Callable[[], bool]], str],
        open_output: Callable[[], None],
        failed_batch_start: Callable[[int], None],
    ):
        super().__init__()
        self.setWindowTitle(window_title)
        # 默认尺寸：优先“适中”而不是巨大；日志区在底部可折叠/可浮动
        # 相比之前更紧凑（约 70–80%），但仍保证表格/按钮/日志好用
        self.resize(980, 720)
        self.setMinimumSize(900, 640)

        self._prefs = _load_ui_prefs()
        self._output_file = output_file
        self._failed_file = failed_file
        self._failed_accounts_file = failed_accounts_file
        self._parse_mail_line = parse_mail_line
        self._run_one = run_one
        self._open_output_cb = open_output
        self._failed_batch_start = failed_batch_start

        self.accounts: list[dict[str, Any]] = []
        self._rows: list[AccountRow] = []
        self._running = False
        self._skip_current = False

        self._thread: Optional[QtCore.QThread] = None
        self._worker: Optional[Worker] = None

        self._build_ui()
        self._apply_initial_split()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        # 顶部工具栏：桌面工具的常规入口
        tb = QtWidgets.QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(tb)

        act_import = QtGui.QAction("导入文件", self)
        act_import.triggered.connect(self.import_file)
        tb.addAction(act_import)

        act_paste = QtGui.QAction("粘贴导入", self)
        act_paste.triggered.connect(self.paste_import)
        tb.addAction(act_paste)

        tb.addSeparator()

        self.act_run_selected = QtGui.QAction("注册选中", self)
        self.act_run_selected.triggered.connect(self.run_selected)
        tb.addAction(self.act_run_selected)

        self.act_run_all = QtGui.QAction("全部轮询", self)
        self.act_run_all.triggered.connect(self.run_all)
        tb.addAction(self.act_run_all)

        self.act_skip = QtGui.QAction("跳过当前", self)
        self.act_skip.setEnabled(False)
        self.act_skip.triggered.connect(self.skip_current)
        tb.addAction(self.act_skip)

        self.act_stop = QtGui.QAction("停止", self)
        self.act_stop.setEnabled(False)
        self.act_stop.triggered.connect(self.stop)
        tb.addAction(self.act_stop)

        tb.addSeparator()
        act_open = QtGui.QAction("打开导出", self)
        act_open.triggered.connect(self._open_output_cb)
        tb.addAction(act_open)

        act_open_failed_plain = QtGui.QAction("打开失败账号", self)
        act_open_failed_plain.triggered.connect(self.open_failed_accounts_plain)
        tb.addAction(act_open_failed_plain)

        # 状态栏：桌面 UX 的“持续反馈”
        self.statusBar().showMessage("就绪")

        # 中央：主工作区（表格 + 详情/进度），日志/结果放到底部 Dock（更符合桌面工具习惯）
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        root.addWidget(splitter)

        # Left: 表格（任务列表）
        left = QtWidgets.QWidget()
        left_l = QtWidgets.QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(8)

        card = QtWidgets.QFrame()
        card.setFrameShape(QtWidgets.QFrame.StyledPanel)
        card_l = QtWidgets.QVBoxLayout(card)
        card_l.setContentsMargins(10, 10, 10, 10)
        card_l.setSpacing(8)
        title = QtWidgets.QLabel("任务列表")
        title.setStyleSheet("font-weight: 600;")
        card_l.addWidget(title)

        self.table = QtWidgets.QTableView()
        self.table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        self.model = AccountsModel(lambda: self._rows)
        self.table.setModel(self.model)
        self._apply_table_column_layout()
        self.table.selectionModel().selectionChanged.connect(lambda _a, _b: self._update_detail())
        card_l.addWidget(self.table)

        # 右键菜单：复制账号/密码/组合
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._open_table_menu)

        left_l.addWidget(card, 1)
        splitter.addWidget(left)

        # Middle: 详情 + 进度（信息层级清晰）
        mid = QtWidgets.QWidget()
        mid_l = QtWidgets.QVBoxLayout(mid)
        mid_l.setContentsMargins(0, 0, 0, 0)
        mid_l.setSpacing(10)

        detail = QtWidgets.QGroupBox("详情")
        dl = QtWidgets.QVBoxLayout(detail)
        dl.setContentsMargins(12, 12, 12, 12)
        dl.setSpacing(6)
        self.lbl_email = QtWidgets.QLabel("邮箱：—")
        self.lbl_email.setStyleSheet("font-weight: 600;")
        self.lbl_status = QtWidgets.QLabel("状态：—")
        self.lbl_status.setStyleSheet("color: #6b7280;")
        self.lbl_tip = QtWidgets.QLabel("提示：选中左侧账号查看详情；运行中会实时更新状态。")
        self.lbl_tip.setWordWrap(True)
        self.lbl_tip.setStyleSheet("color: #6b7280;")
        dl.addWidget(self.lbl_email)
        dl.addWidget(self.lbl_status)
        dl.addSpacing(6)
        dl.addWidget(self.lbl_tip)
        mid_l.addWidget(detail)

        prog = QtWidgets.QGroupBox("进度")
        pl = QtWidgets.QVBoxLayout(prog)
        pl.setContentsMargins(12, 12, 12, 12)
        pl.setSpacing(8)
        row = QtWidgets.QHBoxLayout()
        self.lbl_current = QtWidgets.QLabel("就绪")
        self.lbl_current.setStyleSheet("font-weight: 600;")
        self.lbl_step = QtWidgets.QLabel("")
        self.lbl_step.setStyleSheet("color: #6b7280;")
        row.addWidget(self.lbl_current)
        row.addStretch(1)
        row.addWidget(self.lbl_step)
        pl.addLayout(row)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setValue(0)
        pl.addWidget(self.progress)
        mid_l.addWidget(prog)

        # 不用 stretch 撑高，避免“进度下面一大片空白”
        splitter.addWidget(mid)

        # Dock: 日志 + 结果
        dock = QtWidgets.QDockWidget("运行面板", self)
        dock.setAllowedAreas(
            QtCore.Qt.BottomDockWidgetArea
            | QtCore.Qt.TopDockWidgetArea
            | QtCore.Qt.RightDockWidgetArea
            | QtCore.Qt.LeftDockWidgetArea
        )
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFloatable)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
        self._dock_runpanel = dock

        dock_w = QtWidgets.QWidget()
        dock.setWidget(dock_w)
        dock_l = QtWidgets.QVBoxLayout(dock_w)
        dock_l.setContentsMargins(10, 10, 10, 10)
        dock_l.setSpacing(8)

        tools = QtWidgets.QHBoxLayout()
        self.ed_search = QtWidgets.QLineEdit()
        self.ed_search.setPlaceholderText("搜索日志…")
        self.ed_search.textChanged.connect(self._rebuild_log_view)
        self.cb_only_err = QtWidgets.QCheckBox("仅错误")
        self.cb_only_err.stateChanged.connect(self._rebuild_log_view)
        self.cb_autoscroll = QtWidgets.QCheckBox("自动滚动")
        self.cb_autoscroll.setChecked(True)
        btn_clear = QtWidgets.QPushButton("清空")
        btn_clear.clicked.connect(self.clear_logs)
        tools.addWidget(self.ed_search, 1)
        tools.addWidget(self.cb_only_err)
        tools.addWidget(self.cb_autoscroll)
        tools.addWidget(btn_clear)
        dock_l.addLayout(tools)

        self.tabs = QtWidgets.QTabWidget()
        dock_l.addWidget(self.tabs, 1)

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.tabs.addTab(self.log_view, "日志")

        self.result_view = QtWidgets.QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.tabs.addTab(self.result_view, "结果")

        self._log_buffer: list[str] = []
        self._apply_font()

    def _apply_font(self) -> None:
        # 更像“工具软件”的默认字体（mac 用 Menlo）
        mono = QtGui.QFont("Menlo")
        mono.setStyleHint(QtGui.QFont.Monospace)
        mono.setPointSize(11)
        self.log_view.setFont(mono)
        self.result_view.setFont(mono)

    def _apply_initial_split(self) -> None:
        # 让默认就“显示得全”
        self.centralWidget().layout().activate()
        for w in self.findChildren(QtWidgets.QSplitter):
            if w.orientation() == QtCore.Qt.Horizontal:
                w.setSizes([520, 420, 0])  # Dock 在底部；主区给列表更多空间
                break
        # 底部 Dock 初始高度（避免抢占太多空间）
        try:
            if getattr(self, "_dock_runpanel", None):
                self.resizeDocks([self._dock_runpanel], [240], QtCore.Qt.Vertical)
        except Exception:
            pass

    def _apply_table_column_layout(self) -> None:
        """
        确保表格列宽始终“撑满左侧区域”，且比例稳定。
        说明：QHeaderView 的 Stretch 在某些 reset/model 变更后需要重新设置。
        """
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        # 列宽比例：# 很窄、邮箱吃满剩余、密码中等、状态很窄
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)     # #
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)   # 邮箱
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)     # 密码
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Fixed)     # 状态
        self.table.setColumnWidth(0, 34)
        self.table.setColumnWidth(2, 168)
        self.table.setColumnWidth(3, 68)

    # ---------------- Data / Detail ----------------
    def _refresh_rows(self) -> None:
        self._rows = [
            AccountRow(
                email=a.get("email", ""),
                password=a.get("password", ""),
                status=a.get("status", "等待"),
            )
            for a in self.accounts
        ]
        self.model.refresh_all()
        # 导入/刷新后重新应用列布局，确保“邮箱列撑满”
        self._apply_table_column_layout()
        self._update_detail()

    def _selected_indices(self) -> list[int]:
        sel = self.table.selectionModel().selectedRows()
        return sorted({i.row() for i in sel})

    def _update_detail(self) -> None:
        sel = self._selected_indices()
        if not sel:
            self.lbl_email.setText("邮箱：—")
            self.lbl_status.setText("状态：—")
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self.accounts):
            return
        acc = self.accounts[idx]
        self.lbl_email.setText(f"邮箱：{acc.get('email','')}")
        self.lbl_status.setText(f"状态：{acc.get('status','等待')}")

    # ---------------- Copy helpers ----------------
    def _copy_text(self, text: str) -> None:
        QtWidgets.QApplication.clipboard().setText(text or "")
        self.statusBar().showMessage("已复制到剪贴板", 2500)

    def _selected_accounts(self) -> list[dict[str, Any]]:
        indices = self._selected_indices()
        out: list[dict[str, Any]] = []
        for i in indices:
            if 0 <= i < len(self.accounts):
                out.append(self.accounts[i])
        return out

    @QtCore.Slot(QtCore.QPoint)
    def _open_table_menu(self, pos: QtCore.QPoint) -> None:
        # 确保右键行被选中（常见桌面行为）
        idx = self.table.indexAt(pos)
        if idx.isValid() and not self.table.selectionModel().isRowSelected(idx.row(), QtCore.QModelIndex()):
            self.table.selectRow(idx.row())

        menu = QtWidgets.QMenu(self)
        a1 = menu.addAction("复制邮箱")
        a2 = menu.addAction("复制密码")
        a3 = menu.addAction("复制 邮箱----密码")
        menu.addSeparator()
        a4 = menu.addAction("复制选中（多行，邮箱）")
        a5 = menu.addAction("复制选中（多行，邮箱----密码）")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not action:
            return

        selected = self._selected_accounts()
        if not selected:
            return

        if action == a1:
            self._copy_text(str(selected[0].get("email", "")))
        elif action == a2:
            self._copy_text(str(selected[0].get("password", "")))
        elif action == a3:
            self._copy_text(f"{selected[0].get('email','')}----{selected[0].get('password','')}")
        elif action == a4:
            self._copy_text("\n".join(str(a.get("email", "")) for a in selected if a.get("email")))
        elif action == a5:
            self._copy_text(
                "\n".join(
                    f"{a.get('email','')}----{a.get('password','')}"
                    for a in selected
                    if a.get("email") and a.get("password")
                )
            )

    # ---------------- Import ----------------
    @QtCore.Slot()
    def import_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择账号文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            n = self._add_accounts_from_text(content)
            self.append_log(f"从文件导入 {n} 个账号")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "导入失败", str(e))

    @QtCore.Slot()
    def paste_import(self) -> None:
        text = QtWidgets.QApplication.clipboard().text() or ""
        n = self._add_accounts_from_text(text)
        if n:
            self.append_log(f"从剪贴板导入 {n} 个账号")
        else:
            QtWidgets.QMessageBox.information(self, "提示", "剪贴板中未找到有效账号格式")

    def _add_accounts_from_text(self, text: str) -> int:
        added = 0
        for line in (text or "").strip().splitlines():
            parsed = self._parse_mail_line(line)
            if parsed:
                parsed["status"] = "等待"
                self.accounts.append(parsed)
                added += 1
        if added:
            self._refresh_rows()
        return added

    # ---------------- Run control ----------------
    def _set_running(self, running: bool) -> None:
        self._running = running
        self._skip_current = False
        self.act_run_selected.setEnabled(not running)
        self.act_run_all.setEnabled(not running)
        self.act_skip.setEnabled(running)
        self.act_stop.setEnabled(running)

    def _is_cancelled(self) -> bool:
        return (not self._running) or self._skip_current

    @QtCore.Slot()
    def run_selected(self) -> None:
        indices = self._selected_indices()
        if not indices:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要注册的账号（支持多选）")
            return
        self._start_work(indices)

    @QtCore.Slot()
    def run_all(self) -> None:
        pending = [i for i, a in enumerate(self.accounts) if a.get("status") in ("等待", "失败")]
        if not pending:
            QtWidgets.QMessageBox.information(self, "提示", "没有等待注册或失败的账号")
            return
        self._start_work(pending)

    def _start_work(self, indices: list[int]) -> None:
        self.clear_logs()
        self.progress.setMaximum(len(indices))
        self.progress.setValue(0)
        self.statusBar().showMessage("任务运行中… 请勿关闭 BitBrowser 窗口")
        try:
            self._failed_batch_start(len(indices))
        except Exception:
            pass

        self._set_running(True)

        self._thread = QtCore.QThread()
        self._worker = Worker(
            run_one=self._run_one,
            accounts_ref=self.accounts,
            indices=indices,
            is_cancelled=self._is_cancelled,
            status_texts={},
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.append_log)
        self._worker.status.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.current.connect(self._on_current)
        self._worker.done.connect(self._on_done)
        self._worker.done.connect(self._thread.quit)
        self._worker.done.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    @QtCore.Slot()
    def skip_current(self) -> None:
        self._skip_current = True
        self.append_log(">>> 用户请求跳过当前账号，等待当前步骤结束…")

    @QtCore.Slot()
    def stop(self) -> None:
        self._running = False
        self._skip_current = True
        self.append_log(">>> 用户请求停止")
        self._set_running(False)

    # ---------------- Worker events ----------------
    @QtCore.Slot(str)
    def append_log(self, msg: str) -> None:
        self._log_buffer.append(msg)
        # 立即增量写入（过滤在重建视图里处理）
        self._append_log_if_pass(msg)

    def _classify(self, msg: str) -> str:
        s = (msg or "").strip()
        if not s:
            return "dim"
        if s.startswith("=") or s.startswith(">>>"):
            return "title"
        low = s.lower()
        if any(k in s for k in ("失败", "异常", "错误", "Traceback")) or "error" in low or "exception" in low:
            return "err"
        if any(k in s for k in ("警告", "warning", "WARN")):
            return "warn"
        if any(k in s for k in ("成功", "[成功]", "登录成功", "注册成功")):
            return "ok"
        return ""

    def _passes(self, msg: str, tag: str) -> bool:
        if self.cb_only_err.isChecked() and tag != "err":
            return False
        q = (self.ed_search.text() or "").strip().lower()
        if q and q not in (msg or "").lower():
            return False
        return True

    def _append_log_if_pass(self, msg: str) -> None:
        tag = self._classify(msg)
        if not self._passes(msg, tag):
            return

        cursor = self.log_view.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        fmt = QtGui.QTextCharFormat()
        color_map = {
            "err": "#b91c1c",
            "warn": "#b45309",
            "ok": "#047857",
            "title": "#1d4ed8",
            "dim": "#6b7280",
        }
        if tag in color_map:
            fmt.setForeground(QtGui.QColor(color_map[tag]))
        cursor.insertText(msg + "\n", fmt)
        self.log_view.setTextCursor(cursor)
        if self.cb_autoscroll.isChecked():
            self.log_view.ensureCursorVisible()

    @QtCore.Slot()
    def clear_logs(self) -> None:
        self._log_buffer.clear()
        self.log_view.clear()
        self.result_view.clear()

    @QtCore.Slot()
    def open_failed_accounts_plain(self) -> None:
        path = self._failed_accounts_file
        if path and os.path.isfile(path):
            try:
                if sys.platform == "darwin":
                    QtCore.QProcess.startDetached("open", [path])
                elif sys.platform == "win32":
                    os.startfile(path)  # type: ignore[attr-defined]
                else:
                    QtCore.QProcess.startDetached("xdg-open", [path])
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "打开失败", str(e))
        else:
            QtWidgets.QMessageBox.information(self, "提示", "尚无失败账号导出文件")

    @QtCore.Slot()
    def _rebuild_log_view(self) -> None:
        self.log_view.clear()
        for msg in self._log_buffer:
            self._append_log_if_pass(msg)

    @QtCore.Slot(int, str)
    def _on_status(self, idx: int, st: str) -> None:
        if 0 <= idx < len(self.accounts):
            self.accounts[idx]["status"] = st
        self._refresh_rows()
        self.lbl_step.setText(st)

    @QtCore.Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    @QtCore.Slot(str)
    def _on_current(self, s: str) -> None:
        self.lbl_current.setText(s)

    @QtCore.Slot(int, int)
    def _on_done(self, success: int, fail: int) -> None:
        self._set_running(False)
        self.lbl_current.setText("已完成")
        self.lbl_step.setText("")
        self.statusBar().showMessage(f"本轮结束 · 成功 {success} · 失败 {fail}")
        self.append_log(f"\n任务完成。成功: {success}，失败: {fail}")


def run_qt_app(
    *,
    window_title: str,
    output_file: str,
    failed_file: str,
    failed_accounts_file: str,
    parse_mail_line: Callable[[str], Optional[dict[str, str]]],
    run_one: Callable[[dict[str, Any], Callable[[str], None], Callable[[str], None], Callable[[], bool]], str],
    open_output: Callable[[], None],
    failed_batch_start: Callable[[int], None],
) -> int:
    app = QtWidgets.QApplication(sys.argv)
    apply_light_desktop_palette(app)

    win = MainWindow(
        window_title=window_title,
        output_file=output_file,
        failed_file=failed_file,
        failed_accounts_file=failed_accounts_file,
        parse_mail_line=parse_mail_line,
        run_one=run_one,
        open_output=open_output,
        failed_batch_start=failed_batch_start,
    )
    win.show()
    return app.exec()

