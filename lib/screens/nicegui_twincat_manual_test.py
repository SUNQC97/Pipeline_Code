import os
import json
from pathlib import Path
from nicegui import ui
from dotenv import load_dotenv
from lib.services.twincat_manager import TwinCATManager
import asyncio
from lib.services.opcua_tool import ConfigChangeHandler
from lib.screens import state

def show_twincat_manual_page():
    # Load mapping and config
    config_path = Path(__file__).parent / ".." / "config"
    with open(config_path / "Kanal_Axis_mapping.json", "r", encoding="utf-8") as f:
        axis_mapping = json.load(f)
    available_kanals = list(axis_mapping.keys())

    opc_subscription_started = False
    opc_client = None
    listener_status_label = ui.label("Listener : Stopped").style('color: red; font-weight: bold;')

    # Manager instance, log output to log_area
    log_area = ui.textarea(label='Log').props('readonly').style('width: 100%; height: 200px')
    def append_log(text):
        log_area.value += text + '\n'
 
    manager = TwinCATManager(log_func=append_log)

    config = manager.config
    TWINCAT_PROJECT_PATH = config["TWINCAT_PROJECT_PATH"]
    AMS_NET_ID = config["AMS_NET_ID"]
    EXPORT_BASE_DIR = config["EXPORT_BASE_DIR"]
    IMPORT_BASE_DIR = config["IMPORT_BASE_DIR"]

    # UI controls
    vs_input = ui.input("TwinCAT Project Path", value=TWINCAT_PROJECT_PATH).props('outlined').style('width: 100%')
    ams_input = ui.input("AMS Net ID", value=AMS_NET_ID).props('outlined').style('width: 100%')
    cnc_path = ui.input("CNC Node Path").props('outlined').style('width: 100%')
    export_input = ui.input("Export File Path", value=EXPORT_BASE_DIR + "\\").props('outlined').style('width: 100%')
    import_input = ui.input("Import File Path", value=IMPORT_BASE_DIR + "\\").props('outlined').style('width: 100%')

    uploaded_import_path = None
    available_paths = []

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


    def do_export():
        try:
            manager.export_node(cnc_path.value, export_input.value)
        except Exception as e:
            append_log(f"Export failed: {e}")

    def do_import():
        import_path = uploaded_import_path or import_input.value
        try:
            manager.import_node(cnc_path.value, import_path)
        except Exception as e:
            append_log(f"Import failed: {e}")

    def activate_config():
        try:
            manager.activate_config()
        except Exception as e:
            append_log(f"Activation failed: {e}")

    # OPC UA related operations
    def connect_client():
        manager.connect_client()

    def disconnect_client():
        manager.disconnect_client()

    def apply_trafo_to_twincat():
        kanal = selected_kanal.value
        manager.apply_trafo_to_twincat(kanal, cnc_path.value)

    def apply_trafo_to_all_kanals():
        manager.apply_trafo_to_all_kanals()

    def apply_all_axis_to_twincat_with_mapping():
        kanal = selected_kanal.value
        manager.apply_all_axis_with_mapping(kanal)

    def apply_all_axis_to_twincat_with_matching():
        manager.apply_all_axis_with_matching()

    def apply_one_axis_to_twincat():
        axis_path = cnc_path.value  # Or you can add an axis_path input box
        manager.apply_one_axis(axis_path)

    # Structure browsing
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

    def browse_selected_structure():
        nonlocal available_paths
        keyword = structure_map[structure_dropdown.value]
        available_paths = manager.browse_structure(keyword)
        path_selection_area.clear()
        with path_selection_area:
            path_dropdown = ui.select(label="Select Node Path", options=available_paths).style("width: 100%")
            def confirm():
                cnc_path.value = path_dropdown.value
            ui.button("Confirm Selected Path", on_click=confirm)

    def refresh_upload():
        upload_area.clear()
        with upload_area:
            ui.upload(label="Upload .xml or .sdf File", on_upload=handle_upload, auto_upload=True).props('accept=.xml,.sdf')

    def handle_upload(file):
        nonlocal uploaded_import_path
        os.makedirs(IMPORT_BASE_DIR, exist_ok=True)
        uploaded_import_path = handle_upload_file(file, IMPORT_BASE_DIR)
        import_input.value = uploaded_import_path
        upload_label.text = f"Saved to: {uploaded_import_path}"

    def handle_upload_file(file_obj, save_dir):
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, file_obj.name)
        with open(file_path, "wb") as f:
            f.write(file_obj.content.read())
        append_log(f"Uploaded and saved: {file_path}")
        return file_path

    # UI layout
    ui.label("TwinCAT Automation Tool").style("font-weight: bold; font-size: 20px;")

    with ui.expansion("TwinCAT Initialization and Import/Export", icon='settings'):
        vs_input
        ams_input
        cnc_path
        export_input
        import_input
        ui.button("Initialize TwinCAT Project", on_click=init_sysman, color='primary')
        ui.button("Export CNC Node to XML", on_click=do_export)
        ui.button("Import CNC Node from XML", on_click=do_import)
        ui.button("Activate TwinCAT Configuration", on_click=activate_config)

    with ui.expansion("Upload XML / SDF File", icon='upload'):
        upload_label = ui.label("")
        upload_area = ui.column()
        refresh_upload()
        upload_label

    with ui.expansion("Browse TwinCAT Configuration Structure", icon='list'):
        structure_dropdown = ui.select(
            label="Select a TwinCAT structure to browse",
            options=list(structure_map.keys())
        ).props('outlined').style('width: 100%')
        ui.button("Browse Structure", on_click=browse_selected_structure, color='secondary')
        path_selection_area = ui.column()

    with ui.expansion("OPC UA Client Control", icon='link'):
        dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
        load_dotenv(dotenv_path)
        opc_host = os.getenv("SERVER_IP")
        opc_port = os.getenv("SERVER_PORT")
        with ui.row():
            ui.label(f"OPC UA Server IP: {opc_host}").style("font-weight: bold")
            ui.label(f"Port: {opc_port}").style("font-weight: bold")

        selected_kanal = ui.select(
            label="Select Kanal",
            options=available_kanals,
            value=available_kanals[0] if available_kanals else None
        ).props("outlined").style("width: 200px")

        async def start_opcua_client_listener():
            nonlocal opc_client, opc_subscription_started
            loop = asyncio.get_running_loop()

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
                    ConfigChangeHandler(manager.async_one_click_full_apply, loop)
                )
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



        ui.button("Connect OPC UA Client", on_click=connect_client, color='green')
        ui.button("Disconnect OPC UA Client", on_click=disconnect_client, color='red')
        ui.button("Write Trafo Parameters", on_click=apply_trafo_to_twincat, color='blue')
        ui.button("Write Trafo Parameters to All Kanal", on_click=apply_trafo_to_all_kanals, color='blue')
        ui.button("Write all Axis Parameters with Mapping", on_click=apply_all_axis_to_twincat_with_mapping, color='blue')
        ui.button("Write all Axis Parameters with Matching", on_click=apply_all_axis_to_twincat_with_matching, color='blue')
        ui.button("Write a Axis Parameters", on_click=apply_one_axis_to_twincat, color='blue')
        ui.button("Start OPC UA Listener", on_click=start_opcua_client_listener, color='purple')
        ui.button("Stop OPC UA Listener", on_click=stop_opcua_client_listener, color='purple')
                
        listener_status_label
        log_area