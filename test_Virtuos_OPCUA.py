import os
import json
import xml.etree.ElementTree as ET
from opcua import Client
from lib.services.TwinCAT_interface import (
    init_project,
    export_cnc_node,
    load_config,

)
from lib.utils.xml_trafo import (
    clean_and_insert_trafo_lines,
    update_node_with_xml,
    export_node_to_file
)
# === Connect to OPC UA and read JSON string ===
opcua_client = Client("opc.tcp://localhost:4840")
opcua_client.connect()


# 找到你在 Server 中注册的节点路径
root = opcua_client.get_root_node()
objects = root.get_child(["0:Objects", "2:Config"])  # 2 是你注册的 namespace
json_node = objects.get_child("2:TrafoConfigJSON")

# 读取 JSON 字符串并解析
json_str = json_node.get_value()
opcua_client.disconnect()

# 将 JSON 字符串转换为字典
data = json.loads(json_str)

# 提取参数名和值
param_names = data["param_names"]
param_values = data["param_values"]

# === 转换为 trafo[0].id 和 trafo[0].param[...] 格式 ===
new_trafo_lines = []

for name, value in zip(param_names, param_values):
    spaces = " " * (50 - len(name))
    new_trafo_lines.append(f"{name}{spaces}{value}")


# === Load config ===
config = load_config()
TWINCAT_PROJECT_PATH = config["TWINCAT_PROJECT_PATH"]
AMS_NET_ID = config["AMS_NET_ID"]
EXPORT_BASE_DIR = config["EXPORT_BASE_DIR"]
node_path = "TICC^CNC^Kanal_1"

# === TwinCAT 操作 ===
print(f"Opening TwinCAT project: {TWINCAT_PROJECT_PATH}")
sysman = init_project(TWINCAT_PROJECT_PATH, AMS_NET_ID)
if not sysman:
    print("无法打开 TwinCAT 工程。")
    exit(1)

node = sysman.LookupTreeItem(node_path)
xml_data = node.ProduceXml(True)

try:
    modified_xml = clean_and_insert_trafo_lines(xml_data, new_trafo_lines)
    update_node_with_xml(node, modified_xml)
    export_node_to_file(sysman, node_path, EXPORT_BASE_DIR)
except Exception as e:
    print(f"更新过程中出错: {e}")
finally:
    sysman = None
