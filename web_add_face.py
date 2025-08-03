import os
from flask import Flask, request, render_template, redirect, url_for, flash
import cv2 # Still needed for face_recognition's image loading/saving capabilities
import face_recognition
import numpy as np # Still needed by face_recognition for image arrays

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = 'your_strong_secret_key_here' # !!! IMPORTANT: CHANGE THIS TO A UNIQUE, RANDOM STRING !!!
# Example: app.secret_key = os.urandom(24).hex()

# --- Configuration for Web Server (running on Laptop) ---
script_dir = os.path.dirname(__file__)
# This is now the actual local folder on your laptop where authorized faces will be stored
AUTHORIZED_FACES_DIR = os.path.join(script_dir, "authorized_faces")

# Ensure the authorized_faces directory exists on the laptop
if not os.path.exists(AUTHORIZED_FACES_DIR):
    os.makedirs(AUTHORIZED_FACES_DIR)
    print(f"Created authorized faces directory on laptop: {AUTHORIZED_FACES_DIR}")

# --- Web Server Routes ---

@app.route('/')
def index():
    """Renders the main upload form."""
    return render_template('upload.html')

@app.route('/upload_face', methods=['POST'])
def upload_face():
    """Handles the photo and name upload, processes, and saves locally."""
    if 'photo' not in request.files:
        flash('No photo part in the request.')
        return redirect(request.url)

    file = request.files['photo']
    name = request.form.get('name', '').strip()

    if file.filename == '':
        flash('No selected photo.')
        return redirect(request.url)

    if not name:
        flash('Name cannot be empty.')
        return redirect(request.url)

    if file:
        # Sanitize the name for a valid filename
        sanitized_name = name.replace(" ", "_").lower()
        final_image_path = os.path.join(AUTHORIZED_FACES_DIR, f"{sanitized_name}.jpg")
        
        # Temporary path for initial save, then process
        temp_upload_path = os.path.join('/tmp', f"temp_{os.urandom(8).hex()}_{file.filename}")

        try:
            file.save(temp_upload_path) # Save the uploaded file temporarily

            # Load the image using face_recognition to detect faces
            image = face_recognition.load_image_file(temp_upload_path)
            face_locations = face_recognition.face_locations(image)

            if len(face_locations) == 1:
                # A single face is detected, proceed to save the original uploaded image
                if os.path.exists(final_image_path):
                    flash(f"Warning: A face for '{name}' already exists. Overwriting.")
                
                # Save the uploaded image directly to the authorized_faces folder
                # We use cv2.imwrite to ensure consistent image format/quality if needed,
                # otherwise, a simple os.rename or shutil.copyfile would suffice.
                # For consistency with how face_recognition loads, it's safer to use cv2.imwrite
                # after converting to BGR (OpenCV's default).
                cv2.imwrite(final_image_path, cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
                
                flash(f"Successfully added '{name}' to local authorized faces folder!")
                print(f"Web: Added '{name}' to local authorized faces at {final_image_path}")

            elif len(face_locations) > 1:
                flash('Multiple faces detected in the photo. Please upload a photo with only one face.')
            else:
                flash('No face detected in the photo. Please upload a clearer photo.')
        
        except Exception as e:
            flash(f'An error occurred during processing: {e}')
            print(f"Web Error: {e}")
        finally:
            # Clean up temporary file
            if os.path.exists(temp_upload_path):
                os.remove(temp_upload_path)
                print(f"Cleaned up temporary upload file: {temp_upload_path}")

    return redirect(url_for('index'))

if __name__ == '__main__':
    # Ensure the templates directory exists relative to this script
    templates_dir = os.path.join(script_dir, "templates")
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
        print(f"Created templates directory: {templates_dir}")

    print(f"\nWeb server starting on your laptop. Access it from your phone at http://<Laptop_IP_Address>:5000")
    print(f"Photos will be saved to your laptop's local folder: '{AUTHORIZED_FACES_DIR}'")
    
    # Run Flask app on all available interfaces (0.0.0.0) and port 5000
    # For mobile access on the same network, '0.0.0.0' is usually required.
    app.run(host='0.0.0.0', port=5000, debug=False) # Set debug=False for production
