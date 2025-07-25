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

def fetch_trafo_json(client: Client) -> dict:
    try:
        root = client.get_root_node()
        json_node = root.get_child(["0:Objects", "2:Config", "2:TrafoConfigJSON"])
        json_str = json_node.get_value()
        return json.loads(json_str)
    except Exception as e:
        print(f"Failed to fetch TrafoConfigJSON: {e}")
        return {}

def convert_trafo_lines(param_names: list, param_values: list) -> list:
    trafo_lines = []
    for name, value in zip(param_names, param_values):
        spaces = " " * max(0, 50 - len(name))
        trafo_lines.append(f"{name}{spaces}{value}")
    return trafo_lines


def fetch_axis_json(client: Client) -> dict:
    try:
        root = client.get_root_node()
        json_node = root.get_child(["0:Objects", "2:Config", "2:AxisConfigJSON"])
        json_str = json_node.get_value()
        return json.loads(json_str)
    except Exception as e:
        print(f"Failed to fetch TrafoConfigJSON: {e}")
        return {}
    
def convert_axis_lines(param_names: list, param_values: list) -> list:
    axis_lines = []
    for name, value in zip(param_names, param_values):
        spaces = " " * max(0, 50 - len(name))
        axis_lines.append(f"{name}{spaces}{value}")
    return axis_lines

