import os
import json
from pathlib import Path
from nicegui import ui
from dotenv import load_dotenv
from lib.services.twincat_manager import TwinCATManager
import asyncio
from lib.services.opcua_tool import ConfigChangeHandler
from lib.screens import state
from lib.services.client import (
    connect_opcua_client,
    read_all_kanal_configs,
    read_modifier_info,
    format_modifier_source,
    update_modifier_info_via_client,
    fetch_kanal_inputs_from_opcua
)
from opcua import Client, ua
from lib.services.TwinCAT_interface import collect_paths
from dotenv import load_dotenv
import time
import socket
import getpass
from datetime import datetime
import socket
import getpass
from lib.utils.get_adapter_info import get_all_adapters

skip_write_back_in_TwinCAT = None


def show_twincat_auto_page():   
    is_logged_in = False

    # 连接OPC UA按钮逻辑
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
        one_click_apply_button.enabled = enabled
        one_click_read_button.enabled = enabled
        start_listener_button.enabled = enabled
        stop_listener_button.enabled = enabled
        connect_button.enabled = not enabled
        disconnect_button.enabled = enabled

    # OPC UA 登录表单
    with ui.row().style('margin-bottom: 16px; gap: 12px; align-items: end'):
        opcua_username_input = ui.input('OPC UA Username', value='', placeholder='Enter username').style('width: 180px')
        opcua_password_input = ui.input('OPC UA Password', value='', password=True, placeholder='Enter password').style('width: 180px')
        login_status_label = ui.label('').style('color: gray; font-weight: bold;')

    #username and password read from .env
    opcua_username_input.value = os.getenv("client_username", "")
    opcua_password_input.value = os.getenv("client_password", "")

    def get_modifier(client: Client):
        # Prefer to use client username
        try:
            client_username = opcua_username_input.value.strip()
            if client_username:
                client_username = client_username + " (Client_User)"
                return client_username
        except Exception:
            pass
        # if not found, use system username
        try:
            system_username = getpass.getuser()
            system_username = system_username + " (System_User)"
            if system_username:
                return system_username
        except Exception:
            pass
        # if not found, use hostname and IP
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            return f"{hostname} ({ip})"
        except Exception:
            return "UnknownHost"

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

    opc_subscription_started = False
    opc_client = None
    listener_status_label = ui.label("Listener : Stopped").style('color: red; font-weight: bold;')

    # Manager instance, log output to log_area
    log_area = ui.textarea(label='Log').props('readonly').style('width: 100%; height: 200px')

    pending_panel = ui.column().style('gap:8px; width:100%')

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

    async def one_click_full_apply():
        nonlocal opc_client
        global skip_write_back_in_TwinCAT

        if skip_write_back_in_TwinCAT == "skip_once":
            skip_write_back_in_TwinCAT = None
            append_log("[INFO] Skipping write back to TwinCAT due to previous operation.")
            return

        try:

            if not state.sysman:
                init_sysman()
                if not state.sysman:
                    append_log("Failed to initialize TwinCAT project.")
                    return

            if not opc_client:
                username = opcua_username_input.value.strip()
                password = opcua_password_input.value
                try:
                    opc_client = connect_opcua_client(username, password)

                    manager.opc_client = opc_client
                    login_status_label.text = f"Logged in as: {username}" if username else "Connected"
                except Exception as e:
                    login_status_label.text = f"Login failed: {e}"
                    append_log(f"[ERROR] OPC UA login failed: {e}")
                    return

            # CNC Configuration is the root node
            structure_key = "CNC Configuration"
            keyword = structure_map[structure_key]
            root_node = state.sysman.LookupTreeItem(keyword)
            
            global available_paths

            available_paths = collect_paths(root_node, prefix=keyword)

            if not available_paths:
                append_log("[Abort] Failed to browse CNC structure.")
                return

            manager.apply_trafo_to_all_kanals(available_paths)
            manager.apply_all_axis_with_matching(available_paths)

            append_log("=== [Done] All parameters applied ===")

        except Exception as e:
            append_log(f"[Error] {e}")
            
        finally:
            skip_write_back_in_TwinCAT = None  

    def one_click_full_read():
        nonlocal opc_client
        global skip_write_back_in_TwinCAT 

        skip_write_back_in_TwinCAT = "skip_once"

        # Clear the skip flag after 2 seconds
        async def clear_skip_flag():
            global skip_write_back_in_TwinCAT
            await asyncio.sleep(2)
            if skip_write_back_in_TwinCAT == "skip_once":
                skip_write_back_in_TwinCAT = None
                append_log("[INFO] Resetting skip flag after 2 seconds.")  
        asyncio.create_task(clear_skip_flag())

        append_log("=== [Start] One-click Read ===")

        try:
            if not state.sysman:
                init_sysman()
                if not state.sysman:
                    append_log("Failed to initialize TwinCAT project.")
                    return

            if not opc_client:
                username = opcua_username_input.value.strip()
                password = opcua_password_input.value
                try:
                    opc_client = connect_opcua_client(username, password)
                    manager.opc_client = opc_client
                    login_status_label.text = f"Logged in as: {username}" if username else "Connected"
                except Exception as e:
                    login_status_label.text = f"Login failed: {e}"
                    append_log(f"[ERROR] OPC UA login failed: {e}")
                    return
            
            structure_key = "CNC Configuration"
            keyword = structure_map[structure_key]
            root_node = state.sysman.LookupTreeItem(keyword)

            available_paths = collect_paths(root_node, prefix=keyword)

            if not available_paths:
                append_log("[Abort] Failed to browse CNC structure.")
                return

            kanal_inputs_twincat = fetch_kanal_inputs_from_opcua(opc_client)
            manager.read_trafo_from_all_kanals(read_all_kanal_configs(opc_client, kanal_inputs_twincat), available_paths)
            manager.read_all_axis_with_matching(read_all_kanal_configs(opc_client, kanal_inputs_twincat), available_paths)
            append_log("=== [Done] All parameters read ===")


            current_modifier = get_modifier(opc_client)
            update_modifier_info_via_client(
                opc_client,
                current_modifier,
                "TwinCAT_Read_Operation",
                "Read_from_TwinCAT"
            )

        except Exception as e:
            append_log(f"[Error] Exception during full read: {e}")

    # Start OPC UA Client listener
    PENDING_CHANGES = {}

    async def confirming_on_change():
        global skip_write_back_in_TwinCAT
        if skip_write_back_in_TwinCAT == "skip_once":
            skip_write_back_in_TwinCAT = None
            append_log("[INFO] Skipping write back to TwinCAT due to previous operation.")
            return

        # read modifier info
        modifier_info = read_modifier_info(opc_client)


        #source = f"OPC UA {opc_host}:{opc_port}"
        base_source = f"OPC UA {opc_host}:{opc_port}"
        source = format_modifier_source(base_source, modifier_info)

        # add log
        if modifier_info and modifier_info.get('modifier') and modifier_info.get('modifier') != 'Unknown':
            append_log(f"[Modifier Info] Found modifier: {modifier_info.get('modifier')}")
        else:
            append_log("[Modifier Info] No modifier info or unknown modifier")

        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        change_id = f'change:{ts}'

        old = PENDING_CHANGES.get(change_id)
        if old and 'row' in old:
            try:
                old['row'].delete()
            except:
                pass


        with pending_panel:
            row = ui.row().style(
                'align-items:center; gap:10px; border:1px solid #ddd; '
                'padding:8px; border-radius:8px; width:100%'
            )
            with row:
                # 时间信息
                ui.label(f'Time: {ts}').style('font-weight:bold; flex-shrink:0')
                
                # 审计信息 - 占用剩余空间
                if modifier_info and modifier_info.get('modifier') and modifier_info.get('modifier') != 'Unknown':
                    ui.label(f'Source: {source}').style('color: blue; font-weight: bold; flex-grow:1')
                else:
                    ui.label(f'Source: {source}').style('color: gray; flex-grow:1')

                # 按钮组 - 放在同一行
                with ui.row().style('gap: 8px; flex-shrink:0'):
                    async def do_import():
                        info_str = f" by {modifier_info.get('modifier', 'Unknown')}" if modifier_info else ""
                        append_log(f'[CONFIRM] Import {change_id}{info_str}...')
                        await one_click_full_apply()
                        append_log(f'[OK] Applied {change_id}')
                        PENDING_CHANGES.pop(change_id, None)
                        row.delete()

                    def do_ignore():
                        info_str = f" by {modifier_info.get('modifier', 'Unknown')}" if modifier_info else ""
                        append_log(f'[INFO] Ignore {change_id}{info_str}')
                        PENDING_CHANGES.pop(change_id, None)
                        row.delete()

                    ui.button('IMPORT', on_click=do_import, color='green').style('min-width: 80px')
                    ui.button('IGNORE', on_click=do_ignore, color='red').style('min-width: 80px')

        PENDING_CHANGES[change_id] = {
            'id': change_id,
            'time': ts,
            'source': source,
            'row': row
        }
    
    async def start_opcua_client_listener():
        nonlocal opc_client, opc_subscription_started

        if not state.sysman:
            init_sysman()
            if not state.sysman:
                append_log("[ERROR] TwinCAT system manager not initialized.")
                return

        if opc_subscription_started:
            append_log("[INFO] Listener already started.")
            return  
        
        if not opc_client:
            username = opcua_username_input.value.strip()
            password = opcua_password_input.value
            try:
                manager.opc_client = opc_client
                login_status_label.text = f"Logged in as: {username}" if username else "Connected"
            except Exception as e:
                login_status_label.text = f"Login failed: {e}"
                append_log(f"[ERROR] OPC UA login failed: {e}")
                return

        try:
            subscription = opc_client.create_subscription(
                100,
                ConfigChangeHandler(
                    callback=confirming_on_change,
                    loop=asyncio.get_running_loop(),
                    delay_sec=1.0
                )
            )

            # Data change subscription
            kanal_inputs_twincat = fetch_kanal_inputs_from_opcua(opc_client)
            for kanal in kanal_inputs_twincat.keys():
                kanal_node = opc_client.get_objects_node().get_child([f"2:{kanal}"])
                for var_name in ["TrafoConfigJSON", "AxisConfigJSON"]:
                    var_node = kanal_node.get_child([f"2:{var_name}"])
                    subscription.subscribe_data_change(var_node)
                    append_log(f"[LISTENING] {kanal}/{var_name}")

            listener_status_label.text = "Listener : Active"
            listener_status_label.style('color: green; font-weight: bold;')
            opc_subscription_started = True
            append_log("[OK] OPC UA Client listener active.")
            
        except Exception as e:
            append_log(f"[Error] OPC UA Listener failed: {e}")

    async def stop_opcua_client_listener():
        nonlocal opc_subscription_started
        if opc_subscription_started:
            opc_subscription_started = False
            listener_status_label.text = "Listener : Stopped"
            listener_status_label.style('color: red; font-weight: bold;')
            append_log("[INFO] OPC UA listener manually marked as stopped.")
            disconnect_opcua()
        else:
            append_log("[INFO] No active listener to stop.")
            disconnect_opcua()

    # Only auto/one-click operations
    ui.label("TwinCAT Auto Operations").style("font-weight: bold; font-size: 20px;")
    connect_button = ui.button("Connect to OPCUA", on_click=connect_opcua, color='blue').style('width: 180px')
    disconnect_button = ui.button("Disconnect OPCUA", on_click=disconnect_opcua, color='red').style('width: 180px')
    init_button = ui.button("Initialize TwinCAT Project", on_click=init_sysman).style('width: 180px')
    one_click_apply_button = ui.button("One-click CNC Init + Write", on_click=one_click_full_apply, color='primary').props('raised')
    one_click_read_button = ui.button("One-click Read", on_click=one_click_full_read, color='primary').props('raised')
    start_listener_button = ui.button("Start OPC UA Listener and OPCUA", on_click=start_opcua_client_listener, color='purple')
    stop_listener_button = ui.button("Stop OPC UA Listener and OPCUA", on_click=stop_opcua_client_listener, color='purple')
    
    # 初始化按钮状态
    enable_operation_buttons(False)  # 初始时禁用所有操作按钮
    
    listener_status_label
    log_area
    pending_panel