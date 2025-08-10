from opcua import Server, ua
from dotenv import load_dotenv
import os
import json
from datetime import datetime

def create_opc_server(kanal_names):
    """
    Create and configure OPC UA server with multiple Kanal/Channel nodes.
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

    objects = server.get_objects_node()
    kanal_nodes = {}

    for kanal in kanal_names:
        kanal_node = objects.add_object(idx, kanal)
        kanal_nodes[kanal] = kanal_node

    audit_node = create_audit_trail_node(objects, idx)
    print(f"[OK] OPC UA Server created at {url}")
    
    return server, kanal_nodes, idx

def add_kanal_config(kanal_node, idx, trafo_names, trafo_values, axis_names, axis_values):
    """
    Add Trafo and Axis config variables to a specific Kanal/Channel node.
    """
    if trafo_names and trafo_values:
        trafo_data = json.dumps({"param_names": trafo_names, "param_values": trafo_values})
        trafo_var = kanal_node.add_variable(idx, "TrafoConfigJSON", trafo_data, ua.VariantType.String)
        trafo_var.set_writable()
    if axis_names and axis_values:
        axis_data = json.dumps({"param_names": axis_names, "param_values": axis_values})
        axis_var = kanal_node.add_variable(idx, "AxisConfigJSON", axis_data, ua.VariantType.String)
        axis_var.set_writable()

def start_opc_server_multi_kanal(kanal_data_dict):
    """
    Start the OPC UA server and configure multiple Kanal nodes with their configs.
    """
    kanal_names = list(kanal_data_dict.keys())
    server, kanal_nodes, idx = create_opc_server(kanal_names)

    for kanal, node in kanal_nodes.items():
        data = kanal_data_dict[kanal]
        add_kanal_config(
            kanal_node=node,
            idx=idx,
            trafo_names=data.get("trafo_names"),
            trafo_values=data.get("trafo_values"),
            axis_names=data.get("axis_names"),
            axis_values=data.get("axis_values"),
        )

    server.start()
    print("\n OPC UA Server started with multiple Kanals.")
    return server

def stop_opc_server(server):
    if server:
        server.stop()
        print("OPC UA Server stopped.")
    else:
        print("No server instance to stop.")
    return server

def update_kanal_axis_config(server_instance, kanal_name, param_type, param_names, param_values):
    """
    Update the JSON data for a given Kanal and config type ("TrafoConfigJSON" or "AxisConfigJSON").
    """
    config_obj = server_instance.get_objects_node().get_child([f"2:{kanal_name}"])
    json_node = config_obj.get_child(f"2:{param_type}")

    data = {
        "param_names": param_names,
        "param_values": param_values
    }

    json_str = json.dumps(data)
    json_node.set_value(json_str)
    print(f"[OK] {param_type} for {kanal_name} updated.")

def update_axis_config(server_instance, kanal_name, axis_names, axis_values):
    """
    Specifically update AxisConfigJSON for a given Kanal.
    """
    update_kanal_axis_config(server_instance, kanal_name, "AxisConfigJSON", axis_names, axis_values)
    print(f"[OK] AxisConfigJSON for {kanal_name} updated.")

def update_trafo_config(server_instance, kanal_name, trafo_names, trafo_values):
    """
    Specifically update TrafoConfigJSON for a given Kanal.
    """
    update_kanal_axis_config(server_instance, kanal_name, "TrafoConfigJSON", trafo_names, trafo_values)
    print(f"[OK] TrafoConfigJSON for {kanal_name} updated.")

def read_kanal_data_from_server_instance(server_instance, kanal_name):
    """
    Read Trafo and Axis data from a specific Kanal node in the server instance.
    """
    try:
        kanal_node = server_instance.get_objects_node().get_child([f"2:{kanal_name}"])
        trafo_json = kanal_node.get_child(f"2:TrafoConfigJSON").get_value()
        axis_json = kanal_node.get_child(f"2:AxisConfigJSON").get_value()

        trafo_data = json.loads(trafo_json)
        axis_data = json.loads(axis_json)

        return {
            "trafo_names": trafo_data.get("param_names", []),
            "trafo_values": trafo_data.get("param_values", []),
            "axis_names": axis_data.get("param_names", []),
            "axis_values": axis_data.get("param_values", []),
        }

    except Exception as e:
        print(f"[ERROR] Failed to read kanal '{kanal_name}': {e}")
        return {
            "trafo_names": [],
            "trafo_values": [],
            "axis_names": [],
            "axis_values": [],
        }

def read_all_kanal_data_from_server_instance(server_instance):
    
    result = {}
    kanal_nodes = server_instance.get_objects_node().get_children()

    for kanal_node in kanal_nodes:
        kanal_name = kanal_node.get_browse_name().Name
        try:
            kanal_node_obj = server_instance.get_objects_node().get_child([f"2:{kanal_name}"])
            trafo_raw = kanal_node_obj.get_child(f"2:TrafoConfigJSON").get_value()
            axis_raw = kanal_node_obj.get_child(f"2:AxisConfigJSON").get_value()

            result[kanal_name] = {
                "TrafoConfigJSON": trafo_raw,
                "AxisConfigJSON": axis_raw
            }

        except Exception as e:
            print(f"[ERROR] Failed to read {kanal_name}: {e}")
            continue

    return result

def create_audit_trail_node(objects, idx):
    """
    Create an audit trail node for tracking changes.
    """
    try:
        audit_node = objects.add_object(idx, "AuditTrail")


        # add variables 
        last_modifier_var = audit_node.add_variable(idx, "LastModifier", "Unknown", ua.VariantType.String)
        last_modified_time_var = audit_node.add_variable(idx, "LastModifiedTime", "", ua.VariantType.String)
        last_modified_node_var = audit_node.add_variable(idx, "LastModifiedNode", "", ua.VariantType.String)
        last_operation_var = audit_node.add_variable(idx, "LastOperation", "", ua.VariantType.String)
        session_id_var = audit_node.add_variable(idx, "SessionID", "", ua.VariantType.String)

        # set writable
        last_modifier_var.set_writable()
        last_modified_time_var.set_writable()
        last_modified_node_var.set_writable()
        last_operation_var.set_writable()
        session_id_var.set_writable()
        

        print(f"[OK] Audit trail node created successfully.")
        return audit_node
    except Exception as e:
        print(f"[ERROR] Failed to create audit trail node: {e}")
        return None

def update_audit_info(server_instance, modifier_name, modified_node="", operation="Parameter_Update", session_id=""):
    """
    更新审计信息到 OPC UA 审计节点
    """
    try:
        # 获取审计节点
        audit_node = server_instance.get_objects_node().get_child("2:AuditTrail")
        
        # 更新审计信息
        audit_node.get_child("2:LastModifier").set_value(modifier_name)
        audit_node.get_child("2:LastModifiedTime").set_value(datetime.now().isoformat())
        audit_node.get_child("2:LastModifiedNode").set_value(modified_node)
        audit_node.get_child("2:LastOperation").set_value(operation)
        audit_node.get_child("2:SessionID").set_value(session_id)
        
        print(f"[AUDIT] Updated: modifier={modifier_name}, node={modified_node}, operation={operation}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to update audit info: {e}")
        return False
    
def read_audit_info(server_instance):
    """
    从 OPC UA 服务器读取审计信息
    """
    try:
        audit_node = server_instance.get_objects_node().get_child("2:AuditTrail")
        
        modifier = audit_node.get_child("2:LastModifier").get_value()
        modified_time = audit_node.get_child("2:LastModifiedTime").get_value()
        modified_node = audit_node.get_child("2:LastModifiedNode").get_value()
        operation = audit_node.get_child("2:LastOperation").get_value()
        session_id = audit_node.get_child("2:SessionID").get_value()
        
        return {
            'modifier': modifier,
            'modified_time': modified_time,
            'modified_node': modified_node,
            'operation': operation,
            'session_id': session_id
        }
        
    except Exception as e:
        print(f"[ERROR] Could not read audit info: {e}")
        return None


