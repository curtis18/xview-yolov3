import glob
import math
import os
import random

import cv2
import numpy as np
import scipy.io
import torch

# from torch.utils.data import Dataset
from utils.utils import xyxy2xywh


class ImageFolder():  # for eval-only
    def __init__(self, path, batch_size=1, img_size=416):
        if os.path.isdir(path):
            self.files = sorted(glob.glob('%s/*.*' % path))
        elif os.path.isfile(path):
            self.files = [path]

        self.nF = len(self.files)  # number of image files
        self.nB = math.ceil(self.nF / batch_size)  # number of batches
        self.batch_size = batch_size
        self.height = img_size
        assert self.nF > 0, 'No images found in path %s' % path

        # RGB normalization values
        self.rgb_mean = np.array([60.134, 49.697, 40.746], dtype=np.float32).reshape((3, 1, 1))
        self.rgb_std = np.array([29.99, 24.498, 22.046], dtype=np.float32).reshape((3, 1, 1))

    def __iter__(self):
        self.count = -1
        return self

    def __next__(self):
        self.count += 1
        if self.count == self.nB:
            raise StopIteration
        img_path = self.files[self.count]

        # Add padding
        img = cv2.imread(img_path)  # BGR
        # img = resize_square(img, height=self.height)

        # import matplotlib.pyplot as plt
        # plt.subplot(2, 2, 1).imshow(img[:, :, ::-1])
        # img = random_affine(img, degrees=(-89, 89), translate=(.2, .2), scale=(1, 1), shear=(0, 0))
        # plt.subplot(2, 2, 3).imshow(img[:, :, ::-1])

        # Normalize RGB
        img = img[:, :, ::-1].transpose(2, 0, 1).astype(np.float32)
        img -= self.rgb_mean
        img /= self.rgb_std

        return [img_path], img

    def __len__(self):
        return self.nB  # number of batches


class ListDataset_xview_fast():  # for training
    def __init__(self, folder_path, batch_size=1, img_size=416):
        p = folder_path + 'train_images'
        self.files = sorted(glob.glob('%s/*.bmp' % p))
        self.nF = len(self.files)  # number of image files
        self.nB = math.ceil(self.nF / batch_size)  # number of batches
        self.batch_size = batch_size
        assert self.nB > 0, 'No images found in path %s' % p
        self.height = img_size
        # load targets
        self.mat = scipy.io.loadmat('utils/targets_60c.mat')
        self.mat['id'] = self.mat['id'].squeeze()
        # make folder for reduced size images
        self.small_folder = p + '_' + str(img_size) + '/'
        os.makedirs(self.small_folder, exist_ok=True)

        # RGB normalization values
        self.rgb_mean = np.array([60.134, 49.697, 40.746], dtype=np.float32).reshape((1, 3, 1, 1))
        self.rgb_std = np.array([29.99, 24.498, 22.046], dtype=np.float32).reshape((1, 3, 1, 1))

    def __iter__(self):
        self.count = -1
        self.shuffled_vector = np.random.permutation(self.nF)  # shuffled vector
        return self

    # @profile
    def __next__(self):
        self.count += 1
        if self.count == self.nB:
            raise StopIteration

        ia = self.count * self.batch_size
        ib = min((self.count + 1) * self.batch_size, self.nF)
        indices = list(range(ia, ib))

        img_all = []  # np.zeros((len(indices), self.height, self.height, 3), dtype=np.uint8)
        labels_all = []
        for index, files_index in enumerate(indices):
            img_path = self.files[self.shuffled_vector[files_index]]  # BGR

            # load labels
            chip = img_path.rsplit('/')[-1]
            i = np.nonzero(self.mat['id'] == float(chip.replace('.bmp', '')))[0]
            labels = self.mat['targets'][i]
            nL = len(labels)

            # img = cv2.imread(img_path)
            # h, w, _ = img.shape

            # small_path = self.small_folder + str(chip)
            # if not os.path.isfile(small_path):
            #     img = cv2.imread(img_path)
            #     h, w, _ = img.shape
            #     img = resize_square(img, height=self.height)
            #     cv2.imwrite(small_path, img)
            # else:
            #     img = cv2.imread(small_path)
            #
            # if nL > 0:
            #     # Add padding
            #     w, h = self.mat['wh'][i[0]]
            #     ratio = float(self.height) / max(h, w)
            #     pad, padx, pady = (max(h, w) - min(h, w)) / 2, 0, 0
            #     if h > w:
            #         padx = pad
            #     elif h < w:
            #         pady = pad
            #
            #     labels[:, [1, 3]] += padx
            #     labels[:, [2, 4]] += pady
            #     labels[:, 1:5] *= ratio

            crop_flag = True
            if crop_flag:
                img = cv2.imread(img_path)
                h, w, _ = img.shape

                padx = int(random.random() * (w - self.height))
                pady = int(random.random() * (h - self.height))
                img = img[pady:pady + self.height, padx:padx + self.height]

                if nL > 0:
                    labels[:, [1, 3]] -= padx
                    labels[:, [2, 4]] -= pady
                    labels[:, 1:5] = np.clip(labels[:, 1:5], 0, self.height)
                    # objects must have width and height > 3 pixels
                    labels = labels[((labels[:, 3] - labels[:, 1]) > 3) & ((labels[:, 4] - labels[:, 2]) > 3)]

            # plot
            # import matplotlib.pyplot as plt
            # plt.subplot(2, 2, 1).imshow(img[:, :, ::-1])
            # plt.plot(labels[:, [1, 3, 3, 1, 1]].T, labels[:, [2, 2, 4, 4, 2]].T, '.-')

            # random affine
            # img, labels = random_affine(img, targets=labels, degrees=(-10, 10), translate=(.1, .1), scale=(.9, 1.1))

            nL = len(labels)
            if nL > 0:
                # convert labels to xywh
                labels[:, 1:5] = xyxy2xywh(labels[:, 1:5].copy()) / self.height
                # remap xview classes 11-94 to 0-61
                labels[:, 0] = xview_classes2indices(labels[:, 0])

            # random lr flip
            if random.random() > 0:
                img = np.fliplr(img)
                if nL > 0:
                    labels[:, 1] = 1 - labels[:, 1]

            # random ud flip
            if random.random() > 0:
                img = np.flipud(img)
                if nL > 0:
                    labels[:, 2] = 1 - labels[:, 2]

            # img_all.append(torch.from_numpy(img))
            img_all.append(img)
            labels_all.append(torch.from_numpy(labels))

        # Normalize
        img_all = np.stack(img_all)
        img_all = np.ascontiguousarray(img_all)
        img_all = img_all[:, :, :, ::-1].transpose(0, 3, 1, 2).astype(np.float32) / 255.0  # BGR to RGB
        # img_all -= self.rgb_mean
        # img_all /= self.rgb_std
        return torch.from_numpy(img_all), labels_all

    def __len__(self):
        return self.nB  # number of batches


class ListDataset_xview_crop():  # for training
    def __init__(self, folder_path, batch_size=1, img_size=416):
        p = folder_path + 'train_images'
        self.files = sorted(glob.glob('%s/*.bmp' % p))
        self.nF = len(self.files)  # number of image files
        self.nB = math.ceil(self.nF / batch_size)  # number of batches
        self.batch_size = batch_size
        assert self.nB > 0, 'No images found in path %s' % p
        self.height = img_size
        # load targets
        self.mat = scipy.io.loadmat('utils/targets_62c.mat')
        self.mat['id'] = self.mat['id'].squeeze()
        # make folder for reduced size images
        self.small_folder = p + '_' + str(img_size) + '/'
        os.makedirs(self.small_folder, exist_ok=True)

        # RGB normalization values
        self.rgb_mean = np.array([60.134, 49.697, 40.746], dtype=np.float32).reshape((1, 3, 1, 1))
        self.rgb_std = np.array([29.99, 24.498, 22.046], dtype=np.float32).reshape((1, 3, 1, 1))
        self.hsv_mean = np.array([24.956, 91.347, 61.362], dtype=np.float32).reshape((1, 3, 1, 1))
        self.hsv_std = np.array([15.825, 26.98, 29.618], dtype=np.float32).reshape((1, 3, 1, 1))

    def __iter__(self):
        self.count = -1
        self.shuffled_vector = np.random.permutation(self.nF)  # shuffled vector
        return self

    # @profile
    def __next__(self):
        self.count += 1
        if self.count == self.nB:
            raise StopIteration

        ia = self.count * self.batch_size
        ib = min((self.count + 1) * self.batch_size, self.nF)
        indices = list(range(ia, ib))

        img_all = []  # np.zeros((len(indices), self.height, self.height, 3), dtype=np.uint8)
        labels_all = []
        for index, files_index in enumerate(indices):
            img_path = self.files[self.shuffled_vector[files_index]]  # BGR

            # load labels
            chip = img_path.rsplit('/')[-1]
            i = np.nonzero(self.mat['id'] == float(chip.replace('.bmp', '')))[0]
            labels0 = self.mat['targets'][i]
            nL0 = len(labels0)

            img0 = cv2.imread(img_path)
            # img0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)
            h, w, _ = img0.shape

            for j in range(16):
                padx = int(random.random() * (w - self.height))
                pady = int(random.random() * (h - self.height))
                img = img0[pady:pady + self.height, padx:padx + self.height]

                if nL0 > 0:
                    labels = labels0.copy()
                    labels[:, [1, 3]] -= padx
                    labels[:, [2, 4]] -= pady
                    labels[:, 1:5] = np.clip(labels[:, 1:5], 0, self.height)
                    # objects must have width and height > 3 pixels
                    labels = labels[((labels[:, 3] - labels[:, 1]) > 3) & ((labels[:, 4] - labels[:, 2]) > 3)]
                else:
                    labels = np.array([], dtype=np.float32)

                # plot
                # import matplotlib.pyplot as plt
                # plt.subplot(2, 2, 1).imshow(img[:, :, ::-1])
                # plt.plot(labels[:, [1, 3, 3, 1, 1]].T, labels[:, [2, 2, 4, 4, 2]].T, '.-')

                # random affine
                img, labels = random_affine(img, targets=labels, degrees=(-10, 10), translate=(.05, .05),
                                              scale=(.9, 1.1))
                # plt.subplot(2, 2, 2).imshow(img[:, :, ::-1])
                # plt.plot(labels[:, [1, 3, 3, 1, 1]].T, labels[:, [2, 2, 4, 4, 2]].T, '.-')

                nL = len(labels)
                if nL > 0:
                    # convert labels to xywh
                    labels[:, 1:5] = xyxy2xywh(labels[:, 1:5].copy()) / self.height
                    # remap xview classes 11-94 to 0-61
                    labels[:, 0] = xview_classes2indices(labels[:, 0])

                # random lr flip
                if random.random() > 0:
                    img = np.fliplr(img)
                    if nL > 0:
                        labels[:, 1] = 1 - labels[:, 1]

                # random ud flip
                if random.random() > 0:
                    img = np.flipud(img)
                    if nL > 0:
                        labels[:, 2] = 1 - labels[:, 2]

                img_all.append(img)
                labels_all.append(torch.from_numpy(labels))

        # Randomize
        i = np.random.permutation(len(labels_all))
        img_all = [img_all[j] for j in i]
        labels_all = [labels_all[j] for j in i]

        # Normalize
        img_all = np.stack(img_all)
        img_all = np.ascontiguousarray(img_all)
        img_all = img_all[:, :, :, ::-1].transpose(0, 3, 1, 2).astype(np.float32)  # BGR to RGB
        img_all -= self.rgb_mean
        img_all /= self.rgb_std
        return torch.from_numpy(img_all), labels_all

    def __len__(self):
        return self.nB  # number of batches


def xview_classes2indices(classes):  # remap xview classes 11-94 to 0-61
    indices = [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 0, 1, 2, -1, 3, -1, 4, 5, 6, 7, 8, -1, 9, 10, 11, 12, 13, 14,
               15, -1, -1, 16, 17, 18, 19, 20, 21, 22, -1, 23, 24, 25, -1, 26, 27, -1, 28, -1, 29, 30, 31, 32, 33, 34,
               35, 36, 37, -1, 38, 39, 40, 41, 42, 43, 44, 45, -1, -1, -1, -1, 46, 47, 48, 49, -1, 50, 51, -1, 52, -1,
               -1, -1, 53, 54, -1, 55, -1, -1, 56, -1, 57, -1, 58, 59]
    return [indices[int(c)] for c in classes]


# @profile
def resize_square(img, height=416, color=(0, 0, 0)):  # resizes a rectangular image to a padded square
    shape = img.shape[:2]  # shape = [height, width]
    ratio = float(height) / max(shape)
    new_shape = [round(shape[0] * ratio), round(shape[1] * ratio)]
    dw = height - new_shape[1]  # width padding
    dh = height - new_shape[0]  # height padding
    top, bottom = dh // 2, dh - (dh // 2)
    left, right = dw // 2, dw - (dw // 2)
    img = cv2.resize(img, (new_shape[1], new_shape[0]), interpolation=cv2.INTER_AREA)
    return cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)


# @profile
def random_affine(img, targets=None, degrees=(-10, 10), translate=(.1, .1), scale=(.9, 1.1), shear=(-2, 2)):
    # torchvision.transforms.RandomAffine(degrees=(-10, 10), translate=(.1, .1), scale=(.9, 1.1), shear=(-10, 10))
    # https://medium.com/uruvideo/dataset-augmentation-with-random-homographies-a8f4b44830d4

    # Rotation and Scale
    R = np.eye(3)
    a = random.random() * (degrees[1] - degrees[0]) + degrees[0]
    a += np.random.choice([-180, -90, 0, 90])  # random 90deg rotations added to small rotations

    s = random.random() * (scale[1] - scale[0]) + scale[0]
    R[:2] = cv2.getRotationMatrix2D(angle=a, center=(img.shape[0] / 2, img.shape[1] / 2), scale=s)

    # Translation
    T = np.eye(3)
    T[0, 2] = (random.random() * 2 - 1) * translate[0] * img.shape[0]  # x translation (pixels)
    T[1, 2] = (random.random() * 2 - 1) * translate[1] * img.shape[1]  # y translation (pixels)

    # Shear
    S = np.eye(3)
    S[0, 1] = np.tan((random.random() * (shear[1] - shear[0]) + shear[0]) * math.pi / 180)  # x shear (deg)
    S[1, 0] = np.tan((random.random() * (shear[1] - shear[0]) + shear[0]) * math.pi / 180)  # y shear (deg)

    M = R @ T @ S
    imw = cv2.warpPerspective(img, M, dsize=(img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR)

    # Return warped points also
    if targets is not None:
        if len(targets) > 0:
            n = targets.shape[0]
            points = targets[:, 1:5].copy()

            # warp points
            xy = np.ones((n * 4, 3))
            xy[:, :2] = points[:, [0, 1, 2, 3, 0, 3, 2, 1]].reshape(n * 4, 2)  # x1y1, x2y2, x1y2, x2y1
            xy = (xy @ M.T)[:, :2].reshape(n, 8)

            # create new boxes
            x = xy[:, [0, 2, 4, 6]]
            y = xy[:, [1, 3, 5, 7]]
            xy = np.concatenate((x.min(1), y.min(1), x.max(1), y.max(1))).reshape(4, n).T

            # reject warped points outside of image
            # i = np.all((xy > 0) & (xy < img.shape[0]), 1)
            xy = np.clip(xy, a_min=0, a_max=img.shape[0])
            i = ((xy[:, 2] - xy[:, 0]) > 5) & ((xy[:, 3] - xy[:, 1]) > 5)  # width and height > 5 pixels

            targets = targets[i]
            targets[:, 1:5] = xy[i]

        return imw, targets
    else:
        return imw


def convert_tif2bmp(p='/Users/glennjocher/Downloads/DATA/xview/train_images'):
    import glob
    import cv2
    import os
    files = sorted(glob.glob('%s/*.tif' % p))
    for i, f in enumerate(files):
        print('%g/%g' % (i, len(files)))
        cv2.imwrite(f.replace('.tif', '.bmp'), cv2.imread(f))
        os.system('rm -rf ' + f)
