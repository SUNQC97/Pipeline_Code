import os
import json
from opcua import Client

def connect_opcua_client() -> Client:
    OPCUA_URL = f"opc.tcp://{os.getenv('SERVER_IP')}:{os.getenv('SERVER_PORT')}"
    client = Client(OPCUA_URL)
    client.connect()
    print(f"Connected to OPC UA Server at {OPCUA_URL}")
    return client

def disconnect_opcua_client(client: Client):
    if client:
        try:
            client.disconnect()
            print("Disconnected from OPC UA Server")
        except Exception as e:
            print(f"Error disconnecting OPC UA client: {e}")

def fetch_kanal_config_json(client: Client, kanal_name: str, param_type: str) -> dict:
    try:
        root = client.get_root_node()
        json_node = root.get_child(["0:Objects", f"2:{kanal_name}", f"2:{param_type}"])
        json_str = json_node.get_value()
        return json.loads(json_str)
    except Exception as e:
        print(f"Failed to fetch {param_type} for {kanal_name}: {e}")
        return {}

def fetch_trafo_json(client: Client, kanal_name: str) -> dict:
    return fetch_kanal_config_json(client, kanal_name, "TrafoConfigJSON")

def fetch_axis_json(client: Client, kanal_name: str) -> dict:
    return fetch_kanal_config_json(client, kanal_name, "AxisConfigJSON")

def convert_trafo_lines(param_names: list, param_values: list) -> list:
    return [f"{name}{' ' * max(0, 50 - len(name))}{value}" for name, value in zip(param_names, param_values)]

def convert_axis_lines(param_names: list, param_values: list) -> list:
    return [f"{name}{' ' * max(0, 50 - len(name))}{value}" for name, value in zip(param_names, param_values)]

def read_all_kanal_configs(client: Client, kanal_names: list[str]) -> dict:
    """
    Read all kanal configs (Trafo and Axis) into a structured dict.
    """
    all_configs = {}
    for kanal in kanal_names:
        trafo_data = fetch_trafo_json(client, kanal)
        axis_data = fetch_axis_json(client, kanal)
        all_configs[kanal] = {
            "trafo": trafo_data,
            "axis": axis_data
        }
    return all_configs
