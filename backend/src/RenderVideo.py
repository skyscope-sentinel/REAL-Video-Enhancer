from threading import Thread
from queue import Queue, Empty
from multiprocessing import shared_memory
import os
import math

from .FFmpeg import FFMpegRender
from .SceneDetect import SceneDetect
from .Util import printAndLog, log

# try/except imports
try:
    from .UpscaleNCNN import UpscaleNCNN, getNCNNScale
    from .InterpolateNCNN import InterpolateRIFENCNN
except ImportError:
    log("WARN: unable to import ncnn.")

try:
    from .InterpolateTorch import InterpolateRifeTorch
    from .UpscaleTorch import UpscalePytorch
except ImportError:
    log("WARN: unable to import pytorch.")


class Render(FFMpegRender):
    """
    Subclass of FFmpegRender
    FFMpegRender options:
    inputFile: str, The path to the input file.
    outputFile: str, The path to the output file.
    interpolateTimes: int, this sets the multiplier for the framerate when interpolating, when only upscaling this will be set to 1.
    encoder: str, The exact name of the encoder ffmpeg will use (default=libx264)
    pixelFormat: str, The pixel format ffmpeg will use, (default=yuv420p)

    RenderOptions:
    interpolationMethod
    upscaleModel
    backend (pytorch,ncnn,tensorrt)
    device (cpu,cuda)
    precision (float16,float32)

    NOTE:
    Everything in here has to happen in a specific order:
    Get the video properties (res,fps,etc)
    set up upscaling/interpolation, this gets the scale for upscaling if upscaling is the current task
    assign framechunksize to a value, as this is needed to catch bytes and set up shared memory
    set up shared memory
    """

    def __init__(
        self,
        inputFile: str,
        outputFile: str,
        # backend settings
        backend="pytorch",
        device="default",
        precision="float16",
        # model settings
        upscaleModel=None,
        interpolateModel=None,
        interpolateFactor: int = 1,
        # ffmpeg settings
        encoder: str = "libx264",
        pixelFormat: str = "yuv420p",
        benchmark: bool = False,
        overwrite: bool = False,
        crf: str = "18",
        # misc
        sceneDetectMethod: str = "pyscenedetect",
        sceneDetectSensitivity: float = 3.0,
        sharedMemoryID: str = None,
        trt_optimization_level: int = 3,
    ):
        self.inputFile = inputFile
        self.backend = backend
        self.upscaleModel = upscaleModel
        self.interpolateModel = interpolateModel
        self.device = device
        self.precision = precision
        self.upscaleTimes = 1  # if no upscaling, it will default to 1
        self.interpolateFactor = interpolateFactor
        self.ceilInterpolateFactor = math.ceil(self.interpolateFactor)
        self.setupRender = self.returnFrame  # set it to not convert the bytes to array by default, and just pass chunk through
        self.frame0 = None
        self.sceneDetectMethod = sceneDetectMethod
        self.sceneDetectSensitivty = sceneDetectSensitivity
        self.sharedMemoryID = sharedMemoryID
        self.trt_optimization_level = trt_optimization_level
        # get video properties early
        self.getVideoProperties(inputFile)

        printAndLog("Using backend: " + self.backend)
        if upscaleModel:
            self.setupUpscale()
            self.renderThread = Thread(target=self.renderUpscale)
            printAndLog("Using Upscaling Model: " + self.upscaleModel)
        if interpolateModel:
            self.setupInterpolate()
            self.renderThread = Thread(target=self.renderInterpolate)
            printAndLog("Using Interpolation Model: " + self.interpolateModel)

        self.inputFrameChunkSize = self.width * self.height * 3
        self.outputFrameChunkSize = (
            self.width * self.upscaleTimes * self.height * self.upscaleTimes * 3
        )
        self.shm = shared_memory.SharedMemory(
            name=self.sharedMemoryID, create=True, size=self.outputFrameChunkSize
        )
        super().__init__(
            inputFile=inputFile,
            outputFile=outputFile,
            interpolateFactor=interpolateFactor,
            upscaleTimes=self.upscaleTimes,
            encoder=encoder,
            pixelFormat=pixelFormat,
            benchmark=benchmark,
            overwrite=overwrite,
            frameSetupFunction=self.setupRender,
            crf=crf,
            sharedMemoryID=sharedMemoryID,
            shm=self.shm,
            inputFrameChunkSize=self.inputFrameChunkSize,
            outputFrameChunkSize=self.outputFrameChunkSize,
        )

        self.sharedMemoryThread = Thread(
            target=lambda: self.writeOutInformation(self.outputFrameChunkSize)
        )
        self.sharedMemoryThread.start()
        self.ffmpegReadThread = Thread(target=self.readinVideoFrames)
        self.ffmpegWriteThread = Thread(target=self.writeOutVideoFrames)

        self.ffmpegReadThread.start()
        self.ffmpegWriteThread.start()
        self.renderThread.start()

    def renderUpscale(self):
        """
        self.setupRender, method that is mapped to the bytesToFrame in each respective backend
        self.upscale, method that takes in a chunk, and outputs an array that can be sent to ffmpeg
        """
        log("Starting Upscale")
        for i in range(self.totalInputFrames - 1):
            frame = self.readQueue.get()
            frame = self.upscale(self.frameSetupFunction(frame))
            self.writeQueue.put(frame)
        self.writeQueue.put(None)
        log("Finished Upscale")

    def renderInterpolate(self):
        """Method that performs interpolation between frames.\n
        This method takes in a chunk of frames and outputs an array that can be sent to ffmpeg.\n
        It starts by setting up the initial frame (frame0) using the frameSetupFunction.\n
        Then, for each frame in the input frames, it retrieves the next frame (frame1) from the readQueue.\n
        If frame1 is None, the loop breaks.\n
        If the current frame number is not the transitionFrame, it performs interpolation by calling the interpolate method.\n
        The interpolation is done by generating intermediate frames between frame0 and frame1 using the interpolateFactor.\n
        The resulting frames are then added to the writeQueue.\n
        If the current frame number is the transitionFrame, it uncaches the cached frame and adds it to the writeQueue.\n
        After each iteration, frame0 is updated to setup_frame1.\n
        Finally, None is added to the writeQueue to signal the end of interpolation.\n
        *NOTE:
        - The frameSetupFunction is used to convert the frames to the desired format.
        - The transitionFrame is obtained from the transitionQueue.
        - The interpolate method performs the actual interpolation between frames.
        Returns:
        None
        """

        log("Starting Interpolation")
        try:
            self.transitionFrame = self.transitionQueue.get()
        except AttributeError:
            self.transitionFrame = -1  # if there is no transition queue, set it to -1
        self.frame0 = self.frameSetupFunction(self.readQueue.get())

        for frameNum in range(self.totalInputFrames - 1):
            frame1 = self.readQueue.get()
            if frame1 is None:
                break
            setup_frame1 = self.frameSetupFunction(frame1)
            if frameNum != self.transitionFrame:
                for n in range(self.ceilInterpolateFactor):
                    timestep = 1 / (self.ceilInterpolateFactor - n)
                    if timestep == 1:
                        self.writeQueue.put(frame1)
                        continue

                    frame = self.interpolate(self.frame0, setup_frame1, timestep)
                    self.writeQueue.put(frame)
            else:
                # uncache the cached frame
                self.undoSetup(frame1)
                for n in range(self.ceilInterpolateFactor):
                    self.writeQueue.put(frame1)
                try:  # get_nowait sends an error out of the queue is empty, I would like a better solution than this though
                    self.transitionFrame = self.transitionQueue.get_nowait()
                except Empty:
                    self.transitionFrame = None
            self.frame0 = setup_frame1

        self.writeQueue.put(None)
        log("Finished Interpolation")

    def setupUpscale(self):
        """
        This is called to setup an upscaling model if it exists.
        Maps the self.upscaleTimes to the actual scale of the model
        Maps the self.setupRender function that can setup frames to be rendered
        Maps the self.upscale the upscale function in the respective backend.
        For interpolation:
        Mapss the self.undoSetup to the tensor_to_frame function, which undoes the prep done in the FFMpeg thread. Used for SCDetect
        """
        printAndLog("Setting up Upscale")
        if self.backend == "pytorch" or self.backend == "tensorrt":
            upscalePytorch = UpscalePytorch(
                self.upscaleModel,
                device=self.device,
                precision=self.precision,
                width=self.width,
                height=self.height,
                backend=self.backend,
            )
            self.upscaleTimes = upscalePytorch.getScale()
            self.setupRender = upscalePytorch.bytesToFrame
            self.upscale = upscalePytorch.renderToNPArray

        if self.backend == "ncnn":
            path, last_folder = os.path.split(self.upscaleModel)

            self.upscaleModel = os.path.join(path, last_folder, last_folder)

            self.upscaleTimes = getNCNNScale(modelPath=self.upscaleModel)
            upscaleNCNN = UpscaleNCNN(
                modelPath=self.upscaleModel,
                num_threads=1,
                scale=self.upscaleTimes,
                gpuid=0,  # might have this be a setting
                width=self.width,
                height=self.height,
            )
            self.setupRender = self.returnFrame
            self.upscale = upscaleNCNN.Upscale

    def setupInterpolate(self):
        log("Setting up Interpolation")

        if self.sceneDetectMethod != "none":
            printAndLog("Detecting Transitions")
            scdetect = SceneDetect(
                inputFile=self.inputFile,
                sceneChangeSensitivity=self.sceneDetectSensitivty,
                sceneChangeMethod=self.sceneDetectMethod,
            )
            self.transitionQueue = scdetect.getTransitions()
        else:
            self.transitionQueue = None
        if self.backend == "ncnn":
            interpolateRifeNCNN = InterpolateRIFENCNN(
                interpolateModelPath=self.interpolateModel,
                width=self.width,
                height=self.height,
            )
            self.setupRender = self.returnFrame
            self.undoSetup = interpolateRifeNCNN.uncacheFrame
            self.interpolate = interpolateRifeNCNN.process
        if self.backend == "pytorch" or self.backend == "tensorrt":
            interpolateRifePytorch = InterpolateRifeTorch(
                interpolateModelPath=self.interpolateModel,
                ceilInterpolateFactor=self.ceilInterpolateFactor,
                width=self.width,
                height=self.height,
                device=self.device,
                dtype=self.precision,
                backend=self.backend,
                trt_optimization_level=self.trt_optimization_level,
            )
            self.setupRender = interpolateRifePytorch.frame_to_tensor
            self.undoSetup = self.returnFrame
            self.interpolate = interpolateRifePytorch.process
