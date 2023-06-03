import v2ray
import utils
import pandas as pd
import re
import os
import json
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSemaphore, QTimer
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTableWidget, \
    QTableWidgetItem, QLabel, QLineEdit, QPushButton, QDialog, QMenu, QHBoxLayout, \
    QTableWidgetSelectionRange, QAbstractItemView, QAction, QPlainTextEdit, \
    QHeaderView
import sys
from datetime import datetime
# URL_MATCH_REGEX = r"(http(s)?:\/\/.)?(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)"


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)


class SubscriptionManager(QDialog):
    subscription_updated_sig = pyqtSignal(str, int, pd.DataFrame)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.json_path = "./subscriptions.json"

        self.table = QTableWidget(self)
        self.COLUMNS = ["Address", "Group", "Last Updated", "Status"]
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)

        for i in range(len(self.COLUMNS)):
            self.table.setColumnWidth(i, 100)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(len(self.COLUMNS) - 1, QHeaderView.Stretch)
        for i in range(len(self.COLUMNS) - 1):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

        self.load_json()

        self.table.cellChanged.connect(self.on_cell_changed)
        self.create_layout()

        self.adjustSize()

    def create_layout(self):
        buttons_laytout = QHBoxLayout()

        add_bttn = QPushButton("Add")
        add_bttn.clicked.connect(self.add_sub)

        remove_bttn = QPushButton("Remove")
        remove_bttn.clicked.connect(self.remove_sub)

        update_bttn = QPushButton("Update")
        update_bttn.clicked.connect(self.update)

        update_all_bttn = QPushButton("Update all")
        update_all_bttn.clicked.connect(self.update_all)

        buttons_laytout.addWidget(add_bttn)
        buttons_laytout.addWidget(remove_bttn)
        buttons_laytout.addWidget(update_bttn)
        buttons_laytout.addWidget(update_all_bttn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(buttons_laytout)

    def on_cell_changed(self, row, column):
        self.save_json()

    def save_json(self):
        subscriptions = {"subscriptions": []}
        for row in range(self.table.rowCount()):
            content = {}
            for col, column in enumerate(self.COLUMNS):
                item = self.table.item(row, col)
                if item is not None:
                    content[column] = item.text()
            subscriptions["subscriptions"].append(content)

        with open(self.json_path, "w") as f:
            f.write(json.dumps(subscriptions, indent=4))

    def load_json(self):
        if os.path.isfile(self.json_path):
            with open(self.json_path, "r") as f:
                subscriptions = json.load(f)
        else:
            subscriptions = {
                "subscriptions": [
                    {column: "" for column in self.COLUMNS}
                ]
            }

        for row, sub in enumerate(subscriptions["subscriptions"]):
            self.table.insertRow(row)
            self.set_row(row, sub)

    def add_sub(self):
        # only add a new row if the last row is empty
        row_count = self.table.rowCount()
        is_empty = all(self.table.item(row_count - 1, col).text() == ""
                       for col in range(len(self.COLUMNS)))
        if not is_empty:
            self.table.insertRow(row_count)
            self.set_row(row_count)

    def remove_sub(self):
        selected_rows = self.get_selected_rows()
        for row in selected_rows:
            self.table.removeRow(row)
            group_name = self.table.item(row, self.COLUMNS.index("Group")).text()
            self.subscription_updated_sig.emit(group_name,row, pd.DataFrame())
        self.save_json()

    def update_rows(self, rows):
        subs = []
        for row in rows:
            subs.append(self.table.item(row, self.COLUMNS.index("Address")).text())
            self.table.item(row, self.COLUMNS.index("Status")).setText("Updating...")

        self.thread = v2ray.SubscriptionThread(rows, subs)
        self.thread.finished_sig.connect(self.on_subscription_update)
        self.thread.start()

    def update(self):
        self.update_rows(self.get_selected_rows())

    def update_all(self):
        self.update_rows(list(range(self.table.rowCount())))

    def on_subscription_update(self, success, row, servers: pd.DataFrame):
        if success:
            status = f"{len(servers)} Servers"
            time_now = datetime.now().strftime("%Y/%m/%d %H:%M")
            self.table.item(row, self.COLUMNS.index("Last Updated")).setText(time_now)
            group_name = self.table.item(row, self.COLUMNS.index("Group")).text()
            servers["Group"] = group_name
            self.subscription_updated_sig.emit(group_name, row, servers)
        else:
            status = "Failed"
        self.table.item(row, self.COLUMNS.index("Status")).setText(status)

    def closeEvent(self, event):
        for row in range(self.table.rowCount()):
            name_cell = self.table.item(row, self.COLUMNS.index("Group"))
            # Set the default Group name the URL without the https
            if name_cell.text() == "":
                address = self.table.item(row, self.COLUMNS.index("Address"))
                address = re.sub(r"https?:\/\/", "", address)
                name_cell.setText(address)
        self.save_json()

    def get_selected_rows(self):
        selected_ranges = self.table.selectedRanges()
        selected_rows = []
        for selected_range in selected_ranges:
            for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
                if row not in selected_rows:
                    selected_rows.append(row)
        return selected_rows

    def set_row(self, row, values=None):
        if values is None:
            values = {column: "" for column in self.COLUMNS}
        for col, column in enumerate(self.COLUMNS):
            item = QTableWidgetItem(values[column])
            if col in [2, 3]:
                item.setFlags(item.flags() & ~ Qt.ItemIsEditable)
            self.table.setItem(row, col, item)


class ServersTableWidget(QTableWidget):
    def __init__(self):
        super().__init__()
        self.COLUMNS = ["Type", "Name", "IP", "Port", "Ping", "Real Delay", "Group"]
        self.table_contents = pd.DataFrame(columns=self.COLUMNS)
        self.table_contents["_hashed"] = None
        self.table_contents["_sub_id"] = None
        self.load()

        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_right_click_menu)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.itemClicked.connect(self.highlight_row)

        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSortingEnabled(True)
        self.refresh()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.save)
        self.timer.setInterval(10000)
        self.timer.start()

    def show_right_click_menu(self, position):
        menu = QMenu(self)
        connect_action = QAction("Connect", self)
        connect_action.triggered.connect(self.connect)

        ping_action = QAction("Ping", self)
        ping_action.triggered.connect(self.ping)

        real_delay_action = QAction("Real Delay", self)
        real_delay_action.triggered.connect(self.real_delay)

        delete_config_action = QAction("Delete", self)
        delete_config_action.triggered.connect(self.delete_configs)

        menu.addAction(connect_action)
        menu.addAction(ping_action)
        menu.addAction(real_delay_action)
        menu.addAction(delete_config_action)

        menu.exec_(self.viewport().mapToGlobal(position))

    def connect(self):
        self.connect_thread = v2ray.connect(self.table_contents.iloc[self.currentRow()]["_hashed"])

    def delete_configs(self):
        selected_rows = self.get_selected_rows()
        self.table_contents.drop(selected_rows, inplace=True)
        self.table_contents.reset_index(inplace=True, drop=True)
        self.refresh()

    def ping(self):
        selected_rows = self.get_selected_rows()
        col = self.COLUMNS.index("Ping")
        for row in selected_rows:
            self.setItem(row, col, QTableWidgetItem())
        self.thread = v2ray.PingThread(
            selected_rows, self.table_contents.iloc[selected_rows]["IP"], v2ray.ping_test)
        self.thread.result_sig.connect(lambda row, result: self.set_cell(row, col, result))
        self.thread.start()

    def real_delay(self):
        selected_rows = self.get_selected_rows()
        col = self.COLUMNS.index("Real Delay")
        # clear the old results
        for row in selected_rows:
            self.setItem(row, col, QTableWidgetItem())
        self.thread = v2ray.PingThread(
            selected_rows, self.table_contents.iloc[selected_rows]["_hashed"], v2ray.real_delay_test)
        self.thread.result_sig.connect(lambda row, result: self.set_cell(row, col, result))
        self.thread.start()

    def set_cell(self, row, col, val):
        self.setItem(row, col, QTableWidgetItem(val))
        self.table_contents.iloc[row, col] = val

    def set_row(self, row, config: pd.Series):
        for i, column in enumerate(self.COLUMNS):
            if not pd.isna(config[column]):
                self.setItem(row, i, QTableWidgetItem(str(config[column])))

    def refresh(self):
        self.setRowCount(0)
        for i, config in self.table_contents.iterrows():
            self.insertRow(i)
            self.set_row(i, config)

    def add_configs(self, configs: pd.DataFrame):
        self.table_contents = pd.concat([self.table_contents, configs])
        self.refresh()
        self.save()

    def load(self):
        if os.path.exists("./table.csv"):
            self.table_contents = pd.read_csv("./table.csv")

    def save(self):
        self.table_contents.to_csv("./table.csv", index=False)

    def drop_dupe(self):
        self.table_contents.drop_duplicates(subset=["_hashed"], inplace=True)
        self.refresh()
        self.save()

    def highlight_row(self, item):
        row = item.row()
        self.setRangeSelected(QTableWidgetSelectionRange(row, 0, row, self.columnCount() - 1), True)

    def get_selected_rows(self):
        selected_ranges = self.selectedRanges()
        selected_rows = []
        for selected_range in selected_ranges:
            for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
                if row not in selected_rows:
                    selected_rows.append(row)
        return selected_rows

    def refresh_subscription(self, group, row, servers_configs):
        # remove the old servers
        # row = 0 is reserved for manual imports, so row is added by 1
        self.table_contents = self.table_contents[self.table_contents["_sub_id"] != (row + 1)]
        self.table_contents = pd.concat([self.table_contents, servers_configs])
        self.refresh()


class Main(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('Somso2Ray')
        self.servers_configs = []

        main_layout = QVBoxLayout()

        add_sub_bttn = QPushButton('Manage Subscriptions')
        add_sub_bttn.clicked.connect(self.show_add_subscription_dialog)

        add_connection_bttn = QPushButton('Add Connection')
        add_connection_bttn.clicked.connect(self.show_add_connection_dialog)

        open_preferences_bttn = QPushButton('Preferences')
        open_preferences_bttn.clicked.connect(self.show_preferences_dialog)

        self.servers_tablewid = ServersTableWidget()
        main_layout.setStretchFactor(self.servers_tablewid, 1)

        drop_dupe_bttn = QPushButton('Drop Duplicate servers')
        drop_dupe_bttn.clicked.connect(self.servers_tablewid.drop_dupe)

        buttons_laytout = QHBoxLayout()
        buttons_laytout.addWidget(add_sub_bttn)
        buttons_laytout.addWidget(add_connection_bttn)
        buttons_laytout.addWidget(drop_dupe_bttn)
        buttons_laytout.addWidget(open_preferences_bttn)

        main_layout.addLayout(buttons_laytout)
        main_layout.addWidget(self.servers_tablewid)

        self.setLayout(main_layout)

        self.show()

    def show_preferences_dialog(self):
        dialog = PreferencesDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            # Save settings
            pass

    def show_add_connection_dialog(self):
        dialog = v2ray.AddConnectionsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            input_value = dialog.input.toPlainText().strip()
            servers_configs = v2ray.decode_multiple_configs(input_value.split("\n"))
            servers_configs["Group"] = "Imported"
            servers_configs["_sub_id"] = 0
            self.servers_tablewid.add_configs(servers_configs)
            print(f"Added {len(servers_configs)} servers.")

    def show_add_subscription_dialog(self):
        dialog = SubscriptionManager(self)
        dialog.subscription_updated_sig.connect(self.servers_tablewid.refresh_subscription)
        dialog.exec_()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = Main()
    sys.exit(app.exec_())

