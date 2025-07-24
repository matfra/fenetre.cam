import yaml
from absl import logging


def config_load(config_file_path: str) -> list[dict]:
    try:
        with open(config_file_path, "r") as f:
            config = yaml.safe_load(f)
            res = []
            for section in ["http_server", "cameras", "global", "admin_server"]:
                res.append(config.get(section, {}))
            return res
    except FileNotFoundError:
        logging.error(f"Configuration file {config_file_path} not found.")
        return [{}, {}, {}, {}]
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML configuration file {config_file_path}: {e}")
        return [{}, {}, {}, {}]
