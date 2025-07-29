from opcua import Server, ua
from dotenv import load_dotenv
import os
import json
from lib.services import remote
from lib.services import Virtuos_tool, server
from nicegui import ui
import asyncio
from lib.screens.state import kanal_inputs

# === UI 启动函数 ===
def show_virtuos_server():
    global vz_env, vz, opc_server_instance, initialized
    vz_env = None
    vz = None
    opc_server_instance = None
    initialized = False

    log_area = ui.textarea("Log Output").props('readonly').style('width: 100%; height: 200px')
    kanal_bindings = {}  # 例如：{"Kanal_1": "[Block Diagram].[RobotController]"}

    with ui.column().style("width: 100%; max-width: 600px"):
        ui.label("Block → Kanal Mapping").style("font-weight: bold")

        for kanal in ["Kanal_1", "Kanal_2"]:  # 你也可以让用户动态加
            block_input = ui.input(f"Block for {kanal}", value=f"[Block Diagram].[RobotController]").style("width: 100%")
            kanal_inputs[kanal] = block_input

    async def append_log(text):
        log_area.value += text + '\n'
        log_area.update()
        await asyncio.sleep(0.05)

    async def connect_to_existing_virtuos():
        global initialized, vz_env, vz
        try:
            if not initialized:
                load_dotenv()
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

    async def read_and_start_multi_kanal_server():
        global vz, opc_server_instance

        kanal_data_dict = {}

        for kanal, input_field in kanal_inputs.items():
            block_path = input_field.value.strip()

            trafo_names, trafo_values = Virtuos_tool.extract_trafo_param_list(vz, block_path)
            axis_params = Virtuos_tool.read_Value_Model_json(vz, block_path)[1]
            axis_names, axis_values = Virtuos_tool.extract_axis_param_list(axis_params)

            kanal_data_dict[kanal] = {
                "trafo_names": trafo_names,
                "trafo_values": trafo_values,
                "axis_names": axis_names,
                "axis_values": axis_values,
            }

        opc_server_instance = server.start_opc_server_multi_kanal(kanal_data_dict)
        if opc_server_instance:
            await append_log("[OK] Multi-Kanal OPC UA Server started.")
        else:
            await append_log("[ERROR] Failed to start OPC UA server.")


    async def stop_opc():
        global opc_server_instance
        try:
            if opc_server_instance:
                server.stop_opc_server(opc_server_instance)
                await append_log("[OK] OPC UA Server stopped.")
                opc_server_instance = None
            else:
                await append_log("[INFO] No running OPC UA server.")
        except Exception as e:
            await append_log(f"[EXCEPTION] Failed to stop server: {e}")

    async def refresh_all_on_server():
        global vz, opc_server_instance
        try:
            if not vz:
                await append_log("[ERROR] Virtuos is not initialized.")
                return
            if not opc_server_instance:
                await append_log("[ERROR] OPC UA Server is not running.")
                return

            for kanal, input_field in kanal_inputs.items():
                path = input_field.value.strip()

                trafo_names, trafo_values = Virtuos_tool.extract_trafo_param_list(vz, path)
                server.update_trafo_config(opc_server_instance, kanal, trafo_names, trafo_values)

                axis_params = Virtuos_tool.read_Value_Model_json(vz, path)[1]
                axis_names, axis_values = Virtuos_tool.extract_axis_param_list(axis_params)
                server.update_kanal_axis_config(opc_server_instance, kanal, axis_names, axis_values)

                await append_log(f"[OK] {kanal} refreshed from block {path}")

            await append_log("[OK] All Kanals refreshed.")

        except Exception as e:
            await append_log(f"[EXCEPTION] {e}")


    ui.label("Virtuos → OPC UA Bridge").style("font-weight: bold; font-size: 20px;")
    
    ui.button("Connect to Existing Virtuos", on_click=connect_to_existing_virtuos, color='blue')
    ui.button("Read Data and Start OPC UA Server", on_click=read_and_start_multi_kanal_server, color='green')
    ui.button("Stop OPC UA Server", on_click=stop_opc, color='red')
    ui.button("Refresh All Parameters", on_click=refresh_all_on_server, color='orange')
    log_area
