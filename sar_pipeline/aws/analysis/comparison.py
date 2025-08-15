import json
import os


def load_json_if_path(obj):
    """If obj is a string path to a file, load it as JSON, else return it unchanged."""
    if isinstance(obj, str) and os.path.isfile(obj):
        with open(obj, "r") as f:
            return json.load(f)
    return obj


def compare_json(json_1, json_2, path="", diffs=None):
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


# Example usage
if __name__ == "__main__":
    differences = compare_json("file1.json", "file2.json")

    with open("json_differences.json", "w") as out_file:
        json.dump(differences, out_file, indent=2)

    print(f"Found {len(differences)} differences. Saved to json_differences.json")
