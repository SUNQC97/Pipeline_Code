import os
import xml.etree.ElementTree as ET
import re

FIELD_MAPPING = {
    "v_max": ("getriebe[0].dynamik.vb_max", lambda v: str(int(float(v) * 1000))),
    "a_max": ("getriebe[0].dynamik.a_max", str),
    "s_min": ("kenngr.swe_neg", lambda v: str(int(float(v) * 10000))),
    "s_max": ("kenngr.swe_pos", lambda v: str(int(float(v) * 10000))),
    "s_init": ("antr.abs_pos_offset", lambda v: str(int(float(v) * 10000))),
}



def clean_and_insert_trafo_lines(xml_data, new_trafo_lines):
    if not xml_data:
        raise ValueError("XML data is empty.")
    root = ET.fromstring(xml_data)
    sda_node = root.find(".//SdaMds")
    if sda_node is None:
        raise ValueError("SdaMds node not found in XML.")
    lines = sda_node.text.splitlines()
    cleaned_lines = [line for line in lines if not line.strip().startswith("trafo[")]
    new_trafo_lines = [line.strip() for line in new_trafo_lines]
    try:
        end_index = cleaned_lines.index("Ende")
    except ValueError:
        end_index = len(cleaned_lines)
    combined_lines = cleaned_lines[:end_index] + [""] + new_trafo_lines + [""] + cleaned_lines[end_index:]
    sda_node.text = "\n".join(combined_lines)
    return ET.tostring(root, encoding='unicode')

def read_trafo_lines_from_xml(xml_data):
    if not xml_data:
        raise ValueError("XML data is empty.")

    root = ET.fromstring(xml_data)
    sda_node = root.find(".//SdaMds")
    if sda_node is None or not sda_node.text:
        raise ValueError("SdaMds node not found or empty in XML.")

    cdata = sda_node.text

    # 提取 ID
    match_id = re.search(r"trafo\[0\]\.id\s+(-?\d+)", cdata)
    trafo_id = match_id.group(1) if match_id else "0"

    # 提取所有参数
    param_matches = re.findall(r"trafo\[0\]\.param\[(\d+)]\s+(-?\d+)", cdata)
    param_matches.sort(key=lambda x: int(x[0]))

    param_names = ["trafo[0].id"] + [f"trafo[0].param[{i}]" for i, _ in param_matches]
    param_values = [trafo_id] + [v for _, v in param_matches]

    return param_names, param_values



def update_node_with_xml(node, xml_str):
    node.ConsumeXml(xml_str)
    print("XML updated successfully.")

def axis_param_change_with_mapping(xml_data: str, axis_lines: list) -> str:
    if not xml_data:
        raise ValueError("Empty XML data.")

    root = ET.fromstring(xml_data)

    item_name_node = root.find(".//ItemName")
    if item_name_node is None or not item_name_node.text:
        raise ValueError("ItemName not found in XML.")

    # 统一提取编号，构造为 Axis_X 形式
    item_raw = item_name_node.text.strip()
    match = re.search(r'(\d+)', item_raw)
    if not match:
        raise ValueError(f"No axis number found in ItemName: {item_raw}")

    axis_index = match.group(1).lstrip("0") or "0"
    axis_name = f"Axis_{axis_index}"
    print(f"[Info] ItemName: {item_raw} -> Axis Nummber: {axis_index} -> Axis Param: {axis_name}.")


    # 找到 AchsMds CDATA 区块
    mds_node = root.find(".//AchsMds")
    if mds_node is None or not mds_node.text:
        raise ValueError("AchsMds not found or empty.")
    mds_text = mds_node.text

    # 过滤当前轴对应的参数行
    relevant_lines = [line for line in axis_lines if line.strip().startswith(axis_name + ".")]

    for line in relevant_lines:
        try:
            full_key, raw_value = line.strip().rsplit(maxsplit=1)
            _, param_key = full_key.split(".", 1)
        except ValueError:
            print(f"Invalid line format: {line}")
            continue

        if param_key not in FIELD_MAPPING:
            print(f"Skipping unmapped param: {param_key}")
            continue

        physical_field, transform = FIELD_MAPPING[param_key]
        try:
            new_value = transform(raw_value)
        except Exception as e:
            print(f"Value transform failed for {param_key} with value {raw_value}: {e}")
            continue

        pattern = rf"^({re.escape(physical_field)}\s+)[^\s]+"
        replacement = rf"\g<1>{new_value}"
        new_text, count = re.subn(pattern, replacement, mds_text, flags=re.MULTILINE)

        if count == 0:
            print(f"{physical_field} not found in CDATA.")
        else:
            mds_text = new_text
            print(f"Updated {axis_name}.{param_key} to {new_value}")

    mds_node.text = mds_text
    return ET.tostring(root, encoding="unicode")


def axis_param_change_with_matching(xml_data: str, axis_lines: list) -> str:
    if not xml_data:
        raise ValueError("Empty XML data.")

    root = ET.fromstring(xml_data)

    item_name_node = root.find(".//ItemName")
    if item_name_node is None or not item_name_node.text:
        raise ValueError("ItemName not found in XML.")

    item_raw = item_name_node.text.strip()
    match = re.search(r'(\d+)', item_raw)
    if not match:
        raise ValueError(f"No axis number found in ItemName: {item_raw}")

    axis_index = match.group(1).lstrip("0") or "0"
    axis_name = f"Axis_{axis_index}"
    print(f"[Info] ItemName: {item_raw} → Axis Name Used for Param Matching: {axis_name}")

    mds_node = root.find(".//AchsMds")
    if mds_node is None or not mds_node.text:
        raise ValueError("AchsMds not found or empty.")
    mds_text = mds_node.text

    for line in axis_lines:
        try:
            full_key, raw_value = line.strip().rsplit(maxsplit=1)
            _, param_key = full_key.split(".", 1)
        except ValueError:
            print(f"[Warning] Invalid line format: {line}")
            continue

        if param_key not in FIELD_MAPPING:
            print(f"[Warning] Skipping unmapped param: {param_key}")
            continue

        physical_field, transform = FIELD_MAPPING[param_key]
                
        try:
            new_value = transform(raw_value)
        except Exception as e:
            print(f"[Error] Failed to transform {param_key} = {raw_value}: {e}")
            continue

        pattern = rf"^({re.escape(physical_field)}\s+)[^\s]+"
        replacement = rf"\g<1>{new_value}"
        new_text, count = re.subn(pattern, replacement, mds_text, flags=re.MULTILINE)

        if count == 0:
            print(f"[Not Found] {physical_field} not found in CDATA.")
        else:
            mds_text = new_text
            print(f"[Updated] {full_key} → {new_value}")

    mds_node.text = mds_text
    return ET.tostring(root, encoding="unicode")
