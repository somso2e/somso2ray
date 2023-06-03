from PyQt5.QtCore import QThread, pyqtSignal, QSemaphore
from PyQt5.QtWidgets import QVBoxLayout, QLabel, QPushButton, QDialog, QPlainTextEdit
import utils
import pandas as pd
import requests
import base64
import v2ray


class AddConnectionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Add Connections")

        self.label = QLabel("Put Connections one per line")
        self.input = QPlainTextEdit()

        self.button = QPushButton("Add")
        self.button.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.button)

        self.setLayout(layout)


class PingThread(QThread):
    result_sig = pyqtSignal(int, str)

    def __init__(self, rows, targets, func):
        super().__init__()
        self.rows = rows
        self.targets = targets
        self.func = func
        self.workers = []

    def run(self):
        for row, target in zip(self.rows, self.targets):
            worker = PingWorker(row, target, self.func)
            worker.result_sig.connect(self.handle_sig)
            self.workers.append(worker)
            worker.start()

    def handle_sig(self, row, result):
        self.result_sig.emit(row, result)


class PingWorker(QThread):
    result_sig = pyqtSignal(int, str)
    semaphore = QSemaphore(1000)

    def __init__(self, row, target, func):
        super().__init__()
        self.row = row
        self.target = target
        self.func = func

    def run(self):
        PingWorker.semaphore.acquire()
        self.result_sig.emit(self.row, self.func(self.target))
        PingWorker.semaphore.release()


class SubscriptionThread(QThread):
    finished_sig = pyqtSignal(bool, int, pd.DataFrame)

    def __init__(self, rows, addresses, parent=None):
        super().__init__(parent)
        self.addresses = addresses
        self.rows = rows
        self.workers = []

    def run(self):
        for row, address in zip(self.rows, self.addresses):
            utils.log(f"Updating subscription {address}")
            worker = SubscriptionWorker(row, address)
            worker.finished_sig.connect(self.handle_sig)
            self.workers.append(worker)
            worker.start()

    def handle_sig(self, success, row, result):
        self.finished_sig.emit(success, row, result)


class SubscriptionWorker(QThread):
    finished_sig = pyqtSignal(bool, int, pd.DataFrame)
    semaphore = QSemaphore(10)

    def __init__(self, row, address):
        super().__init__()
        self.address = address
        self.row = row

    def run(self):
        SubscriptionWorker.semaphore.acquire()
        proxies = {
            "http": "192.168.1.102:2000",
            "https": "192.168.1.102:2000"
        }
        proxies = {
            "http": "",
            "https": ""
        }
        success = True
        try:
            ret = requests.get(self.address, proxies=proxies, timeout=30)
            try:
                ret2 = base64.b64decode(ret.text.strip()).decode("utf-8")
                items = ret2.split("\n")
            except Exception:
                items = ret.text.strip().split("\n")
            finally:
                servers_configs = v2ray.decode_multiple_configs(items)
            utils.log(
                f"Subscribing to {self.address} was successful, {len(servers_configs)} servers were added")

        except Exception as e:
            utils.log(f"Error occured while updating subscription: {str(e)}")
            success = False
            servers_configs = pd.DataFrame([])

        self.finished_sig.emit(success, self.row, servers_configs)
        SubscriptionWorker.semaphore.release()
