import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from nicegui import ui
import os
from lib.screens import state
from lib.services.TwinCAT_interface import (
    init_project,
    export_cnc_node,
    import_cnc_node,
    handle_configuration,
    load_config,
    collect_paths,
    get_export_path,
    get_import_path,
    add_child_node
)

# === Configuration Mapping ===
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


# === Global State ===
sysman = None
uploaded_import_path = None  # Path of uploaded XML/SDF file
path_dropdown = None


# === Load config from .env or use default ===
config = load_config()
TWINCAT_PROJECT_PATH = config["TWINCAT_PROJECT_PATH"]
AMS_NET_ID = config["AMS_NET_ID"]
EXPORT_BASE_DIR = config["EXPORT_BASE_DIR"]
IMPORT_BASE_DIR = config["IMPORT_BASE_DIR"]

# === UI Input Fields ===
vs_input = ui.input("TwinCAT Project Path").props('outlined').style('width: 100%')
ams_input = ui.input("AMS Net ID").props('outlined').style('width: 100%')
cnc_path = ui.input("CNC Node Path").props('outlined').style('width: 100%')
export_input = ui.input("Export File Path").props('outlined').style('width: 100%')
import_input = ui.input("Import File Path").props('outlined').style('width: 100%')

# === Set Default Values ===
vs_input.value = TWINCAT_PROJECT_PATH
ams_input.value = AMS_NET_ID
export_input.value = EXPORT_BASE_DIR + "\\"
import_input.value = IMPORT_BASE_DIR + "\\"

# === Logging Area ===
log = ui.textarea(label='Log').props('readonly').style('width: 100%; height: 200px')

def append_log(text: str):
    log.value += text + '\n'

# === TwinCAT Project Initialization ===
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

# === Export ===
def do_export():
    if not sysman:
        append_log("Please initialize the project first.")
        return
    export_cnc_node(sysman, cnc_path.value, export_input.value)
    append_log(f"Exported to {export_input.value}")

# === Import ===
def do_import():
    if not sysman:
        append_log("Please initialize the project first.")
        return
    import_path = uploaded_import_path or import_input.value
    import_cnc_node(sysman, cnc_path.value, import_path)
    append_log(f"Imported from {import_path}")

# === Activate Configuration ===
def activate_config():
    if not sysman:
        append_log("Please initialize the project first.")
        return
    handle_configuration(sysman)
    append_log("Configuration activated.")

# === UI Header ===
ui.label("TwinCAT Automation Tool").style("font-weight: bold; font-size: 20px;")
ui.button("Initialize TwinCAT Project", on_click=init_sysman, color='primary')
ui.button("Export CNC Node to XML", on_click=do_export)
ui.button("Import CNC Node from XML", on_click=do_import)
ui.button("Activate TwinCAT Configuration", on_click=activate_config)
ui.separator()
log
ui.separator()

# === Update Path Based on Selected CNC Node ===
def update_export_import_path():
    export_input.value = get_export_path(EXPORT_BASE_DIR, cnc_path.value)
    import_input.value = get_import_path(IMPORT_BASE_DIR, cnc_path.value)
    append_log(f"Updated paths:\nExport → {export_input.value}\nImport → {import_input.value}")

# === Upload Section ===
ui.label("Upload XML/SDF File").style("margin-top: 20px; font-weight: bold;")
upload_label = ui.label("")
upload_area = ui.column()

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
    global uploaded_import_path
    save_dir = IMPORT_BASE_DIR  
    os.makedirs(save_dir, exist_ok=True)
    uploaded_import_path = os.path.join(save_dir, file.name)
    with open(uploaded_import_path, "wb") as f:
        f.write(file.content.read())
    import_input.value = uploaded_import_path
    upload_label.text = f"Saved to: {uploaded_import_path}"
    append_log(f"Uploaded and saved: {uploaded_import_path}")
    refresh_upload()


refresh_upload()
upload_label

# === Browse TwinCAT Structure and Select Node ===
ui.separator()
with ui.column():
    ui.label("Browse TwinCAT Configuration Structure").style("font-weight: bold; font-size: 16px;")

    structure_dropdown = ui.select(
        label="Select a TwinCAT structure to browse",
        options=list(structure_map.keys())
    ).props('outlined').style('width: 100%')

    browse_button = ui.button("Browse Structure", color='secondary')
    path_selection_area = ui.column()  # Will contain path dropdown and confirm button

# === Browse Structure Logic ===
def browse_selected_structure():
    global path_dropdown
    if not sysman:
        append_log("Please initialize the project first.")
        return

    selected = structure_dropdown.value
    if not selected:
        append_log("Please select a structure.")
        return

    keyword = structure_map[selected]
    try:
        root_node = sysman.LookupTreeItem(keyword)
        append_log(f"Browsing structure: {selected} ({keyword})")
        paths = collect_paths(root_node, prefix=keyword)
        append_log(f"Found {len(paths)} nodes.")

        # Show path dropdown and confirm button
        path_selection_area.clear()
        with path_selection_area:
            path_dropdown = ui.select(label="Select Node Path", options=paths).style("width: 100%")

            def confirm_node_path():
                selected_path = path_dropdown.value
                if selected_path:
                    cnc_path.value = selected_path
                    append_log(f"Selected path set to: {selected_path}")
                    update_export_import_path()

            ui.button("Confirm Selected Path", on_click=confirm_node_path, color='primary')
            
            def confirm_Parent_path():
                selected_path = path_dropdown.value
                if selected_path:
                    parent_path.value = selected_path  
                    append_log(f"[Parent Path] set to: {selected_path}")

            ui.button("Confirm Selected Parent Path", on_click=confirm_Parent_path, color='primary')

    except Exception as e:
        append_log(f"[Error]: {e}")


browse_button.on("click", browse_selected_structure)

# add a Child Node Section
# === Subtype Mapping for Node Type ===
type_map = {
    "Axis": 401,   
    "Kanal": 403
}

ui.separator()
ui.label("Add Axis or Kanal").style("font-weight: bold; font-size: 16px; margin-top: 20px;")

child_name_input = ui.input("Node Name").props("outlined").style("width: 100%")
parent_path = ui.input("Parent Path").props('outlined').style('width: 100%')

type_dropdown = ui.select(
    label="Node Type",
    options=["Axis", "Kanal"]
).props("outlined").style("width: 100%")

def do_add_fixed_type_child():
    if not sysman:
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
        result = add_child_node(sysman, parent_path.value, name, subtype)
        if result:
            append_log(f"Added {type_selected} '{name}' (Subtype {subtype}) under '{parent_path.value}'")
        else:
            append_log("Failed to add node.")
    except Exception as e:
        append_log(f"Error during add: {e}")


ui.button("Add Node", on_click=do_add_fixed_type_child, color='accent')


# === Run UI Application ===
ui.run(native=True)
