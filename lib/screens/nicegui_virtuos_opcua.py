from nicegui import ui
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from lib.services import Virtuos_tool, server
from dotenv import load_dotenv
import asyncio

def show_virtuos_server():
    global vz_env, vz, opc_server_instance, initialized
    vz_env = None
    vz = None
    opc_server_instance = None
    initialized = False
    log_area = ui.textarea("Log Output").props('readonly').style('width: 100%; height: 200px')
    controller_path_input = ui.input("RobotController Path", value="[Block Diagram].[RobotController]").style('width: 100%')

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

    async def read_and_start_server():
        global vz, opc_server_instance
        try:
            if not vz:
                await append_log("[ERROR] Virtuos is not initialized.")
                return

            path = controller_path_input.value.strip()
            param_names, param_values = Virtuos_tool.extract_trafo_param_list(vz, path)
            opc_server_instance = server.start_opc_server_with_trafo(param_names, param_values)
            if opc_server_instance is None:
                await append_log("[ERROR] Failed to start OPC UA Server.")
                return
            await append_log("[OK] OPC UA Server started with Trafo parameters.")

        except Exception as e:
            await append_log(f"[EXCEPTION] {e}")

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

    async def refresh_trafo_on_server():
        global vz, opc_server_instance
        try:
            if not vz:
                await append_log("[ERROR] Virtuos is not initialized.")
                return
            if not opc_server_instance:
                await append_log("[ERROR] OPC UA Server is not running.")
                return

            path = controller_path_input.value.strip()
            param_names, param_values = Virtuos_tool.extract_trafo_param_list(vz, path)
            server.update_trafo_config(opc_server_instance, param_names, param_values)
            await append_log("[OK] Trafo parameters refreshed on OPC UA Server.")

        except Exception as e:
            await append_log(f"[EXCEPTION] {e}")

    ui.label("Virtuos → OPC UA Bridge").style("font-weight: bold; font-size: 20px;")
    controller_path_input
    ui.button("Connect to Existing Virtuos", on_click=connect_to_existing_virtuos, color='blue')
    ui.button("Read Data and Start OPC UA Server", on_click=read_and_start_server, color='green')
    ui.button("Stop OPC UA Server", on_click=stop_opc, color='red')
    ui.button("Refresh Trafo Parameters", on_click=refresh_trafo_on_server, color='orange')
    log_area

