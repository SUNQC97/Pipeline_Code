from dotenv import load_dotenv
import os
import json
from lib.services import remote
from lib.services import Virtuos_tool
from nicegui import ui
import asyncio

skip_write_back_in_virtuos = None

def show_virtuos_robot():
    global vz_env, vz, initialized
    vz_env = None
    vz = None
    initialized = False

    param_data = {
        "trafo_names": [],
        "trafo_values": [],
        "axis_names": [],
        "axis_values": []
    }
    
    # Store UI input elements for parameter editing
    trafo_inputs = []
    axis_inputs = []

    async def append_log(text):
        log_area.value += text + '\n'
        log_area.update()
        await asyncio.sleep(0.05)

    log_area = ui.textarea("Log Output").props('readonly').style('width: 100%; height: 200px')

    async def connect_to_existing_virtuos_before_start():
        global initialized, vz_env, vz
        try:
            if initialized:
                await append_log("[INFO] Virtuos already initialized.")
                return

            vz_env = Virtuos_tool.VirtuosEnv()
            vz = vz_env.connect_to_virtuos()
            if vz:
                initialized = True
                await append_log("[OK] Connected to Virtuos.")
            else:
                await append_log("[ERROR] Failed to connect to Virtuos.")

        except Exception as e:
            await append_log(f"[EXCEPTION] Failed to connect to Virtuos: {e}")

    async def connect_to_existing_virtuos_after_start():
        global initialized, vz_env, vz
        try:
            if not initialized:
                dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
                load_dotenv(dotenv_path)
                project_path = os.getenv("project_path")
                vz_env = Virtuos_tool.VirtuosEnv()
                vz = vz_env.vz
                vz.virtuosDLL()
                vz.corbaInfo()
                vz.startConnectionCorba()
                if vz.isOpen() == vz.V_SUCCD:
                    await append_log("[OK] Connected to already open Virtuos project.")
                else:
                    status = vz.getProject(project_path)
                    if status == vz.V_SUCCD:
                        await append_log("[OK] Project loaded and connected.")
                    else:
                        await append_log("[ERROR] No open project and failed to load.")
                        return
                initialized = True
                
            else:
                await append_log("[INFO] Already initialized.")
        except Exception as e:
            await append_log(f"[EXCEPTION] Connection failed: {e}")

    with ui.expansion("Select Block in Virtuos",icon="link").style("width: 100%; max-width: 800px"):
        
        block_map = Virtuos_tool.load_block_map()

        def find_controller_blocks(block_map: dict, keyword: str = "Controller") -> list:
            seen = set()
            filtered = []
            for name in block_map:
                plain_name = name.strip('[]')
                if keyword.lower() in plain_name.lower() and plain_name not in seen:
                    seen.add(plain_name)
                    filtered.append(plain_name)
            return sorted(filtered)

        controller_block_names = find_controller_blocks(block_map, "Controller")

        if not controller_block_names:
            controller_block_names = ["<No Controller Found>"]

        search_keyword_input = ui.input("Search Keyword", value="Controller").style("width: 50%")

        def apply_search_keyword():
            keyword = search_keyword_input.value.strip()
            new_block_names = find_controller_blocks(block_map, keyword)
            if not new_block_names:
                new_block_names = ["<No Match>"]

        ui.button("Apply Search Keyword", on_click=apply_search_keyword).props("color=primary").style("margin-top: 8px")

        block_select = ui.select(controller_block_names, label="Select Block").style("width: 100%")
        async def show_block_path():
            block_name = block_select.value
            if not block_name or block_name.startswith("<"):
                await append_log("[WARN] Please select a valid block name.")
                return
            block_addr = block_map.get(block_name)
            if not block_addr:
                await append_log(f"[ERROR] Block '{block_name}' not found in map.")
                return
            await append_log(f"[INFO] Block: {block_name} Path: {block_addr}")

        ui.button("Show Block Path", on_click=show_block_path).props("color=primary").style("margin-top: 8px")

    with ui.row():
        ui.label("Selected Block:").style("font-weight: bold;")
        selected_block_label = ui.label(block_select.value or "")
        ui.label("Path:").style("font-weight: bold;")
        selected_path_label = ui.label(block_map.get(block_select.value, ""))

    def update_selected_block_info():
        block_name = block_select.value
        selected_block_label.text = block_name or ""
        selected_path_label.text = block_map.get(block_name, "")

    block_select.on("update:model-value", lambda e: update_selected_block_info())

    # Create parameter display area
    param_container = ui.column().style("width: 100%; max-width: 800px; margin-top: 20px")

    async def update_param_display():
        nonlocal trafo_inputs, axis_inputs
        param_container.clear()
        trafo_inputs = []
        axis_inputs = []
        
        with param_container:
            ui.label("Robot Parameters").classes("text-2xl font-bold mb-4")
            
            # Display Trafo parameters
            if param_data["trafo_names"]:
                with ui.expansion("Trafo Parameters", value=True).classes("w-full mb-4"):
                    for name, value in zip(param_data["trafo_names"], param_data["trafo_values"]):
                        with ui.row().classes("w-full items-center mb-2"):
                            ui.label(name).classes("w-64 font-medium")
                            input_field = ui.input(value=str(value)).props("outlined dense").classes("flex-1")
                            trafo_inputs.append(input_field)
            
            # Display Axis parameters
            if param_data["axis_names"]:
                with ui.expansion("Axis Parameters", value=True).classes("w-full mb-4"):
                    for name, value in zip(param_data["axis_names"], param_data["axis_values"]):
                        with ui.row().classes("w-full items-center mb-2"):
                            ui.label(name).classes("w-64 font-medium")
                            input_field = ui.input(value=str(value)).props("outlined dense").classes("flex-1")
                            axis_inputs.append(input_field)
            
            # Add Write Parameters button if parameters are loaded
            if param_data["trafo_names"] or param_data["axis_names"]:
                with ui.row().classes("w-full justify-center mt-4"):
                    ui.button("Write Parameters to Virtuos", on_click=write_all_param_to_block).props("color=positive size=lg")

    async def read_all_param_from_block():
        block_path = selected_path_label.text

        try:
            trafo_names, trafo_values = Virtuos_tool.extract_trafo_param_list(vz, block_path)
            axis_params = Virtuos_tool.read_Value_Model_json(vz, block_path)[1]
            axis_names, axis_values = Virtuos_tool.extract_axis_param_list(axis_params)
            
            param_data["trafo_names"] = trafo_names
            param_data["trafo_values"] = trafo_values
            param_data["axis_names"] = axis_names
            param_data["axis_values"] = axis_values

            await append_log(f"[OK] Read all parameters from block '{block_path}':")
            await append_log(f"Trafo parameters: {len(trafo_names)}")
            await append_log(f"Axis parameters: {len(axis_names)}")

            await update_param_display()
            
        except Exception as e:
            await append_log(f"[ERROR] Failed to read parameters from block '{block_path}': {e}")

    async def write_all_param_to_block():
        """Collect parameter values from GUI inputs and write to Virtuos"""
        if not initialized or not vz:
            await append_log("[ERROR] Not connected to Virtuos. Please connect first.")
            return

        block_path = selected_path_label.text
        if not block_path:
            await append_log("[ERROR] No block selected.")
            return

        try:
            # Collect modified trafo values from GUI inputs (keep as strings)
            modified_trafo_values = []
            for i, input_field in enumerate(trafo_inputs):
                # Just use the input value directly - Virtuos can handle expressions like PI/180
                value = input_field.value.strip()
                modified_trafo_values.append(value)

            # Collect modified axis values from GUI inputs (keep as strings)
            modified_axis_values = []
            for i, input_field in enumerate(axis_inputs):
                # Just use the input value directly - Virtuos can handle expressions like PI/180
                value = input_field.value.strip()
                modified_axis_values.append(value)

            await append_log(f"[INFO] Writing parameters to Virtuos block '{block_path}'...")
            
            # Use the provided write function
            Virtuos_tool.write_params_to_virtuos(
                vz, 
                block_path,
                param_data["trafo_names"], 
                modified_trafo_values,
                param_data["axis_names"], 
                modified_axis_values
            )
            
            await append_log(f"[OK] Successfully wrote all parameters to Virtuos:")
            await append_log(f"    Trafo parameters: {len(param_data['trafo_names'])}")
            await append_log(f"    Axis parameters: {len(param_data['axis_names'])}")

        except Exception as e:
            await append_log(f"[ERROR] Failed to write parameters to block '{block_path}': {e}")

    ui.button("Read and Display Parameters", on_click=read_all_param_from_block).props("color=primary").style("margin-top: 8px")
    ui.button("Connect to Virtuos (Before Start)", on_click=connect_to_existing_virtuos_before_start).props("color=secondary").style("margin-top: 8px; margin-left: 16px")
    ui.button("Connect to Virtuos (After Start)", on_click=connect_to_existing_virtuos_after_start).props("color=secondary").style("margin-top: 8px; margin-left: 16px")