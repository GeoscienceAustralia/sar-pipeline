from pathlib import Path

import pytest
from ruamel.yaml import YAML

from sar_pipeline.utils import resources
from sar_pipeline.utils.resources import (
    GIB,
    compute_rtc_num_workers,
    get_cgroup_cpu_limit,
    get_cgroup_memory_limit_bytes,
    resolve_rtc_num_workers,
)
from sar_pipeline.pipelines.isce3_rtc.utils.config_manager import (
    RTCConfigManager,
    NUM_WORKERS_KEY,
)

HOST_CPUS = 64
HOST_MEMORY_BYTES = 256 * GIB


@pytest.fixture(autouse=True)
def fake_host(monkeypatch):
    """Make the host fallbacks deterministic and independent of the test machine"""
    monkeypatch.setattr(resources, "_host_cpu_count", lambda: HOST_CPUS)
    monkeypatch.setattr(resources, "_host_memory_bytes", lambda: HOST_MEMORY_BYTES)


def _write_v2(root: Path, cpu_max: str | None, memory_max: str | None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if cpu_max is not None:
        (root / "cpu.max").write_text(cpu_max + "\n")
    if memory_max is not None:
        (root / "memory.max").write_text(memory_max + "\n")
    return root


def _write_v1(
    root: Path, quota: str | None, period: str | None, memory_limit: str | None
) -> Path:
    (root / "cpu").mkdir(parents=True, exist_ok=True)
    (root / "memory").mkdir(parents=True, exist_ok=True)
    if quota is not None:
        (root / "cpu" / "cpu.cfs_quota_us").write_text(quota + "\n")
    if period is not None:
        (root / "cpu" / "cpu.cfs_period_us").write_text(period + "\n")
    if memory_limit is not None:
        (root / "memory" / "memory.limit_in_bytes").write_text(memory_limit + "\n")
    return root


def test_v2_limited(tmp_path):
    root = _write_v2(tmp_path, "400000 100000", str(32 * GIB))
    assert get_cgroup_cpu_limit(root) == 4
    assert get_cgroup_memory_limit_bytes(root) == 32 * GIB
    # cpu=4, memory=(32-2)/8=3.75 with the default 2 GiB reserve
    assert compute_rtc_num_workers(8, root) == 3


def test_v2_unlimited_falls_back_to_host(tmp_path):
    root = _write_v2(tmp_path, "max 100000", "max")
    assert get_cgroup_cpu_limit(root) is None
    assert get_cgroup_memory_limit_bytes(root) is None
    # host cpu=64, host memory=(256-2)/8=31.75
    assert compute_rtc_num_workers(8, root) == 31


def test_v1_limited(tmp_path):
    root = _write_v1(tmp_path, "200000", "100000", str(64 * GIB))
    assert get_cgroup_cpu_limit(root) == 2
    assert get_cgroup_memory_limit_bytes(root) == 64 * GIB
    # cpu=2 is binding, memory=64/8=8
    assert compute_rtc_num_workers(8, root) == 2


def test_v1_unlimited_sentinel(tmp_path):
    root = _write_v1(tmp_path, "-1", "100000", "9223372036854771712")
    assert get_cgroup_cpu_limit(root) is None
    assert get_cgroup_memory_limit_bytes(root) is None
    assert compute_rtc_num_workers(8, root) == 31


def test_fractional_cpu_is_floored(tmp_path):
    root = _write_v2(tmp_path, "350000 100000", str(512 * GIB))
    assert get_cgroup_cpu_limit(root) == 3.5
    assert compute_rtc_num_workers(8, root) == 3


def test_memory_bound(tmp_path):
    # small pod on a large node : 16 CPUs but only 20 GiB
    root = _write_v2(tmp_path, "1600000 100000", str(20 * GIB))
    assert compute_rtc_num_workers(8, root) == 2


def test_cpu_bound(tmp_path):
    root = _write_v2(tmp_path, "300000 100000", str(128 * GIB))
    assert compute_rtc_num_workers(8, root) == 3


def test_minimum_one(tmp_path):
    # quota below one cpu and memory below one burst
    root = _write_v2(tmp_path, "50000 100000", str(4 * GIB))
    assert compute_rtc_num_workers(8, root) == 1


def test_missing_cgroup_files_fall_back_to_host(tmp_path):
    root = tmp_path / "no_cgroup_here"
    assert get_cgroup_cpu_limit(root) is None
    assert get_cgroup_memory_limit_bytes(root) is None
    assert compute_rtc_num_workers(8, root) == 31
    assert compute_rtc_num_workers(1, root) == HOST_CPUS


def test_host_cpu_count_uses_affinity(monkeypatch):
    monkeypatch.undo()  # use the real helper, with a patched os
    monkeypatch.setattr(resources.os, "sched_getaffinity", lambda pid: {0, 1, 2})
    assert resources._host_cpu_count() == 3


def test_host_memory_uses_sysconf(monkeypatch):
    monkeypatch.undo()
    values = {"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": 1000}
    monkeypatch.setattr(resources.os, "sysconf", lambda name: values[name])
    assert resources._host_memory_bytes() == 4096 * 1000


def test_junk_cgroup_values_are_ignored(tmp_path):
    root = _write_v2(tmp_path, "garbage", "also-garbage")
    assert get_cgroup_cpu_limit(root) is None
    assert get_cgroup_memory_limit_bytes(root) is None


def test_invalid_memory_per_worker(tmp_path):
    with pytest.raises(ValueError):
        compute_rtc_num_workers(0, tmp_path)


@pytest.mark.parametrize(
    "reserve_gib,expected",
    [
        (0, 2),  # 16/8 = 2
        (2, 1),  # (16-2)/8 = 1.75
        (1, 1),  # (16-1)/8 = 1.875
        (100, 1),  # reserve larger than the limit still gives 1 worker
    ],
)
def test_memory_reserve_is_subtracted(tmp_path, reserve_gib, expected):
    root = _write_v2(tmp_path, "1600000 100000", str(16 * GIB))
    assert compute_rtc_num_workers(8, root, memory_reserve_gib=reserve_gib) == expected


def test_default_memory_reserve(tmp_path):
    root = _write_v2(tmp_path, "1600000 100000", str(16 * GIB))
    assert resources.DEFAULT_MEMORY_RESERVE_GIB == 2.0
    assert compute_rtc_num_workers(8, root) == compute_rtc_num_workers(
        8, root, memory_reserve_gib=2.0
    )


def test_negative_memory_reserve_rejected(tmp_path):
    with pytest.raises(ValueError):
        compute_rtc_num_workers(8, tmp_path, memory_reserve_gib=-1)


@pytest.mark.parametrize("value", ["auto", "AUTO", " auto "])
def test_resolve_auto(tmp_path, value):
    # cpu=4, memory=(18-2)/8=2
    root = _write_v2(tmp_path, "400000 100000", str(18 * GIB))
    assert resolve_rtc_num_workers(value, 8, root) == 2


def test_resolve_auto_passes_memory_reserve(tmp_path):
    root = _write_v2(tmp_path, "400000 100000", str(18 * GIB))
    assert resolve_rtc_num_workers("auto", 8, root, memory_reserve_gib=0) == 2
    assert resolve_rtc_num_workers("auto", 8, root, memory_reserve_gib=4) == 1


@pytest.mark.parametrize("value,expected", [("3", 3), (5, 5)])
def test_resolve_explicit(tmp_path, value, expected):
    assert resolve_rtc_num_workers(value, 8, tmp_path) == expected


@pytest.mark.parametrize("value", ["0", 0, " 0 "])
def test_resolve_zero_leaves_rtc_default(tmp_path, value):
    # 0 is passed through so RTC picks the number itself, as before this option
    root = _write_v2(tmp_path, "100000 100000", str(1 * GIB))
    assert resolve_rtc_num_workers(value, 8, root) == 0


@pytest.mark.parametrize("value", ["-2", "two", "1.5", None])
def test_resolve_invalid(tmp_path, value):
    with pytest.raises(ValueError):
        resolve_rtc_num_workers(value, 8, tmp_path)


@pytest.mark.parametrize("base_config", ["S1_RTC_IW.yaml", "S1_RTC_STATIC_IW.yaml"])
def test_num_workers_saved_in_run_config(tmp_path, base_config):
    config = RTCConfigManager(base_config=base_config)
    # the base configs default to 0 (RTC then uses os.cpu_count())
    assert config.get(NUM_WORKERS_KEY) == 0
    config.set_num_workers(3)
    save_path = tmp_path / "runconfig.yaml"
    config.save(save_path)

    with open(save_path) as f:
        saved = YAML().load(f)
    assert saved["runconfig"]["groups"]["processing"]["num_workers"] == 3


def test_num_workers_zero_saved_in_run_config(tmp_path):
    config = RTCConfigManager(base_config="S1_RTC_IW.yaml")
    config.set_num_workers(0)
    save_path = tmp_path / "runconfig.yaml"
    config.save(save_path)

    with open(save_path) as f:
        saved = YAML().load(f)
    assert saved["runconfig"]["groups"]["processing"]["num_workers"] == 0


@pytest.mark.parametrize("value", [-1, 2.0, "3", True])
def test_set_num_workers_rejects_invalid(value):
    config = RTCConfigManager(base_config="S1_RTC_IW.yaml")
    with pytest.raises(ValueError):
        config.set_num_workers(value)


def test_cli_num_workers_option_validation():
    import click
    from sar_pipeline.pipelines.isce3_rtc.cli import _validate_num_workers

    assert _validate_num_workers(None, None, "auto") == "auto"
    assert _validate_num_workers(None, None, None) == "auto"
    assert _validate_num_workers(None, None, "4") == 4
    assert _validate_num_workers(None, None, "0") == 0
    for bad in ["-1", "x", "2.5"]:
        with pytest.raises(click.BadParameter):
            _validate_num_workers(None, None, bad)


def test_cli_rejects_invalid_num_workers_before_running(monkeypatch):
    """click validates the option (and env var) before any download/network call"""
    from click.testing import CliRunner
    from sar_pipeline.pipelines.isce3_rtc.cli import (
        get_data_for_scene_and_make_run_config,
    )

    args = [
        "--scene",
        "S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
        "--resolution",
        "20",
        "--product",
        "RTC_S1",
        "--s3-bucket",
        "bucket",
        "--s3-project-folder",
        "folder",
        "--collection-number",
        "1",
        "--download-folder",
        "dl",
        "--scratch-folder",
        "scratch",
        "--out-folder",
        "out",
        "--run-config-save-path",
        "out/config.yaml",
    ]
    runner = CliRunner()
    result = runner.invoke(
        get_data_for_scene_and_make_run_config, args + ["--num-workers", "zero"]
    )
    assert result.exit_code == 2
    assert "--num-workers" in result.output

    result = runner.invoke(
        get_data_for_scene_and_make_run_config,
        args,
        env={"RTC_NUM_WORKERS": "-3"},
    )
    assert result.exit_code == 2

    result = runner.invoke(
        get_data_for_scene_and_make_run_config,
        args + ["--rtc-memory-per-burst-gib", "0"],
    )
    assert result.exit_code == 2

    result = runner.invoke(
        get_data_for_scene_and_make_run_config,
        args + ["--rtc-memory-reserve-gib", "-1"],
    )
    assert result.exit_code == 2
    assert "--rtc-memory-reserve-gib" in result.output

    result = runner.invoke(
        get_data_for_scene_and_make_run_config,
        args,
        env={"RTC_MEMORY_RESERVE_GIB": "-1"},
    )
    assert result.exit_code == 2
