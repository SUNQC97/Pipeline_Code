import os
import json
from pathlib import Path
from nicegui import ui
from dotenv import load_dotenv
from lib.services.twincat_manager import TwinCATManager
import asyncio
from lib.services.opcua_tool import ConfigChangeHandler
from lib.screens import state
from lib.services.client import read_all_kanal_configs, build_kanal_axis_structure
from opcua import Client, ua
from lib.services.TwinCAT_interface import collect_paths
from dotenv import load_dotenv
import time
from datetime import datetime

skip_write_back_in_TwinCAT = None


def show_twincat_auto_page():

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
                manager.connect_client()
                opc_client = manager.opc_client
                if not manager.opc_client:
                    append_log("Failed to connect OPC UA Client.")
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
                manager.connect_client()
            if not opc_client:
                append_log("Failed to connect to OPC UA Client.")
                return

            structure_key = "CNC Configuration"
            keyword = structure_map[structure_key]
            root_node = state.sysman.LookupTreeItem(keyword)

            available_paths = collect_paths(root_node, prefix=keyword)

            if not available_paths:
                append_log("[Abort] Failed to browse CNC structure.")
                return

            manager.read_trafo_from_all_kanals(read_all_kanal_configs(opc_client, state.kanal_inputs), available_paths)
            manager.read_all_axis_with_matching(read_all_kanal_configs(opc_client, state.kanal_inputs), available_paths)
            append_log("=== [Done] All parameters read ===")
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

        source = f"OPC UA {opc_host}:{opc_port}"
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
                ui.label(f'Time: {ts}').style('font-weight:bold')
                ui.label(f'Source: {source}')

                async def do_import():
                    append_log(f'[CONFIRM] Import {change_id}...')
                    await one_click_full_apply()
                    append_log(f'[OK] Applied {change_id}')
                    PENDING_CHANGES.pop(change_id, None)
                    row.delete()

                def do_ignore():
                    append_log(f'[INFO] Ignore {change_id}')
                    PENDING_CHANGES.pop(change_id, None)
                    row.delete()

                ui.button('Import', on_click=do_import, color='green')
                ui.button('Ignore', on_click=do_ignore, color='red')

        PENDING_CHANGES[change_id] = {
            'id': change_id,
            'time': ts,
            'source': source,
            'row': row
        }
    
    async def start_opcua_client_listener():
        nonlocal opc_client, opc_subscription_started
        
        init_sysman()

        if opc_subscription_started:
            append_log("[INFO] Listener already started.")
            return  
        
        if not opc_client:
            manager.connect_client()
            opc_client = manager.opc_client
            if not opc_client:
                append_log("Failed to connect OPC UA Client.")
                return
            append_log("OPC UA Client connected.")

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
            for kanal in state.kanal_inputs.keys():
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
        else:
            append_log("[INFO] No active listener to stop.")

    # Only auto/one-click operations
    ui.label("TwinCAT Auto Operations").style("font-weight: bold; font-size: 20px;")
    ui.button("Initialize TwinCAT Project", on_click=init_sysman).style("width: 100%")
    ui.button("One-click CNC Init + Write", on_click=one_click_full_apply, color='primary').props('raised')
    ui.button("One-click Read", on_click=one_click_full_read, color='primary').props('raised')
    ui.button("Start OPC UA Listener", on_click=start_opcua_client_listener, color='purple')
    ui.button("Stop OPC UA Listener", on_click=stop_opcua_client_listener, color='purple')
    listener_status_label
    log_area

    ui.label("Pending Changes").style("font-weight: bold; font-size: 16px; margin-top: 16px")
    pending_panel