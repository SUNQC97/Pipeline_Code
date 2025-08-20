import os
import xml.etree.ElementTree as ET
import re
from dotenv import load_dotenv

FIELD_MAPPING = {
    "v_max": ("getriebe[0].dynamik.vb_max", lambda v: str(int(float(v) * 1000)), lambda v: str(float(v) / 1000)),
    "a_max": ("getriebe[0].dynamik.a_max", str, str),
    "s_min": ("kenngr.swe_neg", lambda v: str(int(float(v) * 10000)), lambda v: str(float(v) / 10000)),
    "s_max": ("kenngr.swe_pos", lambda v: str(int(float(v) * 10000)), lambda v: str(float(v) / 10000)),
    "s_init": ("antr.abs_pos_offset", lambda v: str(int(float(v) * 10000)), lambda v: str(float(v) / 10000)),
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

        physical_field, transform, _ = FIELD_MAPPING[param_key]

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

        physical_field, transform, _ = FIELD_MAPPING[param_key]

                
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

def read_axis_param_from_xml_with_matching(filtered_names: list[str], filtered_values: list[str], xml_data: str) -> tuple[list[str], list[str]]:
    if not xml_data:
        raise ValueError("Empty XML data.")

    root = ET.fromstring(xml_data)

    item_name_node = root.find(".//ItemName")
    if item_name_node is None or not item_name_node.text:
        raise ValueError("ItemName not found in XML.")

    mds_node = root.find(".//AchsMds")
    if mds_node is None or not mds_node.text:
        raise ValueError("AchsMds not found or empty.")

    mds_text = mds_node.text

    param_names = []
    param_values = []

    for name, expected in zip(filtered_names, filtered_values):
        try:
            _, param_key = name.split(".", 1)
        except ValueError:
            continue

        mapping = FIELD_MAPPING.get(param_key)
        if not mapping:
            print(f"[Warning] No mapping found for {param_key}")
            continue

        mapped_field, _, untransform = mapping
        matched = False

        for line in mds_text.strip().splitlines():
            match = re.match(r'^([^\s]+)\s+([^\s\(\)]+)', line.strip())
            if not match:
                continue
            physical_field, value = match.groups()

            if physical_field.strip().endswith(mapped_field.strip()):
                try:
                    original_value = untransform(value)
                except Exception as e:
                    original_value = value
                param_names.append(name)
                param_values.append(original_value)
                matched = True
                break

        if not matched:
            print(f"[Warning] Cannot find field '{mapped_field}' for {name} in XML")

    return param_names, param_values

def change_xml_from_new_kanal(xml_data) -> str: 
    """
    Write new Kanal XML data to the XML file.
    """
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path) 
    lis_base_path = os.getenv("LIS_BASE_PATH")
    default_lis_filenames = {
        "SdaMds": "sda_mds1.lis",
        "NullpD": "nullp_d1.lis",
        "WerkzD": "werkz_d1.lis",
        "PzvD":   "pzv_d1.lis",
        "VeD":    "ext_var1.lis",
    }

    lis_files = {
        field: os.path.join(lis_base_path, filename)
        for field, filename in default_lis_filenames.items()
    }

    # 3. 解析原始 XML analysieren
    if not xml_data:
        raise ValueError("XML data is empty.")
    
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML data: {e}")

    # 4. 遍历每个字段，插入对应 .lis 内容 durchlaufen 
    for field, file_path in lis_files.items():
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Missing .lis file for {field}: {file_path}")
        
        content = safe_read_file(file_path)
        
        elem = root.find(f".//{field}")
        if elem is None:
            raise ValueError(f"Missing XML element <{field}>")
        
        elem.text = f"<![CDATA[{content}]]>"

    # 5. 输出完整 XML 字符串（修复 CDATA 转义）
    xml_string = ET.tostring(root, encoding="unicode")
    xml_string = xml_string.replace("&lt;![CDATA[", "<![CDATA[").replace("]]&gt;", "]]>")
    
    return xml_string

def safe_read_file(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin1") as f:   
            return f.read()

def change_xml_from_new_axis(xml_data: str, axis_name: str, kanal_name: str) -> str:
    """
    Write new Axis XML data to the XML file, including kanal and axis information.
    """

    # 1. load environment variables and .lis file paths
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path)
    lis_base_path = os.getenv("LIS_BASE_PATH")
    if not lis_base_path:
        raise ValueError("LIS_BASE_PATH is not set in .env")

    lis_file_name = "achsmds1.lis"
    lis_path = os.path.join(lis_base_path, lis_file_name)

    # 2. check and parse XML
    if not xml_data:
        raise ValueError("XML data is empty.")

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}")

    # 3. read .lis file content
    if not os.path.exists(lis_path):
        raise FileNotFoundError(f"{lis_path} not found")

    with open(lis_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 4. extract kanal number from kanal_name and write to <DefaultChannel>
    try:
        kanal_num = int(kanal_name.split("_")[-1])
    except (IndexError, ValueError):
        raise ValueError(f"Invalid kanal_name format: {kanal_name}")

    dc_elem = root.find(".//DefaultChannel")
    if dc_elem is None:
        raise ValueError("Missing <DefaultChannel> element in XML")
    dc_elem.text = str(kanal_num)

    # 5. extract axis number from axis_name and write to <DefaultIndex>
    try:
        axis_index = int(axis_name.split("_")[-1])
    except (IndexError, ValueError):
        raise ValueError(f"Invalid axis_name format: {axis_name}")

    default_index_zero_based = axis_index - 1

    di_elem = root.find(".//DefaultIndex")
    if di_elem is None:
        raise ValueError("Missing <DefaultIndex> element in XML")
    di_elem.text = str(axis_index-1)    # # Index is zero-based, so we subtract 1

    # 6. generate and wirte DefaultProgName
    prog_letters = ["X", "Y", "Z", "A", "B", "C"]
    if default_index_zero_based < len(prog_letters):
        progname = f"{prog_letters[default_index_zero_based]}{kanal_num}"
    else:
        progname = f"U{default_index_zero_based}_{kanal_num}"  # fallback

    dp_elem = root.find(".//DefaultProgName")
    if dp_elem is None:
        raise ValueError("Missing <DefaultProgName> element in XML")
    dp_elem.text = progname

    # 7. inject CDATA content into <AchsMds>
    achs_elem = root.find(".//AchsMds")
    if achs_elem is None:
        raise ValueError("Missing <AchsMds> element in XML")

    achs_elem.text = f"<![CDATA[{content}]]>"

    # 8. return XML string
    xml_string = ET.tostring(root, encoding="unicode")
    xml_string = xml_string.replace("&lt;![CDATA[", "<![CDATA[").replace("]]&gt;", "]]>")

    return xml_string

def change_xml_adapter(xml_data:str, device: dict) -> str:
    """
    Change the XML data for a specific adapter device.
    device: {
        "Name": "Ethernet 5",
        "MAC": "00:01:05:94:25:45",
        "GUID": "{70D021F2-0369-4A3A-A9DE-78608AD033E3}"
    }
    """
    root = ET.fromstring(xml_data)

    # locate AddressInfo -> Pnp
    pnp = root.find(".//AddressInfo/Pnp")
    if pnp is None:
        raise ValueError("XML cannot find AddressInfo/Pnp")

    # DeviceDesc
    desc = pnp.find("DeviceDesc")
    if desc is not None:
        desc.text = device["Name"]

    # DeviceName -> 带 GUID
    devname = pnp.find("DeviceName")
    if devname is not None:
        devname.text = f"\\DEVICE\\{device['GUID'].strip('{}')}"

    # DeviceData -> MAC remove colons
    devdata = pnp.find("DeviceData")
    if devdata is not None and device.get("MAC"):
        devdata.text = device["MAC"].replace(":", "").replace("-", "")

    return ET.tostring(root, encoding='unicode')

