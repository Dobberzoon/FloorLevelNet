import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from network.mynn import Norm2d, Upsample
from network.PosEmbedding import PosEmbedding1D, PosEncoding1D


class HANet_Conv(nn.Module):

    def __init__(self, in_channel, out_channel, kernel_size=3, r_factor=64, layer=3, pos_injection=2, is_encoding=1,
                 pos_rfactor=8, pooling='mean', dropout_prob=0.0, pos_noise=0.0):
        super(HANet_Conv, self).__init__()

        self.pooling = pooling
        self.pos_injection = pos_injection
        self.layer = layer
        self.dropout_prob = dropout_prob
        self.sigmoid = nn.Sigmoid()
        # print(layer)
        # print(in_channel)
        # print(out_channel)
        if r_factor > 0:
            mid_1_channel = math.ceil(in_channel / r_factor)
        elif r_factor < 0:
            r_factor = r_factor * -1
            mid_1_channel = in_channel * r_factor

        if self.dropout_prob > 0:
            self.dropout = nn.Dropout2d(self.dropout_prob)
        # print('mid_1_channel:')
        # print(mid_1_channel)
        # quit()
        # is here about the conv1d !!!
        self.attention_first = nn.Sequential(
            nn.Conv1d(in_channel, out_channel,
                      kernel_size=1, stride=1, padding=0, bias=False),
            #      Norm2d(mid_1_channel),
            #  nn.ReLU(inplace=True)
        )
        layer = 1
        if layer == 2:
            self.attention_second = nn.Sequential(
                nn.Conv1d(in_channels=mid_1_channel, out_channels=out_channel,
                          kernel_size=kernel_size, stride=1, padding=kernel_size // 2, bias=True))
        elif layer == 3:
            mid_2_channel = (mid_1_channel * 2)
            self.attention_second = nn.Sequential(
                nn.Conv1d(in_channels=mid_1_channel, out_channels=mid_2_channel,
                          kernel_size=3, stride=1, padding=1, bias=True),
                Norm2d(mid_2_channel),
                nn.ReLU(inplace=True))
            self.attention_third = nn.Sequential(
                nn.Conv1d(in_channels=mid_2_channel, out_channels=out_channel,
                          kernel_size=kernel_size, stride=1, padding=kernel_size // 2, bias=True))

        if self.pooling == 'mean':
            # print("##### average pooling")
            self.rowpool = nn.AdaptiveAvgPool2d((128 // pos_rfactor, 1))
        else:
            # print("##### max pooling")
            self.rowpool = nn.AdaptiveMaxPool2d((128 // pos_rfactor, 1))

        if pos_rfactor > 0:
            if is_encoding == 0:
                if self.pos_injection == 1:
                    self.pos_emb1d_1st = PosEmbedding1D(pos_rfactor, dim=in_channel, pos_noise=pos_noise)
                elif self.pos_injection == 2:
                    self.pos_emb1d_2nd = PosEmbedding1D(pos_rfactor, dim=mid_1_channel, pos_noise=pos_noise)
            elif is_encoding == 1:
                if self.pos_injection == 1:
                    self.pos_emb1d_1st = PosEncoding1D(pos_rfactor, dim=in_channel, pos_noise=pos_noise)
                elif self.pos_injection == 2:
                    self.pos_emb1d_2nd = PosEncoding1D(pos_rfactor, dim=mid_1_channel, pos_noise=pos_noise)
            else:
                print("Not supported position encoding")
                exit()

    def forward(self, x, out, pos=None, return_attention=False, return_posmap=False, attention_loss=False):
        """
            inputs :
                x : input feature maps( B X C X W X H)
            returns :
                out : self attention value + input feature
                attention: B X N X N (N is Width*Height)
        """
        # print(x.shape)
        H = out.size(2)
        x1d = self.rowpool(x)
        # print(x1d.shape)
        x1d = self.rowpool(x).squeeze(3)
        # print(x1d.shape)

        if pos is not None and self.pos_injection == 1:
            if return_posmap:
                x1d, pos_map1 = self.pos_emb1d_1st(x1d, pos, True)
            else:
                x1d = self.pos_emb1d_1st(x1d, pos)

        if self.dropout_prob > 0:
            x1d = self.dropout(x1d)
        # print(x1d.shape)
        x1d = self.attention_first(x1d)

        if pos is not None and self.pos_injection == 2:
            if return_posmap:
                x1d, pos_map2 = self.pos_emb1d_2nd(x1d, pos, True)
            else:
                x1d = self.pos_emb1d_2nd(x1d, pos)

        # x1d = self.attention_second(x1d)

        if self.layer == 3:
            x1d = self.attention_third(x1d)
            if attention_loss:
                last_attention = x1d
            x1d = self.sigmoid(x1d)
        else:
            if attention_loss:
                last_attention = x1d
            x1d = self.sigmoid(x1d)

        x1d = F.interpolate(x1d, size=H, mode='linear')
        out = torch.mul(out, x1d.unsqueeze(3))

        if return_attention:
            if return_posmap:
                if self.pos_injection == 1:
                    pos_map = (pos_map1)
                elif self.pos_injection == 2:
                    pos_map = (pos_map2)
                return out, x1d, pos_map
            else:
                return out, x1d
        else:
            if attention_loss:
                return out, last_attention
            else:
                return out