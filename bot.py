import logging
import praw
import pdb
import sqlite3
from datetime import datetime, timedelta

FLAIR_BY_MINS = 2
FLAIR_TIME_LIMIT_HRS = 24

logger = logging.getLogger(__name__)
conn = sqlite3.connect("submissions.db")
conn.execute("""
    CREATE TABLE IF NOT EXISTS deleted_submissions (
        submission_id text NOT NULL PRIMARY KEY,
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
            # TODO: Organize no-op functions in one if-statement
            if submission.link_flair_text:
                continue

            # Post already in DB, no action
            if conn.execute("""SELECT *
                               FROM deleted_submissions
                               WHERE submission_id=?""",
                            (submission.id,)).fetchone():
                print(f"Submission {submission.id} already in db")
                continue

            if (datetime.fromtimestamp(submission.created_utc) + timedelta(minutes=FLAIR_BY_MINS) > datetime.now()):
                print("Submission too young to remove")
                continue

            # Post not flaired and older than FLAIR_BY, remove, leave comment, save in DB
            with conn:
                # TODO: More thorough reply
                comment = submission.reply("Removed")
                conn.execute("""INSERT INTO deleted_submissions VALUES (?, ?)
                    """, (submission.id, comment.id))
                submission.mod.remove()
                logger.info(
                    f"Submission {submission.id} removed due to lacking flair")


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
