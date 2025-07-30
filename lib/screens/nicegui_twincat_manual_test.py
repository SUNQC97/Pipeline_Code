import sys
import os
import re
import json
from pathlib import Path
from nicegui import ui
from dotenv import load_dotenv
from lib.services.twincat_manager import TwinCATManager


def show_twincat_manual_page():
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

    config_path = Path(__file__).parent / ".." / "config"
    with open(config_path / "Kanal_Axis_mapping.json", "r", encoding="utf-8") as f:
        axis_mapping = json.load(f)
    available_kanals = list(axis_mapping.keys())

    config = TwinCATManager._load_mapping.__globals__["load_config"]()
    TWINCAT_PROJECT_PATH = config["TWINCAT_PROJECT_PATH"]
    AMS_NET_ID = config["AMS_NET_ID"]
    EXPORT_BASE_DIR = config["EXPORT_BASE_DIR"]
    IMPORT_BASE_DIR = config["IMPORT_BASE_DIR"]

    vs_input = ui.input("TwinCAT Project Path").props('outlined').style('width: 100%')
    ams_input = ui.input("AMS Net ID").props('outlined').style('width: 100%')
    cnc_path = ui.input("CNC Node Path").props('outlined').style('width: 100%')
    export_input = ui.input("Export File Path").props('outlined').style('width: 100%')
    import_input = ui.input("Import File Path").props('outlined').style('width: 100%')
    vs_input.value = TWINCAT_PROJECT_PATH
    ams_input.value = AMS_NET_ID
    export_input.value = EXPORT_BASE_DIR + "\\"
    import_input.value = IMPORT_BASE_DIR + "\\"
    log = ui.textarea(label='Log').props('readonly').style('width: 100%; height: 200px')

    def append_log(text):
        log.value += text + ""
        log.scroll_to_end()
        twincat_manager._log = append_log.props('readonly').style('width: 100%; height: 200px')

    twincat_manager = TwinCATManager(None)

    def browse_structure_and_return_paths(keyword):
        return twincat_manager.browse_structure(keyword)

    def handle_upload_file(file_obj, save_dir):
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, file_obj.name)
        with open(file_path, "wb") as f:
            f.write(file_obj.content.read())
        append_log(f"Uploaded and saved: {file_path}")
        return file_path

    uploaded_import_path = None
    available_paths = []

    def init_sysman():
        twincat_manager.init_sysman(vs_input.value, ams_input.value)

    def do_export():
        twincat_manager.export_node(cnc_path.value, export_input.value)

    def do_import():
        import_path = uploaded_import_path or import_input.value
        twincat_manager.import_node(cnc_path.value, import_path)

    def activate_config():
        twincat_manager.activate_config()

    def connect_client():
        twincat_manager.connect_opcua()

    def disconnect_client():
        twincat_manager.disconnect_opcua()

    def apply_trafo_to_twincat():
        twincat_manager.write_trafo_for_kanal(selected_kanal.value)

    def apply_trafo_to_all_kanals():
        twincat_manager.write_all_kanals()

    def apply_all_axis_to_twincat_with_mapping():
        twincat_manager.write_axis_with_mapping(selected_kanal.value)

    def apply_all_axis_to_twincat_with_matching():
        twincat_manager.write_axis_with_matching()

    def apply_one_axis_to_twincat():
        from lib.services.client import fetch_axis_json, convert_trafo_lines
        if not twincat_manager.sysman or not twincat_manager.opc_client:
            append_log("Please initialize project and connect OPC UA first.")
            return
        data = fetch_axis_json(twincat_manager.opc_client)
        axis_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))
        from lib.services.TwinCAT_interface import write_axis_param_to_twincat
        write_axis_param_to_twincat(twincat_manager.sysman, cnc_path.value, axis_lines)
        append_log("Single axis written.")

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
        available_paths = browse_structure_and_return_paths(keyword)
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

        ui.button("Connect OPC UA Client", on_click=connect_client, color='green')
        ui.button("Disconnect OPC UA Client", on_click=disconnect_client, color='red')
        ui.button("Write Trafo Parameters", on_click=apply_trafo_to_twincat, color='blue')
        ui.button("Write Trafo Parameters to All Kanal", on_click=apply_trafo_to_all_kanals, color='blue')
        ui.button("Write all Axis Parameters with Mapping", on_click=apply_all_axis_to_twincat_with_mapping, color='blue')
        ui.button("Write all Axis Parameters with Matching", on_click=apply_all_axis_to_twincat_with_matching, color='blue')
        ui.button("Write a Axis Parameters", on_click=apply_one_axis_to_twincat, color='blue')
