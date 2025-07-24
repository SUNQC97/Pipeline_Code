# lib/services/TwinCAT_interface.py
import os
import time
import pythoncom
import win32com.client as com
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from lib.utils.xml_write import clean_and_insert_trafo_lines, update_node_with_xml, axis_param_change



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


def write_axis_param_to_twincat(sysman, node_path: str, axis_lines: list):
    if not sysman:
        print("TwinCAT sysman is not initialized.")
        return False
    try:
        node = sysman.LookupTreeItem(node_path)
        xml_data = node.ProduceXml(True)
        modified_xml = axis_param_change(xml_data, axis_lines)
        update_node_with_xml(node, modified_xml)
        print("TwinCAT node updated successfully.")
        return True
    except Exception as e:
        print(f"Error during TwinCAT update: {e}")
        return False

