import face_recognition
import cv2
import numpy as np
import os
import time
# scipy.spatial.distance is still implicitly used by face_recognition for face_distance
import dlib
from datetime import datetime
# requests import is removed as Telegram part is removed

# --- Google Sheets API Configuration ---
# !!! IMPORTANT: REPLACE WITH YOUR GOOGLE SHEET ID !!!
SHEET_ID = "10rV0z0KIMJh1OKZVuewL8WtH4KR2m9zi3SMc_IoxzdI" # <--- YOUR GOOGLE SHEET ID HERE
# The path to your service account key JSON file
SERVICE_ACCOUNT_KEY_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")

# Import gspread and google.oauth2.service_account for Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# --- Configuration ---
script_dir = os.path.dirname(__file__)
AUTHORIZED_FACES_DIR = os.path.join(script_dir, "authorized_faces")
# SHAPE_PREDICTOR_PATH is no longer needed as liveness detection is removed
# ACCESS_LOG_FILE is defined but not actively written to in this version,
# as logging goes directly to Google Sheets.

FACE_RECOGNITION_TOLERANCE = 0.55

# --- Cooldown Period ---
# Prevents logging the same person multiple times in quick succession
# This cooldown applies to both entry and exit actions for a given person.
COOLDOWN_PERIOD_SECONDS = 10.0 # Recommended: 10-30 seconds

# --- Google Sheets Setup ---
client = None # Global gspread client
worksheet = None # Global worksheet object
try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_KEY_PATH, scopes=scopes)
    client = gspread.authorize(creds)
    
    workbook = client.open_by_key(SHEET_ID)
    worksheet = workbook.worksheet("Sheet1") # Assuming your attendance sheet is named "Sheet1"

    # Check and set headers
    head = ['Name', 'Date', 'Entry Time', 'Exit Time']
    current_header = worksheet.row_values(1)
    if current_header != head:
        print("Google Sheet headers do not match expected format. Updating headers...")
        worksheet.update('A1:D1', [head]) # Update the entire header row
        print("Google Sheet headers updated successfully.")
    else:
        print("Google Sheet headers are already correctly set.")

    print(f"Successfully connected to Google Sheet (ID: {SHEET_ID}, Worksheet: Sheet1)")

except FileNotFoundError:
    print(f"ERROR: Google Sheets credentials file not found at '{SERVICE_ACCOUNT_KEY_PATH}'.")
    print("Please ensure you've downloaded 'credentials.json' and placed it in the script directory.")
    exit()
except Exception as e:
    print(f"ERROR: Could not connect to Google Sheets or update headers: {e}")
    print("Please check:")
    print(f"  - Is the Google Sheet ID '{SHEET_ID}' correct?")
    print("  - Is the worksheet named 'Sheet1' in your Google Sheet?")
    print("  - Have you shared the Google Sheet with your service account email (Editor access)?")
    print("  - Is your internet connection stable?")
    exit()

# --- Attendance Logging Functions ---
# This dictionary will hold the state for each known person
# Format: {person_name: {'is_in': bool, 'entry_row': int or None, 'last_action_time': float}}
present_individuals = {}

def log_new_entry(person_name, current_dt):
    """Appends a new entry row to the Google Sheet."""
    log_date = current_dt.strftime("%Y-%m-%d")
    log_time = current_dt.strftime("%H:%M:%S")

    try:
        # Get the current number of rows to determine the new row index
        # This is a simple way to get the next row number.
        # For very high-volume systems, consider more robust row management.
        all_values = worksheet.get_all_values()
        new_row_index = len(all_values) + 1 # +1 because sheet rows are 1-indexed

        worksheet.append_row([person_name, log_date, log_time, '']) # Exit Time is blank initially
        print(f"ATTENDANCE LOG: ENTRY for '{person_name}' recorded to Google Sheet at row {new_row_index} ({log_time} on {log_date}).")
        return new_row_index # Return the row index for later exit update
    except Exception as e:
        print(f"ERROR logging entry for '{person_name}': {e}")
        return None # Indicate failure

def update_exit_time(person_name, row_index, current_dt):
    """Updates the 'Exit Time' for a specific row in the Google Sheet."""
    exit_time = current_dt.strftime("%H:%M:%S")

    try:
        # Update the 'Exit Time' column (column 4) for the given row_index
        worksheet.update_cell(row_index, 4, exit_time)
        print(f"ATTENDANCE LOG: EXIT for '{person_name}' updated in Google Sheet at row {row_index} ({exit_time}).")
        return True
    except Exception as e:
        print(f"ERROR updating exit time for '{person_name}' at row {row_index}: {e}")
        return False

# --- Load all known faces from the 'authorized_faces' directory ---
known_face_encodings = []
known_face_names = []

print(f"Loading authorized faces from: {AUTHORIZED_FACES_DIR}")
if not os.path.exists(AUTHORIZED_FACES_DIR):
    print(f"ERROR: '{AUTHORIZED_FACES_DIR}' directory not found.")
    print("Please create this folder and place authorized person images inside it.")
    exit()

for filename in os.listdir(AUTHORIZED_FACES_DIR):
    if filename.endswith((".jpg", ".jpeg", ".png")):
        person_name = os.path.splitext(filename)[0]
        person_name = person_name.replace("_", " ").title()
        image_path = os.path.join(AUTHORIZED_FACES_DIR, filename)

        try:
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)

            if len(encodings) > 0:
                known_face_encodings.append(encodings[0])
                known_face_names.append(person_name)
                print(f"Loaded '{person_name}' from '{filename}'.")
                # Initialize state for each known person
                present_individuals[person_name] = {'is_in': False, 'entry_row': None, 'last_action_time': 0.0}
            else:
                print(f"WARNING: No face found in '{filename}'. Skipping this image.")
        except Exception as e:
            print(f"ERROR: Could not process '{filename}': {e}")

if not known_face_encodings:
    print("ERROR: No authorized faces loaded. Please ensure 'authorized_faces' folder contains images with clear faces.")
    exit()
print(f"Successfully loaded {len(known_face_encodings)} authorized faces.")

# --- Dlib Face Detector ---
print(f"Loading Dlib face detector...")
try:
    detector = dlib.get_frontal_face_detector()
    print("Dlib face detector loaded successfully.")
except RuntimeError as e:
    print(f"ERROR loading Dlib face detector: {e}")
    exit()

# --- Main Program Execution ---
video_capture = None # Initialize video_capture outside try block
try:
    # --- Webcam Initialization (USB Camera) ---
    video_capture = cv2.VideoCapture(0) # Use 0 for default USB webcam

    if not video_capture.isOpened():
        print("\nERROR: Could not open camera. Please check:")
        print("  1. If your USB webcam is connected and powered on.")
        print("  2. If it is not in use by another application.")
        print("  3. If you have granted camera permissions to your terminal/Python environment (macOS/Linux).")
        exit()

    # Set camera resolution (optional, but good for consistency)
    video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print(f"\nAttendance system started. Press 'q' to quit.")

    # --- Main loop for live recognition and attendance ---
    while True:
        ret, frame = video_capture.read()
        if not ret:
            print("ERROR: Failed to grab frame from webcam. Exiting.")
            break

        small_frame = frame
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)

        current_datetime = datetime.now()
        current_time_epoch = time.time() # For cooldown calculations

        face_locations_dlib = detector(gray_frame, 0) # Use dlib for face detection

        # --- Face Recognition & Attendance Logic ---
        # Default display messages if no specific action occurs
        overall_display_message = "Waiting for Face..."
        overall_display_color = (0, 255, 255) # Yellow

        # Keep track of who was seen in THIS frame
        seen_in_this_frame = set()

        if len(face_locations_dlib) > 0:
            overall_display_message = "Processing Face(s)..."
            overall_display_color = (0, 165, 255) # Orange

            for dlib_rect in face_locations_dlib:
                top_d, right_d, bottom_d, left_d = dlib_rect.top(), dlib_rect.right(), dlib_rect.bottom(), dlib_rect.left()
                face_location_fr = (top_d, right_d, bottom_d, left_d)

                face_encodings_recognition = face_recognition.face_encodings(rgb_small_frame, [face_location_fr])

                display_name_on_box = "Unknown"
                display_color_on_box = (0, 0, 255) # Red for unknown

                if face_encodings_recognition:
                    matches = face_recognition.compare_faces(known_face_encodings, face_encodings_recognition[0], tolerance=FACE_RECOGNITION_TOLERANCE)
                    face_distances = face_recognition.face_distance(known_face_encodings, face_encodings_recognition[0])
                    best_match_index = np.argmin(face_distances)

                    if matches[best_match_index]:
                        recognized_person_name = known_face_names[best_match_index]
                        seen_in_this_frame.add(recognized_person_name) # Mark as seen in this frame

                        person_data = present_individuals[recognized_person_name] # Get their current state

                        # Check cooldown for this person's last action
                        if (current_time_epoch - person_data['last_action_time']) < COOLDOWN_PERIOD_SECONDS:
                            # Still in cooldown, just update display
                            display_name_on_box = f"{recognized_person_name} (Cooldown)"
                            display_color_on_box = (0, 255, 255) # Yellow
                            overall_display_message = f"Cooldown: {recognized_person_name}"
                            overall_display_color = (0, 255, 255) # Yellow
                        else:
                            # Not in cooldown, perform action
                            if not person_data['is_in']: # Person is currently OUT -> ENTRY
                                new_row_idx = log_new_entry(recognized_person_name, current_datetime)
                                if new_row_idx:
                                    present_individuals[recognized_person_name]['is_in'] = True
                                    present_individuals[recognized_person_name]['entry_row'] = new_row_idx
                                    present_individuals[recognized_person_name]['last_action_time'] = current_time_epoch
                                    display_name_on_box = f"ENTRY: {recognized_person_name}"
                                    display_color_on_box = (0, 255, 0) # Green
                                    overall_display_message = f"ENTRY: {recognized_person_name}"
                                    overall_display_color = (0, 255, 0) # Green
                                else:
                                    display_name_on_box = f"Entry Failed: {recognized_person_name}"
                                    display_color_on_box = (0, 0, 255) # Red
                                    overall_display_message = f"Entry Failed: {recognized_person_name}"
                                    overall_display_color = (0, 0, 255) # Red
                            else: # Person is currently IN -> EXIT
                                if person_data['entry_row'] is not None:
                                    if update_exit_time(recognized_person_name, person_data['entry_row'], current_datetime):
                                        present_individuals[recognized_person_name]['is_in'] = False
                                        present_individuals[recognized_person_name]['entry_row'] = None # Clear for next entry
                                        present_individuals[recognized_person_name]['last_action_time'] = current_time_epoch
                                        display_name_on_box = f"EXIT: {recognized_person_name}"
                                        display_color_on_box = (0, 0, 255) # Red
                                        overall_display_message = f"EXIT: {recognized_person_name}"
                                        overall_display_color = (0, 0, 255) # Red
                                    else:
                                        display_name_on_box = f"Exit Failed: {recognized_person_name}"
                                        display_color_on_box = (0, 0, 255) # Red
                                        overall_display_message = f"Exit Failed: {recognized_person_name}"
                                        overall_display_color = (0, 0, 255) # Red
                                else:
                                    # Inconsistent state: is_in is True but no entry_row. Resetting.
                                    print(f"WARNING: Inconsistent state for {recognized_person_name}. Resetting to OUT.")
                                    present_individuals[recognized_person_name]['is_in'] = False
                                    present_individuals[recognized_person_name]['entry_row'] = None
                                    display_name_on_box = f"Error State: {recognized_person_name}"
                                    display_color_on_box = (0, 0, 255) # Red
                                    overall_display_message = f"Error State: {recognized_person_name}"
                                    overall_display_color = (0, 0, 255) # Red
                    else: # Face recognized, but not a known person
                        display_name_on_box = "Unknown Person"
                        display_color_on_box = (0, 0, 255) # Red
                else: # Dlib found a face, but face_recognition couldn't encode it (rare)
                    display_name_on_box = "Processing Face..."
                    display_color_on_box = (0, 165, 255) # Orange

                # Draw bounding box and name
                cv2.rectangle(frame, (left_d, top_d), (right_d, bottom_d), display_color_on_box, 2)
                cv2.rectangle(frame, (left_d, bottom_d - 35), (right_d, bottom_d), display_color_on_box, cv2.FILLED)
                font = cv2.FONT_HERSHEY_DUPLEX
                cv2.putText(frame, display_name_on_box, (left_d + 6, bottom_d - 6), font, 1.0, (255, 255, 255), 1)
        else:
            # No faces detected in the current frame
            overall_display_message = "Waiting for Face..."
            overall_display_color = (0, 255, 255) # Yellow


        # --- Display overall system status ---
        cv2.putText(frame, overall_display_message, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, overall_display_color, 2)
        
        # Display count of people currently "IN"
        num_present = sum(1 for p_data in present_individuals.values() if p_data['is_in'])
        cv2.putText(frame, f"Currently IN: {num_present}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


        cv2.imshow('Attendance System', frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("\n'q' pressed. Exiting...")
            break

finally:
    # --- Cleanup ---
    print("\nCleaning up resources...")
    if video_capture:
        video_capture.release()
    
    cv2.destroyAllWindows()
    print("Program ended.")