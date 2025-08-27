import os
import json
from pathlib import Path
from nicegui import ui
from dotenv import load_dotenv
from lib.services.twincat_manager import TwinCATManager
import asyncio
from lib.services.opcua_tool import ConfigChangeHandler
from lib.screens import state
from lib.services.client import build_kanal_axis_structure, connect_opcua_client
from opcua import Client
from lib.services.TwinCAT_interface import collect_paths
from dotenv import load_dotenv
import time
from lib.utils.structure_compare import compare_kanal_axis_structures


def show_twincat_create_auto_page():
    is_logged_in = False

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

    with ui.row().style('margin-bottom: 16px; gap: 12px; align-items: end'):
        opcua_username_input = ui.input('OPC UA Username', value='', placeholder='Enter username').style('width: 180px')
        opcua_password_input = ui.input('OPC UA Password', value='', password=True, placeholder='Enter password').style('width: 180px')
        login_status_label = ui.label('').style('color: gray; font-weight: bold;')

    # Load environment variables
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path)
    opc_host = os.getenv("SERVER_IP")
    opc_port = os.getenv("SERVER_PORT")

    #username and password read from .env
    opcua_username_input.value = os.getenv("client_username", "")
    opcua_password_input.value = os.getenv("client_password", "")
    
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
            #ui.label(f"Export File Path: {EXPORT_BASE_DIR}\\").style("width: 100%")
            #ui.label(f"Import File Path: {IMPORT_BASE_DIR}\\").style("width: 100%")

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

    def connect_opcua():
        nonlocal opc_client, is_logged_in
        username = opcua_username_input.value.strip()
        password = opcua_password_input.value
        print(f"Connecting to OPC UA with username: {username}")
        print(f"Password: {password}")

        if not username or not password:
            login_status_label.text = "please fill in username and password"
            login_status_label.style('color: red; font-weight: bold;')
            return
        try:
            opc_client = connect_opcua_client(username, password)
            manager.opc_client = opc_client
            is_logged_in = True
            login_status_label.text = f"Logged in as: {username}" if username else "Connected"
            login_status_label.style('color: green; font-weight: bold;')
            append_log(f"[OK] Connected to OPC UA as {username if username else 'Anonymous'}")
            
            # 登录成功后启用操作按钮
            enable_operation_buttons(True)
            
        except Exception as e:
            is_logged_in = False
            opc_client = None
            login_status_label.text = f"Login failed: {e}"
            login_status_label.style('color: red; font-weight: bold;')
            append_log(f"[ERROR] OPC UA login failed: {e}")
            
            # 登录失败时保持操作按钮禁用
            enable_operation_buttons(False)
            return

    def disconnect_opcua():
        nonlocal opc_client, is_logged_in
        try:
            if opc_client:
                opc_client.disconnect()
                append_log("[OK] Disconnected from OPC UA server")
            else:
                append_log("[INFO] No active OPC UA connection to disconnect")

            opc_client = None
            manager.opc_client = None
            is_logged_in = False
            login_status_label.text = "Disconnected"
            login_status_label.style('color: gray; font-weight: bold;')

            # 断开连接后禁用操作按钮
            enable_operation_buttons(False)

        except Exception as e:
            append_log(f"[ERROR] Error disconnecting from OPC UA: {e}")

    def enable_operation_buttons(enabled):
        init_button.enabled = enabled
        connect_button.enabled = not enabled
        disconnect_button.enabled = enabled
        create_kanal_axis_structure_button.enabled = enabled

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
            connect_opcua()
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
    init_button = ui.button("Initialize TwinCAT Project", on_click=init_sysman).style("width: 100%")
    connect_button = ui.button("Connect OPC UA Client", on_click=connect_opcua).style("width: 100%")
    disconnect_button = ui.button("Disconnect OPC UA Client", on_click=disconnect_opcua).style("width: 100%")
    create_kanal_axis_structure_button = ui.button("Create Kanal-Axis Structure", on_click=create_kanal_axis_structure).style("width: 100%")

    enable_operation_buttons(False)
