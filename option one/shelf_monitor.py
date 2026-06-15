import cv2
import numpy as np
import sys
import os


# Range 1 — bright shelf divider strips and front edges
SHELF_LOWER_1 = np.array([18,  9,  40])
SHELF_UPPER_1 = np.array([85, 51,  229])

# Range 2 — warm grey empty shelf surface (yellowish tint, medium dark)
# SHELF_LOWER_2 = np.array([28, 15,  130])
# SHELF_UPPER_2 = np.array([40, 32,  175])

# # Range 3 — cool grey empty shelf surface (greenish tint, darker zones)
# SHELF_LOWER_3 = np.array([48, 10,   90])
# SHELF_UPPER_3 = np.array([68, 30,  120])

ROI_COORDS: tuple[int, int, int, int] | None = (30, 478, 0, 286) 
ALERT_THRESHOLD=30.0
MORPH_KERNEL_SIZE=18


def load_and_crop(image_path: str) ->np.ndarray:
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Image not found at path: {image_path}\n"
                                  f"Please check the path and try again.")
    if ROI_COORDS is not None:
        y1, y2, x1, x2 = ROI_COORDS
        image = image[y1:y2, x1:x2]
        if image.size == 0:
            raise ValueError(f"Invalid ROI coordinates: {ROI_COORDS}\n"
                             f"Please check the coordinates and try again.")
    return image



def build_shelf_mask(image: np.ndarray) -> np.ndarray:
    hsv    = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    mask1  = cv2.inRange(hsv, SHELF_LOWER_1, SHELF_UPPER_1)
    # mask2  = cv2.inRange(hsv, SHELF_LOWER_2, SHELF_UPPER_2)
    # mask3    = cv2.inRange(hsv, SHELF_LOWER_3, SHELF_UPPER_3)
    # # Combine both ranges into one mask
    # combined = cv2.bitwise_or(mask1, mask2)
    # combined = cv2.bitwise_or(combined, mask3)
    # --- Morphological cleanup ---
    # OPEN  = erode then dilate  → removes tiny noise blobs
    # CLOSE = dilate then erode  → fills small holes inside real shelf areas
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    mask = cv2.morphologyEx(mask1, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask



def calculate_stock_percentage(mask: np.ndarray) -> dict:
    total_pixels = mask.shape[0] * mask.shape[1]
    visible_shelf_pixels = cv2.countNonZero(mask)
    yogurt_pixels= total_pixels - visible_shelf_pixels
    if total_pixels == 0:
        raise ValueError("Total pixels in the mask is zero. Check the input image and ROI settings.")
    stock_percentage = (yogurt_pixels / total_pixels) * 100
    empty_percentage = visible_shelf_pixels / total_pixels * 100
    return {
        "total_pixels": total_pixels,
        "visible_shelf_pixels": visible_shelf_pixels,
        "yogurt_pixels": yogurt_pixels,
        "stock_percentage": round(stock_percentage,2),
        "empty_percentage": round(empty_percentage,2)
    }


def print_results(image_name :str, metrics: dict)-> None:
    sep="-" * 40
    print(f"\n{sep}\nImage: {image_name}\n{sep}")
    print(f"Total ROI Pixels: {metrics['total_pixels']}")
    print(f"  Shelf pixels     : {metrics['visible_shelf_pixels']:,}  "
          f"({metrics['empty_percentage']}%  empty)")
    print(f"  Yogurt pixels    : {metrics['yogurt_pixels']:,}  "
          f"({metrics['stock_percentage']}%  filled)")
    print(f"{sep}")
    if metrics['stock_percentage'] < ALERT_THRESHOLD:
        print(f"ALERT: Stock is low! Only {metrics['stock_percentage']}% remaining is below the threshold of {ALERT_THRESHOLD}%.\n")
    else:
        print(f"Stock level is sufficient: {metrics['stock_percentage']}% remaining.\n")


def save_debug_image(bgr_crop: np.ndarray,
                     mask: np.ndarray,
                     output_path: str) -> None:
    """
    For portrait images: stack VERTICALLY (top = original, bottom = overlay).
    Resize to a comfortable viewing size before saving.
    """
    # Red overlay on detected shelf pixels
    overlay = bgr_crop.copy()
    overlay[mask > 0] = [0, 0, 220]

    # Add labels INSIDE the image
    font       = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    thickness  = 1

    orig_labeled = bgr_crop.copy()
    cv2.putText(orig_labeled, "ORIGINAL",
                (8, 20), font, font_scale, (255, 255, 255), thickness)

    cv2.putText(overlay, "RED = EMPTY SHELF DETECTED",
                (8, 20), font, font_scale, (0, 0, 220), thickness)

    # Stack vertically 
    debug_img = np.vstack([orig_labeled, overlay])

    # Resize to 600px tall so it's readable 
    target_height = 900
    scale         = target_height / debug_img.shape[0]
    new_width     = int(debug_img.shape[1] * scale)
    debug_img     = cv2.resize(debug_img, (new_width, target_height),
                               interpolation=cv2.INTER_LINEAR)

    # Draw a white divider line between original and overlay
    mid_y = target_height // 2
    cv2.line(debug_img, (0, mid_y), (new_width, mid_y), (255, 255, 255), 2)

    cv2.imwrite(output_path, debug_img)
    print(f"  Debug image saved → {output_path}")
    print(f"  Debug image size  → {debug_img.shape}")



def analyze_image(image_path: str,
                  save_debug: bool = True) -> dict:
    """
    Full pipeline for one image:
    load → crop → mask → morphological cleanup → count → report.
    """
    crop    = load_and_crop(image_path)
    mask    = build_shelf_mask(crop)
    metrics = calculate_stock_percentage(mask)
 
    image_name = os.path.basename(image_path)
    print_results(image_name, metrics)
 
    if save_debug:
        debug_path = image_path.replace(".", "_debug.")
        save_debug_image(crop, mask, debug_path)
 
    return metrics

if __name__ == "__main__":
    BASE_IMAGE="base one.png"
    if len(sys.argv) > 1:
        BASE_IMAGE = sys.argv[1]
    if os.path.exists(BASE_IMAGE):
        print(f"Analyzing base image: {BASE_IMAGE}")
        analyze_image(BASE_IMAGE, save_debug=True)
    else:
        print(f"Base image not found at path: {BASE_IMAGE}\n"
              f"Please ensure the image exists and try again.")