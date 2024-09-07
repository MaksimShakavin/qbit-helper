import argparse, sys, logging
from modules.config import ConfigManager
from modules.monitor_completed import monitor_completed
from modules.qbittorrent_client import QBitTorrentClient

logger = logging.getLogger(__name__)

def main():
  logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', datefmt='%I:%M:%S %p')

  parser = argparse.ArgumentParser(description="Torrent Manager Tool")
  parser.add_argument('--config', help='Path to config file', default='/config/config.yaml')
  args = parser.parse_args()

  try:
    # Load the configuration
    config_manager = ConfigManager(config_file=args.config)

    # Load qBittorrent configuration
    qb_config = config_manager.get_qbittorrent_config()

    # Initialize qBittorrent client
    qb_client = QBitTorrentClient(qb_config['host'], qb_config['user'], qb_config['password'], qb_config['disable_ssl'])
    qb_client.connect()

    # Check the command configuration
    if config_manager.get_command_config()['monitor_completed']:
      monitor_completed(config_manager, qb_client, logger)
  except Exception as e:
    logger.error(f"Exiting {e}")

if __name__ == "__main__":
  main()
