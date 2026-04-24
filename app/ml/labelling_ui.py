import os
import sys
import csv
import json
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

# Constants
# Resolve absolute paths based on the location of this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(SCRIPT_DIR, "processed_faces")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "labels.csv")
RELABEL_QUEUE_CSV = os.path.join(SCRIPT_DIR, "relabel_queue.csv")
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg')

class LabellingUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Rapid Profile Rater")
        self.root.geometry("1200x800")
        
        # Data setup
        self.profiles = []
        self.current_idx = 0
        self.scored_profiles = set()
        
        # Load relabel queue first
        self.relabel_queue = {}
        if os.path.exists(RELABEL_QUEUE_CSV):
            with open(RELABEL_QUEUE_CSV, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2 and row[0] != "folder_name":
                        self.relabel_queue[row[0]] = row[1]
                        
        self.load_scored_profiles()
        self.load_all_profiles()
        
        if not self.profiles:
            messagebox.showinfo("Done", "No new profiles to score!")
            self.root.quit()
            return

        # UI Layout
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info label
        self.info_label = ttk.Label(self.main_frame, text="", font=("Arial", 14, "bold"))
        self.info_label.pack(pady=10)
        
        # Instructions
        instruction_text = (
            "Press 1-5 to score. Progress automatically saves.\n\n"
            "1: Absolute No\n"
            "2: Below Average / No\n"
            "3: Average / On the Fence\n"
            "4: Cute / Yes\n"
            "5: Elite / Instant Yes"
        )
        ttk.Label(self.main_frame, text=instruction_text, font=("Arial", 11), justify=tk.CENTER).pack()
        
        # Previous score label (if applicable)
        self.previous_score_label = ttk.Label(self.main_frame, text="", font=("Arial", 16, "bold"), foreground="red")
        self.previous_score_label.pack(pady=5)
        
        # Image grid frame
        self.grid_frame = ttk.Frame(self.main_frame)
        self.grid_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Image labels list
        self.image_labels = []
        for r in range(2):
            for c in range(3):
                lbl = tk.Label(self.grid_frame, bg="gray")
                lbl.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
                self.grid_frame.grid_rowconfigure(r, weight=1)
                self.grid_frame.grid_columnconfigure(c, weight=1)
                self.image_labels.append(lbl)
                
        # Bind keys
        for key in ['1', '2', '3', '4', '5']:
            self.root.bind(key, self.handle_score)
            
        # Bind resize event to redraw images if window size changes
        self.root.bind("<Configure>", self.on_resize)
        self.resize_timer = None
        
        # Track window size to prevent infinite resize loops (event storms)
        self.last_width = self.root.winfo_width()
        self.last_height = self.root.winfo_height()
        
        # Load first profile
        self.display_current_profile()
        
    def load_scored_profiles(self):
        """Load already scored profile folder names to skip them."""
        if os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                # Skip header if it exists
                try:
                    next(reader)
                except StopIteration:
                    pass
                for row in reader:
                    if row:
                        self.scored_profiles.add(row[0]) # Assuming profile_id/folder is first col
                        
    def load_all_profiles(self):
        """Scan logs directory for profile folders."""
        if not os.path.exists(LOGS_DIR):
            messagebox.showerror("Error", f"Logs directory not found: {LOGS_DIR}")
            sys.exit(1)
            
        all_dirs = [d for d in os.listdir(LOGS_DIR) if os.path.isdir(os.path.join(LOGS_DIR, d))]
        # Filter out already scored
        self.profiles = [d for d in all_dirs if d not in self.scored_profiles]
        self.profiles.sort() # Ensure consistent ordering
        
    def display_current_profile(self, event=None):
        if self.current_idx >= len(self.profiles):
            messagebox.showinfo("Complete", "All profiles have been scored!")
            self.root.quit()
            return
            
        folder_name = self.profiles[self.current_idx]
        profile_path = os.path.join(LOGS_DIR, folder_name)
        
        # Update info
        self.info_label.config(text=f"Profile: {folder_name} | Progress: {self.current_idx + 1}/{len(self.profiles)}")
        
        if folder_name in self.relabel_queue:
            old_score = self.relabel_queue[folder_name]
            self.previous_score_label.config(text=f"YOUR PREVIOUS SCORE WAS: {old_score}")
        else:
            self.previous_score_label.config(text="")
        
        # Find images
        image_files = []
        for f in os.listdir(profile_path):
            if f.lower().endswith(SUPPORTED_EXTENSIONS):
                image_files.append(os.path.join(profile_path, f))
        
        # Sort to keep photo_1, photo_2 order if possible
        image_files.sort()
        # Limit to 6
        image_files = image_files[:6]
        
        # Clear previous images
        for lbl in self.image_labels:
            lbl.config(image='')
            lbl.image = None # Prevent garbage collection issues
            
        # Calculate cell size
        self.root.update_idletasks() # Ensure geometry is updated
        grid_width = self.grid_frame.winfo_width()
        grid_height = self.grid_frame.winfo_height()
        
        # Fallback if window hasn't fully rendered
        if grid_width <= 1 or grid_height <= 1:
            cell_w = 1200 // 3 - 20
            cell_h = 700 // 2 - 20
        else:
            cell_w = (grid_width // 3) - 20
            cell_h = (grid_height // 2) - 20
            
        # Load and resize images
        for i, img_path in enumerate(image_files):
            try:
                img = Image.open(img_path)
                # Keep aspect ratio
                img.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.image_labels[i].config(image=photo)
                self.image_labels[i].image = photo # Keep reference
            except Exception as e:
                print(f"Error loading {img_path}: {e}")

    def on_resize(self, event):
        # Only process events from the root window itself, not child widgets
        if event.widget == self.root:
            # Only process if the physical size actually changed (not just a position change or internal widget render)
            if event.width != self.last_width or event.height != self.last_height:
                self.last_width = event.width
                self.last_height = event.height
                
                # Debounce resize events
                if self.resize_timer:
                    self.root.after_cancel(self.resize_timer)
                self.resize_timer = self.root.after(300, self.display_current_profile)

    def handle_score(self, event):
        score = event.char
        if score not in ['1', '2', '3', '4', '5']:
            return
            
        if self.current_idx >= len(self.profiles):
            return
            
        folder_name = self.profiles[self.current_idx]
        
        # Log to CSV
        file_exists = os.path.exists(OUTPUT_CSV)
        with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['folder_name', 'score'])
            writer.writerow([folder_name, score])
            
        # Advance
        self.current_idx += 1
        self.display_current_profile()

if __name__ == "__main__":
    root = tk.Tk()
    app = LabellingUI(root)
    root.mainloop()
