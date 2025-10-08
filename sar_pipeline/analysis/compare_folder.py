from pathlib import Path
import pandas as pd

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_exact_files(folder_1: Path, folder_2: Path) -> bool:
    """
    Check if two folders contain exactly the same files (recursively).

    Parameters
    ----------
    folder_1, folder_2 : Path
        Paths to the two folders to compare.

    Returns
    -------
    bool
        True if the folders contain exactly the same files, False otherwise.
    """
    folder_1_files = set(
        f.relative_to(folder_1) for f in folder_1.rglob("*") if f.is_file()
    )
    folder_2_files = set(
        f.relative_to(folder_2) for f in folder_2.rglob("*") if f.is_file()
    )

    return folder_1_files == folder_2_files


def compare_product_folder_files(folder_1: str | Path, folder_2: str | Path) -> dict:
    """Compare file contents and file type distributions between two product folders.

    Scans both folders recursively, counting files by extension and comparing
    the presence of files between directories. Produces a summary of file
    type counts, total files, and lists of missing files in each folder.

    Parameters
    ----------
    folder_1 : str or pathlib.Path
        Path to the first product folder.
    folder_2 : str or pathlib.Path
        Path to the second product folder.

    Returns
    -------
    tuple
        bool
            True if the folders differ in file content or file types, otherwise False.
        dict
            Dictionary containing:
                - folder_1 : str
                    Path to the first folder.
                - folder_2 : str
                    Path to the second folder.
                - in_folder_1_missing_in_folder_2 : list of str
                    Files present in folder_1 but missing in folder_2.
                - in_folder_2_missing_in_folder_1 : list of str
                    Files present in folder_2 but missing in folder_1.
    """
    logger.info(f"Comparing product folders")
    logger.info(f"folder_1 : {folder_1}")
    logger.info(f"folder_2 : {folder_2}")

    folder_1 = Path(folder_1)
    folder_2 = Path(folder_2)

    for i, folder in enumerate([folder_1, folder_2]):
        logger.info(f"Files in folder {i+1}")
        for f in sorted(folder.iterdir()):
            logger.info(f"{f.name}")

    def get_extension_counts(folder: Path) -> pd.Series:
        files = [f.suffix.lower() for f in folder.glob("**/*") if f.is_file()]
        return pd.Series(files).value_counts()

    counts_1 = get_extension_counts(folder_1).rename("folder_1")
    counts_2 = get_extension_counts(folder_2).rename("folder_2")

    # Combine into DataFrame
    df = pd.concat([counts_1, counts_2], axis=1)

    # Add totals row
    totals = df.sum().to_frame().T
    totals.index = ["file count"]  # Name the totals row
    df = pd.concat([df, totals], axis=0)
    logger.info(f"\n{df}\n")

    # get files in different folders
    folder_1_files = set(folder_1.iterdir())  # all files in folder_1
    folder_2_files = set(folder_2.iterdir())  # all files in folder_2

    folders_have_same_files = check_exact_files(folder_1, folder_2)

    diffs = {
        "folder_1": str(folder_1),
        "folder_2": str(folder_2),
        "in_folder_1_missing_in_folder_2": [],
        "in_folder_2_missing_in_folder_1": [],
    }

    if folders_have_same_files:
        is_different = False
        return is_different, diffs
    else:
        is_different = True
        folder_1_names = {f.name for f in folder_1_files}
        folder_2_names = {f.name for f in folder_2_files}
        diffs["in_folder_1_missing_in_folder_2"] = list(folder_1_names - folder_2_names)
        diffs["in_folder_2_missing_in_folder_1"] = list(folder_2_names - folder_1_names)
        return is_different, diffs
