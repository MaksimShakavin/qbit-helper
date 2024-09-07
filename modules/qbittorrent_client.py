import logging

import qbittorrentapi

# Suppress urllib3 and qbittorrent-api warnings
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("qbittorrentapi").setLevel(logging.ERROR)

class QBitTorrentClient:
  def __init__(self, host, username, password, disable_ssl_verify):
    self.client = qbittorrentapi.Client(host=host, username=username, password=password, VERIFY_WEBUI_CERTIFICATE=disable_ssl_verify)

  def connect(self):
    """Authenticates with the qBittorrent client."""
    try:
      self.client.auth_log_in()
    except qbittorrentapi.LoginFailed:
      logging.error("Error: Failed to authenticate with qBittorrent. Please check your username and password.")
      raise
    except qbittorrentapi.exceptions.APIConnectionError:
      logging.error("Error: Failed to connect to qBittorrent. Please check the host address and ensure the service is running.")
      raise
    except Exception as e:
      logging.error(f"Error: An unexpected error occurred while connecting to qBittorrent: {e}")
      raise

  def get_torrents_in_category(self, categories):
    """Returns a set of torrent hashes in the specified categories."""
    torrents = self.client.torrents_info()
    return {torrent.hash for torrent in torrents if torrent.category in categories}
