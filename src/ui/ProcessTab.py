import subprocess
import os
from threading import Thread
import re

from PySide6 import QtGui
from PySide6.QtGui import QPixmap, QPainter, QPainterPath
from PySide6.QtCore import Qt

from .QTcustom import UpdateGUIThread
from ..Util import pythonPath, currentDirectory, modelsPath, printAndLog, log
from ..DownloadModels import DownloadModel
from .SettingsTab import Settings


class ProcessTab:
    def __init__(self, parent, backend: str, method: str):
        self.parent = parent
        self.imagePreviewSharedMemoryID = "/image_preview" + str(os.getpid())
        self.renderTextOutputList = None
        self.currentFrame = 0
        """
        Key value pairs of the model name in the GUI
        Data inside the tuple:
        [0] = file in models directory
        [1] = file to download
        [2] = upscale times
        [3] = arch
        """
        self.ncnnInterpolateModels = {
            "RIFE 4.6 (Fastest Model)": ("rife-v4.6", "rife-v4.6.tar.gz", 1, "rife46"),
            "RIFE 4.7 (Smoothest Model)": ("rife-v4.7", "rife-v4.7.tar.gz", 1, "rife47"),
            "RIFE 4.15": ("rife-v4.15", "rife-v4.15.tar.gz", 1, "rife413"),
            "RIFE 4.18": ("rife-v4.18", "rife-v4.18.tar.gz", 1, "rife413"),
            "RIFE 4.20": ("rife-v4.20", "rife-v4.20.tar.gz", 1, "rife420"),
            "RIFE 4.21": ("rife-v4.21", "rife-v4.21.tar.gz", 1, "rife421"),
            "RIFE 4.22 (Latest General Model)": ("rife-v4.22", "rife-v4.22.tar.gz", 1, "rife421"),
            "RIFE 4.22-lite (Recommended Model)": (
                "rife-v4.22-lite",
                "rife-v4.22-lite.tar.gz",
                1,
                "rife422-lite",
            ),
        }
        self.pytorchInterpolateModels = {
            "RIFE 4.6 (Fastest Model)": ("rife4.6.pkl", "rife4.6.pkl", 1, "rife46"),
            "RIFE 4.7 (Smoothest Model)": ("rife4.7.pkl", "rife4.7.pkl", 1, "rife47"),
            "RIFE 4.15": ("rife4.15.pkl", "rife4.15.pkl", 1, "rife413"),
            "RIFE 4.18": ("rife4.18.pkl", "rife4.18.pkl", 1, "rife413"),
            "RIFE 4.20": ("rife4.20.pkl", "rife4.20.pkl", 1, "rife420"),
            "RIFE 4.21": ("rife4.21.pkl", "rife4.21.pkl", 1, "rife421"),
            "RIFE 4.22 (Latest General Model)": ("rife4.22.pkl", "rife4.22.pkl", 1, "rife421"),
            "RIFE 4.22-lite (Recommended Model)": (
                "rife4.22-lite.pkl",
                "rife4.22-lite.pkl",
                1,
                "rife422-lite",
            ),
        }
        self.tensorrtInterpolateModels = {
            "RIFE 4.6 (Fastest Model)": ("rife4.6.pkl", "rife4.6.pkl", 1, "rife46"),
            "RIFE 4.7 (Smoothest Model)": ("rife4.7.pkl", "rife4.7.pkl", 1, "rife47"),
            "RIFE 4.15": ("rife4.15.pkl", "rife4.15.pkl", 1, "rife413"),
            "RIFE 4.18": ("rife4.18.pkl", "rife4.18.pkl", 1, "rife413"),
            "RIFE 4.20": ("rife4.20.pkl", "rife4.20.pkl", 1, "rife420"),
            "RIFE 4.21": ("rife4.21.pkl", "rife4.21.pkl", 1, "rife421"),
            "RIFE 4.22 (Latest General Model)": ("rife4.22.pkl", "rife4.22.pkl", 1, "rife421"),
            "RIFE 4.22-lite (Recommended Model)": (
                "rife4.22-lite.pkl",
                "rife4.22-lite.pkl",
                1,
                "rife422-lite",
            ),
        }
        self.ncnnUpscaleModels = {
            "SPAN (Animation) (2X)": (
                "2x_ModernSpanimationV2",
                "2x_ModernSpanimationV2.tar.gz",
                2,
                "SPAN",
            ),
            "SPAN (Realistic) (High Quality Source) (4X)": (
                "4xNomos8k_span_otf_weak",
                "4xNomos8k_span_otf_weak.tar.gz",
                4,
                "SPAN",
            ),
            "SPAN (Realistic) (Medium Quality Source) (4X)": (
                "4xNomos8k_span_otf_medium",
                "4xNomos8k_span_otf_medium.tar.gz",
                4,
                "SPAN",
            ),
            "SPAN (Realistic) (Low Quality Source) (4X)": (
                "4xNomos8k_span_otf_strong",
                "4xNomos8k_span_otf_strong.tar.gz",
                4,
                "SPAN",
            ),
            "Compact (Realistic) (HD Input) (2X)": (
                "2x_OpenProteus_Compact_i2_70K",
                "2x_OpenProteus_Compact_i2_70K.tar.gz",
                2,
                "Compact",
            ),
        }
        self.pytorchUpscaleModels = {
            "SPAN (Animation) (2X)": (
                "2x_ModernSpanimationV2.pth",
                "2x_ModernSpanimationV2.pth",
                2,
                "SPAN",
            ),
            "Sudo Shuffle SPAN (Animation) (2X)": (
                "2xSudoShuffleSPAN.pth",
                "2xSudoShuffleSPAN.pth",
                2,
                "SPAN",
            ),
            "SPAN (Realistic) (High Quality Source) (4X)": (
                "4xNomos8k_span_otf_weak.pth",
                "4xNomos8k_span_otf_weak.pth",
                4,
                "SPAN",
            ),
            "SPAN (Realistic) (Medium Quality Source) (4X)": (
                "4xNomos8k_span_otf_medium.pth",
                "4xNomos8k_span_otf_medium.pth",
                4,
                "SPAN",
            ),
            "SPAN (Realistic) (Low Quality Source) (4X)": (
                "4xNomos8k_span_otf_strong.pth",
                "4xNomos8k_span_otf_strong.pth",
                4,
                "SPAN",
            ),
            "Compact (Realistic) (HD Input) (2X)": (
                "2x_OpenProteus_Compact_i2_70K.pth",
                "2x_OpenProteus_Compact_i2_70K.pth",
                2,
                "Compact",
            ),
        }
        self.tensorrtUpscaleModels = {
            "SPAN (Animation) (2X)": (
                "2x_ModernSpanimationV2.pth",
                "2x_ModernSpanimationV2.pth",
                2,
                "SPAN",
            ),
            "SPAN (Realistic) (High Quality Source) (4X)": (
                "4xNomos8k_span_otf_weak.pth",
                "4xNomos8k_span_otf_weak.pth",
                4,
                "SPAN",
            ),
            "SPAN (Realistic) (Medium Quality Source) (4X)": (
                "4xNomos8k_span_otf_medium.pth",
                "4xNomos8k_span_otf_medium.pth",
                4,
                "SPAN",
            ),
            "SPAN (Realistic) (Low Quality Source) (4X)": (
                "4xNomos8k_span_otf_strong.pth",
                "4xNomos8k_span_otf_strong.pth",
                4,
                "SPAN",
            ),
            "Compact (Realistic) (HD Input) (2X)": (
                "2x_OpenProteus_Compact_i2_70K.pth",
                "2x_OpenProteus_Compact_i2_70K.pth",
                2,
                "Compact",
            ),
        }
        # get default backend
        self.QConnect(method=method, backend=backend)
        self.switchInterpolationAndUpscale(method=method, backend=backend)

    def getTotalModels(self, method: str, backend: str) -> dict:
        """
        returns
        the current models available given a method (interpolate, upscale) and a backend (ncnn, tensorrt, pytorch)
        """
        printAndLog("Getting total models, method: " + method + " backend: " + backend)
        if method == "Interpolate":
            match backend:
                case "ncnn":
                    models = self.ncnnInterpolateModels
                case "pytorch":
                    models = self.pytorchInterpolateModels
                case "tensorrt":
                    models = self.tensorrtInterpolateModels
            self.parent.interpolationContainer.setVisible(True)
        if method == "Upscale":
            match backend:
                case "ncnn":
                    models = self.ncnnUpscaleModels
                case "pytorch":
                    models = self.pytorchUpscaleModels
                case "tensorrt":
                    models = self.tensorrtUpscaleModels
        return models

    def QConnect(self, method: str, backend: str):
        # connect file select buttons
        self.parent.inputFileSelectButton.clicked.connect(self.parent.openInputFile)
        self.parent.outputFileSelectButton.clicked.connect(self.parent.openOutputFolder)
        # connect render button
        self.parent.startRenderButton.clicked.connect(self.parent.startRender)
        cbs = (self.parent.backendComboBox, self.parent.methodComboBox)
        for combobox in cbs:
            combobox.currentIndexChanged.connect(
                lambda: self.switchInterpolationAndUpscale(
                    method=method, backend=backend
                )
            )
        # connect gui switching

        self.parent.inputFileText.textChanged.connect(self.parent.updateVideoGUIDetails)
        self.parent.interpolationMultiplierComboBox.currentTextChanged.connect(
            self.parent.updateVideoGUIDetails
        )

    def killRenderProcess(self):
        try:  # kills  render process if necessary
            self.renderProcess.terminate()
        except AttributeError:
            printAndLog("No render process!")

    def switchInterpolationAndUpscale(self, method: str, backend: str):
        """
        Called every render, gets the correct model based on the backend and the method.
        """

        self.parent.modelComboBox.clear()
        # overwrite method
        method = self.parent.methodComboBox.currentText()
        backend = self.parent.backendComboBox.currentText()
        models = self.getTotalModels(method=method, backend=backend)

        self.parent.modelComboBox.addItems(models)
        total_items = self.parent.modelComboBox.count()
        if total_items > 0 and method.lower() == "interpolate":
            self.parent.modelComboBox.setCurrentIndex(total_items - 1)

        if method.lower() == "interpolate":
            self.parent.interpolationContainer.setVisible(True)
        else:
            self.parent.interpolationContainer.setVisible(False)

        self.parent.updateVideoGUIDetails()

    def run(
        self,
        inputFile: str,
        outputPath: str,
        videoWidth: int,
        videoHeight: int,
        videoFps: float,
        videoFrameCount: int,
        method: str,
        backend: str,
        interpolationTimes: int,
        model: str,
        benchmarkMode: bool,
    ):
        self.inputFile = inputFile
        self.outputPath = outputPath
        self.videoWidth = videoWidth
        self.videoHeight = videoHeight
        self.videoFps = videoFps
        self.videoFrameCount = videoFrameCount
        models = self.getTotalModels(method=method, backend=backend)

        # if upscale or interpolate
        """
        Function to start the rendering process
        It will initially check for any issues with the current setup, (invalid file, no permissions, etc..)
        Then, based on the settings selected, it will build a command that is then passed into rve-backend
        Finally, It will handle the render via ffmpeg. Taking in the frames from pipe and handing them into ffmpeg on a sperate thread
        """
        self.benchmarkMode = benchmarkMode
        # get model attributes
        self.modelFile = models[model][0]
        self.downloadFile = models[model][1]
        self.upscaleTimes = models[model][2]
        self.modelArch = models[model][3]

        # get video attributes
        self.outputVideoWidth = videoWidth * self.upscaleTimes
        self.outputVideoHeight = videoHeight * self.upscaleTimes

        # get most recent settings
        settings = Settings()
        settings.readSettings()
        self.settings = settings.settings

        DownloadModel(
            modelFile=self.modelFile,
            downloadModelFile=self.downloadFile,
            backend=backend,
        )
        # self.ffmpegWriteThread()
        writeThread = Thread(
            target=lambda: self.renderToPipeThread(
                method=method, backend=backend, interpolateTimes=interpolationTimes
            )
        )
        writeThread.start()
        self.startGUIUpdate()

    def startGUIUpdate(self):
        self.workerThread = UpdateGUIThread(
            parent=self,
            imagePreviewSharedMemoryID=self.imagePreviewSharedMemoryID,
            outputVideoHeight=self.outputVideoHeight,
            outputVideoWidth=self.outputVideoWidth,
        )
        self.workerThread.latestPreviewPixmap.connect(self.updateProcessTab)
        self.workerThread.finished.connect(self.workerThread.deleteLater)
        self.workerThread.finished.connect(self.workerThread.quit)
        self.workerThread.finished.connect(
            self.workerThread.wait
        )  # need quit and wait to allow process to exit safely
        self.workerThread.start()

    def onRenderCompletion(self):
        self.workerThread.stop()
        self.workerThread.quit()
        self.workerThread.wait()
        # reset image preview
        self.parent.previewLabel.clear()
        self.parent.startRenderButton.setEnabled(True)
        self.parent.enableProcessPage()

    def splitListIntoStringWithNewLines(self, string_list: list[str]):
        # Join the strings with newline characters
        return "\n".join(string_list)
        # Set the text to the QTextEdit

    def renderToPipeThread(self, method: str, backend: str, interpolateTimes: int):
        # builds command
        command = [
            f"{pythonPath()}",
            "-W",
            "ignore",
            os.path.join(currentDirectory(), "backend", "rve-backend.py"),
            "-i",
            self.inputFile,
            "-o",
            f"{self.outputPath}",
            "-b",
            f"{backend}",
            "--precision",
            f"{self.settings['precision']}",
            "--custom_encoder",
            f"-c:v {self.settings['encoder']}",
            "--tensorrt_opt_profile",
            f"{self.settings['tensorrt_optimization_level']}",
        ]
        if method == "Upscale":
            command += [
                "--upscaleModel",
                os.path.join(modelsPath(), self.modelFile),
                "--interpolateFactor",
                "1",
            ]
        if method == "Interpolate":
            command += [
                "--interpolateModel",
                os.path.join(
                    modelsPath(),
                    self.modelFile,
                ),
                "--interpolateFactor",
                f"{interpolateTimes}",
            ]
        if self.settings["preview_enabled"] == "True":
            command += [
                "--shared_memory_id",
                f"{self.imagePreviewSharedMemoryID}",
            ]
        if self.settings["scene_change_detection_enabled"] == "False":
            command += ["--sceneDetectMethod","none"]
        if self.benchmarkMode:
            command += ["--benchmark"]
        self.renderProcess = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        textOutput = []
        for line in iter(self.renderProcess.stdout.readline, b""):
            if self.renderProcess.poll() is not None:
                break  # Exit the loop if the process has terminated
            line = str(line.strip())
            if "it/s" in line:
                textOutput = textOutput[:-1]
            if "FPS" in line:
                textOutput = textOutput[
                    :-2
                ]  # slice the list to only get the last updated data
                self.currentFrame = int(
                    re.search(r"Current Frame: (\d+)", line).group(1)
                )
            textOutput.append(line)
            # self.setRenderOutputContent(textOutput)
            self.renderTextOutputList = textOutput.copy()
            if "Time to complete render" in line:
                break
        log(str(textOutput))
        self.renderProcess.wait()
        # done with render
        self.onRenderCompletion()

    def getRoundedPixmap(self, pixmap, corner_radius):
        size = pixmap.size()
        mask = QPixmap(size)
        mask.fill(Qt.transparent)  # type: ignore

        painter = QPainter(mask)
        painter.setRenderHint(QPainter.Antialiasing)  # type: ignore
        painter.setRenderHint(QPainter.SmoothPixmapTransform)  # type: ignore

        path = QPainterPath()
        path.addRoundedRect(
            0, 0, size.width(), size.height(), corner_radius, corner_radius
        )

        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        rounded_pixmap = QPixmap(size)
        rounded_pixmap.fill(Qt.transparent)  # type: ignore

        painter = QPainter(rounded_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)  # type: ignore
        painter.setRenderHint(QPainter.SmoothPixmapTransform)  # type: ignore
        painter.drawPixmap(0, 0, mask)
        painter.end()

        return rounded_pixmap

    def modelNameToFile(self):
        pass

    def updateProcessTab(self, qimage: QtGui.QImage):
        """
        Called by the worker QThread, and updates the GUI elements: Progressbar, Preview, FPS
        """

        if self.renderTextOutputList is not None:
            # print(self.renderTextOutputList)
            self.parent.renderOutput.setPlainText(
                self.splitListIntoStringWithNewLines(self.renderTextOutputList)
            )
            scrollbar = self.parent.renderOutput.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            self.parent.progressBar.setValue(self.currentFrame)
        if not qimage.isNull():
            width = self.parent.width()
            height = self.parent.height()

            p = qimage.scaled(width / 2, height / 2, Qt.AspectRatioMode.KeepAspectRatio)  # type: ignore
            pixmap = QtGui.QPixmap.fromImage(p)
            roundedPixmap = self.getRoundedPixmap(pixmap, corner_radius=10)
            self.parent.previewLabel.setPixmap(roundedPixmap)
