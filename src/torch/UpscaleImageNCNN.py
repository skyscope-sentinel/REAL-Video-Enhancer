from upscale_ncnn_py import UPSCALE
from realcugan_ncnn_py import Realcugan
import numpy as np
import ncnn
import cv2
class UpscaleNCNN:
    def __init__(self, model: str, num_threads, scale, gpuid=0, width=1920, height=1080):
        '''self.model = UPSCALE(
            gpuid=gpuid, model_str=model, num_threads=num_threads, scale=scale
        )'''
        self.width = width
        self.height = height
        model = model + '.param'
        self.net = ncnn.Net()
        self.net.opt.use_vulkan_compute = True
        self.net.load_param(model.replace('.bin','.param'))
        self.net.load_model(model.replace('.param','.bin'))
        

        

    def ProcessNCNN(self,npArrayImage)-> np.asarray:
        ex = self.net.create_extractor()
        mat_in = ncnn.Mat.from_pixels(
            npArrayImage,
            ncnn.Mat.PixelType.PIXEL_BGR,
            self.width,
            self.height,
        )

        # norm
        mean_vals = []
        norm_vals = [1 / 255.0, 1 / 255.0, 1 / 255.0]
        mat_in.substract_mean_normalize(mean_vals, norm_vals)

        
        # Make sure the input and output names match the param file
        ex.input("data", mat_in)
        ret, mat_out = ex.extract("output")
        out = np.array(mat_out)
        # Transpose the output from `c, h, w` to `h, w, c` and put it back in 0-255 range
        output = out.transpose(1, 2, 0) * 255
        
        return np.ascontiguousarray(output,dtype=np.uint8)
        


    def UpscaleImage(self, image):
        image = np.ascontiguousarray(
            np.frombuffer(image, dtype=np.uint8).reshape(self.height, self.width, 3)
        )

        return self.ProcessNCNN(image)


class UpscaleCuganNCNN:
    def __init__(
        self,
        model="models-se",
        models_path="",
        num_threads=2,
        scale=2,
        gpuid=0,
        noise=0,
        width: int = 1920,
        height: int = 1080,
    ):
        self.width = width
        self.height = height
        self.model = Realcugan(
            gpuid=gpuid,
            models_path=models_path,
            model=model,
            scale=scale,
            num_threads=num_threads,
            noise=noise,
        )

    def UpscaleImage(self, image):
        image = np.ascontiguousarray(
            np.frombuffer(image, dtype=np.uint8).reshape(self.height, self.width, 3)
        )
        return np.ascontiguousarray(self.model.process_cv2(image))
