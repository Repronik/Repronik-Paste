import errno
import shutil
import time

from sqlalchemy import or_

import config
import models
import util.cryptography
from modern_paste import session
from util.exception import *


def create_new_paste(contents, user_id=None, expiry_time=None, title=None, language=None, password=None, is_api_post=False):
    """
    Create a new paste.

    :param user_id: User ID of the paste poster
    :param contents: Contents of the paste
    :param expiry_time: Unix time at which the paste should expire (optional, default to no expiry)
    :param title: Title of the paste (optional)
    :param language: Language of the paste (optional, defaults to plain text)
    :param password: Password of the paste (optional)
    :param is_api_post: True to indicate that the post was posted externally via the API interface (optional)
    :return: An instance of models.Paste representing the newly added paste.
    """
    new_paste = models.Paste(
        user_id=user_id,
        contents=contents,
        expiry_time=int(expiry_time) if expiry_time is not None else None,
        title=title if title else 'Untitled',
        language=language or 'text',
        password_hash=util.cryptography.secure_hash(password) if password is not None else None,
        is_api_post=is_api_post,
    )
    session.add(new_paste)
    session.commit()
    return new_paste


def get_paste_by_id(paste_id, active_only=False):
    """
    Get the specified paste by ID.

    :param paste_id: Paste ID to look up
    :param active_only: Set this flag to True to only query for active and non-expired pastes
    :return: An instance of models.Paste representing the requested paste
    :raises PasteDoesNotExistException: If the paste does not exist
    """
    if active_only:
        paste = models.Paste.query.filter_by(
            paste_id=paste_id,
            is_active=True,
        ).filter(
            or_(models.Paste.expiry_time.is_(None), models.Paste.expiry_time > time.time()),
        ).first()
    else:
        paste = models.Paste.query.filter_by(
            paste_id=paste_id,
        ).first()
    if not paste:
        raise PasteDoesNotExistException(
            'No paste with paste_id {paste_id} exists, or is no longer active due to deactivation or expiry'.format(
                paste_id=paste_id
            )
        )
    return paste


def is_paste_active(paste_id):
    """
    Check if this paste is active. The paste is considered active if it exists, has not been deactivated, and has not
    expired. This procedure is more concise than attempting a try-except on get_paste_by_id.

    :param paste_id: ID of the paste to check
    :return: True if the paste is active; False otherwise
    """
    paste = models.Paste.query.filter_by(paste_id=paste_id).first()
    return paste and paste.is_active and (paste.expiry_time is None or paste.expiry_time > time.time())


def set_paste_password(paste_id, password):
    """
    Set a paste's password. This can either change a password that already exists, set a password that did not
    previously exist, or remove a password that already exists.

    :param paste_id: Paste ID for which to set the password
    :param password: New password to set for the paste, can be None to remove any existing password
    :return: An instance of models.Paste of the affected paste
    :raises PasteDoesNotExistException: If the paste does not exist
    """
    paste = get_paste_by_id(paste_id, active_only=True)
    paste.password_hash = util.cryptography.secure_hash(password) if password is not None else None
    session.commit()
    return paste


def deactivate_paste(paste_id):
    """
    Deactivate the specified paste by ID.

    :param paste_id: Paste ID to deactivate
    :return: An instance of models.Paste of the deactivated paste
    :raises PasteDoesNotExistException: If the paste does not exist
    """
    paste = get_paste_by_id(paste_id)
    paste.is_active = False
    session.commit()
    return paste


def increment_paste_views(paste_id):
    """
    Increment (by 1) the number of times this paste has been viewed.

    :param paste_id: The paste whose view count should be incremented
    :return: The models.Paste object representing the paste whose view was incremented
    :raises PasteDoesNotExistException: If the paste does not exist
    """
    paste = get_paste_by_id(paste_id)
    paste.views += 1
    session.commit()
    return paste


def get_recent_pastes(page_num, num_per_page):
    """
    Get recently posted pastes that are active and not expired. This query is intended to be used in chunks,
    indexed by page: e.g., results 0-4 appear on page 0, 5-9 appear on page 1, etc.

    :param page_num: The page number. Indexes from 0.
    :param num_per_page: The number of results to query for in this chunk (e.g., to display on this page).
    :return: A list of models.Paste objects sorted by post time (descending) that are active and not expired.
    """
    return models.Paste.query.filter_by(
        is_active=True,
    ).filter(
        or_(models.Paste.expiry_time.is_(None), models.Paste.expiry_time > time.time()),
    ).order_by(
        models.Paste.post_time.desc(),
    ).offset(
        page_num * num_per_page,
    ).limit(
        num_per_page,
    ).all()


def get_top_pastes(page_num, num_per_page):
    """
    Get the top (most viewed) pastes that are active and not expired. This query is intended to be used in chunks,
    indexed by page: e.g., results 0-4 appear on page 0, 5-9 appear on page 1, etc.

    :param page_num: The page number. Indexes from 0.
    :param num_per_page: The number of results to query for in this chunk (e.g., to display on this page).
    :return: A list of models.Paste objects sorted by number of views (descending) that are active and not expired.
    """
    return models.Paste.query.filter_by(
        is_active=True,
    ).filter(
        or_(models.Paste.expiry_time.is_(None), models.Paste.expiry_time > time.time()),
    ).order_by(
        models.Paste.views.desc(),
    ).offset(
        page_num * num_per_page,
    ).limit(
        num_per_page,
    ).all()


def get_all_pastes_for_user(user_id, active_only=False):
    """
    Gets all pastes for the specified user ID. Only return pastes that have not expired, and optionally filter by
    whether the paste is active.

    :param user_id: User ID for which to retrieve all the pastes
    :param active_only: Set this flag to True to only query for active and non-expired pastes
    :return: A list of models.Paste objects belonging to the user ID (can be an empty list)
    """
    if active_only:
        return models.Paste.query.filter_by(
            user_id=user_id,
            is_active=True,
        ).filter(
            or_(models.Paste.expiry_time.is_(None), models.Paste.expiry_time > time.time()),
        ).order_by(
            models.Paste.post_time.desc(),
        ).all()
    else:
        return models.Paste.query.filter_by(
            user_id=user_id,
        ).filter(
            or_(models.Paste.expiry_time.is_(None), models.Paste.expiry_time > time.time()),
        ).order_by(
            models.Paste.post_time.desc(),
        ).all()


def scrub_inactive_pastes():
    """
    Goes through the database and deletes all pastes that are either inactive or have expired. This method is not
    intended to be called from within the application, but rather externally either manually or via a script/cron job.

    For example, in a Python shell:
        > import database.paste
        > database.paste.scrub_inactive_pastes()
    """
    inactive_pastes = models.Paste.query.filter(or_(
        models.Paste.is_active.is_(False),
        models.Paste.expiry_time < time.time(),
    ))
    inactive_paste_ids = [paste.paste_id for paste in inactive_pastes]
    if not inactive_paste_ids:
        # No inactive pastes to scrub; quit without taking further action
        return
    inactive_attachments = models.Attachment.query.filter(
        models.Attachment.paste_id.in_(inactive_paste_ids)
    )

    # Attempt to remove the attachment files, if they exist
    for paste_id in inactive_paste_ids:
        try:
            shutil.rmtree('{attachment_dir}/{paste_id}'.format(attachment_dir=config.ATTACHMENTS_DIR, paste_id=paste_id))
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise

    # Then, delete the database entries
    inactive_pastes.delete(synchronize_session='fetch')
    inactive_attachments.delete(synchronize_session='fetch')
    session.commit()
