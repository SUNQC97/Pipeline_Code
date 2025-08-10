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


    with ui.expansion("Block → Kanal Mapping", icon='link').style("width: 100%; max-width: 800px"):
        kanal_count = 1
        kanal_inputs.clear()
        kanal_inputs_list = []  # 存储 (kanal_name_field, path_input, dropdown)
        kanal_container = ui.element('div')

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

        controller_block_names = find_controller_blocks(block_map)
        if not controller_block_names:
            controller_block_names = ["<No Controller Found>"]
        
        def update_kanal_inputs():
            current_count = len(kanal_inputs_list)

            for i in range(current_count, kanal_count):
                kanal_id = f"Kanal_{i+1}"
                with kanal_container:
                    with ui.row():
                        kanal_name_field = ui.input(label="Kanal Name", value=kanal_id).props("readonly").style("width: 20%")

                        dropdown = ui.select(
                            options=controller_block_names,
                            label="Select Controller Block",
                            value=None
                        ).style("width: 40%")

                        path_input = ui.input(label="Block Path", value="").props("readonly").style("width: 40%")

                        # 不绑定事件（点击按钮统一处理）
                        kanal_inputs_list.append((kanal_name_field, path_input, dropdown))

            if kanal_count < current_count:
                for i in range(current_count - 1, kanal_count - 1, -1):
                    kanal_inputs_list[i][0].delete()
                    kanal_inputs_list[i][1].delete()
                    kanal_inputs_list[i][2].delete()
                    kanal_inputs_list.pop(i)

            # 先清空映射，稍后在 fill_all_paths 时更新
            kanal_inputs.clear()

        def on_kanal_count_change(e):
            nonlocal kanal_count
            kanal_count = int(e.value)
            update_kanal_inputs()

        def fill_all_paths():
            kanal_inputs.clear()
            for kanal_name_field, path_input, dropdown in kanal_inputs_list:
                kanal_name = kanal_name_field.value.strip()
                selected_block = dropdown.value

                if selected_block:
                    full_path = block_map.get(f"[{selected_block}]", block_map.get(selected_block, "Not Found"))
                    path_input.value = full_path
                    if full_path == "Not Found":
                        path_input.props("color=red")
                    else:
                        path_input.props("color=primary")
                else:
                    path_input.value = "Not Selected"
                    path_input.props("color=red")

                kanal_inputs[kanal_name] = path_input

            show_kanal_paths()

        ui.number("Number of Kanals", value=1, min=1, max=10, step=1, on_change=on_kanal_count_change).style("width: 50%")
        ui.button("Fill All Block Paths", on_click=fill_all_paths).props("color=primary").style("margin-top: 8px")
        # 搜索关键词输入框（默认是 Controller）
        search_keyword_input = ui.input("Search Keyword", value="Controller").style("width: 50%")

        def apply_search_keyword():
            keyword = search_keyword_input.value.strip()
            new_block_names = find_controller_blocks(block_map, keyword)
            if not new_block_names:
                new_block_names = ["<No Match>"]

            # 更新所有 dropdown 的选项
            for _, _, dropdown in kanal_inputs_list:
                dropdown.options = new_block_names
                dropdown.value = None  # 清空选中

        ui.button("Apply Search Keyword", on_click=apply_search_keyword).props("color=secondary").style("margin-bottom: 10px")
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