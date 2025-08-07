import os
import json
from pathlib import Path
from nicegui import ui
from dotenv import load_dotenv
from lib.services.twincat_manager import TwinCATManager
import asyncio
from lib.services.opcua_tool import ConfigChangeHandler
from lib.screens import state
from lib.services.client import build_kanal_axis_structure
from opcua import Client
from lib.services.TwinCAT_interface import collect_paths
from dotenv import load_dotenv
import time
from lib.utils.structure_compare import compare_kanal_axis_structures

def show_twincat_create_auto_page():
    
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

    opcua_client = None

    # Load environment variables
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path)
    opc_host = os.getenv("SERVER_IP")
    opc_port = os.getenv("SERVER_PORT")

    opc_client = None

    # Manager instance, log output to log_area
    log_area = ui.textarea(label='Log').props('readonly').style('width: 100%; height: 200px')

    def append_log(text):
        log_area.value += text + '\n'

    manager = TwinCATManager(log_func=append_log)

    # Only show config as readonly, do not allow editing
    config = manager.config
    TWINCAT_PROJECT_PATH = config["TWINCAT_PROJECT_PATH"]
    AMS_NET_ID = config["AMS_NET_ID"]
    EXPORT_BASE_DIR = config["EXPORT_BASE_DIR"]
    IMPORT_BASE_DIR = config["IMPORT_BASE_DIR"]

    # Show config as readonly fields
    with ui.row().style("width: 100%; justify-content: space-between"):
        with ui.column().style("flex: 1"):
            ui.label(f"OPC UA Server IP: {opc_host}").style("font-weight: bold")
            ui.label(f"Port: {opc_port}").style("font-weight: bold")

        with ui.column().style("flex: 2"):
            ui.label("TwinCAT Configuration").style("font-weight: bold; font-size: 16px; margin-bottom: 4px")
            ui.label(f"Project Path: {TWINCAT_PROJECT_PATH}").style("width: 100%")
            ui.label(f"AMS Net ID: {AMS_NET_ID}").style("width: 100%")
            ui.label(f"Export File Path: {EXPORT_BASE_DIR}\\").style("width: 100%")
            ui.label(f"Import File Path: {IMPORT_BASE_DIR}\\").style("width: 100%")

    # TwinCAT related operations
    def init_sysman():
        manager.project_path = TWINCAT_PROJECT_PATH
        manager.ams_net_id = AMS_NET_ID
        success = manager.init_project()

        if success:
            state.sysman = manager.sysman
            append_log("initial: Success")
        else:
            append_log("initial: Failed")

    def get_opcua_client():
        nonlocal opc_client

        if not opc_client:
            try:
                manager.connect_client()
                opc_client = manager.opc_client
                append_log(f"Connected to OPC UA Server at {opc_host}:{opc_port}")
            except Exception as e:
                append_log(f"Failed to connect to OPC UA Server: {e}")
        return opc_client


    def create_kanal_axis_structure():
        nonlocal opc_client

        # 确保 TwinCAT 初始化
        if not state.sysman:
            init_sysman()
            if not state.sysman:
                append_log("[Error] Failed to initialize TwinCAT project.")
                return

        # 确保 OPC UA 客户端已连接
        if not opc_client:
            get_opcua_client()
        if not opc_client:
            append_log("[Error] OPC UA client not connected.")
            return

        # 获取 available_paths
        structure_key = "CNC Configuration"
        keyword = structure_map[structure_key]
        root_node = state.sysman.LookupTreeItem(keyword)
        available_paths = collect_paths(root_node, prefix=keyword)

        if not available_paths:
            append_log("[Error] No available paths found in TwinCAT project.")
            return

        try:
            # 获取 OPC UA 结构
            opcua_structure = build_kanal_axis_structure(opc_client)
            append_log("[OK] Built OPC UA Kanal-Axis structure.")

            print(f"OPC UA Kanal-Axis structure: {opcua_structure}")

            # 获取 TwinCAT 结构
            twincat_structure = manager.parse_kanal_and_axis_by_xml(available_paths)
            append_log("[OK] Parsed TwinCAT Kanal-Axis structure.")

            print(f"TwinCAT Kanal-Axis structure: {twincat_structure}")

            # 比较
            comparison_result = compare_kanal_axis_structures(
                opcua_structure,
                twincat_structure,
                "kanal_axis_comparison.json"
            )
            append_log("[OK] Compared structures.")

            create_result = manager.create_missing_kanal_axis_structure(available_paths, comparison_result)
            append_log(f"[Summary] Created {len(create_result['created_kanals'])} Kanals, {len(create_result['created_axes'])} Axes.")

        except Exception as e:
            append_log(f"[Error] {e}")
            return

    # Only auto/one-click operations
    ui.label("TwinCAT Auto Operations").style("font-weight: bold; font-size: 20px;")
    ui.button("Initialize TwinCAT Project", on_click=init_sysman).style("width: 100%")
    ui.button("Connect OPC UA Client", on_click=get_opcua_client).style("width: 100%")
    ui.button("Create Kanal-Axis Structure", on_click=create_kanal_axis_structure).style("width: 100%")

    log_area