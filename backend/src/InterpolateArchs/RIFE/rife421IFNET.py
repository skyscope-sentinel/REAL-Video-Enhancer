import torch
import torch.nn as nn

try:
    from .interpolate import interpolate
except ImportError:
    from torch.nn.functional import interpolate


class MyPixelShuffle(nn.Module):
    def __init__(self, upscale_factor):
        super(MyPixelShuffle, self).__init__()
        self.upscale_factor = upscale_factor

    def forward(self, input):
        b, c, hh, hw = input.size()
        out_channel = c // (self.upscale_factor**2)
        h = hh * self.upscale_factor
        w = hw * self.upscale_factor
        x_view = input.view(
            b, out_channel, self.upscale_factor, self.upscale_factor, hh, hw
        )
        return x_view.permute(0, 1, 4, 2, 5, 3).reshape(b, out_channel, h, w)


def conv(in_planes, out_planes, kernel_size=3, stride=1, padding=1, dilation=1):
    return nn.Sequential(
        nn.Conv2d(
            in_planes,
            out_planes,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            bias=True,
        ),
        nn.LeakyReLU(0.2, True),
    )


class Head(nn.Module):
    def __init__(self):
        super(Head, self).__init__()
        self.cnn0 = nn.Conv2d(3, 32, 3, 2, 1)
        self.cnn1 = nn.Conv2d(32, 32, 3, 1, 1)
        self.cnn2 = nn.Conv2d(32, 32, 3, 1, 1)
        self.cnn3 = nn.ConvTranspose2d(32, 8, 4, 2, 1)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x, feat=False):
        x0 = self.cnn0(x)
        x = self.relu(x0)
        x1 = self.cnn1(x)
        x = self.relu(x1)
        x2 = self.cnn2(x)
        x = self.relu(x2)
        x3 = self.cnn3(x)
        if feat:
            return [x0, x1, x2, x3]
        return x3


class ResConv(nn.Module):
    def __init__(self, c):
        super(ResConv, self).__init__()
        self.conv = nn.Conv2d(c, c, 3, 1, padding=1)
        self.beta = nn.Parameter(torch.ones((1, c, 1, 1)), requires_grad=True)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        return self.relu(self.conv(x) * self.beta + x)


class IFBlock(nn.Module):
    def __init__(self, in_planes, c=64):
        super(IFBlock, self).__init__()
        self.conv0 = nn.Sequential(
            conv(in_planes, out_planes=c // 2, kernel_size=3, stride=2, padding=1),
            conv(c // 2, out_planes=c, kernel_size=3, stride=2, padding=1),
        )
        self.convblock = nn.Sequential(
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
        )
        self.lastconv = nn.Sequential(
            nn.ConvTranspose2d(
                in_channels=c, out_channels=4 * 13, kernel_size=4, stride=2, padding=1
            ),
            MyPixelShuffle(upscale_factor=2),
        )
        self.in_planes = in_planes

    def forward(self, x, scale=1):
        if scale != 1:
            x = interpolate(
                x, scale_factor=1 / scale, mode="bilinear", align_corners=False
            )

        feat = self.conv0(x)
        feat = self.convblock(feat)
        tmp = self.lastconv(feat)
        if scale != 1:
            tmp = interpolate(
                tmp, scale_factor=scale, mode="bilinear", align_corners=False
            )

        # flows, mask, _ = torch.split(tmp, split_size_or_sections=[4, 1, 1], dim=1)
        flow = tmp[:, :4]
        mask = tmp[:, 4:5]
        feat = tmp[:, 5:]
        if scale != 1:
            flow = flow * scale

        return flow, mask, feat


class IFNet(nn.Module):
    def __init__(
        self,
        scale=1.0,
        ensemble=False,
        dtype=torch.float32,
        device="cuda",
        width=1920,
        height=1080,
        backwarp_tenGrid=None,
        tenFlow_div=None,
    ):
        super(IFNet, self).__init__()
        self.block0 = IFBlock(7 + 16, c=256)
        self.block1 = IFBlock(8 + 4 + 16 + 8, c=192)
        self.block2 = IFBlock(8 + 4 + 16 + 8, c=96)
        self.block3 = IFBlock(8 + 4 + 16 + 8, c=48)
        self.encode = Head()
        self.device = device
        self.dtype = dtype
        self.scale_list = [8 / scale, 4 / scale, 2 / scale, 1 / scale]
        self.ensemble = ensemble
        self.width = width
        self.height = height
        self.backwarp_tenGrid = backwarp_tenGrid
        self.tenFlow_div = tenFlow_div

    def forward(self, img0, img1, timestep):
        # cant be cached
        h, w = img0.shape[2], img0.shape[3]
        imgs = torch.cat([img0, img1], dim=1)
        imgs_2 = torch.reshape(imgs, (2, 3, h, w))
        fs_2 = self.encode(imgs_2)
        fs = torch.reshape(fs_2, (1, 16, h, w))
        if self.ensemble:
            fs_rev = torch.cat(torch.split(fs, [8, 8], dim=1)[::-1], dim=1)
            imgs_rev = torch.cat([img1, img0], dim=1)

        warped_img0 = img0
        warped_img1 = img1
        flows = None
        flows = None
        blocks = [self.block0, self.block1, self.block2, self.block3]
        scale_list = [8, 4, 2, 1]
        for block, scale in zip(blocks, scale_list):
            if flows is None:
                temp = torch.cat((imgs, fs, timestep), 1)
                flows, mask, feat = block(temp, scale=scale)
            else:
                temp = torch.cat(
                    (
                        wimg,
                        wf,
                        timestep,
                        mask,
                        feat,
                        (flows * (1 / scale) if scale != 1 else flows),
                    ),
                    1,
                )
                fds, mask, feat = block(temp, scale=scale)

                flows = flows + fds

                if self.ensemble:
                    flows_rev = torch.cat(
                        torch.split(flows, [2, 2], dim=1)[::-1], dim=1
                    )
            precomp = (
                self.backwarp_tenGrid + flows.reshape((2, 2, h, w)) * self.tenFlow_div
            ).permute(0, 2, 3, 1)
            if scale == 1:
                warped_imgs = torch.nn.functional.grid_sample(
                    imgs_2,
                    precomp,
                    mode="bilinear",
                    padding_mode="border",
                    align_corners=True,
                )
            else:
                imgs_fs_2 = torch.cat((imgs_2, fs_2), 1)
                warps = torch.nn.functional.grid_sample(
                    imgs_fs_2,
                    precomp,
                    mode="bilinear",
                    padding_mode="border",
                    align_corners=True,
                )
                wimg, wf = torch.split(warps, [3, 8], dim=1)
                wimg = torch.reshape(wimg, (1, 6, h, w))
                wf = torch.reshape(wf, (1, 16, h, w))

        mask = torch.sigmoid(mask)
        warped_img0, warped_img1 = torch.split(warped_imgs, [1, 1])
        frame = warped_img0 * mask + warped_img1 * (1 - mask)
        frame = frame[:, :, : self.height, : self.width][0]
        return frame.squeeze(0).permute(1, 2, 0).mul(255).float()
