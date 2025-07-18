import os
import shutil

def generate_index_html(work_dir: str, global_config: dict):
    """Generates the index.html file to redirect to the configured landing page."""
    ui_config = global_config.get('ui', {})
    landing_page = ui_config.get('landing_page', 'list')
    redirect_url = f"{landing_page}.html"

    if landing_page == 'fullscreen':
        camera_name = ui_config.get('fullscreen_camera')
        if camera_name:
            redirect_url = f"fullscreen.html?camera={camera_name}"
        else:
            redirect_url = "list.html"  # Fallback

    index_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Fenetre</title>
    <meta http-equiv="refresh" content="0; url={redirect_url}" />
</head>
<body>
    <p>If you are not redirected automatically, follow this <a href="{redirect_url}">link</a>.</p>
</body>
</html>"""

    with open(os.path.join(work_dir, "index.html"), "w") as f:
        f.write(index_content)


def link_html_file(work_dir: str, global_config: dict):
    """Copies all HTML and library files to the working directory."""
    current_dir = os.getcwd()
    # Copy all html files
    for file in os.listdir(current_dir):
        if file.endswith(".html"):
            shutil.copy(os.path.join(current_dir, file), os.path.join(work_dir, file))

    # Create the lib directory if it does not exist.
    lib_dir = os.path.join(work_dir, "lib")
    if not os.path.exists(lib_dir):
        os.makedirs(lib_dir)
    
    source_lib_dir = os.path.join(current_dir, "lib")
    if os.path.exists(source_lib_dir):
        # Copy all the files in the lib directory from the current directory to the work_dir/lib directory.
        for file in os.listdir(source_lib_dir):
            if file.endswith(".js") or file.endswith(".css"):
                shutil.copy(
                    os.path.join(source_lib_dir, file),
                    os.path.join(lib_dir, file),
                )
    generate_index_html(work_dir, global_config)
