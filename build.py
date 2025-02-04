import os
import subprocess
import sys
import os
import subprocess
import sys

import urllib.request


def download_file(url, destination):
    print(f"Downloading file from {url}")
    urllib.request.urlretrieve(url, destination)
    print("File downloaded successfully")


# Rest of the code...


def getPlatform():
    return sys.platform


def build_gui():
    print("Building GUI")
    if getPlatform() == "darwin" or getPlatform() == "linux":
        os.system("pyside6-uic -g python testRVEInterface.ui > mainwindow.py")
    if getPlatform() == "win32":
        os.system(
            r".\venv\Lib\site-packages\PySide6\uic.exe -g python testRVEInterface.ui > mainwindow.py"
        )


def install_pip():
    download_file("https://bootstrap.pypa.io/get-pip.py", "get-pip.py")
    command = ["python3", "get-pip.py"]
    subprocess.run(command)


def install_pip_in_venv():
    command = [
        "venv\\Scripts\\python.exe" if getPlatform() == "win32" else "venv/bin/python3",
        "get-pip.py",
    ]
    subprocess.run(command)


def build_resources():
    print("Building resources.rc")
    if getPlatform() == "darwin" or getPlatform() == "linux":
        os.system("pyside6-rcc -g python resources.qrc > resources_rc.py")
    if getPlatform() == "win32":
        os.system(
            r".\venv\Lib\site-packages\PySide6\rcc.exe -g python resources.qrc > resources_rc.py"
        )


def create_venv():
    print("Creating virtual environment")
    command = ["python3", "-m", "venv", "venv"]
    subprocess.run(command)


def install_requirements_in_venv():
    print("Installing requirements in virtual environment")
    command = [
        "venv\\Scripts\\python.exe" if getPlatform() == "win32" else "venv/bin/python3",
        "-m",
        "pip",
        "install",
        "-r",
        "requirements.txt",
    ]

    subprocess.run(command)


def build_executable():
    print("Building executable")
    if getPlatform() == "win32":
        command = [
            r".\venv\Scripts\python.exe"
            if getPlatform() == "win32"
            else "venv/bin/python3",
            "-m",
            "PyInstaller",
            "main.py",
            "--icon=icons/logo-v2.ico",
            "--noconfirm",
            "--noupx",
        ]
    else:
        command = [
            r".\venv\Scripts\python.exe"
            if getPlatform() == "win32"
            else "venv/bin/python3",
            "-m",
            "cx_Freeze",
            "main.py",
            "--target-dir",
            "dist",
        ]
    subprocess.run(command)


def clean():
    print("Cleaning up")
    os.remove("get-pip.py")


install_pip()
create_venv()
install_pip_in_venv()
install_requirements_in_venv()
build_gui()
build_resources()
if len(sys.argv) > 1:
    if sys.argv[1] == "--build_exe":
        build_executable()
