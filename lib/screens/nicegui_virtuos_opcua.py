from opcua import Server, ua
from dotenv import load_dotenv
import os
import json
from lib.services import remote
from lib.services import Virtuos_tool, server
from nicegui import ui
import asyncio
from lib.screens.state import kanal_inputs
from lib.services.opcua_tool import ConfigChangeHandler
from lib.services.client import connect_opcua_client

# === UI 启动函数 ===
def show_virtuos_server():
    global vz_env, vz, opc_server_instance, initialized, opc_subscription, opc_subscription_started
    vz_env = None
    vz = None
    opc_server_instance = None
    initialized = False
    opc_subscription = None  
    opc_subscription_started = False

    log_area = ui.textarea("Log Output").props('readonly').style('width: 100%; height: 200px')

    listener_status_label = ui.label("Listener : Stopped").style('color: red; font-weight: bold;')


    kanal_bindings = {}  # 例如：{"Kanal_1": "[Block Diagram].[RobotController]"}

    with ui.column().style("width: 100%; max-width: 600px"):
        ui.label("Block → Kanal Mapping").style("font-weight: bold")

        for kanal in ["Kanal_1"]:  # 你也可以让用户动态加
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

                # 更新 Trafo
                trafo_names, trafo_values = Virtuos_tool.extract_trafo_param_list(vz, path)
                server.update_trafo_config(opc_server_instance, kanal, trafo_names, trafo_values)

                # 更新 Axis
                axis_params = Virtuos_tool.read_Value_Model_json(vz, path)[1]
                axis_names, axis_values = Virtuos_tool.extract_axis_param_list(axis_params)
                server.update_kanal_axis_config(opc_server_instance, kanal, "AxisConfigJSON", axis_names, axis_values)

                await append_log(f"[OK] {kanal} refreshed from block {path}")

            await append_log("[OK] All Kanals refreshed.")

        except Exception as e:
            await append_log(f"[EXCEPTION] {e}")

    async def write_back_all_from_opcua_server():
        global vz, opc_server_instance
        if not vz or not opc_server_instance:
            await append_log("[ERROR] Virtuos or OPC UA Server not initialized.")
            return

        for kanal, input_field in kanal_inputs.items():
            block_path = input_field.value.strip()
            kanal_data = server.read_kanal_data_from_server_instance(opc_server_instance, kanal)

            Virtuos_tool.write_params_to_virtuos(
                vz,
                block_path,
                kanal_data["trafo_names"],
                kanal_data["trafo_values"],
                kanal_data["axis_names"],
                kanal_data["axis_values"]
            )

            await append_log(f"[OK] {kanal} → Virtuos written from server variables.")

    async def start_opcua_server_listener():
        opc_client = None
        global opc_subscription, opc_subscription_started

        if opc_subscription_started:
            await append_log("[INFO] OPC UA listener already started.")
            return

        try:
            loop = asyncio.get_event_loop() 

            if not opc_client:
                opc_client = connect_opcua_client()
                if not opc_client:
                    await append_log("[ERROR] Failed to connect OPC UA client.")
                    return

            subscription = opc_client.create_subscription(
                100,
                ConfigChangeHandler(write_back_all_from_opcua_server, loop)
            )

            for kanal in kanal_inputs.keys():
                kanal_node = opc_client.get_objects_node().get_child([f"2:{kanal}"])
                for var_name in ["TrafoConfigJSON", "AxisConfigJSON"]:
                    var_node = kanal_node.get_child([f"2:{var_name}"])
                    subscription.subscribe_data_change(var_node)
                    await append_log(f"[LISTENING] {kanal}/{var_name}")
                    
            opc_subscription_started = True
            listener_status_label.text = "Listener : Active"
            listener_status_label.style('color: green; font-weight: bold;')
            await append_log("[OK] OPC UA Server listener active.")

        except Exception as e:
            await append_log(f"[Error] OPC UA Server Listener failed: {e}")
    
    async def stop_opcua_listener():
        global opc_subscription, opc_subscription_started
        if opc_subscription:
            opc_subscription.delete()
            opc_subscription = None
            listener_status_label.text = "Listener : Stopped"
            listener_status_label.style('color: red; font-weight: bold;')
            await append_log("[INFO] OPC UA listener stopped.")
        else:
            await append_log("[INFO] No active OPC UA listener.")


    ui.label("Virtuos → OPC UA Bridge").style("font-weight: bold; font-size: 20px;")
    ui.button("Connect to Existing Virtuos", on_click=connect_to_existing_virtuos, color='blue')
    ui.button("Read Data and Start OPC UA Server", on_click=read_and_start_multi_kanal_server, color='green')
    ui.button("Stop OPC UA Server", on_click=stop_opc, color='red')
    ui.button("Refresh All Parameters", on_click=refresh_all_on_server, color='orange')
    ui.button("Write Back All from OPC UA Server", on_click=write_back_all_from_opcua_server, color='purple')
    ui.button("Start OPC UA Server Listener", on_click=start_opcua_server_listener, color='teal')
    ui.button("Stop OPC UA Server Listener", on_click=stop_opcua_listener, color='grey')
    
    log_area
