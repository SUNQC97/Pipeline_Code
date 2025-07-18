from opcua import Client ,ua
from dotenv import load_dotenv
import os
import json

def start_opc_client():
    
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path)

    host = os.getenv("OPC_CLIENT_HOST", "localhost")
    port = os.getenv("OPC_CLIENT_PORT", 4840)
    url = f"opc.tcp://{host}:{port}"

    try:
        client = Client(url)
        client.connect()
        print("OPC UA Client connected")
        return client
    except Exception as e:
        print(f"Error connecting to OPC UA Client: {e}")
        return None
    

def stop_opc_client(client):
    if client:
        try:
            client.disconnect()
            print("OPC UA Client disconnected")
        except Exception as e:
            print(f"Error disconnecting OPC UA Client: {e}")
    else:
        print("No client instance to disconnect.")
    
    return client

def read_and_write_variable(client, node_id, value):
    if not client:
        print("Client is not connected.")
        return None
    
    try:
        node = client.get_node(node_id)
        current_value = node.get_value()
        print(f"Current value of {node_id}: {current_value}")
        
        # Write new value
        node.set_value(ua.Variant(value, ua.VariantType.String))
        print(f"New value set for {node_id}: {value}")
        
        return current_value
    except Exception as e:
        print(f"Error reading or writing variable: {e}")
        return None
    

def fetch_trafo_lines_from_client(client, node_path=["0:Objects", "2:Config", "2:TrafoConfigJSON"]):
    try:
        root = client.get_root_node()
        json_node = root.get_child(node_path)
        json_str = json_node.get_value()

        data = json.loads(json_str)
        param_names = data["param_names"]
        param_values = data["param_values"]

        return [
            f"{name}{' ' * (50 - len(name))}{value}"
            for name, value in zip(param_names, param_values)
        ]
    except Exception as e:
        print(f"OPC UA read error: {e}")
        return []
