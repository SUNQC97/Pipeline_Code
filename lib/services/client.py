import os
import json
from opcua import Client
from lib.utils.save_to_file import save_structure_to_file


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

def write_all_configs_to_opcua(client: Client, all_configs: dict):

    try:
        root = client.get_root_node()
        
        for kanal_name, config in all_configs.items():
            for param_type in ["trafo", "axis"]:
                config_data = config.get(param_type)
                if not config_data or not config_data.get("param_names"):
                    print(f"[Skip] No valid {param_type} data in {kanal_name}")
                    continue

                try:
                    node = root.get_child([
                        "0:Objects",
                        f"2:{kanal_name}",
                        f"2:{param_type.capitalize()}ConfigJSON"
                    ])
                    json_str = json.dumps(config_data, indent=2)
                    node.set_value(json_str)
                    print(f"[OK] Updated {kanal_name} → {param_type.capitalize()}ConfigJSON")
                except Exception as e:
                    print(f"[Error] Failed to write {param_type} to {kanal_name}: {e}")

    except Exception as e:
        print(f"[Fatal Error] Cannot access OPC UA structure: {e}")

def build_kanal_axis_structure(client: Client) -> dict:
    """
    Build a structured dict for kanal axis parameters:
    {
        "Kanal_1": ["Axis_1", "Axis_2", ...],
        "Kanal_2": ["Ext_1", "Ext_2", ...]
    }
    """
    kanal_axis_structure = {}
    try:
        root = client.get_root_node()
        objects_node = root.get_child(["0:Objects"])
        kanal_nodes = [
            node for node in objects_node.get_children()
            if "Kanal" in node.get_browse_name().Name
        ]

        for kanal_node in kanal_nodes:
            kanal_name = kanal_node.get_browse_name().Name

            try:
                # get AxisConfigJSON
                axis_config_node = kanal_node.get_child(["2:AxisConfigJSON"])
                axis_config_str = axis_config_node.get_value()
                axis_config = json.loads(axis_config_str)

                axis_names = []
                for name in axis_config.get("param_names", []):
                    if name.startswith(("Axis_", "Ext_", "Achse_")):
                        prefix = name.split(".")[0]
                        if prefix not in axis_names:
                            axis_names.append(prefix)

                kanal_axis_structure[kanal_name] = axis_names

            except Exception as e:
                print(f"[Error] Failed to read AxisConfigJSON for {kanal_name}: {e}")
                kanal_axis_structure[kanal_name] = []

        
    except Exception as e:
        print(f"[Error] Failed to build kanal axis structure: {e}")

    # Save the structure to a file
    save_structure_to_file(kanal_axis_structure, "kanal_axis_structure.json")        

    return kanal_axis_structure

def read_audit_info(client: Client) -> dict:
    """
    从 OPC UA 服务器读取审计信息
    """
    try:
        if not client:
            return None
            
        # 读取审计节点信息
        root = client.get_root_node()
        audit_node = root.get_child(["0:Objects", "2:AuditTrail"])
        
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
        print(f"[DEBUG] Could not read audit info: {e}")
        return None

def check_audit_node_exists(client: Client) -> bool:
    """
    检查审计节点是否存在
    """
    try:
        root = client.get_root_node()
        audit_node = root.get_child(["0:Objects", "2:AuditTrail"])
        return True
    except Exception as e:
        print(f"[INFO] Audit trail node not found: {e}")
        return False

def format_audit_source(base_source: str, audit_info: dict) -> str:
    """
    格式化审计信息为可显示的 source 字符串
    """
    if not audit_info or not audit_info.get('modifier') or audit_info.get('modifier') == 'Unknown':
        return f"{base_source} | Modifier: Unknown"
    
    modifier = audit_info.get('modifier', 'Unknown')
    modified_time = audit_info.get('modified_time', '')
    operation = audit_info.get('operation', '')
    modified_node = audit_info.get('modified_node', '')
    
    source = f"{base_source} | Modified by: {modifier}"
    
    # 格式化时间显示
    if modified_time:
        try:
            from datetime import datetime
            # 尝试解析 ISO 格式时间
            dt = datetime.fromisoformat(modified_time.replace('Z', '+00:00'))
            source += f" at {dt.strftime('%H:%M:%S')}"
        except:
            # 如果解析失败，显示原始时间的前19个字符
            source += f" at {modified_time[:19]}"
    
    # 添加修改的节点信息
    if modified_node and not modified_node.startswith('Server_'):
        source += f" | Node: {modified_node}"
    
    # 添加操作类型（如果不是默认的参数更新）
    if operation and operation not in ["Parameter_Update", "Update_TrafoConfigJSON", "Update_AxisConfigJSON"]:
        source += f" | Op: {operation}"
    
    return source

def get_audit_subscription_nodes(client: Client) -> list:
    """
    获取需要订阅的审计节点列表
    """
    audit_nodes = []
    try:
        root = client.get_root_node()
        audit_node = root.get_child(["0:Objects", "2:AuditTrail"])
        
        # 订阅修改者信息变更
        modifier_node = audit_node.get_child("2:LastModifier")
        audit_nodes.append(("AuditTrail/LastModifier", modifier_node))
        
        # 也可以订阅其他审计信息
        # time_node = audit_node.get_child("2:LastModifiedTime")
        # audit_nodes.append(("AuditTrail/LastModifiedTime", time_node))
        
    except Exception as e:
        print(f"[WARN] Could not get audit subscription nodes: {e}")
    
    return audit_nodes