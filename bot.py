import logging
import praw
import pdb
import sqlite3
from datetime import datetime, timedelta
from textwrap import dedent

FLAIR_BY_MINS = 2
FLAIR_TIME_LIMIT_HRS = 24

logger = logging.getLogger(__name__)
conn = sqlite3.connect("submissions.db")
conn.execute("""
    CREATE TABLE IF NOT EXISTS deleted_submissions (
        submission_id text NOT NULL PRIMARY KEY UNIQUE,
        bot_reply_comment_id text NOT NULL UNIQUE
    );
    """)


def main():
    init_logging()
    reddit = authenticate()
    logger.debug(f"Authenticated as {reddit.config.username}")

    while True:
        check_new_submissions(reddit.user.moderator_subreddits())
        check_old_submissions_for_flair()
        accept_moderator_invites()


def init_logging():
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler("bot.log")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s: %(asctime)s - %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)


def authenticate():
    return praw.Reddit("FlairModerator")


def check_new_submissions(moderated_subreddits):
    for moderated_subreddit in moderated_subreddits:
        for submission in moderated_subreddit.new():
            if (submission.link_flair_text or
                    is_too_young(submission.created_utc)):
                continue

            with conn:
                comment = submission.reply(dedent(f"""
                    This post has automatically been removed for not being flaired within {FLAIR_BY_MINS} minutes.
                    When the post receives a flair it will automatically be restored.
                    \n\n
                    If you believe this removal was in error, please [contact the subreddit moderators.]
                    (https://www.reddit.com/message/compose?to=/r/{submission.subreddit})
                    ***
                    ^(FlairModerator made with 🍵 and ❤️ by) ^[/u\/taylorkline](/user/taylorkline).
                    ^(Visit /r/FlairModerator for more information.)
                    """))
                try:
                    conn.execute("""INSERT INTO deleted_submissions
                                        VALUES (?, ?)
                                        """, (submission.id, comment.id))
                except sqlite3.IntegrityError:
                    logger.warn(f"Submission {submission.id} already recorded"
                                " as removed, but we are removing it again."
                                " Perhaps another moderator manually"
                                " approved it.")
                    comment.delete()

                submission.mod.remove()

            logger.info(
                f"Submission {submission.id} removed due to lacking flair")


def is_too_young(datetimeutc):
    return (datetime.fromtimestamp(datetimeutc) +
            timedelta(minutes=FLAIR_BY_MINS) > datetime.now())


def check_old_submissions_for_flair():
    # iterate through each submission we have removed

    # Over FLAIR_TIME_LIMIT_HRS? Remove and post comment indicating time limit passed

    # Now flaired? Remove my comment and children and approve
    # note: retrieve my comment with reddit.comment(id=xxxxx)
    pass


def accept_moderator_invites():
    # invite includes flair & posts permissions, accept

    # otherwise reject and message moderators
    pass


if __name__ == "__main__":
    main()
