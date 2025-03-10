import h5py
from pathlib import Path

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RTCH5Manager:
    def __init__(self, file_path: str, mode: str = "r"):
        """
        Initialize the manager with a specified HDF5 file.
        :param file_path: Path to the HDF5 file to open.
        :param mode: Mode for opening the file ('r', 'r+', 'w', etc.)
        """
        self.file_path = Path(file_path)
        self.mode = mode

        if not self.file_path.exists() and mode in ("r", "r+"):
            raise FileNotFoundError(f"HDF5 file not found: {self.file_path}")
        
        self.file = h5py.File(self.file_path, mode)
        self.value_keys = self.list_data(print_name=False)

    def list_data(self, print_name=True):
        """list the files/data in the h5 file
        """
        data = []
        def visit_func(name, node):
            if print_name:
                print(name)
            data.append(name)
        self.file.visititems(visit_func)
        return data

    def get_value(self, dataset_path: str):
        """
        Retrieve a dataset value from the HDF5 file using a slash-separated key path.
        Example: dataset_path="group1/dataset1" retrieves /group1/dataset1.
        :param dataset_path: slash separated path to the dataset.
        :return: The value from the dataset.
        """

        if dataset_path not in self.file:
            raise KeyError(f"Dataset '{dataset_path}' not found in HDF5 file.")

        return self.file[dataset_path][()]

    def search_value(self, search_str: str):
        """Retrieve a value by searching with string. If a unique dataset
        parameter has this string, it will be returned. 

        Parameters
        ----------
        search_str : str
            string to search the dataset with.
        """

        keys = [x for x in self.value_keys if search_str in x]
        if len(keys) == 0:
            raise KeyError(f"Dataset containing '{search_str}' not found in HDF5 file.")
        if len(keys) > 1:
            raise KeyError(f"Multiple dataset containing '{search_str}' found in HDF5 file."
                           " Use a more specific string to retrieve unique data")
        else:
            return self.file[keys[0]][()]
    
    def get_array(self, dataset_path: str):
        """
        Retrieve a dataset array data from the HDF5 file using a slash-separated key path.
        Example: dataset_path="group1/dataset1" retrieves /group1/dataset1.
        :param dataset_path: slash separated path to the dataset.
        :return: The value from the dataset.
        """

        if dataset_path not in self.file:
            raise KeyError(f"Dataset '{dataset_path}' not found in HDF5 file.")

        return self.file[dataset_path][:] 

    def save(self, output_path: str):
        """
        Save the modified HDF5 file to a new file.
        (This is essentially a copy operation, as HDF5 files update in-place.)
        :param output_path: Path to save the new HDF5 file.
        """
        output_path = Path(output_path)
        with h5py.File(output_path, "w") as output_file:
            self._recursive_copy(self.file, output_file)

    def _ensure_group(self, group_path: str):
        """
        Ensure that a group exists (creating it if needed).
        :param group_path: Path to the group (slash-separated).
        :return: The group object.
        """
        current_group = self.file
        for part in group_path.split("/"):
            if part:
                current_group = current_group.require_group(part)
        return current_group

    def _recursive_copy(self, src, dest):
        """
        Recursively copy contents from one HDF5 file/group to another.
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
