from __future__ import annotations

import os
import re
import sys
import json
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

KEEP_WINDOW_STATUS_OPTIONS = [
    "未开启2FA",
    "成功",
]


class ProxySettingsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        current_cfg: dict[str, Any],
        test_cb: Callable[[dict[str, str]], tuple[bool, str]],
        test_bb_cb: Callable[[dict[str, Any]], tuple[bool, str]],
    ):
        super().__init__(parent)
        self.setWindowTitle("系统设置")
        self.setMinimumWidth(450)
        self._test_cb = test_cb
        self._test_bb_cb = test_bb_cb
        self._init_ui(current_cfg)

    def _init_ui(self, cfg: dict[str, Any]) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)

        # 代理设置分组
        proxy_group = QtWidgets.QGroupBox("代理配置")
        proxy_layout = QtWidgets.QFormLayout(proxy_group)
        proxy_layout.setSpacing(10)

        self.cb_type = QtWidgets.QComboBox()
        self.cb_type.addItems(["http", "socks5"])
        self.cb_type.setCurrentText(cfg.get("proxyType", "http"))
        proxy_layout.addRow("代理类型：", self.cb_type)

        self.ed_host = QtWidgets.QLineEdit(cfg.get("proxyHost", ""))
        self.ed_host.setPlaceholderText("例如：127.0.0.1 或 代理域名")
        proxy_layout.addRow("服务器地址：", self.ed_host)

        self.ed_port = QtWidgets.QLineEdit(cfg.get("proxyPort", ""))
        self.ed_port.setPlaceholderText("例如：8080")
        proxy_layout.addRow("端口：", self.ed_port)

        self.ed_user = QtWidgets.QLineEdit(cfg.get("proxyUser", ""))
        self.ed_user.setPlaceholderText("选填")
        proxy_layout.addRow("用户名：", self.ed_user)

        self.ed_pass = QtWidgets.QLineEdit(cfg.get("proxyPass", ""))
        self.ed_pass.setPlaceholderText("选填")
        self.ed_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        proxy_layout.addRow("密码：", self.ed_pass)

        self.btn_test_proxy = QtWidgets.QPushButton("测试代理连接")
        self.btn_test_proxy.clicked.connect(self._on_test_proxy)
        proxy_layout.addRow("", self.btn_test_proxy)

        layout.addWidget(proxy_group)

        # BitBrowser 设置分组
        bb_group = QtWidgets.QGroupBox("BitBrowser 配置")
        bb_layout = QtWidgets.QFormLayout(bb_group)
        bb_layout.setSpacing(10)

        self.ed_bb_url = QtWidgets.QLineEdit(cfg.get("bitbrowserUrl", "http://127.0.0.1:54345"))
        self.ed_bb_url.setPlaceholderText("例如：http://127.0.0.1:54345")
        bb_layout.addRow("API 地址：", self.ed_bb_url)

        self.ed_bb_key = QtWidgets.QLineEdit(cfg.get("bitbrowserKey", ""))
        self.ed_bb_key.setPlaceholderText("BitBrowser API Key")
        bb_layout.addRow("API Key：", self.ed_bb_key)

        self.btn_test_bb = QtWidgets.QPushButton("检测 BitBrowser 服务")
        self.btn_test_bb.clicked.connect(self._on_test_bb)
        bb_layout.addRow("", self.btn_test_bb)

        layout.addWidget(bb_group)

        runtime_group = QtWidgets.QGroupBox("运行配置")
        runtime_layout = QtWidgets.QFormLayout(runtime_group)
        runtime_layout.setSpacing(10)

        self.sb_threads = QtWidgets.QSpinBox()
        self.sb_threads.setRange(1, 32)
        self.sb_threads.setValue(max(1, min(32, int(cfg.get("threadCount", 1) or 1))))
        self.sb_threads.setToolTip("同时运行的账号数量，建议从 1-3 开始逐步调整")
        runtime_layout.addRow("线程数：", self.sb_threads)

        keep_box = QtWidgets.QWidget()
        keep_layout = QtWidgets.QGridLayout(keep_box)
        keep_layout.setContentsMargins(0, 0, 0, 0)
        keep_layout.setHorizontalSpacing(14)
        keep_layout.setVerticalSpacing(6)
        selected_keep = {str(v).strip() for v in cfg.get("keepWindowStatuses", []) if str(v).strip()}
        self.keep_window_checks: dict[str, QtWidgets.QCheckBox] = {}
        for i, status in enumerate(KEEP_WINDOW_STATUS_OPTIONS):
            cb = QtWidgets.QCheckBox(status)
            cb.setChecked(status in selected_keep)
            row = i // 2
            col = i % 2
            keep_layout.addWidget(cb, row, col)
            self.keep_window_checks[status] = cb
        runtime_layout.addRow("保留档案：", keep_box)

        tip = QtWidgets.QLabel("建议先用 1-3 个线程测试稳定性，并发过高可能增加风控或资源占用。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #6b7280;")
        runtime_layout.addRow("", tip)

        layout.addWidget(runtime_group)

        remote_group = QtWidgets.QGroupBox("管理中心同步")
        remote_layout = QtWidgets.QFormLayout(remote_group)
        remote_layout.setSpacing(10)

        self.ed_web_admin_base_url = QtWidgets.QLineEdit(cfg.get("webAdminBaseUrl", ""))
        self.ed_web_admin_base_url.setPlaceholderText("例如：http://127.0.0.1:18700/api")
        remote_layout.addRow("客户端 API：", self.ed_web_admin_base_url)

        self.ed_web_admin_client_token = QtWidgets.QLineEdit(cfg.get("webAdminClientToken", ""))
        self.ed_web_admin_client_token.setPlaceholderText("桌面客户端 Token")
        remote_layout.addRow("客户端 Token：", self.ed_web_admin_client_token)

        self.cb_push_github_result = QtWidgets.QCheckBox("注册结果自动同步管理中心")
        self.cb_push_github_result.setChecked(bool(cfg.get("pushGithubResult", False)))
        remote_layout.addRow("", self.cb_push_github_result)

        self.cb_push_github_without_2fa = QtWidgets.QCheckBox("未开启 2FA 也回传（只要注册成功）")
        self.cb_push_github_without_2fa.setChecked(bool(cfg.get("pushGithubWithout2fa", True)))
        remote_layout.addRow("", self.cb_push_github_without_2fa)

        sync_tip = QtWidgets.QLabel("开启后：本地导入账号注册成功会回传 GitHub 账号库，注册失败会按导入时选择的官方/小水滴类型回传邮箱库。")
        sync_tip.setWordWrap(True)
        sync_tip.setStyleSheet("color: #6b7280;")
        remote_layout.addRow("", sync_tip)

        layout.addWidget(remote_group)

        # 底部按钮
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QtWidgets.QPushButton("保存设置")
        self.btn_save.setMinimumWidth(100)
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _on_test_proxy(self) -> None:
        cfg = self.get_config()
        if not cfg["proxyHost"] or not cfg["proxyPort"]:
            QtWidgets.QMessageBox.warning(self, "提示", "请填写完整的代理地址和端口")
            return

        self.btn_test_proxy.setEnabled(False)
        self.btn_test_proxy.setText("正在测试...")
        QtCore.QCoreApplication.processEvents()

        ok, msg = self._test_cb(cfg)
        self.btn_test_proxy.setEnabled(True)
        self.btn_test_proxy.setText("测试代理连接")

        if ok:
            QtWidgets.QMessageBox.information(self, "代理测试成功", msg)
        else:
            QtWidgets.QMessageBox.critical(self, "代理测试失败", msg)

    def _on_test_bb(self) -> None:
        self.btn_test_bb.setEnabled(False)
        self.btn_test_bb.setText("正在检测...")
        QtCore.QCoreApplication.processEvents()

        ok, msg = self._test_bb_cb(self.get_config())

        self.btn_test_bb.setEnabled(True)
        self.btn_test_bb.setText("检测 BitBrowser 服务")

        if ok:
            QtWidgets.QMessageBox.information(self, "BitBrowser 正常", msg)
        else:
            QtWidgets.QMessageBox.critical(self, "BitBrowser 异常", msg)

    def get_config(self) -> dict[str, Any]:
        return {
            "proxyType": self.cb_type.currentText(),
            "proxyHost": self.ed_host.text().strip(),
            "proxyPort": self.ed_port.text().strip(),
            "proxyUser": self.ed_user.text().strip(),
            "proxyPass": self.ed_pass.text().strip(),
            "bitbrowserUrl": self.ed_bb_url.text().strip(),
            "bitbrowserKey": self.ed_bb_key.text().strip(),
            "threadCount": self.sb_threads.value(),
            "webAdminBaseUrl": self.ed_web_admin_base_url.text().strip(),
            "webAdminClientToken": self.ed_web_admin_client_token.text().strip(),
            "pushGithubResult": self.cb_push_github_result.isChecked(),
            "pushGithubWithout2fa": self.cb_push_github_without_2fa.isChecked(),
            "keepWindowStatuses": [
                status for status, cb in self.keep_window_checks.items() if cb.isChecked()
            ],
        }


class ImportAccountsDialog(QtWidgets.QDialog):
    def __init__(self, parent: Optional[QtWidgets.QWidget], current_cfg: dict[str, Any]):
        super().__init__(parent)
        self.setWindowTitle("导入账号")
        self.setMinimumWidth(480)
        self._init_ui(current_cfg)

    def _init_ui(self, cfg: dict[str, Any]) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)

        source_group = QtWidgets.QGroupBox("账号来源")
        source_layout = QtWidgets.QVBoxLayout(source_group)
        source_layout.setSpacing(10)
        self.rb_local = QtWidgets.QRadioButton("本地文件 / 剪贴板")
        self.rb_remote = QtWidgets.QRadioButton("拉取管理中心远程账号")
        source_layout.addWidget(self.rb_local)
        source_layout.addWidget(self.rb_remote)

        source = str(cfg.get("accountSource", "local") or "local")
        if source == "remote":
            self.rb_remote.setChecked(True)
        else:
            self.rb_local.setChecked(True)
        layout.addWidget(source_group)

        remote_group = QtWidgets.QGroupBox("远程拉取")
        remote_layout = QtWidgets.QFormLayout(remote_group)
        remote_layout.setSpacing(10)

        self.ed_remote_base_url = QtWidgets.QLineEdit(cfg.get("webAdminBaseUrl", ""))
        self.ed_remote_base_url.setPlaceholderText("例如：http://127.0.0.1:18700/api")
        remote_layout.addRow("客户端 API：", self.ed_remote_base_url)

        self.ed_remote_token = QtWidgets.QLineEdit(cfg.get("webAdminClientToken", ""))
        self.ed_remote_token.setPlaceholderText("桌面客户端 Token")
        remote_layout.addRow("客户端 Token：", self.ed_remote_token)

        self.cb_receive_mode = QtWidgets.QComboBox()
        self.cb_receive_mode.addItem("小水滴收件", "xiaoshuidi")
        self.cb_receive_mode.addItem("官方收件", "official")
        receive_mode = str(cfg.get("mailReceiveMode", "xiaoshuidi") or "xiaoshuidi")
        idx = self.cb_receive_mode.findData(receive_mode)
        self.cb_receive_mode.setCurrentIndex(idx if idx >= 0 else 0)
        remote_layout.addRow("取件方式：", self.cb_receive_mode)

        mode_box = QtWidgets.QWidget()
        mode_layout = QtWidgets.QHBoxLayout(mode_box)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(12)
        self.rb_remote_count = QtWidgets.QRadioButton("拉取数量")
        self.rb_remote_all = QtWidgets.QRadioButton("拉取全部")
        mode_layout.addWidget(self.rb_remote_count)
        mode_layout.addWidget(self.rb_remote_all)
        mode_layout.addStretch(1)
        remote_layout.addRow("拉取方式：", mode_box)

        self.sb_remote_count = QtWidgets.QSpinBox()
        self.sb_remote_count.setRange(1, 9999)
        self.sb_remote_count.setValue(max(1, int(cfg.get("remoteFetchCount", 10) or 10)))
        remote_layout.addRow("拉取数量：", self.sb_remote_count)

        fetch_mode = str(cfg.get("remoteFetchMode", "count") or "count")
        if fetch_mode == "all":
            self.rb_remote_all.setChecked(True)
        else:
            self.rb_remote_count.setChecked(True)
        layout.addWidget(remote_group)

        tip = QtWidgets.QLabel("远程模式会从管理中心租约拉取邮箱；本地模式保持现有导入方式。当前官方收件仍依赖管理中心接口，小水滴可完全本地运行。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #6b7280;")
        layout.addWidget(tip)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btn_ok = QtWidgets.QPushButton("确定")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QtWidgets.QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

        self.rb_remote.toggled.connect(self._sync_state)
        self.rb_remote_count.toggled.connect(self._sync_state)
        self._sync_state()

    def _sync_state(self) -> None:
        remote_enabled = self.rb_remote.isChecked()
        self.ed_remote_base_url.setEnabled(remote_enabled)
        self.ed_remote_token.setEnabled(remote_enabled)
        self.rb_remote_count.setEnabled(remote_enabled)
        self.rb_remote_all.setEnabled(remote_enabled)
        self.sb_remote_count.setEnabled(remote_enabled and self.rb_remote_count.isChecked())

    def get_values(self) -> dict[str, Any]:
        return {
            "accountSource": "remote" if self.rb_remote.isChecked() else "local",
            "webAdminBaseUrl": self.ed_remote_base_url.text().strip(),
            "webAdminClientToken": self.ed_remote_token.text().strip(),
            "remoteFetchMode": "all" if self.rb_remote_all.isChecked() else "count",
            "remoteFetchCount": self.sb_remote_count.value(),
            "mailReceiveMode": str(self.cb_receive_mode.currentData() or "xiaoshuidi"),
        }


def _get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

UI_PREFS_FILE = os.path.join(_get_base_path(), ".ui_prefs.json")


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
            if s in ("成功", "未开启2FA"):
                return QtGui.QBrush(QtGui.QColor("#047857"))
            if s in ("失败",):
                return QtGui.QBrush(QtGui.QColor("#b91c1c"))
            if s in ("已注册",):
                return QtGui.QBrush(QtGui.QColor("#9333ea"))
            if s in ("用户名占用",):
                return QtGui.QBrush(QtGui.QColor("#c2410c"))
            if s in ("服务拒绝",):
                return QtGui.QBrush(QtGui.QColor("#dc2626"))
            if s in ("进行中", "人机验证", "取码验证", "获取2FA"):
                return QtGui.QBrush(QtGui.QColor("#1d4ed8"))
            if s in ("已跳过",):
                return QtGui.QBrush(QtGui.QColor("#6b7280"))
        return None

    def refresh_all(self) -> None:
        self.beginResetModel()
        self.endResetModel()


class AccountWorker(QtCore.QObject):
    log = QtCore.Signal(str)
    status = QtCore.Signal(int, str)         # idx, status_text
    current = QtCore.Signal(str)             # current label
    done = QtCore.Signal(int, str)           # idx, result

    def __init__(
        self,
        run_one: Callable[[dict[str, Any], Callable[[str], None], Callable[[str], None], Callable[[], bool]], str],
        account: dict[str, Any],
        idx: int,
        seq: int,
        total: int,
        slot_id: int,
        should_cancel_current: Callable[[], bool],
    ):
        super().__init__()
        self._run_one = run_one
        self._account = account
        self._idx = idx
        self._seq = seq
        self._total = total
        self._slot_id = slot_id
        self._should_cancel_current = should_cancel_current

    def slot_id(self) -> int:
        return self._slot_id

    def _log_prefix(self) -> str:
        email = str(self._account.get("email", ""))
        return f"[线程{self._slot_id}][{self._seq}/{self._total}][{email}]"

    def _format_log(self, msg: str) -> str:
        text = str(msg or "")
        if not text:
            return self._log_prefix()
        email = str(self._account.get("email", ""))
        email_tag = f"[{email}] "
        lines = text.splitlines()
        if not lines:
            lines = [text]
        out: list[str] = []
        for line in lines:
            clean = line
            if clean.startswith(email_tag):
                clean = clean[len(email_tag):]
            if clean:
                out.append(f"{self._log_prefix()} {clean}")
            else:
                out.append(self._log_prefix())
        return "\n".join(out)

    @QtCore.Slot()
    def run(self) -> None:
        if self._should_cancel_current():
            self.done.emit(self._idx, "skipped")
            return

        email = self._account.get("email", "")
        self.current.emit(f"线程{self._slot_id} 处理中: {email}")
        self.log.emit("\n" + self._format_log("=" * 55))
        self.log.emit(self._format_log("开始处理账号"))
        self.log.emit(self._format_log("=" * 55))

        def _log(msg: str) -> None:
            self.log.emit(self._format_log(msg))

        def _on_status(st: str) -> None:
            self.status.emit(self._idx, st)

        result = self._run_one(self._account, _log, _on_status, self._should_cancel_current)
        self.done.emit(self._idx, result)


class WorkerController(QtCore.QObject):
    log = QtCore.Signal(str)
    status = QtCore.Signal(int, str)
    progress = QtCore.Signal(int, int)
    current = QtCore.Signal(str)
    done = QtCore.Signal(int, int)
    stopping = QtCore.Signal()
    slot_update = QtCore.Signal(int, str, str)  # slot_id, label, state

    def __init__(
        self,
        run_one: Callable[[dict[str, Any], Callable[[str], None], Callable[[str], None], Callable[[], bool]], str],
        accounts_ref: list[dict[str, Any]],
        indices: list[int],
        concurrency: int,
        should_stop_dispatch: Callable[[], bool],
        should_cancel_current: Callable[[], bool],
    ):
        super().__init__()
        self._run_one = run_one
        self._accounts = accounts_ref
        self._indices = indices
        self._concurrency = max(1, concurrency)
        self._should_stop_dispatch = should_stop_dispatch
        self._should_cancel_current = should_cancel_current
        self._next_pos = 0
        self._running = 0
        self._completed = 0
        self._success = 0
        self._fail = 0
        self._finished = False
        self._stop_notice_emitted = False
        self._threads: list[QtCore.QThread] = []
        self._workers: list[AccountWorker] = []
        self._result_lock = threading.Lock()
        self._free_slots: list[int] = list(range(1, self._concurrency + 1))
        self._worker_slots: dict[AccountWorker, int] = {}

    @QtCore.Slot()
    def run(self) -> None:
        if not self._indices:
            self._finalize_if_needed()
            return
        for slot_id in range(1, self._concurrency + 1):
            self.slot_update.emit(slot_id, f"线程{slot_id}", "空闲")
        self.progress.emit(0, len(self._indices))
        self._launch_more()

    def _launch_more(self) -> None:
        while (
            not self._should_stop_dispatch()
            and self._running < self._concurrency
            and self._free_slots
            and self._next_pos < len(self._indices)
        ):
            idx = self._indices[self._next_pos]
            seq = self._next_pos + 1
            if self._start_one(idx, seq, len(self._indices)):
                self._next_pos += 1
            else:
                break

        if self._should_stop_dispatch() and not self._stop_notice_emitted:
            self._stop_notice_emitted = True
            self.log.emit(">>> 已停止派发新任务，等待已启动线程收尾…")
            self.stopping.emit()
        self._finalize_if_needed()

    def _start_one(self, idx: int, seq: int, total: int) -> bool:
        if not self._free_slots:
            return False
        slot_id = self._free_slots.pop(0)
        email = str(self._accounts[idx].get("email", ""))
        worker = AccountWorker(
            run_one=self._run_one,
            account=self._accounts[idx],
            idx=idx,
            seq=seq,
            total=total,
            slot_id=slot_id,
            should_cancel_current=self._should_cancel_current,
        )
        thread = QtCore.QThread()
        worker.moveToThread(thread)

        worker.log.connect(self.log)
        worker.status.connect(self.status)
        worker.current.connect(self.current)
        worker.done.connect(self._on_worker_done)
        worker.done.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thr=thread, wk=worker: self._cleanup_worker(thr, wk))

        self._threads.append(thread)
        self._workers.append(worker)
        self._worker_slots[worker] = slot_id
        self._running += 1
        self.slot_update.emit(slot_id, f"线程{slot_id}", f"运行中 · {email}")
        thread.start()
        return True

    def _cleanup_worker(self, thread: QtCore.QThread, worker: AccountWorker) -> None:
        if thread in self._threads:
            self._threads.remove(thread)
        if worker in self._workers:
            self._workers.remove(worker)
        slot_id = self._worker_slots.pop(worker, 0)
        if slot_id:
            self._free_slots.append(slot_id)
            self._free_slots.sort()
            self.slot_update.emit(slot_id, f"线程{slot_id}", "空闲")
        self._launch_more()

    @QtCore.Slot(int, str)
    def _on_worker_done(self, idx: int, result: str) -> None:
        with self._result_lock:
            self._running = max(0, self._running - 1)
            self._completed += 1
            if result in ("success", "partial"):
                self._success += 1
            elif result == "failed":
                self._fail += 1

        email = ""
        if 0 <= idx < len(self._accounts):
            email = str(self._accounts[idx].get("email", ""))
        if email:
            self.current.emit(f"最近完成: {email}")
        self.progress.emit(self._completed, len(self._indices))

    def _finalize_if_needed(self) -> None:
        if self._finished:
            return
        if self._running > 0:
            return
        if self._next_pos < len(self._indices) and not self._should_stop_dispatch():
            return
        self._finished = True
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
        deduplicate_failed: Callable[[], int],
        get_app_cfg: Callable[[], dict[str, Any]],
        get_proxy_cfg: Callable[[], dict[str, str]],
        save_proxy_cfg: Callable[[dict[str, Any]], None],
        test_proxy_conn: Callable[[dict[str, str]], tuple[bool, str]],
        test_bb_conn: Callable[..., tuple[bool, str]],
        pull_remote_accounts: Callable[[dict[str, Any]], list[dict[str, Any]]],
        icon_path: Optional[str] = None,
    ):
        super().__init__()
        self.setWindowTitle(window_title)
        # 默认尺寸：优先“适中”而不是巨大；日志区在底部可折叠/可浮动
        # 相比之前更紧凑（约 70–80%），但仍保证表格/按钮/日志好用
        self.resize(980, 720)
        self.setMinimumSize(900, 640)
        
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        self._prefs = _load_ui_prefs()
        self._output_file = output_file
        self._failed_file = failed_file
        self._failed_accounts_file = failed_accounts_file
        self._parse_mail_line = parse_mail_line
        self._run_one = run_one
        self._open_output_cb = open_output
        self._failed_batch_start = failed_batch_start
        self._deduplicate_failed = deduplicate_failed
        self._get_app_cfg = get_app_cfg
        self._get_proxy_cfg = get_proxy_cfg
        self._save_proxy_cfg = save_proxy_cfg
        self._test_proxy_conn = test_proxy_conn
        self._test_bb_conn = test_bb_conn
        self._pull_remote_accounts = pull_remote_accounts

        self.accounts: list[dict[str, Any]] = []
        self._rows: list[AccountRow] = []
        self._running = False
        self._stop_requested = False
        self._skip_current = False
        self._thread_count = max(1, min(32, int(self._get_app_cfg().get("threadCount", 1) or 1)))

        self._worker: Optional[WorkerController] = None
        self._thread_status_labels: dict[int, QtWidgets.QLabel] = {}
        self._current_batch_indices: list[int] = []
        self._batch_total = 0
        self._batch_done = 0
        self._batch_success = 0
        self._batch_fail = 0

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

        act_dedup = QtGui.QAction("清理已成功", self)
        act_dedup.triggered.connect(self.deduplicate_accounts)
        tb.addAction(act_dedup)

        tb.addSeparator()
        act_proxy = QtGui.QAction("系统设置", self)
        act_proxy.triggered.connect(self.show_proxy_settings)
        tb.addAction(act_proxy)

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
        self.lbl_threads = QtWidgets.QLabel(f"并发线程：{self._thread_count}")
        self.lbl_threads.setStyleSheet("color: #6b7280;")
        pl.addWidget(self.lbl_threads)

        self.thread_group = QtWidgets.QGroupBox("线程状态")
        thread_layout = QtWidgets.QGridLayout(self.thread_group)
        thread_layout.setContentsMargins(12, 12, 12, 12)
        thread_layout.setHorizontalSpacing(10)
        thread_layout.setVerticalSpacing(8)
        self._thread_status_layout = thread_layout
        pl.addWidget(self.thread_group)

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
        self._rebuild_thread_status_panel()
        self._refresh_result_view()

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

    def _rebuild_thread_status_panel(self) -> None:
        while self._thread_status_layout.count():
            item = self._thread_status_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._thread_status_labels.clear()

        cols = 2 if self._thread_count > 1 else 1
        for i in range(self._thread_count):
            slot_id = i + 1
            label = QtWidgets.QLabel(f"线程{slot_id}：空闲")
            label.setStyleSheet("color: #6b7280;")
            label.setWordWrap(True)
            row = i // cols
            col = i % cols
            self._thread_status_layout.addWidget(label, row, col)
            self._thread_status_labels[slot_id] = label

    def _set_thread_status(self, slot_id: int, text: str, running: bool = False) -> None:
        label = self._thread_status_labels.get(slot_id)
        if not label:
            return
        color = "#1d4ed8" if running else "#6b7280"
        label.setStyleSheet(f"color: {color};")
        label.setText(text)

    def _get_batch_metrics(self) -> dict[str, int]:
        if not self._current_batch_indices:
            return {
                "total": 0,
                "done": 0,
                "success": 0,
                "fail": 0,
                "skipped": 0,
            }

        success_states = {"成功", "未开启2FA"}
        failure_states = {"失败", "已注册", "用户名占用", "服务拒绝"}

        success = 0
        fail = 0
        skipped = 0
        total = 0
        for idx in self._current_batch_indices:
            if idx < 0 or idx >= len(self.accounts):
                continue
            total += 1
            status = str(self.accounts[idx].get("status", "等待"))
            if status in success_states:
                success += 1
            elif status in failure_states:
                fail += 1
            elif status == "已跳过":
                skipped += 1

        done = success + fail + skipped
        return {
            "total": total,
            "done": done,
            "success": success,
            "fail": fail,
            "skipped": skipped,
        }

    def _refresh_result_view(self) -> None:
        total = len(self.accounts)
        counts = {
            "等待": 0,
            "进行中": 0,
            "成功": 0,
            "失败": 0,
            "已跳过": 0,
            "其他": 0,
        }
        success_lines: list[str] = []
        failed_lines: list[str] = []

        success_states = {"成功", "未开启2FA"}
        running_states = {"进行中", "人机验证", "取码验证", "获取2FA"}
        failure_states = {"失败", "已注册", "用户名占用", "服务拒绝"}

        for acc in self.accounts:
            email = str(acc.get("email", ""))
            status = str(acc.get("status", "等待"))
            if status == "等待":
                counts["等待"] += 1
            elif status in running_states:
                counts["进行中"] += 1
            elif status in success_states:
                counts["成功"] += 1
                success_lines.append(f"{email}\t{status}")
            elif status in failure_states:
                counts["失败"] += 1
                failed_lines.append(f"{email}\t{status}")
            elif status == "已跳过":
                counts["已跳过"] += 1
            else:
                counts["其他"] += 1

        batch = self._get_batch_metrics()
        if batch["done"] < batch["total"]:
            batch_denominator = batch["done"]
            batch_rate_label = "当前成功率（已完成）"
        else:
            batch_denominator = batch["total"]
            batch_rate_label = "批次成功率"
        batch_rate = (batch["success"] / batch_denominator * 100.0) if batch_denominator else 0.0

        lines = [
            f"总数：{total}",
            f"等待：{counts['等待']}",
            f"进行中：{counts['进行中']}",
            f"成功：{counts['成功']}",
            f"失败：{counts['失败']}",
            f"已跳过：{counts['已跳过']}",
        ]
        if counts["其他"]:
            lines.append(f"其他：{counts['其他']}")

        if batch["total"] > 0:
            lines.extend([
                "",
                "[当前批次]",
                f"批次总数：{batch['total']}",
                f"批次完成：{batch['done']}",
                f"批次成功：{batch['success']}",
                f"批次失败：{batch['fail']}",
                f"批次跳过：{batch['skipped']}",
                f"{batch_rate_label}：{batch_rate:.1f}%",
            ])

        if success_lines:
            lines.append("")
            lines.append("[成功账号]")
            lines.extend(success_lines)

        if failed_lines:
            lines.append("")
            lines.append("[失败账号]")
            lines.extend(failed_lines)

        self.result_view.setPlainText("\n".join(lines))

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
        self._refresh_result_view()

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
        dlg = ImportAccountsDialog(self, self._get_app_cfg())
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        opts = dlg.get_values()
        self._save_proxy_cfg(opts)
        if opts["accountSource"] == "remote":
            try:
                accounts = self._pull_remote_accounts(opts)
                n = self._add_remote_accounts(accounts)
                self.append_log(f"从管理中心拉取 {n} 个账号")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "远程拉取失败", str(e))
            return

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
        dlg = ImportAccountsDialog(self, self._get_app_cfg())
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        opts = dlg.get_values()
        self._save_proxy_cfg(opts)
        if opts["accountSource"] == "remote":
            try:
                accounts = self._pull_remote_accounts(opts)
                n = self._add_remote_accounts(accounts)
                self.append_log(f"从管理中心拉取 {n} 个账号")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "远程拉取失败", str(e))
            return

        text = QtWidgets.QApplication.clipboard().text() or ""
        n = self._add_accounts_from_text(text)
        if n:
            self.append_log(f"从剪贴板导入 {n} 个账号")
        else:
            QtWidgets.QMessageBox.information(self, "提示", "剪贴板中未找到有效账号格式")

    def _add_accounts_from_text(self, text: str) -> int:
        receive_mode = str(self._get_app_cfg().get("mailReceiveMode", "xiaoshuidi") or "xiaoshuidi")
        added = 0
        for line in (text or "").strip().splitlines():
            parsed = self._parse_mail_line(line, receive_mode)
            if parsed:
                parsed["status"] = "等待"
                self.accounts.append(parsed)
                added += 1
        if added:
            self._refresh_rows()
        return added

    def _add_remote_accounts(self, accounts: list[dict[str, Any]]) -> int:
        added = 0
        for account in accounts:
            if not isinstance(account, dict):
                continue
            account = dict(account)
            account["status"] = "等待"
            self.accounts.append(account)
            added += 1
        if added:
            self._refresh_rows()
        return added

    # ---------------- Run control ----------------
    def _set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self._stop_requested = False
            self._skip_current = False
        self.act_run_selected.setEnabled(not running)
        self.act_run_all.setEnabled(not running)
        self.act_skip.setEnabled(running and self._thread_count == 1)
        self.act_stop.setEnabled(running)

    def _should_stop_dispatch(self) -> bool:
        return self._stop_requested or (not self._running)

    def _should_cancel_current(self) -> bool:
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
        pending = [i for i, a in enumerate(self.accounts) if a.get("status") in ("等待", "失败", "服务拒绝", "用户名占用")]
        if not pending:
            QtWidgets.QMessageBox.information(self, "提示", "没有等待注册或失败的账号")
            return
        self._start_work(pending)

    def _start_work(self, indices: list[int]) -> None:
        self.clear_logs()
        self._rebuild_thread_status_panel()
        self._current_batch_indices = list(indices)
        self._batch_total = len(indices)
        self._batch_done = 0
        self._batch_success = 0
        self._batch_fail = 0
        self._refresh_result_view()
        self.progress.setMaximum(len(indices))
        self.progress.setValue(0)
        self.lbl_threads.setText(f"并发线程：{self._thread_count}")
        self.statusBar().showMessage(f"任务运行中… 请勿关闭 BitBrowser 窗口（并发 {self._thread_count}）")
        try:
            self._failed_batch_start(len(indices))
        except Exception:
            pass

        self._set_running(True)
        self._worker = WorkerController(
            run_one=self._run_one,
            accounts_ref=self.accounts,
            indices=indices,
            concurrency=self._thread_count,
            should_stop_dispatch=self._should_stop_dispatch,
            should_cancel_current=self._should_cancel_current,
        )
        self._worker.log.connect(self.append_log)
        self._worker.status.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.current.connect(self._on_current)
        self._worker.stopping.connect(self._on_stopping)
        self._worker.slot_update.connect(self._on_slot_update)
        self._worker.done.connect(self._on_done)
        self._worker.done.connect(self._worker.deleteLater)
        self._worker.done.connect(lambda *_args: setattr(self, "_worker", None))
        QtCore.QTimer.singleShot(0, self._worker.run)

    @QtCore.Slot()
    def skip_current(self) -> None:
        if self._thread_count > 1:
            QtWidgets.QMessageBox.information(self, "提示", "多线程模式下不支持“跳过当前”，请使用“停止”。")
            return
        self._skip_current = True
        self.append_log(">>> 用户请求跳过当前账号，等待当前步骤结束…")

    @QtCore.Slot()
    def stop(self) -> None:
        self._stop_requested = True
        self.append_log(">>> 用户请求停止：不再派发新任务，已启动线程会继续收尾")
        self.statusBar().showMessage("正在停止任务…等待已启动线程收尾")
        self.act_run_selected.setEnabled(False)
        self.act_run_all.setEnabled(False)
        self.act_skip.setEnabled(False)
        self.act_stop.setEnabled(False)

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
        self._refresh_result_view()

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
    def deduplicate_accounts(self, silent: bool = False) -> None:
        try:
            n = self._deduplicate_failed()
            if not silent:
                if n > 0:
                    self.append_log(f">>> 清理完成：从失败列表中移除了 {n} 个已成功的账号")
                    QtWidgets.QMessageBox.information(self, "清理完成", f"已从失败列表中移除 {n} 个已成功的账号")
                else:
                    self.append_log(">>> 清理完成：失败列表中未发现已成功的账号")
                    QtWidgets.QMessageBox.information(self, "清理完成", "失败列表中未发现已成功的账号")
        except Exception as e:
            if not silent:
                QtWidgets.QMessageBox.warning(self, "清理失败", str(e))

    @QtCore.Slot()
    def show_proxy_settings(self) -> None:
        current = self._get_app_cfg()

        def _test_bb_with_current_ui(cfg: dict[str, Any]) -> tuple[bool, str]:
            try:
                return self._test_bb_conn(cfg)
            except TypeError:
                return self._test_bb_conn()

        dlg = ProxySettingsDialog(self, current, self._test_proxy_conn, _test_bb_with_current_ui)
        self._active_settings_dialog = dlg
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            new_cfg = dlg.get_config()
            self._save_proxy_cfg(new_cfg)
            self._thread_count = max(1, min(32, int(new_cfg.get("threadCount", 1) or 1)))
            self.lbl_threads.setText(f"并发线程：{self._thread_count}")
            self._rebuild_thread_status_panel()
            self.append_log(">>> 系统设置已保存")
            QtWidgets.QMessageBox.information(self, "设置已保存", "新的代理与 BitBrowser 配置已生效。")
        self._active_settings_dialog = None

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
        self._batch_done = done
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self._refresh_result_view()

    @QtCore.Slot(str)
    def _on_current(self, s: str) -> None:
        self.lbl_current.setText(s)

    @QtCore.Slot()
    def _on_stopping(self) -> None:
        self.lbl_step.setText("停止中")
        self.statusBar().showMessage("已停止派发新任务，等待已启动线程收尾")

    @QtCore.Slot(int, str, str)
    def _on_slot_update(self, slot_id: int, label: str, state: str) -> None:
        text = f"{label}：{state}"
        running = state != "空闲"
        self._set_thread_status(slot_id, text, running=running)

    @QtCore.Slot(int, int)
    def _on_done(self, success: int, fail: int) -> None:
        batch = self._get_batch_metrics()
        self._batch_success = batch["success"]
        self._batch_fail = batch["fail"]
        self._batch_done = batch["done"]
        self._set_running(False)
        self.lbl_current.setText("已完成")
        self.lbl_step.setText("")
        if batch["done"] < batch["total"]:
            rate_denominator = batch["done"]
            rate_label = "成功率（已完成部分）"
        else:
            rate_denominator = batch["total"]
            rate_label = "成功率"
        rate = (batch["success"] / rate_denominator * 100.0) if rate_denominator else 0.0
        self.statusBar().showMessage(
            f"本轮结束 · 成功 {success} · 失败 {fail} · {rate_label} {rate:.1f}%"
        )
        self.append_log(
            f"\n任务完成。成功: {success}，失败: {fail}，{rate_label}: {rate:.1f}%"
        )
        for slot_id in self._thread_status_labels:
            self._set_thread_status(slot_id, f"线程{slot_id}：空闲", running=False)
        self._refresh_result_view()
        # 任务结束后自动执行一次清理
        self.deduplicate_accounts(silent=True)


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
    deduplicate_failed: Callable[[], int],
    get_app_cfg: Callable[[], dict[str, Any]],
    get_proxy_cfg: Callable[[], dict[str, str]],
    save_proxy_cfg: Callable[[dict[str, Any]], None],
    test_proxy_conn: Callable[[dict[str, str]], tuple[bool, str]],
    test_bb_conn: Callable[..., tuple[bool, str]],
    pull_remote_accounts: Callable[[dict[str, Any]], list[dict[str, Any]]],
    **kwargs: Any,
) -> int:
    app = QtWidgets.QApplication(sys.argv)
    apply_light_desktop_palette(app)
    
    if kwargs.get("icon_path") and os.path.exists(kwargs["icon_path"]):
        app.setWindowIcon(QtGui.QIcon(kwargs["icon_path"]))

    win = MainWindow(
        window_title=window_title,
        output_file=output_file,
        failed_file=failed_file,
        failed_accounts_file=failed_accounts_file,
        parse_mail_line=parse_mail_line,
        run_one=run_one,
        open_output=open_output,
        failed_batch_start=failed_batch_start,
        deduplicate_failed=deduplicate_failed,
        get_app_cfg=get_app_cfg,
        get_proxy_cfg=get_proxy_cfg,
        save_proxy_cfg=save_proxy_cfg,
        test_proxy_conn=test_proxy_conn,
        test_bb_conn=test_bb_conn,
        pull_remote_accounts=pull_remote_accounts,
        icon_path=kwargs.get("icon_path"),
    )
    win.show()
    return app.exec()
