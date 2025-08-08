from dotenv import load_dotenv
import os
import json
from lib.services import remote
from lib.services import Virtuos_tool
from nicegui import ui
import asyncio
from lib.screens.state import kanal_inputs

skip_write_back_in_virtuos = None

def show_virtuos_server():
    global vz_env, vz, initialized
    vz_env = None
    vz = None
    initialized = False

    def show_kanal_paths():
        kanal_paths_container.clear()
        with kanal_paths_container:
            for kanal_name, path_input in kanal_inputs.items():
                ui.label(f"{kanal_name}: → {path_input.value}").style("color: #333; padding: 2px 0")
                
    kanal_paths_container = ui.column().style("margin-top: 10px")

    log_area = ui.textarea("Log Output").props('readonly').style('width: 100%; height: 200px')

    with ui.expansion("Block → Kanal Mapping", icon='link').style("width: 100%; max-width: 600px"):
        kanal_count = 1
        kanal_inputs.clear()
        kanal_inputs_list = []  # 使用列表存储 (kanal_name_input, path_input)
        kanal_container = ui.element('div')

        def update_kanal_inputs():
            current_count = len(kanal_inputs_list)

            # 增加输入框
            for i in range(current_count, kanal_count):
                with kanal_container:
                    with ui.row():
                        kanal_name_input = ui.input(f"Kanal Name {i+1}", value=f"RobotController").style("width: 60%")
                        path_input = ui.input(f"Block Path {i+1}", value="").props("readonly").style("width: 60%")
                        kanal_inputs_list.append((kanal_name_input, path_input))

            # 删除多余的输入框（从 UI 和列表中都删）
            if kanal_count < current_count:
                for i in range(current_count - 1, kanal_count - 1, -1):
                    kanal_inputs_list[i][0].delete()
                    kanal_inputs_list[i][1].delete()
                    kanal_inputs_list.pop(i)

            kanal_inputs.clear()
            for i, (kanal_name_input, path_input) in enumerate(kanal_inputs_list, start=1):
                kanal_id = f"Kanal_{i}"
                kanal_inputs[kanal_id] = path_input
            show_kanal_paths()

        def on_kanal_count_change(e):
            nonlocal kanal_count
            kanal_count = int(e.value)
            update_kanal_inputs()

        def get_all_paths():
            block_map = Virtuos_tool.load_block_map()
            for kanal_name_input, path_input in kanal_inputs_list:
                block_name = kanal_name_input.value.strip()
                full_path = Virtuos_tool.get_block_path(block_name, block_map)
                if full_path == "Not Found":
                    path_input.props("color=red")
                    path_input.value = "Not Found"
                else:
                    path_input.props("color=primary")
                    path_input.value = full_path
            show_kanal_paths()

        ui.number("Number of Kanals", value=1, min=1, max=10, step=1, on_change=on_kanal_count_change).style("width: 50%")
        ui.button("GET ALL PATHS", on_click=get_all_paths).props("color=primary").style("margin-top: 8px")
        update_kanal_inputs()

    async def append_log(text):
        log_area.value += text + '\n'
        log_area.update()
        await asyncio.sleep(0.05)

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

    ui.label("Virtuos Robot Block Mapping").style("font-weight: bold; font-size: 20px;")
    kanal_paths_container
    log_area
    ui.button("Connect to Existing Virtuos(before start)", on_click=connect_to_existing_virtuos_before_start, color='blue')
    ui.button("Connect to Existing Virtuos(after start)", on_click=connect_to_existing_virtuos_after_start, color='blue')