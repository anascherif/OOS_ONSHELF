import cv2
import numpy as np
import sys
import os

"""
HSV SAMPLER ; run this ONCE to find exact shelf HSV values.
Click anywhere on the image → prints exact OpenCV HSV value.
Press Q to quit
"""

image_path = "base one.png"

if not os.path.exists(image_path):
    print(f"Error: Image not found at path: {image_path}")
    sys.exit(1)

_img = cv2.imread(image_path)
if _img is None:
    print(f"Error: Could not read image at path: {image_path}")
    sys.exit(1)
img: np.ndarray = _img
hsv: np.ndarray = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

clicked_values = []

def on_click(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        h, s, v = hsv[y, x]
        b, g, r = img[y, x]

        clicked_values.append((int(h), int(s), int(v)))

        print(f"  Pixel ({x:3d}, {y:3d}) "
              f"→ OpenCV HSV: H={h:3d}  S={s:3d}  V={v:3d}  "
              f"| BGR: ({b},{g},{r})")

        cv2.circle(img, (x, y), 5, (0, 255, 0), -1)
        cv2.imshow(win, img)


win = "Click on EMPTY SHELF areas | Q to quit"
cv2.imshow(win, img)
cv2.setMouseCallback(win, on_click)

print("\n  Click on every empty shelf area you can see.")
print("  Focus on top half — we already know the bottom.")
print("  Press Q when done.\n")

while True:
    key = cv2.waitKey(20) & 0xFF
    if key in (ord('q'), ord('Q'), 27):
        break

cv2.destroyAllWindows()

# Print summary
if clicked_values:
    h_vals = [v[0] for v in clicked_values]
    s_vals = [v[1] for v in clicked_values]
    v_vals = [v[2] for v in clicked_values]
    print(f"\n  {'─'*45}")
    print(f"  Sampled {len(clicked_values)} points")
    print(f"  H range → min={min(h_vals)}  max={max(h_vals)}")
    print(f"  S range → min={min(s_vals)}  max={max(s_vals)}")
    print(f"  V range → min={min(v_vals)}  max={max(v_vals)}")
    print(f"  {'─'*45}")
    print(f"\n  Paste into your config:")
    print(f"  SHELF_HSV_LOWER = np.array([{min(h_vals)-5},  "
          f"{max(0,min(s_vals)-5)},  {max(0,min(v_vals)-15)}])")
    print(f"  SHELF_HSV_UPPER = np.array([{max(h_vals)+5},  "
          f"{min(255,max(s_vals)+5)},  {min(255,max(v_vals)+15)}])")