import cv2
import os
import subprocess
import queue
import sys
import time
import math
from tqdm import tqdm
from multiprocessing import shared_memory
from .Util import currentDirectory, log, printAndLog


class FFMpegRender:
    """Args:
        inputFile (str): The path to the input file.
        outputFile (str): The path to the output file.
        interpolateFactor (int, optional): Sets the multiplier for the framerate when interpolating. Defaults to 1.
        upscaleTimes (int, optional): Upscaling factor. Defaults to 1.
        encoder (str, optional): The exact name of the encoder ffmpeg will use. Defaults to "libx264".
        pixelFormat (str, optional): The pixel format ffmpeg will use. Defaults to "yuv420p".
        benchmark (bool, optional): Enable benchmark mode. Defaults to False.
        overwrite (bool, optional): Overwrite existing output file if it exists. Defaults to False.
        frameSetupFunction (function, optional): Function to setup frames. Defaults to None.
        crf (str, optional): Constant Rate Factor for video quality. Defaults to "18".
        sharedMemoryID (str, optional): ID for shared memory. Defaults to None.
        shm (shared_memory.SharedMemory, optional): Shared memory object. Defaults to None.
        inputFrameChunkSize (int, optional): Size of input frame chunks. Defaults to None.
        outputFrameChunkSize (int, optional): Size of output frame chunks. Defaults to None.
    pass
    Gets the properties of the video file.
    Args:
        inputFile (str, optional): The path to the input file. If None, uses the inputFile specified in the constructor. Defaults to None.
    pass
    Generates the FFmpeg command for reading video frames.
    Returns:
        list: The FFmpeg command for reading video frames.
    pass
    Generates the FFmpeg command for writing video frames.
    Returns:
        list: The FFmpeg command for writing video frames.
    pass
    Starts reading video frames using FFmpeg.
    pass
    Returns a frame.
    Args:
        frame: The frame to be returned.
    Returns:
        The returned frame.
    pass
    Prints data in real-time.
    Args:
        data: The data to be printed.
    pass
    Writes frames to shared memory.
    Args:
        fcs: The frame chunk size.
    pass
    Writes out video frames using FFmpeg.
    pass"""

    def __init__(
        self,
        inputFile: str,
        outputFile: str,
        interpolateFactor: int = 1,
        upscaleTimes: int = 1,
        encoder: str = "libx264",
        pixelFormat: str = "yuv420p",
        benchmark: bool = False,
        overwrite: bool = False,
        frameSetupFunction=None,
        crf: str = "18",
        sharedMemoryID: str = None,
        shm: shared_memory.SharedMemory = None,
        inputFrameChunkSize: int = None,
        outputFrameChunkSize: int = None,
    ):
        """
        Generates FFmpeg I/O commands to be used with VideoIO
        Options:
        inputFile: str, The path to the input file.
        outputFile: str, The path to the output file.
        interpolateTimes: int, this sets the multiplier for the framerate when interpolating, when only upscaling this will be set to 1.
        upscaleTimes: int,
        encoder: str, The exact name of the encoder ffmpeg will use (default=libx264)
        pixelFormat: str, The pixel format ffmpeg will use, (default=yuv420p)
        overwrite: bool, overwrite existing output file if it exists
        """
        self.inputFile = inputFile
        self.outputFile = outputFile

        # upsacletimes will be set to the scale of the loaded model with spandrel
        self.upscaleTimes = upscaleTimes
        self.interpolateFactor = interpolateFactor
        self.ceilInterpolateFactor = math.ceil(self.interpolateFactor)
        self.encoder = encoder
        self.pixelFormat = pixelFormat
        self.benchmark = benchmark
        self.overwrite = overwrite
        self.readingDone = False
        self.writingDone = False
        self.writeOutPipe = False
        self.previewFrame = None
        self.crf = crf
        self.frameSetupFunction = frameSetupFunction
        self.sharedMemoryID = sharedMemoryID
        self.shm = shm
        self.inputFrameChunkSize = inputFrameChunkSize
        self.outputFrameChunkSize = outputFrameChunkSize
        
        self.totalOutputFrames = self.totalInputFrames * self.ceilInterpolateFactor

        self.writeOutPipe = self.outputFile == "PIPE"

        self.readQueue = queue.Queue(maxsize=50)
        self.writeQueue = queue.Queue(maxsize=50)

    def getVideoProperties(self, inputFile: str = None):
        log("Getting Video Properties...")
        if inputFile is None:
            cap = cv2.VideoCapture(self.inputFile)
        else:
            cap = cv2.VideoCapture(inputFile)
        if not cap.isOpened():
            print("Error: Could not open video.")
            exit()

        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.totalInputFrames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = cap.get(cv2.CAP_PROP_FPS)

        self.outputFrameChunkSize = None

    def getFFmpegReadCommand(self):
        log("Generating FFmpeg READ command...")
        command = [
            f"{os.path.join(currentDirectory(),'bin','ffmpeg')}",
            "-i",
            f"{self.inputFile}",
            "-f",
            "image2pipe",
            "-pix_fmt",
            "rgb24",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{self.width}x{self.height}",
            "-",
        ]
        return command

    def getFFmpegWriteCommand(self):
        log("Generating FFmpeg WRITE command...")
        if not self.benchmark:
            # maybe i can split this so i can just use ffmpeg normally like with vspipe
            command = [
                f"{os.path.join(currentDirectory(),'bin','ffmpeg')}",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-vcodec",
                "rawvideo",
                "-s",
                f"{self.width * self.upscaleTimes}x{self.height * self.upscaleTimes}",
                "-r",
                f"{self.fps * self.ceilInterpolateFactor}",
                "-i",
                "-",
                "-i",
                f"{self.inputFile}",
                "-r",
                f"{self.fps * self.interpolateFactor}",
                f"-crf",
                f"{self.crf}",
                "-pix_fmt",
                self.pixelFormat,
                "-c:a",
                "copy",
                "-loglevel",
                "error",
            ]
            for i in self.encoder.split():
                command.append(i)
            command.append(
                f"{self.outputFile}",
            )

            if self.overwrite:
                command.append("-y")
            return command

    def readinVideoFrames(self):
        log("Starting Video Read")
        self.readProcess = subprocess.Popen(
            self.getFFmpegReadCommand(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        for i in range(self.totalInputFrames - 1):
            chunk = self.readProcess.stdout.read(self.inputFrameChunkSize)
            self.readQueue.put(chunk)
        log("Ending Video Read")
        self.readQueue.put(None)
        self.readingDone = True
        self.readProcess.stdout.close()
        self.readProcess.terminate()

    def returnFrame(self, frame):
        return frame

    def realTimePrint(self, data):
        data = str(data)
        # Clear the last line
        sys.stdout.write("\r" + " " * self.last_length)
        sys.stdout.flush()

        # Write the new line
        sys.stdout.write("\r" + data)
        sys.stdout.flush()

        # Update the length of the last printed line
        self.last_length = len(data)

    def writeOutInformation(self, fcs):
        """
        fcs = framechunksize
        """
        # Create a shared memory block

        buffer = self.shm.buf

        log(f"Shared memory name: {self.shm.name}")
        while True:
            if self.writingDone:
                self.shm.close()
                self.shm.unlink()
                break
            if self.previewFrame is not None:
                # print out data to stdout
                fps = round(self.currentFrame / (time.time() - self.startTime))
                message = f"FPS: {fps} Current Frame: {self.currentFrame}"
                self.realTimePrint(message)
                if self.sharedMemoryID is not None:
                    # Update the shared array
                    buffer[:fcs] = bytes(self.previewFrame)

            time.sleep(0.1)

    def writeOutVideoFrames(self):
        """
        Writes out frames either to ffmpeg or to pipe
        This is determined by the --output command, which if the PIPE parameter is set, it outputs the chunk to pipe.
        A command like this is required,
        ffmpeg -f rawvideo -pix_fmt rgb24 -s 1920x1080 -framerate 24 -i - -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a copy out.mp4
        """
        log("Rendering")
        #
        self.startTime = time.time()
        self.currentFrame: int = 0
        self.last_length: int = 0

        if self.benchmark:
            # pbar = tqdm(total=self.totalOutputFrames)
            while True:
                frame = self.writeQueue.get()
                self.previewFrame = frame
                if frame is None:
                    break
                # pbar.update(1)
                self.currentFrame += 1
        else:
            self.writeProcess = subprocess.Popen(
                self.getFFmpegWriteCommand(),
                stdin=subprocess.PIPE,
                text=True,
                universal_newlines=True,
            )
            while True:
                frame = self.writeQueue.get()

                if frame is None:
                    break
                self.writeProcess.stdin.buffer.write(frame)
                # Update other variables
                self.previewFrame = frame
                # Update progress bar
                # pbar.update(1)
                self.currentFrame += 1
            self.writeProcess.stdin.close()
            self.writeProcess.wait()

        renderTime = time.time() - self.startTime
        self.writingDone = True
        printAndLog(f"\nTime to complete render: {round(renderTime, 2)}")
