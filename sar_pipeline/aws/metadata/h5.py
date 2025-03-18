import h5py
from pathlib import Path
import numpy as np

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class H5Manager:
    def __init__(self, file_path: str | Path, mode: str = "r"):
        """Initialize the manager with a specified HDF5 file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file to open.
        mode : str, optional
            Mode for opening the file ('r', 'r+', 'w', etc.), by default "r"

        Raises
        ------
        FileNotFoundError
        """

        self.file_path = Path(file_path)
        self.mode = mode
        self.decode_method = 'utf-8'

        if not self.file_path.exists() and mode in ("r", "r+"):
            raise FileNotFoundError(f"HDF5 file not found: {self.file_path}")
        
        self.file = h5py.File(self.file_path, mode)
        self.keys = self.get_key_list(print_name=False)
        self.value_keys = self.get_keys_with_values()

    def get_key_list(self, print_name=False) -> list:
        """list the files/data in the h5 file

        Parameters
        ----------
        print_name : bool, optional
            Print the keys in the file, by default False

        Returns
        -------
        list
            List of data paths in the .h5 file
        """
        data = []
        def visit_func(name, node):
            if print_name:
                print(name)
            data.append(name)
        self.file.visititems(visit_func)
        return data
    
    def get_keys_with_values(self):
        """get the list of keys in the .h5 that have a retrievable value
        
        Returns
        -------
        list
            List of data paths in the .h5 file
        """
        value_keys = []
        for k in self.keys:
            try:
                self.get_value(k)
                value_keys.append(k)
            except:
                continue
        return value_keys

    def get_value(self, dataset_path: str, decode_bytes=True):
        """Retrieve a dataset value from the HDF5 file using a slash-separated key path.
        Example: dataset_path="group1/dataset1" retrieves /group1/dataset1.

        Parameters
        ----------
        dataset_path : str
            slash separated path to the dataset.
        decode_bytes: bool
            decode values that are of type bytes. this makes data json compatible. 
            Default is True.

        Returns
        -------
            The encoded value from the dataset.

        Raises
        ------
        KeyError
            Dataset is not in the .h5 file
        """

        if dataset_path not in self.file:
            raise KeyError(f"Dataset '{dataset_path}' not found in HDF5 file.")

        val = self.file[dataset_path][()]

        def _json_serialize(obj):
            # convert values to json compatible formats 
            if isinstance(obj, (np.integer, np.floating)):
                return obj.item()  # Convert to native Python types
            elif isinstance(obj, np.ndarray):
                return obj.tolist()  # Convert arrays to lists
            elif isinstance(obj, np.bool_):  
                return bool(obj)  # Convert NumPy bool_ to Python bool
            return obj
        
        def _decode_recursive(item):
            # handle decoding of nested encoded lists
            if isinstance(item, (bytes, np.bytes_)):
                return item.decode(self.decode_method)
            elif isinstance(item, (list, np.ndarray)):
                return [_decode_recursive(x) for x in item]
            return item

        if decode_bytes:
            val = _decode_recursive(val)
            val = _json_serialize(val)

        return val


    def search_value(self, search_str: str, decode_bytes=True):
        """Retrieve a value by searching keys with string. If a unique dataset
        parameter has this string, it will be returned. For example,
        "filteringApplied" will return the value for 
        "metadata/processingInformation/parameters/filteringApplied". If
        the string corresponds to more than one key, an error would be raised.
        For example, the string "metadata" is associated with many keys.

        Parameters
        ----------
        search_str : str
            string to use to search for keys
        decode_bytes: bool
            decode values that are of type bytes. Default is True.

        Returns
        -------
        Data corresponding to the key

        Raises
        ------
        KeyError
            Key is not found, or multiple keys match the search string and a
            more specific string should be used for searching. 
        """

        keys = [x for x in self.value_keys if search_str in x]
        if len(keys) == 0:
            raise KeyError(f"Dataset containing '{search_str}' not found in HDF5 file.")
        if len(keys) > 1:
            raise KeyError(f"Multiple datasets containing the string '{search_str}' found in HDF5 file."
                           " Use a more specific string to retrieve unique data")
        else:
            return self.get_value(keys[0], decode_bytes=decode_bytes)
    
    def get_array(self, dataset_path: str):
        """Retrieve a dataset array data from the HDF5 file using a slash-separated key path.
        Example: dataset_path="group1/dataset1" retrieves /group1/dataset1.

        Parameters
        ----------
        dataset_path : str
            slash separated path to the dataset.

        Returns
        -------
        Encoded array data corresponding to key

        Raises
        ------
        KeyError
            Key not found
        """

        if dataset_path not in self.file:
            raise KeyError(f"Dataset '{dataset_path}' not found in HDF5 file.")

        return self.file[dataset_path][:] 

    def save(self, output_path: str | Path):
        """Save the modified HDF5 file to a new file.
        (This is essentially a copy operation, as HDF5 files update in-place.)

        Parameters
        ----------
        output_path : str | Path
            Location to save file
        """
        
        output_path = Path(output_path)
        with h5py.File(output_path, "w") as output_file:
            self._recursive_copy(self.file, output_file)

    def _ensure_group(self, group_path: str):
        """Ensure that a group exists (creating it if needed).

        Parameters
        ----------
        group_path : str
            Path to the group (slash-separated).

        Returns
        -------
        _type_
            The group object.
        """
        current_group = self.file
        for part in group_path.split("/"):
            if part:
                current_group = current_group.require_group(part)
        return current_group

    def _recursive_copy(self, src, dest):
        """Recursively copy contents from one HDF5 file/group to another.
        """
        for name, item in src.items():
            if isinstance(item, h5py.Group):
                group = dest.create_group(name)
                self._recursive_copy(item, group)
            else:
                dest.create_dataset(name, data=item[()])

    def close(self):
        """ Close the open file handle. """
        if self.file:
            self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
