import os

from modules.utils import get_torrent_hash

def monitor_completed(config, qb_client, logger):
  """Monitors the completed directory and removes orphaned .torrent files."""
  monitor_config = config.get_monitor_completed_config()
  is_dryrun = config.get_command_config()['dry']
  completed_dir = monitor_config['completed_dir']
  categories = monitor_config['categories']

  # Get the set of torrents in the specified categories
  logger.info(f" Getting torrents for categories: {categories}")
  torrents_in_category = qb_client.get_torrents_in_category(categories)
  logger.info(f" Loaded {len(torrents_in_category)} torrents");

  # Process .torrent files in the completed directory
  processed = 0;
  removed = 0;
  for filename in os.listdir(completed_dir):
    if filename.endswith('.torrent'):
      torrent_file_path = os.path.join(completed_dir, filename)
      torrent_hash = get_torrent_hash(torrent_file_path)
      if torrent_hash not in torrents_in_category:
        file_path = os.path.join(completed_dir, filename)
        logger.info(f" Removing {filename}")
        if not is_dryrun:
          os.remove(file_path)
          removed+=1
      processed+=1
  logger.info(f" Processed: {processed} files. Removed: {removed}")
