import logging

from libaccess import models

logger = logging.getLogger(__name__)



def load_access_data():
    ix = models.importer.get_index('access')
    models.importer.import_from_index(ix, 'access')


if __name__ == "__main__":
    logger.info(f"Starting appteam.cronjobs.load_access_data")
    load_access_data()
    logger.info(f"Completed appteam.cronjobs.load_access_data")

