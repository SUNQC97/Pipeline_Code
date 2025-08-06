import json
import os
from lib.utils.save_to_file import save_structure_to_file

def compare_kanal_axis_structures(opcua_data: dict, twincat_data: dict, save_filename: str) -> dict:
    """
    Compare kanal and axis structures between OPC UA and TwinCAT.
    """
    #print(opcua_data)
    #print(twincat_data)
    
    
    missing_kanals = []
    missing_axes = {}
    extra_kanals = []
    extra_axes = {}

    # 1. Find missing Kanal in TwinCAT
    for kanal in opcua_data:
        if kanal not in twincat_data:
            missing_kanals.append(kanal)
        else:
            # 2. Find missing Axis in TwinCAT
            opcua_axes = set(opcua_data[kanal])
            twincat_axes = set(twincat_data.get(kanal, []))
            diff_axes = opcua_axes - twincat_axes
            if diff_axes:
                missing_axes[kanal] = list(diff_axes)

    # 3. Find extra Kanal in TwinCAT
    for kanal in twincat_data:
        if kanal not in opcua_data:
            extra_kanals.append(kanal)
        else:
            # 4. Find extra Axis in TwinCAT
            twincat_axes = set(twincat_data[kanal])
            opcua_axes = set(opcua_data.get(kanal, []))
            diff_axes = twincat_axes - opcua_axes
            if diff_axes:
                extra_axes[kanal] = list(diff_axes)

    result = {
        "missing_kanals": missing_kanals,   # Kanal in OPC UA but not in TwinCAT
        "missing_axes": missing_axes,       # Axis in OPC UA but not in TwinCAT
        "extra_kanals": extra_kanals,       # Kanal in TwinCAT but
        "extra_axes": extra_axes,           # Axis in TwinCAT but not in OPC UA
    }

    # Save the result to a JSON file
    save_structure_to_file(result, save_filename)

    return result

