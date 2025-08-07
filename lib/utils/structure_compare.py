import json
import os
from lib.utils.save_to_file import save_structure_to_file

def compare_kanal_axis_structures(opcua_data: dict, twincat_data: dict, save_filename: str) -> dict:
    """
    Compare kanal and axis structures between OPC UA and TwinCAT.
    """

    missing_kanals = []
    missing_axes = {}
    extra_kanals = []
    extra_axes = {}

    # 1. Detect missing Kanäle and axes in TwinCAT
    for kanal in opcua_data:
        opcua_axes = set(opcua_data.get(kanal, []))
        twincat_axes = set(twincat_data.get(kanal, [])) if kanal in twincat_data else set()

        if kanal not in twincat_data:
            missing_kanals.append(kanal)

        diff_axes = opcua_axes - twincat_axes
        if diff_axes:
            # Sort axis names numerically
            missing_axes[kanal] = sorted(diff_axes, key=lambda x: int(x.split("_")[-1]))

    # 2. Detect extra Kanäle and axes in TwinCAT
    for kanal in twincat_data:
        if kanal not in opcua_data:
            extra_kanals.append(kanal)
        else:
            twincat_axes = set(twincat_data.get(kanal, []))
            opcua_axes = set(opcua_data.get(kanal, []))
            diff_axes = twincat_axes - opcua_axes
            if diff_axes:
                extra_axes[kanal] = sorted(diff_axes, key=lambda x: int(x.split("_")[-1]))

    # Sort Kanal names numerically
    missing_kanals = sorted(missing_kanals, key=lambda x: int(x.split("_")[-1]))
    extra_kanals = sorted(extra_kanals, key=lambda x: int(x.split("_")[-1]))

    # 3. Result dictionary
    result = {
        "missing_kanals": missing_kanals,
        "missing_axes": missing_axes,
        "extra_kanals": extra_kanals,
        "extra_axes": extra_axes,
    }

    # 4. Save result to file
    save_structure_to_file(result, save_filename)

    return result
