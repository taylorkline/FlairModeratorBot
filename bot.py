from datetime import datetime, timedelta
from textwrap import dedent
from time import sleep
import logging
import praw
import sqlite3
import sys

# the opportunity window for a user to flair before their submission
# is temporarily removed
FLAIR_BY_MINS = 2

# the amount of time before a submission is permanently removed and
# the user is encouraged to re-submit
FLAIR_DEADLINE_HRS = 24

# we won't look at posts older than this after being invited to a new subreddit
REACHBACK_HRS = 2

logger = logging.getLogger(__name__)
conn = sqlite3.connect("submissions.db")
conn.execute("""
    CREATE TABLE IF NOT EXISTS deleted_submissions (
        submission_id text NOT NULL PRIMARY KEY UNIQUE,
        bot_reply_comment_id text NOT NULL UNIQUE
    );
    """)


def main():
    try:
        run_bot()
    except Exception as e:
        logger.exception("Unhandled exception during bot execution")
        sleep(20)
    main()


def run_bot():
    reddit = authenticate()
    logger.debug(f"Authenticated as {reddit.config.username}")

    while True:
        check_new_submissions(reddit.user.moderator_subreddits())
        check_old_submissions_for_flair(reddit)
        accept_moderator_invites(reddit.inbox, reddit.user.me())


def init_logging():
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler("bot.log")
    sh = logging.StreamHandler(sys.stdout)
    fh.setLevel(logging.DEBUG)
    sh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s: %(asctime)s - %(message)s")
    fh.setFormatter(formatter)
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)


def authenticate():
    return praw.Reddit()


def check_new_submissions(moderated_subreddits):
    for moderated_subreddit in moderated_subreddits:
        for submission in moderated_subreddit.new():
            if (is_too_old(submission.created_utc)):
                break

            if (submission.link_flair_text or
                    is_too_young(submission.created_utc)):
                continue

            with conn:
                comment = submission.reply(dedent(f"""
                    This post has automatically been removed for not being
                    flaired within {FLAIR_BY_MINS} minutes. When the post
                    receives a flair, it will automatically be restored.
                    \n\n
                    If you believe this removal was in error,
                    please [contact the subreddit moderators.]
                    (https://www.reddit.com/message/compose?to=/r/{submission.subreddit})
                    ***
                    ^(FlairModerator made with 🍵 and ❤️ by)
                    ^[/u\/taylorkline](/user/taylorkline).
                    ^(Visit /r/FlairModerator for more information.)
                    """))
                try:
                    conn.execute("""INSERT INTO deleted_submissions
                                        VALUES (?, ?)
                                        """, (submission.id, comment.id))
                except sqlite3.IntegrityError:
                    logger.warn(f"Submission https://redd.it/{submission.id} already recorded"
                                " as removed, but we are removing it again."
                                " Perhaps another moderator manually approved"
                                " it or the flair was later removed.")
                    comment.delete()

                submission.mod.remove()

            logger.info(
                f"Submission https://redd.it/{submission.id} removed due to lacking flair")


def is_too_old(datetimeutc):
    return (datetime.fromtimestamp(datetimeutc) +
            timedelta(hours=REACHBACK_HRS) < datetime.now())


def is_too_young(datetimeutc):
    return (datetime.fromtimestamp(datetimeutc) +
            timedelta(minutes=FLAIR_BY_MINS) > datetime.now())


def check_old_submissions_for_flair(reddit):
    # iterate through each submission we have removed
    cur = conn.cursor()
    cur.execute("SELECT * FROM deleted_submissions")
    for submission_id, bot_comment_id in cur:
        submission = reddit.submission(id=submission_id)

        if submission.link_flair_text:
            logger.info(f"Submission https://redd.it/{submission_id} approved since being "
                        f"flaired with: {submission.link_flair_text}")
            with conn:
                conn.execute("""DELETE FROM deleted_submissions
                                    WHERE submission_id=?""",
                             (submission_id,))
                remove_bot_comment_tree(reddit.comment(id=bot_comment_id))
                submission.mod.approve()
        elif (datetime.fromtimestamp(submission.created_utc) +
              timedelta(hours=FLAIR_DEADLINE_HRS) < datetime.now()):
            logger.info(f"Removing submission https://redd.it/{submission_id} permanently as"
                        f" {FLAIR_DEADLINE_HRS} hours has elapsed.")
            with conn:
                conn.execute("""DELETE FROM deleted_submissions
                                    WHERE submission_id=?""",
                             (submission_id,))
                submission.reply(dedent(f"""
                    Your submission has been permanently removed as it was not
                    flaired within {FLAIR_DEADLINE_HRS} hours.
                    \n\n
                    Feel free to create a new post and flair it appropriately.
                    ***
                    ^(FlairModerator made with 🍵 and ❤️ by)
                    ^[/u\/taylorkline](/user/taylorkline).
                    ^(Visit /r/FlairModerator for more information.)
                    """))
                remove_bot_comment_tree(reddit.comment(id=bot_comment_id))


def remove_bot_comment_tree(bot_comment):
    bot_comment.refresh()
    bot_comment.replies.replace_more()
    comments_to_remove = bot_comment.replies.list() + [bot_comment]
    for comment_to_remove in comments_to_remove:
        comment_to_remove.mod.remove()


def accept_moderator_invites(inbox, me):
    for msg in inbox.unread(limit=5):
        msg.mark_read()
        if msg.body.startswith("**gadzooks!") and msg.subreddit is not None:
            try:
                msg.subreddit.mod.accept_invite()
            except praw.exceptions.APIException as e:
                if e.error_type != "NO_INVITE_FOUND":
                    raise e
                logger.warn(f"Attempted to accept invite but no invitation"
                            f" found. Message {msg} of type {type(msg)} with"
                            f" body: {msg.body}")

            # Verify permissions to function correctly
            for moderator in msg.subreddit.moderator():
                if moderator != me:
                    continue

                if not ("all" in moderator.mod_permissions or
                        ("flair" in moderator.mod_permissions and
                         "posts" in moderator.mod_permissions)):
                    logger.info(f"Invited to subreddit {msg.subreddit}"
                                f" but with incorrect permissions:"
                                f" {moderator.mod_permissions}."
                                f" Rejecting invitation with response.")
                    msg.subreddit.moderator.leave()
                    msg.reply("FlairModerator requires flair and"
                              " posts permissions to function correctly."
                              " The invitation has been rejected;"
                              " please re-invite with flair and posts"
                              " permissions.")
                else:
                    logger.info(f"Successfully invited as a moderator"
                                f" of subreddit: {msg.subreddit}")
                    msg.reply("/u/FlairModerator has joined your"
                              " subreddit! Please visit"
                              " /r/FlairModerator for more details"
                              " or contact /u/taylorkline for any"
                              " questions.")


if __name__ == "__main__":
    init_logging()
    main()
