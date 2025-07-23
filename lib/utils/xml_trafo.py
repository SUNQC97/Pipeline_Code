import os
import xml.etree.ElementTree as ET

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

def update_node_with_xml(node, xml_str):
    node.ConsumeXml(xml_str)
    print("XML updated successfully.")
