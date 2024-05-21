import os
import re
import subprocess
from pathlib import Path

# Define the directory containing the files
directory = './PrivacyPoliciesDataset_Brianna/GooglePlay_Privacy_Policies/'

# Loop through all files in the specified directory
for filename in os.listdir(directory):
    file_path = Path(directory) / filename

    # Make sure we're only processing files (not directories)
    if file_path.is_file():
        with open(file_path, 'r') as file:
            # Read the first three lines; the URL is on the third line
            lines = file.readlines()
            if len(lines) < 3:
                print(f"Not enough lines in {filename}")
                continue  # Skip to the next file
            third_line = lines[2].strip()
            
            # Extract the URL from the third line
            prefix = 'Privacy Policy URL: '
            if third_line.startswith(prefix):
                policy_url = third_line[len(prefix):]
                filename_withoutExt = re.sub(r'\.[^\.]+$', '', filename)
                os.makedirs(f"output/{filename_withoutExt}/", exist_ok=True)


                # Define the commands to run
                commands = [
                    f"python -m poligrapher.scripts.html_crawler {policy_url} output/{filename_withoutExt}/",
                    f"python -m poligrapher.scripts.init_document output/{filename_withoutExt}/",
                    f"python -m poligrapher.scripts.run_annotators output/{filename_withoutExt}/",
                    f"python -m poligrapher.scripts.build_graph --pretty output/{filename_withoutExt}/"
                ]

                # Execute each command
                for command in commands:
                    process = subprocess.run(command, shell=True)
                    if process.returncode != 0:
                        print(f"Command failed: {command}")
                        break
    # input(f"Poligrapher done on: {filename}\n\n") # For testing
