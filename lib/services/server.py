from opcua import Server, ua
from dotenv import load_dotenv
import os
import json


def create_opc_server():
    """
    Create and configure the OPC UA Server without Trafo-specific logic.
    """
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path)

    host = os.getenv("SERVER_IP")
    port = os.getenv("SERVER_PORT")
    url = f"opc.tcp://{host}:{port}"

    server = Server()
    server.set_endpoint(url)
    server.set_server_name("TwinCAT OPC UA Server")
    idx = server.register_namespace("http://example.org/")

    # Create Config node
    objects = server.get_objects_node()
    config_obj = objects.add_object(idx, "Config")

    print(f"OPC UA Server created at {url}")
    return server, config_obj, idx


def add_trafo_config(config_obj, idx, param_names, param_values):
    """
    Add a TrafoConfigJSON variable to the Config node.
    """
    if param_names and param_values:
        data = {
            "param_names": param_names,
            "param_values": param_values
        }
        json_str = json.dumps(data)
        json_node = config_obj.add_variable(
            idx, "TrafoConfigJSON", json_str, varianttype=ua.VariantType.String
        )
        json_node.set_writable()
        print("TrafoConfigJSON written to OPC UA node.")


def add_axis_config(config_obj, idx, param_names, param_values):
    """
    Add an AxisConfigJSON variable to the Config node using param_names + param_values.
    """
    if param_names and param_values:
        data = {
            "param_names": param_names,
            "param_values": param_values
        }
        json_str = json.dumps(data)
        json_node = config_obj.add_variable(
            idx, "AxisConfigJSON", json_str, varianttype=ua.VariantType.String
        )
        json_node.set_writable()
        print("AxisConfigJSON written to OPC UA node.")


def start_opc_server_with_trafo_and_axis(trafo_names=None, trafo_values=None, axis_names=None, axis_values=None):
    server, config_obj, idx = create_opc_server()
    if trafo_names and trafo_values:
        add_trafo_config(config_obj, idx, trafo_names, trafo_values)
    if axis_names and axis_values:
        add_axis_config(config_obj, idx, axis_names, axis_values)
    server.start()
    print("OPC UA Server started.")
    return server


def stop_opc_server(server):
    if server:
        server.stop()
        print("OPC UA Server stopped.")
    else:
        print("No server instance to stop.")

    return server


def update_trafo_config(server_instance, param_names, param_values):
    config_obj = server_instance.get_objects_node().get_child(["2:Config"])
    json_node = config_obj.get_child("2:TrafoConfigJSON")

    data = {
        "param_names": param_names,
        "param_values": param_values
    }

    json_str = json.dumps(data)
    json_node.set_value(json_str)
    print("[OK] TrafoConfigJSON updated.")


def update_axis_config(server_instance, param_names, param_values):
    config_obj = server_instance.get_objects_node().get_child(["2:Config"])
    json_node = config_obj.get_child("2:AxisConfigJSON")

    data = {
        "param_names": param_names,
        "param_values": param_values
    }

    json_str = json.dumps(data)
    json_node.set_value(json_str)
    print("[OK] AxisConfigJSON updated.")

