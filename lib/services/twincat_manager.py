# lib/services/twincat_manager.py
import os
import re
import json
from pathlib import Path
from lib.screens import state
from lib.screens.state import kanal_inputs
from lib.services.TwinCAT_interface import (
    init_project, export_cnc_node, import_cnc_node, handle_configuration,
    load_config, collect_paths, get_export_path, get_import_path,
    add_child_node, write_trafo_lines_to_twincat, write_axis_param_to_twincat,
    write_all_trafo_to_twincat, write_all_axis_param_to_twincat
)
from lib.services.client import (
    connect_opcua_client, disconnect_opcua_client,
    convert_trafo_lines, fetch_trafo_json, fetch_axis_json,
    read_all_kanal_configs
)


class TwinCATManager:
    def __init__(self, log_callback):
        self.state = state
        self.log = log_callback
        self.sysman = self.state.sysman
        self.axis_mapping = self._load_mapping()
        self.config = load_config()
        self.opc_client = None
        self.available_paths = []

    def _log(self, text: str):
        if self.log:
            self.log(text)

    def _load_mapping(self):
        current_dir = Path(__file__).parent
        mapping_path = current_dir.parent.parent / "lib" / "config" / "Kanal_Axis_mapping.json"
        with open(mapping_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def init_sysman(self, project_path, ams_id):
        if self.state.sysman is None:
            self._log("Initializing TwinCAT project...")
            self.state.sysman = init_project(project_path, ams_id)
            self.sysman = self.state.sysman
            if self.sysman:
                self._log("TwinCAT project initialized.")
                return True
            else:
                self._log("Failed to initialize TwinCAT project.")
                return False
        else:
            self._log("TwinCAT project already initialized.")
            return True

    def export_node(self, cnc_path, export_path):
        if not self.sysman:
            self._log("Please initialize the project first.")
            return
        export_cnc_node(self.sysman, cnc_path, export_path)
        self._log(f"Exported to {export_path}")

    def import_node(self, cnc_path, import_path):
        if not self.sysman:
            self._log("Please initialize the project first.")
            return
        import_cnc_node(self.sysman, cnc_path, import_path)
        self._log(f"Imported from {import_path}")

    def activate_config(self):
        if not self.sysman:
            self._log("Please initialize the project first.")
            return
        handle_configuration(self.sysman)
        self._log("Configuration activated.")

    def browse_structure(self, keyword):
        if not self.sysman:
            self._log("Please initialize the project first.")
            return []
        root_node = self.sysman.LookupTreeItem(keyword)
        self.available_paths = collect_paths(root_node, prefix=keyword)
        self._log(f"Found {len(self.available_paths)} nodes.")
        return self.available_paths

    def connect_opcua(self):
        if self.opc_client:
            self._log("OPC Client already connected.")
            return self.opc_client
        self.opc_client = connect_opcua_client()
        if self.opc_client:
            self._log("OPC Client connected successfully.")
        else:
            self._log("Failed to connect OPC Client.")
        return self.opc_client

    def disconnect_opcua(self):
        if self.opc_client:
            disconnect_opcua_client(self.opc_client)
            self._log("OPC Client disconnected.")
            self.opc_client = None

    def write_trafo_for_kanal(self, kanal):
        if not self.sysman:
            self._log("Initialize TwinCAT project first.")
            return
        if not self.opc_client:
            self._log("Connect to OPC UA Client first.")
            return
        data = fetch_trafo_json(self.opc_client, kanal)
        trafo_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))
        write_trafo_lines_to_twincat(self.sysman, kanal, trafo_lines)
        self._log(f"Trafo parameters for {kanal} applied.")

    def write_all_kanals(self):
        if not self.sysman:
            self._log("Initialize TwinCAT project first.")
            return
        if not self.opc_client:
            self._log("Connect to OPC UA Client first.")
            return
        kanal_paths = [p for p in self.available_paths if p.split("^")[-1].lower().startswith(("kanal", "channel"))]
        configs = read_all_kanal_configs(self.opc_client, kanal_inputs)
        for path in kanal_paths:
            try:
                write_all_trafo_to_twincat(self.sysman, path, configs)
                self._log(f"Wrote to {path}")
            except Exception as e:
                self._log(f"Failed to write {path}: {e}")

    def write_axis_with_mapping(self, kanal):
        if kanal not in self.axis_mapping:
            self._log(f"Kanal '{kanal}' not found in mapping.")
            return
        data = fetch_axis_json(self.opc_client)
        axis_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))
        kanal_mapping = self.axis_mapping[kanal]
        axis_names = [k for k in kanal_mapping if re.match(r'^(Axis_|Achse_|Ext_)\d+', k)]
        for axis_name in sorted(axis_names):
            twincat_axis = kanal_mapping.get(axis_name)
            if not twincat_axis:
                self._log(f"[Mapping Missing] {axis_name}")
                continue
            path = next((p for p in self.available_paths if p.endswith(f"^{twincat_axis}")), None)
            if not path:
                self._log(f"[Path Missing] {twincat_axis}")
                continue
            single_lines = [line for line in axis_lines if line.startswith(f"{axis_name}.")]
            if not single_lines:
                self._log(f"[No Params] {axis_name}")
                continue
            write_axis_param_to_twincat(self.sysman, path, single_lines)
            self._log(f"{axis_name} written to {path}")

    def write_axis_with_matching(self):
        axis_paths = [p for p in self.available_paths if p.count("^") == 3 and p.split("^")[-1].lower().startswith(("axis_", "achse_", "ext_"))]
        configs = read_all_kanal_configs(self.opc_client, kanal_inputs)
        for path in axis_paths:
            try:
                result = write_all_axis_param_to_twincat(self.sysman, path, configs)
                if result:
                    self._log(f"[OK] {path}")
                else:
                    self._log(f"[Fail] {path}")
            except Exception as e:
                self._log(f"[Error] {e} at {path}")
                
    def apply_one_axis_to_path(self, target_path):
        from lib.services.client import fetch_axis_json, convert_trafo_lines
        from lib.services.TwinCAT_interface import write_axis_param_to_twincat

        if not self.sysman or not self.opc_client:
            self._log("Please initialize project and connect OPC UA first.")
            return

        data = fetch_axis_json(self.opc_client)
        axis_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))
        write_axis_param_to_twincat(self.sysman, target_path, axis_lines)
        self._log("Single axis written.")


    def browse_structure_and_return_paths(self, keyword):
        if not self.sysman:
            self._log("Please initialize the project first.")
            return []
        return self.browse_structure(keyword)


    def handle_upload_file(self, file_obj, save_dir):
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, file_obj.name)
        with open(file_path, "wb") as f:
            f.write(file_obj.content.read())
        self._log(f"Uploaded and saved: {file_path}")
        return file_path
