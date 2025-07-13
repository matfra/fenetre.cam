import yaml
from absl import logging

def config_load(config_file_path: str) -> list[dict]:
    try:
        with open(config_file_path, "r") as f:
            config = yaml.safe_load(f)
            res = []
            # Ensure all expected sections are present, providing empty dicts if not
            # Added 'config_server' section
            for section in ["http_server", "cameras", "global", "config_server"]:
                res.append(config.get(section, {}))
            return res
    except FileNotFoundError:
        logging.error(f"Configuration file {config_file_path} not found.")
        # Provide default empty configs to prevent crashes, though app might be non-functional
        return [{}, {}, {}]
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML configuration file {config_file_path}: {e}")
        return [{}, {}, {}]
