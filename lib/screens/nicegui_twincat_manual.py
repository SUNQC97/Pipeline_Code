import sys
import os
import asyncio
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import re
from nicegui import ui
from lib.screens import state
import json
from pathlib import Path
from lib.screens.state import kanal_inputs
from lib.services.TwinCAT_interface import (
    init_project,
    export_cnc_node,
    import_cnc_node,
    handle_configuration,
    load_config,
    collect_paths,
    get_export_path,
    get_import_path,
    add_child_node,
    write_trafo_lines_to_twincat,
    write_axis_param_to_twincat,
    write_all_trafo_to_twincat,
    write_all_axis_param_to_twincat,
    read_all_trafo_from_twincat,
    read_all_axis_from_twincat,
    import_child_node
)
from lib.services.client import (
    connect_opcua_client,
    disconnect_opcua_client,
    convert_trafo_lines,
    fetch_trafo_json,
    fetch_axis_json,
    read_all_kanal_configs,
    write_all_configs_to_opcua
)
from lib.services.opcua_tool import ConfigChangeHandler


available_paths = []

def show_twincat_page():

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

    uploaded_import_path = None
    path_dropdown = None
    config = load_config()
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

    opc_subscription_started = False
    listener_status_label = ui.label("Listener : Stopped").style('color: red; font-weight: bold;')

    log = ui.textarea(label='Log').props('readonly').style('width: 100%; height: 200px')
    
    current_dir = Path(__file__).parent

    # Load axis mapping from JSON file
    mapping_path = current_dir.parent.parent / "lib" / "config" / "Kanal_Axis_mapping.json"

    with open(mapping_path, "r", encoding="utf-8") as f:
        axis_mapping = json.load(f)

    #available_kanals = list(axis_mapping.keys())

    available_kanals = list(kanal_inputs.keys())


    def append_log(text: str):
        log.value += text + '\n'

    def init_sysman():
        if state.sysman is None:
            append_log("Initializing TwinCAT project...")
            state.sysman = init_project(vs_input.value, ams_input.value)
            if state.sysman:
                ui.notify("TwinCAT project initialized successfully.")
                append_log("TwinCAT project initialized.")
            else:
                ui.notify("Initialization failed.", color='red')
                append_log("Failed to initialize TwinCAT project.")
        else:
            ui.notify("TwinCAT project already initialized.")
            append_log("TwinCAT project already initialized.")

    def do_export():
        if not state.sysman:
            append_log("Please initialize the project first.")
            return
        export_cnc_node(state.sysman, cnc_path.value, export_input.value)
        append_log(f"Exported to {export_input.value}")

    def do_import():
        nonlocal uploaded_import_path
        if not state.sysman:
            append_log("Please initialize the project first.")
            return
        import_path = uploaded_import_path or import_input.value
        import_cnc_node(state.sysman, cnc_path.value, import_path)
        append_log(f"Imported from {import_path}")

    def activate_config():
        if not state.sysman:
            append_log("Please initialize the project first.")
            return
        handle_configuration(state.sysman)
        append_log("Configuration activated.")

    def update_export_import_path():
        export_input.value = get_export_path(EXPORT_BASE_DIR, cnc_path.value)
        import_input.value = get_import_path(IMPORT_BASE_DIR, cnc_path.value)
        append_log(f"Updated paths:\nExport → {export_input.value}\nImport → {import_input.value}")

    def refresh_upload():
        upload_area.clear()
        with upload_area:
            ui.upload(
                label="Upload .xml or .sdf File",
                on_upload=handle_upload,
                auto_upload=True,
                multiple=False
            ).props('accept=.xml,.sdf')

    def handle_upload(file):
        nonlocal uploaded_import_path
        save_dir = IMPORT_BASE_DIR
        os.makedirs(save_dir, exist_ok=True)
        uploaded_import_path = os.path.join(save_dir, file.name)
        with open(uploaded_import_path, "wb") as f:
            f.write(file.content.read())
        import_input.value = uploaded_import_path
        upload_label.text = f"Saved to: {uploaded_import_path}"
        append_log(f"Uploaded and saved: {uploaded_import_path}")
        refresh_upload()

    def browse_selected_structure():
        nonlocal path_dropdown
        if not state.sysman:
            append_log("Please initialize the project first.")
            return

        selected = structure_dropdown.value
        if not selected:
            append_log("Please select a structure.")
            return

        keyword = structure_map[selected]
        try:
            root_node = state.sysman.LookupTreeItem(keyword)
            append_log(f"Browsing structure: {selected} ({keyword})")
            global available_paths
            available_paths = collect_paths(root_node, prefix=keyword)
            append_log(f"Found {len(available_paths)} nodes.")

            path_selection_area.clear()
            with path_selection_area:
                path_dropdown = ui.select(label="Select Node Path", options=available_paths).style("width: 100%")

                def confirm_node_path():
                    selected_path = path_dropdown.value
                    if selected_path:
                        cnc_path.value = selected_path
                        append_log(f"Selected path set to: {selected_path}")
                        update_export_import_path()

                def confirm_Parent_path():
                    selected_path = path_dropdown.value
                    if selected_path:
                        parent_path.value = selected_path
                        append_log(f"[Parent Path] set to: {selected_path}")

                ui.button("Confirm Selected Path", on_click=confirm_node_path, color='primary')
                ui.button("Confirm Selected Parent Path", on_click=confirm_Parent_path, color='primary')

        except Exception as e:
            append_log(f"[Error]: {e}")

    def do_add_fixed_type_child():
        if not state.sysman:
            append_log("Please initialize the TwinCAT project first.")
            return
        if not parent_path.value:
            append_log("Please select a parent path.")
            return

        name = child_name_input.value.strip()
        type_selected = type_dropdown.value
        if not name or not type_selected:
            append_log("Please fill in node name and select a type.")
            return

        subtype = type_map.get(type_selected)
        if subtype is None:
            append_log(f"Unknown type: {type_selected}")
            return

        try:
            result = add_child_node(state.sysman, parent_path.value, name, subtype)
            if result:
                append_log(f"Added {type_selected} '{name}' (Subtype {subtype}) under '{parent_path.value}'")
            else:
                append_log("Failed to add node.")
        except Exception as e:
            append_log(f"Error during add: {e}")

    def do_import_Child_xml():
        if not state.sysman:
            append_log("Please initialize the TwinCAT project first.")
            return
        if not parent_path.value:
            append_log("Please select a parent path.")
            return

        # 如果上传了 XML，就用它；否则用手动输入路径
        xml_path = import_input.value.strip()

        if not xml_path or not os.path.isfile(xml_path):
            append_log("No valid XML path provided.")
            return

        try:
            success = import_child_node(state.sysman, parent_path.value, xml_path)
            if success:
                append_log(f"Imported child node from '{xml_path}' under '{parent_path.value}'")
            else:
                append_log(f"Failed to import XML: {xml_path}")
        except Exception as e:
            append_log(f"Error during import: {e}")



    type_map = {
        "Axis": 401,
        "Kanal": 403
    }

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
        browse_button = ui.button("Browse Structure", on_click=browse_selected_structure, color='secondary')
        path_selection_area = ui.column()

    with ui.expansion("Add Axis or Kanal Node", icon='plus'):
        child_name_input = ui.input("Node Name").props("outlined").style("width: 100%")
        parent_path = ui.input("Parent Path").props('outlined').style("width: 100%")
        type_dropdown = ui.select(
            label="Node Type",
            options=["Axis", "Kanal"]
        ).props("outlined").style("width: 100%")
        ui.button("Add Node", on_click=do_add_fixed_type_child, color='accent')
        ui.button("Import Child Node from XML", on_click=do_import_Child_xml, color='accent')

    with ui.expansion("OPC UA Client Control", icon='link'):
        from dotenv import load_dotenv
        dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
        load_dotenv(dotenv_path)
        opc_host = os.getenv("SERVER_IP")
        opc_port = os.getenv("SERVER_PORT")


        with ui.row():
            ui.label(f"OPC UA Server IP: {opc_host}").style("font-weight: bold")
            ui.label(f"Port: {opc_port}").style("font-weight: bold")
        opc_client = None

        selected_kanal = ui.select(
            label="Select Kanal",
            options=available_kanals,
            value=available_kanals[0] if available_kanals else None
        ).props("outlined").style("width: 200px")
        

        def connect_client():
            nonlocal opc_client
            if opc_client:
                append_log("OPC Client is already connected.")
                return
            opc_client = connect_opcua_client()
            if opc_client:
                append_log("OPC Client connected successfully.")
            else:
                append_log("Failed to connect OPC Client.")

        def disconnect_client():
            nonlocal opc_client
            if opc_client:
                disconnect_opcua_client(opc_client)
                append_log("OPC Client disconnected.")
                opc_client = None
            else:
                append_log("No active OPC Client instance.")

        
        def apply_trafo_to_twincat():
            if not state.sysman:
                append_log("Please initialize the TwinCAT project first.")
                return
            if not opc_client:
                append_log("Please connect to OPC UA Client first.")
                return
            kanal = selected_kanal.value
            if not kanal:
                append_log("Please select a Kanal.")
                return
            try:
                data = fetch_trafo_json(opc_client, kanal)
                trafo_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))
                write_trafo_lines_to_twincat(state.sysman, cnc_path.value, trafo_lines)
                append_log(f"Trafo parameters for {kanal} applied to TwinCAT.")
            except Exception as e:
                append_log(f"[Error] {e}")
                append_log("Failed to apply trafo to TwinCAT node.")

        def apply_trafo_to_all_kanals():
            if not state.sysman:
                append_log("Please initialize the TwinCAT project first.")
                return
            if not opc_client:
                append_log("Please connect to OPC UA Client first.")
                return

            kanal_paths = [
                path for path in available_paths
                if path.split("^")[-1].lower().startswith("kanal") or path.split("^")[-1].lower().startswith("channel")
            ]

            if not kanal_paths:
                append_log("[Warning] No Kanal/Channel paths found in available_paths.")
                return

            append_log(f"[Info] Found {len(kanal_paths)} Kanal/Channel nodes.")

            success = []
            failed = []

            for path in kanal_paths:
                print(f"Processing {path}")

                try:
                    all_configs = read_all_kanal_configs(opc_client, kanal_inputs)
                    if not all_configs:
                        append_log(f"[Warning] No configurations found for {path}. Skipping.")
                        continue
                    write_all_trafo_to_twincat(state.sysman, path, all_configs)
                    
                    success.append(path)
                except Exception as e:
                    append_log(f"[Error] Failed to write to {path}: {e}")
                    failed.append(path)

            append_log(f"\n[Summary] Success: {len(success)} | Failed: {len(failed)}")

        def read_trafo_from_all_kanals(all_configs):
            if not state.sysman:
                append_log("Please initialize the TwinCAT project first.")
                return all_configs
            if not opc_client:
                append_log("Please connect to OPC UA Client first.")
                return all_configs

            kanal_paths = [
                path for path in available_paths
                if path.split("^")[-1].lower().startswith("kanal") or path.split("^")[-1].lower().startswith("channel")
            ]

            if not kanal_paths:
                append_log("[Warning] No Kanal/Channel paths found in available_paths.")
                return all_configs

            append_log(f"[Info] Found {len(kanal_paths)} Kanal/Channel nodes.")

            if not all_configs:
                append_log("[Warning] Input all_configs is empty. Abort.")
                return all_configs

            success = []
            failed = []

            for path in kanal_paths:
                try:
                    updated = read_all_trafo_from_twincat(state.sysman, path, all_configs)
                    if updated:
                        all_configs = updated 
                        success.append(path)
                    else:
                        failed.append(path)
                except Exception as e:
                    append_log(f"[Error] Failed to read from {path}: {e}")
                    failed.append(path)

            append_log(f"\n[Summary] Success: {len(success)} | Failed: {len(failed)}")
            write_all_configs_to_opcua(opc_client, all_configs)  
            append_log("All Kanal configurations updated in OPC UA Server.")    

        def apply_all_axis_to_twincat_with_mapping():
            if not state.sysman:
                append_log("Please initialize the TwinCAT project first.")
                return
            if not opc_client:
                append_log("Please connect to OPC UA Client first.")
                return
            
            kanal = selected_kanal.value
            if kanal not in axis_mapping:
                append_log(f"[Error] Selected Kanal '{kanal}' not found in mapping.")
                return        
                    
            try:
                
                data = fetch_axis_json(opc_client)
                axis_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))

                kanal_mapping = axis_mapping[kanal]
                axis_names = [k for k in kanal_mapping if re.match(r'^(Axis_|Achse_|Ext_)\d+', k)]
                
                success_axes = []
                failed_axes = []

                for axis_name in sorted(axis_names):
                    twincat_axis_name = kanal_mapping.get(axis_name)
                    if not twincat_axis_name:
                        append_log(f"[Warning] No TwinCAT mapping found for {axis_name}")
                        failed_axes.append(axis_name)
                        continue

                    target_path = next(
                        (p for p in available_paths if p.endswith(f"^{twincat_axis_name}")),
                        None
                    )
                    
                    if not target_path:
                        append_log(f"[Warning] Path not found in available paths: {target_path}")
                        failed_axes.append(axis_name)
                        continue

                    single_axis_lines = [line for line in axis_lines if line.startswith(f"{axis_name}.")]
                    if not single_axis_lines:
                        append_log(f"[Warning] No parameters found for {axis_name}")
                        failed_axes.append(axis_name)
                        continue

                    write_axis_param_to_twincat(state.sysman, target_path, single_axis_lines)
                    success_axes.append(axis_name)
                    append_log(f"{axis_name} written to TwinCAT path: {target_path}")


                if len(success_axes)>0 and len(failed_axes) == 0:
                    append_log("All axis parameters applied to TwinCAT")
                elif len(success_axes) > 0:
                    append_log(f"Successfully applied: {', '.join(success_axes)}")
                    append_log(f"Failed/skipped: {', '.join(failed_axes)}")
                else:
                    append_log("No axis parameters were successfully applied.")
                
            except Exception as e:
                append_log(f"[Error] {e}")
                append_log("Failed to apply trafo to TwinCAT node.")

        def apply_all_axis_to_twincat_with_matching():
            if not state.sysman:
                append_log("Please initialize the TwinCAT project first.")
                return
            if not opc_client:
                append_log("Please connect to OPC UA Client first.")
                return
            
            # get all available paths
            axis_paths_all = [
                path for path in available_paths
                if path.count("^") == 3 and path.split("^")[-1].lower().startswith(("axis_", "achse_", "ext_"))
            ]


            if not axis_paths_all:
                append_log("[Warning] No Axis/Achse paths found in available_paths.")
                return

            append_log(f"[Info] Found {len(axis_paths_all)} Axis/Achse nodes.")

            success = []
            failed = []

            # Pre-read all Kanal configurations once
            all_configs = read_all_kanal_configs(opc_client, kanal_inputs)
            if not all_configs:
                append_log("[Error] Failed to fetch Kanal configurations from OPC UA.")
                return

            for path in axis_paths_all:
                print(f"Processing {path}")
                try:
                    result = write_all_axis_param_to_twincat(state.sysman, path, all_configs)
                    if result:
                        success.append(path)
                    else:
                        failed.append(path)
                except Exception as e:
                    append_log(f"[Error] Exception while writing to {path}: {e}")
                    failed.append(path)

            # Output final statistics
            append_log(f"\n[Summary] Axis write completed.")
            append_log(f"Success: {len(success)}")
            append_log(f"Failed: {len(failed)}")

            if failed:
                for f in failed:
                    append_log(f"[Failed] {f}")
        
        def read_all_axis_from_twincat_with_matching(all_configs):
            if not state.sysman:
                append_log("TwinCAT is not initialized. Please initialize it first.")
                return all_configs

            if not opc_client:
                append_log("OPC UA client is not connected. Please connect first.")
                return all_configs

            axis_paths_all = [
                path for path in available_paths
                if path.count("^") == 3 and path.split("^")[-1].lower().startswith(("axis_", "achse_", "ext_"))
            ]

            if not axis_paths_all:
                append_log("[Warning] No Axis/Achse paths found.")
                return all_configs

            append_log(f"[Info] Found {len(axis_paths_all)} Axis/Achse nodes.")

            success = []
            failed = []

            for path in axis_paths_all:
                print(f"Processing {path}")
                try:
                    updated_config = read_all_axis_from_twincat(state.sysman, path, all_configs)
                    if updated_config:
                        all_configs = updated_config 
                        success.append(path)
                    else:
                        append_log(f"[Failed] Could not read from: {path}")
                        failed.append(path)
                except Exception as e:
                    append_log(f"[Error] Exception while reading from {path}: {e}")
                    failed.append(path)

            append_log("\n[Summary] Axis parameter reading completed.")
            append_log(f"Successful: {len(success)}")
            append_log(f"Failed: {len(failed)}")
            if failed:
                for f in failed:
                    append_log(f"[Failed] {f}")

            write_all_configs_to_opcua(opc_client, all_configs) 
            append_log("All axis configurations updated in OPC UA Server.")     

        def apply_one_axis_to_twincat():
            if not state.sysman:
                append_log("Please initialize the TwinCAT project first.")
                return
            if not opc_client:
                append_log("Please connect to OPC UA Client first.")
                return
            try:
                data = fetch_axis_json(opc_client)
                axis_lines = convert_trafo_lines(data.get("param_names", []), data.get("param_values", []))
                write_axis_param_to_twincat(state.sysman, cnc_path.value, axis_lines)
                append_log("Trafo parameters applied to TwinCAT.")

            except Exception as e:
                append_log(f"[Error] {e}")
                append_log("Failed to apply trafo to TwinCAT node.")

        ui.button("Connect OPC UA Client", on_click=connect_client, color='green')
        ui.button("Disconnect OPC UA Client", on_click=disconnect_client, color='red')
        ui.button("Write Trafo Parameters", on_click=apply_trafo_to_twincat, color='blue')
        ui.button("Write Trafo Parameters to All Kanal", on_click=apply_trafo_to_all_kanals, color='blue')
        ui.button("Write all Axis Parameters with Mapping", on_click=apply_all_axis_to_twincat_with_mapping, color='blue')
        ui.button("Write all Axis Parameters with Matching", on_click=apply_all_axis_to_twincat_with_matching, color='blue')
        ui.button("Write a Axis Parameters", on_click=apply_one_axis_to_twincat, color='blue')
        ui.button("Read Trafo Parameters from All Kanal", on_click=read_trafo_from_all_kanals, color='blue')
        ui.button("Read Axis Parameters from All Kanal", on_click=read_all_axis_from_twincat_with_matching, color='blue')

    async def one_click_full_apply():
        append_log("=== [Start] One-click CNC Init + Write ===")

        try:
            if not state.sysman:
                init_sysman()
                if not state.sysman:
                    append_log("Failed to initialize TwinCAT project.")
                    return

            if not opc_client:
                connect_client()
                if not opc_client:
                    append_log("Failed to connect OPC UA Client.")
                    return

            # CNC结构遍历（确保 available_paths 被更新）
            append_log("Browsing CNC structure...")
            # 这里自动选择结构并遍历，比如默认用 "CNC Configuration"
            structure_key = "CNC Configuration"
            keyword = structure_map[structure_key]
            root_node = state.sysman.LookupTreeItem(keyword)
            global available_paths
            available_paths = collect_paths(root_node, prefix=keyword)
            append_log(f"Found {len(available_paths)} nodes.")

            if not available_paths:
                append_log("[Abort] Failed to browse CNC structure.")
                return

            append_log("Writing Trafo to all Kanal paths...")
            apply_trafo_to_all_kanals()

            append_log("Writing Axis with automatic matching...")
            apply_all_axis_to_twincat_with_matching()

            append_log("=== [Done] All parameters applied ===")


            
        except Exception as e:
            append_log(f"[Error] {e}")

    def one_click_full_read():
        append_log("=== [Start] One-click Read ===")

        try:
            if not state.sysman:
                append_log("Please initialize the TwinCAT project first.")
                return

            if not opc_client:
                connect_client()
            if not opc_client:
                append_log("Failed to connect to OPC UA Client.")
                return

            append_log("Step 1: Fetching base configs from OPC UA...")


            append_log("Step 2: Reading Trafo from TwinCAT...")
            read_trafo_from_all_kanals(read_all_kanal_configs(opc_client, kanal_inputs))

            append_log("Step 3: Reading Axis from TwinCAT...")
            read_all_axis_from_twincat_with_matching(read_all_kanal_configs(opc_client, kanal_inputs))


        except Exception as e:
            append_log(f"[Error] Exception during full read: {e}")

    async def start_opcua_client_listener():
        nonlocal opc_client, opc_subscription_started
        loop = asyncio.get_running_loop()  # 👈 获取主线程中的 loop

        if not opc_client:
            opc_client = connect_opcua_client()
            if not opc_client:
                append_log("Failed to connect OPC UA Client.")
                return
            append_log("OPC UA Client connected.")

        try:
            # 👇 把 loop 显式传入
            subscription = opc_client.create_subscription(
                100,
                ConfigChangeHandler(one_click_full_apply, loop)
            )
            

            for kanal in kanal_inputs.keys():
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

    #ui.button("One-click CNC Init + Write", on_click=one_click_full_apply, color='primary').props('raised')
    #ui.button("One-click Read", on_click=one_click_full_read, color='primary').props('raised')
    #ui.button("Start OPC UA Listener", on_click=start_opcua_client_listener, color='purple')
    #ui.button("Stop OPC UA Listener", on_click=stop_opcua_client_listener, color='purple')
