"""Run isolated host/protocol regressions without a panel or provider credentials."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "g++"), help="C++ compiler executable")
    parser.add_argument("--cc", default=os.environ.get("CC", "gcc"), help="C compiler for native LVGL tests")
    parser.add_argument("--ui", action="store_true", help="Also build and run the actual LVGL dashboard/settings")
    parser.add_argument("--screenshots", type=Path, help="Directory for native UI PPM screenshots")
    args = parser.parse_args()
    compiler = shutil.which(args.cxx)
    if not compiler:
        parser.error("C++ compiler not found; install g++ or supply --cxx PATH")
    json_include = ROOT / ".pio/libdeps/esp32p4-release/ArduinoJson/src"
    if not json_include.is_dir():
        parser.error("ArduinoJson missing; run the esp32p4-release PlatformIO build first")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
                   cwd=ROOT, check=True)
    scratch = ROOT / "work"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="protocol-tests-", dir=scratch) as directory:
        binary = Path(directory) / ("protocol-tests.exe" if os.name == "nt" else "protocol-tests")
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                        "-I", str(json_include), str(ROOT / "tests/test_protocol.cpp"), "-o", str(binary)],
                       cwd=ROOT, check=True)
        subprocess.run([str(binary)], cwd=ROOT, check=True)
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-DAIM_BOARD_WAVESHARE_S3=1", "-I", str(ROOT / "src"),
                        "-I", str(json_include), str(ROOT / "tests/test_protocol.cpp"), "-o", str(binary)], cwd=ROOT, check=True)
        subprocess.run([str(binary)], cwd=ROOT, check=True)
        settings_binary = Path(directory) / ("settings-tests.exe" if os.name == "nt" else "settings-tests")
        lease_binary = Path(directory) / ("enrollment-lease-tests.exe" if os.name == "nt" else "enrollment-lease-tests")
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                        str(ROOT / "tests/test_enrollment_lease.cpp"), "-o", str(lease_binary)], cwd=ROOT, check=True)
        subprocess.run([str(lease_binary)], cwd=ROOT, check=True)
        delivery_binary = Path(directory) / ("permission-delivery-tests.exe" if os.name == "nt" else "permission-delivery-tests")
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                        str(ROOT / "tests/test_permission_delivery.cpp"), "-o", str(delivery_binary)], cwd=ROOT, check=True)
        subprocess.run([str(delivery_binary)], cwd=ROOT, check=True)
        history_binary=Path(directory)/("history-tests.exe" if os.name=="nt" else "history-tests")
        subprocess.run([compiler,"-std=c++17","-Wall","-Wextra","-Werror","-I",str(ROOT/"src"),
                        "-I",str(json_include),str(ROOT/"tests/test_history_usb.cpp"),"-o",str(history_binary)],cwd=ROOT,check=True)
        subprocess.run([str(history_binary)],cwd=ROOT,check=True)
        animation_binary=Path(directory)/("animation-tests.exe" if os.name=="nt" else "animation-tests")
        subprocess.run([compiler,"-std=c++17","-Wall","-Wextra","-Werror","-I",str(ROOT/"src"),
                        "-I",str(json_include),str(ROOT/"tests/test_animation.cpp"),"-o",str(animation_binary)],cwd=ROOT,check=True)
        subprocess.run([str(animation_binary)],cwd=ROOT,check=True)
        for name in ('companion_store','pack_protocol'):
            target=Path(directory)/(name+('.exe' if os.name=='nt' else ''))
            subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'src'),
                '-I',str(json_include),str(ROOT/('tests/test_'+name+'.cpp')),'-o',str(target)],cwd=ROOT,check=True)
            subprocess.run([str(target)],cwd=ROOT,check=True)
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                        "-I", str(ROOT / "tests/native"), str(ROOT / "tests/test_settings.cpp"), "-o", str(settings_binary)],
                       cwd=ROOT, check=True)
        subprocess.run([str(settings_binary)], cwd=ROOT, check=True)
        live_binary = Path(directory) / ("claude-live-tests.exe" if os.name == "nt" else "claude-live-tests")
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                        "-I", str(json_include), str(ROOT / "tests/test_claude_live.cpp"), "-o", str(live_binary)],
                       cwd=ROOT, check=True)
        subprocess.run([str(live_binary)], cwd=ROOT, check=True)
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                        "-I", str(json_include), str(ROOT / "tests/test_usb_live.cpp"), "-o", str(live_binary)],
                       cwd=ROOT, check=True)
        subprocess.run([str(live_binary)], cwd=ROOT, check=True)
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-DAIM_BOARD_WAVESHARE_S3=1",
                        "-I", str(ROOT / "src"), "-I", str(json_include),
                        str(ROOT / "tests/test_usb_live.cpp"), "-o", str(live_binary)], cwd=ROOT, check=True)
        subprocess.run([str(live_binary)], cwd=ROOT, check=True)
    if args.ui:
        c_compiler = shutil.which(args.cc)
        if not c_compiler or not shutil.which("cmake") or not shutil.which("ninja"):
            parser.error("--ui requires a C compiler, CMake and Ninja")
        build = scratch / "ui-native"
        subprocess.run(["cmake", "-S", str(ROOT / "tests/native"), "-B", str(build), "-G", "Ninja",
                        "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_C_COMPILER={Path(c_compiler).as_posix()}",
                        f"-DCMAKE_CXX_COMPILER={Path(compiler).as_posix()}"], cwd=ROOT, check=True)
        subprocess.run(["cmake", "--build", str(build), "--parallel", "4"], cwd=ROOT, check=True)
        binary = build / ("test_ui.exe" if os.name == "nt" else "test_ui")
        screenshots = args.screenshots.resolve() if args.screenshots else scratch / "ui-previews"
        subprocess.run([str(binary), str(screenshots)], cwd=ROOT, check=True)
        s3_binary = build / ("test_ui_s3.exe" if os.name == "nt" else "test_ui_s3")
        subprocess.run([str(s3_binary), str(screenshots / 's3')], cwd=ROOT, check=True)
        permission_binary = build / ("test_ui_permissions.exe" if os.name == "nt" else "test_ui_permissions")
        subprocess.run([str(permission_binary), str(screenshots / 'permission-wrapper')], cwd=ROOT, check=True)
        mirror_binary=build/("test_mirror.exe" if os.name=="nt" else "test_mirror")
        subprocess.run([str(mirror_binary)],cwd=ROOT,check=True)
    print("All requested regressions passed.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
