import yaml

class ConfigManager:
  def __init__(self, config_file=None):
    # Default configuration
    self.config = {
      'commands': {
        'monitor_completed': False,
      },
      'qbittorrent': {
        'host': 'http://localhost:8080',
        'user': '',
        'password': ''
      },
      'monitor_completed': {
        'completed_dir': '',
        'categories': []
      }
    }

    # If a config file is provided, load it
    if config_file:
      self.load_config(config_file)

  def load_config(self, config_file):
    """Loads the configuration from a YAML file."""
    try:
      with open(config_file, 'r') as f:
        loaded_config = yaml.safe_load(f)
        self.config.update(loaded_config)
    except Exception as e:
      print(f"Error loading config file: {e}")
      raise

  def get(self, key):
    """Allows access to configuration keys."""
    return self.config.get(key, None)

  def get_command_config(self):
    """Returns the commands configuration."""
    return self.config.get('commands')

  def get_qbittorrent_config(self):
    """Returns the qBittorrent configuration."""
    return self.config.get('qbittorrent')

  def get_monitor_completed_config(self):
    """Returns the monitor completed configuration."""
    return self.config.get('monitor_completed')
