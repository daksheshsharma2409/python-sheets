import cv2
import os
import shutil

# Step 1: Ask user for full name
full_name = input("Enter your full name: ").strip().replace(" ", "_")
filename = f"{full_name}.jpg"

# Step 2: Create subdirectory if it doesn't exist
subdir = "authorized_faces"
os.makedirs(subdir, exist_ok=True)

# Step 3: Start webcam
cap = cv2.VideoCapture(0)
print("Press SPACE to capture photo. Press ESC to exit without capturing.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame.")
        break

    cv2.imshow("Camera - Press SPACE to Capture", frame)

    key = cv2.waitKey(1)
    if key == 27:  # ESC key
        print("Escape hit, closing...")
        break
    elif key == 32:  # SPACE key
        cv2.imwrite(filename, frame)
        print(f"Photo saved as {filename}")
        break

# Release resources
cap.release()
cv2.destroyAllWindows()

# Step 4: Move the image to subdirectory
if os.path.exists(filename):
    dest_path = os.path.join(subdir, filename)
    shutil.move(filename, dest_path)
    print(f"Moved photo to: {dest_path}")
else:
    print("No photo was taken.")
