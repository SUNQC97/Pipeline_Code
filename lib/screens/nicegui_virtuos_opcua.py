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
from lib.services.client import connect_opcua_client, read_audit_info, format_audit_source
from lib.utils.save_to_file import save_opcua_data_to_file
from datetime import datetime

skip_write_back_in_virtuos = None

def show_virtuos_server():
    global vz_env, vz, opc_server_instance, initialized, opc_client
    vz_env = None
    vz = None
    opc_server_instance = None
    initialized = False
    opc_subscription_started = False
    opc_client = None

    def show_kanal_paths():
        kanal_paths_container.clear()
        with kanal_paths_container:
            for kanal_name, path_input in kanal_inputs.items():
                ui.label(f"{kanal_name}: → {path_input.value}").style("color: #333; padding: 2px 0")
                
    kanal_paths_container = ui.column().style("margin-top: 10px")

    log_area = ui.textarea("Log Output").props('readonly').style('width: 100%; height: 200px')
    listener_status_label = ui.label("Listener : Stopped").style('color: red; font-weight: bold;')

    modifier_input = ui.input(
        label="Modifier Name",
        value="User1",
        placeholder="Enter your name or ID for audit trail"
    ).style("width: 200px; margin-bottom: 10px")


    pending_panel = ui.column().style('gap:8px; width:100%')

    def get_current_modifier():
        return modifier_input.value.strip() or "Unknown_User"

    with ui.expansion("Block → Kanal Mapping", icon='link').style("width: 100%; max-width: 800px"):
        kanal_count = 1
        kanal_inputs.clear()
        kanal_inputs_list = [] 
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

        controller_block_names = find_controller_blocks(block_map, "Controller")

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
                dropdown.update()
        
        ui.button("Apply Search Keyword", on_click=apply_search_keyword).props("color=primary").style("margin-top: 8px")
        update_kanal_inputs()

    async def append_log(text):
        log_area.value += text + '\n'
        log_area.update()
        await asyncio.sleep(0.05)

    async def check_virtuos_and_opc_server():
        if not vz:
            await append_log("[ERROR] Virtuos is not initialized.")
            return False
        if not opc_server_instance:
            await append_log("[ERROR] OPC UA Server is not running.")
            return False
        return True

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

    async def refresh_all_on_server():
        global vz, opc_server_instance, skip_write_back_in_virtuos

        skip_write_back_in_virtuos = "skip_once"
        
        async def clear_skip_flag():
            await asyncio.sleep(2)
            global skip_write_back_in_virtuos
            if skip_write_back_in_virtuos == "skip_once":
                skip_write_back_in_virtuos = None
                await append_log("[INFO] Resetting skip flag after 2 seconds.")
        asyncio.create_task(clear_skip_flag())

        try:
            if not vz:
                await append_log("[ERROR] Virtuos is not initialized.")
                return
            if not opc_server_instance:
                await append_log("[ERROR] OPC UA Server is not running.")
                return

            modifier_name = get_current_modifier()

            for kanal, input_field in kanal_inputs.items():
                path = input_field.value.strip()

                trafo_names, trafo_values = Virtuos_tool.extract_trafo_param_list(vz, path)
                server.update_trafo_config(opc_server_instance, kanal, trafo_names, trafo_values)

                axis_params = Virtuos_tool.read_Value_Model_json(vz, path)[1]
                axis_names, axis_values = Virtuos_tool.extract_axis_param_list(axis_params)
                server.update_kanal_axis_config(opc_server_instance, kanal, "AxisConfigJSON", axis_names, axis_values)
                
                server.update_audit_info(
                    opc_server_instance, 
                    modifier_name, 
                    "Refresh_TrafoConfigJSON & AxisConfigJSON", 
                    "Refresh_byVirtuos"
                )
                await append_log(f"[OK] {kanal} refreshed from block {path}")
            
            await append_log("[OK] All Kanals refreshed.")

        except Exception as e:
            await append_log(f"[EXCEPTION] {e}")

    async def write_back_all_from_opcua_server():
        global vz, opc_server_instance, skip_write_back_in_virtuos
        
        if skip_write_back_in_virtuos == "skip_once":
            skip_write_back_in_virtuos = None
            await append_log("[INFO] Skipping write back to Virtuos as per configuration.")
            return

        if not vz or not opc_server_instance:
            await append_log("[ERROR] Virtuos or OPC UA Server not initialized.")
            return

        try:
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

            save_opcua_data(opc_server_instance)

        except Exception as e:
            await append_log(f"[EXCEPTION] Failed to write back from OPC UA Server: {e}")

        finally:
            skip_write_back_in_virtuos = None        

    async def read_and_start_multi_kanal_server():
        global vz, opc_server_instance, skip_write_back_in_virtuos

        skip_write_back_in_virtuos = "skip_once"

        kanal_data_dict = {}


        try:
            modifier_name = get_current_modifier()

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
                                # 初始化审计信息
                server.update_audit_info(
                    opc_server_instance, 
                    modifier_name, 
                    "Server_Initialization_Virtuos", 
                    "Start_OPC_Server_Virtuos"
                )
            else:
                await append_log("[ERROR] Failed to start OPC UA server.")
            
            # save the initial data to file
            save_opcua_data(opc_server_instance)
        except Exception as e:
            await append_log(f"[EXCEPTION] Failed to start OPC UA server: {e}")                            
    
    async def stop_opc():
        global opc_server_instance
        try:
            if opc_server_instance:
                
                modifier_name = get_current_modifier()
                
                # 记录停止操作的审计信息
                server.update_audit_info(
                    opc_server_instance, 
                    modifier_name, 
                    "Server_Termination", 
                    "Stop_OPC_Server"
                )
                
                server.stop_opc_server(opc_server_instance)
                await append_log("[OK] OPC UA Server stopped.")
                opc_server_instance = None
            else:
                await append_log("[INFO] No running OPC UA server.")
        except Exception as e:
            await append_log(f"[EXCEPTION] Failed to stop server: {e}")

        # Start OPC UA Client listener
    
    PENDING_CHANGES = {}



    async def confirming_on_change():
        global skip_write_back_in_TwinCAT
        if skip_write_back_in_TwinCAT == "skip_once":
            skip_write_back_in_TwinCAT = None
            append_log("[INFO] Skipping write back to TwinCAT due to previous operation.")
            return

        # read audit info
        audit_info = read_audit_info(opc_client)
        
        dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
        load_dotenv(dotenv_path)
        opc_host = os.getenv("SERVER_IP")
        opc_port = os.getenv("SERVER_PORT")

        #source = f"OPC UA {opc_host}:{opc_port}"
        base_source = f"OPC UA {opc_host}:{opc_port}"
        source = format_audit_source(base_source, audit_info)

        # add log
        if audit_info and audit_info.get('modifier') and audit_info.get('modifier') != 'Unknown':
            append_log(f"[AUDIT] Found modifier: {audit_info.get('modifier')}")
        else:
            append_log("[AUDIT] No audit info or unknown modifier")
            
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        change_id = f'change:{ts}'

        old = PENDING_CHANGES.get(change_id)
        if old and 'row' in old:
            try:
                old['row'].delete()
            except:
                pass


        with pending_panel:
            row = ui.row().style(
                'align-items:center; gap:10px; border:1px solid #ddd; '
                'padding:8px; border-radius:8px; width:100%'
            )
            with row:
                # 时间信息
                ui.label(f'Time: {ts}').style('font-weight:bold; flex-shrink:0')
                
                # 审计信息 - 占用剩余空间
                if audit_info and audit_info.get('modifier') and audit_info.get('modifier') != 'Unknown':
                    ui.label(f'Source: {source}').style('color: blue; font-weight: bold; flex-grow:1')
                else:
                    ui.label(f'Source: {source}').style('color: gray; flex-grow:1')

                # 按钮组 - 放在同一行
                with ui.row().style('gap: 8px; flex-shrink:0'):
                    async def do_import():
                        modifier_info = f" by {audit_info.get('modifier', 'Unknown')}" if audit_info else ""
                        append_log(f'[CONFIRM] Import {change_id}{modifier_info}...')
                        await write_back_all_from_opcua_server()
                        append_log(f'[OK] Applied {change_id}')
                        PENDING_CHANGES.pop(change_id, None)
                        row.delete()

                    def do_ignore():
                        modifier_info = f" by {audit_info.get('modifier', 'Unknown')}" if audit_info else ""
                        append_log(f'[INFO] Ignore {change_id}{modifier_info}')
                        PENDING_CHANGES.pop(change_id, None)
                        row.delete()

                    ui.button('IMPORT', on_click=do_import, color='green').style('min-width: 80px')
                    ui.button('IGNORE', on_click=do_ignore, color='red').style('min-width: 80px')

        PENDING_CHANGES[change_id] = {
            'id': change_id,
            'time': ts,
            'source': source,
            'row': row
        }

    async def start_opcua_server_listener():
        global opc_client
        nonlocal opc_subscription_started
        if opc_subscription_started:
            await append_log("[INFO] OPC UA listener already started.")
            return
        try:
            loop = asyncio.get_event_loop()
            opc_client = connect_opcua_client()
            if not opc_client:
                await append_log("[ERROR] Failed to connect OPC UA client.")
                return
            opc_subscription = opc_client.create_subscription(
                100,
                ConfigChangeHandler(callback=confirming_on_change, loop=asyncio.get_running_loop())
            )
            for kanal in kanal_inputs.keys():
                kanal_node = opc_client.get_objects_node().get_child([f"2:{kanal}"])
                for var_name in ["TrafoConfigJSON", "AxisConfigJSON"]:
                    var_node = kanal_node.get_child([f"2:{var_name}"])
                    opc_subscription.subscribe_data_change(var_node)
                    await append_log(f"[LISTENING] {kanal}/{var_name}")
            opc_subscription_started = True
            listener_status_label.text = "Listener : Active"
            listener_status_label.style('color: green; font-weight: bold;')
            await append_log("[OK] OPC UA Server listener active.")
        except Exception as e:
            await append_log(f"[Error] OPC UA Server Listener failed: {e}")

    async def stop_opcua_listener():
        nonlocal opc_subscription_started
        if opc_subscription_started:
            try:
                opc_subscription_started.delete()
                await append_log("[INFO] OPC UA listener stopped.")
            except Exception as e:
                await append_log(f"[EXCEPTION] Failed to delete subscription: {e}")
            finally:
                opc_subscription_started = False
                listener_status_label.text = "Listener : Stopped"
                listener_status_label.style('color: red; font-weight: bold;')
        else:
            await append_log("[INFO] No active OPC UA listener.")
    
    def save_opcua_data(opc_server_instance):
        
        kanal_data_dict = server.read_all_kanal_data_from_server_instance(opc_server_instance)
        save_opcua_data_to_file(kanal_data_dict)

    # 添加手动更新审计信息的功能
    async def manual_update_audit():
        if not opc_server_instance:
            await append_log("[ERROR] OPC UA Server is not running.")
            return
            
        modifier_name = get_current_modifier()
        server.update_audit_info(
            opc_server_instance, 
            modifier_name, 
            "Manual_Update", 
            "Manual_Audit_Update"
        )
        await append_log(f"[OK] Audit info manually updated by {modifier_name}")

    ui.label("Virtuos → OPC UA Bridge").style("font-weight: bold; font-size: 20px;")
    
    # 审计信息输入和状态显示
    with ui.row().style("margin-bottom: 10px; gap: 12px; align-items: end"):
        modifier_input
        ui.button("Update Audit Info", on_click=manual_update_audit, color='orange').style("height: 56px")
        listener_status_label

    ui.label("Virtuos → OPC UA Bridge").style("font-weight: bold; font-size: 20px;")
    with ui.row().style("margin-bottom: 10px"):
        listener_status_label
    ui.button("Connect to Existing Virtuos(before start)", on_click=connect_to_existing_virtuos_before_start, color='blue')
    ui.button("Connect to Existing Virtuos(after start)", on_click=connect_to_existing_virtuos_after_start, color='cyan')
    ui.button("Read Data and Start OPC UA Server", on_click=read_and_start_multi_kanal_server, color='green')
    ui.button("Stop OPC UA Server", on_click=stop_opc, color='red')
    ui.button("Refresh All on Virtuos Server", on_click=refresh_all_on_server, color='purple')
    ui.button("Write Back All from OPC UA Server", on_click=write_back_all_from_opcua_server, color='orange')
    ui.button("Start OPC UA Server Listener", on_click=start_opcua_server_listener, color='teal')
    ui.button("Stop OPC UA Server Listener", on_click=stop_opcua_listener, color='grey')
    kanal_paths_container
    log_area
    
    
    ui.label("Pending Changes").style("font-weight: bold; font-size: 16px; margin-top: 16px")
    pending_panel