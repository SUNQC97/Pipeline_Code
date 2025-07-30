# lib/services/TwinCAT_interface.py
import os
import time
import pythoncom
import win32com.client as com
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from lib.utils.xml_read_write import (
    update_node_with_xml,
    axis_param_change_with_mapping, 
    axis_param_change_with_matching,
    read_trafo_lines_from_xml,
    clean_and_insert_trafo_lines
)
from lib.services.client import convert_trafo_lines, convert_axis_lines, fetch_axis_json, fetch_trafo_json, read_all_kanal_configs


def load_config():
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path)

    return {
        "TWINCAT_PROJECT_PATH": os.getenv("TWINCAT_PROJECT_PATH", ""),
        "AMS_NET_ID": os.getenv("AMS_NET_ID", ""),
        "EXPORT_BASE_DIR": os.getenv("EXPORT_BASE_DIR", r"C:\Temp\Export"),
        "IMPORT_BASE_DIR": os.getenv("IMPORT_BASE_DIR", r"C:\Temp\Import"),
    }

def init_project(vs_path, ams_net_id):
    try:
        pythoncom.CoInitialize()

        if not os.path.isfile(vs_path):
            print("VS Solution file not found!")
            return None

        dte = com.GetActiveObject("TcXaeShell.DTE.15.0")
        dte.SuppressUI = True   

        solution = dte.Solution
        time.sleep(2)

        if solution.Projects.Count == 0:
            print("No projects loaded from solution.")
            return None

        project = solution.Projects.Item(1)
        sysman = project.Object

        sysman.SetTargetNetId(ams_net_id)
        print(f"AMS Net ID set: {sysman.GetTargetNetId()}")
        return sysman

    except Exception as e:
        print(f"Initialization failed: {e}")
        return None

def export_cnc_node(sysman, kanal_node_path, export_path):
    try:
        node = sysman.LookupTreeItem(kanal_node_path)
        if not node:
            print(f"Node not found: {kanal_node_path}")
            return False
        xml = node.ProduceXml(True)
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"Exported to: {export_path}")
        return True
    except Exception as e:
        print(f"Export failed: {e}")
        return False

def import_cnc_node(sysman, kanal_node_path, import_path):
    try:
        node = sysman.LookupTreeItem(kanal_node_path)
        if not node:
            print(f"Node not found: {kanal_node_path}")
            return False
        if not os.path.isfile(import_path):
            print(f"Import file not found: {import_path}")
            return False
        with open(import_path, "r", encoding="utf-8") as f:
            xml = f.read()
        node.ConsumeXml(xml)
        print(f"Imported from: {import_path}")
        return True
    except Exception as e:
        print(f"Import failed: {e}")
        return False

def handle_configuration(sysman):
    try:
        sysman.ActivateConfiguration()
        time.sleep(2)
        sysman.StartRestartTwinCAT()
        print("Configuration activated and TwinCAT restarted")
        return True
    except Exception as e:
        print(f"Restart failed: {e}")
        return False

def browse_tree(node, indent=""):
    try:
        print(indent + node.Name)
        for child in node:  # COM enumerator iteration
            browse_tree(child, indent + "  ")
    except Exception as e:
        print(indent + f"[Error accessing children: {e}]")

def collect_paths(node, prefix="", current_path="", result=None, skip_root=True):
    if result is None:
        result = []
    try:
        if skip_root:
            for child in node:
                collect_paths(child, prefix=prefix, current_path=prefix, result=result, skip_root=False)
        else:
            full_path = current_path + "^" + node.Name if current_path else node.Name
            result.append(full_path)
            for child in node:
                collect_paths(child, current_path=full_path, result=result, skip_root=False)
    except Exception:
        pass
    return result

def get_export_path(base_dir, cnc_path):
    last = cnc_path.split("^")[-1] if cnc_path else "default"
    return f"{base_dir}\\{last}.xml"

def get_import_path(base_dir, cnc_path):
    last = cnc_path.split("^")[-1] if cnc_path else "default"
    return f"{base_dir}\\{last}.xml"

def add_child_node(sysman, parent_path, new_name, subtype):
    try:
        parent_node = sysman.LookupTreeItem(parent_path)
        if not parent_node:
            print(f"Parent node not found: {parent_path}")
            return False

        # Create a new child node under the parent node
        pipItem = parent_node.CreateChild(new_name, subtype, "", None)
        print(f"Child node '{new_name}' with subtype '{subtype}' added under '{parent_path}'")
        return True
    except Exception as e:
        print(f"Failed to add child node: {e}")
        return False
       
def write_trafo_lines_to_twincat(sysman, node_path: str, trafo_lines: list):
    if not sysman:
        print("TwinCAT sysman is not initialized.")
        return False
    try:
        node = sysman.LookupTreeItem(node_path)
        xml_data = node.ProduceXml(True)
        modified_xml = clean_and_insert_trafo_lines(xml_data, trafo_lines)
        update_node_with_xml(node, modified_xml)
        print("TwinCAT node updated successfully.")
        return True
    except Exception as e:
        print(f"Error during TwinCAT update: {e}")
        return False

def write_all_trafo_to_twincat(sysman, node_path: str, all_configs: list):
    if not sysman:
        print("TwinCAT sysman is not initialized.")
        return False
    try:
        node = sysman.LookupTreeItem(node_path)
        xml_data = node.ProduceXml(True)

        root = ET.fromstring(xml_data)

        item_type = root.findtext("ItemType")
        item_id = root.findtext("ItemId")
        print(f"Parsed ItemType = {item_type}, ItemId = {item_id}")

        if item_type != "401":
            print(f"Node {node_path} is not a valid Kanal node.")
            return False

        kanal_name = f"Kanal_{int(item_id)}"
        trafo_config = all_configs.get(kanal_name, {}).get("trafo", {})
        if not trafo_config:
            print(f"No trafo configuration found for {kanal_name}.")
            return False

        
        param_names = trafo_config.get("param_names", [])
        param_values = [str(v) for v in trafo_config.get("param_values", [])]
        if not param_names or not param_values:
            print(f"No valid trafo parameters found for {kanal_name}.")
            return False
        
        scaled_param_values = scale_trafo_values(param_names, param_values)
        trafo_lines = convert_trafo_lines(param_names, scaled_param_values)

        # Clean and insert the new trafo lines into the XML
        modified_xml = clean_and_insert_trafo_lines(xml_data, trafo_lines)
        update_node_with_xml(node, modified_xml)

        print(f"TwinCAT node Kanal {kanal_name} updated successfully.")

    except Exception as e:
        print(f"Error during TwinCAT update: {e}")
        return False

def read_all_trafo_from_twincat(sysman, node_path: str, all_configs: dict) -> dict | None:
    if not sysman:
        print("TwinCAT sysman is not initialized.")
        return None
    try:
        node = sysman.LookupTreeItem(node_path)
        xml_data = node.ProduceXml(True)

        root = ET.fromstring(xml_data)
        item_type = root.findtext("ItemType")
        item_id = root.findtext("ItemId")

        print(f"Parsed ItemType = {item_type}, ItemId = {item_id}")
        if item_type != "401":
            print(f"Node {node_path} is not a valid Kanal node.")
            return None

        kanal_name = f"Kanal_{int(item_id)}"
        param_names, param_values = read_trafo_lines_from_xml(xml_data)

        all_configs[kanal_name] = {
            "trafo": {
                "param_names": param_names,
                "param_values": param_values
            }
        }

        print(f"[OK] TwinCAT node {kanal_name} read and updated into all_configs.")
        return all_configs

    except Exception as e:
        print(f"[Error] Failed to read TwinCAT node: {e}")
        return None


def write_axis_param_to_twincat(sysman, node_path: str, axis_lines: list):
    if not sysman:
        print("TwinCAT sysman is not initialized.")
        return False
    try:
        node = sysman.LookupTreeItem(node_path)
        xml_data = node.ProduceXml(True)
        modified_xml = axis_param_change_with_mapping(xml_data, axis_lines)
        update_node_with_xml(node, modified_xml)
        print("TwinCAT node updated successfully.")
        return True
    except Exception as e:
        print(f"Error during TwinCAT update: {e}")
        return False

def write_all_axis_param_to_twincat(sysman, node_path: str, all_configs: list):
    if not sysman:
        print("TwinCAT sysman is not initialized.")
        return False
    try:
        node = sysman.LookupTreeItem(node_path)
        xml_data = node.ProduceXml(True)

        root = ET.fromstring(xml_data)

        item_type = root.findtext("ItemType")
        axis_name_twincat = root.findtext("ItemName")
        axis_def = root.find("IsgAxisDef")

        if axis_def is None:
            print(f"[ERROR] No IsgAxisDef block in XML for {node_path}")
            return False
        
        DefaultChannel = axis_def.findtext("DefaultChannel") 
        DefaultIndex = axis_def.findtext("DefaultIndex")
        index = int(DefaultIndex)

        if item_type != "403":
            print(f"Node {node_path} is not a valid Axis node.")
            return False
        if not axis_name_twincat or not DefaultChannel or not DefaultIndex:
            print(f"Node {node_path} is missing required Axis parameters.")
            return False
        
        kanal_name = f"Kanal_{DefaultChannel}"

        axis_config = all_configs.get(kanal_name, {}).get("axis", {})
        if not axis_config:
            print(f"No axis configuration found for {kanal_name}.")
            return False

        param_names = axis_config.get("param_names", [])
        param_values = [str(v) for v in axis_config.get("param_values", [])]

        prefixes = [f"Axis_{index+1}", f"Achse_{index+1}", f"Ext_{index+1}"]

        filtered_names = []
        filtered_values = []

        for name, value in zip(param_names, param_values):
            if any(name.startswith(f"{p}.") for p in prefixes):
                filtered_names.append(name)
                filtered_values.append(value)

        if not filtered_names or not filtered_values:
            print(f"No valid axis parameters found for {kanal_name}.")
            return False

        axis_lines = convert_axis_lines(filtered_names, filtered_values)

        # Clean and update the XML with the new axis parameters
        modified_xml = axis_param_change_with_matching(xml_data, axis_lines)
        update_node_with_xml(node, modified_xml)        
        
        print(f"Axis '{axis_name_twincat}' in Kanal '{kanal_name}' updated successfully.")

        return True

    except Exception as e:
        print(f"Error during TwinCAT update: {e}")
        return False

def scale_trafo_values(param_names: list, param_values: list, factor: int = 10000) -> list:
    """
    对所有 param[...] 项进行缩放，id 保持原值。
    """
    scaled_values = []
    for name, value in zip(param_names, param_values):
        try:
            if "param[" in name:
                scaled = str(int(float(value) * factor))
            else:
                scaled = str(value)
        except ValueError:
            scaled = str(value)  # fallback fallback fallback
        scaled_values.append(scaled)
    return scaled_values

    