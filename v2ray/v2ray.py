import json
import subprocess
import re
import utils
import base64
import pandas as pd
from PyQt5.Qt import QThread, pyqtSignal


class V2rayConnectionThread(QThread):
    logs_received = pyqtSignal(str)

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in iter(process.stdout.readline, b''):
            self.logs_received.emit(line.decode())
        process.stdout.close()
        process.wait()


def connect(server):
    server_protocol, server_configs = server.split("://")
    server_json = json.loads(base64.b64decode(server_configs).decode("utf-8"))
    with open("./config.json.template", "r") as f:
        v2ray_config = json.load(f)
    tlssettings = {}
    if server_json["tls"] == "tls":
        tlssettings = {
            "allowInsecure": False,
            "serverName": server_json["host"]
        }
    wsssettings = {}
    if server_json["net"] == "ws":
        wsssettings = {
            "connectionReuse": True,  # TODO:????
            "headers": {"Host": server_json["host"]},
            "path": server_json["path"].replace("\\", ""),
        }

    v2ray_config["outbounds"][0] = {
        "protocol": server_protocol,
        "settings": {
            "vnext": [{
                "address": server_json["add"],
                "port": int(server_json["port"]),
                "users": [{
                    "alterId": int(server_json["aid"]),
                    "id": server_json["id"],
                    "level":8,
                    "security":"auto"
                }],
            }]
        },
        "tag": "proxy",
        "streamSettings": {
            "network": server_json["net"],
            "security": server_json["tls"],
            "tlssettings": tlssettings,
            "wsssettings": wsssettings,
        },
        "mux": {
            "enabled": False
        }
    }
    with open("./config.json", "w") as f:
        f.write(json.dumps(v2ray_config, indent=4))
    v2ray_kill_process = subprocess.Popen(
        ["killall", "v2ray"]
    )
    v2ray_kill_process.communicate()

    v2ray_process = V2rayConnectionThread(["v2ray", "run", "-config", "config.json"])
    v2ray_process.logs_received.connect(utils.log)
    v2ray_process.start()

    return v2ray_process


def decode_config(server_config):
    if not re.match(r"^\w+\:\/\/.+$", server_config):
        return {}
    item_protocol, item_source = server_config.split("://", 1)
    if item_protocol != "vmess":
        return {}
    item_node = json.loads(base64.b64decode(item_source).decode("utf-8"))
    for key in ["ps", "add", "port"]:
        if key not in item_node.keys():
            return {}
    return {"Type": "Vmess",
            "Name": item_node["ps"],
            "IP": item_node["add"],
            "Port": item_node["port"],
            "Ping": "",
            "Real Delay": "",
            "_hashed": server_config,
            "_sub_id": 0}


def decode_multiple_configs(server_configs: list):
    decoded_servers = [decode_config(server_config)
                       for server_config in server_configs]
    return pd.DataFrame(decoded_servers).dropna()


def real_delay_test(server):
    name = decode_config(server)["Name"]
    utils.log(f"Real Delay test {name}")
    ping_process = subprocess.Popen(
        ["./vmessping_amd64_linux", "-c", "1", "-o", "10", server],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = ping_process.communicate()
    if ping_process.returncode == 0:
        time_index = stdout.decode().find("time=")
        if time_index != -1:
            time_str = stdout.decode()[time_index + 5:]
            time_ms = time_str[:time_str.find(" ")] + "ms"
            utils.log(f"Real Delay {name} result: {time_ms}")
            return time_ms
    utils.log(f"Real Delay {name} failed.")
    return "TIMEOUT"


def ping_test(ip):
    utils.log(f"Pinging {ip}")
    ping_process = subprocess.Popen(
        ["ping", "-c", "1", "-W", "10", ip],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = ping_process.communicate()
    if ping_process.returncode == 0:
        time_index = stdout.decode().find("time=")
        if time_index != -1:
            time_str = stdout.decode()[time_index + 5:]
            time_ms = time_str[:time_str.find(" ")] + "ms"
            utils.log(f"Ping {ip} result: {time_ms}")
            return time_ms
    utils.log(f"Ping {ip} failed.")
    return "TIMEOUT"
