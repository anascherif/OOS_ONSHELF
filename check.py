import cv2
import numpy as np
import sys
import os

img = cv2.imread("base one.png")
if img is None:
    print("Error: Could not load image 'base one.png'. Check the file path.")
    sys.exit(1)
print(img.shape)