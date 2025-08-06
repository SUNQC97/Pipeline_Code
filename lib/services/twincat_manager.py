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
    write_all_trafo_to_twincat, write_all_axis_param_to_twincat,
    read_all_trafo_from_twincat, read_all_axis_from_twincat, parse_axis_xml,
    parse_kanal_xml
)
from lib.services.client import (
    fetch_axis_json, convert_trafo_lines, write_all_configs_to_opcua,
    read_all_kanal_configs, fetch_trafo_json
)
import lib.services.client as client
import asyncio
import pythoncom
from lib.utils.save_to_file import save_structure_to_file
from lib.utils.structure_compare import compare_kanal_axis_structures


class TwinCATManager:
    def __init__(
        self,
        sysman=None,
        available_paths: list[str] = None,
        log_func: callable = None,
        opc_client=None,
        logger: callable = None
    ):
        self.log = log_func or logger or print
        self.status = {}

        self.sysman = sysman
        self.opc_client = opc_client

        self.config = load_config()
        self.project_path = self.config["TWINCAT_PROJECT_PATH"]
        self.ams_net_id = self.config["AMS_NET_ID"]
        self.export_base = self.config["EXPORT_BASE_DIR"]
        self.import_base = self.config["IMPORT_BASE_DIR"]

        self.available_paths = available_paths if available_paths is not None else []
        self.axis_mapping = self.load_axis_mapping()
        self.kanal_inputs = kanal_inputs

    def log(self, message):
        self.logger(message)

    def load_axis_mapping(self):
        mapping_path = Path(__file__).parent.parent / "config" / "Kanal_Axis_mapping.json"
        with open(mapping_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def init_project(self):
        if not self.sysman:
            self.sysman = init_project(self.project_path, self.ams_net_id)
        return self.sysman is not None

    def browse_structure(self, structure_key_or_keyword="CNC Configuration"):
        structure_map = {
            "I/O Configuration": "TIIC",
            "I/O Devices": "TIID",
            "Real-Time Configuration": "TIRC",
            "Route Settings": "TIRR",
            "Additional Tasks": "TIRT",
            "Real-Time Settings": "TIRS",
            "PLC Configuration": "TIPC",
            "NC Configuration": "TINC",
            "CNC Configuration": "TICC",
            "CAM Configuration": "TIAC",
        }

        if not self.sysman:
            raise RuntimeError("Project not initialized")

        if structure_key_or_keyword in structure_map:
            keyword = structure_map[structure_key_or_keyword]
        elif structure_key_or_keyword in structure_map.values():
            keyword = structure_key_or_keyword
        else:
            raise KeyError(f"'{structure_key_or_keyword}' is not a valid structure key or keyword")

        root_node = self.sysman.LookupTreeItem(keyword)
        self.available_paths = collect_paths(root_node, prefix=keyword)
        return self.available_paths
    
    def export_node(self, node_path: str, export_path: str):
        if not self.sysman:
            raise RuntimeError("Project not initialized")
        export_cnc_node(self.sysman, node_path, export_path)
        self.log(f"Exported {node_path} to {export_path}")

    def import_node(self, node_path: str, import_path: str):
        if not self.sysman:
            raise RuntimeError("Project not initialized")
        import_cnc_node(self.sysman, node_path, import_path)
        self.log(f"Imported {import_path} to {node_path}")

    def activate_config(self):
        if not self.sysman:
            raise RuntimeError("Project not initialized")
        handle_configuration(self.sysman)
        self.log("Configuration activated.")
    
    def add_child(self, parent_path: str, name: str, type_str: str) -> tuple[bool, str]:
        type_map = {
            "Axis": 401,
            "Kanal": 403
        }
        subtype = type_map.get(type_str)
        if not self.sysman:
            return False, "TwinCAT project not initialized."
        if not subtype:
            return False, f"Unknown type: {type_str}"

        try:
            result = add_child_node(self.sysman, parent_path, name, subtype)
            if result:
                return True, f"Added {type_str} '{name}' (Subtype {subtype}) under '{parent_path}'"
            else:
                return False, "Failed to add node."
        except Exception as e:
            return False, f"Error during add: {e}"

    def parse_kanal_and_axis(self, available_paths: list[str]) -> dict:
        grouped = {}
        channel_name_map = {}

        # 1. 先解析 Kanal 节点，建立映射表 {channel_number: kanal_name}
        kanal_paths_all = [
            path for path in available_paths
            if path.count("^") == 2 and path.split("^")[-1].lower().startswith(("kanal", "channel"))
        ]
        for idx, path in enumerate(kanal_paths_all, start=1):
            result = parse_kanal_xml(self.sysman, path)
            if "error" in result:
                self.log(f"[Error] Kanal parse failed for {path}: {result['error']}")
                continue
            grouped[result["kanal_name"]] = []
            channel_name_map[idx] = result["kanal_name"]


        # 2. 再解析 Axis 节点，直接放到对应 Kanal
        axis_paths_all = [
            p for p in available_paths
            if p.count("^") == 3 and p.split("^")[-1].lower().startswith(("axis_", "achse_", "ext_"))
        ]
        for path in axis_paths_all:
            result = parse_axis_xml(self.sysman, path, channel_name_map)
            if "error" in result:
                self.log(f"[Error] Axis parse failed for {path}: {result['error']}")
                continue
            grouped[result["kanal_name"]].append(result["axis_name"])

        save_structure_to_file(grouped, "TwinCAT_Kanal_Axis_Structure.json")
        return grouped

    def connect_client(self):
        if self.opc_client:
            self.status = "already_connected"
            self.log("OPC Client is already connected.")
            return True
        self.opc_client = client.connect_opcua_client()
        if self.opc_client:
            self.status = "connected"
            self.log("OPC Client connected successfully.")
            return True
        else:
            self.status = "connect_failed"
            self.log("Failed to connect OPC Client.")
            return False

    def disconnect_client(self):
        if self.opc_client:
            client.disconnect_opcua_client(self.opc_client)
            self.log("OPC Client disconnected.")
            self.opc_client = None
            self.status = "disconnected"
            return True
        else:
            self.status = "no_client"
            self.log("No active OPC Client instance.")
            return False
        
    def apply_trafo_to_twincat(self, kanal: str, cnc_path: str):
        if not self.sysman:
            self.log("Please initialize the TwinCAT project first.")
            return False

        if not self.opc_client:
            self.log("Please connect to OPC UA Client first.")
            return False

        if not kanal:
            self.log("Please select a Kanal.")
            return False

        try:
            data = fetch_trafo_json(self.opc_client, kanal)
            trafo_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))
            write_trafo_lines_to_twincat(self.sysman, cnc_path, trafo_lines)
            self.log(f"Trafo parameters for {kanal} applied to TwinCAT.")
            return True
        except Exception as e:
            self.log(f"[Error] {e}")
            self.log("Failed to apply trafo to TwinCAT node.")
            return False   

    def apply_trafo_to_all_kanals(self, available_paths: list[str]):
        if not self.sysman:
            self.log("Please initialize the TwinCAT project first.")
            return False
        if not self.opc_client:
            self.log("Please connect to OPC UA Client first.")
            return False

        kanal_paths = [
            path for path in available_paths
            if path.split("^")[-1].lower().startswith(("kanal", "channel"))
        ]

        if not kanal_paths:
            self.log("[Warning] No Kanal/Channel paths found.")
            return False

        #self.log(f"[Info] Found {len(kanal_paths)} Kanal/Channel nodes.")

        success = []
        failed = []

        try:
            all_configs = read_all_kanal_configs(self.opc_client, self.kanal_inputs)
        except Exception as e:
            self.log(f"[Error] Failed to read OPC UA config: {e}")
            return False

        for path in kanal_paths:
            try:
                if not all_configs:
                    self.log(f"[Warning] No configurations found for {path}. Skipping.")
                    continue
                write_all_trafo_to_twincat(self.sysman, path, all_configs)
                success.append(path)
            except Exception as e:
                self.log(f"[Error] Failed to write to {path}: {e}")
                failed.append(path)

        self.log(f"[Summary] Kanal write completed. Success: {len(success)} | Failed: {len(failed)}")
        return True

    def read_trafo_from_all_kanals(self, all_configs: dict, available_paths: list[str]) -> dict:
        if not self.sysman:
            self.log("Please initialize the TwinCAT project first.")
            return all_configs

        if not self.opc_client:
            self.log("Please connect to OPC UA Client first.")
            return all_configs

        kanal_paths = [
            path for path in available_paths
            if path.split("^")[-1].lower().startswith(("kanal", "channel"))
        ]

        if not kanal_paths:
            self.log("[Warning] No Kanal/Channel paths found in available_paths.")
            return all_configs

        #self.log(f"[Info] Found {len(kanal_paths)} Kanal/Channel nodes.")

        if not all_configs:
            self.log("[Warning] Input all_configs is empty. Abort.")
            return all_configs

        success = []
        failed = []

        for path in kanal_paths:
            try:
                updated = read_all_trafo_from_twincat(self.sysman, path, all_configs)
                if updated:
                    all_configs = updated
                    success.append(path)
                else:
                    failed.append(path)
            except Exception as e:
                self.log(f"[Error] Failed to read from {path}: {e}")
                failed.append(path)

        self.log(f"[Summary] Success: {len(success)} | Failed: {len(failed)}")

        write_all_configs_to_opcua(self.opc_client, all_configs)
        self.log("All Kanal configurations updated in OPC UA Server.")

        return all_configs

    def apply_all_axis_with_mapping(self, kanal: str) -> bool:
        if not self.sysman:
            self.log("Please initialize the TwinCAT project first.")
            return False
        if not self.opc_client:
            self.log("Please connect to OPC UA Client first.")
            return False

        if kanal not in self.axis_mapping:
            self.log(f"[Error] Selected Kanal '{kanal}' not found in mapping.")
            return False

        try:
            data = fetch_axis_json(self.opc_client)
            axis_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))

            kanal_mapping = self.axis_mapping[kanal]
            axis_names = [k for k in kanal_mapping if re.match(r'^(Axis_|Achse_|Ext_)\\d+', k)]

            success_axes = []
            failed_axes = []

            for axis_name in sorted(axis_names):
                twincat_axis_name = kanal_mapping.get(axis_name)
                if not twincat_axis_name:
                    self.log(f"[Warning] No TwinCAT mapping found for {axis_name}")
                    failed_axes.append(axis_name)
                    continue

                target_path = next(
                    (p for p in self.available_paths if p.endswith(f"^{twincat_axis_name}")),
                    None
                )

                if not target_path:
                    self.log(f"[Warning] Path not found in available paths: {twincat_axis_name}")
                    failed_axes.append(axis_name)
                    continue

                single_axis_lines = [line for line in axis_lines if line.startswith(f"{axis_name}.")]
                if not single_axis_lines:
                    self.log(f"[Warning] No parameters found for {axis_name}")
                    failed_axes.append(axis_name)
                    continue

                write_axis_param_to_twincat(self.sysman, target_path, single_axis_lines)
                success_axes.append(axis_name)
                #self.log(f"{axis_name} written to TwinCAT path: {target_path}")

            if success_axes and not failed_axes:
                self.log("All axis parameters applied to TwinCAT.")
            elif success_axes:
                #self.log(f"Successfully applied: {', '.join(success_axes)}")
                #self.log(f"Failed/skipped: {', '.join(failed_axes)}")
                self.log(f"[summary] Successfully applied: {len(success_axes)} | Failed/skipped: {len(failed_axes)}")
            else:
                self.log("No axis parameters were successfully applied.")

            return len(success_axes) > 0

        except Exception as e:
            self.log(f"[Error] {e}")
            self.log("Failed to apply axis parameters to TwinCAT node.")
            return False

    def apply_all_axis_with_matching(self, available_paths: list[str]) -> bool:
        if not self.sysman:
            self.log("Please initialize the TwinCAT project first.")
            return False

        if not self.opc_client:
            self.log("Please connect to OPC UA Client first.")
            return False

        axis_paths_all = [
            path for path in available_paths
            if path.count("^") == 3 and path.split("^")[-1].lower().startswith(("axis_", "achse_", "ext_"))
        ]

        if not axis_paths_all:
            self.log("[Warning] No Axis/Achse paths found in available_paths.")
            return False

        self.log(f"[Info] Found {len(axis_paths_all)} Axis/Achse nodes.")

        try:
            all_configs = read_all_kanal_configs(self.opc_client, self.kanal_inputs)
        except Exception as e:
            self.log(f"[Error] Failed to fetch OPC UA Kanal configs: {e}")
            return False

        if not all_configs:
            self.log("[Error] No configs retrieved from OPC UA.")
            return False

        success = []
        failed = []

        for path in axis_paths_all:
            try:
                result = write_all_axis_param_to_twincat(self.sysman, path, all_configs)
                if result:
                    success.append(path)
                else:
                    failed.append(path)
            except Exception as e:
                self.log(f"[Error] Exception while writing to {path}: {e}")
                failed.append(path)

        self.log(f"[Summary] Axis write completed. success: {len(success)}, failed: {len(failed)}")
        #self.log(f"Success: {len(success)}")
        #self.log(f"Failed: {len(failed)}")

        if failed:
            for f in failed:
                self.log(f"[Failed] {f}")

        return len(success) > 0

    def read_all_axis_with_matching(self, all_configs: dict, available_paths: list[str]) -> dict:
        if not self.sysman:
            self.log("TwinCAT is not initialized. Please initialize it first.")
            return all_configs

        if not self.opc_client:
            self.log("OPC UA client is not connected. Please connect first.")
            return all_configs

        axis_paths_all = [
            path for path in available_paths
            if path.count("^") == 3 and path.split("^")[-1].lower().startswith(("axis_", "achse_", "ext_"))
        ]

        if not axis_paths_all:
            self.log("[Warning] No Axis/Achse paths found.")
            return all_configs

        #self.log(f"[Info] Found {len(axis_paths_all)} Axis/Achse nodes.")

        success = []
        failed = []

        for path in axis_paths_all:
            try:
                updated_config = read_all_axis_from_twincat(self.sysman, path, all_configs)
                if updated_config:
                    all_configs = updated_config
                    success.append(path)
                else:
                    self.log(f"[Failed] Could not read from: {path}")
                    failed.append(path)
            except Exception as e:
                self.log(f"[Error] Exception while reading from {path}: {e}")
                failed.append(path)

        self.log(f"[Summary] Axis parameter reading completed. success: {len(success)}, failed: {len(failed)}")
        #self.log(f"Successful: {len(success)}")
        #self.log(f"Failed: {len(failed)}")
        for f in failed:
            self.log(f"[Failed] {f}")

        write_all_configs_to_opcua(self.opc_client, all_configs)
        self.log("All axis configurations updated in OPC UA Server.")

        return all_configs

    def apply_one_axis(self, axis_path: str) -> bool:
        if not self.sysman:
            self.log("Please initialize the TwinCAT project first.")
            return False
        if not self.opc_client:
            self.log("Please connect to OPC UA Client first.")
            return False
        try:
            data = fetch_axis_json(self.opc_client)
            axis_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))
            write_axis_param_to_twincat(self.sysman, axis_path, axis_lines)
            self.log(f"Axis parameters applied to TwinCAT path: {axis_path}")
            return True
        except Exception as e:
            self.log(f"[Error] {e}")
            self.log("Failed to apply axis parameters to TwinCAT node.")
            return False

    def create_axis_name(self, kanal_name: str, used_indices: set) -> str:
        """根据 Kanal 名和已用序号生成唯一的 Axis 名"""
        # 从 Kanal 名提取编号，例如 Kanal_1 → 1
        match = re.search(r'(\d+)$', kanal_name)
        kanal_num = match.group(1) if match else "0"

        # 找到未用的下一个序号
        index = 1
        while index in used_indices:
            index += 1

        # 生成名称，例如 Achse_11
        return f"Achse_{kanal_num}{index}", index

    def create_missing_kanal_axis_structure(self, available_paths: list[str], compare_result: dict):
        """
        Compare kanal and axis structures between OPC UA and TwinCAT.
        """
        if not self.sysman:
            self.log("[Error] TwinCAT project is not initialized.")
            return False

        created_kanals = []
        created_axes = []

        kanal_parent_path, axis_parent_path = self.detect_parent_paths(available_paths)

        if not kanal_parent_path or not axis_parent_path:
            self.log("[Error] Cannot find Kanal or Axis parent path from available_paths.")
            return False

        # 1. 创建缺失的 Kanal
        for kanal_name in compare_result.get("missing_kanals", []):
            ok, msg = self.add_child(kanal_parent_path, kanal_name, "Kanal")
            self.log(f"[{'OK' if ok else 'Error'}] {msg}")
            if ok:
                created_kanals.append(kanal_name)

        # 2. 创建缺失的 Axis（自动命名）
        for kanal_name, axes in compare_result.get("missing_axes", {}).items():
            used_indices = set()  # 已用的序号
            for axis_name in axes:
                # 自动生成 Axis 名
                new_axis_name, new_index = self.create_axis_name(kanal_name, used_indices)
                ok, msg = self.add_child(axis_parent_path, new_axis_name, "Axis")
                self.log(f"[{'OK' if ok else 'Error'}] {msg}")
                if ok:
                    created_axes.append((kanal_name, new_axis_name))
                    used_indices.add(new_index)

        # 3. 报告多余的 Kanal
        for kanal_name in compare_result.get("extra_kanals", []):
            self.log(f"[Error] Extra Kanal in TwinCAT: {kanal_name}")

        # 4. 报告多余的 Axis
        for kanal_name, axes in compare_result.get("extra_axes", {}).items():
            for axis_name in axes:
                self.log(f"[Error] Extra Axis in TwinCAT: {axis_name} in {kanal_name}")

        self.log(f"[Summary] Created {len(created_kanals)} Kanal(s), {len(created_axes)} Axis(es).")
        return {
            "created_kanals": created_kanals,
            "created_axes": created_axes
        }

    def detect_parent_paths(self, available_paths: list[str]) -> tuple[str, str] | None:
        kanal_parent_path = None
        axis_parent_path = None
        
        for path in available_paths:
            parts = path.split("^")
            if len(parts) == 2:  
                kanal_parent_path = path
                break
    
        axis_keywords = ("axis_", "achse_", "ext_")
        for path in available_paths:
            parts = path.split("^")
            if len(parts) >= 4 and any(parts[3].lower().startswith(k) for k in axis_keywords):
                axis_parent_path = "^".join(parts[:3])  
                break

        if not kanal_parent_path or not axis_parent_path:
            self.log("[Error] Cannot find Kanal or Axis parent path from available_paths.")
            return None

        self.log(f"[Info] Detected Kanal parent path: {kanal_parent_path}")
        self.log(f"[Info] Detected Axis parent path: {axis_parent_path}")
        return kanal_parent_path, axis_parent_path
