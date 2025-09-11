import json
import os
import xml.etree.ElementTree as ET
import os


def load_json_if_path(obj):
    """If obj is a string path to a file, load it as JSON, else return it unchanged."""
    if isinstance(obj, str) and os.path.isfile(obj):
        with open(obj, "r") as f:
            return json.load(f)
    return obj


def compare_json(json_1: dict | str, json_2: dict | str, path="", diffs=None):
    """
    Recursively compare two dicts/lists and record differences with values.
    json_1 and json_2 can be dicts/lists or file paths to JSON.
    """
    if diffs is None:
        diffs = []

    # Load JSON if file paths are provided
    json_1 = load_json_if_path(json_1)
    json_2 = load_json_if_path(json_2)

    if isinstance(json_1, dict) and isinstance(json_2, dict):
        for key in json_1.keys() | json_2.keys():  # union of keys
            new_path = f"{path}.{key}" if path else key
            if key not in json_2:
                diffs.append(
                    {
                        "path": new_path,
                        "status": "missing_in_second",
                        "value_first": json_1[key],
                        "value_second": None,
                    }
                )
            elif key not in json_1:
                diffs.append(
                    {
                        "path": new_path,
                        "status": "missing_in_first",
                        "value_first": None,
                        "value_second": json_2[key],
                    }
                )
            else:
                compare_json(json_1[key], json_2[key], new_path, diffs)
    elif isinstance(json_1, list) and isinstance(json_2, list):
        min_len = min(len(json_1), len(json_2))
        for i in range(min_len):
            compare_json(json_1[i], json_2[i], f"{path}[{i}]", diffs)
        if len(json_1) != len(json_2):
            diffs.append(
                {
                    "path": path,
                    "status": "list_length_differs",
                    "value_first_length": len(json_1),
                    "value_second_length": len(json_2),
                }
            )
    else:
        if json_1 != json_2:
            diffs.append(
                {
                    "path": path,
                    "status": "value_differs",
                    "value_first": json_1,
                    "value_second": json_2,
                }
            )

    return diffs


def write_diffs_to_json(diffs, output_file):
    """
    Write differences to an json file.
    """
    with open(output_file, "w") as out_file:
        json.dump(diffs, out_file, indent=2)


def load_xml_if_path(obj):
    """If obj is a string path to a file, load it as an XML ElementTree, else return it unchanged."""
    if isinstance(obj, str) and os.path.isfile(obj):
        tree = ET.parse(obj)
        return tree.getroot()
    return obj


def compare_xml(elem1, elem2, path="", diffs=None):
    """
    Recursively compare two XML elements and record differences.
    """
    if diffs is None:
        diffs = []

    elem1 = load_xml_if_path(elem1)
    elem2 = load_xml_if_path(elem2)

    # Compare tags
    if elem1.tag != elem2.tag:
        diffs.append(
            {
                "path": path,
                "status": "tag_differs",
                "value_first": elem1.tag,
                "value_second": elem2.tag,
            }
        )

    # Compare text
    if (elem1.text or "").strip() != (elem2.text or "").strip():
        diffs.append(
            {
                "path": path,
                "status": "text_differs",
                "value_first": elem1.text,
                "value_second": elem2.text,
            }
        )

    # Compare attributes
    all_keys = set(elem1.attrib) | set(elem2.attrib)
    for key in all_keys:
        if key not in elem1.attrib:
            diffs.append(
                {
                    "path": f"{path}/@{key}",
                    "status": "missing_in_first",
                    "value_first": None,
                    "value_second": elem2.attrib[key],
                }
            )
        elif key not in elem2.attrib:
            diffs.append(
                {
                    "path": f"{path}/@{key}",
                    "status": "missing_in_second",
                    "value_first": elem1.attrib[key],
                    "value_second": None,
                }
            )
        elif elem1.attrib[key] != elem2.attrib[key]:
            diffs.append(
                {
                    "path": f"{path}/@{key}",
                    "status": "attr_differs",
                    "value_first": elem1.attrib[key],
                    "value_second": elem2.attrib[key],
                }
            )

    # Compare children
    children1 = list(elem1)
    children2 = list(elem2)
    min_len = min(len(children1), len(children2))
    for i in range(min_len):
        compare_xml(children1[i], children2[i], f"{path}/{elem1.tag}[{i}]", diffs)
    if len(children1) != len(children2):
        diffs.append(
            {
                "path": path,
                "status": "children_length_differs",
                "value_first_length": len(children1),
                "value_second_length": len(children2),
            }
        )

    return diffs


def write_diffs_to_xml(diffs, output_file):
    """
    Write differences to an XML file.
    """
    root = ET.Element("differences")
    for diff in diffs:
        entry = ET.SubElement(root, "difference")
        for key, value in diff.items():
            child = ET.SubElement(entry, key)
            child.text = str(value)
    tree = ET.ElementTree(root)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
