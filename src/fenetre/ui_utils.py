import filecmp
import logging
import os
import shutil


def generate_index_html(work_dir: str, global_config: dict):
    """Generates the index.html file by copying the configured landing page."""
    logger = logging.getLogger(__name__)
    ui_config = global_config.get("ui", {})
    landing_page = ui_config.get("landing_page", "list")  # default to list

    dest_path = os.path.join(work_dir, "index.html")

    if landing_page == "fullscreen":
        camera_name = ui_config.get("fullscreen_camera")
        if not camera_name:
            logger.warning(
                "Fullscreen landing page is configured but no camera was selected. Falling back to list.html"
            )
            landing_page = "list"  # Fallback to list
        else:
            source_path = os.path.join(work_dir, "fullscreen.html")
            if not os.path.exists(source_path):
                logger.error(
                    f"fullscreen.html not found in '{work_dir}'. Cannot create index.html."
                )
                return

            with open(source_path, "r") as f:
                content = f.read()

            # Hardcode the camera name in the javascript
            content = content.replace(
                "const cameraName = urlParams.get('camera');",
                f"const cameraName = '{camera_name}';",
            )

            with open(dest_path, "w") as f:
                f.write(content)
            logger.info(
                f"Generated index.html from fullscreen.html for camera '{camera_name}'"
            )
            return

    # For map.html, list.html, or fallback from fullscreen
    source_filename = f"{landing_page}.html"
    source_path = os.path.join(work_dir, source_filename)

    if not os.path.exists(source_path):
        logger.error(
            f"Landing page '{source_filename}' not found in '{work_dir}'. Cannot create index.html."
        )
        return

    try:
        if not os.path.exists(dest_path) or not filecmp.cmp(source_path, dest_path):
            shutil.copy(source_path, dest_path)
            logger.info(f"Copied {source_filename} to index.html in {work_dir}")
        else:
            logger.debug(
                f"index.html is already a copy of {source_filename}, skipping copy."
            )
    except Exception as e:
        logger.error(f"Failed to create index.html from {source_filename}: {e}")


def copy_public_html_files(work_dir: str, global_config: dict):
    """Copies all HTML and library files to the working directory."""
    logger = logging.getLogger(__name__)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    public_html_dir = os.path.join(current_dir, "static", "public")
    # Copy all html files
    for file in os.listdir(public_html_dir):
        # if file.endswith(".html"):
        source_path = os.path.join(public_html_dir, file)
        dest_path = os.path.join(work_dir, file)
        if not os.path.exists(dest_path) or not filecmp.cmp(source_path, dest_path):
            shutil.copy(source_path, dest_path)
            logger.info(f"Copied {file} to {work_dir}")
        else:
            logger.debug(f"{file} already exists and is identical, skipping copy.")

    # Create the lib directory if it does not exist.
    lib_dir = os.path.join(work_dir, "lib")
    if not os.path.exists(lib_dir):
        os.makedirs(lib_dir)

    source_lib_dir = os.path.join(current_dir, "lib")
    if os.path.exists(source_lib_dir):
        # Copy all the files in the lib directory from the current directory to the work_dir/lib directory.
        for file in os.listdir(source_lib_dir):
            if file.endswith(".js") or file.endswith(".css"):
                source_path = os.path.join(source_lib_dir, file)
                dest_path = os.path.join(lib_dir, file)
                if not os.path.exists(dest_path) or not filecmp.cmp(
                    source_path, dest_path
                ):
                    shutil.copy(source_path, dest_path)
                    logger.info(f"Copied {file} to {lib_dir}")
                else:
                    logger.debug(
                        f"{file} already exists and is identical, skipping copy."
                    )

    generate_index_html(work_dir, global_config)
