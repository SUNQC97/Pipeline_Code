import os
import json
from pathlib import Path
from nicegui import ui
from dotenv import load_dotenv
from lib.services.twincat_manager import TwinCATManager
import asyncio
from lib.services.opcua_tool import ConfigChangeHandler
from lib.screens import state
from lib.services.client import (
    connect_opcua_client,
    read_all_kanal_configs,
    read_modifier_info,
    format_modifier_source,
    update_modifier_info_via_client,
    fetch_kanal_inputs_from_opcua
)
from opcua import Client, ua
from lib.services.TwinCAT_interface import collect_paths
from dotenv import load_dotenv
import time
import socket
import getpass
from datetime import datetime
import socket
import getpass
from lib.utils.get_adapter_info import get_all_adapters

def twinCAT_adapter_operations():
    # Initialize TwinCAT manager
    manager = TwinCATManager()

    # Load environment variables
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path)
    # Only show config as readonly, do not allow editing
    config = manager.config
    TWINCAT_PROJECT_PATH = config["TWINCAT_PROJECT_PATH"]
    AMS_NET_ID = config["AMS_NET_ID"]
    EXPORT_BASE_DIR = config["EXPORT_BASE_DIR"]
    IMPORT_BASE_DIR = config["IMPORT_BASE_DIR"]

    
    # Manager instance, log output to log_area
    log_area = ui.textarea(label='Log').props('readonly').style('width: 100%; height: 200px')

    def append_log(text):
        log_area.value += text + '\n'


    # TwinCAT related operations
    def init_sysman():
        manager.project_path = TWINCAT_PROJECT_PATH
        manager.ams_net_id = AMS_NET_ID
        success = manager.init_project()

        if success:
            state.sysman = manager.sysman
            append_log("initial: Success")
        else:
            append_log("initial: Failed")

    ui.label("Ethernet Adapter Configuration").style("font-weight: bold; font-size: 20px;")

    # Initialize TwinCAT project button
    ui.button("Initialize TwinCAT Project", on_click=init_sysman).style("margin-bottom: 15px")

    # adapter selection
    try:
        all_adapters = get_all_adapters()
        adapter_options = []

        # Populate adapter options
        for adapter in all_adapters:
            adapter_options.append(adapter["Name"])
        
        append_log(f"Found {len(adapter_options)} adapters.")

    except Exception as e:
        append_log(f"Error fetching adapters: {e}")
        all_adapters = []
        adapter_options = ["No adapters found"]

    adapter_selection = ui.select(
        label="Select Adapter", 
        options=adapter_options,
        value=adapter_options[0] if adapter_options else ''
    ).style("width: 100%")

    # Adapter change event
    def on_adapter_change():
        selected_adapter_name = adapter_selection.value
        if selected_adapter_name and selected_adapter_name != "No adapters found":
            
            selected_adapter_info = next((adapter for adapter in all_adapters if adapter['Name'] == selected_adapter_name), None)
            append_log(f"Selected adapter: {selected_adapter_name}")
            
        else:
            append_log("No adapter selected")
    
    adapter_selection.on('update:model-value', on_adapter_change)

    # refresh adapter list
    def refresh_adapters():
        try:
            nonlocal all_adapters  
            all_adapters = get_all_adapters()
            new_options = []
            
            for adapter in all_adapters:
                new_options.append(adapter['Name'])
            
            adapter_selection.set_options(new_options)
            adapter_selection.value = new_options[0] if new_options else ''
            append_log(f"Refreshed: Found {len(new_options)} adapters")
            
        except Exception as e:
            append_log(f"Failed to refresh adapters: {str(e)}")
    
    ui.button("Refresh Adapters", on_click=refresh_adapters).style("margin-top: 10px")

    # I/O Configuration section
    ui.separator()
    ui.label("I/O Configuration").style("font-weight: bold; font-size: 18px; margin-top: 20px")
    
    # I/O path selection
    io_path_selection = ui.select(
        label="Select I/O Path",
        options=["Please browse I/O paths first"],
        value="Please browse I/O paths first"
    ).style("width: 100%")

    # Function to browse I/O structure and populate paths
    def browse_io_paths():
        try:
            if not manager.sysman:
                append_log("Please initialize TwinCAT project first")
                return
                
            io_paths = manager.browse_IO_structure("TIID")
            
            if not io_paths:
                append_log("No I/O paths found")
                io_path_selection.set_options(["No I/O paths found"])
                io_path_selection.value = "No I/O paths found"
                return
            
            # Check if io_paths is a dictionary or list
            if isinstance(io_paths, dict):
                path_list = list(io_paths.keys())
            else:
                path_list = io_paths
                
            append_log(f"Found {len(path_list)} I/O paths")
            
            if len(path_list) == 1:
                # 只有一个path，直接显示
                io_path_selection.set_options(path_list)
                io_path_selection.value = path_list[0]
                append_log(f"Auto-selected I/O path: {path_list[0]}")
            else:
                # 多个path，做成列表
                io_path_selection.set_options(path_list)
                io_path_selection.value = path_list[0] if path_list else "No I/O paths found"
                append_log(f"Available I/O paths loaded as list")
                
        except Exception as e:
            append_log(f"Error browsing I/O structure: {e}")
            io_path_selection.set_options([])

    # I/O path change event
    def on_io_path_change():
        selected_path = io_path_selection.value
        if selected_path:
            append_log(f"Selected I/O path: {selected_path}")
        else:
            append_log("No I/O path selected")
    
    io_path_selection.on('update:model-value', on_io_path_change)
    
    # Function to apply adapter change to selected I/O path
    def apply_adapter_change():
        selected_adapter_name = adapter_selection.value
        selected_io_path = io_path_selection.value
        
        if not selected_adapter_name or selected_adapter_name == "No adapters found":
            append_log("Please select a valid adapter")
            return
            
        if not selected_io_path or selected_io_path in ["Please browse I/O paths first", "No I/O paths found"]:
            append_log("Please select a valid I/O path")
            return
            
        # Get the full adapter info from the original list
        selected_adapter_info = next((adapter for adapter in all_adapters if adapter['Name'] == selected_adapter_name), None)
        
        if not selected_adapter_info:
            append_log("Error: Could not find adapter information")
            return
            
        try:
            # Call the manager's io_adapter_change method
            success = manager.io_adapter_change(selected_io_path, selected_adapter_info)
            
            if success:
                append_log(f"Successfully applied adapter '{selected_adapter_name}' to I/O path '{selected_io_path}'")
            else:
                append_log("Failed to apply adapter change")
                
        except Exception as e:
            append_log(f"Error applying adapter change: {e}")

    ui.button("Browse I/O Paths", on_click=browse_io_paths).style("margin-top: 10px")
    ui.button("Apply Adapter Change", on_click=apply_adapter_change).style("margin-top: 10px")
    
