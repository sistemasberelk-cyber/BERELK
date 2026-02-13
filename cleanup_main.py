
import sys

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip_until = -1

for i, line in enumerate(lines):
    line_num = i + 1
    
    # Skip the old duplicate version of print_labels_v2 (173 to 255)
    if line_num == 173:
        skip_until = 255
        continue
    
    if line_num <= skip_until:
        continue
        
    # Also fix the admin redirect to point to / instead of /dashboard
    if 'RedirectResponse("/dashboard")' in line:
        line = line.replace('"/dashboard"', '"/"')
        
    new_lines.append(line)

# Add health check route after the app definition
final_lines = []
for line in new_lines:
    final_lines.append(line)
    if 'app = FastAPI(' in line:
        # Add health check right after app creation
        final_lines.append("\n@app.get(\"/health\")\n")
        final_lines.append("@app.head(\"/health\")\n")
        final_lines.append("def health_check():\n")
        final_lines.append("    return {\"status\": \"ok\"}\n\n")

with open('main_clean.py', 'w', encoding='utf-8') as f:
    f.writelines(final_lines)

print("Cleanup complete. Created main_clean.py")
