import argparse
import hashlib
import base64
from collections import namedtuple

import cv2
import numpy as np
from pyzbar.pyzbar import ZBarSymbol
from pyzbar.pyzbar import decode

from transform import four_point_transform

Code = namedtuple('Code', 'id total data chksum valid')
Entry = namedtuple("Entry", "code polygon proj_matrix")

pts = []

class PolygonSelector:
    def __init__(self):
        self.pts = []
        self.window_name = "PolygonSelector"

    @staticmethod
    def click(event, x, y, flags, param):
        # grab references to the global variables
        self = param[0]

        # if the left mouse button was clicked, record the starting
        # (x, y) coordinates and indicate that cropping is being
        # performed
        if event == cv2.EVENT_LBUTTONDOWN:
            self.pts.append((x, y))

    def select_points(self, image, window_width=1200):

        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.click, [self])

        image_resized = ResizeWithAspectRatio(image, width=1200)

        # keep looping until the 'q' key is pressed
        while True:
            # display the image and wait for a keypress
            cv2.imshow(self.window_name, image_resized)
            key = cv2.waitKey(1) & 0xFF

            # if the 'r' key is pressed, reset the cropping region
            if key == ord("r"):
                self.pts = []

            # if the 'c' key is pressed, break from the loop
            elif key == ord("c"):
                break

            if len(self.pts) == 4:
                break

        # close all open windows
        cv2.destroyWindow(self.window_name)

        ret_pts = np.array(self.pts, dtype="float32")
        ret_pts[:, 0] *= (image.shape[0] / image_resized.shape[0])
        ret_pts[:, 1] *= (image.shape[1] / image_resized.shape[1])

        self.pts = []

        return ret_pts

def drawBox(image, polygon, color, M=None):
    if M is not None:
        pts = np.array([[float(p.x), float(p.y), 1.0] for p in polygon], dtype=np.float32)
        M_inv = np.linalg.inv(M)
        pts = M_inv @ pts.transpose()
        pts[0,:] /= pts[2,:]
        pts[1, :] /= pts[2, :]
        pts = pts[0:2,:].transpose()
    else:
        pts = np.array([[float(p.x), float(p.y)] for p in polygon], dtype=np.float32)

    image = cv2.polylines(image, np.int32([pts]), thickness=5, isClosed=True, color=color)

    return image

def parse_data(data):
    id = None
    total_codes = None
    b64_data = None
    valid = False
    chksum_read = None


    # split at spaces
    data = data.split(b' ')
    if len(data) != 3:
        return Code(id, total_codes, b64_data, chksum_read, valid)

    cnt = data[0].split(b'/')
    if len(cnt) != 2:
        return Code(id, total_codes, b64_data, chksum_read, valid)

    try:
        id = int(cnt[0])
    except:
        return Code(id, total_codes, b64_data, chksum_read, valid)

    try:
        total_codes = int(cnt[1])
    except:
        return Code(id, total_codes, b64_data, chksum_read, valid)

    if id > total_codes:
        return Code(id, total_codes, b64_data, chksum_read, valid)

    b64_data = data[1]

    chksum_read = data[2].decode('ascii')
    chksum_data = hashlib.md5(b64_data).hexdigest()[0:6]

    if chksum_read == chksum_data:
        valid = True

    return Code(id, total_codes, b64_data, chksum_read, valid)


def ResizeWithAspectRatio(image, width=None, height=None, inter=cv2.INTER_AREA):
    dim = None
    (h, w) = image.shape[:2]

    if width is None and height is None:
        return image
    if width is None:
        r = height / float(h)
        dim = (int(w * r), height)
    else:
        r = width / float(w)
        dim = (width, int(h * r))

    return cv2.resize(image, dim, interpolation=inter)

def update_display_image(image, data):
    img_boxes = image
    for entry in data:
        if entry.code.valid:
            img_boxes = drawBox(img_boxes, entry.polygon, (0, 255, 0), M=entry.proj_matrix)
        else:
            img_boxes = drawBox(img_boxes, entry.polygon, (0, 0, 255), M=entry.proj_matrix)

    return img_boxes

def get_majority_total(data):
    hist = {}
    for d in data:
        if d.code.total not in hist.keys():
            hist[d.code.total] = 1
        else:
            hist[d.code.total] += 1

    best_total = -1
    for total in hist.keys():
        if hist[total] > best_total:
            best_total = total

    return best_total

def update_data(data, results, M):
    for det in results:
        code = parse_data(det.data)
        points = det.polygon
        if code.id not in [d.code.id for d in data]:
            data.append(Entry(code, points, M))

    best_total = get_majority_total(data)

    # clean up entries which provide the wrong total
    for d in data:
        if d.code.total != best_total:
            data.remove(d)

    # clean up entries which are duplicates
    existing_ids = []
    for d in data:
        if d.code.id in existing_ids:
           data.remove(d)
        else:
            existing_ids.append(d.code.id)

    # print missing ids
    missing_ids = [id for id in range(best_total) if id not in existing_ids ]
    print("Following codes are still missing: {}".format(missing_ids))
    return data, best_total


def get_detections_from_roi(image, pts):
    warped, M = four_point_transform(image, pts)

    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(gray, (1, 1), 0)
    ret3, thresholded = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    detection_results = decode(thresholded, symbols=[ZBarSymbol.QRCODE])

    return detection_results, M


def main():
    # construct the argument parse and parse the arguments
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--image", help="path to the image file")
    args = vars(ap.parse_args())

    image = cv2.imread(args["image"])
    disp_image = image

    data = []
    total_codes = -1

    selector = PolygonSelector()

    pts = np.array([[0, 0], [0, image.shape[0]], [image.shape[1], image.shape[0]], [image.shape[1], 0]], dtype="float32")
    detection_results, M = get_detections_from_roi(image, pts)
    data, total_codes = update_data(data, detection_results, M)
    disp_image = update_display_image(image, data)

    while len(data) < total_codes or total_codes < 0:
        pts = selector.select_points(disp_image)
        detection_results, M = get_detections_from_roi(image, pts)
        data, total_codes = update_data(data, detection_results, M)
        disp_image = update_display_image(image, data)

    data = sorted(data, key=lambda x: x.code.id)

    b64_payload = b""
    for d in data:
        print("{}: {}".format(d.code.id, d.code.data))
        b64_payload += d.code.data

    with open(args["image"]+'.decoded.b64', 'wb') as fp:
        fp.write(b64_payload)

    binary_payload = base64.b64decode(b64_payload.decode('ascii'))

    with open(args["image"]+'.decoded.bin', 'wb') as fp:
        fp.write(binary_payload)

    print("Done!")


if __name__ == "__main__":
    main()