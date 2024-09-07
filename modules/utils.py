import hashlib
import logging

import bencodepy

def get_torrent_hash(torrent_file_path):
  """Extracts the info hash from a .torrent file."""
  try:
    with open(torrent_file_path, 'rb') as f:
      torrent_data = bencodepy.decode(f.read())
      # The 'info' field contains the metadata for the torrent
      info = torrent_data[b'info']
      # Calculate the SHA-1 hash of the bencoded info dictionary
      torrent_hash = hashlib.sha1(bencodepy.encode(info)).hexdigest().lower()
      return torrent_hash
  except FileNotFoundError:
    logging.warning(f"Error: Torrent file '{torrent_file_path}' not found.")
    return None
  except bencodepy.BencodeDecodeError:
    logging.warning(f"Error: Failed to decode torrent file '{torrent_file_path}'. It may be corrupted.")
    return None
  except Exception as e:
    logging.warning(f"Error: An unexpected error occurred while processing '{torrent_file_path}': {e}")
    return None
